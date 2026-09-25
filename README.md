# Review Ingestion Pipeline

Collect a defined list of Google Play apps, save review records into one persistent SQLite database, and resume from the last committed page. This is a bounded research prototype. Amazon work is paused; its code and findings remain as the earlier source-feasibility experiment.

**For a quick review:** start with [the current findings](docs/google-play-v2-findings.md), then [the source and storage audit](samples/google_play_v2_audit.json).

## What was tested

On September 25, 2026, the collector fetched two pages each for Spotify, Duolingo and Google Maps, exited, and resumed in a new process for two more pages. Two later runs collected the first two pages again, separated by a 30-second interval.

- 24 page requests completed in the network-enabled test: 1,200 record observations, 601 unique reviews.
- All 601 stored reviews matched their latest saved source-record snapshots after normalization.
- SQLite integrity and foreign-key checks passed.
- Resume added later pages; repeating the recent window updated existing records without duplicating them.
- Duolingo's newest returned review was approximately 15 days old despite requesting `NEWEST`. This needs further investigation; successful collection does not establish source freshness or complete coverage.

The database is local and persistent on the machine running the collector. It is shared by all runs using the same database path. No always-on cloud collection service is configured.

## Collect reviews

### One-command refresh

After installing the requirements below, run:

```powershell
.venv\Scripts\python.exe -m review_ingestion.refresh_play --input config/google_play_apps.example.json --db data/google_play_v2.sqlite3 --pages 2 --count 50
```

This collects reviews, creates a separate SQLite snapshot, audits that snapshot, and generates an inspection page with app filtering, text search and 20-row pagination. The command prints the page path. Each refresh gets its own directory in `data/cycles/`; earlier snapshots are preserved. `data/cycles/latest.json` points to the latest refresh result, including failures.

Status is `ready`, `warning` (for example, old review dates), `needs_attention` (collection or storage checks failed), or `failed` (the refresh could not finish). A warning is not a completeness guarantee. Exit code is nonzero for `needs_attention` and `failed`. Failed source requests cannot be reported as success just because older reviews exist. Add `--resume RUN_ID` with the same configuration to retry a checkpoint.

Snapshot directories are local backups on the same disk; they are not off-site disaster recovery. No recurring background task is enabled by this command. Review and remove old snapshots yourself when no longer needed.

### Setup and collection-only command

Use Python 3.11 or newer. Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m review_ingestion.google_play_cli `
  --input config/google_play_apps.example.json `
  --db data/google_play_v2.sqlite3 `
  --report data/latest-run.json `
  --pages 2 --count 50 --delay 2
```

On macOS/Linux, use `.venv/bin/python` and shell-appropriate line continuation. Input uses app IDs such as `com.spotify.music`. `--count` is the requested records per page; `--pages` limits additional pages per app in this invocation. Actual returned counts are recorded. Requests use the configured locale and `NEWEST` sort; locale parameters do not guarantee every review is written in that language.

For repeated collection, append `--runs 3 --interval 60`. Each run starts with recent reviews and writes into the same database. Run and page budgets keep this research test bounded.

## Resume after stopping

The command prints its run ID as soon as the run is saved. Reuse the same input, database, locale and page size, adding `--resume RUN_ID`:

```powershell
.venv\Scripts\python.exe -m review_ingestion.google_play_cli `
  --input config/google_play_apps.example.json `
  --db data/google_play_v2.sqlite3 `
  --report data/resumed-run.json `
  --resume YOUR_RUN_ID --pages 2 --count 50
```

Every committed page saves its reviews, source-record snapshot, observations and next cursor in one transaction. A failed or interrupted request keeps the previous checkpoint. A failed database transaction rolls back the whole page. Another process cannot collect into the same database simultaneously.

Saved cursors may expire or become invalid upstream. A failed resume is reported; it does not silently restart at page one. Start a new run to refresh recent reviews when needed. Source exhaustion, repeated cursors and rejected records stop further requests for that app.

## Inspect and export

```powershell
.venv\Scripts\python.exe -m review_ingestion.audit_play --db data/google_play_v2.sqlite3 --report data/audit.json
.venv\Scripts\python.exe -m review_ingestion.inspect_play --db data/google_play_v2.sqlite3 --output data/inspection
```

Open `data/inspection/index.html` in a browser. It shows counts, app and text filters, and paginated review rows, with links to:

- `reviews.json`: actual normalized review records, including text, rating, timestamps and app IDs;
- `reviews.sqlite3`: a consistent copy of the actual database, ready to open in a SQLite viewer. This is a database file, not a SQL import script.

The exported database also contains page snapshots, attempts and checkpoints. These files stay local and are ignored by Git; published sample reports contain counts and findings, not review text or usernames.

## How the code is organized

| File | Purpose |
| --- | --- |
| `google_play_cli.py` | App list, run limits, repeated runs and resume command |
| `play_pipeline.py` | Per-page transactions, checkpoints, retries and run reports |
| `play_worker.py` | Isolated single-page adapter with HTTPS verification and timeouts |
| `google_play.py` | Review validation and normalization |
| `google_play_storage.py` | Shared app/review tables and deduplicating writes |
| `audit_play.py` | Reconcile snapshots, counts, dates and database records |
| `inspect_play.py` | Readable offline preview, review JSON and database snapshot |

These files are in `review_ingestion/`. The main tables are `apps`, `reviews`, `collection_runs`, `review_observations`, `play_jobs`, `play_pages` and `play_attempts`. The older `collection_run_apps` table is retained for compatibility with the first prototype.

## Limits and source decision

Google Play is promising for a bounded prototype, with freshness still unresolved for one tested app. This short test does not prove long-term availability, expired-token recovery or historical completeness. Empty pages are conservatively flagged for investigation. Rejected rows retain reasons and source snapshots; they are not silently accepted. Ratings are source star scores, not sentiment predictions.

The adapter uses the pinned third-party `google-play-scraper==1.2.7`. Its public `reviews()` helper can swallow request errors; the isolated adapter uses its single-page primitive so those errors remain visible. That private interface is a maintenance risk and must be checked before any dependency upgrade. See [project comparison and design decisions](docs/google-play-v2-findings.md).

The [existing public website](https://product-review-data.review-data-lab.workers.dev/) still demonstrates the historical Amazon prototype. Google Play currently runs through the commands above and has a local inspection page. See [Amazon findings](FINDINGS.md).

## Tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fixtures, including failed requests, timeout handling, transaction rollback, resume, repeated pages, invalid records, duplicate records, concurrent collectors, timestamp conversion and export checks. The dated live reports are in `samples/google_play_v2_*.json`.

Use a fresh `google_play_v2.sqlite3` for this version. The first prototype incorrectly labelled local naive timestamps as UTC. Existing v1 timestamps are not silently rewritten; recollect the relevant records with v2.
