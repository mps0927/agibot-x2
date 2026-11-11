import json,os,socket,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app import parse_args
from configuration import ROOT,load_config,ssh_options,remote_paths
HOME_ENV={key:os.environ[key] for key in ('HOME','USERPROFILE','HOMEDRIVE','HOMEPATH') if key in os.environ}

class PortableConfiguration(unittest.TestCase):
    def test_same_default_port_and_offline_cannot_enable_hardware(self):
        with patch.dict(os.environ,{},clear=True):
            live=parse_args([]);offline=parse_args(['--offline','--allow-control','--allow-posture-actions'])
        self.assertEqual(live.port,8766);self.assertEqual(offline.port,8766)
        self.assertTrue(offline.read_only);self.assertFalse(offline.allow_control);self.assertFalse(offline.allow_posture_actions)
    def test_env_is_data_and_exported_values_take_priority(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,dict(HOME_ENV,X2_SSH_HOST='robot.example'),clear=True):
            path=Path(directory)/'.env';path.write_text('X2_SSH_HOST=ignored.example\nX2_SSH_PASSWORD=local-test\nUNRELATED_SECRET=ignored\nOPENROUTER_API_KEY=test-only\n',encoding='utf-8')
            load_config(path);options=ssh_options()
            self.assertEqual(options['host'],'robot.example');self.assertEqual(options['password'],'local-test')
            self.assertNotIn('UNRELATED_SECRET',os.environ)
    def test_ssh_keys_and_host_keys_are_configurable_without_factory_password(self):
        with patch.dict(os.environ,dict(HOME_ENV,X2_SSH_KEY='~/.ssh/x2',X2_SSH_KNOWN_HOSTS='~/known_x2',X2_SSH_USER='operator'),clear=True):
            options=ssh_options();self.assertNotIn('password',options)
            self.assertTrue(Path(options['client_keys'][0]).is_absolute());self.assertTrue(Path(options['known_hosts']).is_absolute())
            self.assertEqual(remote_paths(),('/home/operator','/home/operator/aimdk'))
    def test_invalid_remote_settings_are_rejected(self):
        for key,value in [('X2_SSH_HOST','-oProxyCommand=bad'),('X2_SSH_USER','user;bad'),('X2_REMOTE_SDK','relative/path')]:
            with patch.dict(os.environ,{key:value},clear=True),self.assertRaises(ValueError):ssh_options()

class ManagedService(unittest.TestCase):
    def test_background_start_reuse_status_different_options_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            env=dict(os.environ,X2_RUNTIME_DIR=directory)
            script=str(ROOT/'x2_motion/dashboard_service.py')
            def call(*args,ok=True):
                result=subprocess.run([sys.executable,script,*args],env=env,capture_output=True,text=True,encoding='utf-8',timeout=25)
                if ok:self.assertEqual(result.returncode,0,result.stderr)
                return result
            options=('launch','--offline','--background','--port',str(port))
            try:
                first=json.loads(call(*options).stdout);self.assertEqual(first['status'],'started')
                second=json.loads(call(*options).stdout);self.assertEqual(second['pid'],first['pid']);self.assertEqual(second['status'],'already_running')
                self.assertEqual(json.loads(call('status').stdout)['status'],'running')
                self.assertNotEqual(call(*options,'--allow-control',ok=False).returncode,0)
                info=json.loads((Path(directory)/'dashboard.json').read_text());self.assertEqual(info['port'],port)
                self.assertIn('--offline',info['command'])
            finally:call('stop')
            self.assertEqual(json.loads(call('status').stdout)['status'],'stopped')

if __name__=='__main__':unittest.main()
