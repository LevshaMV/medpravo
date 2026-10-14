"""Read-only Yandex Browser diagnostic on an ephemeral GitHub runner."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import monitor as m

IDS={'ffoms','tfoms','kaluga-health','kaluga-gov','rospotreb','kaluga-rospotreb','rostrud','rkn','fas'}
browser=shutil.which('yandex-browser-stable') or shutil.which('yandex-browser')
if not browser:raise SystemExit('Yandex Browser is not installed')
print('Browser:',subprocess.check_output([browser,'--version'],text=True).strip(),flush=True)

def probe(source):
    start=time.monotonic();url=source['seeds'][0]
    result={'source':source['id'],'requested':url,'browser':'Yandex'}
    try:
        with tempfile.TemporaryDirectory() as profile:
            env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','DISPLAY','XDG_RUNTIME_DIR')}
            run=subprocess.run([browser,'--headless','--disable-gpu','--no-first-run','--disable-background-networking',
                '--user-data-dir='+profile,'--virtual-time-budget=12000','--dump-dom',url],capture_output=True,timeout=40,env=env)
            text=run.stdout.decode('utf-8',errors='replace')
            page=m.parse_page(text)
            visible=page.visible[:2000]
            if re.search('Доступ из вашего региона запрещ|You are unable to access|Access Denied|Forbidden|ERR_CONNECTION|ERR_CERT|ERR_TIMED_OUT|cannot be reached|Не удается получить доступ',visible,re.I):
                result.update(ok=False,error=visible[:600])
            elif not text or run.returncode:
                result.update(ok=False,error='Браузер не получил страницу',diagnostic=run.stderr.decode('utf-8',errors='replace')[-500:])
            else:
                links,pages=m.discover(text,url,source)
                result.update(ok=bool(links),links=len(links),pages=len(pages),title=' '.join(page.title_parts),excerpt=visible[:600])
    except subprocess.TimeoutExpired:result.update(ok=False,error='Браузер не получил каталог за 40 секунд')
    except Exception as exc:result.update(ok=False,error=type(exc).__name__+': '+str(exc)[:200])
    result['seconds']=round(time.monotonic()-start,2);print(json.dumps(result,ensure_ascii=False),flush=True);return result

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(probe,[s for s in m.catalog() if s['id'] in IDS]))
with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
    out.write('# Яндекс Браузер на GitHub\n\n| Источник | Каталог прочитан | Ссылок | Причина |\n|---|---|---|---|\n')
    for row in results:out.write('| '+row['source']+' | '+str(row['ok'])+' | '+str(row.get('links',0))+' | '+row.get('error','').replace('|',' ')+' |\n')
