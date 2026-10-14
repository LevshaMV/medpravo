import base64
import json
import os
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch
import test_monitor as baseline
import downloads
monitor=baseline.monitor

class DownloadTests(unittest.TestCase):
    setUp=baseline.FeedTests.setUp
    tearDown=baseline.FeedTests.tearDown
    content=baseline.FeedTests.content

    def stored_file(self):
        candidate={**self.candidate,'url':'https://minzdrav.gov.ru/files/приказ № 25.zip','source_page':self.source['seeds'][0]}
        monitor.store_publication(self.source,candidate,{'type':'binary'},False)
        return candidate

    def relay(self,url):
        return downloads.document_file(url,monitor.connection,monitor.catalog,monitor.canonical,monitor.permitted,monitor.fetch)

    def test_real_zip_signature_and_utf8_filename(self):
        candidate=self.stored_file()
        with patch.object(monitor,'fetch',return_value={'type':'binary','raw':b'PK\x03\x04payload'}):
            raw,name,mime=self.relay(candidate['url'])
        self.assertEqual(name,'приказ № 25.zip')
        self.assertEqual(mime,'application/zip')
        self.assertEqual(raw,b'PK\x03\x04payload')

    def test_arbitrary_url_is_not_a_proxy(self):
        with patch.object(monitor,'fetch') as fetch:
            with self.assertRaises(downloads.DownloadError) as error:self.relay('http://127.0.0.1/private.zip')
        self.assertEqual(error.exception.status,404)
        fetch.assert_not_called()

    def test_stored_url_must_still_belong_to_source(self):
        candidate={**self.candidate,'url':'https://attacker.example/file.zip'}
        monitor.store_publication(self.source,candidate,{'type':'binary'},False)
        with patch.object(monitor,'fetch') as fetch:
            with self.assertRaises(downloads.DownloadError) as error:self.relay(candidate['url'])
        self.assertEqual(error.exception.status,403);fetch.assert_not_called()

    def test_html_disguised_as_archive_is_reported(self):
        candidate=self.stored_file()
        with patch.object(monitor,'fetch',return_value={'type':'binary','raw':b'<html>Access denied</html>'}):
            with self.assertRaises(downloads.DownloadError) as error:self.relay(candidate['url'])
        self.assertEqual(error.exception.status,502)

    def test_network_failure_is_clear_and_slot_is_released(self):
        candidate=self.stored_file()
        with patch.object(monitor,'fetch',side_effect=OSError('temporary')):
            with self.assertRaises(downloads.DownloadError) as error:self.relay(candidate['url'])
        self.assertEqual(error.exception.status,502)
        with patch.object(monitor,'fetch',return_value={'raw':b'PK\x03\x04retry'}):
            self.assertEqual(self.relay(candidate['url'])[0],b'PK\x03\x04retry')

    def test_source_page_survives_pending_queue(self):
        listing=self.content('<a href="/files/document.zip">Приказ о медицинской помощи детям</a>')
        listing['url']=self.source['seeds'][0]
        with patch.object(monitor,'fetch',side_effect=[listing,{'type':'binary','raw':b'PK\x03\x04'}]):monitor.scan_source(self.source)
        row=monitor.list_publications({})['publications'][0]
        self.assertEqual(row['source_page'],self.source['seeds'][0])
        self.assertEqual(row['file_type'],'zip')

    def test_location_from_another_domain_is_not_saved(self):
        candidate={**self.candidate,'source_page':'https://attacker.example/'}
        monitor.store_publication(self.source,candidate,self.content(),False)
        self.assertIsNone(monitor.list_publications({})['publications'][0]['source_page'])

    def test_http_file_requires_login_and_sets_attachment_headers(self):
        candidate=self.stored_file()
        with patch.dict(os.environ,{'ADMIN_USER':'owner','ADMIN_PASSWORD':'qa-password-long-enough'}),patch.object(monitor,'fetch',return_value={'raw':b'PK\x03\x04payload'}):
            server=monitor.ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_port)+'/api/file?'+urllib.parse.urlencode({'url':candidate['url']})
            try:
                with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(url)
                self.assertEqual(err.exception.code,401)
                auth='Basic '+base64.b64encode(b'owner:qa-password-long-enough').decode()
                with urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':auth})) as response:
                    self.assertIn('attachment;',response.headers['Content-Disposition'])
                    self.assertIn('filename*=UTF-8',response.headers['Content-Disposition'])
                    self.assertEqual(response.headers['Content-Type'],'application/zip')
                    self.assertEqual(response.read(),b'PK\x03\x04payload')
            finally:server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
