"""Compare official-source access from GitHub runners, keeping TLS verification."""
import concurrent.futures
import json
import os
from pathlib import Path
import platform
import socket
import time
import urllib.parse
import monitor as m

ids={'ffoms','tfoms','kaluga-health','kaluga-gov','rospotreb','kaluga-rospotreb','rostrud','rkn','fas'}
m.DATA=Path('.probe-data');m.initialize();os.environ['FETCH_TIMEOUT']='5'
original=socket.getaddrinfo
def ipv4_first(*args,**kwargs):
    return sorted(original(*args,**kwargs),key=lambda x:x[0]!=socket.AF_INET)
socket.getaddrinfo=ipv4_first

def probe(item):
    source,url=item;start=time.monotonic()
    row={'source':source['id'],'requested':url,'runner':platform.system()}
    try:
        result=m.fetch(url,source)
        links,pages=m.discover(result['text'],result['url'],source) if result['type']=='text' else ([],[])
        row.update(ok=True,final=result['url'],type=result['type'],bytes=len(result['raw']),links=len(links),pages=len(pages))
    except Exception as exc:row.update(ok=False,error=type(exc).__name__+': '+str(exc)[:220])
    row['seconds']=round(time.monotonic()-start,2);print(json.dumps(row,ensure_ascii=False),flush=True);return row

items=[]
for source in m.catalog():
    if source['id'] not in ids:continue
    primary=source['seeds'][0];items.append((source,primary))
    value=urllib.parse.urlsplit(primary)
    if value.scheme=='https':items.append((source,urllib.parse.urlunsplit(value._replace(scheme='http'))))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(probe,items))
Path('probe-result.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
summary=os.environ.get('GITHUB_STEP_SUMMARY')
if summary:
    with open(summary,'a',encoding='utf-8') as out:
        out.write('# Проверка доступа: '+platform.system()+'\n\n| Источник | Адрес | Ссылок | Ошибка |\n|---|---|---|---|\n')
        for row in rows:out.write('| '+row['source']+' | '+row['requested']+' | '+str(row.get('links','—'))+' | '+row.get('error','')+' |\n')
