from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from review_ingestion.google_play import collect_app, normalize_review, validate_app_id
from review_ingestion.google_play_storage import (
    connect,
    save_observations,
    upsert_app,
    upsert_reviews,
)


def raw_review(review_id: str = "review-1", content: str = "Useful app.") -> dict:
    return {
        "reviewId": review_id,
        "userName": "Example User",
        "content": content,
        "score": 4,
        "thumbsUpCount": 3,
        "reviewCreatedVersion": "1.2.3",
        "at": datetime(2026, 9, 24, 12, 0, 0),
        "replyContent": None,
        "repliedAt": None,
    }


class GooglePlayCollectorTests(unittest.TestCase):
    def test_app_id_validation(self) -> None:
        self.assertEqual(validate_app_id("com.example.app"), "com.example.app")
        for value in ["", "spotify", "https://play.google.com/store/apps"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_app_id(value)

    def test_collects_and_normalizes_a_bounded_page(self) -> None:
        def app_fetcher(*args, **kwargs):
            return {"title": "Example App", "developer": "Example Co", "genre": "Tools"}

        def review_fetcher(*args, **kwargs):
            return [raw_review(), raw_review()], SimpleNamespace(token="next")

        app, reviews, has_more, skipped = collect_app(
            "com.example.app",
            count=50,
            app_fetcher=app_fetcher,
            review_fetcher=review_fetcher,
            newest_sort="newest",
        )
        self.assertEqual(app.title, "Example App")
        self.assertEqual(len(reviews), 1)
        self.assertTrue(has_more)
        self.assertEqual(skipped, 1)
        self.assertEqual(reviews[0].score, 4)

    def test_invalid_review_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_review(
                raw_review(content=""),
                app_id="com.example.app",
                source_url="https://play.google.com/store/apps/details?id=com.example.app",
                collected_at="2026-09-24T12:00:00Z",
            )

    def test_terminal_token_object_does_not_mean_more_pages(self) -> None:
        _, _, has_more, _ = collect_app(
            "com.example.app",
            app_fetcher=lambda *a, **k: {"title": "Example"},
            review_fetcher=lambda *a, **k: ([raw_review()], SimpleNamespace(token=None)),
        )
        self.assertFalse(has_more)

    def test_database_upserts_reviews_and_keeps_run_observations(self) -> None:
        def app_fetcher(*args, **kwargs):
            return {"title": "Example App", "developer": "Example Co", "genre": "Tools"}

        def review_fetcher(*args, **kwargs):
            return [raw_review()], None

        app, reviews, _, _ = collect_app(
            "com.example.app",
            app_fetcher=app_fetcher,
            review_fetcher=review_fetcher,
            newest_sort="newest",
        )
        with tempfile.TemporaryDirectory() as folder:
            connection = connect(Path(folder) / "reviews.sqlite3")
            try:
                upsert_app(connection, app, reviews[0].collected_at)
                self.assertEqual(upsert_reviews(connection, reviews), (1, 0))
                self.assertEqual(upsert_reviews(connection, reviews), (0, 1))
                connection.execute(
                    """
                    INSERT INTO collection_runs (
                      run_id, sequence_number, source, started_at, completed_at,
                      status, lang, country, requested_per_app, report_json
                    ) VALUES ('run-1', 1, 'google_play', 'a', 'b', 'completed', 'en', 'us', 1, '{}')
                    """
                )
                save_observations(connection, "run-1", reviews)
                connection.commit()
                self.assertEqual(connection.execute("SELECT count(*) FROM reviews").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT count(*) FROM review_observations").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
