import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import document_metadata as dates
import text_extract
import monitor as m
import test_monitor as baseline
m=baseline.monitor

class MetadataTests(unittest.TestCase):
 def test_russian_api_dates_and_invalid_dates(self):
  for value in ['01.10.2026','1/10/2026','1 октября 2026','2026-10-01T11:20:00+03:00']:
   self.assertEqual(dates.normalize(value),'2026-10-01')
  for value in ['31.09.2026','вступает в силу 01.10.2026','123','2026-02-30']:
   self.assertIsNone(dates.normalize(value))
 def test_labelled_publication_not_signing_or_effective_date(self):
  page='<main><h1>Приказ от 01.09.2026 № 3</h1><p>Вступает в силу 01.11.2026</p><span>Дата опубликования:</span><span>02.10.2026</span></main>'
  self.assertEqual(dates.publication(page,{'id':'pravo'},m.parse_page)['date'],'2026-10-02')
 def test_updated_date_never_counts_as_publication(self):
  page='<time datetime="2026-10-14">Обновлён 14 октября 2026</time><meta property="article:modified_time" content="2026-10-14">'
  self.assertIsNone(dates.publication(page,{'id':'minzdrav'},m.parse_page)['date'])
 def test_minzdrav_and_minjust_formats(self):
  pages=['<time datetime="2026-10-02">Опубликован 2 октября 2026</time>','<span>Опубликовано на сайте:</span><span>2 октября 2026</span>','<meta itemprop="datePublished" content="2026-10-02">']
  for page in pages:self.assertEqual(dates.publication(page,{'id':'minzdrav'},m.parse_page)['date'],'2026-10-02')
 def test_conflicting_publication_dates_are_not_guessed(self):
  page='<meta itemprop="datePublished" content="2026-10-02"><time itemprop="datePublished" datetime="2026-10-03">x</time>'
  self.assertIsNone(dates.publication(page,{'id':'minzdrav'},m.parse_page)['date'])
 def test_act_date_is_distinct_from_dates_of_cited_agreements(self):
  self.assertEqual(dates.document_date('Дополнительное соглашение от 07.10.2026 № 8 к Тарифному соглашению от 26.12.2025'),'2026-10-07')
  self.assertIsNone(dates.document_date('Дополнительное соглашение к Тарифному соглашению от 26.12.2025'))
  self.assertIsNone(dates.document_date('О внесении изменений в приказ от 07.10.2026 № 8'))
  self.assertIsNone(dates.document_date('document-20261014.pdf'))
 def test_catalogue_dates_stay_with_their_own_document(self):
  source=next(s for s in m.catalog() if s['id']=='pravo')
  page='<div class="documents-items"><a href="/document/0001202610010001">Приказ о помощи детям № 1</a><span>Дата опубликования:</span><span>01.10.2026</span></div><div class="documents-items"><a href="/document/0001202609300001">Приказ о помощи детям № 2</a><span>Дата опубликования:</span><span>30.09.2026</span></div>'
  found,_=m.discover(page,source['seeds'][0],source)
  self.assertEqual([p['published_at'] for p in found],['2026-10-01','2026-09-30'])
 def test_attachments_outside_source_are_not_fetched(self):
  source=next(s for s in m.catalog() if s['id']=='pravo')
  page='<a href="/file/pdf?eoNumber=0001202610010001">PDF</a><a href="http://127.0.0.1/a.pdf">no</a><a href="https://evil.example/a.docx">no</a>'
  found=dates.attachments(page,source['seeds'][0],source,m.parse_page,m.permitted)
  self.assertEqual(len(found),1);self.assertIn('/file/pdf?',found[0])

class FileTextTests(unittest.TestCase):
 def test_docx_text_without_executing_macros(self):
  raw=io.BytesIO()
  with zipfile.ZipFile(raw,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="urn:w"><w:t>Медицинская помощь детям</w:t></w:document>')
  got=text_extract.extract(raw.getvalue())
  self.assertEqual(got['status'],'docx_text');self.assertIn('детям',got['text'])
 def test_zip_is_not_treated_as_document_text(self):
  raw=io.BytesIO()
  with zipfile.ZipFile(raw,'w') as z:z.writestr('untrusted.sh','echo unsafe')
  self.assertEqual(text_extract.extract(raw.getvalue())['status'],'unsupported_file')
 def test_pdf_without_text_is_marked_for_ocr(self):
  from pypdf import PdfWriter
  raw=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.write(raw)
  self.assertEqual(text_extract.extract(raw.getvalue())['status'],'scan_needs_ocr')
 def test_pdf_text_and_truncation(self):
  from pypdf import PdfWriter
  from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
  writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
  font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
  page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
  stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 700 Td (Medical care and diagnostic equipment requirements) Tj ET')
  page[NameObject('/Contents')]=writer._add_object(stream)
  raw=io.BytesIO();writer.write(raw);got=text_extract.extract(raw.getvalue())
  self.assertEqual(got['status'],'pdf_text');self.assertIn('Medical care',got['text'])

class StoreExtractionTests(unittest.TestCase):
 setUp=baseline.FeedTests.setUp
 tearDown=baseline.FeedTests.tearDown
 content=baseline.FeedTests.content
 def test_page_date_evidence_and_text_are_persisted(self):
  html='<main><h1>Приказ о медицинской помощи</h1><p>Дата опубликования: 01.10.2026</p><p>Медицинская помощь детям</p></main>'
  with patch.dict(m.__dict__,PUBLICATION_SINCE='2026-10-01'):
   self.assertTrue(m.store_publication(self.source,{**self.candidate,'published_at':None},self.content(html),False))
  with m.connection() as con:
   row=con.execute('SELECT * FROM publication_content').fetchone()
   self.assertIn('Дата',row['date_basis']);self.assertIn('детям',row['text']);self.assertEqual(row['text_status'],'page_text')
 def test_undated_pdf_does_not_get_a_date_from_its_filename(self):
  with patch.dict(m.__dict__,PUBLICATION_SINCE='2026-10-01'),patch.object(text_extract,'extract',return_value={'text':'Приказ без установленной даты','status':'scan_needs_ocr'}) as extract:
   self.assertFalse(m.store_publication(self.source,{**self.candidate,'published_at':None,'url':'https://minzdrav.gov.ru/2026/10/14/act.pdf'},{'type':'binary','raw':b'%PDF'},False))
   extract.assert_called_once()
 def test_owner_allows_confirmed_new_act_date_without_publication_date(self):
  source={**self.source,'allow_document_date':True}
  candidate={**self.candidate,'published_at':None,'title':'Приказ о медицинской помощи'}
  with patch.dict(m.__dict__,PUBLICATION_SINCE='2026-10-01'),patch.object(text_extract,'extract',return_value={'text':'ПРИКАЗ Министерства здравоохранения от 07.10.2026 № 8 О медицинской помощи','status':'pdf_ocr'}):
   self.assertTrue(m.store_publication(source,candidate,{'type':'binary','raw':b'%PDF'},False))
  with m.connection() as con:
   self.assertEqual(con.execute('SELECT published_at FROM publications').fetchone()[0],'2026-10-07')
   self.assertIn('Дата самого акта',con.execute('SELECT date_basis FROM publication_content').fetchone()[0])
 def test_explicit_publication_date_overrides_candidate_act_date(self):
  candidate={**self.candidate,'published_at':'2026-10-07','date_basis':'Дата самого акта; дата публикации не указана'}
  page=self.content('<main>Приказ о медицинской помощи. Дата опубликования: 14.10.2026</main>')
  with patch.dict(m.__dict__,PUBLICATION_SINCE='2026-10-01'):
   self.assertTrue(m.store_publication(self.source,candidate,page,False))
  with m.connection() as con:self.assertEqual(con.execute('SELECT published_at FROM publications').fetchone()[0],'2026-10-14')
 def test_conflicting_page_dates_cannot_be_overridden_by_catalogue(self):
  html='<meta itemprop="datePublished" content="2026-10-02"><time itemprop="datePublished" datetime="2026-10-03">x</time>'
  result=self.content(html)
  with patch.dict(m.__dict__,PUBLICATION_SINCE='2026-10-01'):
   self.assertFalse(m.store_publication(self.source,{**self.candidate,'published_at':'2026-10-02'},result,False))
  self.assertTrue(result['date_rejected'])
