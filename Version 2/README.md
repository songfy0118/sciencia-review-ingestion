# Version 2 — Google Play

Current deliverable: controlled, repeated App-review ingestion into local SQLite.
Start with the [John requirements and acceptance summary](docs/john-acceptance-2026-10-02.md).
No additional website work or unattended scheduling is part of this milestone.
The requested [manual local-to-public sync](docs/public-sync-2026-10-03.md) is
prepared but awaiting the original Cloudflare management login; it is not yet
an uploaded dataset or automatic mirroring.

## Where to look

Current milestone: [controlled repeated ingestion](docs/controlled-ingestion.md).
The [October 2 source-quality follow-up](docs/source-quality-2026-10-02.md) adds
bounded catch-up and database quality assessments. The store now holds 3,798
unique reviews; Duolingo freshness and three missing-overlap windows remain flagged.
See [September 29 results](docs/controlled-findings-2026-09-29.md): three live
rounds, 3,000 observations, 1,003 unique stored reviews, with freshness still open.
The [September 30 follow-up](docs/controlled-findings-2026-09-30.md) reused the
same database about 23.73 hours later: 999 additional IDs, 2,002 unique reviews
total. Duolingo's newest returned date moved backwards and remains a source warning.
The database is the collection output; the website is an inspection interface.
The experiment uses one persistent local SQLite database. It does not modify or
measure the separate public D1 database.

| Folder | Contents |
| --- | --- |
| [web/](web/) | Public website, online collector and database schema |
| [review_ingestion/](review_ingestion/) | Python workflow using `google-play-scraper`, with saved progress and repeatable collection |
| [samples/](samples/) | Test reports and collection counts |
| [tests/](tests/) | Checks for the Python workflow |
| [docs/](docs/) | Findings, data fields and deployment details |
| [config/](config/) | Example app list |

The public website stores data in Cloudflare D1. The Python workflow stores data in local SQLite. They are separate databases; new writes are not automatically mirrored between them.
The [existing public website](https://product-review-data.review-data-lab.workers.dev/)
is a separate historical demo, not the evidence for the current local experiment.

## What works, and what remains

Saved-data search, star/helpful-vote filters, live sample collection, duplicate updates and continuing a saved run have been tested. Failed pages keep earlier saved data. The public adapter is JavaScript based on the `google-play-scraper` request format; the Python workflow uses the package directly.

This remains a research prototype. Samples do not prove full coverage; returned review dates can be old. The public site allows 25 requested reviews per page, three pages per run and 60 shared page requests per hour. Scheduled collection is not enabled.

- [Public deployment and verification](docs/public-preview.md)
- [New-app collection check: Telegram](samples/google_play_new_app_public_2026-09-27.json)
- [Source reliability findings](docs/google-play-cross-day-findings.md)
- [Detailed setup and local commands](GUIDE.md)

For a local run, open a terminal in this **Version 2** folder and run `../.venv/Scripts/python.exe -m review_ingestion.serve_play` using the existing Windows environment. A fresh setup is described in the guide.
