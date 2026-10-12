# John requirements review - October 12

John's October 5 email was re-read on October 12. No later message from his known address was returned by the personal-mailbox search. After the initial offline review, the user approved one additional bounded collection; its results are included below.

## Requirement and evidence

| Requirement | Current evidence | Boundary |
| --- | --- | --- |
| Check Duolingo freshness against the store and other Apps | October 7 store checks included Duolingo, Spotify and Maps; October 10 Duolingo visible IDs matched collected records | Recent symptom did not recur; underlying delay cause is unknown |
| Repeat collection over a few days across several Apps | Five Apps on October 7, 8, 10 and 12, using the same database and bounded protocol | Intervals 9.21, 48.79 and 64.61 hours; not fixed daily or consecutive-four-day testing |
| Record new, repeated, updated and newest review timestamp | Per-App reports and enhanced multiday summary | New means new to this database; updated is a subset of repeated |
| Keep results in the same GitHub repository | Saved reports, store checks and two quality-improvement passes | Operational SQLite stays local; published static snapshot is separate |
| Defer scheduler until behavior is reliable | No scheduler enabled | No production frequency or full-coverage guarantee established |

John did not specify a date range, exactly three consecutive days, a 24-hour interval or complete review-history collection. Fixed-interval observations are a useful follow-up recommendation, not an invented acceptance requirement.

## Current state and this review's fixes

- Latest completed collection: October 12, 1,000 accepted observations, 998 new IDs, two repeated and two updated records; local database contains 7,608 unique reviews.
- October 12 post-collection audit: integrity ok, zero foreign-key issues, zero snapshot/count issues. Ten successful page requests, zero failures, no retries. All five Apps' newest returned timestamps are October 11, about one day old. No new store UI comparison was performed today.
- Corrected stale README and protocol statements about 3,798 reviews, a one-day experiment and an unexecuted October 8 run.
- Linked current evidence from the README instead of presenting the October 2 review as the latest acceptance state.
- All 100 offline tests were rerun and passed on October 12 (9.918 seconds); this documentation update does not change collection logic.

## What can be reported

The requested multiday checks and metric reporting have been performed. Results are sufficient for a progress discussion, but not a statement that every source-reliability issue is solved. Duolingo's newest date advanced from September 27 to October 7, October 9 and October 11. Its old-date symptom has not recurred in the last three runs. A signed-in store view and an anonymous collector need not expose identical order or context.

The remaining uncertainty is source behavior, not a proven storage defect. A 200-record window with low overlap cannot establish complete coverage. Do not fabricate missing dates, enlarge the crawler without a budget, enable scheduling prematurely or describe local data as synced to the public website.

Next discussion with John: share the results and ask whether another short fixed-interval observation series would be useful before selecting a schedule. Keep the email as an unsent draft until user approval.

- [October 12 collection](manual-freshness-2026-10-12.md)
- [October 10 store check](manual-freshness-2026-10-10.md)
- [Enhanced multiday summary](../samples/john_multiday_quality_2026-10-12.json)
- [Two improvement passes](mature-project-review-2026-10-10.md)
