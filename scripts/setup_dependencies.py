"""Reuse the venv; invoke pip only when dependency inputs or imports changed."""
import hashlib,importlib,json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
requirements=root/'x2_motion/requirements-dashboard.txt'
stamp=root/'.venv/.requirements.sha256'
digest=hashlib.sha256(requirements.read_bytes()).hexdigest()
installed=False
if stamp.exists() and stamp.read_text().strip()==digest:
    try:
        for name in ('aiohttp','PIL','asyncssh'):importlib.import_module(name)
        installed=True
    except ImportError:pass
if not installed:
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','-r',str(requirements)],check=True)
    stamp.write_text(digest+'\n')
print(json.dumps(dict(python=sys.version.split()[0],environment='reused' if installed else 'prepared',system_python_installed=False)))
