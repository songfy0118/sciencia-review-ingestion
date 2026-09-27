"""Export only the public review fields, excluding reviewer names and local logs."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def export(source, destination):
    source = sqlite3.connect(f"file:{Path(source).as_posix()}?mode=ro", uri=True)
    quote = lambda value: "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"
    lines = []
    for row in source.execute("SELECT app_id,label,last_collected_at FROM apps"):
        lines.append("INSERT INTO apps(app_id,label,updated_at) VALUES (" + ",".join(map(quote,row)) + ") ON CONFLICT(app_id) DO NOTHING;")
    fields = "app_id,review_id,content,score,thumbs_up_count,review_at,last_collected_at,review_created_version,reply_content,replied_at"
    count = 0
    for row in source.execute("SELECT " + fields + " FROM reviews"):
        lines.append("INSERT INTO reviews(" + fields.replace("last_collected_at", "collected_at") + ") VALUES (" + ",".join(map(quote,row)) + ") ON CONFLICT(app_id,review_id) DO NOTHING;")
        count += 1
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    source.close()
    print(f"Exported {count} review rows to {destination}")

if __name__ == "__main__":
    export(ROOT / "data/google_play_v2.sqlite3", ROOT / "data/deployment/seed.sql")
