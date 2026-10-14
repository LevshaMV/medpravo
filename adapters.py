"""Official catalog adapters. No page execution or AI is required."""
import datetime as dt
import html
import json
import re
import urllib.parse
import titles
import xml.etree.ElementTree as ET

def parse_clinrec(text,source):
    value=json.loads(text)
    records=value.get('Data')
    if not isinstance(records,list):raise ValueError('Изменилась схема API клинических рекомендаций')
    links=[]
    for row in records:
        identifier=row.get('CodeVersion')
        if not re.fullmatch(r'\d+_\d+',str(identifier)):raise ValueError('API не вернул идентификатор версии КР')
        links.append({'url':'https://cr.minzdrav.gov.ru/preview-cr/'+identifier,
            'title':'Клинические рекомендации: '+row['Name']+' · '+str(row.get('AgeCategoryStr','')),
            'published_at':row.get('PublishDateStr'),'metadata':True,
            'text':json.dumps(row.get('Developers',[]),ensure_ascii=False)})
    total=value.get('TotalRecords',value.get('Total',value.get('TotalCount')))
    return links,int(total) if total is not None else None

def parse_projects(text,source):
    root=ET.fromstring(text)
    if root.tag!='projects':raise ValueError('Изменилась схема открытых данных проектов')
    links=[]
    for row in root.findall('project'):
        identifier=row.get('id','')
        if not identifier.isdigit():raise ValueError('API не вернул идентификатор проекта')
        # The individual official XML resource is a verified route, not an inferred UI URL.
        links.append({'url':'https://regulation.gov.ru/api/npalist/'+identifier,
            'title':'Проект: '+' '.join((row.findtext('title') or '').split()),
            'published_at':row.findtext('publishDate'),'metadata':True,
            'text':row.findtext('department') or ''})
    return links,int(root.get('total','0'))

def miac_rows(text,base,parse_page):
    links=[]
    for block in re.findall(r'<tr\b[^>]*>(.*?)</tr>',text,re.S|re.I):
        page=parse_page(block)
        found={}
        for href,title in page.links:
            if re.fullmatch(r'/documents/\d+',urllib.parse.urlsplit(href).path):
                url=urllib.parse.urljoin(base,href)
                if url not in found or len(title)>len(found[url]):found[url]=title
        for url,title in found.items():
            if not title or title=='Скачать документ':continue
            date=re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b',page.visible)
            links.append({'url':url,'title':title,'published_at':f'{date[3]}-{date[2]}-{date[1]}' if date else None})
    return links

def api_request(source,position=0,limit=50):
    if source['adapter']=='clinrec':
        return ('https://apicr.minzdrav.gov.ru/api.ashx?op=GetJsonClinrecsFilterV2',
            {'filters':[{'fieldName':'status','filterType':1,'filterValueType':2,'value1':0,'value2':'','values':[]}],
             'sortOption':{'fieldName':'publishdate','sortType':2},'pageSize':limit,
             'currentPage':position+1,'useANDoperator':True,'columns':[]})
    if source['adapter']=='projects':
        return ('https://regulation.gov.ru/api/npalist?'+urllib.parse.urlencode({'limit':limit,'offset':position*limit,'sort':'desc'}),None)
    raise ValueError('Неизвестный API-адаптер')

def ffoms_rows(text,base,parse_page):
    links=[]
    for block in re.split(r'<div[^>]+class="structure-list[^"\n]*"[^>]*>',text)[1:]:
        page=parse_page(block)
        job=re.search(r'<div[^>]+class="job"[^>]*>(.*?)</div>',block,re.S)
        if not job:continue
        title=parse_page(job[1]).visible
        link=next((href for href,_ in page.links if '/documents/' in href and href.rstrip('/')!=urllib.parse.urlsplit(base).path.rstrip('/')),None)
        if not link:link=next((href for href,_ in page.links if re.search(r'\.(pdf|docx?)$',href)),None)
        if link and title:
            name=re.search(r'<div[^>]+class="name"[^>]*>(.*?)</div>',block,re.S)
            subject=parse_page(name[1]).visible if name else ''
            links.append({'url':urllib.parse.urljoin(base,link),'title':titles.combine(title,subject),
                          'original_title':title,'published_at':None})
    return links
