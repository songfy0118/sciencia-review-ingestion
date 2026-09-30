import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from review_ingestion.evaluate_play import evaluate
from review_ingestion.play_pipeline import run_once


def record(key='one', content='Good', at='2020-01-01T00:00:00Z'):
    return dict(reviewId=key, content=content, score=4, at=at)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / 'reviews.sqlite3'

    def collect(self, records, hours_ago=0, count=50):
        report = run_once(db_path=self.db, apps=[dict(app_id='com.example.app', label='Example')],
                         pages=1, count=count, delay=0, retries=0,
                         fetcher=lambda **_: dict(records=records, cursor=None))
        observed = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat().replace('+00:00','Z')
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE collection_runs SET started_at=? WHERE run_id=?', (observed, report['run_id']))
            c.execute('UPDATE play_pages SET collected_at=? WHERE run_id=?', (observed, report['run_id']))
            c.commit()
        return report['run_id']

    def test_current_stale_window_not_masked_by_accumulated_fresh_record(self):
        self.collect([record('old-run', at=datetime.now(timezone.utc).isoformat())], hours_ago=48)
        current = self.collect([record('current-run')])
        item = evaluate(self.db, current)['apps'][0]
        self.assertEqual(item['newest_returned_review'], '2020-01-01T00:00:00Z')
        self.assertTrue(any('seven days' in w for w in item['warnings']))

    def test_unchanged_cross_day_window_is_flagged(self):
        first = self.collect([record()], hours_ago=48)
        second = self.collect([record()])
        item = evaluate(self.db, second)['apps'][0]
        self.assertEqual(item['comparison']['previous_run_id'], first)
        self.assertEqual(item['comparison']['id_jaccard'], 1)
        self.assertTrue(any('24 hours' in w for w in item['warnings']))

    def test_changed_review_and_new_id_are_distinguished(self):
        self.collect([record('one'), record('leaves-window')], hours_ago=48)
        second = self.collect([record('one', content='Edited'), record('two')])
        change = evaluate(self.db, second)['apps'][0]['comparison']
        self.assertEqual(change['new_ids_in_window'], 1)
        self.assertEqual(change['ids_no_longer_in_window'], 1)
        self.assertEqual(change['changed_text_rating_or_reply'], 1)

    def test_different_page_size_is_not_comparable(self):
        self.collect([record()], hours_ago=48, count=100)
        second = self.collect([record()], count=50)
        self.assertIsNone(evaluate(self.db, second)['apps'][0]['comparison'])

    def test_future_timestamp_is_flagged(self):
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        current = self.collect([record(at=future)])
        self.assertTrue(any('future' in w for w in evaluate(self.db, current)['apps'][0]['warnings']))

    def test_conflicting_duplicate_uses_same_record_as_storage(self):
        self.collect([record()], hours_ago=48)
        current = self.collect([record(), record(content='Duplicate differs')])
        item = evaluate(self.db, current)['apps'][0]
        self.assertEqual(item['comparison']['changed_text_rating_or_reply'], 0)

    def test_new_ids_do_not_hide_backwards_newest_timestamp(self):
        self.collect([record('previous', at='2026-09-28T10:00:00Z')], hours_ago=24)
        current = self.collect([record('different', at='2026-09-27T10:00:00Z')])
        item = evaluate(self.db, current)['apps'][0]
        self.assertEqual(item['comparison']['new_ids_in_window'], 1)
        self.assertEqual(item['comparison']['shared_ids_in_window'], 0)
        self.assertEqual(item['comparison']['newest_timestamp_change_seconds'], -86400)
        self.assertTrue(any('backwards' in warning for warning in item['warnings']))

    def test_failed_current_window_is_not_used_for_overlap_comparison(self):
        self.collect([record()], hours_ago=24)
        current = self.collect([record()])
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE play_jobs SET status='failed' WHERE run_id=?", (current,))
            connection.commit()
        item = evaluate(self.db, current)['apps'][0]
        self.assertIsNone(item['comparison'])
        self.assertTrue(any('incomplete or failed' in warning for warning in item['warnings']))


if __name__ == '__main__':
    unittest.main()
