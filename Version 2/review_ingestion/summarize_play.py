"""Summarize saved reports without collecting data or modifying the database."""
from __future__ import annotations

import argparse
import json
from datetime import timezone
from pathlib import Path

from .evaluate_play import timestamp


def summarize(reports: list[dict]) -> dict:
    rows, seen = [], set()
    for report in reports:
        for run in report['runs']:
            if run['run_id'] in seen:
                raise ValueError('Duplicate run ID; provide each run once')
            seen.add(run['run_id'])
            config = run['config']
            evaluated = {a['app_id']: a for a in run.get('evaluation', {}).get('apps', [])}
            for app in run['apps']:
                evidence = evaluated.get(app['app_id'], {})
                observed = evidence.get('sample_collected_at')
                instant = timestamp(observed) if observed else None
                if instant and instant.tzinfo is None:
                    raise ValueError('Sample collection timestamp must include a timezone')
                day = instant.astimezone(timezone.utc).date().isoformat() if instant else None
                new, repeated = app['new_records'], app['repeated_records']
                updated, unchanged, stale = (app[k] for k in ('changed_records', 'unchanged_records', 'stale_records'))
                accounting_ok = (new + repeated == app['accepted_records'] and
                                 updated + unchanged + stale == repeated and
                                 app.get('unclassified_pages', 0) == 0)
                valid = (run['status'] == 'bounded_success' and
                         run.get('verification_status') == 'passed' and
                         app['status'] in ('paused', 'source_end') and
                         bool(observed) and bool(evidence.get('unique_reviews_in_run')) and accounting_ok)
                rows.append(dict(run_id=run['run_id'], app_id=app['app_id'], label=app['label'],
                    observed_at=observed, day_utc=day, valid_collection=valid,
                    accepted=app['accepted_records'], new=new, repeated=repeated,
                    updated=updated, unchanged=unchanged, stale=stale,
                    accounting_ok=accounting_ok, newest_review=evidence.get('newest_returned_review'),
                    age_days=evidence.get('newest_review_age_days_at_collection'),
                    warnings=evidence.get('warnings', []),
                    protocol={k: config.get(k) for k in ('lang', 'country', 'count', 'sort', 'adapter', 'package')},
                    pages=app['pages']))
    rows.sort(key=lambda r: (r['observed_at'] or '', r['app_id'], r['run_id']))
    groups = {}
    for row in rows:
        key = (row['app_id'], json.dumps(row['protocol'], sort_keys=True), row['pages'])
        groups.setdefault(key, []).append(row)
    coverage = []
    for (app_id, _, pages), group in sorted(groups.items()):
        days = sorted({r['day_utc'] for r in group if r['valid_collection']})
        streak = longest = 0
        previous = None
        for day in days:
            current = timestamp(day + 'T00:00:00Z').date()
            streak = streak + 1 if previous and (current - previous).days == 1 else 1
            longest = max(longest, streak)
            previous = current
        coverage.append(dict(app_id=app_id, protocol=group[0]['protocol'], pages=pages,
                             valid_days_utc=days, longest_consecutive_days=longest))
    return dict(date_basis='UTC date of saved sample collection, not report generation',
                rows=rows, coverage=coverage,
                limitations=['Same-day runs count as one day; parameter changes form separate groups.',
                             'A valid collection can still have freshness warnings; inspect warnings.',
                             'New means new to this database; updated is a subset of repeated.',
                             'Coverage does not establish source completeness or scheduler readiness.'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize([json.loads(p.read_text(encoding='utf-8')) for p in args.reports]), indent=2))


if __name__ == '__main__':
    main()
