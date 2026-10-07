# Manual multi-day follow-up protocol

John's October 5 follow-up requires source freshness checks and repeated collections over a few days before adding a scheduler. The October 7 experiment is day 1, not completion of this requirement.

## Repeatable procedure

Use the same persistent local database and five-App configuration. Keep English / US, NEWEST, 100 records per page, two pages per App, no automatic retries, 2-second delays and a 20-second timeout. Each day's run has a new report filename; do not overwrite the October 7 report or resume its completed run to represent a new day.

Example for October 8, from Version 2 (planned, not executed):

```powershell
../.venv/Scripts/python.exe -m review_ingestion.google_play_cli --input config/google_play_controlled.json --db data/controlled-2026-09-29.sqlite3 --report samples/google_play_controlled_2026-10-08.json --runs 1 --pages 2 --count 100 --delay 2 --timeout 20 --retries 0
```

Collect on separate actual dates, preferably near the same time. Never change the machine clock, backdate reports or count multiple same-day invocations as multiple days. UTC observation dates are the portable basis of the summary; local calendar dates around midnight can differ.

## Offline comparison

The new tool reads saved report files only, prints JSON, and does not collect, schedule, write to SQLite, or publish. Supply only reports that actually exist:

```powershell
../.venv/Scripts/python.exe -m review_ingestion.summarize_play samples/google_play_controlled_2026-10-07.json
```

Add each later completed report as another argument. A duplicate run ID is rejected, rather than silently counted twice. The tool uses saved sample timestamps, not report-generation time. Runs without timezone-aware timestamps are rejected. Failed runs, missing samples, failed verification and inconsistent accounting do not count toward valid collection days. Protocol differences, including actual page counts, create separate coverage groups.

Each row includes new, repeated, updated, unchanged, stale, latest review date, age and source warnings. Updated is a subset of repeated, not an additional observation. A valid collection day means collection/accounting passed; it does not mean source freshness passed.

See [October 7 summary](../samples/john_multiday_summary_2026-10-07.json) and [store comparison findings](manual-freshness-2026-10-07.md). All five Apps currently have only one valid day in this follow-up. Dates with no experiments are not filled in.

## Store control and interpretation

For Duolingo and controls, open the English / US Google Play listing, select Phone, leave star ratings unfiltered, open all reviews and explicitly select Newest. Record the observed date and whether visible IDs match the collected sample where available. Store UI dates have day precision and signed-in browser context may differ from the collector.

October 7: Duolingo's first three visible IDs match the run and show September 27; Spotify shows October 6. Google Maps' initial UI reads timed out, but a later manual session successfully verified the first five visible dates under Newest as October 6. Both store-page controls now agree at day precision with the collector. These findings do not prove that no newer Duolingo reviews exist elsewhere. Do not claim the freshness issue is fixed or alter source dates to make the data look fresh.

Keep raw review text and the operational database local. Publish aggregate reports and findings only. Do not enable scheduling or send John a completion email until the actual remaining observations and review are done.
