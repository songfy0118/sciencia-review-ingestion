# October 16: bounded incremental catch-up

October 19 update: ID-only stopping can be premature when a known review returns
with a changed date. The [cross-day fix and results](crossday-catchup-2026-10-19.md)
supersede the boundary rule described in this historical report.

Follow-up: the initially capped Duolingo target was subsequently reached on page 42
after an explicitly authorized cap extension. See the [closure report and latest tests](duolingo-catchup-completed-2026-10-16.md).
The live tables and 114-test result below preserve the initial experiment; they are not the latest state.

## Requirement and implementation

John's October 16 reply asks for recurring collection that pages backward until an already stored review ID is reached, subject to a page or record cap, followed by multi-App tests for missed reviews, duplicates and excessive old-data retrieval. Scheduler remains deferred. No deadline was stated.

The Python workflow now offers `--catch-up --max-pages N`. The historical fixed-window mode and explicit `--overlap-run` experiment remain available; the public website and local UI are not converted into recurring collectors.

- At a new run's start, freeze existing review IDs for each App in `play_catchup_baseline`, in the same transaction as job creation. This is database-wide per App, not limited to a manually chosen previous run.
- Fetch NEWEST pages and save the entire boundary page, including any new IDs after the first known ID. Do not request another page once a pre-run ID is observed. This avoids discarding new reviews on a mixed page.
- The database primary key and upsert path prevent duplicate rows and preserve field updates. Page snapshots, observations and cursor changes remain atomic.
- The page cap is total per App per run, including resumes. With page size 100 and a 10-page cap, each App can commit at most 1,000 returned records; oversized responses are rejected. Retries are separately bounded; the validation used zero.
- Ordinary resume retains its existing total cap and configuration. A subsequently added explicit `--extend-max-pages` option permits a higher authorized cap while preserving cursor and baseline; it logs the limit change. See the closure report for its guards and tests.
- A fresh catch-up run inherits the frozen target of the latest unresolved catch-up for each App. Partial data from a capped or failed attempt must not become a misleading new stopping boundary. `inherited_from_run` makes this visible.
- Reports distinguish `known_id_reached`, `source_end`, `page_limit`, `invocation_limit` and failures. An unresolved boundary sets `gap_risk=true`, source quality needs_attention and a nonzero CLI exit, even if all writes pass verification.
- Summary reporting separates catch-up/max-page protocols from historical fixed windows and retains unresolved-boundary warnings.

No dependencies were added. Two additive SQLite tables are created when the pipeline starts; existing records are not rewritten. Frozen baseline IDs consume local storage proportional to the existing App IDs per catch-up run; retention/compaction is not implemented in this prototype.

## Running and resuming

From Version 2, using the existing environment:

```powershell
../.venv/Scripts/python.exe -m review_ingestion.google_play_cli --input config/google_play_catchup_validation.json --db data/YOUR_EXPERIMENT.sqlite3 --report samples/YOUR_NEW_REPORT.json --catch-up --max-pages 10 --count 100 --delay 2 --timeout 20 --retries 0
```

The default catch-up invocation budget equals max-pages, not the legacy two pages. To intentionally pause earlier, add `--pages 2`; use `--resume RUN_ID` with identical App/locale/page-size/catch-up/cap settings to continue, while retaining the original total cap. Omit `--catch-up` only for explicitly fixed-window experiments.

A reached hard cap is not completion. Re-running with the same insufficient cap can repeat the unresolved head. After explicit authorization, prefer extending the existing catch-up run using `--resume`, `--catch-up`, `--extend-max-pages` and a higher `--max-pages` so the saved cursor is retained. Do not loop or raise limits automatically. Budget selection for a backlog is distinct from choosing a recurring collection frequency.

## Offline verification

Full suite: **114 tests passed** after the final inheritance fix. Run:

```powershell
../.venv/Scripts/python.exe -m unittest discover -s tests -q
```

The new catch-up module has 13 tests, plus one new summary test. Coverage includes:

- Three Apps with 260 known new IDs each: all 780 captured in three pages per App, whereas two 100-record pages would omit 60 per App. Only 40 baseline IDs per App are revisited on the boundary page; no fourth-page old tail is requested. SQLite audit passes and total unique IDs are exactly 1,080.
- In-run repeats and cross-page duplicates do not count as pre-run boundaries. New IDs after a known ID on the same page are retained.
- Whole-page replay updates existing records without adding duplicate rows; IDs are App-scoped.
- A restart retains its original ID snapshot and cursor; total cap cannot reset on resume.
- A new run after a capped run cannot turn the partial new head into false evidence of closure.
- Cold starts, transport failure, rejected records, oversized responses, SQLite rollback and source-quality persistence fail closed as appropriate.

These are controlled source fixtures with known expected IDs. They establish no misses for those fixtures, not for all Google Play reviews.

## Live validation

User-approved ceiling: three Apps, at most two rounds, ten pages of 100 per App per round, at most 60 requests, no retries. The operational database was copied using SQLite backup to `data/catchup-validation-2026-10-16.sqlite3`. Original database remains at **7,608 unique reviews** and was not modified.

Round 1 used 20 successful requests, zero failures:

| App | Pages | New IDs | Repeated | Updated subset | Stop |
| --- | ---: | ---: | ---: | ---: | --- |
| Duolingo | 10 | 1000 | 0 | 0 | page_limit, unresolved |
| Google Maps | 3 | 298 | 2 | 2 | known_id_reached |
| Spotify | 7 | 699 | 1 | 1 | known_id_reached |

Both Maps and Spotify needed more than the prior fixed 200-review window. This does not mean every returned ID was published since October 12; new means new to this database.

After saving round 1, the two-round launcher was stopped before round 2. Review of the capped result prompted the additional unresolved-boundary inheritance fix and its regression test. Round 2 was then invoked separately with the final code, under the original approval; no third round ran. The round-1 artifact is preserved as captured, so it lacks the subsequently added `inherited_from_run` field.

Round 2 used 12 successful requests, zero failures:

| App | Pages | New IDs | Repeated | Updated subset | Stop |
| --- | ---: | ---: | ---: | ---: | --- |
| Duolingo | 10 | 1 | 999 | 0 | page_limit, inherited original unresolved target |
| Google Maps | 1 | 0 | 100 | 0 | known_id_reached |
| Spotify | 1 | 0 | 100 | 0 | known_id_reached |

Total: **32 requests**, 3,200 accepted observations, 1,998 new unique IDs; experiment-copy count increased from 7,608 to **9,606**. Both round audits passed: integrity ok, no foreign-key issues, snapshot mismatches or accounting issues. No within-page or cross-page duplicates were reported in either live round. Repeated observations are expected, not duplicate database rows.

The nonzero round-2 exit is intentional: Duolingo still has an unresolved gap. Its 999 repeated records are the incomplete recently collected head, not IDs in its older frozen target. Maps and Spotify stop after a single boundary page on the repeat, limiting unnecessary old-tail retrieval.

## Remaining limitations and next decision

- Duolingo has not completed catch-up at this approved 10-page cap. Do not tell John it has. Its capped repeat demonstrates why a scheduler must not blindly repeat this budget.
- Meeting one known ID is a practical boundary heuristic, not a global completeness guarantee. Pinned/reordered reviews, source omissions and legacy gaps can undermine continuity. Existing timestamp-inversion checks remain in place.
- A boundary page necessarily revisits up to one page of old IDs. The collector does not discard the rest of that page, because it may contain unseen IDs or edits.
- An unresolved inherited target may require rereading the head in a fresh run. Operators must review an adequate bounded backlog budget rather than automate repeated capped runs.
- No new store-browser comparison, public database sync, scheduler, email send or full-history collection was performed. Same-day repeat evidence does not prove behavior at a daily interval.
- Next useful experiment is an explicitly authorized larger bounded Duolingo backlog test, then a separated-time catch-up run. This was not added to the approved 60-request experiment.

## Saved evidence

- [Round 1 aggregate report](../samples/google_play_catchup_2026-10-16.json)
- [Round 2 aggregate report](../samples/google_play_catchup_2026-10-16_round2.json)
- [Enhanced summary](../samples/john_catchup_summary_2026-10-16.json)
- [Regression tests](../tests/test_catchup.py)

Only implementation, aggregate reports and findings are published. Operational database, raw snapshots and email content stay local.
