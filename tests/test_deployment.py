import base64
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import test_monitor as baseline
import install_server
import maintenance
import transport
monitor=baseline.monitor

class DeploymentTests(unittest.TestCase):
    setUp=baseline.FeedTests.setUp
    tearDown=baseline.FeedTests.tearDown
    content=baseline.FeedTests.content

    def test_failed_page_is_retained_after_restart(self):
        source={**self.source,'page_limit':2}
        first=self.content('<a href="?page=2">Следующая</a>')
        first['url']=source['seeds'][0]
        with patch.object(monitor,'fetch',side_effect=[first,OSError('temporary')]):monitor.scan_source(source)
        with monitor.connection() as con:
            queue=json.loads(con.execute('SELECT queue FROM source_cursor WHERE source_id=?',(source['id'],)).fetchone()[0])
        self.assertTrue(any('page=2' in url for url in queue))
        monitor.initialize()
        with patch.object(monitor,'fetch',side_effect=[first,self.content('')]) as fetch:monitor.scan_source(source)
        self.assertTrue(any('page=2' in call.args[0] for call in fetch.call_args_list))

    def test_api_last_full_page_finishes_without_false_partial(self):
        source={**next(s for s in monitor.catalog() if s['id']=='clinrec'),'api_page_size':1,'page_limit':2}
        responses=[self.content(json.dumps({'Data':[{'CodeVersion':str(i)+'_1','Name':'Помощь детям','AgeCategoryStr':'Дети'}],'TotalRecords':2})) for i in (1,2)]
        # API JSON is not HTML.
        for response in responses:response['text']=response['text'][6:-7]
        with patch.object(monitor,'fetch',side_effect=responses):result=monitor.scan_source(source)
        self.assertEqual(result['status'],'collected')
        self.assertEqual(result['added'],2)

    def test_verified_empty_api_establishes_initial_baseline(self):
        source=next(s for s in monitor.catalog() if s['id']=='clinrec')
        response={**self.content(),'text':json.dumps({'Data':[],'TotalRecords':0})}
        with patch.object(monitor,'fetch',return_value=response):result=monitor.scan_source(source)
        self.assertEqual(result['status'],'collected')
        with monitor.connection() as con:self.assertEqual(con.execute('SELECT initialized FROM sources WHERE id=?',(source['id'],)).fetchone()[0],1)

    def test_cache_eviction_does_not_remove_history(self):
        monitor.store_publication(self.source,self.candidate,self.content(),False)
        at=time.time()
        with monitor.connection() as con:
            for i,fetched in enumerate((at-transport.CACHE_AGE-1,at-10,at)):
                con.execute('INSERT INTO http_cache VALUES (?,?,?,?,?,?,?,?)',('https://minzdrav.gov.ru/cache/'+str(i),None,None,b'1234567890','text/html','utf-8','https://minzdrav.gov.ru/',fetched))
            transport.trim_cache(con,max_bytes=15,at=at)
            self.assertEqual(con.execute('SELECT count(*) FROM http_cache').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT count(*) FROM publications').fetchone()[0],1)

    def test_backup_restores_reviews_settings_and_dates(self):
        monitor.store_publication(self.source,self.candidate,self.content(),True)
        with monitor.connection() as con:
            con.execute('UPDATE publications SET reviewed=1')
            original=dict(con.execute('SELECT * FROM publications').fetchone())
            settings=con.execute('SELECT data FROM settings').fetchone()[0]
        backup=monitor.DATA/'backup.sqlite'
        maintenance.backup_database(monitor.DATA/'monitor.sqlite',backup)
        with contextlib.closing(sqlite3.connect(backup)) as con:
            con.row_factory=sqlite3.Row
            self.assertEqual(dict(con.execute('SELECT * FROM publications').fetchone()),original)
            self.assertEqual(con.execute('SELECT data FROM settings').fetchone()[0],settings)
        with self.assertRaises(ValueError):maintenance.backup_database(monitor.DATA/'monitor.sqlite',backup)

    def test_retention_only_removes_own_old_backups(self):
        monitor.store_publication(self.source,self.candidate,self.content(),False)
        folder=monitor.DATA/'backups';folder.mkdir()
        (folder/'keep.txt').write_text('keep')
        for i in range(9):maintenance.backup_database(monitor.DATA/'monitor.sqlite',folder/f'medpravo-backup-2024010{i}T000000Z.sqlite')
        result=maintenance.daily_backup(monitor.DATA)
        self.assertEqual(result['retained'],7)
        self.assertEqual(len(list(folder.glob('medpravo-backup-*.sqlite'))),7)
        self.assertTrue((folder/'keep.txt').exists())

    def test_native_plan_keeps_app_private_and_uses_service_restart(self):
        self.assertIn('BIND',Path(install_server.__file__).read_text(encoding='utf-8'))
        self.assertIn('Restart=on-failure',install_server.app_unit())
        self.assertIn('ProtectSystem=strict',install_server.app_unit())
        self.assertIn('reverse_proxy 127.0.0.1:8080',install_server.proxy_config('example.org'))
        self.assertIn('Persistent=true',install_server.backup_timer())
        self.assertEqual(install_server.site_name('93.184.216.34'),'93.184.216.34.sslip.io')
        for ip,name in [('127.0.0.1',''),('93.184.216.34','https://example.org'),('93.184.216.34','example.org; echo bad')]:
            with self.assertRaises(ValueError):install_server.site_name(ip,name)

    def test_malformed_download_url_is_controlled_error(self):
        with self.assertRaises(monitor.downloads.DownloadError) as error:
            monitor.downloads.document_file('http://[',monitor.connection,monitor.catalog,monitor.canonical,monitor.permitted,monitor.fetch)
        self.assertEqual(error.exception.status,400)

    def test_duma_catalogue_is_not_a_bill(self):
        source=next(s for s in monitor.catalog() if s['id']=='duma')
        self.assertFalse(monitor.is_publication_link('https://sozd.duma.gov.ru/oz/pch?list=1','Законы о федеральном бюджете на 2026 год',source))
        self.assertTrue(monitor.is_publication_link('https://sozd.duma.gov.ru/bill/686123-8','Проект федерального закона о медицинской помощи № 686123-8',source))

    def test_old_reference_page_is_preserved_outside_medical_feed(self):
        source=next(s for s in monitor.catalog() if s['id']=='duma')
        candidate={**self.candidate,'url':'https://sozd.duma.gov.ru/oz/pch?list=1','title':'Законы о федеральном бюджете на 2026 год'}
        monitor.store_publication(source,candidate,self.content(),True)
        with monitor.connection() as con:
            con.execute('DELETE FROM title_migrations WHERE version=3')
            con.execute('UPDATE publications SET reviewed=1')
            before=dict(con.execute('SELECT * FROM publications').fetchone())
        monitor.initialize()
        after=monitor.list_publications({'relevance':['all']})['publications'][0]
        self.assertEqual(after['category'],'Справочная страница')
        for key in ('url','first_seen','published_at','reviewed','initial'):self.assertEqual(after[key],before[key])
        with patch.object(monitor,'fetch',return_value=self.content('')):result=monitor.scan_source(source)
        self.assertEqual(result['status'],'needs_adapter')

    def test_rkn_communications_services_are_not_medical_acts(self):
        source=next(s for s in monitor.catalog() if s['id']=='rkn')
        self.assertFalse(monitor.is_publication_link('https://rkn.gov.ru/activity/connection/license/','Изменения в закон о связи от 07.07.2003 № 126-ФЗ',source))

    def test_health_detects_broken_database_and_rejects_wrong_auth_scheme(self):
        with patch.dict(os.environ,{'ADMIN_USER':'owner','ADMIN_PASSWORD':'qa-password-long-enough'}):
            server=monitor.ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with urllib.request.urlopen(base+'/health') as response:self.assertTrue(json.load(response)['ok'])
                request=urllib.request.Request(base+'/api/state',headers={'Authorization':'Bearer '+base64.b64encode(b'owner:qa-password-long-enough').decode()})
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                self.assertEqual(error.exception.code,401)
                with monitor.connection() as con:con.execute('DELETE FROM settings')
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/health')
                self.assertEqual(error.exception.code,503)
            finally:server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
