"""Prepare mounted settings, then run the dashboard as an unprivileged user."""
import asyncio
import os
from pathlib import Path
import shutil
import sys

ROOT=Path('/app')
sys.path.insert(0,str(ROOT/'x2_motion'))

def prepare():
    uid=gid=10001
    runtime=Path('/run/x2');runtime.mkdir(mode=0o700,exist_ok=True)
    for source,target in (('/run/secrets/x2_config','config.env'),('/run/secrets/robot_key','robot_key')):
        if not Path(source).exists():
            if target=='config.env':raise RuntimeError('설정 파일 .env를 준비하세요.')
            continue
        dest=runtime/target
        shutil.copyfile(source,dest);os.chmod(dest,0o600);os.chown(dest,uid,gid)
    os.chown(runtime,uid,gid)
    data=Path('/data');data.mkdir(exist_ok=True)
    for path in (data,data/'ssh',data/'artifacts'):
        path.mkdir(exist_ok=True);os.chown(path,uid,gid)
    os.setgroups([]);os.setgid(gid);os.setuid(uid)

async def trust_host():
    import asyncssh
    from configuration import load_config,ssh_options
    load_config();options=ssh_options();host=options['host']
    key=await asyncio.wait_for(asyncssh.get_server_host_key(host,config=None),timeout=5)
    if key is None:raise RuntimeError('로봇의 SSH 호스트 키를 가져오지 못했습니다.')
    fingerprint=key.get_fingerprint('sha256')
    path=Path(options['known_hosts']);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        for line in path.read_text().splitlines():
            if line.split(' ',1)[0]==host:
                expected=key.export_public_key().decode().strip()
                if line.split(' ',1)[1].strip()!=expected:raise RuntimeError('기존 호스트 키와 다릅니다. 로봇의 키를 확인하세요.')
                print('등록된 로봇 호스트 키:',fingerprint);return
    print('로봇 SSH 호스트:',host,'지문:',fingerprint,flush=True)
    if input('실제 로봇의 지문과 일치하면 yes 입력: ').strip()!='yes':raise RuntimeError('호스트 키를 등록하지 않았습니다.')
    with path.open('a',encoding='utf-8') as output:output.write(host+' '+key.export_public_key().decode().strip()+'\n')
    os.chmod(path,0o600)
    print('호스트 키를 등록했습니다.')

def main():
    prepare()
    command=sys.argv[1] if len(sys.argv)>1 else 'serve'
    if command=='trust-host':asyncio.run(trust_host());return
    if command=='doctor':
        os.execv(sys.executable,[sys.executable,str(ROOT/'docker/doctor.py')])
    if command=='serve':
        args=sys.argv[2:]
        flags=[] if '--offline' in args else ['--allow-control','--allow-posture-actions']
        os.execv(sys.executable,[sys.executable,str(ROOT/'x2_motion/dashboard.py'),*flags,*args])
    raise ValueError('지원 명령: serve, doctor, trust-host')

if __name__=='__main__':
    try:main()
    except Exception as exc:print('X2 Docker:',str(exc),file=sys.stderr);sys.exit(1)
