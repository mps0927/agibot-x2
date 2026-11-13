"""Run the real Compose file in a fresh checkout copy with synthetic settings."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid

from PIL import Image


def main():
    root=Path(__file__).resolve().parent.parent
    image=os.environ.get('X2_TEST_IMAGE','agibot-x2:runtime-test')
    project='x2-startup-test-'+uuid.uuid4().hex[:10]
    environment={key:value for key,value in os.environ.items()
                 if not key.startswith(('X2_','OPENROUTER_','VLM_','COMPOSE_'))}
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        checkout=Path(directory)/'checkout'
        shutil.copytree(root,checkout,ignore=shutil.ignore_patterns(
            '.git','.venv','.runtime','artifacts','__pycache__','.env','.env.*','env','backups','inspection','offline_bundle'))
        compose_file=checkout/'compose.yaml'
        compose=compose_file.read_text(encoding='utf-8')
        compose=compose.replace('image: agibot-x2:local','image: '+image)
        compose=compose.replace('127.0.0.1:8766:8766','127.0.0.1::8766')
        compose=compose.replace('name: agibot-x2-data','name: '+project+'-data')
        compose_file.write_text(compose,encoding='utf-8')

        def dc(*args):
            result=subprocess.run(['docker','compose','-p',project,*args],cwd=checkout,
                                  env=environment,capture_output=True,text=True,timeout=120)
            if result.returncode:
                raise RuntimeError('Compose '+args[0]+' failed: '+result.stderr[-2000:])
            return result.stdout

        def start(*extra):
            dc('up','-d',*extra)
            port=dc('port','x2','8766').strip().rsplit(':',1)[1]
            address='http://127.0.0.1:'+port
            for _ in range(100):
                try:
                    with urllib.request.urlopen(address+'/api/config',timeout=1) as response:
                        return address,json.load(response)
                except (OSError,ValueError):time.sleep(.1)
            raise AssertionError('Dashboard did not start')

        def get(address,path):
            with urllib.request.urlopen(address+path,timeout=5) as response:return response.read()

        try:
            assert not (checkout/'.env').exists()
            address,config=start()
            assert config['mode']=='ssh-direct'
            assert not config['pipeline']['configured']
            state=json.loads(get(address,'/api/status'))
            assert state['connected'] is False and state['armed'] is False
            assert b'LiDAR' in get(address,'/')
            print('PASS: compose up -d without .env or a robot',flush=True)

            # Test literal special characters without using real credentials.
            (checkout/'.env').write_text('X2_SSH_HOST=127.0.0.1\nX2_SSH_USER=fixture\n'
                'X2_SSH_PASSWORD=fixture$$!#=only\nOPENROUTER_API_KEY=fixture-only\n'
                'VLM_MODEL=fixture/model\n',encoding='utf-8')
            address,config=start('--force-recreate')
            assert config['robot']=='127.0.0.1' and config['pipeline']['configured']
            assert config['pipeline']['model']=='fixture/model'
            dc('exec','-T','x2','python','-c',
               "import os;assert os.environ['X2_SSH_PASSWORD']=='fixture$$!#=only'")
            print('PASS: optional .env settings and literal password characters',flush=True)

            picture=io.BytesIO();Image.new('RGB',(12,12),'blue').save(picture,format='JPEG')
            boundary='fixture'+uuid.uuid4().hex
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="fixture.jpg"\r\n'
                  'Content-Type: image/jpeg\r\n\r\n').encode()+picture.getvalue()+f'\r\n--{boundary}--\r\n'.encode()
            request=urllib.request.Request(address+'/api/upload',data=body,
                headers={'Origin':address,'Content-Type':'multipart/form-data; boundary='+boundary})
            with urllib.request.urlopen(request,timeout=5) as response:upload=json.load(response)
            saved=get(address,upload['url']);time.sleep(3.5)
            assert get(address,upload['url'])==saved
            print('PASS: uploaded image survives connection retries',flush=True)

            dc('exec','-T','--user','10001:10001','x2','python','-c',
               "from pathlib import Path;p=Path('/data/artifacts/startup-test.txt');p.write_text('fixture')")
            dc('stop')
            exported=checkout/'artifacts';exported.mkdir()
            dc('cp','x2:/data/artifacts/.',str(exported))
            assert (exported/'startup-test.txt').read_text()=='fixture'
            dc('down');start()
            assert dc('exec','-T','x2','cat','/data/artifacts/startup-test.txt').strip()=='fixture'
            print('PASS: record export and persistence across down/up',flush=True)
        finally:
            # Unique test project and synthetic-data volume only.
            assert project.startswith('x2-startup-test-')
            dc('down','--volumes')


if __name__=='__main__':main()
