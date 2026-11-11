"""Portable SHA-256 manifest (Linux/macOS/Windows; no sha256sum dependency)."""
import argparse,hashlib,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
EXCLUDE={'.git','.venv','.runtime','__pycache__','artifacts','offline_bundle','inspection','backups'}
def sources():
    for directory,folders,files in os.walk(ROOT):
        folders[:]=sorted(f for f in folders if f not in EXCLUDE)
        for name in sorted(files):
            if name=='FILE_SHA256SUMS.txt' or name.endswith(('.pyc','.log','.pid')) or (name.startswith('.env') and name!='.env.example'):continue
            yield Path(directory)/name
def verify():
    expected={}
    for line in (ROOT/'FILE_SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1);expected[name]=digest
    actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources()}
    changed=sorted(name for name in set(expected)|set(actual) if expected.get(name)!=actual.get(name))
    if changed:raise ValueError('Checksum mismatch: '+', '.join(changed)+'. Run python refresh_checksums.py after intentional source changes.')
    return len(actual)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.check:print('Checksums OK:',verify())
    else:
        entries=sorted((p.relative_to(ROOT).as_posix(),hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources())
        (ROOT/'FILE_SHA256SUMS.txt').write_text(''.join(digest+'  '+name+'\n' for name,digest in entries),encoding='utf-8')
        print('Checksums written:',len(entries))
