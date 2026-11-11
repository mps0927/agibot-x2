import argparse,asyncio,base64,io,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from PIL import Image
from app import create_app
from posture_actions import prepare_posture_request,validate_posture_request
from control_policy import permissions,command_allowed
from test_seat_and_config import seated_joints

class PostureContract(unittest.TestCase):
    def test_actual_mc_log_mapping_and_preconditions(self):
        for name,target in [('stand_up_from_seat','SIT_UP_DEFAULT'),('sit_down','SIT_DOWN_DEFAULT')]:
            req=prepare_posture_request(Obj(source='',command=Obj(action_desc='')),name,'test_source')
            self.assertEqual(req.command.action_desc,target);self.assertEqual(req.source,'test_source')
        self.assertEqual(validate_posture_request('stand_up_from_seat','SIT_JOINT_DEFAULT',100,.1,.1,seated_joints(),True),'REQUEST_ALLOWED')
        for mode,status,support in [('PASSIVE_DEFAULT',100,True),('SIT_JOINT_DEFAULT',200,True),('SIT_JOINT_DEFAULT',100,False)]:
            with self.assertRaises(ValueError):validate_posture_request('stand_up_from_seat',mode,status,.1,.1,seated_joints(),support)
        self.assertEqual(validate_posture_request('sit_down','STAND_DEFAULT',100,.1,.1,seated_joints(),True),'REQUEST_ALLOWED')
        self.assertTrue(command_allowed('hold',permissions(full=True,postures=True)))
        self.assertTrue(command_allowed('posture',permissions(postures=True)))
        self.assertFalse(command_allowed('posture',permissions(presets=True)))

class RecordAndRoute(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        args=argparse.Namespace(offline=True,read_only=False,allow_control=True,allow_presets=True,allow_seat_hold=True,allow_posture_actions=True,
            origin='',operator_ready=False,vlm_record_root=Path(self.tmp.name))
        self.application=create_app(args);self.d=self.application['dashboard'];self.sent=[]
        async def send(msg):self.sent.append(msg)
        self.d.send=send
        self.client=TestClient(TestServer(self.application));await self.client.start_server()
        self.origin=str(self.client.make_url('/')).rstrip('/')
        self.d.state.update(connected=True,ready=True,fsm='SIT_JOINT_DEFAULT',fsm_status=100,mode_age_ms=10,leg_age_ms=10,joint_values=seated_joints(),sdk_version='test')
        self.d.state_at=time.monotonic()
        async def provider(request):
            self.provider_input=await request.json()
            return web.json_response(dict(scene='시험 영상',plan_status='analysis_only',explanation='관찰만',decision_reason='시험',actions=[]))
        mock=web.Application();mock.router.add_post('/plan',provider)
        self.provider=TestServer(mock);await self.provider.start_server();self.d.pipeline.endpoint=str(self.provider.make_url('/plan'))
    async def asyncTearDown(self):
        await self.client.close();await self.provider.close();self.tmp.cleanup()

    async def test_posture_http_calls_real_named_worker_action_once_and_preserves_mode_checks(self):
        response=await self.client.post('/api/postures/stand_up_from_seat',json={'confirmed':True},headers={'Origin':self.origin})
        self.assertEqual(response.status,202);self.assertEqual(self.sent,[dict(action='posture',name='stand_up_from_seat',confirmed=True)])
        self.d.state['fsm']='STAND_DEFAULT'
        response=await self.client.post('/api/postures/stand_up_from_seat',json={},headers={'Origin':self.origin})
        self.assertEqual((await response.json())['status'],'ALREADY_ACTIVE');self.assertEqual(len(self.sent),1)
        response=await self.client.post('/api/postures/sit_down',json={'confirmed':True},headers={'Origin':self.origin})
        self.assertEqual(response.status,202);self.assertEqual(self.sent[-1]['name'],'sit_down')

    async def test_every_vlm_request_has_its_own_exact_input_image_and_response(self):
        image=Image.new('RGB',(16,12),(30,100,180));buffer=io.BytesIO();image.save(buffer,format='JPEG');jpeg=buffer.getvalue()
        frame=self.d.store_frame(jpeg,dict(source='Uploaded POV'))
        recordings=[]
        for _ in range(2):
            response=await self.client.post('/api/infer',json=dict(instruction='관찰만',frame_id=frame['frame_id']),headers={'Origin':self.origin})
            result=await response.json();self.assertEqual(response.status,200,result)
            folder=Path(result['recording']['directory']);recordings.append(folder)
            self.assertEqual((folder/'input.jpg').read_bytes(),jpeg)
            sent_image=self.provider_input['observation']['image'].split(',',1)[1]
            self.assertEqual(base64.b64decode(sent_image),jpeg)
            self.assertTrue((folder/'model_response.json').exists());self.assertTrue((folder/'result.json').exists())
            self.assertEqual(json.loads((folder/'instruction.json').read_text(encoding='utf-8'))['instruction'],'관찰만')
        self.assertNotEqual(*recordings);self.assertEqual(self.sent,[])

class ReplayMode(unittest.IsolatedAsyncioTestCase):
    async def test_saved_vision_is_usable_without_ssh_or_hardware_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);buffer=io.BytesIO();Image.new('RGB',(8,8),'blue').save(buffer,format='JPEG')
            (root/'rgb.jpg').write_bytes(buffer.getvalue())
            (root/'state.json').write_text(json.dumps(dict(fsm='STAND_DEFAULT',ready=True,connected=True,events=[],pipeline_status={},arm_actions={'wave_right':1002})),encoding='utf-8')
            (root/'frame.json').write_text(json.dumps(dict(captured_at=1.,sensor_frame=7)),encoding='utf-8')
            args=argparse.Namespace(offline=False,read_only=False,allow_control=True,allow_presets=True,allow_posture_actions=True,allow_seat_hold=True,
                replay=str(root),origin='',operator_ready=False)
            application=create_app(args);d=application['dashboard']
            async def forbidden():raise AssertionError('Replay attempted SSH')
            d.connect_worker=forbidden
            client=TestClient(TestServer(application));await client.start_server()
            try:
                config=await (await client.get('/api/config')).json()
                self.assertEqual(config['mode'],'replay');self.assertTrue(config['read_only'])
                self.assertFalse(any(config['control_permissions'].values()))
                self.assertFalse(d.state['connected']);self.assertFalse(d.state['ready']);self.assertIsNone(d.process)
                ws=await client.ws_connect('/ws',headers={'Origin':str(client.make_url('/')).rstrip('/')})
                state=await asyncio.wait_for(ws.receive_json(),2)
                self.assertEqual(state['fsm'],'STAND_DEFAULT');self.assertTrue(state['recorded_state'])
                self.assertFalse(state['connected']);await ws.close()
                response=await client.post('/api/capture',json={},headers={'Origin':str(client.make_url('/')).rstrip('/')})
                self.assertEqual(response.status,200);self.assertTrue((await response.json())['recorded'])
            finally:await client.close()

if __name__=='__main__':unittest.main()
