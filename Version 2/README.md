# Version 2 — Google Play

**[Try the public website](https://product-review-data.review-data-lab.workers.dev/)**

Search saved app reviews, or paste a Google Play link to collect a small new sample. Records are saved to a shared online database; visitors do not need local files.

## Where to look

| Folder | Contents |
| --- | --- |
| [web/](web/) | Public website, online collector and database schema |
| [review_ingestion/](review_ingestion/) | Python workflow using `google-play-scraper`, with saved progress and repeatable collection |
| [samples/](samples/) | Test reports and collection counts |
| [tests/](tests/) | Checks for the Python workflow |
| [docs/](docs/) | Findings, data fields and deployment details |
| [config/](config/) | Example app list |

The public website stores data in Cloudflare D1. The Python workflow stores data in local SQLite. They are separate databases; new writes are not automatically mirrored between them.

## What works, and what remains

Saved-data search, star/helpful-vote filters, live sample collection, duplicate updates and continuing a saved run have been tested. Failed pages keep earlier saved data. The public adapter is JavaScript based on the `google-play-scraper` request format; the Python workflow uses the package directly.

This remains a research prototype. Samples do not prove full coverage; returned review dates can be old. The public site allows 25 requested reviews per page, three pages per run and 60 shared page requests per hour. Scheduled collection is not enabled.

- [Public deployment and verification](docs/public-preview.md)
- [New-app collection check: Telegram](samples/google_play_new_app_public_2026-09-27.json)
- [Source reliability findings](docs/google-play-cross-day-findings.md)
- [Detailed setup and local commands](GUIDE.md)

For a local run, open a terminal in this **Version 2** folder and run `../.venv/Scripts/python.exe -m review_ingestion.serve_play` using the existing Windows environment. A fresh setup is described in the guide.
