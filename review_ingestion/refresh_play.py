"""Collect, audit and publish a local inspection snapshot in one command."""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from .audit_play import audit
from .google_play import utc_now
from .google_play_cli import load_apps
from .inspect_play import export_database
from .play_pipeline import run_once


def write_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def refresh(*, apps: list[dict], db: Path, output: Path, collector=run_once, **options) -> dict:
    cycle_id = uuid.uuid4().hex
    folder = output / cycle_id
    folder.mkdir(parents=True, exist_ok=False)
    health = {"cycle_id": cycle_id, "started_at": utc_now(), "status": "running",
              "run_id": None, "issues": [], "snapshot": None}
    write_atomic(folder / "health.json", health)
    try:
        report = collector(apps=apps, db_path=db, **options)
        health["run_id"] = report["run_id"]
        write_atomic(folder / "run.json", report)
        # The audit and exports refer to exactly the same SQLite backup.
        export_database(db, folder)
        checks = audit(folder / "reviews.sqlite3")
        write_atomic(folder / "audit.json", checks)
        if report["status"] != "bounded_success":
            health["issues"].append("Collection needs attention; saved reviews may include earlier runs.")
        if not checks["storage_checks_passed"]:
            health["issues"].append("Stored records did not pass the source-snapshot audit.")
        stale = [app["app_id"] for app in checks["apps"] if app["freshness_warning"]]
        if stale:
            health["issues"].append("Review freshness needs checking: " + ", ".join(stale))
        health["status"] = "needs_attention" if report["status"] != "bounded_success" or not checks["storage_checks_passed"] else "warning" if stale else "ready"
        health["snapshot"] = str((folder / "index.html").resolve())
        health["unique_reviews"] = checks["unique_reviews"]
        # Attach current-cycle results to the already-created inspection page.
        from html import escape
        banner = '<section aria-label="Collection status"><h2>Latest refresh: ' + escape(health["status"].replace("_", " ")) + '</h2>'
        banner += '<p>' + escape(health["started_at"]) + ' · Run ' + escape(report["run_id"]) + '</p>'
        banner += ''.join('<p>' + escape(issue) + '</p>' for issue in health["issues"])
        banner += '<p><a href="run.json">Collection report</a> · <a href="audit.json">Data checks</a></p></section>'
        page = folder / "index.html"
        page.write_text(page.read_text(encoding="utf-8").replace('<section>', banner + '<section>', 1), encoding="utf-8")
    except Exception as exc:
        health["status"] = "failed"
        health["issues"].append(f"{type(exc).__name__}: {exc}")
    health["completed_at"] = utc_now()
    write_atomic(folder / "health.json", health)
    # Previous cycle directories are preserved even when this refresh fails.
    write_atomic(output / "latest.json", health)
    return health


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/cycles"))
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--country", default="us")
    parser.add_argument("--resume")
    args = parser.parse_args()
    health = refresh(apps=load_apps(args.input), db=args.db, output=args.output,
                     pages=args.pages, count=args.count, delay=args.delay, timeout=args.timeout,
                     retries=args.retries, lang=args.lang, country=args.country, resume=args.resume)
    print(json.dumps(health, indent=2))
    return 1 if health["status"] in ("failed", "needs_attention") else 0


if __name__ == "__main__":
    raise SystemExit(main())
