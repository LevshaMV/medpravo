import contextlib
import gzip
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_monitor as baseline
import github_collect as c
import github_state as state

class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.old=c.m.DATA;c.m.DATA=self.root/'data';c.m.initialize()
        self.source=next(s for s in c.m.catalog() if s['id']=='minzdrav')
        self.doc={'url':'https://minzdrav.gov.ru/documents/test','title':'Приказ о помощи детям','published_at':'2026-10-14'}
        c.m.store_publication(self.source,self.doc,{'type':'metadata','text':''},True)
    def tearDown(self):
        c.m.DATA=self.old;self.tmp.cleanup()
    def test_export_contains_only_public_fields_and_relative_assets(self):
        with c.m.connection() as con:con.execute('UPDATE publications SET reviewed=1')
        data=c.export_site(self.root/'site','LevshaMV/medpravo',archive=False)
        self.assertFalse(data['publications'][0]['reviewed'])
        self.assertIsNone(data['last_checked_at'])
        self.assertNotIn('http_cache',data)
        self.assertNotIn('runs',data)
        page=(self.root/'site/index.html').read_text(encoding='utf-8')
        self.assertIn('./github-client.js',page);self.assertNotIn('href="/style.css"',page)
        self.assertIn('/actions/workflows/collect.yml',data['workflow_url'])
    def test_state_restore_keeps_queue_dates_and_history_without_cache_or_reviews(self):
        with c.m.connection() as con:
            con.execute('UPDATE publications SET reviewed=1')
            con.execute('INSERT OR REPLACE INTO source_cursor VALUES (?,?)',('minzdrav','["https://minzdrav.gov.ru/documents?page=2"]'))
            con.execute('INSERT INTO http_cache VALUES (?,?,?,?,?,?,?,?)',('https://minzdrav.gov.ru/a',None,None,b'secret test cache','text/html','utf-8','https://minzdrav.gov.ru/a',9999999999))
        persist=self.root/'persist';c.compact_state(persist)
        fresh=self.root/'fresh';self.assertTrue(c.restore_state(persist,fresh))
        with contextlib.closing(sqlite3.connect(fresh/'monitor.sqlite')) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM publications').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT reviewed FROM publications').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT count(*) FROM http_cache').fetchone()[0],0)
            self.assertIn('page=2',con.execute('SELECT queue FROM source_cursor').fetchone()[0])
        with self.assertRaises(ValueError):c.restore_state(persist,fresh)
    def test_corrupt_state_does_not_silently_reset_history(self):
        persist=self.root/'persist';persist.mkdir();(persist/'state.sqlite.gz').write_bytes(gzip.compress(b'not sqlite'))
        with self.assertRaises(ValueError):c.restore_state(persist,self.root/'new')
    def test_file_archive_reuses_verified_copy_and_never_emits_html(self):
        source=next(s for s in c.m.catalog() if s['id']=='tfoms')
        doc={**self.doc,'url':'https://oms-kaluga.ru/files/test.pdf','title':'Тарифное соглашение ОМС.pdf'}
        c.m.store_publication(source,doc,{'type':'binary','raw':b'%PDF-qa'},True)
        persist=self.root/'persist';site=self.root/'site';site.mkdir()
        with patch.object(c.m,'fetch',return_value={'type':'binary','raw':b'%PDF-qa'}):
            pubs=c.publications();result=c.archive_files(pubs,persist,site)
        self.assertEqual(result['files'],1)
        target=next(p for p in pubs if p['source_id']=='tfoms')['download_path']
        self.assertEqual((site/target).read_bytes(),b'%PDF-qa')
        with patch.object(c.m,'fetch',side_effect=AssertionError('Must reuse cached file')):self.assertEqual(c.archive_files(c.publications(),persist,site)['files'],1)
        for p in (persist/'files').iterdir():p.write_bytes(b'<html>bad</html>')
        with patch.object(c.m,'fetch',return_value={'type':'text','raw':b'<html>bad</html>'}):
            result=c.archive_files(c.publications(),persist,site)
        self.assertEqual(result['files'],0)
    def test_git_state_survives_two_clean_clones(self):
        original=Path.cwd()
        remote=self.root/'remote.git';repo=self.root/'repo'
        subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
        subprocess.run(['git','init',str(repo)],check=True,capture_output=True)
        def run(*args,cwd=repo):return subprocess.run(['git',*args],cwd=cwd,check=True,capture_output=True)
        run('config','user.name','QA');run('config','user.email','qa@example.invalid')
        (repo/'README.md').write_text('qa');run('add','.');run('commit','-m','initial');run('remote','add','origin',str(remote));run('push','origin','HEAD:main')
        folder=repo/'.state';persist=folder/'persist';c.compact_state(persist)
        try:
            import os
            os.chdir(repo);state.save(folder)
            clone=self.root/'clone';subprocess.run(['git','clone','--branch','main',str(remote),str(clone)],check=True,capture_output=True)
            os.chdir(clone);state.restore(clone/'.state')
            self.assertTrue(c.restore_state(clone/'.state/persist',clone/'.state/data'))
            c.m.DATA=clone/'.state/data';c.m.initialize()
            # Known URL remains one record after another collection process.
            self.assertFalse(c.m.store_publication(self.source,self.doc,{'type':'metadata','text':''},False))
            c.compact_state(clone/'.state/persist');state.save(clone/'.state')
            names=run('ls-tree','-r','--name-only','medpravo-state',cwd=remote).stdout.decode()
            self.assertEqual(names.strip(),'state.sqlite.gz')
        finally:os.chdir(original)

if __name__=='__main__':unittest.main()
