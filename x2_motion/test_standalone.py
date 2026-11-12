"""Single-host operation against a local SSH/SFTP robot fixture; no hardware."""
import argparse,asyncio,base64,io,json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import asyncssh
from aiohttp.test_utils import TestClient,TestServer
from PIL import Image
from app import create_app
from configuration import ROOT,ssh_options
from worker_deploy import WORKER_FILES

class DirectRobotConnection(unittest.IsolatedAsyncioTestCase):
    async def test_ssh_failure_keeps_the_direct_reconnection_loop_running(self):
        with tempfile.TemporaryDirectory() as directory:
            args=argparse.Namespace(offline=False,allow_control=False,allow_presets=False,allow_seat_hold=False,
                allow_posture_actions=False,origin='',operator_ready=False,env_file=str(Path(directory)/'empty.env'))
            application=create_app(args);dashboard=application['dashboard'];dashboard.reconnect_delay=.01;attempts=[]
            async def fail():
                attempts.append(1);raise asyncssh.ConnectionLost('local connection fixture')
            dashboard.connect_worker=fail
            buffer=io.BytesIO();Image.new('RGB',(8,8),'blue').save(buffer,format='JPEG')
            jpeg=buffer.getvalue();uploaded=dashboard.store_frame(jpeg,dict(source='Uploaded POV'))
            client=TestClient(TestServer(application));await client.start_server()
            try:
                for _ in range(100):
                    if len(attempts)>=2:break
                    await asyncio.sleep(.01)
                self.assertGreaterEqual(len(attempts),2)
                self.assertFalse(dashboard.tasks[0].done());self.assertFalse(dashboard.state['connected'])
                image=await self.client_frame(client,uploaded['url'])
                self.assertEqual(image,jpeg)
            finally:await client.close()

    @staticmethod
    async def client_frame(client,url):
        response=await client.get(url)
        if response.status!=200:raise AssertionError('Uploaded image disappeared during connection retries')
        return await response.read()

    async def test_this_host_deploys_worker_and_receives_state_and_rgb_over_one_ssh_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);key=asyncssh.generate_private_key('ssh-ed25519');commands=[];received=[]
            class Robot(asyncssh.SSHServer):
                def begin_auth(self,username):return True
                def password_auth_supported(self):return True
                def validate_password(self,username,password):return username=='robot' and password=='local-fixture'
            buf=io.BytesIO();Image.new('RGB',(16,12),'blue').save(buf,format='JPEG');jpeg=buf.getvalue()
            async def process(worker):
                commands.append(worker.command)
                state=dict(type='state',fsm='PASSIVE_DEFAULT',fsm_status=100,ready=False,armed=False,moving=False,
                    sdk_version='fixture-sdk',arm_actions={'wave_right':1002},joint_values={})
                camera=dict(type='camera_frame',jpeg=base64.b64encode(jpeg).decode(),at=time.time(),sequence=1,
                    frame_id='test-camera',source_hz=30,preview_fps=30)
                worker.stdout.write((json.dumps(state)+'\n'+json.dumps(camera)+'\n').encode())
                async for line in worker.stdin:
                    command=json.loads(line);received.append(command)
                    if command.get('action')=='lidar_frame_request':
                        frame=dict(type='lidar_frame',topic='/aima/hal/sensor/lidar_chest_front/lidar_pointcloud',
                            frame_request_id=command['request_id'],frame_id='lidar_chest_front',sequence=1,generation=1,
                            stamp=dict(sec=1,nanosec=0),points_total=1,points=[[1.,2.,3.]],source_age_ms=0)
                        worker.stdout.write((json.dumps(frame)+'\n').encode())
                worker.exit(0)
            server=await asyncssh.create_server(Robot,'127.0.0.1',0,server_host_keys=[key],process_factory=process,
                sftp_factory=lambda channel:asyncssh.SFTPServer(channel,chroot=directory),encoding=None)
            port=server.get_port();known=root/'known_hosts'
            known.write_bytes(('[127.0.0.1]:'+str(port)+' ').encode()+key.export_public_key())
            settings=dict(X2_SSH_HOST='127.0.0.1',X2_SSH_USER='robot',X2_SSH_PASSWORD='local-fixture',
                X2_SSH_KNOWN_HOSTS=str(known),X2_REMOTE_HOME='/home/robot',X2_REMOTE_SDK='/home/robot/aimdk')
            try:
                with patch.dict(os.environ,settings):
                    options=dict(ssh_options(),port=port,client_keys=[])
                    self.assertIsNone(options['config']);self.assertIsNone(options['tunnel'])
                    args=argparse.Namespace(offline=False,allow_control=False,allow_presets=False,allow_seat_hold=False,
                        allow_posture_actions=False,origin='',operator_ready=False,env_file=str(root/'empty.env'))
                    with patch('app.ssh_options',return_value=options):
                        application=create_app(args);dashboard=application['dashboard'];dashboard.capture_root=root/'captures'
                        dashboard.reconnect_delay=.01;attempts=[];original_connect=dashboard.connect_worker
                        async def connect_later():
                            attempts.append(1)
                            if len(attempts)<3:raise asyncssh.ConnectionLost('robot not plugged in yet')
                            return await original_connect()
                        dashboard.connect_worker=connect_later
                        client=TestClient(TestServer(application));await client.start_server()
                        try:
                            for _ in range(100):
                                if dashboard.state.get('connected') and dashboard.latest_jpeg and dashboard.lidar.ready(True):break
                                await asyncio.sleep(.02)
                            self.assertTrue(dashboard.state.get('connected'));self.assertEqual(dashboard.latest_jpeg,jpeg)
                            self.assertGreaterEqual(len(attempts),3);self.assertFalse(dashboard.state['armed'])
                            ws=await client.ws_connect('/ws',headers={'Origin':str(client.make_url('/')).rstrip('/')})
                            live_state=await ws.receive_json()
                            self.assertTrue(live_state['connected'])
                            self.assertGreaterEqual(live_state['received_age_ms'],0)
                            self.assertLess(live_state['received_age_ms'],1500)
                            await ws.close()
                            config=await (await client.get('/api/config')).json()
                            self.assertEqual(config['mode'],'ssh-direct');self.assertEqual(config['robot'],'127.0.0.1')
                            response=await client.post('/api/capture',json={},headers={'Origin':str(client.make_url('/')).rstrip('/')})
                            self.assertEqual(response.status,200);self.assertEqual(len(commands),1)
                            self.assertTrue(received);self.assertTrue(all(x['action']=='lidar_frame_request' for x in received))
                            frame=await (await client.get('/api/lidar/frame')).json()
                            self.assertEqual(frame['points'],[[1.,2.,3.]])
                            self.assertIn('/home/robot/aimdk/install/setup.bash',commands[0])
                            self.assertIn('X2_ALLOW_CONTROL=0',commands[0])
                            deployed=root/'home/robot/agibot_dashboard'
                            self.assertEqual({p.name for p in deployed.iterdir()},set(WORKER_FILES))
                            self.assertFalse((deployed/'.env').exists())
                        finally:await client.close()
            finally:server.close();await server.wait_closed()

class LocalBoundary(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.sent=[]
        args=argparse.Namespace(offline=True,allow_control=True,allow_presets=True,allow_seat_hold=True,
            allow_posture_actions=True,origin='',operator_ready=False,env_file=str(Path(self.tmp.name)/'empty.env'),
            vlm_record_root=Path(self.tmp.name)/'runs')
        application=create_app(args);self.d=application['dashboard']
        async def send(msg):self.sent.append(msg)
        self.d.send=send;self.d.state.update(connected=True,ready=True,fsm='STAND_DEFAULT');self.d.state_at=time.monotonic()
        self.client=TestClient(TestServer(application));await self.client.start_server()
        self.origin=str(self.client.make_url('/')).rstrip('/')
    async def asyncTearDown(self):await self.client.close();self.tmp.cleanup()
    async def test_lidar_polling_resumes_after_an_ssh_write_disconnect(self):
        self.d.state['connected']=True;self.d.state_at=time.monotonic()
        sent=[]
        async def send(dashboard,message):
            sent.append(message)
            if len(sent)==1:raise asyncssh.ConnectionLost('fixture disconnected while writing')
            dashboard.closing=True
        with patch('dashboard_base.Dashboard.send',new=send):
            await asyncio.wait_for(self.d.poll_lidar(),2)
        self.assertEqual(len(sent),2)
        self.assertTrue(all(message['action']=='lidar_frame_request' for message in sent))
        self.assertNotEqual(sent[0]['request_id'],sent[1]['request_id'])
    async def test_lidar_request_never_connects_to_a_separate_local_bridge(self):
        with patch.object(self.d.session,'get',Mock(side_effect=AssertionError('Unexpected sidecar connection'))) as get:
            response=await self.client.post('/api/infer',json={'instruction':'관찰','include_lidar':True},headers={'Origin':self.origin})
            self.assertEqual(response.status,400);self.assertIn('LiDAR',(await response.json())['error']);get.assert_not_called()
    async def test_lidar_topic_is_changed_only_after_worker_accepts(self):
        old=self.d.lidar.topic;target='/sensor/lidar/points'
        self.d.state.update(connected=True);self.d.state_at=time.monotonic()
        self.d.state['lidar']={'available_topics':[target]}
        async def reject(msg):self.d.lidar_event(dict(event='lidar_subscription_error',request_id=msg['request_id'],error='failed'))
        self.d.send=reject
        response=await self.client.post('/api/lidar/topic',json={'topic':target},headers={'Origin':self.origin})
        self.assertEqual(response.status,400);self.assertEqual(self.d.lidar.topic,old)
        async def accept(msg):self.d.lidar_event(dict(event='lidar_subscription',request_id=msg['request_id']))
        self.d.send=accept
        response=await self.client.post('/api/lidar/topic',json={'topic':target},headers={'Origin':self.origin})
        self.assertEqual(response.status,200);self.assertEqual(self.d.lidar.topic,target)
    async def test_old_joint_environment_flags_cannot_enable_a_foreign_adapter(self):
        settings={name:'1' for name in ('X2_ALLOW_FIELD','X2_ALLOW_JOINT_POSE','X2_ALLOW_WHOLE_BODY_JOINT_POSE','X2_ALLOW_ROS2_CONTROL')}
        with patch.dict(os.environ,settings):
            config=await (await self.client.get('/api/config')).json();self.assertFalse(config['joint_pose_enabled'])
            ws=await self.client.ws_connect('/ws',headers={'Origin':self.origin});await ws.receive_json()
            await ws.send_json({'action':'joint_execute','confirmed':True,'support_confirmed':True})
            response=await asyncio.wait_for(ws.receive_json(),2)
            while response.get('type')=='state':response=await asyncio.wait_for(ws.receive_json(),2)
            self.assertEqual(response['type'],'error');self.assertIn('미리보기',response['message']);self.assertEqual(self.sent,[])
            await ws.close()

class CheckoutIsolation(unittest.TestCase):
    def test_checkout_uses_its_own_explicit_config_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);checkout=root/'independent device';app=checkout/'x2_motion';app.mkdir(parents=True)
            for path in (ROOT/'x2_motion').iterdir():
                if path.is_file() and path.suffix in ('.py','.json'):shutil.copy2(path,app/path.name)
            (app/'env').write_text('X2_SSH_HOST=stale-laptop.example\nVLM_MODEL=stale-model\n')
            (app/'.env').write_text('X2_SSH_HOST=another-laptop.example\n')
            selected=checkout/'.env';selected.write_text('X2_SSH_HOST=x2.local\nVLM_MODEL=device-model\n')
            env={k:v for k,v in os.environ.items() if not k.startswith(('X2_','VLM_','OPENROUTER_'))}
            code='import sys,json,os;sys.path.insert(0,sys.argv[1]);from app import parse_args;parse_args(["--offline","--env-file",sys.argv[2]]);print(json.dumps({"host":os.environ["X2_SSH_HOST"],"model":os.environ["VLM_MODEL"]}))'
            result=subprocess.run([sys.executable,'-c',code,str(app),str(selected)],cwd=root,env=env,text=True,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),{'host':'x2.local','model':'device-model'})

if __name__=='__main__':unittest.main()
