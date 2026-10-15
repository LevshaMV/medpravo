import unittest
from unittest.mock import patch
import test_monitor as baseline
import date_policy

m=baseline.monitor
class DatePolicyTests(baseline.FeedTests):
    def test_cutoff_is_inclusive_and_unknown_is_not_discovery_time(self):
        self.assertTrue(date_policy.eligible('2026-10-01'))
        for value in [None,'','2026-09-30','2026-02-30','2999-10-01']:
            self.assertFalse(date_policy.eligible(value))
    def test_collector_does_not_store_old_or_undated(self):
        with patch.dict(m.__dict__,PUBLICATION_SINCE=date_policy.SINCE):
            for day in ['2026-09-30',None]:
                self.assertFalse(m.store_publication(self.source,{**self.candidate,'published_at':day},self.content(),False))
            self.assertTrue(m.store_publication(self.source,{**self.candidate,'published_at':'2026-10-01'},self.content(),False))
    def test_migration_removes_old_records_and_child_metadata(self):
        for i,day in enumerate(['2026-09-30',None,'2026-10-01']):
            m.store_publication(self.source,{**self.candidate,'url':self.candidate['url']+str(i),'published_at':day},self.content(),False)
        self.assertEqual(date_policy.prune(m.connection),2)
        with m.connection() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM publications').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT count(*) FROM publication_sources').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT count(*) FROM publication_labels').fetchone()[0],1)
