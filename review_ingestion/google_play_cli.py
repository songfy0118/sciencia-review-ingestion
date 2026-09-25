from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from .google_play import collect_app, utc_now, validate_app_id
from .google_play_storage import (
    connect,
    save_app_result,
    save_observations,
    save_run,
    upsert_app,
    upsert_reviews,
)
from .storage import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded, repeated Google Play review collection test."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--country", default="us")
    return parser.parse_args()


def load_apps(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Input must be a non-empty JSON list.")
    apps: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each app must be a JSON object.")
        app_id = validate_app_id(str(item.get("app_id") or ""))
        if app_id in seen:
            raise ValueError(f"Duplicate app_id in input: {app_id}")
        seen.add(app_id)
        apps.append({"app_id": app_id, "label": str(item.get("label") or app_id)})
    return apps


def overlap_rate(previous: list[str], current: list[str]) -> float | None:
    if not previous or not current:
        return None
    return round(len(set(previous) & set(current)) / min(len(previous), len(current)), 3)


def run_collection(
    *,
    apps: list[dict[str, str]],
    db_path: Path,
    runs: int,
    count: int,
    delay: float,
    lang: str,
    country: str,
) -> dict:
    if not 1 <= runs <= 20:
        raise ValueError("runs must be between 1 and 20.")
    if not 1 <= count <= 200:
        raise ValueError("count must be between 1 and 200.")
    if delay < 0:
        raise ValueError("delay cannot be negative.")

    connection = connect(db_path)
    all_runs: list[dict] = []
    previous_ids: dict[str, list[str]] = {}
    try:
        for sequence in range(1, runs + 1):
            run_id = str(uuid.uuid4())
            started_at = utc_now()
            app_results: list[dict] = []
            collected_reviews: dict[str, list] = {}
            for app_config in apps:
                app_id = app_config["app_id"]
                try:
                    app_record, reviews, has_more, skipped = collect_app(
                        app_id,
                        label=app_config["label"],
                        lang=lang,
                        country=country,
                        count=count,
                    )
                    collected_at = reviews[0].collected_at if reviews else utc_now()
                    upsert_app(connection, app_record, collected_at)
                    new_count, repeated_count = upsert_reviews(connection, reviews)
                    collected_reviews[app_id] = reviews
                    current_ids = [review.review_id for review in reviews]
                    result = {
                        "app_id": app_id,
                        "label": app_record.label,
                        "status": "collected",
                        "requested_count": count,
                        "received_count": len(reviews),
                        "new_count": new_count,
                        "repeated_count": repeated_count,
                        "skipped_count": skipped,
                        "continuation_available": has_more,
                        "overlap_with_previous_run": overlap_rate(
                            previous_ids.get(app_id, []), current_ids
                        ),
                    }
                    previous_ids[app_id] = current_ids
                except Exception as exc:
                    result = {
                        "app_id": app_id,
                        "label": app_config["label"],
                        "status": "failed",
                        "requested_count": count,
                        "received_count": 0,
                        "new_count": 0,
                        "repeated_count": 0,
                        "skipped_count": 0,
                        "continuation_available": False,
                        "overlap_with_previous_run": None,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                app_results.append(result)

            completed_at = utc_now()
            status = "completed" if all(item["status"] == "collected" for item in app_results) else "partial"
            run_report = {
                "run_id": run_id,
                "sequence_number": sequence,
                "started_at": started_at,
                "completed_at": completed_at,
                "status": status,
                "apps": app_results,
            }
            save_run(
                connection,
                run_id=run_id,
                sequence_number=sequence,
                started_at=started_at,
                completed_at=completed_at,
                status=status,
                lang=lang,
                country=country,
                requested_per_app=count,
                report=run_report,
            )
            for result in app_results:
                save_app_result(connection, run_id, result)
                save_observations(
                    connection,
                    run_id,
                    collected_reviews.get(result["app_id"], []),
                )
            connection.commit()
            all_runs.append(run_report)
            if sequence < runs and delay:
                time.sleep(delay)

        successful_app_runs = sum(
            app_result["status"] == "collected"
            for run in all_runs
            for app_result in run["apps"]
        )
        expected_app_runs = runs * len(apps)
        unique_reviews = connection.execute("SELECT count(*) FROM reviews").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        suitability = (
            "promising_for_prototype"
            if successful_app_runs == expected_app_runs and unique_reviews > 0
            else "needs_more_evaluation"
        )
        return {
            "source": "google_play",
            "generated_at": utc_now(),
            "apps_requested": len(apps),
            "runs_requested": runs,
            "successful_app_runs": successful_app_runs,
            "expected_app_runs": expected_app_runs,
            "unique_reviews_in_database": unique_reviews,
            "database_integrity_check": integrity,
            "foreign_key_issues": len(foreign_key_issues),
            "suitability": suitability,
            "limitations": [
                "Uses an unofficial third-party scraper rather than an official Google Play review API.",
                "Results depend on language, country, sort order, and the requested recent-review window.",
                "The live Google Play response format can change and requires ongoing contract checks.",
                "This bounded test does not claim complete historical coverage.",
            ],
            "runs": all_runs,
        }
    finally:
        connection.close()


def main() -> int:
    args = parse_args()
    apps = load_apps(args.input)
    report = run_collection(
        apps=apps,
        db_path=args.db,
        runs=args.runs,
        count=args.count,
        delay=args.delay,
        lang=args.lang,
        country=args.country,
    )
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["successful_app_runs"] == report["expected_app_runs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
