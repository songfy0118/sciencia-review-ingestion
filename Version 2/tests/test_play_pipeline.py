from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from review_ingestion.google_play import datetime_text
from review_ingestion.play_pipeline import SourceError, fetch_page, run_once
from review_ingestion.inspect_play import export_database


def record(key="r1", **changes):
    return {"reviewId": key, "content": "Helpful app", "score": 4,
            "at": "2026-09-25T10:00:00Z", **changes}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / "reviews.sqlite3"
        self.args = dict(apps=[{"app_id": "com.example.app", "label": "Example"}],
                         db_path=self.db, pages=1, count=2, delay=0, retries=0)

    def query(self, sql):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute(sql).fetchall()

    def run_page(self, records, cursor=None, **kwargs):
        return run_once(**(self.args | kwargs), fetcher=lambda **_: {"records": records, "cursor": cursor})

    def test_resume_deduplicates_and_preserves_observations(self):
        first = self.run_page([record()], "cursor-one")
        seen = []
        def next_page(**request):
            seen.append(request["cursor"])
            return {"records": [record(), record("r2")], "cursor": None}
        second = run_once(**self.args, resume=first["run_id"], fetcher=next_page)
        self.assertEqual(seen, ["cursor-one"])
        self.assertEqual(second["unique_reviews_in_database"], 2)
        self.assertEqual(second["observations_in_run"], 2)
        self.assertEqual(second["apps"][0]["pages"], 2)
        self.assertEqual(second["apps"][0]["status"], "source_end")
        self.assertEqual(self.query("pragma foreign_key_check"), [])

    def test_failure_retains_cursor_and_resume_retries_that_page(self):
        first = self.run_page([record()], "cursor-one")
        def fail(**_):
            raise SourceError("HTTP 429", True)
        failed = run_once(**self.args, resume=first["run_id"], fetcher=fail)
        self.assertEqual(failed["status"], "needs_attention")
        self.assertEqual(self.query("select cursor,pages from play_jobs"), [("cursor-one", 1)])
        done = self.run_page([record("r2")], resume=first["run_id"])
        self.assertEqual(done["unique_reviews_in_database"], 2)
        self.assertEqual(done["failed_attempts"], 1)

    def test_database_failure_rolls_back_records_and_checkpoint(self):
        first = self.run_page([record()], "cursor-one")
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER fail_page BEFORE INSERT ON play_pages BEGIN SELECT RAISE(ABORT,'disk failure simulation'); END")
            c.commit()
        failed = self.run_page([record("r2")], "cursor-two", resume=first["run_id"])
        self.assertEqual(failed["status"], "needs_attention")
        self.assertIn("Database page commit failed", failed["apps"][0]["error"])
        self.assertEqual(self.query("select count(*) from reviews"), [(1,)])
        self.assertEqual(self.query("select cursor,pages from play_jobs"), [("cursor-one", 1)])
        self.assertEqual(self.query("select count(*) from play_page_changes"), [(1,)])

    def test_repeated_collection_distinguishes_updates_and_duplicates(self):
        self.run_page([record("one"), record("two")])
        second = self.run_page([record("one", thumbsUpCount=7), record("two"), record("three"), record("three")], "next")
        app = second["apps"][0]
        self.assertEqual((app["new_records"], app["changed_records"], app["unchanged_records"], app["duplicates"]), (1, 1, 1, 1))
        resumed = self.run_page([record("three"), record("four")], resume=second["run_id"])
        self.assertEqual(resumed["apps"][0]["cross_page_duplicates"], 1)
        self.assertEqual(resumed["unique_reviews_in_database"], 4)

    def test_database_failure_allows_other_apps_and_resume(self):
        first = self.run_page([record()], "next")
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER fail_page BEFORE INSERT ON play_pages WHEN NEW.app_id='com.example.app' BEGIN SELECT RAISE(ABORT,'test'); END")
            c.commit()
        apps = self.args["apps"] + [{"app_id": "com.example.other", "label": "Other"}]
        failed = self.run_page([record("new")], apps=apps)
        self.assertEqual(failed["status"], "needs_attention")
        self.assertEqual(failed["unique_reviews_in_database"], 2)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("DROP TRIGGER fail_page")
            c.commit()
        recovered = self.run_page([record("new")], resume=first["run_id"])
        self.assertEqual(recovered["status"], "bounded_success")

    def test_storage_failure_history_survives_successful_resume(self):
        first = self.run_page([record()], "next")
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER fail_page BEFORE INSERT ON play_pages BEGIN SELECT RAISE(ABORT,'disk error'); END")
            c.commit()
        failed = self.run_page([record("two")], resume=first["run_id"])
        self.assertEqual(len(failed["apps"][0]["storage_failures"]), 1)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("DROP TRIGGER fail_page")
            c.commit()
        recovered = self.run_page([record("two")], resume=first["run_id"])
        self.assertEqual(recovered["status"], "bounded_success")
        self.assertIsNone(recovered["apps"][0]["error"])
        self.assertEqual(recovered["apps"][0]["storage_failures"], failed["apps"][0]["storage_failures"])
        self.assertEqual(recovered["failed_attempts"], 0)

    def test_failure_logging_error_propagates_with_checkpoint_intact(self):
        first = self.run_page([record()], "next")
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER fail_page BEFORE INSERT ON play_pages BEGIN SELECT RAISE(ABORT,'page error'); END")
            c.execute("CREATE TRIGGER fail_log BEFORE INSERT ON play_storage_failures BEGIN SELECT RAISE(ABORT,'log error'); END")
            c.commit()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "log error"):
            self.run_page([record("two")], resume=first["run_id"])
        self.assertEqual(self.query("SELECT count(*) FROM reviews"), [(1,)])
        self.assertEqual(self.query("SELECT cursor,pages FROM play_jobs"), [("next", 1)])

    def test_empty_page_never_looks_like_success(self):
        report = self.run_page([])
        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(report["apps"][0]["pages"], 0)

    def test_catchup_stops_when_previous_window_is_observed(self):
        baseline = self.run_page([record('old')])
        calls = []
        def fetch(**request):
            calls.append(request['cursor'])
            return {'records': [record('new' if len(calls) == 1 else 'old')], 'cursor': 'next'}
        result = run_once(**(self.args | {'pages': 5}), overlap_run=baseline['run_id'], fetcher=fetch)
        self.assertEqual(calls, [None, 'next'])
        self.assertEqual(result['apps'][0]['overlap']['status'], 'boundary_observed')
        self.assertFalse(result['apps'][0]['overlap']['complete_coverage'])
        self.assertEqual(result['unique_reviews_in_database'], 2)
        self.run_page([record('unused')], resume=result['run_id'], overlap_run=baseline['run_id'])
        self.assertEqual(self.query('SELECT count(*) FROM reviews'), [(2,)])

    def test_catchup_budget_exhaustion_flags_gap_risk(self):
        baseline = self.run_page([record('old')])
        result = self.run_page([record('different')], 'cursor', overlap_run=baseline['run_id'])
        self.assertTrue(result['apps'][0]['overlap']['gap_risk'])
        self.assertEqual(result['apps'][0]['overlap']['shared_ids'], 0)

    def test_catchup_baseline_locale_mismatch_is_rejected(self):
        baseline = self.run_page([record('old')])
        with self.assertRaisesRegex(ValueError, 'settings differ'):
            self.run_page([record()], overlap_run=baseline['run_id'], country='gb')

    def test_failed_run_cannot_be_a_catchup_baseline(self):
        baseline = self.run_page([record('old')])
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE collection_runs SET status='needs_attention'")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'completed successful'):
            self.run_page([record()], overlap_run=baseline['run_id'])

    def test_resume_invalidates_prior_quality_before_fetch(self):
        from review_ingestion.google_play_cli import persist_assessments
        from review_ingestion.evaluate_play import evaluate
        first = self.run_page([record()], 'next')
        first['verification_status'] = 'passed'
        first['evaluation'] = evaluate(self.db, first['run_id'])
        persist_assessments(self.db, first)
        def fetch(**_):
            self.assertEqual(self.query('SELECT count(*) FROM play_source_assessments'), [(0,)])
            self.assertEqual(self.query('SELECT quality_status FROM latest_play_source_quality'), [('unassessed',)])
            return {'records': [record('next')], 'cursor': None}
        run_once(**self.args, resume=first['run_id'], fetcher=fetch)
        with self.assertRaisesRegex(ValueError, 'changed during verification'):
            persist_assessments(self.db, first)

    def test_resuming_old_run_becomes_latest_quality_activity(self):
        old = self.run_page([record()], 'next')
        new = self.run_page([record('two')])
        self.assertEqual(self.query('SELECT run_id FROM latest_play_source_quality'), [(new['run_id'],)])
        def fetch(**_):
            self.assertEqual(self.query('SELECT run_id,quality_status FROM latest_play_source_quality'),
                             [(old['run_id'], 'unassessed')])
            return {'records': [record('three')], 'cursor': None}
        resumed = run_once(**self.args, resume=old['run_id'], fetcher=fetch)
        self.assertEqual(self.query('SELECT run_id FROM latest_play_source_quality'), [(resumed['run_id'],)])

    def test_audit_comparison_rejects_different_adapter_settings(self):
        from review_ingestion.audit_play import audit
        prior = self.run_page([record()])
        self.run_page([record()])
        with closing(sqlite3.connect(self.db)) as c:
            report = json.loads(c.execute('SELECT report_json FROM collection_runs WHERE run_id=?',
                                         (prior['run_id'],)).fetchone()[0])
            report['config']['sort'] = 'MOST_RELEVANT'
            c.execute('UPDATE collection_runs SET report_json=? WHERE run_id=?',
                      (json.dumps(report), prior['run_id']))
            c.commit()
        item = audit(self.db)['apps'][0]
        self.assertNotIn('comparable_run_ids', item)

    def test_transport_is_atomic_with_page(self):
        metadata = {'request_sort': 2, 'http_date': 'Fri, 02 Oct 2026 04:00:00 GMT',
                    'response_at_utc': '2026-10-02T04:00:02Z', 'age_header': None}
        run_once(**self.args, fetcher=lambda **_: {'records': [record()], 'cursor': None, 'transport': metadata})
        self.assertEqual(json.loads(self.query('SELECT transport_json FROM play_page_transport')[0][0]), metadata)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TRIGGER fail_transport BEFORE INSERT ON play_page_transport BEGIN SELECT RAISE(ABORT,'transport write failed'); END")
            c.commit()
        failed = run_once(**self.args, fetcher=lambda **_: {'records': [record('two')], 'cursor': None, 'transport': metadata})
        self.assertEqual(failed['status'], 'needs_attention')
        self.assertEqual(self.query('SELECT count(*) FROM reviews'), [(1,)])
        self.assertEqual(self.query('SELECT count(*) FROM play_pages'), [(1,)])

    def test_audit_recomputes_accounting_and_checkpoints(self):
        from review_ingestion.audit_play import audit
        self.run_page([record('one'), record('two')])
        self.run_page([record('one')])
        self.assertTrue(audit(self.db)['storage_checks_passed'])
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE play_pages SET new_count=0,repeated_count=2 WHERE new_count=2')
            c.execute('UPDATE play_jobs SET pages=3')
            c.commit()
        result = audit(self.db)
        self.assertFalse(result['storage_checks_passed'])
        issues = {item['issue'] for item in result['count_issues']}
        self.assertIn('derived_accounting_mismatch', issues)
        self.assertIn('checkpoint_page_mismatch', issues)

    def test_audit_detects_observation_hash_and_false_change_counts(self):
        from review_ingestion.audit_play import audit
        self.run_page([record()])
        self.run_page([record()])
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE review_observations SET content_hash='wrong'")
            c.execute('UPDATE play_page_changes SET changed=1,unchanged=0 WHERE unchanged=1')
            c.commit()
        issues = {item['issue'] for item in audit(self.db)['count_issues']}
        self.assertIn('observation_snapshot_mismatch', issues)
        self.assertIn('change_accounting_mismatch', issues)

    def test_backwards_date_is_detected_even_with_different_page_counts(self):
        baseline = self.run_page([record('old', at='2026-09-28T10:00:00Z')], 'next')
        self.run_page([record('older', at='2026-09-27T10:00:00Z')], resume=baseline['run_id'])
        current = self.run_page([record('old', at='2026-09-26T10:00:00Z')], overlap_run=baseline['run_id'])
        self.assertEqual(current['apps'][0]['overlap']['newest_timestamp_change_seconds'], -172800)
        self.assertTrue(current['apps'][0]['overlap']['warnings'])

    def test_rejected_record_has_reason_and_blocks_further_pages(self):
        report = self.run_page([record(), record("bad", score=9), record()], "cursor")
        app = report["apps"][0]
        self.assertEqual((app["accepted_records"], app["rejected_records"], app["duplicates"]), (1, 1, 1))
        self.assertEqual(app["status"], "quality_error")
        self.assertIn("invalid score", self.query("select rejects_json from play_pages")[0][0])

    def test_repeated_cursor_stops_loop(self):
        first = self.run_page([record()], "cursor")
        report = self.run_page([record("r2")], "cursor", resume=first["run_id"])
        self.assertEqual(report["apps"][0]["status"], "stalled")

    def test_resume_configuration_mismatch_rejected(self):
        first = self.run_page([record()], "cursor")
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            self.run_page([record()], resume=first["run_id"], country="gb")

    def test_retry_only_transient_errors(self):
        calls = []
        def fetch(**_):
            calls.append(1)
            if len(calls) == 1:
                raise SourceError("temporarily unavailable", True)
            return {"records": [record()], "cursor": None}
        report = run_once(**(self.args | {"retries": 2}), fetcher=fetch)
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["status"], "bounded_success")
        self.assertEqual(report["failed_attempts"], 1)

    def test_local_naive_timestamp_is_converted_not_relabelled(self):
        epoch = 1700000000
        expected = datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")
        self.assertEqual(datetime_text(datetime.fromtimestamp(epoch)), expected)
        with self.assertRaises(ValueError):
            datetime_text("not-a-date")

    def test_worker_failure_is_not_empty_success(self):
        from types import SimpleNamespace
        with patch("review_ingestion.play_pipeline.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout=json.dumps({"ok": False, "error": "HTTP 403", "retryable": False}))):
            with self.assertRaisesRegex(SourceError, "403"):
                fetch_page(timeout=1)

    def test_worker_timeout_is_retryable(self):
        with patch("review_ingestion.play_pipeline.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 1)):
            with self.assertRaises(SourceError) as result:
                fetch_page(timeout=1)
            self.assertTrue(result.exception.retryable)

    def test_one_app_failure_does_not_lose_other_apps(self):
        apps = self.args["apps"] + [{"app_id": "com.example.broken", "label": "Broken"}]
        def fetch(**request):
            if request["app_id"].endswith("broken"):
                raise SourceError("HTTP 404")
            return {"records": [record()], "cursor": None}
        report = run_once(**(self.args | {"apps": apps, "retries": 3}), fetcher=fetch)
        self.assertEqual(report["unique_reviews_in_database"], 1)
        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(report["failed_attempts"], 1)

    def test_malformed_payload_is_recorded_without_aborting_other_apps(self):
        apps = self.args['apps'] + [{'app_id': 'com.example.broken', 'label': 'Broken'}]
        report = run_once(**(self.args | {'apps': apps}), fetcher=lambda **r:
                          None if r['app_id'].endswith('broken') else {'records': [record()], 'cursor': None})
        self.assertEqual(report['unique_reviews_in_database'], 1)
        self.assertEqual(report['failed_attempts'], 1)
        self.assertEqual(report['status'], 'needs_attention')

    def test_malformed_worker_error_is_diagnostic(self):
        from types import SimpleNamespace
        with patch('review_ingestion.play_pipeline.subprocess.run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps({'ok': False}))):
            with self.assertRaisesRegex(SourceError, 'invalid response'):
                fetch_page(timeout=1)

    def test_second_collector_cannot_take_same_database(self):
        def fetch(**_):
            with self.assertRaisesRegex(RuntimeError, "Another collector"):
                self.run_page([record()])
            return {"records": [record()], "cursor": None}
        run_once(**self.args, fetcher=fetch)

    def test_offline_exports_contain_real_reviews_and_escape_html(self):
        self.run_page([record(content="<script>alert(1)</script>")])
        output = Path(self.folder.name) / "inspection"
        result = export_database(self.db, output)
        self.assertEqual(result["unique_reviews"], 1)
        document = (output / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", document)
        self.assertIn("&lt;script&gt;", document)
        self.assertEqual(json.loads((output / "reviews.json").read_text())[0]["content"], "<script>alert(1)</script>")
        with closing(sqlite3.connect(output / "reviews.sqlite3")) as c:
            self.assertEqual(c.execute("pragma integrity_check").fetchone()[0], "ok")

    def test_old_collection_cannot_overwrite_new_review(self):
        from review_ingestion.google_play import normalize_review
        from review_ingestion.google_play_storage import upsert_reviews
        self.run_page([record()])
        old = normalize_review(record(content="Stale text"), app_id="com.example.app",
                               source_url="https://play.google.com", collected_at="2000-01-01T00:00:00Z")
        with closing(sqlite3.connect(self.db)) as c:
            upsert_reviews(c, [old])
            c.commit()
        self.assertEqual(self.query("select content from reviews"), [("Helpful app",)])

    def test_audit_detects_changed_stored_content(self):
        from review_ingestion.audit_play import audit
        self.run_page([record()])
        self.assertTrue(audit(self.db)["storage_checks_passed"])
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE reviews SET content='unexpected change'")
            c.commit()
        report = audit(self.db)
        self.assertFalse(report["storage_checks_passed"])
        self.assertEqual(report["snapshot_mismatches"], 1)


if __name__ == "__main__":
    unittest.main()
