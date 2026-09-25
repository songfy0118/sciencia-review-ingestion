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
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_page([record("r2")], "cursor-two", resume=first["run_id"])
        self.assertEqual(self.query("select count(*) from reviews"), [(1,)])
        self.assertEqual(self.query("select cursor,pages from play_jobs"), [("cursor-one", 1)])

    def test_empty_page_never_looks_like_success(self):
        report = self.run_page([])
        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(report["apps"][0]["pages"], 0)

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
