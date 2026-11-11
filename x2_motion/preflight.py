"""Local integrity/dependency checks and read-only robot SDK inspection."""
import argparse,ast,asyncio,json,os,shlex,subprocess,sys
from pathlib import Path
from configuration import ROOT,load_config,remote_paths,ssh_options
sys.path.insert(0,str(ROOT))
from refresh_checksums import verify

async def check_robot():
    import asyncssh
    _,sdk=remote_paths()
    probe="import json; from pathlib import Path; import rclpy; from aimdk_msgs.srv import GetMcAction,GetAllJointState,SetMcAction,SetMcPresetMotion,SetMcInputSource,GetRobotResources,ExecuteActionResource; from aimdk_msgs.msg import McLocomotionVelocity; from sensor_msgs.msg import CompressedImage; print(json.dumps(dict(ros='humble',sdk=Path("+repr(sdk+"/version")+").read_text().strip())))"
    command='set -e\nsource /opt/ros/humble/setup.bash\nsource '+shlex.quote(sdk+'/install/setup.bash')+'\npython3 -c '+shlex.quote(probe)
    async with asyncssh.connect(**ssh_options()) as connection:
        result=await connection.run('bash --noprofile --norc -c '+shlex.quote(command),check=True,timeout=25)
        lines=[line for line in result.stdout.splitlines() if line.startswith('{')]
        if not lines:raise RuntimeError('Robot SDK probe returned no result')
        print('Robot SDK: '+lines[-1])

def main():
    parser=argparse.ArgumentParser(description='Preflight performs no robot motion or service migration')
    # Mode starts with --, so remove it before argparse option processing.
    argv=sys.argv[1:];mode=argv.pop(0) if argv and argv[0] in ('--offline','--field') else '--offline'
    parser.add_argument('--env-file',default=None);parser.add_argument('--test',action='store_true')
    args,unknown=parser.parse_known_args(argv);load_config(args.env_file)
    assert sys.version_info>=(3,10),'Python 3.10+ required'
    import aiohttp,PIL,asyncssh
    print('Source checksums:',verify())
    for path in (ROOT/'x2_motion').glob('*.py'):ast.parse(path.read_text(encoding='utf-8'),filename=str(path),feature_version=(3,10))
    for path in (ROOT/'x2_motion').glob('*.json'):json.loads(path.read_text(encoding='utf-8'))
    from app import parse_args
    options=[v for v in unknown if v!='--background']
    if args.env_file:options+=['--env-file',args.env_file]
    parse_args((['--offline'] if mode=='--offline' else [])+options)
    print('Host: Python '+sys.version.split()[0]+'; aiohttp / Pillow / AsyncSSH OK')
    if args.test:
        subprocess.run([sys.executable,'-m','unittest','discover','-q','-s',str(ROOT/'x2_motion'),'-p','test_*.py'],check=True,cwd=ROOT)
    if mode=='--field':asyncio.run(check_robot())
    print('Preflight '+mode+': OK (port '+os.environ.get('X2_PORT','8766')+')')

if __name__=='__main__':
    try:main()
    except Exception as exc:print('Preflight failed: '+str(exc),file=sys.stderr);sys.exit(1)
