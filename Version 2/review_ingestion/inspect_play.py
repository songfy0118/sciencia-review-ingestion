"""Create an offline, read-only review browser and actual SQLite snapshot."""
from __future__ import annotations

import argparse
import base64
import html
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .google_play import APP_ID_PATTERN, app_url


def _text(value: object) -> str:
    return html.escape(str(value or ""))


def _name(app: dict) -> str:
    label = app["label"]
    return label if label and label != app["app_id"] else app["app_id"].rsplit(".", 1)[-1].replace("_", " ").title()


def _icon(app_id: str, name: str) -> str:
    if APP_ID_PATTERN.fullmatch(app_id):
        for extension, mime in (("png", "image/png"), ("jpg", "image/jpeg")):
            path = Path(__file__).with_name("app_icons") / f"{app_id}.{extension}"
            if path.is_file():
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                return f'<img src="data:{mime};base64,{data}" alt="" loading="lazy">'
    return f'<span class="tile-fallback" aria-hidden="true">{_text(name[:1].upper())}</span>'


def _review_card(record: dict, app: dict) -> str:
    name = _name(app)
    score = record["score"]
    votes = record["thumbs_up_count"]
    reply = record["reply_content"]
    author = record["author_name"] or "Google Play reviewer"
    version = record["review_created_version"] or "Not provided"
    source = app_url(record["app_id"])
    reply_html = (
        f'<details><summary>Developer reply</summary><p class="reply">{_text(reply)}</p></details>'
        if reply else ""
    )
    return (
        f'<article class="review-card" data-app="{_text(record["app_id"])}" data-name="{_text(name.casefold())}" '
        f'data-score="{score}" data-helpful="{votes}">'
        f'<div class="review-head"><div class="review-app">{_icon(record["app_id"], name)}'
        f'<span>{_text(name)}</span></div><time datetime="{_text(record["review_at"])}">'
        f'{_text(record["review_at"][:10])}</time></div>'
        f'<div class="stars" aria-label="{score} out of 5 stars">{"★" * score}{"☆" * (5 - score)}'
        f'<small>{score}/5</small></div>'
        f'<p class="review-text">{_text(record["content"])}</p>'
        f'{reply_html}'
        f'<div class="review-foot"><span>{_text(author)}</span><span>{votes} helpful vote{"s" if votes != 1 else ""}</span>'
        f'<details><summary>Record details</summary><div class="record-detail">'
        f'<p>Review ID: {_text(record["review_id"])}</p>'
        f'<p>Exact review time: {_text(record["review_at"])} (UTC)</p>'
        f'<p>App version: {_text(version)}</p>'
        f'<p><a href="{_text(source)}" target="_blank" rel="noopener noreferrer">App on Google Play</a></p>'
        f'</div></details></div></article>'
    )


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
            records = [dict(row) for row in target.execute(
                "SELECT * FROM reviews ORDER BY review_at DESC, app_id, review_id"
            )]
            apps = [dict(row) for row in target.execute(
                "SELECT a.app_id, a.label, count(r.review_id) reviews "
                "FROM apps a JOIN reviews r ON a.app_id=r.app_id GROUP BY a.app_id, a.label"
            )]
    apps.sort(key=lambda app: _name(app).casefold())
    app_by_id = {app["app_id"]: app for app in apps}
    (output / "reviews.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    app_cards = ['<button class="app-tile selected" type="button" data-app="" aria-pressed="true">'
                 '<span class="tile-fallback" aria-hidden="true">All</span><span class="label">All apps'
                 f'<small>{len(records)} saved reviews</small></span></button>']
    options = []
    for app in apps:
        name = _name(app)
        app_cards.append(
            f'<button class="app-tile" type="button" data-app="{_text(app["app_id"])}" aria-pressed="false">'
            f'{_icon(app["app_id"], name)}<span class="label">{_text(name)}'
            f'<small>{app["reviews"]} saved reviews</small></span></button>'
        )
        options.append(f'<option value="{_text(app["app_id"])}">{_text(name)}</option>')
    cards = "".join(_review_card(record, app_by_id[record["app_id"]]) for record in records)
    template = Path(__file__).with_name("play_results.html").read_text(encoding="utf-8")
    document = (template.replace("RECORD_COUNT", f"{len(records):,}")
                .replace("APP_COUNT", str(len(apps)))
                .replace("APP_CARDS", "".join(app_cards))
                .replace("APP_OPTIONS", "".join(options))
                .replace("REVIEW_CARDS", cards))
    (output / "index.html").write_text(document, encoding="utf-8")
    return {"unique_reviews": len(records), "preview": str((output / "index.html").resolve()),
            "database": str(snapshot.resolve())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/inspection"))
    args = parser.parse_args()
    print(json.dumps(export_database(args.db, args.output), indent=2))


if __name__ == "__main__":
    main()
