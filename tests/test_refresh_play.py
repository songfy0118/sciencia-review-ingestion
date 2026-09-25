import json
import tempfile
import unittest
from functools import partial
from pathlib import Path

from review_ingestion.play_pipeline import run_once, SourceError
from review_ingestion.refresh_play import refresh


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.options = dict(apps=[{"app_id": "com.example.app", "label": "Example"}],
                            db=root / "live.sqlite3", output=root / "cycles", pages=1,
                            count=1, delay=0, retries=0)

    def collect(self, **request):
        return {"records": [{"reviewId": "one", "content": "Useful", "score": 4,
                             "at": "2000-01-01T00:00:00Z"}], "cursor": None}

    def test_stale_data_is_warning_and_export_is_inspectable(self):
        health = refresh(**self.options, collector=partial(run_once, fetcher=self.collect))
        self.assertEqual(health["status"], "warning")
        folder = Path(health["snapshot"]).parent
        self.assertEqual(json.loads((folder / "reviews.json").read_text())[0]["content"], "Useful")
        self.assertTrue(json.loads((folder / "audit.json").read_text())["storage_checks_passed"])
        self.assertIn("Review freshness", (folder / "index.html").read_text(encoding="utf-8"))

    def test_exception_preserves_previous_snapshot_and_publishes_failure(self):
        first = refresh(**self.options, collector=partial(run_once, fetcher=self.collect))
        old = Path(first["snapshot"]).read_bytes()
        def broken(**kwargs):
            raise RuntimeError("Disk unavailable")
        failed = refresh(**self.options, collector=broken)
        self.assertEqual(failed["status"], "failed")
        self.assertIsNone(failed["snapshot"])
        self.assertEqual(Path(first["snapshot"]).read_bytes(), old)
        latest = json.loads((self.options["output"] / "latest.json").read_text())
        self.assertEqual(latest["status"], "failed")

    def test_failed_collection_is_not_success_because_old_data_exists(self):
        refresh(**self.options, collector=partial(run_once, fetcher=self.collect))
        def broken(**kwargs):
            raise SourceError("Source unavailable")
        health = refresh(**self.options, collector=partial(run_once, fetcher=broken))
        self.assertEqual(health["status"], "needs_attention")
        self.assertEqual(health["unique_reviews"], 1)


if __name__ == "__main__":
    unittest.main()
