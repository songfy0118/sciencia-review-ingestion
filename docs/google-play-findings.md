# Google Play Repeatability Findings

> Historical v1 test. The [v2 review](google-play-v2-findings.md) supersedes the continuation-token and timezone assumptions below and adds real pagination, restart/resume tests, and a freshness limitation. The old JSON report is retained unchanged as the original experiment record.

**Test date:** September 25, 2026

## Question

Can Google Play provide a more repeatable live review source than the anonymous Amazon HTML workflow, and can repeated collections be stored automatically in one centralized database?

## Test design

The pipeline collected the 50 newest US-English reviews for three apps in three consecutive runs, with a two-second delay between runs.

| App | Google Play app ID |
| --- | --- |
| Spotify | `com.spotify.music` |
| Duolingo | `com.duolingo` |
| Google Maps | `com.google.android.apps.maps` |

All runs used the same app list, locale, sort order, and requested count. Reviews were keyed by app ID and source review ID. The pipeline inserted new reviews, updated existing reviews, and recorded a separate observation for every review seen in every run.

## Observed result

| Check | Result |
| --- | --- |
| Successful app collections | 9 of 9 |
| Records returned per app and run | 50 of 50 |
| Invalid records skipped | 0 |
| Unique reviews in the database | 150 |
| Per-run review observations | 450 |
| Overlap in runs 2 and 3 | 100% for every app |
| More results detected | Yes, for every app and run |
| SQLite integrity check | `ok` |
| Foreign-key issues | 0 |

The complete per-run result is saved in `samples/google_play_repeatability.json`.

## What worked

- The same bounded request completed reliably across several apps and repeated runs.
- Stable review IDs allowed the database to update repeated records without duplicating them.
- App data, normalized review records, run status, and per-run observations were written automatically into one SQLite database.
- The report records received, new, repeated, and skipped counts for each app and run.
- Continuation tokens showed that controlled pagination is possible.

## Limitations

- `google-play-scraper` is a third-party package, not an official Google review API.
- This was a short test with three apps and 50 reviews per app. It demonstrates repeatability for a bounded recent-review window, not complete historical coverage.
- Results may differ with language, country, sorting, or the time of collection.
- The live response format may change and should be checked by scheduled tests.
- Continuation tokens are currently detected but are not yet persisted as durable checkpoints. A long collection cannot yet resume from its last completed page after interruption.

## Recommendation

Google Play is suitable for the next prototype stage. The next work should add persistent pagination checkpoints, resume support, and a scheduled longer-running test before claiming production reliability or complete review coverage.
