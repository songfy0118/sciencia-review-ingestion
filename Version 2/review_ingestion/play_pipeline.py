"""Page-atomic ingestion with durable checkpoints and auditable source snapshots."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .google_play import GooglePlayApp, app_url, normalize_review, utc_now, validate_app_id
from .google_play_storage import connect, save_run, upsert_app, upsert_reviews
from .evaluate_play import sample, timestamp


SCHEMA = """
CREATE TABLE IF NOT EXISTS play_jobs (
 run_id TEXT NOT NULL REFERENCES collection_runs(run_id), app_id TEXT NOT NULL,
 label TEXT NOT NULL, cursor TEXT, pages INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'pending', error TEXT,
 PRIMARY KEY(run_id, app_id)
);
CREATE TABLE IF NOT EXISTS play_pages (
 run_id TEXT NOT NULL, app_id TEXT NOT NULL, page INTEGER NOT NULL,
 collected_at TEXT NOT NULL, raw_count INTEGER NOT NULL, accepted INTEGER NOT NULL,
 duplicates INTEGER NOT NULL, rejected INTEGER NOT NULL, new_count INTEGER NOT NULL,
 repeated_count INTEGER NOT NULL, records_json TEXT NOT NULL, rejects_json TEXT NOT NULL,
 PRIMARY KEY(run_id, app_id, page),
 FOREIGN KEY(run_id, app_id) REFERENCES play_jobs(run_id, app_id)
);
CREATE TABLE IF NOT EXISTS play_attempts (
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, app_id TEXT NOT NULL,
 page INTEGER NOT NULL, attempted_at TEXT NOT NULL, success INTEGER NOT NULL,
 error TEXT, retryable INTEGER NOT NULL,
 FOREIGN KEY(run_id, app_id) REFERENCES play_jobs(run_id, app_id)
);
CREATE TABLE IF NOT EXISTS play_page_changes (
 run_id TEXT NOT NULL, app_id TEXT NOT NULL, page INTEGER NOT NULL,
 changed INTEGER NOT NULL, unchanged INTEGER NOT NULL, stale INTEGER NOT NULL,
 cross_page_duplicates INTEGER NOT NULL,
 PRIMARY KEY(run_id, app_id, page),
 FOREIGN KEY(run_id, app_id, page) REFERENCES play_pages(run_id, app_id, page)
);
CREATE TABLE IF NOT EXISTS play_storage_failures (
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, app_id TEXT NOT NULL,
 page INTEGER NOT NULL, failed_at TEXT NOT NULL, error TEXT NOT NULL,
 FOREIGN KEY(run_id, app_id) REFERENCES play_jobs(run_id, app_id)
);
CREATE TABLE IF NOT EXISTS play_page_transport (
 run_id TEXT NOT NULL, app_id TEXT NOT NULL, page INTEGER NOT NULL,
 transport_json TEXT NOT NULL,
 PRIMARY KEY(run_id, app_id, page),
 FOREIGN KEY(run_id, app_id, page) REFERENCES play_pages(run_id, app_id, page)
);
BEGIN IMMEDIATE;
DROP VIEW IF EXISTS latest_play_source_quality;
CREATE VIEW latest_play_source_quality AS
 WITH ranked AS (
  SELECT j.run_id,j.app_id,r.status collection_status,j.status job_status,
   ROW_NUMBER() OVER(PARTITION BY j.app_id ORDER BY
    COALESCE(json_extract(r.report_json,'$.generated_at'),r.started_at) DESC,r.rowid DESC) rank
  FROM play_jobs j JOIN collection_runs r USING(run_id)
 )
 SELECT q.run_id,q.app_id,q.collection_status,q.job_status,
  CASE WHEN q.collection_status='running' THEN 'unassessed'
       ELSE COALESCE(a.status,'unassessed') END quality_status,a.report_json
 FROM ranked q LEFT JOIN play_source_assessments a USING(run_id,app_id)
 WHERE q.rank=1;
COMMIT;
"""


class SourceError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def fetch_page(**request) -> dict:
    try:
        process = subprocess.run(
            [sys.executable, "-m", "review_ingestion.play_worker"],
            input=json.dumps(request), capture_output=True, text=True,
            encoding="utf-8", timeout=request["timeout"] + 5,
            cwd=Path(__file__).resolve().parent.parent,
        )
    except subprocess.TimeoutExpired as exc:
        raise SourceError("Page worker exceeded its time limit", True) from exc
    if process.returncode:
        raise SourceError(f"Worker exited {process.returncode}: {process.stderr[-1000:]}")
    try:
        result = json.loads(process.stdout)
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise ValueError("Missing worker status")
        if not result['ok'] and (not isinstance(result.get('error'), str) or type(result.get('retryable')) is not bool):
            raise ValueError('Invalid worker error details')
    except (ValueError, TypeError) as exc:
        raise SourceError("Worker returned an invalid response") from exc
    if not result["ok"]:
        raise SourceError(result["error"], result["retryable"])
    return result


def run_once(*, db_path: Path, **kwargs) -> dict:
    """Hold an OS lock across network and commit; process exit releases it."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with Path(str(db_path.resolve()) + ".lock").open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another collector is using this database") from exc
        try:
            return _run_once(db_path=db_path, **kwargs)
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _run_once(*, apps: list[dict], db_path: Path, count: int = 50,
             pages: int = 2, lang: str = "en", country: str = "us",
             delay: float = 2, timeout: float = 25, retries: int = 2,
             resume: str | None = None, overlap_run: str | None = None, fetcher=fetch_page) -> dict:
    if not apps or len({a["app_id"] for a in apps}) != len(apps):
        raise ValueError("Provide a non-empty list of distinct app IDs")
    for app in apps:
        validate_app_id(app["app_id"])
    if not 1 <= count <= 200 or not 1 <= pages <= 100 or not 0 <= retries <= 3:
        raise ValueError("count: 1..200; pages per invocation: 1..100; retries: 0..3")
    if not math.isfinite(delay) or delay < 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Use finite nonnegative delay and positive timeout")
    if not (len(lang) == 2 and lang.isalpha() and len(country) == 2 and country.isalpha()):
        raise ValueError("Use two-letter language and country codes")
    lang, country = lang.lower(), country.lower()
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    config = {"apps": apps, "lang": lang, "country": country, "count": count,
              "sort": "NEWEST", "adapter": "strict-single-page-v2", "package": "1.2.7"}
    run_id = resume or str(uuid.uuid4())
    try:
        baseline_ids = {}
        if overlap_run:
            baseline = connection.execute("SELECT * FROM collection_runs WHERE run_id=?", (overlap_run,)).fetchone()
            if baseline is None:
                raise ValueError("Overlap baseline run not found")
            if baseline['status'] != 'bounded_success' or overlap_run == run_id:
                raise ValueError("Overlap baseline must be a distinct completed successful run")
            baseline_config = json.loads(baseline["report_json"]).get("config", {})
            if any(baseline_config.get(key) != config[key] for key in ("lang", "country", "count", "sort", "adapter", "package")):
                raise ValueError("Overlap baseline request settings differ")
            for app in apps:
                prior = connection.execute("SELECT status FROM play_jobs WHERE run_id=? AND app_id=?",
                                           (overlap_run, app["app_id"])).fetchone()
                ids = {row[0] for row in connection.execute(
                    "SELECT review_id FROM review_observations WHERE run_id=? AND app_id=?", (overlap_run, app["app_id"]))}
                if prior is None or prior[0] not in ("paused", "source_end") or not ids:
                    raise ValueError("Overlap baseline must contain successful observations for every App")
                baseline_ids[app["app_id"]] = ids
            config["overlap_run"] = overlap_run
        if resume:
            saved = connection.execute("SELECT report_json FROM collection_runs WHERE run_id=?", (run_id,)).fetchone()
            if not saved or json.loads(saved[0]).get("config") != config:
                raise ValueError("Resume ID not found or app/locale/page-size configuration differs")
        else:
            with connection:
                save_run(connection, run_id=run_id, sequence_number=1,
                         started_at=utc_now(), completed_at="", status="running",
                         lang=lang, country=country, requested_per_app=count,
                         report={"config": config})
                connection.executemany("INSERT INTO play_jobs(run_id,app_id,label) VALUES(?,?,?)",
                                       [(run_id, a["app_id"], a["label"]) for a in apps])
        # stdout is reserved for JSON reports; this ID remains available after a crash.
        print(f"Run {run_id}: checkpoint database {db_path}", file=sys.stderr, flush=True)
        with connection:
            connection.execute("""UPDATE collection_runs SET status='running', completed_at='',
                report_json=json_set(report_json,'$.generated_at',?) WHERE run_id=?""", (utc_now(), run_id))
            connection.execute('DELETE FROM play_source_assessments WHERE run_id=?', (run_id,))
        for app in apps:
            app_id = app["app_id"]
            for _ in range(pages):
                job = connection.execute("SELECT * FROM play_jobs WHERE run_id=? AND app_id=?", (run_id, app_id)).fetchone()
                if job["status"] in ("source_end", "stalled", "quality_error"):
                    break
                if overlap_run:
                    observed = {row[0] for row in connection.execute(
                        "SELECT review_id FROM review_observations WHERE run_id=? AND app_id=?", (run_id, app_id))}
                    if observed & baseline_ids[app_id]:
                        break
                page_number = job["pages"] + 1
                payload = None
                for attempt in range(retries + 1):
                    if delay:
                        time.sleep(delay * (2 ** attempt))
                    attempted_at = utc_now()
                    try:
                        payload = fetcher(app_id=app_id, count=count, lang=lang,
                                          country=country, cursor=job["cursor"], timeout=timeout)
                        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                            raise SourceError("Review response is not a list")
                        if 'transport' in payload and not isinstance(payload['transport'], dict):
                            raise SourceError("Invalid transport metadata")
                        cursor = payload.get("cursor")
                        if cursor is not None and (not isinstance(cursor, str) or not cursor):
                            raise SourceError("Invalid continuation token")
                        if not payload["records"]:
                            raise SourceError("Empty page: cannot distinguish source end from response change")
                    except SourceError as exc:
                        with connection:
                            connection.execute("INSERT INTO play_attempts(run_id,app_id,page,attempted_at,success,error,retryable) VALUES(?,?,?,?,0,?,?)",
                                               (run_id, app_id, page_number, attempted_at, str(exc), int(exc.retryable)))
                            connection.execute("UPDATE play_jobs SET status='failed', error=? WHERE run_id=? AND app_id=?",
                                               (str(exc), run_id, app_id))
                        payload = None
                        if not exc.retryable:
                            break
                    else:
                        with connection:
                            connection.execute("INSERT INTO play_attempts(run_id,app_id,page,attempted_at,success,retryable) VALUES(?,?,?,?,1,0)",
                                               (run_id, app_id, page_number, attempted_at))
                        break
                if payload is None:
                    break
                collected_at = utc_now()
                reviews, rejects, seen = [], [], set()
                duplicates = 0
                url = app_url(app_id, lang, country)
                for index, raw in enumerate(payload["records"]):
                    try:
                        review = normalize_review(raw, app_id=app_id, source_url=url, collected_at=collected_at)
                    except (ValueError, TypeError) as exc:
                        rejects.append({"index": index, "reason": str(exc)})
                        continue
                    if review.review_id in seen:
                        duplicates += 1
                        continue
                    seen.add(review.review_id)
                    reviews.append(review)
                cursor = payload.get("cursor")
                prior_ids = {row[0] for row in connection.execute(
                    "SELECT review_id FROM review_observations WHERE run_id=? AND app_id=?", (run_id, app_id))}
                stalled = bool(cursor) and (cursor == job["cursor"] or (seen and seen <= prior_ids))
                status = "stalled" if stalled else "paused" if cursor else "source_end"
                if rejects:
                    status = "quality_error"
                # Records, source snapshot, observations and next cursor commit together.
                # A kill or database failure before commit leaves the old cursor intact.
                with page_transaction(connection, run_id, app_id, page_number):
                    upsert_app(connection, GooglePlayApp(app_id, app["label"], app["label"], "", "", url), collected_at)
                    changes = classify_existing(connection, reviews)
                    new, repeated = upsert_reviews(connection, reviews)
                    connection.execute("INSERT INTO play_pages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (run_id, app_id, page_number, collected_at, len(payload["records"]),
                         len(reviews), duplicates, len(rejects), new, repeated,
                         json.dumps(payload["records"], ensure_ascii=False), json.dumps(rejects)))
                    connection.execute("INSERT INTO play_page_changes VALUES(?,?,?,?,?,?,?)",
                        (run_id, app_id, page_number, *changes, len(seen & prior_ids)))
                    if 'transport' in payload:
                        connection.execute('INSERT INTO play_page_transport VALUES(?,?,?,?)',
                            (run_id, app_id, page_number, json.dumps(payload['transport'])))
                    connection.executemany(
                        "INSERT OR IGNORE INTO review_observations VALUES(?,?,?,?,?,?)",
                        [(run_id, app_id, r.review_id, job["pages"] * count + i,
                          collected_at, r.content_hash) for i, r in enumerate(reviews, 1)])
                    connection.execute("UPDATE play_jobs SET cursor=?, pages=?, status=?, error=? WHERE run_id=? AND app_id=?",
                        (cursor, page_number, status,
                         "Rejected records require inspection" if rejects else "Pagination made no progress" if stalled else None,
                         run_id, app_id))
                committed_status = connection.execute(
                    "SELECT status FROM play_jobs WHERE run_id=? AND app_id=?", (run_id, app_id)).fetchone()[0]
                if committed_status != "paused":
                    break
        report = summarize(connection, run_id, config)
        with connection:
            connection.execute("UPDATE collection_runs SET status=?,completed_at=?,report_json=? WHERE run_id=?",
                (report["status"], utc_now(), json.dumps(report), run_id))
        return report
    finally:
        connection.close()


def classify_existing(connection, reviews):
    changed = unchanged = stale = 0
    for review in reviews:
        stored = connection.execute("SELECT * FROM reviews WHERE app_id=? AND review_id=?",
                                    (review.app_id, review.review_id)).fetchone()
        if stored is None:
            continue
        if review.collected_at < stored["last_collected_at"]:
            stale += 1
        elif any(stored[key] != value for key, value in review.to_dict().items() if key != "collected_at"):
            changed += 1
        else:
            unchanged += 1
    return changed, unchanged, stale


@contextmanager
def page_transaction(connection, run_id, app_id, page):
    try:
        with connection:
            yield
    except sqlite3.Error as exc:
        # The page is rolled back before recording the failure in a new transaction.
        # If even this write fails, propagate the error rather than claim recovery.
        with connection:
            connection.execute(
                "INSERT INTO play_storage_failures(run_id,app_id,page,failed_at,error) VALUES(?,?,?,?,?)",
                (run_id, app_id, page, utc_now(), str(exc)))
            connection.execute("UPDATE play_jobs SET status='failed', error=? WHERE run_id=? AND app_id=?",
                               (f"Database page commit failed: {exc}", run_id, app_id))


def summarize(connection: sqlite3.Connection, run_id: str, config: dict) -> dict:
    apps = []
    for job in connection.execute("SELECT * FROM play_jobs WHERE run_id=? ORDER BY app_id", (run_id,)):
        counts = dict(connection.execute("""SELECT coalesce(sum(raw_count),0) raw_records,
            coalesce(sum(accepted),0) accepted_records, coalesce(sum(duplicates),0) duplicates,
            coalesce(sum(rejected),0) rejected_records, coalesce(sum(new_count),0) new_records,
            coalesce(sum(repeated_count),0) repeated_records FROM play_pages WHERE run_id=? AND app_id=?""",
            (run_id, job["app_id"])).fetchone())
        changes = dict(connection.execute("""SELECT count(*) classified_pages,
            coalesce(sum(changed),0) changed_records, coalesce(sum(unchanged),0) unchanged_records,
            coalesce(sum(stale),0) stale_records,
            coalesce(sum(cross_page_duplicates),0) cross_page_duplicates
            FROM play_page_changes WHERE run_id=? AND app_id=?""", (run_id, job["app_id"])).fetchone())
        changes["unclassified_pages"] = job["pages"] - changes["classified_pages"]
        overlap = None
        if config.get("overlap_run"):
            shared = connection.execute("""SELECT count(*) FROM review_observations current
                JOIN review_observations baseline ON current.app_id=baseline.app_id AND current.review_id=baseline.review_id
                WHERE current.run_id=? AND baseline.run_id=? AND current.app_id=?""",
                (run_id, config["overlap_run"], job["app_id"])).fetchone()[0]
            overlap = {"baseline_run_id": config["overlap_run"], "shared_ids": shared,
                       "status": "boundary_observed" if shared else "overlap_not_reached",
                       "gap_risk": not bool(shared), "complete_coverage": False, "warnings": []}
            current_run = connection.execute("SELECT * FROM collection_runs WHERE run_id=?", (run_id,)).fetchone()
            prior_run = connection.execute("SELECT * FROM collection_runs WHERE run_id=?", (config["overlap_run"],)).fetchone()
            current_records, _ = sample(connection, current_run, job["app_id"])
            previous_records, _ = sample(connection, prior_run, job["app_id"])
            if current_records and previous_records:
                delta = (max(timestamp(r.review_at) for r in current_records.values()) -
                         max(timestamp(r.review_at) for r in previous_records.values())).total_seconds()
                overlap['newest_timestamp_change_seconds'] = delta
                if delta < 0:
                    overlap['warnings'].append('Newest timestamp moved backwards relative to overlap baseline')
        failures = [dict(row) for row in connection.execute(
            "SELECT page,failed_at,error FROM play_storage_failures WHERE run_id=? AND app_id=? ORDER BY id",
            (run_id, job["app_id"]))]
        apps.append({"app_id": job["app_id"], "label": job["label"], "status": job["status"],
                     "pages": job["pages"], "can_resume": job["status"] in ("paused", "failed", "pending"),
                     "error": job["error"], "storage_failures": failures, "overlap": overlap, **counts, **changes})
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    fk = connection.execute("PRAGMA foreign_key_check").fetchall()
    clean = all(a["status"] in ("paused", "source_end") and a["accepted_records"] > 0 and a["rejected_records"] == 0 for a in apps)
    return {"run_id": run_id, "source": "google_play", "config": config,
            "generated_at": utc_now(), "status": "bounded_success" if clean and integrity == "ok" and not fk else "needs_attention",
            "coverage": "bounded_sample_not_complete_history", "apps": apps,
            "database_integrity_check": integrity, "foreign_key_issues": len(fk),
            "unique_reviews_in_database": connection.execute("SELECT count(*) FROM reviews").fetchone()[0],
            "observations_in_run": connection.execute("SELECT count(*) FROM review_observations WHERE run_id=?", (run_id,)).fetchone()[0],
            "failed_attempts": connection.execute("SELECT count(*) FROM play_attempts WHERE run_id=? AND success=0", (run_id,)).fetchone()[0]}
