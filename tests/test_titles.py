import time
import datetime as dt
import unittest
from unittest.mock import patch
import test_monitor as baseline
import adapters
import titles
monitor=baseline.monitor

class TitleTests(unittest.TestCase):
    setUp=baseline.FeedTests.setUp
    tearDown=baseline.FeedTests.tearDown
    content=baseline.FeedTests.content

    def test_subject_is_copied_and_original_preserved(self):
        candidate={**self.candidate,'title':'Приказ Минздрава от 14.10.2026 № 25'}
        monitor.store_publication(self.source,candidate,self.content('<h1>Об утверждении порядка медицинской помощи детям</h1>'),False)
        row=monitor.list_publications({})['publications'][0]
        self.assertEqual(row['title'],candidate['title']+' — Об утверждении порядка медицинской помощи детям')
        self.assertEqual(row['original_title'],candidate['title'])

    def test_already_informative_title_is_kept(self):
        title='Приказ № 25 «Об утверждении порядка медицинской помощи»'
        self.assertEqual(titles.detail_title(title,'<h1>О других требованиях к помощи детям</h1>',monitor.parse_page),title)

    def test_other_law_in_body_is_not_used(self):
        title='Постановление от 14.10.2026 № 25'
        self.assertEqual(titles.detail_title(title,'<main><p>См. закон «Об охране здоровья граждан».</p></main>',monitor.parse_page),title)
        self.assertEqual(titles.detail_title(title,'<main><h1>Каталог</h1><h2>Об охране здоровья граждан</h2></main>',monitor.parse_page),title)

    def test_binary_without_description_is_not_invented(self):
        monitor.store_publication(self.source,{**self.candidate,'title':'Скачать'}, {'type':'binary'},False)
        row=monitor.list_publications({})['publications'][0]
        self.assertEqual(row['title'],'Скачать')

    def test_tfoms_uses_only_comment_from_same_attachment_card(self):
        source=next(s for s in monitor.catalog() if s['id']=='tfoms')
        text='<div class="elem"><a href="/a.zip"><span>Дополнительное соглашение № 3</span></a><div class="comment">от 13.04.2026 к Тарифному соглашению в сфере обязательного медицинского страхования в Калужской области от 26.12.2025</div></div><div class="elem"><a href="/b.zip">Дополнительное соглашение № 4</a><div class="comment">от 29.04.2026 к Тарифному соглашению от 26.12.2025</div></div>'
        links,_=monitor.discover(text,source['seeds'][0],source)
        self.assertIn('13.04.2026',links[0]['title'])
        self.assertNotIn('29.04.2026',links[0]['title'])
        self.assertEqual(links[0]['original_title'],'Дополнительное соглашение № 3')

    def test_ffoms_selects_subject_in_own_card(self):
        source=next(s for s in monitor.catalog() if s['id']=='ffoms')
        text='<div class="structure-list"><a href="/documents/one/"></a><div class="job">Приказ ФОМС № 13</div><div class="name">Об утверждении порядка оплаты медицинской помощи</div></div><div class="structure-list"><a href="/documents/two/"></a><div class="job">Приказ ФОМС № 14</div><div class="name">О внесении изменений в бюджет</div></div>'
        links=adapters.ffoms_rows(text,source['seeds'][0],monitor.parse_page)
        self.assertIn('порядка оплаты',links[0]['title'])
        self.assertNotIn('бюджет',links[0]['title'])
        monitor.store_publication(source,links[0],self.content(),False)
        self.assertEqual(monitor.list_publications({})['publications'][0]['original_title'],'Приказ ФОМС № 13')

    def test_cached_upgrade_preserves_count_review_and_dates(self):
        candidate={**self.candidate,'title':'Приказ Минздрава № 25'}
        monitor.store_publication(self.source,candidate,self.content(),True)
        with monitor.connection() as con:
            con.execute('UPDATE publications SET reviewed=1')
            before=dict(con.execute('SELECT * FROM publications').fetchone())
            con.execute('DELETE FROM title_migrations')
            con.execute('INSERT INTO http_cache VALUES (?,?,?,?,?,?,?,?)',(candidate['url'],None,None,'<main><h1>Об утверждении порядка медицинской помощи детям</h1></main>'.encode(),'text/html','utf-8',candidate['url'],time.time()))
        with patch.object(monitor,'fetch',side_effect=AssertionError('No network')):
            monitor.initialize()
            monitor.initialize()
        rows=monitor.list_publications({})['publications']
        self.assertEqual(len(rows),1)
        self.assertIn('Об утверждении',rows[0]['title'])
        for key in ('first_seen','published_at','reviewed','initial'):
            self.assertEqual(rows[0][key],before[key])

    def test_known_link_can_gain_subject_without_download(self):
        original='Приказ Минздрава № 25'
        candidate={**self.candidate,'title':original}
        monitor.store_publication(self.source,candidate,self.content(),False)
        enriched={**candidate,'title':original+' — Об утверждении порядка медицинской помощи','original_title':original}
        self.assertFalse(monitor.store_publication(self.source,enriched,self.content(),False))
        row=monitor.list_publications({})['publications'][0]
        self.assertEqual(row['original_title'],original)
        self.assertIn('Об утверждении',row['title'])

    def test_first_install_has_no_delay_for_initial_collection(self):
        self.assertIsNone(monitor.next_collection_at())

    def test_schedule_recovers_from_saved_run_after_restart(self):
        with monitor.connection() as con:
            con.execute('INSERT INTO runs VALUES (?,?,?,?)',('one','2026-10-14T06:00:00+00:00','2026-10-14T06:05:00+00:00','[]'))
            con.execute('INSERT INTO runs VALUES (?,?,?,?)',('interrupted','2026-10-14T10:00:00+00:00',None,None))
        monitor.initialize()
        self.assertEqual(monitor.next_collection_at(),dt.datetime(2026,10,14,12,tzinfo=dt.timezone.utc))

    def test_local_mode_reports_automatic_collection_disabled(self):
        with patch.dict(monitor.os.environ,{'LOCAL_TEST':'1'}):
            self.assertFalse(monitor.app_state()['schedule']['enabled'])

if __name__=='__main__':unittest.main()
