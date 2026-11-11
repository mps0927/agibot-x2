"""VLM -> local server -> fake worker -> SDK request contract. No robot I/O."""
import argparse,asyncio,json,time,unittest
from types import SimpleNamespace as Obj
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from app import create_app
from capabilities import preset_mapping,prepare_preset_request,planner_catalog
from control_policy import permissions,validate_plan_execution
from pipeline import validate_result
from x2_worker import finish_native_request

class MappingContract(unittest.TestCase):
    def test_binding_and_sdk_payload_are_canonical(self):
        self.assertEqual(set(preset_mapping({'wave_right':1002,'wave_left':9999,'bow':True})),{'wave_right'})
        action=validate_result(dict(scene='test',plan_status='ready',actions=[dict(type='gesture',name='wave_right')]),{'wave_right':1002})['actions'][0]
        req=prepare_preset_request(Obj(motion=Obj(value=0),area=Obj(value=0),interrupt=True),action['name'],{'wave_right':1002})
        self.assertEqual((req.motion.value,req.area.value,req.interrupt),(1002,2,False))
        with self.assertRaises(ValueError):prepare_preset_request(req,'wave_left',{'wave_right':1002})

    def test_model_cannot_supply_sdk_fields_or_combine_native_actions(self):
        for actions in ([dict(type='gesture',name='wave_right',motion=3001)],
                        [dict(type='gesture',name='wave_right'),dict(type='stop')],
                        [dict(name='wave_right')],
                        [dict(type='gesture',name='wave_left')]):
            with self.assertRaises(ValueError):validate_result(dict(scene='test',actions=actions),{'wave_right':1002})
        scopes=permissions(presets=True)
        catalog=planner_catalog({'wave_right':1002},control_permissions=scopes)
        self.assertEqual(catalog['moves'],{})
        with self.assertRaises(ValueError):
            validate_result(dict(scene='test',actions=[dict(type='move',velocity=[.1,0,0],seconds=1.)]),control_permissions=scopes)

    def test_execution_rechecks_age_mode_version_catalog_and_busy_state(self):
        now=time.monotonic()
        plan=dict(created=now,fsm='STAND_DEFAULT',sdk_version='test-sdk')
        state=dict(connected=True,fsm='STAND_DEFAULT',fsm_status=100,sdk_version='test-sdk',arm_actions={'wave_right':1002})
        actions=[dict(type='gesture',name='wave_right',action_id=1002)]
        validate_plan_execution(plan,actions,state,.1,permissions(presets=True),now)
        changes=[dict(fsm='SIT_JOINT_DEFAULT'),dict(fsm_status=200),dict(sdk_version='different'),
                 dict(arm_actions={'wave_right':123}),dict(gesture='bow'),dict(connected=False)]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_plan_execution(plan,actions,dict(state,**change),.1,permissions(presets=True),now)
        with self.assertRaises(ValueError):validate_plan_execution(plan,actions,state,.1,permissions(presets=True),now+31)
        with self.assertRaises(ValueError):validate_plan_execution(plan,actions,state,2.,permissions(presets=True),now)

class VLMDispatch(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        args=argparse.Namespace(offline=True,read_only=False,allow_control=False,allow_presets=True,origin='',operator_ready=False)
        self.application=create_app(args);self.d=self.application['dashboard']
        self.client=TestClient(TestServer(self.application));await self.client.start_server()
        self.origin=str(self.client.make_url('/')).rstrip('/')
        self.commands=[];self.sdk=[];self.provider_requests=[];self.sdk_reply_state=1
        self.reply=dict(scene='사람이 있음',plan_status='ready',explanation='오른손 인사',decision_reason='테스트',actions=[dict(type='gesture',name='wave_right')])
        async def provider(request):
            self.provider_requests.append(await request.json());return web.json_response(self.reply)
        mock=web.Application();mock.router.add_post('/plan',provider)
        self.provider=TestServer(mock);await self.provider.start_server();self.d.pipeline.endpoint=str(self.provider.make_url('/plan'))
        self.d.state.update(connected=True,ready=True,fsm='STAND_DEFAULT',fsm_status=100,sdk_version='test-sdk',arm_actions={'wave_right':1002})
        self.d.state_at=time.monotonic()
        outer=self
        class Input:
            def write(self,body):
                msg=json.loads(body);outer.commands.append(msg)
                if msg['action']=='arm':outer.d.state['armed']=True
                elif msg['action']=='gesture':
                    req=prepare_preset_request(Obj(motion=Obj(value=0),area=Obj(value=0),interrupt=True),msg['name'],outer.d.state['arm_actions'])
                    outer.sdk.append(dict(motion=req.motion.value,area=req.area.value,interrupt=req.interrupt))
                    outer.d.state.update(gesture=msg['name'],arm_pending=True,native_result=None)
                    def reply():
                        finish_native_request(outer.d.state,msg,0,outer.sdk_reply_state,'SetMcPresetMotion',lambda *args,**kwargs:None)
                        outer.d.state_at=time.monotonic()
                    asyncio.get_running_loop().call_later(.08,reply)
                outer.d.state_at=time.monotonic()
            async def drain(self):pass
        self.d.process=Obj(returncode=None,stdin=Input())

    async def asyncTearDown(self):
        await self.d.cancel_plan();self.d.owner=None;self.d.process=None
        await self.client.close();await self.provider.close()

    async def infer(self):
        r=await self.client.post('/api/infer',json={'instruction':'오른손 흔들어'},headers={'Origin':self.origin})
        return r,await r.json()

    async def receive_error(self,ws):
        for _ in range(20):
            v=await asyncio.wait_for(ws.receive_json(),2)
            if v['type']=='error':return v
        self.fail('Expected an error')

    async def test_model_plan_dispatches_once_releases_on_sdk_reply_and_rejects_replay(self):
        response,plan=await self.infer();self.assertEqual(response.status,200,plan)
        self.assertTrue(plan['executable']);self.assertEqual(plan['sdk_requests'][0]['area'],2)
        self.assertEqual(self.provider_requests[0]['capabilities']['moves'],{})
        ws=await self.client.ws_connect('/ws',headers={'Origin':self.origin});await ws.receive_json()
        await ws.send_json(dict(action='plan_execute',plan_id=plan['plan_id'],confirmed=True))
        for _ in range(80):
            if self.sdk:break
            await asyncio.sleep(.01)
        self.assertEqual(self.sdk,[dict(motion=1002,area=2,interrupt=False)])
        self.assertEqual(self.d.state['gesture'],'wave_right')
        self.assertFalse(self.d.plan_task.done())
        await asyncio.wait_for(self.d.plan_task,2)
        self.assertIsNone(self.d.state['gesture'])
        self.assertFalse(self.d.state['arm_pending'])
        self.assertTrue(self.d.state['native_result']['accepted'])
        self.assertNotIn('acknowledge_motion_complete',[m['action'] for m in self.commands])
        await ws.send_json(dict(action='plan_execute',plan_id=plan['plan_id'],confirmed=True))
        error=await self.receive_error(ws)
        self.assertIn('이미 실행',error['message']);self.assertEqual(len(self.sdk),1)
        await ws.close()

    async def test_sdk_failure_ends_plan_and_surfaces_rejection(self):
        self.sdk_reply_state=2
        _,plan=await self.infer()
        ws=await self.client.ws_connect('/ws',headers={'Origin':self.origin});await ws.receive_json()
        await ws.send_json(dict(action='plan_execute',plan_id=plan['plan_id'],confirmed=True))
        for _ in range(100):
            if self.d.plan_task and self.d.plan_task.done():break
            await asyncio.sleep(.01)
        self.assertTrue(self.d.plan_task.done())
        self.assertEqual(self.d.pipeline_status['stage'],'rejected')
        self.assertIsNone(self.d.state['gesture']);self.assertFalse(self.d.state['native_result']['accepted'])
        self.assertEqual(len(self.sdk),1)
        await ws.close()

    async def test_next_preset_needs_no_manual_completion_message(self):
        ws=await self.client.ws_connect('/ws',headers={'Origin':self.origin});await ws.receive_json()
        for _ in range(2):
            _,plan=await self.infer()
            previous=self.d.plan_task
            await ws.send_json(dict(action='plan_execute',plan_id=plan['plan_id'],confirmed=True))
            for _ in range(100):
                if self.d.plan_task is not previous:break
                await asyncio.sleep(.01)
            await asyncio.wait_for(self.d.plan_task,2)
        self.assertEqual(len(self.sdk),2)
        self.assertEqual(sum(m['action']=='gesture' for m in self.commands),2)
        await ws.close()

    async def test_mode_change_after_inference_blocks_dispatch(self):
        _,plan=await self.infer()
        self.d.state.update(fsm='SIT_JOINT_DEFAULT',ready=True)
        ws=await self.client.ws_connect('/ws',headers={'Origin':self.origin});await ws.receive_json()
        await ws.send_json(dict(action='plan_execute',plan_id=plan['plan_id'],confirmed=True))
        error=await self.receive_error(ws);self.assertIn('안정 서기',error['message'])
        self.assertEqual(self.sdk,[]);self.assertEqual(self.commands,[])
        await ws.close()

    async def test_unmapped_model_response_is_not_executable(self):
        self.reply['actions']=[dict(type='gesture',name='invented_motion')]
        response,result=await self.infer();self.assertEqual(response.status,422,result)
        self.assertEqual(self.commands,[])
        response=await self.client.get('/api/action-map');data=await response.json()
        self.assertEqual(data['mappings']['wave_right']['motion'],1002)
        self.assertFalse(data['physical_execution_verified'])

if __name__=='__main__':unittest.main()
