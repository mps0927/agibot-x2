import argparse
import asyncio
import json
import math
import unittest

from aiohttp.test_utils import TestClient, TestServer
from app import create_app
from capabilities import PRESETS, validate_velocity, validate_profile
from joint_contract import canonical_action, validate_physical_pose
from pipeline import validate_result
from control_policy import permissions,command_allowed,seat_hold_check


class Contracts(unittest.TestCase):
    def test_presets_scope_excludes_locomotion_and_unpublished_seated_mode(self):
        scopes=permissions(presets=True)
        self.assertTrue(command_allowed('gesture',scopes))
        for action,mode in [('hold',None),('set_mode','stable_stand'),('set_mode','seat_hold'),('arm_joint_pose',None)]:
            self.assertFalse(command_allowed(action,scopes,mode))
        self.assertFalse(command_allowed('set_mode',permissions(full=True),'seat_hold'))
        self.assertEqual(seat_hold_check('SIT_JOINT_DEFAULT',.2),'ALREADY_ACTIVE')
        for mode,age in [('STAND_DEFAULT',.1),('PASSIVE_DEFAULT',.1),('SIT_JOINT_DEFAULT',3),('SIT_JOINT_DEFAULT',None)]:
            with self.assertRaises(ValueError):seat_hold_check(mode,age)

    def test_x2_elbow_direction_and_unknown_g1_name(self):
        target=dict(type='arm_joint_pose',object='robot_joint',destination='none',joints={'left_elbow_joint':-1.0},seconds=1.)
        self.assertEqual(canonical_action(target)[0]['joints']['left_elbow_joint'],-1.)
        with self.assertRaises(ValueError):canonical_action(dict(target,joints={'left_elbow':1.0}))
        with self.assertRaises(ValueError):canonical_action(dict(target,joints={'left_elbow_joint':1.0}))
        with self.assertRaises(ValueError):validate_physical_pose(target)

    def test_nonfinite_and_unbounded_movement_rejected(self):
        for vector in ([math.nan,0,0],[True,0,0],[.31,0,0]):
            with self.assertRaises(ValueError):validate_velocity(vector)
        for seconds in (None,0,6,math.inf):
            with self.assertRaises(ValueError):validate_result(dict(scene='test',actions=[dict(type='move',velocity=[.1,0,0],seconds=seconds)]))
        with self.assertRaises(ValueError):validate_profile(dict(forward_mps=.1,lateral_mps=.1,yaw_rps=.1,burst_seconds=0))

    def test_documented_preset_combinations_and_manual_mode_boundary(self):
        self.assertEqual(len(PRESETS),29)
        self.assertEqual(PRESETS['wave_left']['area'],1)
        self.assertEqual(PRESETS['wave_right']['area'],2)
        with self.assertRaises(ValueError):validate_result(dict(scene='test',actions=[dict(type='mode',name='zero_torque')]))
        with self.assertRaises(ValueError):validate_result(dict(scene='test',actions=[dict(type='gesture',name='unlisted')]),{'wave_left':1002})


class ReadOnlyBoundary(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        args=argparse.Namespace(offline=True,read_only=True,allow_control=False,origin='',operator_ready=False,camera_port=18013,simulation=False)
        self.application=create_app(args)
        self.client=TestClient(TestServer(self.application))
        await self.client.start_server()
        self.origin=str(self.client.make_url('/')).rstrip('/')
        self.dashboard=self.application['dashboard']
        self.sent=[]
        async def record(msg):self.sent.append(msg)
        self.dashboard.send=record
        self.dashboard.state.update(connected=True,ready=True,fsm='STAND_DEFAULT',arm_actions={'wave_left':1002})
        self.dashboard.state_at=__import__('time').monotonic()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_crafted_browser_commands_cannot_bypass_readonly(self):
        ws=await self.client.ws_connect('/ws',headers={'Origin':self.origin})
        await ws.receive_json()
        for action in ('arm','hold','gesture','custom_motion','set_mode','plan_step','plan_execute','joint_execute'):
            await ws.send_json(dict(action=action,confirmed=True,name='wave_left',mode='zero_torque'))
            message=await asyncio.wait_for(ws.receive_json(),2)
            while message.get('type')=='state':
                message=await asyncio.wait_for(ws.receive_json(),2)
            self.assertEqual(message['type'],'error',action)
        self.assertEqual(self.sent,[])
        await ws.close()

    async def test_cross_origin_mutations_and_websocket_rejected(self):
        response=await self.client.post('/api/joints/preview',json={},headers={'Origin':'https://untrusted.example'})
        self.assertEqual(response.status,403)
        from aiohttp import WSServerHandshakeError
        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect('/ws',headers={'Origin':'https://untrusted.example'})
        self.assertEqual(self.sent,[])

    async def test_catalog_preview_and_no_fake_camera(self):
        response=await self.client.get('/api/motions');data=await response.json()
        self.assertEqual([p['name'] for p in data['actions'][0]],['wave_left'])
        self.assertFalse(data['preset_execution_verified'])
        response=await self.client.post('/api/joints/preview',json=dict(joints={'left_elbow_joint':-1.},seconds=1.),headers={'Origin':self.origin})
        self.assertEqual(response.status,200)
        self.assertFalse((await response.json())['executable'])
        response=await self.client.post('/api/capture',json={},headers={'Origin':self.origin})
        self.assertEqual(response.status,400)
        self.assertEqual(self.sent,[])

    async def test_seated_status_never_dispatches_control(self):
        self.dashboard.state.update(fsm='SIT_JOINT_DEFAULT',mode_age_ms=10)
        response=await self.client.post('/api/seat-hold',json={},headers={'Origin':self.origin})
        self.assertEqual(response.status,200)
        self.assertEqual((await response.json())['status'],'ALREADY_ACTIVE')
        self.dashboard.state['fsm']='PASSIVE_DEFAULT'
        response=await self.client.post('/api/seat-hold',json={},headers={'Origin':self.origin})
        self.assertEqual(response.status,400)
        self.assertIn('지지', (await response.json())['error'])
        self.assertEqual(self.sent,[])

    async def test_camera_is_fixed_at_30_without_configuration_endpoint(self):
        response=await self.client.get('/api/config')
        self.assertEqual((await response.json())['camera_fps'],30)
        response=await self.client.post('/api/settings/camera',json={'fps':15},headers={'Origin':self.origin})
        self.assertEqual(response.status,404)
        self.assertEqual(self.sent,[])
        self.assertTrue(self.dashboard.args.read_only)

    async def test_vlm_plan_roundtrip_stays_readonly(self):
        from aiohttp import web
        seen=[]
        async def provider(request):
            seen.append(await request.json())
            return web.json_response(dict(scene='테스트 장면',explanation='왼손 인사 제안',
                plan_status='ready',decision_reason='계약 검증용 응답',
                actions=[dict(type='gesture',name='wave_left',seconds=2.,reason='테스트')]))
        mock=web.Application();mock.router.add_post('/plan',provider)
        mock_server=TestServer(mock);await mock_server.start_server()
        self.dashboard.pipeline.endpoint=str(mock_server.make_url('/plan'))
        try:
            response=await self.client.post('/api/infer',json=dict(instruction='왼손 인사 계획을 보여줘'),headers={'Origin':self.origin})
            data=await response.json()
            self.assertEqual(response.status,200,data)
            self.assertEqual(data['actions'][0]['name'],'wave_left')
            self.assertFalse(data['executable'])
            self.assertEqual(seen[0]['robot_state']['fsm'],'STAND_DEFAULT')
            self.assertTrue(seen[0]['robot_state']['read_only'])
            self.assertEqual(self.sent,[])
        finally:await mock_server.close()


class ScopedTransport(unittest.IsolatedAsyncioTestCase):
    async def test_preset_only_transport_rejects_other_control(self):
        from app import X2Dashboard
        import time
        args=argparse.Namespace(offline=True,read_only=False,allow_control=False,allow_presets=True,origin='',operator_ready=False,camera_port=18013,simulation=False)
        dashboard=X2Dashboard(args)
        sent=[]
        class Input:
            def write(self,body):sent.append(json.loads(body))
            async def drain(self):pass
        class Process:
            returncode=None
            stdin=Input()
        dashboard.process=Process()
        dashboard.state.update(connected=True,ready=True,fsm='STAND_DEFAULT',arm_actions={'wave_left':1002})
        dashboard.state_at=time.monotonic()
        for msg in (dict(action='hold',direction='forward'),dict(action='set_mode',mode='stable_stand'),dict(action='set_mode',mode='seat_hold'),dict(action='gesture',name='heart_both'),dict(action='arm_joint_pose')):
            with self.assertRaises(ValueError):await dashboard.send(msg)
        self.assertEqual(sent,[])
        await dashboard.send(dict(action='gesture',name='wave_left'))
        self.assertEqual(len(sent),1)
        self.assertEqual(sent[0]['name'],'wave_left')
        self.assertIn('request_id',sent[0])

if __name__=='__main__':unittest.main()
