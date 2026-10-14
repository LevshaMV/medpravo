"""Authenticated, pinned SSH forwarding on a disposable GitHub Linux runner."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import tempfile
import time

def folder():
    root=Path(os.environ['RUNNER_TEMP']).resolve()
    return root,root/'medpravo-relay-session.json'

def start():
    root,record=folder()
    host=os.environ.get('RELAY_HOST','')
    key=os.environ.get('RELAY_PRIVATE_KEY','')
    known=os.environ.get('RELAY_KNOWN_HOSTS','')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',host):raise ValueError('Invalid relay host')
    if not key.startswith('-----BEGIN OPENSSH PRIVATE KEY-----') or len(key)>16000:raise ValueError('Missing relay key')
    if not known.strip() or len(known)>16000:raise ValueError('Missing pinned SSH host key')
    task=Path(tempfile.mkdtemp(prefix='medpravo-relay-',dir=root))
    private=task/'key';private.write_text(key.rstrip()+'\n',encoding='utf-8');private.chmod(0o600)
    hosts=task/'known_hosts';hosts.write_text(known.rstrip()+'\n',encoding='utf-8');hosts.chmod(0o600)
    # The child receives no repository token or relay private-key environment.
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG')}
    with open(task/'ssh.log','wb') as log:
        process=subprocess.Popen(['ssh','-N','-T','-L','127.0.0.1:8118:127.0.0.1:8118',
            '-o','ExitOnForwardFailure=yes','-o','StrictHostKeyChecking=yes','-o','BatchMode=yes',
            '-o','IdentitiesOnly=yes','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=2',
            '-o','UserKnownHostsFile='+str(hosts),'-i',str(private),'medpravo-relay@'+host],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,start_new_session=True)
    record.write_text(json.dumps({'pid':process.pid,'folder':str(task)}),encoding='utf-8')
    ready=False
    for _ in range(30):
        if process.poll() is not None:break
        try:
            with socket.create_connection(('127.0.0.1',8118),timeout=.5):ready=True;break
        except OSError:time.sleep(.5)
    if not ready:raise RuntimeError('Russian relay unavailable; check server and pinned SSH key')
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as out:out.write('proxy_url=http://127.0.0.1:8118\n')
    print('Russian source relay connected',flush=True)

def stop():
    root,record=folder()
    if not record.exists():return
    data=json.loads(record.read_text(encoding='utf-8'));task=Path(data['folder']).resolve()
    if task.parent!=root or not task.name.startswith('medpravo-relay-'):raise ValueError('Invalid temporary relay folder')
    try:os.killpg(int(data['pid']),signal.SIGTERM)
    except ProcessLookupError:pass
    for name in ('key','known_hosts','ssh.log'):
        path=task/name
        if path.is_file():path.unlink()
    task.rmdir();record.unlink()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['start','stop']);args=parser.parse_args()
    (start if args.mode=='start' else stop)()

if __name__=='__main__':main()
