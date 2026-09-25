# Review Ingestion Pipeline

This repository evaluates live review sources and stores normalized review data in one centralized SQLite database. Google Play is now the primary prototype source. The earlier Amazon collector remains in the repository as a completed feasibility study because its access results were not stable enough for a repeatable pipeline.

## Current result

The first Google Play repeatability test collected the 50 newest US-English reviews for Spotify, Duolingo, and Google Maps in three consecutive runs.

- 9 of 9 app collections completed successfully.
- Every app returned 50 valid records in every run.
- Runs two and three repeated the same bounded review window, giving 100% overlap with the previous run.
- The centralized database contained 150 unique reviews and 450 per-run observations.
- SQLite integrity and foreign-key checks passed.
- A continuation token was available in every collection, so later work can add controlled pagination and resume support.

See [Google Play findings](docs/google-play-findings.md) and the machine-readable [repeatability report](samples/google_play_repeatability.json).

## Run the Google Play test

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m review_ingestion.google_play_cli `
  --input config\google_play_apps.example.json `
  --db data\google_play_reviews.sqlite3 `
  --report data\google_play_repeatability.json `
  --runs 3 `
  --count 50 `
  --delay 2
```

The input file contains Google Play app IDs such as `com.spotify.music`. One command collects several apps repeatedly and writes all results into the same database. Repeated reviews update the existing record instead of creating duplicates.

## Centralized database

The SQLite database is the primary output. It contains:

- `apps`: one row per Google Play app;
- `reviews`: one normalized row per unique app and review ID;
- `collection_runs`: one row per complete pipeline run;
- `collection_run_apps`: the status and counts for every app in each run;
- `review_observations`: a trace showing which reviews appeared in each run.

Review fields include the source review ID, app ID, author name, review text, rating, helpful-vote count, app version, review timestamp, developer response, source URL, and first/last collection times.

## Main files

- `review_ingestion/google_play.py`: collects and normalizes Google Play app and review data.
- `review_ingestion/google_play_storage.py`: creates and updates the centralized SQLite database.
- `review_ingestion/google_play_cli.py`: runs repeated collection across several apps and creates the report.
- `config/google_play_apps.example.json`: example app list.
- `samples/google_play_repeatability.json`: results from the first live repeated-collection test.
- `tests/test_google_play.py`: validation, normalization, deduplication, and database tests.

## Current limitations

- The collector uses the unofficial `google-play-scraper` package rather than an official review API.
- Results depend on language, country, sort order, and the selected review window.
- The current test intentionally requests only 50 reviews per app and does not claim complete historical coverage.
- The collector detects that more pages are available, but durable continuation-token checkpoints and automatic resume are the next implementation step.
- Live page or response changes can still require maintenance, so scheduled repeatability checks are needed.

## Amazon feasibility study

Amazon-specific development is paused. The experiment showed that the same ASIN could expose reviews in one request and return sign-in or verification in another. Pagination could also stop unpredictably. These results are documented in [FINDINGS.md](FINDINGS.md), and the earlier [public web demo](https://product-review-data.review-data-lab.workers.dev/) remains available as historical prototype evidence.

The Amazon adapter, sample results, and website are retained so the source decision remains reviewable. They are not the recommended foundation for the next ingestion stage.

## Tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The unit tests use local fixtures and do not contact Google Play or Amazon.
