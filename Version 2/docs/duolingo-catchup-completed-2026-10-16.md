# Duolingo catch-up closure - October 16

Historical result: the [October 19 cross-day test](crossday-catchup-2026-10-19.md)
subsequently exposed premature ID-only stops for date-changed reviews. The current
collector requires an unchanged frozen review timestamp as well as a known ID.
Read the counts below as the October 16 experiment, not the latest stopping guarantee.

## Outcome

The previously unresolved Duolingo target was reached on **page 42**, below the explicitly extended **50-page** total cap. The boundary page contains **32 IDs from the original frozen target**. The workflow stopped without requesting page 43.

A subsequent fresh catch-up run stopped after **one page**, capturing **28 previously unseen database IDs** and revisiting 72 existing IDs without adding duplicate rows. This verifies the tested stopping behavior, not complete Google Play history or a chosen daily frequency.

## What changed

Added `--extend-max-pages` for an explicitly approved catch-up resume. It requires `--resume`, `--catch-up` and a higher `--max-pages`; ordinary resume still cannot raise its own cap.

- Preserve the same run ID, frozen baseline, inherited-target lineage and saved cursor. Start at page 11 instead of rereading the first 1,000 records.
- Validate that App list, locale, sort, adapter and page size are unchanged. Only the total page cap may increase through this explicit option, still within 1..100.
- Save previous/new limits and extension time in `limit_extensions`, and invalidate old quality assessments atomically before another request.
- Retain the extension history in subsequent reports and ordinary resumes. No scheduler or automatic budget increase was added.

The frozen target remains the October 16 first catch-up run's pre-existing Duolingo IDs, not the newly saved partial head. This is why reaching page 42 closes the earlier target rather than merely recognizing the recent 1,000-record sample.

## Live result

Only the existing experiment copy `data/catchup-validation-2026-10-16.sqlite3` changed. The original database remains at **7,608** unique reviews. User authorized an appropriate cap increase; this follow-up used 33 new requests, no retries or failures, within the announced 40-new-request ceiling.

| Phase | New page requests | Accepted observations | New database IDs | Repeated observations | Updated subset |
| --- | ---: | ---: | ---: | ---: | ---: |
| Resume Duolingo pages 11-42 | 32 | 3200 | 3167 | 33 | 3 |
| Fresh Duolingo boundary check | 1 | 100 | 28 | 72 | 0 |
| This follow-up total | 33 | 3300 | 3195 | 105 | 3 |

The 33 repeated observations during resume include 32 original target IDs and one other ID already in the accumulated database. Whole-database repeat counts and frozen-target boundary counts intentionally differ. Updated is a subset of repeated, not an additional record.

Maps and Spotify were present in the resumed run's configuration for compatibility, but their previously resolved jobs made **zero new requests**. Their old observation timestamps and one-page results are retained; they were not recollected during this follow-up.

The experiment copy increased from **9,606 to 12,773** unique reviews during resume, then to **12,801** after the fresh check. Combined with the earlier separately authorized 32-request experiment, all October 16 catch-up validation used 65 requests. The new authorization covers this follow-up; it is not presented as part of the earlier 60-request ceiling.

## Verification

- **117 offline tests passed**, including three new cases for explicit extension, forbidden configuration changes/shrinking, CLI persistence, cursor continuity and quality invalidation.
- Both live follow-up invocations exited successfully with `bounded_success`, verification `passed` and `bounded_checks_passed`.
- Both audits: integrity ok, foreign-key issues 0, snapshot mismatches 0, no accounting issues. No rejected records or within-/cross-page duplicates were reported.
- No adjacent timestamp inversions were reported in the completed Duolingo run.
- The first two historical JSON snapshots remain unchanged. The extended report uses the same run ID as the old round-2 report and contains cumulative totals, not just the 32 added pages.

Do not sum the pre-extension round-2 report and the extended report as separate runs. The summary command correctly rejects duplicate run IDs; use the current snapshot instead:

```powershell
../.venv/Scripts/python.exe -m review_ingestion.summarize_play samples/google_play_catchup_2026-10-16.json samples/google_play_duolingo_extended_2026-10-16.json samples/google_play_duolingo_repeat_2026-10-16.json
```

## Reproduce an explicitly authorized extension

Historical command used for this follow-up (do not rerun it as a new experiment):

```powershell
../.venv/Scripts/python.exe -m review_ingestion.google_play_cli --input config/google_play_catchup_validation.json --db data/catchup-validation-2026-10-16.sqlite3 --report samples/google_play_duolingo_extended_2026-10-16.json --resume 160d6290-24e3-4861-8c1a-43022fabb774 --runs 1 --catch-up --extend-max-pages --max-pages 50 --pages 40 --count 100 --delay 2 --timeout 20 --retries 0
```

For future use, select the actual pending run and a fresh report filename; obtain an explicit budget before enabling extension. A cursor can expire upstream; an error must remain visible rather than be reinterpreted as source exhaustion or a known-ID boundary.

## Remaining boundary

The formerly capped target is now resolved under the known-ID stopping rule. It is reasonable to report this implementation and test result to John when the user approves communication. No email was sent or modified.

This does not prove there are no upstream omissions, reordered/pinned records or legacy gaps. New means new to this database, not necessarily posted between requests. Same-day repeated checks do not determine a production polling interval. Scheduler, website, cloud database sync and operational-database promotion remain unchanged.

- [Completed cumulative report](../samples/google_play_duolingo_extended_2026-10-16.json)
- [Fresh one-page check](../samples/google_play_duolingo_repeat_2026-10-16.json)
- [Current catch-up summary](../samples/john_catchup_completed_2026-10-16.json)
- [Earlier capped experiment](incremental-catchup-2026-10-16.md)
