import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from review_ingestion.audit_play import audit
from review_ingestion.google_play import utc_now
from review_ingestion.google_play_cli import assessment_status, main, persist_assessments
from review_ingestion.play_pipeline import SourceError, run_once


REVIEW_TIME = utc_now()


def record(key, **changes):
    return dict(reviewId=key, content='Review', score=4, at=REVIEW_TIME) | changes


class CatchupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / 'reviews.sqlite3'
        self.apps = [dict(app_id=f'com.example.app{i}', label=f'App {i}') for i in range(3)]
        self.args = dict(db_path=self.db, apps=self.apps, count=100, pages=10,
                         catch_up=True, max_pages=10, delay=0, retries=0)

    def query(self, sql, params=()):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute(sql, params).fetchall()

    def seed(self, count=100):
        return run_once(**(self.args | dict(catch_up=False, pages=1)),
                        fetcher=lambda **_: dict(records=[record(f'old-{i}') for i in range(count)], cursor=None))

    def test_three_apps_capture_more_than_200_and_stop_before_old_tail(self):
        self.seed()
        calls = []
        def fetch(**r):
            calls.append((r['app_id'], r['cursor']))
            page = int(r['cursor'] or 0)
            ids = [f'new-{i}' for i in range(260)] + [f'old-{i}' for i in range(100)]
            return dict(records=[record(k) for k in ids[page*100:(page+1)*100]], cursor=str(page+1))
        result = run_once(**self.args, fetcher=fetch)
        self.assertEqual(len(calls), 9)
        self.assertEqual(result['unique_reviews_in_database'], 1080)
        for app in result['apps']:
            self.assertEqual((app['new_records'], app['repeated_records'], app['pages']), (260, 40, 3))
            self.assertEqual(app['catch_up']['stop_reason'], 'known_id_reached')
            self.assertEqual(app['catch_up']['known_ids_observed'], 40)
            self.assertFalse(app['can_resume'])
            saved = {r[0] for r in self.query('SELECT review_id FROM reviews WHERE app_id=?', (app['app_id'],))}
            self.assertTrue({f'new-{i}' for i in range(260)} <= saved)
        self.assertTrue(audit(self.db)['storage_checks_passed'])
        self.assertEqual(self.query('SELECT count(*) FROM reviews')[0][0], 1080)

    def test_repeated_page_ids_are_not_pre_run_boundaries(self):
        self.seed(1)
        pages = iter([(['a', 'b'], 'one'), (['b', 'c'], 'two'), (['old-0', 'd'], 'three')])
        calls = []
        def fetch(**r):
            calls.append(r['cursor'])
            ids, cursor = next(pages)
            return dict(records=[record(k) for k in ids], cursor=cursor)
        args = self.args | dict(apps=self.apps[:1], count=2)
        result = run_once(**args, fetcher=fetch)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result['apps'][0]['cross_page_duplicates'], 1)
        self.assertEqual(result['apps'][0]['new_records'], 4)
        # New records after a known ID on the boundary page are not discarded.
        self.assertEqual(self.query('SELECT count(*) FROM reviews WHERE app_id=?', (self.apps[0]['app_id'],)), [(5,)])
        run_once(**args, resume=result['run_id'], fetcher=lambda **_: self.fail('Fetched after boundary'))

    def test_resume_keeps_original_boundary_snapshot(self):
        self.seed(1)
        args = self.args | dict(apps=self.apps[:1], pages=1)
        first = run_once(**args, fetcher=lambda **_: dict(records=[record('new')], cursor='next'))
        self.assertEqual(first['apps'][0]['catch_up']['stop_reason'], 'invocation_limit')
        second = run_once(**args, resume=first['run_id'], fetcher=lambda **_: dict(
            records=[record('new'), record('old-0')], cursor='after'))
        self.assertEqual(second['apps'][0]['pages'], 2)
        self.assertEqual(second['apps'][0]['catch_up']['known_ids_observed'], 1)
        self.assertEqual(second['apps'][0]['catch_up']['baseline_ids'], 1)

    def test_total_page_cap_survives_resume_and_blocks_false_quality(self):
        self.seed(1)
        args = self.args | dict(apps=self.apps[:1], pages=1, max_pages=2)
        first = run_once(**args, fetcher=lambda **_: dict(records=[record('one')], cursor='one'))
        last = run_once(**args, resume=first['run_id'], fetcher=lambda **_: dict(records=[record('two')], cursor='two'))
        app = last['apps'][0]
        self.assertEqual(app['catch_up']['stop_reason'], 'page_limit')
        self.assertTrue(app['catch_up']['gap_risk'])
        self.assertFalse(app['can_resume'])
        self.assertEqual(assessment_status(dict(verification_status='passed'), app, dict(warnings=[])), 'needs_attention')
        run_once(**args, resume=first['run_id'], fetcher=lambda **_: self.fail('Exceeded total cap'))
        with self.assertRaisesRegex(ValueError, 'configuration differs'):
            run_once(**(args | dict(max_pages=3)), resume=first['run_id'])

    def test_empty_database_reaches_source_end_or_marks_cap(self):
        result = run_once(**self.args, fetcher=lambda **_: dict(records=[record('first')], cursor=None))
        for app in result['apps']:
            self.assertEqual(app['catch_up']['baseline_ids'], 0)
            self.assertEqual(app['catch_up']['stop_reason'], 'source_end')
            self.assertTrue(app['catch_up']['boundary_resolved'])
        self.assertEqual(result['unique_reviews_in_database'], 3)

    def test_explicit_extension_keeps_cursor_boundary_and_audit_history(self):
        self.seed(1)
        args = self.args | dict(apps=self.apps[:1], max_pages=1)
        first = run_once(**args, fetcher=lambda **_: dict(records=[record('new')], cursor='saved-cursor'))
        first.update(verification_status='passed', evaluation=dict(apps=[dict(
            app_id=self.apps[0]['app_id'], warnings=[])]))
        persist_assessments(self.db, first)
        self.assertEqual(self.query('SELECT count(*) FROM play_source_assessments'), [(1,)])
        seen = []
        def fetch(**request):
            seen.append(request['cursor'])
            self.assertEqual(self.query('SELECT count(*) FROM play_source_assessments'), [(0,)])
            return dict(records=[record('old-0')], cursor='after-boundary')
        result = run_once(**(args | dict(max_pages=3)), resume=first['run_id'],
                          extend_max_pages=True, fetcher=fetch)
        self.assertEqual(seen, ['saved-cursor'])
        app = result['apps'][0]
        self.assertEqual(app['pages'], 2)
        self.assertEqual(app['catch_up']['baseline_ids'], 1)
        self.assertTrue(app['catch_up']['boundary_resolved'])
        history = result['limit_extensions']
        self.assertEqual((history[0]['previous_max_pages'], history[0]['new_max_pages']), (1, 3))
        again = run_once(**(args | dict(max_pages=3)), resume=first['run_id'],
                         fetcher=lambda **_: self.fail('Boundary already reached'))
        self.assertEqual(again['limit_extensions'], history)

    def test_explicit_extension_cannot_change_other_configuration_or_shrink(self):
        self.seed(1)
        args = self.args | dict(apps=self.apps[:1], max_pages=1)
        first = run_once(**args, fetcher=lambda **_: dict(records=[record('new')], cursor='next'))
        for changes in (dict(max_pages=1), dict(max_pages=3, country='gb'), dict(max_pages=3, count=50)):
            with self.assertRaises(ValueError):
                run_once(**(args | changes), resume=first['run_id'], extend_max_pages=True,
                         fetcher=lambda **_: self.fail('Invalid extension fetched data'))
        with self.assertRaisesRegex(ValueError, 'requires a catch-up resume'):
            run_once(**args, extend_max_pages=True)
        with self.assertRaisesRegex(ValueError, 'requires a catch-up resume'):
            run_once(**(args | dict(catch_up=False)), resume=first['run_id'], extend_max_pages=True)
        self.assertEqual(self.query('SELECT pages FROM play_jobs WHERE run_id=?', (first['run_id'],)), [(1,)])

    def test_redated_known_review_does_not_stop_before_stable_boundary(self):
        self.seed(2)
        calls = []
        def fetch(**r):
            calls.append(r['cursor'])
            if len(calls) == 1:
                return dict(records=[record('new'), record('old-0', at=utc_now())], cursor='after-edit')
            return dict(records=[record('more-new'), record('old-1')], cursor='after-boundary')
        result = run_once(**(self.args | dict(apps=self.apps[:1])), fetcher=fetch)
        app = result['apps'][0]
        self.assertEqual(len(calls), 2)
        self.assertEqual(app['new_records'], 2)
        self.assertEqual(app['catch_up']['known_ids_observed'], 2)
        self.assertEqual(app['catch_up']['qualified_boundary_ids'], 1)
        self.assertEqual(app['catch_up']['nonqualifying_known_ids'], 1)
        self.assertTrue(app['catch_up']['boundary_resolved'])

    def test_redated_boundary_resume_uses_original_snapshot_not_updated_table(self):
        self.seed(1)
        args = self.args | dict(apps=self.apps[:1], pages=1)
        first = run_once(**args, fetcher=lambda **_: dict(records=[record('old-0', at=utc_now())], cursor='after-edit'))
        self.assertTrue(first['apps'][0]['catch_up']['gap_risk'])
        self.assertTrue(first['apps'][0]['can_resume'])
        result = run_once(**args, resume=first['run_id'],
                          fetcher=lambda **_: dict(records=[record('new'), record('old-0')], cursor='after-stable'))
        self.assertEqual(result['apps'][0]['pages'], 2)
        self.assertEqual(result['apps'][0]['catch_up']['qualified_boundary_ids'], 1)

    def test_duplicate_raw_entry_cannot_fabricate_stable_boundary(self):
        self.seed(1)
        result = run_once(**(self.args | dict(apps=self.apps[:1], max_pages=1)),
                          fetcher=lambda **_: dict(records=[record('old-0', at=utc_now()), record('old-0')], cursor='next'))
        self.assertEqual(result['apps'][0]['duplicates'], 1)
        self.assertEqual(result['apps'][0]['catch_up']['qualified_boundary_ids'], 0)
        self.assertTrue(result['apps'][0]['catch_up']['gap_risk'])

    def test_inherited_redated_id_keeps_original_frozen_date(self):
        self.seed(1)
        edited = utc_now()
        args = self.args | dict(apps=self.apps[:1], max_pages=1)
        fetch = lambda **_: dict(records=[record('old-0', at=edited)], cursor='next')
        first = run_once(**args, fetcher=fetch)
        again = run_once(**args, fetcher=fetch)
        app = again['apps'][0]
        self.assertEqual(app['catch_up']['inherited_from_run'], first['run_id'])
        self.assertEqual(app['catch_up']['qualified_boundary_ids'], 0)
        self.assertTrue(app['catch_up']['gap_risk'])

    def test_fresh_run_cannot_hide_prior_cap_behind_partial_new_head(self):
        self.seed(1)
        args = self.args | dict(apps=self.apps[:1], max_pages=1)
        capped = run_once(**args, fetcher=lambda **_: dict(records=[record('partial-head')], cursor='next'))
        again = run_once(**args, fetcher=lambda **_: dict(records=[record('partial-head')], cursor='next'))
        app = again['apps'][0]
        self.assertEqual(app['catch_up']['inherited_from_run'], capped['run_id'])
        self.assertEqual(app['catch_up']['known_ids_observed'], 0)
        self.assertTrue(app['catch_up']['gap_risk'])
        calls = []
        def fetch(**r):
            calls.append(r['cursor'])
            return dict(records=[record('partial-head' if r['cursor'] is None else 'old-0')],
                        cursor='second' if r['cursor'] is None else 'third')
        done = run_once(**(args | dict(max_pages=2)), fetcher=fetch)
        self.assertEqual(len(calls), 2)
        self.assertTrue(done['apps'][0]['catch_up']['boundary_resolved'])

    def test_existing_ids_are_app_scoped_and_replay_updates_without_duplicates(self):
        self.seed(1)
        result = run_once(**self.args, fetcher=lambda **_: dict(records=[record('old-0', thumbsUpCount=7)], cursor='unused'))
        self.assertEqual(result['unique_reviews_in_database'], 3)
        self.assertTrue(all(a['pages'] == 1 and a['changed_records'] == 1 for a in result['apps']))
        other = dict(app_id='com.example.fresh', label='Fresh')
        fresh = run_once(**(self.args | dict(apps=[other], max_pages=1)),
                         fetcher=lambda **_: dict(records=[record('old-0')], cursor='next'))
        self.assertEqual(fresh['apps'][0]['catch_up']['baseline_ids'], 0)
        self.assertEqual(fresh['apps'][0]['catch_up']['stop_reason'], 'page_limit')

    def test_network_failure_keeps_other_apps_and_can_resume(self):
        self.seed(1)
        def fetch(**r):
            if r['app_id'] == self.apps[0]['app_id']:
                raise SourceError('Temporary failure', True)
            return dict(records=[record('old-0')], cursor='next')
        result = run_once(**self.args, fetcher=fetch)
        self.assertEqual(result['failed_attempts'], 1)
        self.assertTrue(result['apps'][0]['can_resume'])
        self.assertTrue(all(a['catch_up']['boundary_resolved'] for a in result['apps'][1:]))
        done = run_once(**self.args, resume=result['run_id'],
                        fetcher=lambda **_: dict(records=[record('old-0')], cursor='next'))
        self.assertTrue(all(a['catch_up']['boundary_resolved'] for a in done['apps']))

    def test_rejected_page_never_resolves_boundary(self):
        self.seed(1)
        result = run_once(**self.args, fetcher=lambda **_: dict(
            records=[record('old-0'), record('bad', score=9)], cursor='next'))
        self.assertTrue(all(a['catch_up']['gap_risk'] and not a['can_resume'] for a in result['apps']))

    def test_oversized_response_is_rejected_before_storage(self):
        result = run_once(**(self.args | dict(count=1)), fetcher=lambda **_: dict(
            records=[record('one'), record('two')], cursor='next'))
        self.assertEqual(result['unique_reviews_in_database'], 0)
        self.assertEqual(result['failed_attempts'], 3)

    def test_database_failure_does_not_commit_false_boundary(self):
        self.seed(1)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER fail_page BEFORE INSERT ON play_pages BEGIN SELECT RAISE(ABORT,'test disk error'); END")
            c.commit()
        failed = run_once(**self.args, fetcher=lambda **_: dict(records=[record('old-0'), record('new')], cursor='next'))
        self.assertTrue(all(a['catch_up']['known_ids_observed'] == 0 and a['catch_up']['gap_risk'] for a in failed['apps']))
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('DROP TRIGGER fail_page')
            c.commit()
        done = run_once(**self.args, resume=failed['run_id'],
                        fetcher=lambda **_: dict(records=[record('old-0'), record('new')], cursor='next'))
        self.assertTrue(all(a['catch_up']['boundary_resolved'] for a in done['apps']))
        self.assertEqual(done['unique_reviews_in_database'], 6)

    def test_invalid_caps_and_mutually_exclusive_modes(self):
        for limit in (0, 101, True, 1.5):
            with self.assertRaises(ValueError):
                run_once(**(self.args | dict(max_pages=limit)))
        with self.assertRaisesRegex(ValueError, 'not both'):
            run_once(**self.args, overlap_run='anything')

    def test_cli_uses_catchup_budget_and_persists_assessment(self):
        self.seed(1)
        root = Path(self.folder.name)
        config = root / 'apps.json'
        config.write_text(json.dumps(self.apps))
        destination = root / 'report.json'
        calls = []
        def collect(**kwargs):
            calls.append(kwargs)
            return run_once(**kwargs, fetcher=lambda **_: dict(records=[record('old-0')], cursor='next'))
        argv = ['collect', '--input', str(config), '--db', str(self.db), '--report', str(destination),
                '--catch-up', '--max-pages', '7', '--delay', '0', '--retries', '0']
        with patch('sys.argv', argv), patch('review_ingestion.google_play_cli.run_once', side_effect=collect), redirect_stdout(StringIO()):
            self.assertEqual(main(), 0)
        self.assertEqual(calls[0]['pages'], 7)
        self.assertTrue(calls[0]['catch_up'])
        stored = self.query('SELECT report_json FROM play_source_assessments')
        self.assertTrue(all(json.loads(row[0])['catch_up']['boundary_resolved'] for row in stored))

    def test_cli_explicit_extension_preserves_cap_history(self):
        self.seed(1)
        review_time = REVIEW_TIME
        first = run_once(**(self.args | dict(max_pages=1)),
                         fetcher=lambda **_: dict(records=[record('new', at=review_time)], cursor='saved'))
        root = Path(self.folder.name)
        config = root / 'apps.json'
        config.write_text(json.dumps(self.apps))
        destination = root / 'extended.json'
        seen = []
        def collect(**kwargs):
            def fetch(**r):
                seen.append(r['cursor'])
                return dict(records=[record('old-0', at=review_time)], cursor='after')
            return run_once(**kwargs, fetcher=fetch)
        argv = ['collect', '--input', str(config), '--db', str(self.db), '--report', str(destination),
                '--resume', first['run_id'], '--catch-up', '--extend-max-pages', '--max-pages', '3',
                '--count', '100', '--pages', '2', '--delay', '0', '--retries', '0']
        with patch('sys.argv', argv), patch('review_ingestion.google_play_cli.run_once', side_effect=collect), redirect_stdout(StringIO()):
            code = main()
        self.assertEqual(code, 0, json.loads(destination.read_text())['runs'][0].get('evaluation'))
        result = json.loads(destination.read_text())['runs'][0]
        self.assertEqual(seen, ['saved'] * 3)
        self.assertEqual(result['limit_extensions'][0]['new_max_pages'], 3)
        self.assertTrue(result['storage_audit']['storage_checks_passed'])
