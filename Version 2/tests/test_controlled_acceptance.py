"""Offline acceptance fixtures: five Apps, realistic page sizes, bounded retries."""
import contextlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from review_ingestion.audit_play import audit
from review_ingestion.evaluate_play import evaluate
from review_ingestion.google_play_cli import persist_assessments
from review_ingestion.play_pipeline import SourceError, run_once


class ControlledAcceptanceTests(unittest.TestCase):
    def test_five_apps_three_rounds_and_failed_page_recovery(self):
        apps = [dict(app_id=f'com.example.app{i}', label=f'App {i}') for i in range(5)]
        now = datetime.now(timezone.utc)
        def records(page, edited=False):
            return [dict(reviewId=f'r{page * 100 + i}',
                         content='Edited' if edited and page == 0 and i == 0 else 'Original',
                         score=4, at=(now - timedelta(minutes=page * 100 + i)).isoformat())
                    for i in range(100)]

        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'reviews.sqlite3'
            options = dict(db_path=db, apps=apps, count=100, pages=2, delay=0, retries=0)
            reports = []
            for round_number in range(3):
                def fetch(**request):
                    page = 0 if request['cursor'] is None else 1
                    return dict(records=records(page, edited=round_number > 0),
                                cursor='page-two' if page == 0 else None)
                report = run_once(**options, fetcher=fetch)
                report['verification_status'] = 'passed' if audit(db)['storage_checks_passed'] else 'failed'
                report['evaluation'] = evaluate(db, report['run_id'])
                persist_assessments(db, report)
                reports.append(report)
            self.assertEqual([r['observations_in_run'] for r in reports], [1000, 1000, 1000])
            self.assertEqual([sum(a['new_records'] for a in r['apps']) for r in reports], [1000, 0, 0])
            self.assertEqual([sum(a['changed_records'] for a in r['apps']) for r in reports], [0, 5, 0])
            self.assertEqual([sum(a['unchanged_records'] for a in r['apps']) for r in reports], [0, 995, 1000])
            self.assertEqual(reports[-1]['unique_reviews_in_database'], 1000)
            with contextlib.closing(sqlite3.connect(db)) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM latest_play_source_quality WHERE quality_status='bounded_checks_passed'").fetchone()[0], 5)

            fail_once = True
            def flaky_fetch(**request):
                nonlocal fail_once
                if request['app_id'] == apps[0]['app_id'] and request['cursor'] and fail_once:
                    fail_once = False
                    raise SourceError('Fixture: transient source timeout', True)
                page = 0 if request['cursor'] is None else 1
                return dict(records=records(page, edited=True), cursor='page-two' if page == 0 else None)
            failed = run_once(**options, fetcher=flaky_fetch)
            self.assertEqual(failed['status'], 'needs_attention')
            self.assertEqual(failed['apps'][0]['pages'], 1)
            with contextlib.closing(sqlite3.connect(db)) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM latest_play_source_quality WHERE quality_status='unassessed'").fetchone()[0], 5)
            recovered = run_once(**options, resume=failed['run_id'], fetcher=flaky_fetch)
            self.assertEqual(recovered['status'], 'bounded_success')
            self.assertEqual(recovered['failed_attempts'], 1)
            self.assertEqual(recovered['observations_in_run'], 1000)
            self.assertEqual(recovered['unique_reviews_in_database'], 1000)
            self.assertTrue(audit(db)['storage_checks_passed'])


if __name__ == '__main__':
    unittest.main()
