"""Validate a web JSON export and load it into a persistent SQLite database.

This schema is versioned separately from the original feasibility CLI database.
Use a new database path for web exports; incompatible existing schemas are rejected.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


FIELDS = (
    "review_id", "product_asin", "title", "body", "rating", "review_date",
    "review_date_raw", "variation", "verified_purchase", "source_url", "collected_at",
)
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS products (
    asin TEXT PRIMARY KEY,
    source_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT NOT NULL,
    product_asin TEXT NOT NULL REFERENCES products(asin),
    title TEXT NOT NULL,
    body TEXT NOT NULL CHECK(length(trim(body)) > 0),
    rating REAL CHECK(rating IS NULL OR rating BETWEEN 1 AND 5),
    review_date TEXT,
    review_date_raw TEXT NOT NULL,
    variation TEXT NOT NULL,
    verified_purchase INTEGER CHECK(verified_purchase IS NULL OR verified_purchase IN (0, 1)),
    source_url TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (product_asin, review_id)
);
CREATE INDEX IF NOT EXISTS reviews_product_date ON reviews(product_asin, review_date);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    source_file TEXT NOT NULL
);
"""


def validate(rows: object) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError("Expected a JSON array from the review export, not a run report.")
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise ValueError(f"Record {index + 1}: fields do not match schema version 1.0.")
        for key in ("review_id", "product_asin", "title", "body", "review_date_raw", "variation", "source_url", "collected_at"):
            if not isinstance(row[key], str):
                raise ValueError(f"Record {index + 1}: {key} must be a string.")
        if not re.fullmatch(r"R[A-Z0-9]+", row["review_id"]) or not re.fullmatch(r"[A-Z0-9]{10}", row["product_asin"]):
            raise ValueError(f"Record {index + 1}: invalid review or product ID.")
        if not row["body"].strip():
            raise ValueError(f"Record {index + 1}: review text is empty.")
        rating = row["rating"]
        if rating is not None and (type(rating) not in (int, float) or not math.isfinite(rating) or not 1 <= rating <= 5):
            raise ValueError(f"Record {index + 1}: rating must be null or a number from 1 to 5.")
        if row["verified_purchase"] is not None and type(row["verified_purchase"]) is not bool:
            raise ValueError(f"Record {index + 1}: verified_purchase must be true, false, or null.")
        if row["review_date"] is not None:
            if not isinstance(row["review_date"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["review_date"]):
                raise ValueError(f"Record {index + 1}: use YYYY-MM-DD or null for review_date.")
            date.fromisoformat(row["review_date"])
        stamp = datetime.fromisoformat(row["collected_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError(f"Record {index + 1}: collected_at needs a timezone.")
        source = urlparse(row["source_url"])
        if source.scheme != "https" or source.hostname not in {"amazon.com", "www.amazon.com"} or source.username or source.password:
            raise ValueError(f"Record {index + 1}: unsupported source URL.")
    return rows


def import_reviews(input_path: Path, db_path: Path) -> dict:
    rows = validate(json.loads(input_path.read_text(encoding="utf-8-sig")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        existing = {row[1] for row in connection.execute("PRAGMA table_info(reviews)")}
        if existing and existing != set(FIELDS):
            raise ValueError("This database uses the legacy schema. Choose a new database path for web exports.")
        # Exact column names alone are insufficient: enforce the composite identity too.
        primary = {row[1]: row[5] for row in connection.execute("PRAGMA table_info(reviews)") if row[5]}
        if existing and primary != {"product_asin": 1, "review_id": 2}:
            raise ValueError("This database has an incompatible primary key. Choose a new database path.")
        connection.executescript(SCHEMA)
        for row in rows:
            connection.execute("INSERT INTO products(asin, source_url) VALUES (?, ?) ON CONFLICT(asin) DO NOTHING", (row["product_asin"], f'https://www.amazon.com/dp/{row["product_asin"]}'))
        columns = ", ".join(FIELDS)
        updates = ", ".join(f"{field}=excluded.{field}" for field in FIELDS if field not in ("review_id", "product_asin"))
        connection.executemany(
            f"INSERT INTO reviews ({columns}) VALUES ({', '.join('?' for _ in FIELDS)}) ON CONFLICT(product_asin, review_id) DO UPDATE SET {updates} WHERE julianday(excluded.collected_at) >= julianday(reviews.collected_at)",
            [tuple(row[field] for field in FIELDS) for row in rows],
        )
        connection.execute("INSERT INTO ingestion_runs VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(), len(rows), input_path.name))
        count = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_key_errors:
            raise ValueError("Database integrity validation failed.")
    return {"input_records": len(rows), "stored_reviews": count, "integrity_check": integrity, "foreign_key_errors": len(foreign_key_errors)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a Review Collector JSON export into SQLite.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(import_reviews(args.input, args.db), indent=2))


if __name__ == "__main__":
    main()
