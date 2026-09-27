"""Collect, audit and publish a local inspection snapshot in one command."""
from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from html import escape
from pathlib import Path

from .audit_play import audit
from .google_play import utc_now
from .google_play_cli import load_apps
from .evaluate_play import evaluate
from .inspect_play import export_database
from .play_pipeline import run_once


def write_atomic(path: Path, value: dict) -> None:
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2))


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_health(path: Path) -> dict:
    health = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(health, dict) or not isinstance(health.get('started_at'), str)
            or not isinstance(health.get('status'), str) or not isinstance(health.get('issues'), list)
            or not all(isinstance(issue, str) for issue in health['issues'])):
        raise ValueError('Invalid saved status fields')
    return health


def publish_history(output: Path) -> None:
    cycles = []
    damaged = []
    for path in output.glob('*/health.json'):
        if re.fullmatch(r'[0-9a-f]{32}', path.parent.name):
            try:
                health = read_health(path)
            except (OSError, ValueError) as exc:
                damaged.append(f'Cannot read saved status {path.parent.name}: {type(exc).__name__}')
                continue
            cycles.append((health, path.parent.name))
    cycles.sort(key=lambda entry: entry[0]['started_at'], reverse=True)
    if not cycles:
        return
    write_atomic(output / 'latest.json', cycles[0][0])
    rows = []
    for health, folder in cycles:
        link = f'<a href="{folder}/index.html">View results</a>' if health.get('snapshot') else f'<a href="{folder}/health.json">View status</a>'
        issues = '<br>'.join(escape(issue) for issue in health['issues'])
        rows.append(f'<tr><td>{escape(health["started_at"])}</td><td>{escape(health["status"])}</td>'
                    f'<td>{health.get("unique_reviews", "—")}</td><td>{issues}</td><td>{link}</td></tr>')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review collection history</title><style>body{font:16px/1.6 system-ui;color:#243143;background:#f5f7fa;margin:0}main{max-width:1150px;margin:40px auto;padding:24px}table{border-collapse:collapse;background:white;width:100%}th,td{padding:14px;border-bottom:1px solid #dae0e8;text-align:left;vertical-align:top}a{color:#244dac}.scroll{overflow:auto}</style>
<main><h1>Review collection history</h1><p>Saved refreshes from the local Google Play collection workflow.</p>
<p>Each refresh keeps its own data snapshot and checks. Counts are database totals at that time, not new reviews per run. A warning means the result needs review.</p>
<p>This page shows saved results. It does not start collection or refresh automatically.</p>
<div class="scroll"><table><thead><tr><th>Started (UTC)</th><th>Status</th><th>Stored reviews</th><th>Notes</th><th>Details</th></tr></thead><tbody>ROWS</tbody></table></div></main></html>'''
    if damaged:
        document = document.replace('<div class="scroll">', '<p role="alert">' + '<br>'.join(escape(e) for e in damaged) + '</p><div class="scroll">', 1)
    write_text_atomic(output / 'index.html', document.replace('ROWS', ''.join(rows)))


def refresh(*, apps: list[dict], db: Path, output: Path, collector=run_once, **options) -> dict:
    cycle_id = uuid.uuid4().hex
    folder = output / cycle_id
    folder.mkdir(parents=True, exist_ok=False)
    health = {"cycle_id": cycle_id, "started_at": utc_now(), "status": "running",
              "run_id": None, "issues": [], "snapshot": None}
    write_atomic(folder / "health.json", health)
    publish_history(output)
    try:
        report = collector(apps=apps, db_path=db, **options)
        health["run_id"] = report["run_id"]
        write_atomic(folder / "run.json", report)
        # The audit and exports refer to exactly the same SQLite backup.
        export_database(db, folder)
        checks = audit(folder / "reviews.sqlite3")
        write_atomic(folder / "audit.json", checks)
        evaluation = evaluate(folder / "reviews.sqlite3", report["run_id"])
        write_atomic(folder / "evaluation.json", evaluation)
        if report["status"] != "bounded_success":
            health["issues"].append("Collection needs attention; saved reviews may include earlier runs.")
        if not checks["storage_checks_passed"]:
            health["issues"].append("Stored records did not pass the source-snapshot audit.")
        for app in evaluation["apps"]:
            for warning in app["warnings"]:
                health["issues"].append(app["app_id"] + ": " + warning)
        health["status"] = "needs_attention" if report["status"] != "bounded_success" or not checks["storage_checks_passed"] else "warning" if health["issues"] else "ready"
        health["snapshot"] = str((folder / "index.html").resolve())
        health["unique_reviews"] = checks["unique_reviews"]
        # Attach current-cycle results to the already-created inspection page.
        banner = '<section aria-label="Collection status"><h2>Latest refresh: ' + escape(health["status"].replace("_", " ")) + '</h2>'
        banner += '<p>' + escape(health["started_at"]) + ' · Run ' + escape(report["run_id"]) + '</p>'
        banner += ''.join('<p>' + escape(issue) + '</p>' for issue in health["issues"])
        banner += '<p><a href="../index.html">All refreshes</a> · <a href="run.json">Collection report</a> · <a href="audit.json">Data checks</a> · <a href="evaluation.json">Source evaluation</a></p>'
        banner += '<div class="scroll"><table><thead><tr><th>App</th><th>Reviews in this run</th><th>Newest review (UTC)</th><th>Hours since comparable sample</th><th>New IDs in window</th></tr></thead><tbody>'
        for app in evaluation['apps']:
            comparison = app['comparison'] or {}
            values = [app['label'], app['unique_reviews_in_run'], app['newest_returned_review'] or 'Unavailable',
                      comparison.get('hours_between_samples', 'Not compared'), comparison.get('new_ids_in_window', 'Not compared')]
            banner += '<tr>' + ''.join('<td>' + escape(str(v)) + '</td>' for v in values) + '</tr>'
        banner += '</tbody></table></div></section>'
        page = folder / "index.html"
        page.write_text(page.read_text(encoding="utf-8").replace('<section>', banner + '<section>', 1), encoding="utf-8")
    except Exception as exc:
        health["status"] = "failed"
        health["issues"].append(f"{type(exc).__name__}: {exc}")
    health["completed_at"] = utc_now()
    write_atomic(folder / "health.json", health)
    # Previous cycle directories are preserved even when this refresh fails.
    publish_history(output)
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
