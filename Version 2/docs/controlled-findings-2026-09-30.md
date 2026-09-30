# Cross-date ingestion findings: September 30, 2026

This manual collection used the same five Apps, en/us locale, NEWEST sort and
two pages of 100 requested reviews per App as September 29. It wrote into the
same local SQLite database. Samples were about 23.73 hours apart; this is a
cross-date comparison, not a full 24-hour measurement or a scheduled job.

Evidence: [collection and audit](../samples/google_play_controlled_2026-09-30.json),
[subsequent source evaluation](../samples/google_play_cross_day_evaluation_2026-09-30.json).
The latter re-evaluates saved snapshots with the added ordering diagnostic;
it does not represent another network collection.

| App | Returned | New to database | Existing unchanged | Latest returned UTC | Age at collection |
| --- | ---: | ---: | ---: | --- | ---: |
| Duolingo | 200 | 199 | 1 | Sep 22 04:11:31 | 8.72 days |
| Google Maps | 200 | 200 | 0 | Sep 29 21:24:13 | 1.00 days |
| Netflix | 200 | 200 | 0 | Sep 29 21:15:50 | 1.01 days |
| Spotify | 200 | 200 | 0 | Sep 29 21:20:31 | 1.00 days |
| WhatsApp | 200 | 200 | 0 | Sep 29 21:25:28 | 1.00 days |

Ten page requests succeeded. No source or storage failures, rejected rows,
within-page duplicates, cross-page duplicates or changed existing reviews were
observed. The database increased from 1,003 to 2,002 unique reviews. Integrity,
foreign keys and source-snapshot reconciliation passed across all 40 saved pages.

New to database means a previously unobserved ID. These counts are not daily
posting rates. The four non-Duolingo windows had zero shared IDs with the preceding
round; Duolingo shared one. A finite recent window can miss reviews that arrive
and leave between collection runs; zero overlap cannot establish complete coverage.

Duolingo's newest returned timestamp moved backwards by 2,492 seconds (41 minutes
32 seconds), from Sep 22 04:53:03 to Sep 22 04:11:31, despite matching NEWEST
settings. Its 199 different IDs therefore do not demonstrate improved freshness.
The cause is unresolved. The other Apps still returned newest dates about one day
behind collection time; this also needs source investigation before choosing a
production freshness promise.

## Next decision

Keep this as a bounded App-review ingestion prototype. Use Duolingo as a source
diagnostic rather than assume all NEWEST responses are fresh. The new evaluation
reports shared IDs, the previous newest timestamp and its change, and explicitly
warns when the newest timestamp moves backwards. 58 Python tests passed, including
a regression demonstrating that different IDs must not conceal that warning.

The evidence is sufficient to show working local repeated loading across two dates.
It is not sufficient to choose a daily schedule, claim full coverage or establish
Cloudflare D1 reliability. Cloud and local databases remain separate. No scheduler
or model training was added.

## Delivery checks

The CLI rejects input, database and report paths that point to the same file,
preventing an accidental report export from overwriting the database or App list.
Incomplete or failed current windows retain warnings and are excluded from overlap
comparison. The final Python suite contains 60 passing tests. These additional
checks were offline; the live collection counts above are unchanged.
