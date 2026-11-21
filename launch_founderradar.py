"""One-click local launcher. Server is loopback-only; the browser opens on readiness."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

ROOT=Path(__file__).resolve().parent


def healthy(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1) as response:return response.read(32)==b'ok'
    except Exception:return False


def main():
    from mvp.engine import data_dir
    storage=data_dir();storage.mkdir(parents=True,exist_ok=True)
    state=storage/'server.json'
    if state.exists():
        try:
            record=json.loads(state.read_text(encoding='utf-8'))
            if record.get('root')==str(ROOT) and healthy(record['port']):
                webbrowser.open(f'http://127.0.0.1:{record["port"]}')
                print('FounderRadar wurde im Browser geöffnet.');return
        except (ValueError,KeyError,OSError):pass
    port=None
    for candidate in range(8502,8520):
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',candidate));port=candidate;break
            except OSError:continue
    if port is None:raise RuntimeError('Kein freier lokaler Port zwischen 8502 und 8519.')
    env=dict(os.environ,FOUNDERRADAR_UI='mvp',PYTHONIOENCODING='utf-8')
    startup=None
    if os.name=='nt':
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    with (storage/'server.log').open('a',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'cockpit.py'),
            '--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true','--browser.gatherUsageStats=false',
            '--theme.base=light','--theme.primaryColor=#17624d','--theme.backgroundColor=#ffffff',
            '--theme.secondaryBackgroundColor=#f3f7f5','--theme.textColor=#171b19'],
            cwd=ROOT,env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,startupinfo=startup,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(90):
        if process.poll() is not None:raise RuntimeError('Serverstart fehlgeschlagen; siehe '+str(storage/'server.log'))
        if healthy(port):
            state.write_text(json.dumps({'root':str(ROOT),'port':port,'pid':process.pid}),encoding='utf-8')
            webbrowser.open(f'http://127.0.0.1:{port}')
            print(f'FounderRadar ist bereit: http://127.0.0.1:{port}');return
        time.sleep(1)
    process.terminate()
    raise RuntimeError('Serverstart dauerte zu lange; siehe '+str(storage/'server.log'))


if __name__=='__main__':main()
