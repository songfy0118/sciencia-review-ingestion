import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from review_ingestion.import_web import import_reviews, validate


def record(**changes):
    row = dict(review_id="RTEST", product_asin="B09XS7JWHH", title="Good", body="First paragraph.\nSecond paragraph.", rating=None, review_date=None, review_date_raw="Unrecognized date", variation="", verified_purchase=None, source_url="https://www.amazon.com/dp/B09XS7JWHH", collected_at="2026-09-21T00:00:00.000Z")
    return dict(row, **changes)


class WebImportTests(unittest.TestCase):
    def test_repeated_import_and_foreign_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path, db = Path(folder) / "rows.json", Path(folder) / "reviews.sqlite3"
            path.write_text(json.dumps([record(), record(product_asin="B09XS7JWHX")]), encoding="utf-8")
            import_reviews(path, db)
            result = import_reviews(path, db)
            self.assertEqual(result["stored_reviews"], 2)
            self.assertEqual(result["integrity_check"], "ok")
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM ingestion_runs").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT body, rating, verified_purchase FROM reviews LIMIT 1").fetchone(), (record()["body"], None, None))
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_invalid_values_rejected_before_database_write(self):
        for changes in [dict(rating=0), dict(rating=True), dict(rating=6), dict(review_date="2026-02-30"), dict(verified_purchase="yes"), dict(body=""), dict(collected_at="2026-09-21"), dict(source_url="https://evil.example")]:
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                validate([record(**changes)])

    def test_older_export_does_not_overwrite_newer_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path, db = Path(folder) / "rows.json", Path(folder) / "reviews.sqlite3"
            path.write_text(json.dumps([record(body="Newer.")]), encoding="utf-8")
            import_reviews(path, db)
            path.write_text(json.dumps([record(body="Older.", collected_at="2026-09-20T00:00:00.000Z")]), encoding="utf-8")
            import_reviews(path, db)
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT body FROM reviews").fetchone()[0], "Newer.")


if __name__ == "__main__":
    unittest.main()
