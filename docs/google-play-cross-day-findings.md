# Google Play repeated-collection findings — September 27, 2026

Google Play remains suitable for bounded evaluation, but the observed freshness gap prevents a stronger reliability claim. This follows John's requested multi-app repeated-collection test; Amazon work remains paused.

## Measured results

A fresh run requested one page of 50 reviews for each app, using English, US and NEWEST. The comparison uses an equal-size September 25 run, approximately 46.97 hours earlier. These were separate test runs, not continuous collection during that interval.

| App | Returned | IDs absent from prior sample | Newest returned review (UTC) | Age at collection |
| --- | ---: | ---: | --- | ---: |
| Duolingo | 50 | 49 | September 10, 20:31:09 | 17.02 days |
| Google Maps | 50 | 50 | September 26, 20:56:12 | 1.00 day |
| Spotify | 50 | 50 | September 26, 21:00:14 | 1.00 day |

All three requests completed without retries. The shared database increased from 624 to 773 unique reviews. All 773 records matched their latest normalized source snapshots; SQLite integrity passed and there were no foreign-key violations. These checks validate storage consistency, not the completeness or truth of the upstream dataset.

A separate two-request Duolingo probe used US and GB country parameters. Both returned the same 50 IDs and the same newest date. Changing this parameter did not resolve the observed freshness gap. The test cannot establish the cause or verify reviewers' locations.

## Workflow changes

- Freshness is evaluated from the current run's saved source records, rather than the accumulated database.
- Comparable runs report elapsed time, new IDs within the window and changes to shared reviews' text, rating or developer reply. IDs leaving the window are not treated as deletions.
- Every refresh preserves its database snapshot, collection report, storage audit and source evaluation. A local history page provides links to each saved result, including failed refreshes.
- Review records continue to accumulate automatically in one SQLite database; individual downloads are optional inspection outputs.

## Remaining limits and next decision

New IDs are not necessarily newly posted reviews, as the Duolingo result demonstrates. Seven days is a diagnostic warning threshold, not an agreed service requirement. The sample does not prove full historical coverage, long-term uptime or recovery from expired upstream cursors. No always-on deployment or recurring scheduler is configured.

Continue bounded tests across additional dates and check freshness against independently visible review dates before adopting this as a reliable live source. Keep Duolingo flagged for investigation. The existing checkpoint and retry implementation is useful, but cannot guarantee that upstream continuation tokens remain valid indefinitely.

Evidence: [run, audit and comparison](../samples/google_play_cross_day_2026-09-27.json), [locale probe](../samples/google_play_locale_probe_2026-09-27.json). Public reports contain aggregate findings, not review text or usernames.
