# October 12 bounded manual observation

Run `199164ef-4741-4db4-a698-dd0afeaf1ffb`, finished 2026-10-12T23:19:14.556521Z (October 12, America/Chicago). Same persistent local SQLite database, five Apps, en/US, NEWEST, pinned google-play-scraper 1.2.7, strict single-page adapter, two pages of 100 per App, delay 2 seconds, timeout 20 seconds, no retries. User approved this one bounded round. No scheduler, cloud database sync or email sending.

## Results

| App | New database IDs | Repeated | Updated subset | Latest returned UTC | Shared IDs vs October 10 |
| --- | ---: | ---: | ---: | --- | ---: |
| Duolingo | 200 | 0 | 0 | 2026-10-11T23:15:16Z | 0 |
| Google Maps | 199 | 1 | 1 | 2026-10-11T23:18:09Z | 1 |
| Netflix | 199 | 1 | 1 | 2026-10-11T23:16:43Z | 0 |
| Spotify | 200 | 0 | 0 | 2026-10-11T23:14:09Z | 0 |
| WhatsApp | 200 | 0 | 0 | 2026-10-11T23:18:16Z | 0 |
| Total | 998 | 2 | 2 | | 1 |

Accepted observations: 1,000; rejected: 0. Ten successful page attempts, zero failures, no automatic retries. Local unique reviews increased from 6,610 to 7,608; historical observations total 9,800. Updated is a subset of repeated, not an additional count.

The Netflix repeated ID was already in the database but absent from the preceding bounded window, so whole-database repeated counts and window overlap differ. New IDs are new to this database, not necessarily newly posted reviews.

## Verification

Run status bounded_success; verification passed; current bounded source checks passed. SQLite integrity ok, foreign-key issues 0, snapshot mismatches 0, accounting issues 0. No code or dependency changes. The 100 offline tests were already rerun and passed earlier on October 12.

The enhanced offline summary adds zero-overlap warnings for Duolingo, Netflix, Spotify and WhatsApp, separate from successful storage and freshness checks. A passing bounded source check is not evidence of source completeness.

## Freshness and limitations

All five Apps returned a newest review dated October 11, about one day before collection. Duolingo's newest timestamps in the recent series advanced from September 27 to October 7, October 9 and October 11. Its previous old-date symptom has not recurred in the last three runs. Since controls have a similar newest-date age today, this run does not show a Duolingo-specific lag.

This is collector evidence only: no new Google Play browser/store comparison was performed on October 12. The latest direct Duolingo store check remains October 10. The exact cause of the original delay, and whether newer reviews exist outside this request context, remain unknown.

Valid UTC observation dates are October 7, 8, 10 and 12. Intervals are 9.21, 48.79 and 64.61 hours; October 9 and 11 have no observations in this series. This is not fixed-daily or consecutive-four-day testing. Do not backfill missing experiments.

The 200-review cap and minimal overlap still cannot establish complete coverage or select a production collection frequency. The requested multiday counts and newest-timestamp tracking have been performed; findings are suitable for a progress discussion. Scheduler remains deferred.

- [Collection and audit](../samples/google_play_controlled_2026-10-12.json)
- [Four-date enhanced summary](../samples/john_multiday_quality_2026-10-12.json)
- [Previous store comparison](manual-freshness-2026-10-10.md)
