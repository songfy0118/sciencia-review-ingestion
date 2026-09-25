"""Create an offline, read-only review browser and actual SQLite snapshot."""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def export_database(db: Path, output: Path) -> dict:
    if not db.is_file():
        raise ValueError("Database does not exist")
    output.mkdir(parents=True, exist_ok=True)
    snapshot = output / "reviews.sqlite3"
    if snapshot.resolve() == db.resolve():
        raise ValueError("Choose an output directory separate from the live database")
    # SQLite backup gives a consistent view even if the collector is active.
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
            target.row_factory = sqlite3.Row
            records = [dict(r) for r in target.execute("SELECT * FROM reviews ORDER BY app_id,review_at DESC,review_id")]
            apps = [dict(r) for r in target.execute("SELECT app_id,count(*) reviews FROM reviews GROUP BY app_id")]
    (output / "reviews.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    def escape(value):
        return html.escape(str(value))
    rows = "".join(
        f'<tr data-app="{escape(r["app_id"])}"><td>{escape(r["app_id"])}</td><td>{r["score"]}/5</td>'
        f'<td>{escape(r["review_at"])}</td><td class="content">{escape(r["content"])}</td>'
        f'<td>{escape(r["review_id"])}</td></tr>' for r in records
    )
    summary = "".join(f'<li>{escape(a["app_id"])}: {a["reviews"]} reviews</li>' for a in apps)
    options = ''.join(f'<option value="{escape(a["app_id"])}">{escape(a["app_id"])}</option>' for a in apps)
    document = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review data | Collection snapshot</title>
<style>body{font:16px/1.6 system-ui,sans-serif;color:#243143;background:#f5f7fa;margin:0}
main{max-width:1200px;margin:40px auto;padding:24px}h1{font-size:32px;margin-bottom:4px}
a{color:#244dac}section{background:white;border:1px solid #dae0e8;border-radius:8px;padding:24px;margin:24px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:14px;border-bottom:1px solid #e4e8ee;text-align:left;vertical-align:top}
th{background:#edf1f6}td{overflow-wrap:anywhere}.content{min-width:260px;white-space:pre-wrap}.scroll{overflow:auto}
input,select,button{font:inherit;padding:8px;border:1px solid #bec9d7;border-radius:4px;margin:4px}button{cursor:pointer}button:disabled{cursor:default;opacity:.5}
</style><main><h1>Review data</h1><p>A saved view of the Google Play collection database.</p>
<section><h2>Stored reviews</h2><p>RECORD_COUNT unique reviews. This is a collected sample, not the complete review history.</p>
<ul>APP_SUMMARY</ul><p><a href="reviews.json" download>Download review JSON</a> ·
<a href="reviews.sqlite3" download>Download SQLite database</a></p>
<p>JSON contains review records. SQLite also contains collection history, page snapshots and checkpoints.</p></section>
<section><h2>Browse reviews</h2><p>Filter by app or search the stored records. Downloads contain all stored reviews.
Ratings are the original star scores; no sentiment model has been applied. Dates are UTC.</p>
<label>App <select id="app"><option value="">All apps</option>APP_OPTIONS</select></label>
<label>Search <input id="search" type="search" placeholder="Review text or ID"></label>
<p id="count" role="status"></p><button id="previous">Previous</button><button id="next">Next</button>
<div class="scroll"><table><thead><tr><th>App</th><th>Rating</th><th>Review date</th><th>Review</th><th>Review ID</th></tr></thead>
<tbody>REVIEW_ROWS</tbody></table></div></section></main>
<script>
const rows = [...document.querySelectorAll('tbody tr')];
const app = document.getElementById('app'), search = document.getElementById('search');
const previous = document.getElementById('previous'), next = document.getElementById('next');
let page = 0;
function render() {
 const matches = rows.filter(r => (!app.value || r.dataset.app === app.value) && r.textContent.toLowerCase().includes(search.value.toLowerCase()));
 page = Math.min(page, Math.max(0, Math.ceil(matches.length / 20) - 1));
 rows.forEach(r => r.hidden = true);
 matches.slice(page * 20, page * 20 + 20).forEach(r => r.hidden = false);
 document.getElementById('count').textContent = matches.length ? `${page*20+1}–${Math.min(page*20+20,matches.length)} of ${matches.length} matching reviews` : 'No matching reviews';
 previous.disabled = page === 0; next.disabled = (page+1)*20 >= matches.length;
}
app.addEventListener('change', () => {page=0;render()});
search.addEventListener('input', () => {page=0;render()});
previous.addEventListener('click', () => {page--;render()});
next.addEventListener('click', () => {page++;render()});
render();
</script></html>'''
    document = document.replace("RECORD_COUNT", str(len(records))).replace("APP_SUMMARY", summary).replace("APP_OPTIONS", options).replace("REVIEW_ROWS", rows)
    (output / "index.html").write_text(document, encoding="utf-8")
    return {"unique_reviews": len(records), "preview": str((output / "index.html").resolve()), "database": str(snapshot.resolve())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/inspection"))
    args = parser.parse_args()
    print(json.dumps(export_database(args.db, args.output), indent=2))


if __name__ == "__main__":
    main()
