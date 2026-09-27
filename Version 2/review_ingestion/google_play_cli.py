from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from .google_play import validate_app_id
from .play_pipeline import run_once
from .storage import write_json


def load_apps(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Input must be a non-empty JSON list")
    apps = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each app must be an object")
        app_id = validate_app_id(str(item.get("app_id") or ""))
        apps.append({"app_id": app_id, "label": str(item.get("label") or app_id)})
    if len({a["app_id"] for a in apps}) != len(apps):
        raise ValueError("Duplicate app IDs")
    return apps


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect bounded Google Play pages into a persistent database")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--count", type=int, default=50, help="Requested records per page (1..200)")
    parser.add_argument("--pages", type=int, default=2, help="Additional pages per app in this invocation")
    parser.add_argument("--delay", type=float, default=2, help="Seconds between page attempts")
    parser.add_argument("--interval", type=float, default=30, help="Seconds between repeated runs")
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--country", default="us")
    parser.add_argument("--resume", help="Resume a run ID printed by an earlier invocation")
    args = parser.parse_args()
    if not 1 <= args.runs <= 20 or not math.isfinite(args.interval) or args.interval < 0:
        parser.error("runs must be 1..20; interval must be nonnegative")
    if args.resume and args.runs != 1:
        parser.error("Use --runs 1 when resuming")
    apps = load_apps(args.input)
    reports = []
    for index in range(args.runs):
        report = run_once(apps=apps, db_path=args.db, count=args.count, pages=args.pages,
                          lang=args.lang, country=args.country, delay=args.delay,
                          timeout=args.timeout, retries=args.retries, resume=args.resume)
        reports.append(report)
        # Refresh after each run; completed runs survive later interruption.
        write_json(args.report, {"schema_version": 2, "runs": reports})
        if index + 1 < args.runs:
            time.sleep(args.interval)
    print(json.dumps({"schema_version": 2, "runs": reports}, indent=2))
    return 0 if all(r["status"] == "bounded_success" for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
