"""One dashboard/port per checkout; a local instance ID verifies managed stop."""
import contextlib,json,os,signal,socket,subprocess,sys,time,urllib.request,uuid
from pathlib import Path
from configuration import ROOT,load_config
RUNTIME=Path(os.environ.get('X2_RUNTIME_DIR',str(ROOT/'.runtime')));STATE=RUNTIME/'dashboard.json';LOG=RUNTIME/'dashboard.log'

@contextlib.contextmanager
def lock():
    RUNTIME.mkdir(parents=True,exist_ok=True)
    with (RUNTIME/'dashboard.lock').open('a+b') as handle:
        if os.name=='nt':
            import msvcrt
            handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX)
        try:yield
        finally:
            if os.name=='nt':handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)

def metadata():
    try:return json.loads(STATE.read_text())
    except (OSError,ValueError):return None

def alive_pid(pid):
    try:os.kill(pid,0);return True
    except OSError:return False

def owned(info):
    if not info:return False
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:'+str(info['port'])+'/api/config',timeout=1) as response:config=json.load(response)
        return config.get('instance_id')==info['instance_id']
    except (OSError,ValueError):return False

def stop():
    with lock():
        info=metadata()
        if not info:print('Dashboard is not running');return
        if not owned(info):
            if alive_pid(info['pid']):raise RuntimeError('Process identity cannot be verified; no process was stopped')
            STATE.unlink(missing_ok=True);print('Removed stale process record');return
        os.kill(info['pid'],signal.SIGTERM)
        deadline=time.monotonic()+12
        while owned(info) and time.monotonic()<deadline:time.sleep(.1)
        if owned(info):raise RuntimeError('Dashboard is still stopping; no forced kill was sent')
        STATE.unlink(missing_ok=True)
        print('Local dashboard stopped. Robot power-off uses the physical shutdown procedure.')

def launch(options):
    mode=options.pop(0) if options and options[0] in ('--offline','--field') else '--offline'
    background='--background' in options;options=[x for x in options if x!='--background']
    from app import parse_args
    args=parse_args((['--offline'] if mode=='--offline' else [])+options)
    if args.replay:mode='--offline'
    command=[sys.executable,str(ROOT/'x2_motion/dashboard.py')]+(['--offline'] if mode=='--offline' else [])+options
    with lock():
        info=metadata()
        if owned(info):
            if info['command'][2:]!=command[2:]:raise RuntimeError('Dashboard already has different options. Run ./stop.sh, then launch again.')
            print(json.dumps(dict(status='already_running',pid=info['pid'],url='http://127.0.0.1:'+str(info['port']))));return
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',args.port))==0:raise RuntimeError('Port '+str(args.port)+' is occupied. Stop the existing dashboard first.')
        if background:
            instance=uuid.uuid4().hex
            with LOG.open('ab',buffering=0) as output:
                process=subprocess.Popen(command+['--instance-id',instance],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                    env=dict(os.environ,PYTHONUNBUFFERED='1'),start_new_session=os.name!='nt',
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.DETACHED_PROCESS) if os.name=='nt' else 0)
            info=dict(pid=process.pid,port=args.port,instance_id=instance,command=command,mode=mode)
            STATE.write_text(json.dumps(info,indent=2)+'\n')
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                if owned(info):print(json.dumps(dict(status='started',pid=process.pid,url='http://127.0.0.1:'+str(args.port),log=str(LOG))));return
                if process.poll() is not None:STATE.unlink(missing_ok=True);raise RuntimeError('Dashboard exited; see .runtime/dashboard.log')
                time.sleep(.1)
            process.terminate();STATE.unlink(missing_ok=True);raise RuntimeError('Dashboard startup timed out; see .runtime/dashboard.log')
    print('X2 dashboard: http://127.0.0.1:'+str(args.port),flush=True)
    os.execv(sys.executable,command)

def main():
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='launch':launch(sys.argv[2:])
    elif action=='stop':stop()
    elif action=='status':
        info=metadata();print(json.dumps(dict(status='running' if owned(info) else 'stopped',url='http://127.0.0.1:'+str(info['port']) if info else None)))
    else:raise ValueError('usage: dashboard_service.py launch|status|stop')

if __name__=='__main__':
    try:main()
    except Exception as exc:print('Dashboard: '+str(exc),file=sys.stderr);sys.exit(1)
