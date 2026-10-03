"""Publish a contact-redacted snapshot, never the operational SQLite database."""
import argparse
import gzip
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

CONTACT = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\w)\+?\d[\d ().-]{5,}\d(?!\w)')
SECRET = re.compile(r'-----BEGIN [^-]*PRIVATE KEY-----|github_pat_[\w]+|gh[pousr]_[\w]+|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}', re.I)


def redact(text):
    if text is None:
        return None, 0
    cleaned, contacts = CONTACT.subn('[REDACTED CONTACT]', text)
    cleaned, secrets = SECRET.subn('[REDACTED SECRET]', cleaned)
    return cleaned, contacts + secrets


def export(source: Path, output: Path):
    if not source.is_file():
        raise ValueError('Source database not found')
    if source.resolve() == output.resolve():
        raise ValueError('Output must be a directory separate from source')
    fields = 'r.app_id,a.label,r.review_id,r.content,r.score,r.thumbs_up_count,r.review_at,r.last_collected_at AS collected_at,r.review_created_version,r.reply_content,r.replied_at,r.source_url'
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as c:
        c.row_factory = sqlite3.Row
        c.execute('BEGIN')
        rows = [dict(row) for row in c.execute('SELECT ' + fields + ' FROM reviews r JOIN apps a USING(app_id) ORDER BY r.app_id,r.review_id')]
        quality = [dict(row) for row in c.execute('SELECT app_id,quality_status FROM latest_play_source_quality ORDER BY app_id')]
    replacements = 0
    for row in rows:
        for field in ('content', 'reply_content'):
            row[field], count = redact(row[field])
            replacements += count
    raw = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    compressed = gzip.compress(raw, mtime=0)
    metadata = {'schema_version': 1, 'reviews': len(rows), 'apps': len({r['app_id'] for r in rows}),
                'snapshot_not_live_database': True, 'source': 'Google Play; English/US bounded collection',
                'contact_or_secret_replacements': replacements,
                'excluded_fields': ['author_name', 'avatars', 'raw_source_snapshots', 'operational_logs', 'credentials'],
                'privacy_limitations': 'Pattern-based redaction is not a guarantee of complete anonymization; dates/numbers may be over-redacted.',
                'quality': quality, 'uncompressed_sha256': hashlib.sha256(raw).hexdigest(),
                'compressed_sha256': hashlib.sha256(compressed).hexdigest(),
                'coverage': 'Bounded sample, not complete history; source freshness warnings remain.'}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'reviews.json.gz').write_bytes(compressed)
    (output / 'preview.json').write_text(json.dumps(rows[:10], ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.source, args.output), indent=2))
