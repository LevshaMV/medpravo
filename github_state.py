"""Persist resumable collection in a dedicated Git branch, never commit secrets."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import github_collect as collect

BRANCH='medpravo-state'
STATE_FILES=('state.sqlite.gz','files.json','digests.json')

def git(*args,input=None,env=None):
    result=subprocess.run(['git',*args],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,check=True)
    return result.stdout

def restore(folder):
    folder.mkdir(parents=True,exist_ok=True)
    refs=git('ls-remote','--heads','origin','refs/heads/'+BRANCH).decode().strip()
    if not refs:return
    sha=refs.split()[0]
    if not re.fullmatch(r'[0-9a-f]{40}',sha):raise ValueError('Invalid state ref')
    git('fetch','--depth=1','origin','refs/heads/'+BRANCH)
    paths=git('ls-tree','-r','--name-only',sha).decode().splitlines()
    for name in paths:
        if name not in STATE_FILES and not collect.FILE_PATH.fullmatch(name):raise ValueError('Unexpected file in state branch')
        raw=git('show',sha+':'+name)
        if len(raw)>20*1024*1024:raise ValueError('State blob too large')
        path=folder/'persist'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (folder/'parent.txt').write_text(sha,encoding='ascii')

def save(folder):
    root=folder/'persist'
    parent=(folder/'parent.txt').read_text(encoding='ascii').strip() if (folder/'parent.txt').exists() else None
    if parent and not re.fullmatch('[0-9a-f]{40}',parent):raise ValueError('Invalid parent')
    index=folder.resolve()/'state.index'
    if index.exists():index.unlink()
    env={**os.environ,'GIT_INDEX_FILE':str(index),'GIT_AUTHOR_NAME':'MedPravo','GIT_AUTHOR_EMAIL':'medpravo@users.noreply.github.com','GIT_COMMITTER_NAME':'MedPravo','GIT_COMMITTER_EMAIL':'medpravo@users.noreply.github.com'}
    count=0
    for path in sorted(root.rglob('*')):
        if not path.is_file():continue
        name=path.relative_to(root).as_posix()
        if name not in STATE_FILES and not collect.FILE_PATH.fullmatch(name):raise ValueError('Refusing to publish unexpected file')
        if path.stat().st_size>20*1024*1024:raise ValueError('Blob too large')
        sha=git('hash-object','-w','--',str(path)).decode().strip()
        git('update-index','--add','--cacheinfo','100644,'+sha+','+name,env=env);count+=1
    if not (root/'state.sqlite.gz').exists() or not count:raise ValueError('History missing')
    tree=git('write-tree',env=env).decode().strip()
    args=['commit-tree',tree]
    if parent:args+=['-p',parent]
    sha=git(*args,input=b'Save MedPravo collection history\n',env=env).decode().strip()
    git('push','origin',sha+':refs/heads/'+BRANCH)
    print('History persisted:',count,'files')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['restore','save']);parser.add_argument('--folder',type=Path,default=Path('.state'))
    args=parser.parse_args();(restore if args.action=='restore' else save)(args.folder)
