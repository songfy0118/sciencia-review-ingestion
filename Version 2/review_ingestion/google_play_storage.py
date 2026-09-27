from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .google_play import GooglePlayApp, GooglePlayReview


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    sequence_number INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source = 'google_play'),
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    lang TEXT NOT NULL,
    country TEXT NOT NULL,
    requested_per_app INTEGER NOT NULL,
    report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS apps (
    app_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    title TEXT NOT NULL,
    developer TEXT NOT NULL,
    genre TEXT NOT NULL,
    source_url TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    app_id TEXT NOT NULL REFERENCES apps(app_id),
    review_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    thumbs_up_count INTEGER NOT NULL CHECK (thumbs_up_count >= 0),
    review_created_version TEXT,
    review_at TEXT NOT NULL,
    reply_content TEXT,
    replied_at TEXT,
    source_url TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_collected_at TEXT NOT NULL,
    PRIMARY KEY (app_id, review_id)
);

CREATE TABLE IF NOT EXISTS collection_run_apps (
    run_id TEXT NOT NULL REFERENCES collection_runs(run_id),
    app_id TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_count INTEGER NOT NULL,
    received_count INTEGER NOT NULL,
    new_count INTEGER NOT NULL,
    repeated_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    continuation_available INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (run_id, app_id)
);

CREATE TABLE IF NOT EXISTS review_observations (
    run_id TEXT NOT NULL REFERENCES collection_runs(run_id),
    app_id TEXT NOT NULL,
    review_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    collected_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (run_id, app_id, review_id),
    FOREIGN KEY (app_id, review_id) REFERENCES reviews(app_id, review_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_app_date ON reviews(app_id, review_at DESC);
CREATE INDEX IF NOT EXISTS idx_reviews_score ON reviews(score);
CREATE INDEX IF NOT EXISTS idx_observations_app ON review_observations(app_id, run_id);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def upsert_app(connection: sqlite3.Connection, app: GooglePlayApp, collected_at: str) -> None:
    connection.execute(
        """
        INSERT INTO apps (
          app_id, label, title, developer, genre, source_url,
          first_collected_at, last_collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(app_id) DO UPDATE SET
          label=excluded.label,
          title=excluded.title,
          developer=excluded.developer,
          genre=excluded.genre,
          source_url=excluded.source_url,
          last_collected_at=excluded.last_collected_at
        """,
        (
            app.app_id, app.label, app.title, app.developer, app.genre,
            app.source_url, collected_at, collected_at,
        ),
    )


def upsert_reviews(
    connection: sqlite3.Connection,
    reviews: list[GooglePlayReview],
) -> tuple[int, int]:
    if not reviews:
        return 0, 0
    existing = {
        row[0]
        for row in connection.execute(
            "SELECT review_id FROM reviews WHERE app_id = ? AND review_id IN ({})".format(
                ",".join("?" for _ in reviews)
            ),
            (reviews[0].app_id, *(review.review_id for review in reviews)),
        )
    }
    connection.executemany(
        """
        INSERT INTO reviews (
          app_id, review_id, author_name, content, score, thumbs_up_count,
          review_created_version, review_at, reply_content, replied_at,
          source_url, first_collected_at, last_collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(app_id, review_id) DO UPDATE SET
          author_name=excluded.author_name,
          content=excluded.content,
          score=excluded.score,
          thumbs_up_count=excluded.thumbs_up_count,
          review_created_version=excluded.review_created_version,
          review_at=excluded.review_at,
          reply_content=excluded.reply_content,
          replied_at=excluded.replied_at,
          source_url=excluded.source_url,
          last_collected_at=excluded.last_collected_at
        WHERE excluded.last_collected_at >= reviews.last_collected_at
        """,
        [
            (
                review.app_id, review.review_id, review.author_name, review.content,
                review.score, review.thumbs_up_count, review.review_created_version,
                review.review_at, review.reply_content, review.replied_at,
                review.source_url, review.collected_at, review.collected_at,
            )
            for review in reviews
        ],
    )
    repeated = sum(review.review_id in existing for review in reviews)
    return len(reviews) - repeated, repeated


def save_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    sequence_number: int,
    started_at: str,
    completed_at: str,
    status: str,
    lang: str,
    country: str,
    requested_per_app: int,
    report: dict,
) -> None:
    connection.execute(
        """
        INSERT INTO collection_runs (
          run_id, sequence_number, source, started_at, completed_at, status,
          lang, country, requested_per_app, report_json
        ) VALUES (?, ?, 'google_play', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, sequence_number, started_at, completed_at, status,
            lang, country, requested_per_app, json.dumps(report, ensure_ascii=False),
        ),
    )


def save_app_result(connection: sqlite3.Connection, run_id: str, result: dict) -> None:
    connection.execute(
        """
        INSERT INTO collection_run_apps (
          run_id, app_id, status, requested_count, received_count, new_count,
          repeated_count, skipped_count, continuation_available, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, result["app_id"], result["status"], result["requested_count"],
            result["received_count"], result["new_count"], result["repeated_count"],
            result["skipped_count"], int(result["continuation_available"]), result.get("error"),
        ),
    )


def save_observations(
    connection: sqlite3.Connection,
    run_id: str,
    reviews: list[GooglePlayReview],
) -> None:
    connection.executemany(
        """
        INSERT INTO review_observations (
          run_id, app_id, review_id, position, collected_at, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id, review.app_id, review.review_id, position,
                review.collected_at, review.content_hash,
            )
            for position, review in enumerate(reviews, start=1)
        ],
    )
