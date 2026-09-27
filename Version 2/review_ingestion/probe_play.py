"""Bounded locale diagnostic. Does not alter the main review database."""
import argparse
import json
import time
from pathlib import Path

from .google_play import app_url, normalize_review, utc_now, validate_app_id
from .play_pipeline import fetch_page, SourceError
from .refresh_play import write_atomic


def probe(app_id, *, countries=('us', 'gb'), count=50, fetcher=fetch_page, delay=2):
    validate_app_id(app_id)
    if not 1 <= count <= 200 or not 1 <= len(countries) <= 3:
        raise ValueError('Use 1..200 reviews and at most three countries')
    if any(len(country) != 2 or not country.isascii() or not country.isalpha() for country in countries):
        raise ValueError('Countries must be two-letter codes')
    results, baseline = [], None
    for country in countries:
        if results:
            time.sleep(delay)
        collected_at = utc_now()
        try:
            payload = fetcher(app_id=app_id, lang='en', country=country.lower(), count=count, cursor=None, timeout=20)
            records = [normalize_review(raw, app_id=app_id, source_url=app_url(app_id, 'en', country), collected_at=collected_at)
                       for raw in payload['records']]
            ids = {r.review_id for r in records}
            newest = max((r.review_at for r in records), default=None)
            results.append({'country_requested': country, 'lang_requested': 'en', 'collected_at': collected_at,
                            'status': 'received' if records else 'empty', 'records': len(records), 'unique_ids': len(ids),
                            'newest_returned_review': newest,
                            'same_ids_as_first_country': ids == baseline if baseline is not None else None})
            if baseline is None:
                baseline = ids
        except (SourceError, ValueError, TypeError) as exc:
            results.append({'country_requested': country, 'status': 'failed', 'error': str(exc)})
    return {'app_id': app_id, 'generated_at': utc_now(), 'samples': results,
            'limitations': 'Requested locales are not verified reviewer locations. This comparison does not identify the cause of stale results.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-id', required=True)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    result = probe(args.app_id)
    write_atomic(args.report, result)
    print(json.dumps(result, indent=2))
    return 1 if any(s['status'] != 'received' for s in result['samples']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
