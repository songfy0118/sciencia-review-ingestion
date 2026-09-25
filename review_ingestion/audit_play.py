"""Reconcile stored pages with normalized records; publish counts, not review text."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .google_play import app_url, normalize_review, utc_now
from .storage import write_json


def audit(db: Path) -> dict:
    if not db.is_file():
        raise ValueError("Database does not exist")
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as c:
        c.row_factory = sqlite3.Row
        issues, expected = [], {}
        pages = c.execute("""SELECT p.*,r.lang,r.country FROM play_pages p JOIN collection_runs r
                             USING(run_id) ORDER BY p.collected_at,p.rowid""").fetchall()
        for page in pages:
            raw = json.loads(page["records_json"])
            if len(raw) != page["raw_count"] or page["raw_count"] != page["accepted"] + page["duplicates"] + page["rejected"]:
                issues.append({"run_id": page["run_id"], "app_id": page["app_id"], "page": page["page"], "issue": "page_count_mismatch"})
            seen = set()
            for item in raw:
                try:
                    review = normalize_review(item, app_id=page["app_id"],
                        source_url=app_url(page["app_id"], page["lang"], page["country"]), collected_at=page["collected_at"])
                except (TypeError, ValueError):
                    continue
                if review.review_id not in seen:
                    expected[(review.app_id, review.review_id)] = review
                    seen.add(review.review_id)
        mismatches = 0
        for (app_id, review_id), review in expected.items():
            stored = c.execute("SELECT * FROM reviews WHERE app_id=? AND review_id=?", (app_id, review_id)).fetchone()
            if stored is None or any(stored[key] != value for key, value in review.to_dict().items() if key != "collected_at"):
                mismatches += 1
        now = datetime.now(timezone.utc)
        apps = []
        for row in c.execute("SELECT app_id,count(*) unique_reviews,min(review_at) oldest_review,max(review_at) newest_review FROM reviews GROUP BY app_id"):
            item = dict(row)
            newest = datetime.fromisoformat(item["newest_review"].replace("Z", "+00:00"))
            age = round((now - newest).total_seconds() / 86400, 2)
            item["newest_review_age_days"] = age
            item["freshness_warning"] = "Newest returned review is over seven days old; investigate source freshness" if age > 7 else None
            candidates = c.execute("""SELECT j.run_id,j.pages,r.lang,r.country,r.requested_per_app
                FROM play_jobs j JOIN collection_runs r USING(run_id)
                WHERE j.app_id=? AND r.status='bounded_success'
                ORDER BY r.started_at DESC""", (row["app_id"],)).fetchall()
            comparable = []
            if candidates:
                latest = candidates[0]
                comparable = [r for r in candidates if tuple(r)[1:] == tuple(latest)[1:]][:2]
            if len(comparable) == 2:
                sets = [{r[0] for r in c.execute("SELECT review_id FROM review_observations WHERE run_id=? AND app_id=?",
                                               (run[0], row["app_id"]))} for run in comparable]
                item["comparable_run_ids"] = [r[0] for r in comparable]
                item["comparison_parameters"] = dict(pages=latest["pages"], lang=latest["lang"],
                    country=latest["country"], count=latest["requested_per_app"], sort="NEWEST")
                item["review_id_jaccard"] = round(len(sets[0] & sets[1]) / len(sets[0] | sets[1]), 4) if sets[0] | sets[1] else None
            apps.append(item)
        integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(c.execute("PRAGMA foreign_key_check").fetchall())
        unique_count = c.execute("SELECT count(*) FROM reviews").fetchone()[0]
        return {"generated_at": utc_now(), "integrity": integrity, "foreign_key_issues": foreign_keys,
                "committed_pages": len(pages), "source_records_seen": sum(p["raw_count"] for p in pages),
                "unique_reviews": unique_count,
                "snapshot_backed_unique_reviews": len(expected), "snapshot_mismatches": mismatches,
                "count_issues": issues, "apps": apps,
                "storage_checks_passed": integrity == "ok" and not foreign_keys and not mismatches and not issues and len(expected) == unique_count,
                "coverage": "Bounded sample; storage checks cannot establish source completeness or freshness"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.db)
    write_json(args.report, report)
    print(json.dumps(report, indent=2))
    return 0 if report["storage_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
