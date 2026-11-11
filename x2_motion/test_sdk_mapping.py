import argparse,asyncio,json,re,time,unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from aiohttp.test_utils import TestClient,TestServer
from app import create_app
from capabilities import PRESETS,preset_mapping,prepare_preset_request,planner_catalog
from sdk_catalog import definition,sdk_inventory,READ_QUERIES

ROOT=Path(__file__).parent
class Coverage(unittest.TestCase):
    def test_every_saved_service_is_catalogued_with_exact_schema(self):
        manifest=json.loads((ROOT.parent/'sdk_reference/interface_manifest.json').read_text())
        self.assertEqual(manifest,{s['name']:s['sha256'] for s in definition()['services']})
        inventory=sdk_inventory({})
        self.assertEqual(inventory['summary']['service_total'],27)
        self.assertEqual(inventory['summary']['service_mapped'],12)
        self.assertTrue(all(s['handler'] or s['reason'] for s in inventory['services']))
        self.assertTrue(all(s['service_ready'] is None for s in inventory['services']))

    def test_every_installed_preset_reaches_exact_sdk_payload(self):
        path=ROOT.parent/'sdk_reference/McPresetMotion.msg'
        ids={int(x) for x in re.findall(r'int32 \w+\s*=\s*(\d+)',path.read_text(encoding='utf-8'))}
        available={n:p['motion'] for n,p in PRESETS.items() if p['motion'] in ids}
        self.assertEqual(len(available),17)
        self.assertNotIn('clap',available);self.assertNotIn('goodbye',available)
        self.assertEqual(set(planner_catalog(available)['gestures']),set(available))
        for name in available:
            with self.subTest(name=name):
                req=prepare_preset_request(Obj(motion=Obj(value=0),area=Obj(value=0),interrupt=True),name,available)
                self.assertEqual((req.motion.value,req.area.value,req.interrupt),(PRESETS[name]['motion'],PRESETS[name]['area'],False))

class Routes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        args=argparse.Namespace(offline=True,allow_control=True,allow_presets=True,allow_seat_hold=True,allow_posture_actions=True,
            origin='',operator_ready=False)
        app=create_app(args);self.d=app['dashboard'];self.client=TestClient(TestServer(app));await self.client.start_server()
        self.d.state.update(connected=True,arm_actions={'wave_right':1002,'wave_left':9999,'clap':True,'unknown':3024})
        self.d.state_at=time.monotonic()
    async def asyncTearDown(self):await self.client.close()
    async def test_only_exact_installed_mappings_are_listed(self):
        body=await (await self.client.get('/api/motions')).json()
        self.assertEqual([p['name'] for p in body['actions'][0]],['wave_right'])
        self.assertEqual(body['executor_actions'],{'wave_right':1002})
        self.d.state['connected']=False
        body=await (await self.client.get('/api/motions')).json()
        self.assertEqual(body['actions'][0],[])
        self.d.state['recorded_state']=True
        body=await (await self.client.get('/api/motions')).json()
        self.assertTrue(body['recorded']);self.assertEqual(len(body['actions'][0]),1)
    async def test_action_map_includes_movement_and_manual_postures(self):
        body=await (await self.client.get('/api/action-map')).json()
        self.assertIn('move',body['allowed_action_types']);self.assertEqual(len(body['movement']['directions']),6)
        self.assertEqual(body['manual_postures']['stand_up_from_seat']['action_desc'],'SIT_UP_DEFAULT')
        self.assertEqual(body['seat_hold']['action_desc'],'SIT_JOINT_DEFAULT')
        body=await (await self.client.get('/api/sdk-map')).json()
        self.assertEqual(body['summary']['preset_mapped'],1)
    async def test_posture_cannot_take_over_another_control_session(self):
        self.d.owner=Obj()
        self.d.state.update(fsm='SIT_JOINT_DEFAULT',fsm_status=100,mode_age_ms=0,leg_age_ms=0)
        from test_seat_and_config import seated_joints
        self.d.state['joint_values']=seated_joints()
        sent=[]
        async def send(msg):sent.append(msg)
        self.d.send=send
        response=await self.client.post('/api/postures/stand_up_from_seat',json={'confirmed':True},headers={'Origin':str(self.client.make_url('/')).rstrip('/')})
        self.assertEqual(response.status,400);self.assertEqual(sent,[]);self.d.owner=None

    async def test_supported_mode_switch_is_independent_of_locomotion_arm(self):
        self.d.state.update(fsm='SIT_JOINT_DEFAULT',fsm_status=100,ready=False,armed=False)
        self.d.state_at=time.monotonic();sent=[]
        async def send(msg):sent.append(msg)
        self.d.send=send
        origin=str(self.client.make_url('/')).rstrip('/')
        ws=await self.client.ws_connect('/ws',headers={'Origin':origin});await ws.receive_json()
        await ws.send_json(dict(action='set_mode',mode='zero_torque',confirmed=False,condition_confirmed=True))
        for _ in range(20):
            reply=await asyncio.wait_for(ws.receive_json(),2)
            if reply['type']=='error':break
        self.assertEqual(reply['type'],'error');self.assertEqual(sent,[])
        await ws.send_json(dict(action='set_mode',mode='zero_torque',confirmed=True,condition_confirmed=True))
        for _ in range(50):
            if sent:break
            await asyncio.sleep(.01)
        self.assertEqual(sent,[dict(action='set_mode',mode='zero_torque',confirmed=True,condition_confirmed=True)])
        self.assertFalse(self.d.state['armed'])
        await ws.close()

if __name__=='__main__':unittest.main()
