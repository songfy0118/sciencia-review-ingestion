import http.client
import json
import sqlite3
from contextlib import closing
import tempfile
import threading
import unittest
from functools import partial
from pathlib import Path

from review_ingestion.play_pipeline import run_once
from review_ingestion.refresh_play import refresh
from review_ingestion.serve_play import Collector, make_server, parse_app


class ControlPanelTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.entered, self.release = threading.Event(), threading.Event()

        def fetch(**request):
            self.entered.set()
            if not self.release.wait(5):
                raise RuntimeError('Fixture collection was not released')
            key = 'second' if request['cursor'] else 'first'
            return dict(records=[dict(reviewId=key, content='Useful', score=4, at='2026-09-27T10:00:00Z')],
                        cursor=None if request['cursor'] else 'next-page')

        def runner(**options):
            options['delay'] = 0
            return refresh(**options, collector=partial(run_once, fetcher=fetch))

        self.collector = Collector(root / 'live.sqlite3', root / 'results',
                                   [dict(app_id='com.example.app', label='Example')], runner)
        self.server = make_server(self.collector, 0)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.stop)
        self.token = self.request('GET', '/api/state')[1]['token']

    def stop(self):
        self.release.set()
        if self.collector.thread:
            self.collector.thread.join(5)
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(5)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method, path, json.dumps(body) if body is not None else None, headers or {})
            response = conn.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if response.getheader('Content-Type') == 'application/json' else raw
        finally:
            conn.close()

    def post(self, body):
        return self.request('POST', '/api/collect', body, {
            'Origin': f'http://127.0.0.1:{self.server.server_port}', 'X-Collection-Token': self.token})

    def test_start_is_nonblocking_and_duplicate_click_is_rejected(self):
        self.assertEqual(self.post({'apps': ['com.example.app']})[0], 202)
        self.assertTrue(self.entered.wait(3))
        self.assertTrue(self.request('GET', '/api/state')[1]['active'])
        self.assertEqual(self.post({'apps': ['com.example.app']})[0], 409)
        self.release.set()
        self.collector.thread.join(5)
        state = self.request('GET', '/api/state')[1]
        self.assertFalse(state['active'])
        self.assertEqual(state['stored_reviews'], 1)
        self.assertTrue(state['cycles'][0]['result_url'])
        self.assertEqual(self.request('GET', state['cycles'][0]['result_url'])[0], 200)
        self.assertEqual(self.request('GET', '/results/index.html')[0], 200)

    def test_resume_after_controller_restart_reuses_stored_cursor(self):
        self.release.set()
        self.post({'apps': ['com.example.app'], 'count': 25})
        self.collector.thread.join(5)
        run = self.collector.state()['runs'][0]
        restarted = Collector(self.collector.db, self.collector.output, self.collector.apps, self.collector.runner)
        options = restarted.prepare({'resume': run['run_id'], 'pages': 1})
        self.assertEqual(options['count'], 25)
        restarted.start({'resume': run['run_id'], 'pages': 1})
        restarted.thread.join(5)
        self.assertEqual(restarted.state()['stored_reviews'], 2)
        self.assertFalse(restarted.state()['runs'][0]['can_resume'])

    def test_foreign_origin_missing_token_and_host_are_rejected(self):
        body = {'apps': ['com.example.app']}
        self.assertEqual(self.request('POST', '/api/collect', body)[0], 403)
        self.assertEqual(self.request('POST', '/api/collect', body, {'Origin': 'https://example.com',
                         'X-Collection-Token': self.token})[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Host': 'attacker.example'})[0], 403)
        self.assertFalse(self.collector.db.exists())

    def test_bad_input_and_duplicate_ids_do_not_start_collection(self):
        for body in ([], {'apps': []}, {'apps': ['not-an-id']}, {'apps': ['com.example.app'], 'pages': True},
                     {'apps': ['com.example.app'], 'pages': 6}, {'apps': ['com.example.app', 'com.example.app']}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0], 400)
        self.assertFalse(self.collector.db.exists())

    def test_file_serving_is_restricted_to_result_files(self):
        for path in ('/results/../../README.md', '/results/' + 'a'*32 + '/../../README.md', '/README.md'):
            self.assertEqual(self.request('GET', path)[0], 404)

    def test_google_play_links_are_normalized_without_fetching_arbitrary_urls(self):
        self.assertEqual(parse_app(' https://play.google.com/store/apps/details?id=com.example.app&hl=en '), 'com.example.app')
        for value in ('https://example.com/?id=com.example.app', 'https://play.google.com@evil.example/store/apps/details?id=com.example.app'):
            with self.assertRaises(ValueError):
                parse_app(value)

    def test_new_app_shares_database_without_mixing_reviews_or_losing_its_name(self):
        self.release.set()
        body = {'apps': ['com.example.app'],
                'extra_app': 'https://play.google.com/store/apps/details?id=com.example.other',
                'extra_name': 'Another app', 'count': 25}
        self.assertEqual(self.post(body)[0], 202)
        self.collector.thread.join(5)
        with closing(sqlite3.connect(self.collector.db)) as c:
            # The fixture returns the same review ID for both apps.
            self.assertEqual(c.execute('SELECT count(*) FROM reviews').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT count(DISTINCT app_id) FROM reviews').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT label FROM apps WHERE app_id=?',
                                      ('com.example.other',)).fetchone()[0], 'Another app')
        self.assertEqual(self.collector.prepare({'apps': ['com.example.other']})['apps'][0]['label'], 'Another app')
        self.assertEqual(self.post(body)[0], 202)
        self.collector.thread.join(5)
        self.assertEqual(self.collector.state()['stored_reviews'], 2)
        result = self.collector.state()['cycles'][0]['result_url']
        status, page = self.request('GET', result)
        self.assertEqual(status, 200)
        self.assertIn(b'Another app', page)

    def test_extra_app_validation_and_combined_limit(self):
        for body in ({'apps': [], 'extra_app': 'Uber'},
                     {'apps': ['com.example.app'], 'extra_app': 'com.example.app'},
                     {'apps': [], 'extra_app': 'com.example.other', 'extra_name': 'x' * 81},
                     {'apps': ['com.example.a', 'com.example.b', 'com.example.c', 'com.example.d', 'com.example.e'],
                      'extra_app': 'com.example.f'}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0], 400)
