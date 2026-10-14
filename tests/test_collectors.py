import io
import json
import ssl
import time
import urllib.error
import unittest
from unittest.mock import patch
import test_monitor as baseline
monitor=baseline.monitor
import adapters
import transport
import network

class CollectorTests(unittest.TestCase):
    setUp=baseline.FeedTests.setUp
    tearDown=baseline.FeedTests.tearDown
    content=baseline.FeedTests.content
    def test_pending_documents_survive_missing_listing(self):
        listing=self.content('<a href="/documents/test">Приказ о медицинской помощи детям</a>')
        with patch.object(monitor,'fetch',side_effect=[listing,OSError('temporary')]):monitor.scan_source(self.source)
        with monitor.connection() as con:
            con.execute('UPDATE pending_documents SET next_retry=0')
        with patch.object(monitor,'fetch',side_effect=[self.content(''),self.content()]):result=monitor.scan_source(self.source)
        self.assertEqual(result['added'],1)
        self.assertEqual(result['pending'],0)
    def test_explicit_unrelated_acts_are_not_downloaded_but_unclear_are_retained(self):
        listing=self.content('<a href="/documents/schools.pdf">Постановление о строительстве школ</a><a href="/documents/unknown.pdf">Приказ № 25 от 14.10.2026</a>')
        with patch.object(monitor,'fetch',side_effect=[listing,{'type':'binary','raw':b'%PDF-qa'}]) as fetch:result=monitor.scan_source(self.source)
        self.assertEqual(fetch.call_count,2)
        self.assertTrue(fetch.call_args_list[-1].args[0].endswith('/unknown.pdf'))
        self.assertEqual(result['added'],1)
        self.assertEqual(monitor.list_publications({})['publications'][0]['relevance'],'review')
    def test_next_page_is_resumed_on_next_run(self):
        source={**self.source,'page_limit':1}
        page1=self.content('<a href="?page=2">Следующая</a>')
        with patch.object(monitor,'fetch',return_value=page1):monitor.scan_source(source)
        source['page_limit']=2
        with patch.object(monitor,'fetch',side_effect=[page1,self.content('')]) as fetch:monitor.scan_source(source)
        self.assertTrue(any('page=2' in call.args[0] for call in fetch.call_args_list))
    def test_api_metadata_requires_no_document_download(self):
        source=next(s for s in monitor.catalog() if s['id']=='clinrec')
        response=self.content()
        response['text']=json.dumps({'Data':[{'CodeVersion':'123_2','Name':'Анестезия детям','PublishDateStr':'2026-10-14','AgeCategoryStr':'Дети'}],'TotalRecords':1})
        with patch.object(monitor,'fetch',return_value=response) as fetch:result=monitor.scan_source(source)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(result['added'],1)
        row=monitor.list_publications({})['publications'][0]
        self.assertEqual(row['published_at'],'2026-10-14')
        self.assertIn('Наркоз',row['topics'])
    def test_api_failure_is_not_success_or_empty_catalog(self):
        source=next(s for s in monitor.catalog() if s['id']=='clinrec')
        response={**self.content(),'text':'<html>Unavailable</html>'}
        with patch.object(monitor,'fetch',return_value=response):result=monitor.scan_source(source)
        self.assertEqual(result['status'],'blocked')
    def test_miac_title_and_date_from_same_row(self):
        source=next(s for s in monitor.catalog() if s['id']=='kaluga-miac')
        found=adapters.miac_rows('<table><tr><td>21/05/2026</td><td><a href="/documents/2192" title="Скачать документ"></a><a href="/documents/2192">Приказ о медицинских услугах</a></td></tr></table>',source['seeds'][0],monitor.parse_page)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['title'],'Приказ о медицинских услугах')
        self.assertEqual(found[0]['published_at'],'2026-05-21')
    def test_projects_xml_preserves_status_category_and_date(self):
        source=next(s for s in monitor.catalog() if s['id']=='regulation')
        links,total=adapters.parse_projects('<projects total="1"><project id="1"><title>Об утверждении медицинских правил</title><publishDate>2026-10-14T10:00:00Z</publishDate></project></projects>',source)
        self.assertEqual(total,1)
        self.assertTrue(links[0]['title'].startswith('Проект:'))
        self.assertIn('/api/npalist/1',links[0]['url'])
    def test_section_titles_and_illegal_consumption_reports_are_not_acts(self):
        self.assertFalse(monitor.is_publication_link('https://rostrud.gov.ru/control/labor/','Соблюдение законодательства о труде',self.source))
        self.assertFalse(monitor.is_publication_link('https://minzdrav.gov.ru/page/report','Годовой отчет о профилактике незаконного потребления наркотиков за 2026 год',self.source))
    def test_ffoms_card_title_is_not_replaced_by_section_title(self):
        source=next(s for s in monitor.catalog() if s['id']=='ffoms')
        links=adapters.ffoms_rows('<div class="structure-list p-3"><a href="/documents/the-orders-oms/letter-1/"></a><div class="job">Совместное письмо от 03.04.2026 № 31-2/6103</div><div class="name"></div></div>',source['seeds'][0],monitor.parse_page)
        self.assertEqual(len(links),1)
        monitor.store_publication(source,links[0],{**self.content(),'text':'<title>Приказы ФОМС</title>'},False)
        self.assertEqual(monitor.list_publications({})['publications'][0]['title'],'Совместное письмо от 03.04.2026 № 31-2/6103')
    def test_verified_empty_rostrud_catalog_is_distinct_from_unreadable_js(self):
        source=next(s for s in monitor.catalog() if s['id']=='rostrud')
        empty={**self.content(),'text':'<h1>Перечень нормативных актов</h1><div class="b-listing-link"><div class="bs"></div></div>'}
        with patch.object(monitor,'fetch',return_value=empty):result=monitor.scan_source(source)
        self.assertEqual(result['status'],'collected')
    def test_one_document_can_belong_to_two_sources(self):
        monitor.store_publication(self.source,self.candidate,self.content(),False)
        other=next(s for s in monitor.catalog() if s['id']=='roszdrav')
        monitor.store_publication(other,self.candidate,self.content(),False)
        self.assertEqual(monitor.list_publications({'source':[other['id']]})['total'],1)
        self.assertEqual(monitor.list_publications({'relevance':['all']})['total'],1)
    def test_tariff_attachment_from_tfoms_keeps_oms_topic(self):
        source=next(s for s in monitor.catalog() if s['id']=='tfoms')
        relevance,topics,category=monitor.classify('Дополнительное соглашение № 3','',source)
        self.assertEqual(relevance,'medical')
        self.assertIn('ОМС',topics)
        self.assertEqual(category,'ОМС / тарифы')
    def test_conditional_get_uses_etag_and_cached_304_body(self):
        with monitor.connection() as con:
            con.execute('INSERT INTO http_cache VALUES (?,?,?,?,?,?,?,?)',(self.candidate['url'],'"version1"',None,'<main>Приказ</main>'.encode(),'text/html','utf-8',self.candidate['url'],time.time()))
        error=urllib.error.HTTPError(self.candidate['url'],304,'Not modified',{},io.BytesIO())
        opener=unittest.mock.Mock()
        opener.open.side_effect=error
        with patch.object(transport.urllib.request,'build_opener',return_value=opener),patch.object(transport,'pace'):
            result=monitor.fetch(self.candidate['url'],self.source)
        self.assertTrue(result['cached'])
        self.assertIn('Приказ',result['text'])
        self.assertEqual(opener.open.call_args.args[0].get_header('If-none-match'),'"version1"')
    def test_certificate_failure_is_not_retried_without_verification(self):
        opener=unittest.mock.Mock()
        opener.open.side_effect=urllib.error.URLError(ssl.SSLCertVerificationError('synthetic'))
        with patch.object(transport.urllib.request,'build_opener',return_value=opener),patch.object(transport,'pace'):
            with self.assertRaises(urllib.error.URLError):monitor.fetch(self.candidate['url'],self.source)
        self.assertEqual(opener.open.call_count,1)
    def test_portal_database_overload_is_retried_and_reported_clearly(self):
        def unavailable(*args,**kwargs):
            raise urllib.error.HTTPError(self.candidate['url'],500,'Internal Server Error',{},io.BytesIO(b'Mysql connect error: Too many connections'))
        opener=unittest.mock.Mock();opener.open.side_effect=unavailable
        with patch.object(transport.urllib.request,'build_opener',return_value=opener),patch.object(transport,'pace'),patch.object(transport.time,'sleep'):
            with self.assertRaises(urllib.error.HTTPError) as err:monitor.fetch(self.candidate['url'],self.source)
        self.assertEqual(opener.open.call_count,2)
        self.assertIn('базой данных',str(err.exception))
    def test_direct_network_uses_only_its_socket_interface(self):
        sock=unittest.mock.Mock()
        with patch.object(network.socket,'getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]),patch.object(network.socket,'socket',return_value=sock):
            self.assertIs(network.connect_direct(12,('example.gov',443),5),sock)
        sock.setsockopt.assert_called_once_with(network.socket.IPPROTO_IP,31,b'\x00\x00\x00\x0c')
        sock.connect.assert_called_once_with(('8.8.8.8',443))
    def test_direct_network_does_not_connect_to_private_targets(self):
        with patch.object(network.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch.object(network.socket,'socket') as create:
            with self.assertRaises(OSError):network.connect_direct(12,('example.gov',443),5)
        create.assert_not_called()

