"""Create an isolated environment once, then launch the local app."""
from pathlib import Path
import subprocess
import sys
import venv
import shutil
import hashlib
ROOT=Path(__file__).resolve().parent

def main():
    if sys.version_info < (3,10):raise SystemExit('Please install Python 3.10 or newer (3.11/3.12 recommended).')
    env=ROOT/'.venv'
    python=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if not python.exists():
        print('Creating isolated Python environment...',flush=True);venv.create(env,with_pip=True)
    req=ROOT/'requirements.txt';fingerprint=hashlib.sha256(req.read_bytes()).hexdigest();stamp=env/'requirements.sha256'
    if not stamp.exists() or stamp.read_text()!=fingerprint:
        subprocess.run([str(python),'-m','pip','install','-r',str(req)],check=True,cwd=ROOT)
        stamp.write_text(fingerprint)
    secret=ROOT/'llm_secrets.env'
    if not secret.exists():
        shutil.copyfile(ROOT/'llm_secrets.env.example',secret)
        print('Created llm_secrets.env. Fill your DeepSeek key locally; otherwise use rule mode.',flush=True)
        if sys.platform=='win32':subprocess.Popen(['notepad.exe',str(secret)])
    subprocess.run([str(python),str(ROOT/'app_ui.py')]+sys.argv[1:],cwd=ROOT,check=True)
if __name__=='__main__':
    try:main()
    except (subprocess.CalledProcessError,OSError) as e:print('Launch failed:',e);sys.exit(1)
