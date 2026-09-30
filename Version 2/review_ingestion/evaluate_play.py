"""Compare immutable per-run samples, rather than today's accumulated review table."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .google_play import app_url, normalize_review, utc_now


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def sample(connection, run, app_id):
    records = {}
    observed_at = None
    for page in connection.execute(
        "SELECT records_json,collected_at FROM play_pages WHERE run_id=? AND app_id=? ORDER BY page",
        (run["run_id"], app_id),
    ):
        observed_at = page["collected_at"]
        seen = set()
        for raw in json.loads(page["records_json"]):
            try:
                review = normalize_review(raw, app_id=app_id,
                    source_url=app_url(app_id, run["lang"], run["country"]), collected_at=page["collected_at"])
            except (ValueError, TypeError):
                continue
            if review.review_id not in seen:
                records[review.review_id] = review
                seen.add(review.review_id)
    return records, observed_at


def evaluate(db: Path, run_id: str) -> dict:
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as c:
        c.row_factory = sqlite3.Row
        run = c.execute("SELECT * FROM collection_runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise ValueError("Run not found")
        config = json.loads(run["report_json"]).get("config", {})
        results = []
        for job in c.execute("SELECT * FROM play_jobs WHERE run_id=? ORDER BY app_id", (run_id,)):
            records, observed_at = sample(c, run, job["app_id"])
            warnings = []
            if job["status"] not in ("paused", "source_end") or not records:
                warnings.append("Current collection incomplete or failed; inspect the run report")
            dates = [timestamp(r.review_at) for r in records.values()]
            newest = max(dates) if dates else None
            age = (timestamp(observed_at) - newest).total_seconds() / 86400 if newest and observed_at else None
            if age is not None and age > 7:
                warnings.append("Newest returned review was over seven days old at collection")
            if age is not None and age < -1:
                warnings.append("Returned review timestamp is more than one day in the future")
            comparison = None
            # Equal page count and request settings are necessary for useful ID overlap.
            candidates = c.execute("""SELECT r.* FROM collection_runs r JOIN play_jobs j USING(run_id)
                WHERE j.app_id=? AND r.run_id<>? AND r.started_at<?
                AND j.pages=? AND j.status IN ('paused','source_end')
                AND r.lang=? AND r.country=? AND r.requested_per_app=?
                ORDER BY r.started_at DESC""",
                (job["app_id"], run_id, run["started_at"], job["pages"], run["lang"], run["country"], run["requested_per_app"]))
            for earlier in candidates:
                if job["status"] not in ("paused", "source_end"):
                    break
                previous_config = json.loads(earlier["report_json"]).get("config", {})
                if any(previous_config.get(k) != config.get(k) for k in ("sort", "adapter", "package")):
                    continue
                previous, previous_at = sample(c, earlier, job["app_id"])
                if not previous or not records or not previous_at or not observed_at:
                    continue
                elapsed = (timestamp(observed_at) - timestamp(previous_at)).total_seconds() / 3600
                if elapsed <= 0:
                    continue  # A resumed old run may actually have been observed later.
                shared = records.keys() & previous.keys()
                previous_newest = max(timestamp(r.review_at) for r in previous.values())
                newest_change = (newest - previous_newest).total_seconds()
                changed = sum((records[k].content, records[k].score, records[k].reply_content) !=
                              (previous[k].content, previous[k].score, previous[k].reply_content) for k in shared)
                comparison = {"previous_run_id": earlier["run_id"], "hours_between_samples": round(elapsed, 2),
                              "shared_ids_in_window": len(shared),
                              "previous_newest_returned_review": previous_newest.isoformat().replace("+00:00", "Z"),
                              "newest_timestamp_change_seconds": newest_change,
                              "new_ids_in_window": len(records.keys() - previous.keys()),
                              "ids_no_longer_in_window": len(previous.keys() - records.keys()),
                              "changed_text_rating_or_reply": changed,
                              "id_jaccard": round(len(shared) / len(records.keys() | previous.keys()), 4)}
                if newest_change < 0:
                    warnings.append("Newest returned review moved backwards despite matching NEWEST settings; investigate source ordering")
                if elapsed >= 24 and not comparison["new_ids_in_window"] and not changed:
                    warnings.append("Same review window after at least 24 hours; source freshness needs investigation")
                break
            results.append({"app_id": job["app_id"], "label": job["label"], "status": job["status"],
                            "pages": job["pages"], "unique_reviews_in_run": len(records),
                            "sample_collected_at": observed_at,
                            "newest_returned_review": newest.isoformat().replace("+00:00", "Z") if newest else None,
                            "newest_review_age_days_at_collection": round(age, 2) if age is not None else None,
                            "comparison": comparison, "warnings": warnings})
        return {"run_id": run_id, "generated_at": utc_now(), "apps": results,
                "recommendation": "investigate_source_quality" if any(a["warnings"] for a in results) else "continue_bounded_evaluation",
                "limitations": ["A changed or unchanged bounded window does not prove historical completeness.",
                                "IDs leaving a window are not evidence of deleted reviews.",
                                "Seven days is a diagnostic threshold, not a promised freshness requirement."]}
