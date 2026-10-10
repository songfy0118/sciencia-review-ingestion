"""Summarize saved reports without collecting data or modifying the database."""
from __future__ import annotations

import argparse
import json
from datetime import timedelta, timezone
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
            app_ids = [a['app_id'] for a in run['apps']]
            if len(app_ids) != len(set(app_ids)):
                raise ValueError('Duplicate App ID within a run')
            evaluations = run.get('evaluation', {}).get('apps', [])
            evaluated = {a['app_id']: a for a in evaluations}
            if len(evaluated) != len(evaluations):
                raise ValueError('Duplicate App ID within evaluation')
            for app in run['apps']:
                evidence = evaluated.get(app['app_id'], {})
                observed = evidence.get('sample_collected_at')
                instant = timestamp(observed) if observed else None
                if instant and instant.tzinfo is None:
                    raise ValueError('Sample collection timestamp must include a timezone')
                day = instant.astimezone(timezone.utc).date().isoformat() if instant else None
                new, repeated = app['new_records'], app['repeated_records']
                updated, unchanged, stale = (app[k] for k in ('changed_records', 'unchanged_records', 'stale_records'))
                counts = (new, repeated, updated, unchanged, stale, app['accepted_records'],
                          app.get('unclassified_pages', 0), app['pages'])
                accounting_ok = (all(type(n) is int and n >= 0 for n in counts) and
                                 new + repeated == app['accepted_records'] and
                                 updated + unchanged + stale == repeated and
                                 app.get('unclassified_pages', 0) == 0)
                unique = evidence.get('unique_reviews_in_run')
                try:
                    newest = timestamp(evidence.get('newest_returned_review'))
                    newest_ok = bool(instant and newest.tzinfo and newest <= instant)
                except (ValueError, TypeError, AttributeError):
                    newest_ok = False
                evidence_ok = (type(unique) is int and 0 < unique <= app['accepted_records'] and
                               evidence.get('pages') == app['pages'] and
                               evidence.get('status') == app['status'] and
                               newest_ok)
                valid = (run['status'] == 'bounded_success' and
                         run.get('verification_status') == 'passed' and
                         app['status'] in ('paused', 'source_end') and
                         bool(observed) and evidence_ok and accounting_ok)
                warnings = list(evidence.get('warnings', []))
                comparison = evidence.get('comparison')
                if comparison and comparison.get('shared_ids_in_window') == 0:
                    warnings.append('No overlap with previous bounded window; continuity is unverified')
                rows.append(dict(run_id=run['run_id'], app_id=app['app_id'], label=app['label'],
                    observed_at=observed, day_utc=day, valid_collection=valid,
                    accepted=app['accepted_records'], new=new, repeated=repeated,
                    updated=updated, unchanged=unchanged, stale=stale,
                    accounting_ok=accounting_ok, evidence_consistent=evidence_ok,
                    source_quality_ok=valid and not warnings,
                    overlap_with_previous=comparison.get('shared_ids_in_window') if comparison else None,
                    newest_review=evidence.get('newest_returned_review'),
                    age_days=evidence.get('newest_review_age_days_at_collection'),
                    warnings=warnings,
                    protocol={**{k: config.get(k) for k in ('lang', 'country', 'count', 'sort', 'adapter', 'package')},
                              'overlap_run': config.get('overlap_run')},
                    pages=app['pages']))
    rows.sort(key=lambda r: (timestamp(r['observed_at']).timestamp() if r['observed_at'] else float('-inf'),
                             r['app_id'], r['run_id']))
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
        observed_rows = [r for r in group if r['valid_collection']]
        intervals = []
        for earlier, later in zip(observed_rows, observed_rows[1:]):
            hours = (timestamp(later['observed_at']) - timestamp(earlier['observed_at'])).total_seconds() / 3600
            intervals.append(dict(previous_run_id=earlier['run_id'], run_id=later['run_id'],
                                  hours=round(hours, 2),
                                  near_daily_interval=20 <= hours <= 28))
        missing_days = []
        if days:
            current = timestamp(days[0] + 'T00:00:00Z').date()
            end = timestamp(days[-1] + 'T00:00:00Z').date()
            while current < end:
                if current.isoformat() not in days:
                    missing_days.append(current.isoformat())
                current += timedelta(days=1)
        coverage.append(dict(app_id=app_id, protocol=group[0]['protocol'], pages=pages,
                             valid_days_utc=days, longest_consecutive_days=longest,
                             missing_days_utc=missing_days, intervals=intervals,
                             near_daily_intervals=bool(intervals) and all(i['near_daily_interval'] for i in intervals)))
    return dict(date_basis='UTC date of saved sample collection, not report generation',
                rows=rows, coverage=coverage,
                limitations=['Same-day runs count as one day; parameter changes form separate groups.',
                             '20-28 hours is a reporting diagnostic, not an approved collection frequency.',
                             'Missing days are absence of valid observations, not proof that no attempt occurred.',
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
