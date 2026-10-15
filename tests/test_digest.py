from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

import daily_digest as d

def publication(suffix='1', **changes):
    return {'url': 'https://minzdrav.gov.ru/documents/' + suffix,
            'title': 'Приказ о порядке оплаты медицинской помощи по ОМС',
            'category': 'Приказ', 'source_id': 'minzdrav', 'published_at': '2026-10-15',
            'first_seen': '2026-10-15T12:00:00+03:00', 'relevance': 'medical',
            'topics': ['ОМС'], 'text_status': 'page_text', 'date_kind': 'publication',
            'text_excerpt': 'Утверждается порядок оплаты медицинской помощи по ОМС.', **changes}

def source_data(*pubs):
    return {'publications': list(pubs), 'last_checked_at': '2026-10-15T14:50:46+03:00',
            'sources': [{'id': 'minzdrav', 'name': 'Минздрав', 'status': 'partial', 'detail': 'Очередь обхода'}],
            'settings': {'enabled_sources': ['minzdrav']}}

def inference(sources):
    return {s['id']: {'summary': 'Документ описывает порядок оплаты помощи по ОМС.',
                      'why': 'Может касаться расчётов центра по ОМС.',
                      'check': 'Сверить круг организаций и сроки в оригинале.',
                      'evidence': s['title']} for s in sources}

def history(): return {'schema': 1, 'reports': []}

class DigestTests(unittest.TestCase):
    now = datetime.fromisoformat('2026-10-15T18:10:00+03:00')

    def test_moscow_cutoff_and_medical_scope(self):
        pubs = [publication(), publication('old', first_seen='2026-10-14T18:00:00+03:00'),
                publication('future', first_seen='2026-10-15T18:00:01+03:00'),
                publication('noise', relevance='other'), publication('review', relevance='review'),
                publication('nonmedical-review', relevance='review', topics=[])]
        report = d.make_digest(source_data(*pubs), history(), self.now, inference)['reports'][0]
        self.assertEqual(report['total'], 2)
        self.assertEqual(report['analyzed'], 2)
        self.assertEqual(report['period_end'], '2026-10-15T18:00:00+03:00')
        self.assertEqual(report['responding_sources'], 1)
        self.assertEqual(len(report['source_issues']), 1)

    def test_empty_day_does_not_call_model(self):
        def no_call(_): self.fail('Empty day must not call inference')
        report = d.make_digest(source_data(), history(), self.now, no_call)['reports'][0]
        self.assertEqual(report['status'], 'empty')
        self.assertIsNone(report['model'])
        self.assertTrue(report['source_issues'])

    def test_partial_error_does_not_advance_cursor_or_lose_pending(self):
        def failed(_): raise d.InferenceError('Квота исчерпана')
        first = d.make_digest(source_data(publication()), history(), self.now, failed)
        self.assertEqual(first['reports'][0]['status'], 'unavailable')
        day2 = datetime.fromisoformat('2026-10-16T18:01:00+03:00')
        # Without a successful report the default period would lose yesterday's candidate:
        # retry window must begin at the oldest unfinished period.
        second = d.make_digest(source_data(publication()), first, day2, inference)
        self.assertEqual(second['reports'][-1]['total'], 1)

    def test_republish_cache_never_calls_paid_or_alternate_model(self):
        data = source_data(publication())
        first = d.make_digest(data, history(), self.now, inference)
        second = d.make_digest(data, first, self.now, lambda _: self.fail('Must reuse checked analysis'))
        self.assertEqual(second['reports'][-1]['analyzed'], 1)

    def test_provisional_report_does_not_consume_evening_window(self):
        early = datetime.fromisoformat('2026-10-15T16:00:00+03:00')
        first = d.make_digest(source_data(publication()), history(), early, inference)
        self.assertTrue(first['reports'][0]['provisional'])
        late_pub = publication('2', first_seen='2026-10-15T17:30:00+03:00')
        evening = d.make_digest(source_data(publication(), late_pub), first, self.now, inference)['reports'][0]
        self.assertFalse(evening['provisional'])
        self.assertEqual(evening['total'], 2)

    def test_failed_rerun_keeps_successful_report(self):
        first = d.make_digest(source_data(publication()), history(), self.now, inference)
        def failed(_): raise d.InferenceError('Unavailable')
        second = d.make_digest(source_data(publication(), publication('2')), first, self.now, failed)
        self.assertEqual(second['reports'][0]['status'], 'complete')
        self.assertEqual(second['last_attempt']['status'], 'partial')

    def test_titles_only_are_labelled_and_category_preserved(self):
        report = d.make_digest(source_data(publication(text_excerpt='', category='Проект')), history(), self.now, inference)['reports'][0]
        item = report['items'][0]
        self.assertEqual(item['basis'], 'title_only')
        self.assertEqual(item['category'], 'Проект')
        self.assertEqual(item['url'], publication()['url'])

    def test_invented_quote_or_id_is_rejected(self):
        sources = [d.source_input(publication())]
        answer = {'items': [{'id': sources[0]['id'], **inference(sources)[sources[0]['id']]}]}
        answer['items'][0]['evidence'] = 'Выдуманная обязанность вступает в силу завтра'
        with self.assertRaises(ValueError): d.parse_answer(json.dumps(answer), sources)
        answer['items'][0]['id'] = 'invented'
        with self.assertRaises(ValueError): d.parse_answer(json.dumps(answer), sources)

    def test_duplicate_or_missing_result_is_rejected(self):
        sources = [d.source_input(publication()), d.source_input(publication('2'))]
        one = {'id': sources[0]['id'], **inference(sources)[sources[0]['id']]}
        for items in ([one], [one, one]):
            with self.assertRaises(ValueError): d.parse_answer(json.dumps({'items': items}), sources)

    def test_loopback_endpoint_no_credentials_and_bounded_requests(self):
        sources = [d.source_input(publication())]
        result = {'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({'items': [{'id': sources[0]['id'], **inference(sources)[sources[0]['id']]}]})}}
        seen = []
        def opener(request, timeout):
            seen.append(request)
            return io.BytesIO(json.dumps(result).encode())
        model = d.LocalModel(opener=opener, sleep=lambda _: None)
        self.assertEqual(model(sources), inference(sources))
        self.assertEqual(seen[0].full_url, d.ENDPOINT)
        self.assertEqual(seen[0].full_url, 'http://127.0.0.1:11434/api/chat')
        self.assertIsNone(seen[0].get_header('Authorization'))
        self.assertEqual(json.loads(seen[0].data)['model'], d.MODEL)
        model.calls = d.MAX_CALLS
        with self.assertRaises(d.InferenceError): model(sources)
        self.assertEqual(len(seen), 1)

    def test_runtime_error_does_not_disclose_response_body(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, 'Forbidden', {}, io.BytesIO(b'private-test-token'))
        model = d.LocalModel(opener=opener, sleep=lambda _: None)
        with self.assertRaises(d.InferenceError) as error: model([d.source_input(publication())])
        self.assertNotIn('private-test-token', str(error.exception))
        self.assertIn('Qwen', str(error.exception))

    def test_corrupt_history_fails_instead_of_resetting_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'digests.json'
            path.write_text('invalid')
            with self.assertRaises(ValueError): d.load_history(path)

if __name__ == '__main__': unittest.main()
