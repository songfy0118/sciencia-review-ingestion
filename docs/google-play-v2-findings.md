# Google Play: pagination, repeatability and storage review

Test date: September 25, 2026. Scope: John's request for a small repeated-collection test across several apps, organized in the same repository. Amazon development remains paused.

## Source projects reviewed

| Project | Relevant behavior | Decision for this prototype |
| --- | --- | --- |
| [JoMingyu/google-play-scraper](https://github.com/JoMingyu/google-play-scraper) | Python review extraction and continuation tokens; package 1.2.7 is already in use | Keep the existing dependency and its extraction definitions; isolate the single-page adapter |
| [facundoolano/google-play-scraper](https://github.com/facundoolano/google-play-scraper#reviews) | Explicit paginated review responses, locale parameters and throttling; documents that star-rating totals are not written-review totals | Use explicit page budgets and cursor state, pace requests, and avoid promises based on the store's rating count |

The Python project's [issue tracker](https://github.com/JoMingyu/google-play-scraper/issues) also contains rate-limit and locale-related reports. Those are user reports, not proof that every collection fails. Our source decision relies on the local tests below.

No replacement runtime or additional dependency was added. Neither project provides the complete checkpointed database workflow required here, so the application owns that workflow.

## Problems found in version 1

- The continuation-token object can exist while its internal token is `None`. Checking only the object's presence can incorrectly report more pages.
- The installed package's public `reviews()` catches request/parser errors and may return an empty or partial result. That is unsafe evidence for declaring source exhaustion.
- Its timestamp parser uses `datetime.fromtimestamp()`, producing local naive datetimes. Version 1 incorrectly labelled those values UTC instead of converting them.
- The installed request helper changes the process-wide default SSL context and has no explicit network timeout. Version 2 isolates package imports in a child process, restores that default, uses a verified HTTPS context, and enforces socket and process timeouts.
- Version 1 committed only after processing the whole app group and did not persist continuation tokens. A stopped process could lose progress.
- The previous success verdict could rely on reviews already present in the database instead of a useful current result.

Version 2 fetches one page at a time through the package's private single-page primitive, allowing errors to propagate. This interface is pinned to 1.2.7 and documented as a maintenance dependency. A package upgrade needs adapter tests and a new live source check.

## Live experiment

Requested settings: `lang=en`, `country=us`, `NEWEST`, 50 records per page. App IDs: `com.spotify.music`, `com.duolingo`, `com.google.android.apps.maps`. Requests were separated by a two-second delay. There was no application response cache.

| Stage | Pages across 3 apps | Records observed | Unique records in database |
| --- | ---: | ---: | ---: |
| Initial collection: 2 pages per app | 6 | 300 | 300 |
| New process resumes the same run: 2 additional pages per app | 6 | 300 | 600 |
| New run, first 2 pages per app | 6 | 300 | 601 |
| Repeat after a 30-second interval | 6 | 300 | 601 |
| Total | 24 | 1,200 | 601 |

One previously unseen Spotify review appeared in the later recent-window test. The final two comparable runs returned identical ID sets for each app (Jaccard overlap 1.0). Repeated rows updated existing records rather than increasing the unique count.

All network-enabled page attempts succeeded without retry. An earlier sandbox-only attempt was denied by the local network policy; its three errors are retained in the local database and excluded from the source-availability result. No real upstream outage was observed during this test.

Evidence:

- [Initial run](../samples/google_play_v2_initial.json)
- [Same run after a new process resumed it](../samples/google_play_v2_resumed.json)
- [Two later repeated runs](../samples/google_play_v2_repeated.json)
- [Snapshot reconciliation, database checks and freshness audit](../samples/google_play_v2_audit.json)

The audit reconciled all 601 unique database records with their latest normalized source-record snapshots. There were zero snapshot mismatches, page-count discrepancies or foreign-key issues. SQLite integrity was `ok`. This checks preservation of received data; it cannot prove that the source exposed every review.

## Freshness finding

Duolingo's newest returned timestamp was `2026-09-10T20:31:09Z`, approximately 15 days before collection. Google Maps and Spotify had newest returned timestamps on September 24. Although `NEWEST` was requested, we cannot yet establish why Duolingo's response was older. The records also include multiple languages despite the English locale setting.

The audit reports a warning when the newest collected review is over seven days old. This is a diagnostic threshold, not a service guarantee or evidence of an upstream bug. Request locale and source-review language must not be treated as equivalent. Store rating counts also cannot be used as a denominator for written-review completeness.

## Failure and recovery tests

Offline tests cover a failed second page, transient versus non-transient errors, timeout propagation, repeated cursor/no-progress stopping, duplicate IDs, malformed records, mismatched resume configuration, concurrent-writer exclusion and database transaction rollback. The rollback test forces a write failure and verifies that both previously saved records and the old cursor remain intact. A separate test confirms that one failed app does not lose another app's records.

Cross-process resume was tested live. Hard-kill/power-loss behavior and an expired upstream continuation token have not been tested live. Page atomicity is supported by the transaction rollback test, not a claim of an exhaustive crash-recovery certification.

## Current operating model

- Reviews, observations and next cursor commit together after each page.
- Pages and rejection reasons remain in the local database for inspection.
- Network failures preserve the cursor and have bounded retry for transient errors.
- `paused` means the configured page budget was reached and a cursor is saved.
- `source_end` means a nonempty response returned no usable next cursor; it is not a full-history guarantee.
- `failed` means a request failed; `--resume` retries the same checkpoint.
- `stalled` and `quality_error` require inspection before further collection. Saved rows are retained.
- An ambiguous empty response is an error, not silently counted as success.
- SQLite snapshots are actual database files. JSON exports contain normalized reviews, while the run JSON contains operational results.

The inspection page and database are local. The old public Amazon demo is unchanged. There is no persistent cloud service or scheduled unattended collector yet; `--runs` and `--interval` provide finite repeated tests.

## Recommendation

Continue with Google Play for bounded ingestion experiments. The collection/storage mechanics now support controlled pagination and process restart, but source freshness needs further checking. The next evaluation should repeat across several days and investigate Duolingo's date range before adopting this source for an always-on pipeline. Do not claim full coverage or production reliability from this test.

The original [v1 report](google-play-findings.md) is retained as historical evidence; its token and timezone claims are superseded by this review. Start v2 with a fresh database rather than silently interpreting v1 dates as corrected.
