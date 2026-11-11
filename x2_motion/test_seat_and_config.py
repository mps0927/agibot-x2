import argparse,ast,json,math,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from app import create_app
from control_policy import seat_hold_check
from pipeline import load_openrouter_config

def seated_joints():
    return {side+'_'+name+'_joint':dict(position=pos,velocity=0.,error_code=0)
            for side in ('left','right') for name,pos in [('hip_pitch',-1.1),('knee',1.4)]}

class SeatPolicy(unittest.TestCase):
    def test_worker_event_accepts_action_name_without_argument_collision(self):
        tree=ast.parse(Path(__file__).with_name('x2_worker.py').read_text(encoding='utf-8'))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        event=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='event')
        captured=[];namespace={'emit':captured.append,'time':time}
        exec(compile(ast.Module(body=[event],type_ignores=[]),'<worker-event>','exec'),namespace)
        namespace['event']('sdk_request_sent',name='wave_right',service='SetMcPresetMotion')
        self.assertEqual(captured[0]['name'],'wave_right')
        self.assertEqual(captured[0]['event'],'sdk_request_sent')

    def test_only_supported_seated_preparation_passes(self):
        joints=seated_joints()
        self.assertEqual(seat_hold_check('PASSIVE_DEFAULT',.1,True,.1,joints),'REQUEST_ALLOWED')
        cases=[('STAND_DEFAULT',.1,True,.1,joints),('PASSIVE_DEFAULT',3.,True,.1,joints),
               ('PASSIVE_DEFAULT',.1,False,.1,joints),('PASSIVE_DEFAULT',.1,True,3.,joints),
               ('PASSIVE_DEFAULT',.1,True,.1,{})]
        for values in cases:
            with self.assertRaises(ValueError):seat_hold_check(*values)
        joints['left_knee_joint']['position']=math.nan
        with self.assertRaises(ValueError):seat_hold_check('PASSIVE_DEFAULT',.1,True,.1,joints)
        joints=seated_joints();joints['left_hip_pitch_joint']['position']=0.
        with self.assertRaises(ValueError):seat_hold_check('PASSIVE_DEFAULT',.1,True,.1,joints)

    def test_parent_config_accepts_raw_key_or_named_key_and_ignores_other_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'.env'
            for body in ('sk-or-v1-example-test-value','OPENROUTER_API_KEY=sk-or-v1-example-test-value\nUNRELATED_TEST_SECRET=ignored'):
                p.write_text(body,encoding='utf-8')
                with patch.dict(os.environ,{},clear=True):
                    load_openrouter_config(p)
                    self.assertEqual(os.environ['OPENROUTER_API_KEY'],'sk-or-v1-example-test-value')
                    self.assertNotIn('UNRELATED_TEST_SECRET',os.environ)

class SeatAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        args=argparse.Namespace(offline=True,read_only=False,allow_control=False,allow_presets=True,allow_seat_hold=True,origin='',operator_ready=False)
        self.app=create_app(args);self.d=self.app['dashboard'];self.sent=[]
        async def send(msg):self.sent.append(msg)
        self.d.send=send
        self.client=TestClient(TestServer(self.app));await self.client.start_server()
        self.d.state.update(connected=True,fsm='PASSIVE_DEFAULT',mode_age_ms=10,leg_age_ms=10,joint_values=seated_joints())
        self.d.state_at=time.monotonic()
        self.origin=str(self.client.make_url('/')).rstrip('/')
    async def asyncTearDown(self):await self.client.close()

    async def test_button_request_is_scoped_and_already_active_does_not_repeat(self):
        r=await self.client.post('/api/seat-hold',json={'confirmed':True},headers={'Origin':self.origin})
        self.assertEqual(r.status,202);self.assertEqual(self.sent,[dict(action='seat_hold',confirmed=True)])
        self.d.state['fsm']='SIT_JOINT_DEFAULT'
        r=await self.client.post('/api/seat-hold',json={},headers={'Origin':self.origin})
        self.assertEqual((await r.json())['status'],'ALREADY_ACTIVE');self.assertEqual(len(self.sent),1)

    async def test_support_check_and_movement_mode_block_dispatch(self):
        for confirmed,mode in [(False,'PASSIVE_DEFAULT'),(True,'STAND_DEFAULT')]:
            self.d.state['fsm']=mode
            r=await self.client.post('/api/seat-hold',json={'confirmed':confirmed},headers={'Origin':self.origin})
            self.assertEqual(r.status,400)
        self.assertEqual(self.sent,[])
        r=await self.client.get('/api/postures/stand_up_from_seat');v=await r.json()
        self.assertEqual(v['controller'],'↑ + □');self.assertTrue(v['sdk_callable'])
        self.assertFalse(v['control_request_sent'])

if __name__=='__main__':unittest.main()
