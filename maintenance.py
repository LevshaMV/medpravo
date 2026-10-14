"""Consistent SQLite backups and package checks; no external Python dependencies."""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parent

def check_database(path):
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
        if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('База данных повреждена')
        tables={row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'publications','settings','sources'}<=tables:raise ValueError('Это не база МедПраво')
        cfg=json.loads(con.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        if not isinstance(cfg.get('enabled_sources'),list):raise ValueError('Некорректные настройки источников')
        return {'records':con.execute('SELECT count(*) FROM publications').fetchone()[0],
                'reviewed':con.execute('SELECT count(*) FROM publications WHERE reviewed=1').fetchone()[0]}

def backup_database(source,destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source==destination or destination.exists():raise ValueError('Копия должна быть новым отдельным файлом')
    before=check_database(source)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with contextlib.closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,contextlib.closing(sqlite3.connect(destination)) as dest:
        src.backup(dest)
        dest.commit()
    if check_database(destination)!=before:raise ValueError('Проверка резервной копии не прошла')
    return before

def check_package():
    required=['monitor.py','collector.py','adapters.py','transport.py','network.py','titles.py','downloads.py',
              'static/index.html','static/app.js','static/api-client.js','static/style.css','sources.json',
              'certs/russian-chain.pem','install_server.py']
    for name in required:
        path=ROOT/name
        if not path.is_file():raise ValueError('В пакете отсутствует '+name)
        if path.suffix=='.py':compile(path.read_text(encoding='utf-8'),str(path),'exec')
    sources=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
    if len({s['id'] for s in sources})!=len(sources):raise ValueError('Повторяющиеся источники')
    import transport
    if hashlib.sha256((ROOT/'certs/russian-chain.pem').read_bytes()).hexdigest()!=transport.CHAIN_SHA256:
        raise ValueError('Контрольная сумма сертификатов не совпадает')
    return {'package_ok':True,'sources':len(sources),'python_dependencies':'standard_library'}

def daily_backup(data):
    data=Path(data).resolve()
    folder=data/'backups'
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination=folder/('medpravo-backup-'+stamp+'.sqlite')
    result=backup_database(data/'monitor.sqlite',destination)
    copies=sorted(folder.glob('medpravo-backup-*.sqlite'),reverse=True)
    for old in copies[7:]:
        if old.is_file() and not old.is_symlink() and old.resolve().parent==folder.resolve():old.unlink()
    return {**result,'backup':str(destination),'retained':min(len(copies),7)}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['check','backup'])
    args=parser.parse_args()
    if args.action=='backup':result=daily_backup(os.environ.get('DATA_DIR','/var/lib/medpravo'))
    else:
        result=check_package()
        path=Path(os.environ.get('DATA_DIR','/var/lib/medpravo'))/'monitor.sqlite'
        if path.exists():result['database']=check_database(path)
    print(json.dumps(result,ensure_ascii=False,indent=2))
