# October 19: cross-day catch-up and re-dated ID guard

## Outcome

After the October 16 validation, the same experiment database was tested again on October 19 across Duolingo, Google Maps and Spotify. All three reached a qualified existing-ID boundary under the revised rule. **58 successful requests**, no failures or retries, stayed within the approved **70-request** total.

The cross-day test found a real flaw in stopping at any known ID: a stored Duolingo review previously dated **October 13 at 11:07:09 UTC** returned dated **October 18 at 14:01:56 UTC**. It appeared in page 3 while the previous run's newest review was dated October 15. Thus an already stored ID can move into the new head; that ID alone is not reliable evidence that the interval has been traversed. Who changed it and the source's exact date semantics were not established.

## Fix

A known ID qualifies as a stopping boundary only if its normalized returned review timestamp matches its frozen pre-run timestamp. Date-changed known IDs still update the stored review, but no longer stop paging.

- Reconstruct baseline dates from immutable accepted page snapshots before the original boundary's run start, not from the already-updated current reviews table.
- For an inherited unresolved target, follow its original lineage rather than using dates from the intervening partial head.
- Use the same normalizer and first-valid-per-page deduplication as ingestion. A duplicate raw entry cannot manufacture a stable boundary.
- Retain caps, continuation cursors, transaction behavior and explicit cap-extension approval. No schema migration or new dependency was required.
- Report known IDs separately from qualified boundary IDs, nonqualifying known IDs and available baseline dates. The rule is tagged `known_id_with_stable_review_timestamp_v1`.
- Group this rule separately from `known_id_v1` in offline summaries. Old and new stopping criteria must not be treated as equivalent protocol evidence.

## Budget and execution

Initial permission: Duolingo at most 50 pages, Maps and Spotify at most 10 each; 100 records per page, 2-second delay, 20-second timeout, zero retries. Existing October 16 experiment copy only. New run IDs were created for this actual date.

The first ID-only snapshots stopped at Duolingo page 3, Maps page 1 and Spotify page 10; each stopping ID had a changed date and no qualified timestamp match. Those snapshots are preserved as superseded results, not current successful quality claims.

The runs were resumed from their saved cursors with the new rule. Duolingo completed at page 30. The user then explicitly reassigned its unused 20-page allocation to Spotify, raising Spotify's cap from 10 to 30 while keeping the overall 70-request total. Maps had already completed at page 10 and made no request during Spotify's extension. The shared controls run's metadata shows cap 30 after extension, but Maps' approved and actual count remained ten.

No earlier pages were refetched during the resumes or cap extension. No fresh duplicate run was created to reset the boundary or cap.

## Final counts

| App | Pages | New database IDs | Repeated | Updated subset | Qualified boundary IDs | Known IDs with changed dates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Duolingo | 30 | 2904 | 96 | 10 | 92 | 4 |
| Google Maps | 10 | 930 | 70 | 30 | 62 | 8 |
| Spotify | 18 | 1751 | 49 | 3 | 46 | 3 |
| Total | 58 | 5585 | 215 | 43 | 200 | 15 |

5,800 accepted observations; zero rejected records, within-page duplicates or cross-page duplicates. Updated is a subset of repeated. The experiment copy grew from **12,801 to 18,386** unique reviews; the original database remains **7,608**. Database duplicate keys: zero.

The initial ID-only snapshots had inserted 1,397 new IDs. Continuing behind their premature stopping positions found **4,188 additional previously unseen IDs**: 2,605 Duolingo, 831 Maps and 752 Spotify. This is concrete evidence that the original stop positions were insufficient; it is not a global source-completeness measurement.

All Apps' newest returned dates were October 18. Intervals since each App's preceding actual observation were about **66.42 hours** for Duolingo, **67.70** for Maps and **67.71** for Spotify. This is separated-day evidence, not fixed-daily testing.

## Verification

- **122 offline tests passed** on October 19 after the final code change.
- Five added regression tests cover re-dated known IDs, immutable-date recovery on resume, duplicate raw entries, inherited original dates and protocol grouping.
- Both final logical runs: bounded_success, verification passed, bounded_checks_passed. Source evaluations reported no timestamp-order or freshness warnings.
- Audits: integrity ok, zero foreign-key issues, zero snapshot mismatches and no accounting issues.
- Latest per-App persisted source assessments for all three Apps are bounded_checks_passed.

To reproduce the final offline summary:

```powershell
../.venv/Scripts/python.exe -m review_ingestion.summarize_play samples/google_play_duolingo_extended_2026-10-16.json samples/google_play_duolingo_repeat_2026-10-16.json samples/google_play_duolingo_crossday_verified_2026-10-19.json samples/google_play_controls_crossday_completed_2026-10-19.json
```

Do not also include earlier snapshots of these same October 19 run IDs; they are not independent runs or extra experiment days.

## Saved evidence

- [Initial Duolingo ID-only snapshot - superseded](../samples/google_play_duolingo_crossday_2026-10-19.json)
- [Initial controls ID-only snapshot - superseded](../samples/google_play_controls_crossday_2026-10-19.json)
- [Final Duolingo stable-date report](../samples/google_play_duolingo_crossday_verified_2026-10-19.json)
- [Intermediate controls report at ten-page cap - superseded](../samples/google_play_controls_crossday_verified_2026-10-19.json)
- [Final controls report after approved Spotify extension](../samples/google_play_controls_crossday_completed_2026-10-19.json)
- [Current cross-day summary](../samples/john_catchup_crossday_2026-10-19.json)

The historical October 16 artifacts are retained unchanged; their ID-only stopping evidence must be read with the newly demonstrated limitation.

## Remaining limits

The known-ID rule is now more conservative, but matching one unchanged timestamp is still a heuristic. Pinned/reordered records, unstable source windows, upstream omissions and pre-existing historical gaps are not ruled out. Original/frozen dates can only be recovered where accepted source snapshots exist; unknown dates do not qualify.

No claim of complete Google Play history or zero global missed reviews is made. New means new to this database, not necessarily newly posted between collections. This controlled experiment does not choose a production polling frequency. No new store-browser comparison, scheduler, cloud database sync or email action was performed.
