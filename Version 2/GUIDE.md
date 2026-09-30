# Version 2 — Detailed guide

For the current milestone, start with [controlled repeated ingestion](docs/controlled-ingestion.md).
It uses a fixed five-App configuration and reports new, changed, unchanged and
duplicate observations plus source evaluation and storage checks after every round.

Collect a defined list of Google Play apps, save review records into one persistent SQLite database, and resume from the last committed page. This is a bounded research prototype. Amazon work is paused; its code and findings remain as the earlier source-feasibility experiment.

Run the commands below from the **Version 2** directory. The existing virtual environment is one level above it.

## Try the public preview

**[Open App Reviews](https://product-review-data.review-data-lab.workers.dev/)** — no login or local files required. Search the shared library by app name or review text, filter stars/helpful votes, and collect a small sample using a Google Play app link. Reviews are stored in Cloudflare D1. Each public run requests up to 25 reviews per page, with up to three pages and a shared limit of 60 page requests per hour. Scheduled updates are not enabled.

The public preview lives in [web/](web/). Its JavaScript source adapter follows the `google-play-scraper` request format; the research pipeline below still uses the Python package directly. The cloud database was seeded from selected local review fields, excluding author names. It is separate from the local SQLite database; subsequent writes are not automatically synchronized between them. See [deployment and verification](docs/public-preview.md).

## Two stages of the project

| Stage | Where to look | Status |
| --- | --- | --- |
| Amazon feasibility test | [../Version%201/archive/amazon/](../Version%201/archive/amazon/) — original code, website, samples and findings | Preserved; development paused because access varied between runs |
| Google Play collection | [review_ingestion/](review_ingestion/) — current Python workflow using `google-play-scraper` | Active; repeated collection into one SQLite database, with checkpoints and data checks |

**For a quick review:** read [the current findings](docs/google-play-cross-day-findings.md), then try the local panel below. [samples/](samples/) contains Google Play test reports; [tests/](tests/) covers the current pipeline. The [implementation review](docs/implementation-review.md) explains the checks and remaining limits.

## What was tested

On September 27, five more app IDs were tested for one page of 25 reviews each: WhatsApp, Netflix, YouTube, Instagram and Reddit. All five requests and storage checks passed, adding 125 unique records. Combined with the earlier Spotify, Duolingo and Google Maps samples, the database then held 1,048 unique reviews across eight apps. This is one successful sample from the five new apps, not a repeated reliability result for them. Google Maps had 313 stored app reviews. [Aggregate test evidence](samples/google_play_eight_apps_2026-09-27.json) records the counts without publishing review text.

On September 27, another one-page collection across the same three apps was compared with an equal-size sample from about 47 hours earlier. All three requests succeeded; 149 additional unique reviews were stored (773 total). Duolingo returned different IDs but its newest review was still 17 days old. An additional US/GB probe returned identical IDs and did not resolve that freshness question. These are discrete tests, not 47 hours of continuous operation.

On September 25, 2026, the collector fetched two pages each for Spotify, Duolingo and Google Maps, exited, and resumed in a new process for two more pages. Two later runs collected the first two pages again, separated by a 30-second interval.

- 24 page requests completed in the network-enabled test: 1,200 record observations, 601 unique reviews.
- All 601 stored reviews matched their latest saved source-record snapshots after normalization.
- SQLite integrity and foreign-key checks passed.
- Resume added later pages; repeating the recent window updated existing records without duplicating them.
- Duolingo's newest returned review was approximately 15 days old despite requesting `NEWEST`. This needs further investigation; successful collection does not establish source freshness or complete coverage.

The Python collector database is local and persistent on the machine running the collector. It is shared by all runs using the same database path. The public preview has a separate cloud database; neither version schedules automatic collection.

## Collect reviews

### Local control panel

After installing the requirements, start:

```powershell
..\.venv\Scripts\python.exe -m review_ingestion.serve_play
```

Open http://127.0.0.1:8768/. Choose the apps, start collection and browse the saved results. The eight examples are starting points, not an allowlist. To collect another app, paste its Google Play link or app ID and optionally enter a display name. The panel supports 1–5 pages per app and up to five apps; a saved run can continue from its committed cursor using its original settings. Data goes into `data/google_play_v2.sqlite3`, and snapshots are kept in `data/inspection/`.

Searching the results page reads saved records; it does not contact Google Play. An exact saved app name selects that app, while other keywords search review text and partial app names. If an app has not been collected, use **Add another app**, run collection, and open the new result. The old result is a fixed snapshot. Helpful votes are the source's count of people who marked a review helpful; stars are the reviewer's rating of the app.

For a small first test, leave Google Maps selected, keep one page per app, and click **Start collection**. This collects reviews of the Google Maps Android app, not reviews of businesses or places in Maps. Eight verified app IDs are listed as examples; select up to five per run. Open **Browse latest saved data**, choose Google Maps in the app filter, and inspect the rows or download the review JSON or SQLite database. Run the same input again to check repeatability; existing review IDs are updated rather than inserted twice. **Saved checkpoints** lets you continue a run to later pages. Duolingo is also included as a diagnostic case: its returned review dates have been unexpectedly old.

Keep the command running while using the panel. It is local only and does not schedule background collection. An older `python -m http.server` preview must be stopped before using the same port. For the implementation review, source comparisons and remaining limits, see [requirements and validation](docs/implementation-review.md). For tables, export meanings and SQL examples, see [the data contract](docs/google-play-data-contract.md).

### One-command refresh

After installing the requirements below, run:

```powershell
..\.venv\Scripts\python.exe -m review_ingestion.refresh_play --input config/google_play_apps.example.json --db data/google_play_v2.sqlite3 --pages 2 --count 50
```

This collects reviews, creates a separate SQLite snapshot, audits that snapshot, and generates an inspection page with named app tiles, app and review-text search, star-rating and helpful-vote filters, and 20-review pagination. The command prints the page path. Each refresh gets its own directory in `data/inspection/`, shared with the local control panel; earlier snapshots are preserved. `data/inspection/latest.json` points to the latest refresh result, including failures. App icons for the eight examples are cached from their Google Play listings; other apps use an initial until an icon is supplied.

Open `data/inspection/index.html` for refresh history. Each result also includes `evaluation.json`, comparing the actual returned sample with an earlier run using matching settings. Freshness warnings use this run's source snapshots, so previously stored fresh reviews cannot hide a stale response. New IDs in a sample do not necessarily mean newly posted reviews. Older CLI snapshots in `data/cycles/` remain there; use `--output data/cycles` if continuing that separate history.

Status is `ready`, `warning` (for example, old review dates), `needs_attention` (collection or storage checks failed), or `failed` (the refresh could not finish). A warning is not a completeness guarantee. Exit code is nonzero for `needs_attention` and `failed`. Failed source requests cannot be reported as success just because older reviews exist. Add `--resume RUN_ID` with the same configuration to retry a checkpoint.

Snapshot directories are local backups on the same disk; they are not off-site disaster recovery. No recurring background task is enabled by this command. Review and remove old snapshots yourself when no longer needed.

Scheduled collection and a shared database work together: a scheduler would run this refresh command for a chosen app list, merge returned records into the same database, and preserve a report. Searches would read saved data between updates. The schedule and app-selection policy remain open questions; no daily task or all-review backfill is enabled.

### Setup and collection-only command

Use Python 3.11 or newer. Windows PowerShell:

```powershell
python -m venv ../.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m review_ingestion.google_play_cli `
  --input config/google_play_apps.example.json `
  --db data/google_play_v2.sqlite3 `
  --report data/latest-run.json `
  --pages 2 --count 50 --delay 2
```

On macOS/Linux, use `../.venv/bin/python` and shell-appropriate line continuation. Input uses app IDs such as `com.spotify.music`. `--count` is the requested records per page; `--pages` limits additional pages per app in this invocation. Actual returned counts are recorded. Requests use the configured locale and `NEWEST` sort; locale parameters do not guarantee every review is written in that language.

For repeated collection, append `--runs 3 --interval 60`. Each run starts with recent reviews and writes into the same database. Run and page budgets keep this research test bounded.

## Resume after stopping

The command prints its run ID as soon as the run is saved. Reuse the same input, database, locale and page size, adding `--resume RUN_ID`:

```powershell
..\.venv\Scripts\python.exe -m review_ingestion.google_play_cli `
  --input config/google_play_apps.example.json `
  --db data/google_play_v2.sqlite3 `
  --report data/resumed-run.json `
  --resume YOUR_RUN_ID --pages 2 --count 50
```

Every committed page saves its reviews, source-record snapshot, observations and next cursor in one transaction. A failed or interrupted request keeps the previous checkpoint. A failed database transaction rolls back the whole page. Another process cannot collect into the same database simultaneously.

Saved cursors may expire or become invalid upstream. A failed resume is reported; it does not silently restart at page one. Start a new run to refresh recent reviews when needed. Source exhaustion, repeated cursors and rejected records stop further requests for that app.

## Inspect and export

```powershell
..\.venv\Scripts\python.exe -m review_ingestion.audit_play --db data/google_play_v2.sqlite3 --report data/audit.json
..\.venv\Scripts\python.exe -m review_ingestion.inspect_play --db data/google_play_v2.sqlite3 --output data/inspection
```

Open `data/inspection/index.html` in a browser. It shows named apps, text and rating filters, and paginated review cards, with links to:

- `reviews.json`: actual normalized review records, including text, rating, timestamps and app IDs;
- `reviews.sqlite3`: a consistent copy of the actual database, ready to open in a SQLite viewer. This is a database file, not a SQL import script.

The exported database also contains page snapshots, attempts and checkpoints. These files stay local and are ignored by Git; published sample reports contain counts and findings, not review text or usernames.

The local panel at `127.0.0.1` is available only on the computer running it. The [public website](https://product-review-data.review-data-lab.workers.dev/) uses a separate shared cloud database and supports live sample collection. GitHub holds code and aggregate evidence, not the local SQLite database. Neither version has an unattended collection schedule. Review photos and videos are not present in the current review schema; the page does not offer a media filter. Star groups are source ratings, not predicted sentiment.

## How the code is organized

| File | Purpose |
| --- | --- |
| `google_play_cli.py` | App list, run limits, repeated runs and resume command |
| `play_pipeline.py` | Per-page transactions, checkpoints, retries and run reports |
| `play_worker.py` | Isolated single-page adapter with HTTPS verification and timeouts |
| `google_play.py` | Review validation and normalization |
| `google_play_storage.py` | Shared app/review tables and deduplicating writes |
| `audit_play.py` | Reconcile snapshots, counts, dates and database records |
| `evaluate_play.py` | Compare per-run freshness, IDs and edited reviews |
| `refresh_play.py` | Collect, check and preserve results in a local history page |
| `serve_play.py` | Local controls for starting and continuing bounded collection |
| `probe_play.py` | Small locale comparison without changing the main database |
| `inspect_play.py` | Readable offline preview, review JSON and database snapshot |

These files are in `review_ingestion/`. The main tables are `apps`, `reviews`, `collection_runs`, `review_observations`, `play_jobs`, `play_pages` and `play_attempts`. The older `collection_run_apps` table is retained for compatibility with the first prototype.

## Limits and source decision

Google Play is promising for a bounded prototype, with freshness still unresolved for one tested app. This short test does not prove long-term availability, expired-token recovery or historical completeness. Empty pages are conservatively flagged for investigation. Rejected rows retain reasons and source snapshots; they are not silently accepted. Ratings are source star scores, not sentiment predictions.

The adapter uses the pinned third-party `google-play-scraper==1.2.7`. Its public `reviews()` helper can swallow request errors; the isolated adapter uses its single-page primitive so those errors remain visible. That private interface is a maintenance risk and must be checked before any dependency upgrade. See [project comparison and design decisions](docs/google-play-v2-findings.md).

The adapter also validates the pagination response before the upstream parser runs: a missing or malformed continuation field is a source error, not evidence that the review history ended. Unrecognized response shapes require inspection before the adapter is updated.

The [public website](https://product-review-data.review-data-lab.workers.dev/) now runs the Google Play preview with a shared online database. The commands above run the separate local workflow. See the [Amazon archive](../Version%201/archive/amazon/README.md) for the preserved source and findings.

## Tests

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test web/worker.test.mjs
```

Tests use fixtures, including failed requests, timeout handling, transaction rollback, resume, repeated pages, invalid records, duplicate records, concurrent collectors, timestamp conversion and export checks. The dated live reports are in `samples/google_play_v2_*.json`.

Use a fresh `google_play_v2.sqlite3` for this version. The first prototype incorrectly labelled local naive timestamps as UTC. Existing v1 timestamps are not silently rewritten; recollect the relevant records with v2.
