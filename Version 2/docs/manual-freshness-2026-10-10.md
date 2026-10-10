# October 10 controlled manual update

Run `b5b163f6-f8da-4e5a-8bb0-b76c36043f6d`, finished 2026-10-10T06:42:25.833631Z; local date October 10, America/Chicago. Same database and protocol as October 7/8: five Apps, en/US, NEWEST, google-play-scraper 1.2.7, two pages of 100 per App, 2-second delay, 20-second timeout, no retries. Ten successful requests, zero failed attempts. No collector code changes, scheduler, cloud sync or emails.

## Results

| App | New database IDs | Repeated | Updated subset | Latest returned UTC |
| --- | ---: | ---: | ---: | --- |
| Duolingo | 200 | 0 | 0 | 2026-10-09T06:40:37Z |
| Google Maps | 197 | 3 | 3 | 2026-10-09T06:42:02Z |
| Netflix | 200 | 0 | 0 | 2026-10-09T06:40:42Z |
| Spotify | 199 | 1 | 1 | 2026-10-09T06:40:29Z |
| WhatsApp | 200 | 0 | 0 | 2026-10-09T06:42:04Z |
| Total | 996 | 4 | 4 | |

1,000 observations were accepted. All four repeated records had normalized field changes. Updated is a subset of repeated, not an additional count. New means new to the database, not necessarily recently posted. Local unique reviews increased from 5,614 to 6,610; historical page observations total 8,800.

Storage audit: integrity ok, foreign-key issues 0, snapshot mismatches 0, accounting issues 0. Storage and current bounded source-quality checks passed. All Apps' newest samples are about one day old. Seven summary tests passed today; the full suite was not rerun because no code changed.

## Duolingo store check

The [store page](https://play.google.com/store/apps/details?id=com.duolingo&hl=en_US&gl=US) was checked with Phone selected, no star filter, explicit Newest sorting. The first three visible reviews showed October 9 and matched collected IDs:

- `f688319e-0047-4088-92e8-aecde5f26dcd`: 2026-10-09T06:22:36Z.
- `ff771e49-845e-404f-9b2a-50b825f732b3`: 2026-10-09T06:22:22Z.
- `e7a4a375-5594-4006-9aa5-7e11b7d977dd`: 2026-10-09T06:20:09Z.

The collector's newest record is later than these visible first three, so ordering/context is not assumed identical. UI dates are day-precision and the browser is signed in. No UI-visible newer reviews missing from this collected sample were observed. Store controls were checked on October 7, not rechecked today.

Duolingo's latest returned date has advanced across September 27 (October 7 run), October 7 (October 8 run), and October 9 (today). The previous stale-feed symptom has not recurred in the last two runs. Its underlying cause is still unknown; this is not a proven permanent fix.

## Coverage limitations

The recent series has three actual observation dates: October 7, 8 and 10. There is no October 9 experiment. The two intervals are about 9.21 and 48.79 hours; do not label this consecutive-three-day or fixed-daily testing. The longest consecutive UTC-date streak remains two.

Today's shared IDs with the preceding window were one for Maps, one for Spotify and zero for the other Apps. Maps repeated three IDs against the full database, but only one against the October 8 sample; these metrics intentionally measure different baselines. Low overlap under a 200-record cap cannot establish complete coverage or justify a production collection frequency.

This is enough for an interim progress update, not a claim of complete reliability validation. Scheduler remains deferred. A subsequent fixed-interval manual observation would strengthen evidence before choosing frequency.

- [Collection and audit](../samples/google_play_controlled_2026-10-10.json)
- [Three-date summary](../samples/john_multiday_summary_2026-10-10.json)
