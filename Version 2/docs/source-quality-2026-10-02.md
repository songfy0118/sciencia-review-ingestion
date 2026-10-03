# Source quality and bounded catch-up: October 2, 2026

Dates in this title use America/Chicago. Network observations occurred shortly
after midnight October 3 UTC. This is a manual experiment, not scheduled collection.

## Implemented changes

The collector now supports --overlap-run: start from the current recent page,
continue until an ID from a matching baseline run is observed, or stop at the
configured page budget. Baselines must match locale, page size, adapter and sort,
and contain successful observations for every requested App. Resume preserves
the same baseline. Newest-date regression is checked against that baseline even
when adaptive collection makes the page counts unequal.

The CLI separately reports collection, storage verification and source quality.
Missing overlap or freshness warnings set source_quality_status to needs_attention
and produce a nonzero exit, even if every page was stored successfully. Per-App
evidence is stored in play_source_assessments in the main database, so downstream
processes do not need to infer quality from a separate downloaded report.

Source epochs are converted directly to timezone-aware UTC, avoiding a naive
local-time round trip. The diagnostic probe also records response Date, Age,
requested sort and adjacent timestamp ordering. It does not collect cookies or
credentials. These changes cannot force Google Play to publish fresher results.

## Live results

Baseline: September 30 run d212805c-fa96-4540-b2b3-d415098bdb19. Budget: five Apps,
at most five pages of 100 each, with no retries. Eighteen requests were needed.

| App | Pages | Returned | New to DB | Changed existing | Shared IDs with baseline | Assessment |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Duolingo | 1 | 100 | 99 | 0 | 1 | Needs attention: stale/backwards source dates |
| Google Maps | 2 | 200 | 198 | 2 | 2 | Bounded checks passed |
| Netflix | 5 | 500 | 500 | 0 | 0 | Needs attention: budget reached without overlap |
| Spotify | 5 | 500 | 499 | 1 | 0 | Needs attention: budget reached without overlap |
| WhatsApp | 5 | 500 | 500 | 0 | 0 | Needs attention: budget reached without overlap |

The main database increased from 2,002 to 3,798 unique reviews. This collection
observed 1,800 records, including 1,796 newly observed IDs, three changed existing
records and one unchanged existing record. Updates count any normalized field;
they are not necessarily edits to review text. Storage audit passed across all
58 committed pages. No source or storage failure occurred in this live run.

Evidence: [catch-up report](../samples/google_play_catchup_2026-10-02.json).
The new baseline-date diagnostic and database quality entries were added after
collection from saved snapshots, without additional source requests.

## Freshness diagnosis

The separate [US/GB Duolingo probe](../samples/google_play_freshness_probe_2026-10-02.json)
made two requests of 50 reviews each. Both returned the same IDs and newest
timestamp, September 22 at 03:47:09 UTC, about 11 days old. No adjacent date
inversions were observed in either page. Source HTTP Date and local receipt time
were within seconds, and the configured sort value was NEWEST (2). A separate
Google Play HEAD request also had a matching server clock.

These observations do not identify why the upstream window is stale. They do
not establish that no fresher reviews exist. The other four Apps still returned
newest timestamps about one day old. No artificial date offset was applied.

Seeing baseline IDs only establishes observed overlap, not complete coverage:
ordering changes, edits, source filtering and hidden reviews can still leave
gaps. gap_risk=false means the specific missing-overlap condition was not detected.
All reports retain complete_coverage=false. The three budget-limited Apps need
a shorter manual interval or a separately bounded continuation experiment before
choosing an eventual schedule. No broader crawl or unattended scheduler was added.

## Run and inspect

```powershell
../.venv/Scripts/python.exe -m review_ingestion.google_play_cli --input config/google_play_controlled.json --db data/google_play.sqlite3 --report data/catchup.json --overlap-run BASELINE_RUN_ID --count 100 --pages 5 --delay 2 --retries 0
```

Use the database that contains BASELINE_RUN_ID. The live experiment used the
existing data/controlled-2026-09-29.sqlite3. --pages is an additional-page budget
per invocation, including resume; it is not an unlimited backfill.

Read current quality using collection time rather than assessment time, since
older runs may be re-evaluated later:

```sql
WITH latest AS (
  SELECT j.run_id,j.app_id,
         ROW_NUMBER() OVER (PARTITION BY j.app_id ORDER BY r.started_at DESC,r.rowid DESC) AS rank
  FROM play_jobs j JOIN collection_runs r USING(run_id)
)
SELECT l.app_id,COALESCE(a.status,'unassessed') AS quality,a.report_json
FROM latest l LEFT JOIN play_source_assessments a USING(run_id,app_id)
WHERE l.rank=1;
```

Unassessed is not a passing quality result. bounded_checks_passed is not a source
freshness SLA or a coverage guarantee. Public D1 remains separate from this local
SQLite experiment. Sixty-seven Python tests passed, covering bounded overlap, resume,
budget exhaustion, incompatible baselines, UTC timestamps and assessment storage.
