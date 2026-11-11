"""Portable host settings. .env is parsed as data, never executed as shell code."""
import os,re
from pathlib import Path
from pipeline import load_env,load_openrouter_config

ROOT=Path(__file__).resolve().parent.parent
DEFAULT_PORT=8766
CONFIG_KEYS={'OPENROUTER_API_KEY','VLM_MODEL','VLM_PIPELINE_URL','VLM_PIPELINE_KEY',
    'X2_SSH_HOST','X2_SSH_USER','X2_SSH_PASSWORD','X2_SSH_KEY','X2_SSH_KNOWN_HOSTS',
    'X2_REMOTE_HOME','X2_REMOTE_SDK','X2_PORT'}

def load_config(path=None):
    path=Path(path or os.environ.get('X2_ENV_FILE',ROOT/'.env')).expanduser()
    load_env(path,allowed_keys=CONFIG_KEYS);load_openrouter_config(path)
    return path

def remote_paths():
    username=os.environ.get('X2_SSH_USER','agi')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',username):raise ValueError('Invalid X2_SSH_USER')
    home=os.environ.get('X2_REMOTE_HOME','/home/'+username)
    sdk=os.environ.get('X2_REMOTE_SDK',home+'/aimdk')
    for path in (home,sdk):
        if not path.startswith('/') or any(c in path for c in ('\0','\n','\r')):raise ValueError('Robot paths must be absolute POSIX paths')
    return home,sdk

def ssh_options():
    host=os.environ.get('X2_SSH_HOST','10.0.1.41')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,253}',host):raise ValueError('Invalid X2_SSH_HOST (use address only; set user separately)')
    username=os.environ.get('X2_SSH_USER','agi');remote_paths()
    options=dict(host=host,username=username,
        known_hosts=str(Path(os.environ.get('X2_SSH_KNOWN_HOSTS','~/.ssh/known_hosts')).expanduser()),
        connect_timeout=5,login_timeout=8,keepalive_interval=2,keepalive_count_max=3)
    if os.environ.get('X2_SSH_KEY'):options['client_keys']=[str(Path(os.environ['X2_SSH_KEY']).expanduser())]
    if os.environ.get('X2_SSH_PASSWORD'):options['password']=os.environ['X2_SSH_PASSWORD']
    return options
