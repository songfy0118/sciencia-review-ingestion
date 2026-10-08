# October 8 manual experiment: day 2

Run `f2010d5a-51ab-4bb0-a0c6-ab732bc951b5`, finished 2026-10-08T05:55:03.496743Z. Local date is October 8 in America/Chicago. Same five Apps, English / US, NEWEST, two pages of 100 records per App, pinned 1.2.7 adapter, no retries, 2-second delay, 20-second timeout. The same local SQLite database was used.

There were ten successful page requests and no failed attempts. No scheduler, D1 synchronization, or email sending was performed.

## Results

| App | New to database | Repeated | Updated subset | Unchanged | Newest returned review UTC | Age days |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| Duolingo | 200 | 0 | 0 | 0 | 2026-10-07T05:39:45Z | 1.01 |
| Google Maps | 122 | 78 | 3 | 75 | 2026-10-07T05:51:45Z | 1 |
| Netflix | 125 | 75 | 0 | 75 | 2026-10-07T05:45:14Z | 1.01 |
| Spotify | 171 | 29 | 3 | 26 | 2026-10-07T05:50:14Z | 1 |
| WhatsApp | 200 | 0 | 0 | 0 | 2026-10-07T05:54:54Z | 1 |
| Total | 818 | 182 | 6 | 176 | | |

All five Apps returned 200 accepted observations each: 1,000 total. New IDs are newly encountered by this database, not necessarily newly posted reviews. Updated is a subset of repeated and includes normalized metadata changes; it is not limited to edited text. Text/rating/reply changes within the shared window were 2 for Spotify and 0 for the other Apps.

Local unique reviews: 5,614 (previously 4,796). Historical page observations: 7,800. Storage integrity is ok, foreign-key issues and snapshot/accounting mismatches are zero. Storage verification and current bounded source checks passed. Seven summary-tool tests passed today; no collector code was changed. These checks do not prove complete source coverage.

## Duolingo follow-up

The newest returned timestamp advanced from September 27 to October 7, and age decreased from 10.68 to 1.01 days. This was observed without changing request parameters or date parsing. It is a recovered freshness signal, not a proven fix or diagnosis.

The [Google Play page](https://play.google.com/store/apps/details?id=com.duolingo&hl=en_US&gl=US) was checked again on October 8 with Phone selected, no star filter and the dialog explicitly sorted by Newest. The first three visible dates were October 7, 2026; all three IDs matched the collected records:

- `3326bf36-8077-4558-9b07-9515bbbf3b8a`: 2026-10-07T05:39:45Z.
- `1f291a32-5988-46f6-8553-48db2530134b`: 2026-10-07T05:08:48Z.
- `b9f55c1d-c158-4c2c-9af0-79285d5166be`: 2026-10-07T04:50:53Z.

The signed-in browser and anonymous collector are not identical contexts; UI dates have day precision. No newer UI-visible reviews missing from the collector were observed in this sample. The reason for the previous lag remains unknown. The store controls Spotify and Maps were verified on October 7, not rechecked on October 8.

## Cross-day limits and next step

All five Apps now have two consecutive UTC observation dates, October 7 and 8, with matching sampling parameters. However, the actual interval was only about **9.21 hours**: the second run occurred just after local midnight. This is not two full 24-hour observation windows and should not be extrapolated into daily ingestion volume or a recommended daily frequency.

Review overlap with yesterday was 78 IDs for Maps, 75 for Netflix, 29 for Spotify and 0 for Duolingo/WhatsApp. Zero overlap under a 200-record cap does not prove missed reviews, but it also cannot establish continuity or complete coverage. Duolingo's advancing head window is not proof that intervening review history was captured.

A further manual run on another actual date, preferably roughly 24 hours after this one, would strengthen the short observation series. October 9 is our proposed next date, not a deadline or date explicitly specified by John. Scheduled collection remains deferred until the results are reviewed.

- [Full collection evidence](../samples/google_play_controlled_2026-10-08.json)
- [Two-day summary](../samples/john_multiday_summary_2026-10-08.json)
- [Day 1 store controls](manual-freshness-2026-10-07.md)
