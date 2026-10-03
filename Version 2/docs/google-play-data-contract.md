# Google Play data contract

The authoritative local store is the SQLite database passed as `--db`. Every successful page is cleaned and loaded automatically. Exporting or importing a file is not a required collection step.

| Table | Purpose | Key |
| --- | --- | --- |
| `apps` | App ID, configured label and source link | `app_id` |
| `reviews` | Latest observed review text, stars, timestamps and available metadata | `(app_id, review_id)` |
| `collection_runs` | Original request settings and run report | `run_id` |
| `review_observations` | Which review IDs appeared in each run | `(run_id, app_id, review_id)` |
| `play_jobs` | Per-app saved cursor, page count and status | `(run_id, app_id)` |
| `play_pages` | Original adapter records, rejection reasons and counts | `(run_id, app_id, page)` |
| `play_attempts` | Successful and failed request attempts | `id` |
| `play_page_changes` | Changed, unchanged, stale and cross-page overlap counts, committed with the page | `(run_id, app_id, page)` |
| `play_storage_failures` | Database page failures retained after successful resume | `id` |
| `play_source_assessments` | Per-App freshness and overlap evidence for downstream checks | `(run_id, app_id)` |
| `play_page_transport` | HTTP Date/Age, receipt time and sort metadata committed atomically with new pages | `(run_id, app_id, page)` |
| `latest_play_source_quality` | View of latest per-App collection and assessment state | `app_id` |

Each review has an app ID, review ID, nonempty original-language content, integer score from 1 to 5, review timestamp, source URL and first/last collection timestamps. Optional developer replies and app versions use null when unavailable. Author names are display names, not verified user identities. The current collector uses configured app labels; title/developer/genre are not independently verified app metadata. See `google_play.py` and `google_play_storage.py` for exact fields.

Timestamps are ISO 8601 UTC. Text is Unicode-normalized and stripped of null characters and surrounding whitespace. Missing or invalid required fields cause a recorded rejection and a quality warning; the raw page record remains available. A future review date or old newest-review date triggers evaluation warnings rather than fabricated replacement values.

`reviews.json` contains normalized review records. `reviews.sqlite3` is an actual database backup, including operational tables. `run.json`, `audit.json`, `evaluation.json` and `health.json` are reports, not review datasets. They answer different questions and are labeled separately in the result page.

Example read-only checks in any SQLite viewer:

```sql
-- Collected sample size per app, not the store's total review count.
SELECT app_id, count(*) AS stored_reviews, max(review_at) AS newest_review
FROM reviews GROUP BY app_id;

-- Original stars and text for inspection; no sentiment classification.
SELECT review_at, score, content, review_id
FROM reviews WHERE app_id = 'com.spotify.music'
ORDER BY review_at DESC LIMIT 20;

-- Rejected rows that need inspection.
SELECT run_id, app_id, page, rejected, rejects_json
FROM play_pages WHERE rejected > 0;

PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Source snapshots contain author metadata as returned upstream. Generated datasets stay local and are ignored by Git; public evidence reports contain aggregate results. A deployment would need its own access, retention, backup and database migration decisions.

For downstream quality gating, query `latest_play_source_quality`. A resumed run
invalidates its previous assessment before fetching. `unassessed` and
`needs_attention` are not passing results. Verification uses consistent read
transactions; publishing assessments rejects a run changed during verification.
Historical pages without transport rows remain explicitly unrecorded, not
retroactively verified. `collection_runs.report_json` retains the collector
summary; post-collection quality evidence is in `play_source_assessments`.
