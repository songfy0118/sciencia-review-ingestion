# Manual public data sync: October 3, 2026

Status: prepared, not uploaded. The user requested synchronizing the local
experiment data to the existing public preview. The public D1 database and local
SQLite database remain separate; no automatic schedule was enabled.

The existing Cloudflare management login is unavailable on this computer.
The public read/collect API does not grant bulk import or administrative access.
The Cloudflare login page has been opened for the user; do not create a replacement
account/database or collect credentials in chat to work around this blocker.

## Prepared and verified

`web/seed.py` now supports explicit source/destination arguments. It exports only
the existing public review schema: App ID, label, review ID, text, score, helpful
vote count, dates, app version and developer reply. Reviewer names, avatars,
raw pages, local logs and credentials are not exported or committed to GitHub.

Reviews are merged by `(app_id, review_id)`. Local records update existing cloud
records only when their collection timestamp is newer. Cloud-only and newer
cloud records remain intact. Repeating the same import does not add duplicates.

The real local database audit passed. Its public projection contains 3,798 reviews;
loading the generated SQL twice into a temporary SQLite database using the public
schema still produced 3,798 reviews with zero foreign-key violations. This is an
offline schema/merge test, not a D1 import. All 83 Python tests passed, including
privacy-field exclusion, merge behavior and destination-file protection.

Aggregate evidence: [preparation report](../samples/google_play_sync_preparation_2026-10-03.json).
The generated 2.8 MB SQL stays in ignored `data/deployment/sync-2026-10-03.sql`.

## Finish after management access is restored

Use the existing `app-review-data` D1 binding in `web/wrangler.jsonc`. First obtain
a recoverable cloud backup and check current counts/locks. Import into this
database, not a new one. Preserve existing online rows and source timestamps.
Then verify all projected IDs and expected retained values, run public search
checks for the five Apps, and record actual added/updated/retained counts. Do not
call the synchronization complete from local export success alone.

The website's historical online count was 1,267. The merged total cannot be
calculated by adding 1,267 and 3,798: shared IDs reduce the total, and newer cloud
rows must be preserved. Determine the actual count after import.

3,798 unique reviews across five Apps is enough for the requested controlled
ingestion experiment. It is not evidence of complete App histories or sufficient
coverage for a future model. Duolingo freshness and bounded-window warnings remain
valid after synchronization; uploading data does not make it newer or more complete.

```powershell
../.venv/Scripts/python.exe web/seed.py --source data/controlled-2026-09-29.sqlite3 --destination data/deployment/sync-2026-10-03.sql
```

Cloud import requires authenticated administration. No dependency installation,
credential creation, cloud write or new source collection occurred in this pass.
