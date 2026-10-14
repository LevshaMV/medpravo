"""Install on a NEW Ubuntu 24.04 VPS: Python + Caddy + systemd, without Docker."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import maintenance

APP=Path('/opt/medpravo-feed')
DATA=Path('/var/lib/medpravo')
CONFIG=Path('/etc/medpravo')

def site_name(ip,name=''):
    try:address=ipaddress.IPv4Address(ip)
    except ValueError as exc:raise ValueError('Введите корректный внешний IPv4 сервера') from exc
    if not address.is_global:raise ValueError('Нужен публичный IPv4, не локальный адрес компьютера')
    name=(name or str(address)+'.sslip.io').lower()
    if len(name)>253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in name.split('.')):
        raise ValueError('Введите имя сайта без https://, порта и пробелов')
    if '.' not in name:raise ValueError('Нужно полное доменное имя сайта')
    return name

def app_unit():
    return '''[Unit]
Description=MedPravo publication monitor
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=medpravo
Group=medpravo
WorkingDirectory=/opt/medpravo-feed
EnvironmentFile=/etc/medpravo/app.env
ExecStart=/usr/bin/python3 /opt/medpravo-feed/monitor.py
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/medpravo
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
MemoryMax=768M
TasksMax=64
UMask=0077

[Install]
WantedBy=multi-user.target
'''

def backup_unit():
    return '''[Unit]
Description=MedPravo consistent database backup
After=medpravo.service

[Service]
Type=oneshot
User=medpravo
Group=medpravo
EnvironmentFile=/etc/medpravo/app.env
ExecStart=/usr/bin/python3 /opt/medpravo-feed/maintenance.py backup
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/medpravo
UMask=0077
'''

def backup_timer():
    return '''[Unit]
Description=MedPravo daily backup

[Timer]
OnCalendar=*-*-* 01:30:00 UTC
Persistent=true
Unit=medpravo-backup.service

[Install]
WantedBy=timers.target
'''

def proxy_config(domain):
    return domain+' {\n  encode gzip\n  reverse_proxy 127.0.0.1:8080\n}\n'

def read_env(path):
    values={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            key,value=line.split('=',1);values[key]=value
    if len(values.get('ADMIN_PASSWORD',''))<16:raise ValueError('В конфигурации отсутствует безопасный пароль')
    if values.get('BIND')!='127.0.0.1' or values.get('DATA_DIR')!=str(DATA):raise ValueError('Некорректный адрес приложения или папка данных')
    return values

def run(*args):
    subprocess.run(args,check=True)

def available_ports():
    for port in (80,443,8080):
        with socket.socket() as test:
            try:test.bind(('0.0.0.0',port))
            except OSError as exc:raise ValueError(f'Порт {port} занят. Нужен новый отдельный сервер для МедПраво.') from exc

def install(args):
    if sys.platform!='linux' or os.geteuid()!=0:raise ValueError('Установщик запускается на Linux-сервере под root, а не на Windows-компьютере')
    release=Path('/etc/os-release').read_text()
    if not re.search(r'^ID=ubuntu$',release,re.M) or 'VERSION_ID="24.04"' not in release:
        raise ValueError('Выберите Ubuntu 24.04: этот установщик рассчитан на неё')
    if sys.version_info<(3,12):raise ValueError('Нужен Python 3.12 или новее')
    if Path(__file__).resolve().parent!=APP:raise ValueError('Распакуйте пакет в /opt/medpravo-feed')
    maintenance.check_package()
    existing=(CONFIG/'deployment.json').exists()
    if not existing:
        available_ports()
        if Path('/etc/caddy/Caddyfile').exists():raise ValueError('Обнаружена чужая конфигурация Caddy. Нужен новый отдельный сервер.')
    if args.import_db and (DATA/'monitor.sqlite').exists():raise ValueError('История уже существует. Установщик не будет её перезаписывать.')
    if args.import_db:maintenance.check_database(Path(args.import_db))
    if existing:
        domain=json.loads((CONFIG/'deployment.json').read_text())['domain']
        site_name('1.1.1.1',domain)
    else:
        ip=args.ip or input('Внешний IPv4 вашего сервера: ').strip()
        domain=site_name(ip,args.domain or input('Имя сайта (Enter — бесплатный адрес): ').strip())
    CONFIG.mkdir(mode=0o700,exist_ok=True)
    CONFIG.chmod(0o700)
    (CONFIG/'deployment.json').write_text(json.dumps({'domain':domain,'mode':'native','app':str(APP),'status':'installing'}),encoding='utf-8')
    print('Устанавливаем серверные пакеты Ubuntu. Docker не используется.',flush=True)
    run('apt-get','update')
    run('apt-get','install','-y','python3','caddy','ca-certificates')
    if not (CONFIG/'app.env').exists():
        password=secrets.token_hex(24)
        values={'ADMIN_USER':'owner','ADMIN_PASSWORD':password,'DATA_DIR':str(DATA),'BIND':'127.0.0.1','PORT':'8080',
                'PYTHONUNBUFFERED':'1','PYTHONDONTWRITEBYTECODE':'1'}
        (CONFIG/'app.env').write_text(''.join(key+'='+value+'\n' for key,value in values.items()),encoding='utf-8')
        (CONFIG/'app.env').chmod(0o600)
    else:values=read_env(CONFIG/'app.env')
    if subprocess.run(['id','-u','medpravo'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        run('useradd','--system','--user-group','--home-dir',str(DATA),'--shell','/usr/sbin/nologin','medpravo')
    DATA.mkdir(mode=0o700,exist_ok=True)
    if existing:
        if Path('/etc/systemd/system/medpravo.service').exists():run('systemctl','stop','medpravo')
        if (DATA/'monitor.sqlite').exists():maintenance.daily_backup(DATA)
    if args.import_db:maintenance.backup_database(Path(args.import_db),DATA/'monitor.sqlite')
    shutil.chown(DATA,user='medpravo',group='medpravo')
    for path in DATA.iterdir():
        if path.name.startswith('monitor.sqlite') and path.is_file():
            shutil.chown(path,user='medpravo',group='medpravo');path.chmod(0o600)
    if (DATA/'backups').exists():
        shutil.chown(DATA/'backups',user='medpravo',group='medpravo')
        for path in (DATA/'backups').glob('medpravo-backup-*.sqlite'):shutil.chown(path,user='medpravo',group='medpravo')
    for name,text in {'medpravo.service':app_unit(),'medpravo-backup.service':backup_unit(),'medpravo-backup.timer':backup_timer()}.items():
        Path('/etc/systemd/system',name).write_text(text,encoding='utf-8')
    Path('/etc/caddy/Caddyfile').write_text(proxy_config(domain),encoding='utf-8')
    run('caddy','validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
    run('systemctl','daemon-reload')
    run('systemctl','enable','--now','medpravo','medpravo-backup.timer','caddy')
    run('systemctl','restart','medpravo')
    run('systemctl','reload','caddy')
    for attempt in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2) as response:
                if json.load(response)['ok']:break
        except (OSError,ValueError):time.sleep(1)
    else:raise ValueError('Приложение не прошло проверку запуска. Выполните journalctl -u medpravo -n 30 --no-pager')
    run('systemctl','start','medpravo-backup.service')
    (CONFIG/'deployment.json').write_text(json.dumps({'domain':domain,'mode':'native','app':str(APP),'status':'installed'}),encoding='utf-8')
    print('\nСайт: https://'+domain+'\nЛогин: '+values['ADMIN_USER']+'\nПароль: '+values['ADMIN_PASSWORD'])
    print('Сохраните пароль. Для HTTPS должны быть открыты порты 80 и 443. Проверьте «Источники» после первого сбора.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip');parser.add_argument('--domain');parser.add_argument('--import-db')
    parser.add_argument('--plan',action='store_true',help='Показать план без установки')
    args=parser.parse_args()
    try:
        if args.plan:
            domain=site_name(args.ip or '93.184.216.34',args.domain or '')
            print(json.dumps({'mode':'native','requires':'New Ubuntu 24.04 VPS, root','domain':domain,
                              'packages':['python3','caddy','ca-certificates'],'app_service':app_unit(),
                              'proxy_config':proxy_config(domain),'backup_timer':backup_timer()},ensure_ascii=False,indent=2))
        else:install(args)
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print('Установка остановлена: '+str(exc),file=sys.stderr);sys.exit(1)
