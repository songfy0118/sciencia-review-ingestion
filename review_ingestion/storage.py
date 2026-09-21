from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .amazon import Review


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    asin TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    source_url TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    product_asin TEXT NOT NULL REFERENCES products(asin),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    rating REAL,
    review_date TEXT NOT NULL,
    variation TEXT NOT NULL,
    verified_purchase INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    collected_at TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection


def upsert_product(
    connection: sqlite3.Connection,
    asin: str,
    label: str,
    source_url: str,
    updated_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO products (asin, label, source_url, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(asin) DO UPDATE SET
          label=excluded.label,
          source_url=excluded.source_url,
          updated_at=excluded.updated_at
        """,
        (asin, label, source_url, updated_at),
    )


def upsert_reviews(connection: sqlite3.Connection, reviews: list[Review]) -> int:
    before = connection.total_changes
    connection.executemany(
        """
        INSERT INTO reviews (
          review_id, product_asin, title, body, rating, review_date,
          variation, verified_purchase, source_url, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(review_id) DO UPDATE SET
          title=excluded.title,
          body=excluded.body,
          rating=excluded.rating,
          review_date=excluded.review_date,
          variation=excluded.variation,
          verified_purchase=excluded.verified_purchase,
          source_url=excluded.source_url,
          collected_at=excluded.collected_at
        """,
        [
            (
                review.review_id,
                review.product_asin,
                review.title,
                review.body,
                review.rating,
                review.review_date,
                review.variation,
                int(review.verified_purchase),
                review.source_url,
                review.collected_at,
            )
            for review in reviews
        ],
    )
    return connection.total_changes - before


def save_run(
    connection: sqlite3.Connection,
    run_id: str,
    started_at: str,
    completed_at: str,
    status: str,
    report: dict,
) -> None:
    connection.execute(
        """
        INSERT INTO ingestion_runs (run_id, started_at, completed_at, status, report_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, started_at, completed_at, status, json.dumps(report, ensure_ascii=False)),
    )


def export_csv(path: Path, reviews: list[Review]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(Review.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(review) for review in reviews)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

