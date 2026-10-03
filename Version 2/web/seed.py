"""Export only the public review fields, excluding reviewer names and local logs."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def export(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or (source.exists() and destination.exists() and source.samefile(destination)):
        raise ValueError('Database and SQL destination must be distinct files')
    quote = lambda value: "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"
    lines = []
    fields = "app_id,review_id,content,score,thumbs_up_count,review_at,last_collected_at,review_created_version,reply_content,replied_at"
    public_fields = fields.replace('last_collected_at', 'collected_at')
    updates = ','.join(f'{key}=excluded.{key}' for key in public_fields.split(',')[2:])
    count = 0
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.execute('BEGIN')
        for row in connection.execute("SELECT app_id,label,last_collected_at FROM apps ORDER BY app_id"):
            lines.append("INSERT INTO apps(app_id,label,updated_at) VALUES (" + ",".join(map(quote,row)) + ") ON CONFLICT(app_id) DO UPDATE SET label=excluded.label,updated_at=excluded.updated_at WHERE excluded.updated_at > apps.updated_at;")
        for row in connection.execute("SELECT " + fields + " FROM reviews ORDER BY app_id,review_id"):
            lines.append("INSERT INTO reviews(" + public_fields + ") VALUES (" + ",".join(map(quote,row)) + ") ON CONFLICT(app_id,review_id) DO UPDATE SET " + updates + " WHERE excluded.collected_at > reviews.collected_at;")
            count += 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    print(f"Exported {count} review rows to {destination}")
    return count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/google_play_v2.sqlite3')
    parser.add_argument('--destination', type=Path, default=ROOT / 'data/deployment/seed.sql')
    args = parser.parse_args()
    export(args.source, args.destination)
