# October 7 manual freshness experiment

This is day 1 of the follow-up requested on October 5. It is not a completed consecutive-day study. Scheduled collection remains disabled.

## Protocol

- Local date: 2026-10-07 (America/Chicago).
- Run: `f6092027-17fe-47b9-a760-627269b8110e`.
- Collection finished: 2026-10-07T20:42:39Z.
- Five Apps, English / US, NEWEST, two pages of 100 requested records per App.
- Existing pinned adapter: google-play-scraper 1.2.7, strict-single-page-v2.
- No automatic retries; 2-second delay and 20-second worker timeout.
- The first invocation recorded five local socket-permission failures (WinError 10013), with zero saved pages. After network permission was granted, the same run resumed and saved ten pages. Durable accounting therefore contains 15 attempts: five local failures and ten successful source requests.
- The same persistent local SQLite database was used. No D1/site sync was performed.

## Results

| App | Observations | New IDs | Repeated | Updated | Unchanged | Latest returned review (UTC) | Age at collection |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Duolingo | 200 | 199 | 1 | 1 | 0 | 2026-09-27T04:21:41Z | 10.68 days |
| Google Maps | 200 | 199 | 1 | 1 | 0 | 2026-10-06T20:38:52Z | 1.00 day |
| Netflix | 200 | 200 | 0 | 0 | 0 | 2026-10-06T20:38:49Z | 1.00 day |
| Spotify | 200 | 200 | 0 | 0 | 0 | 2026-10-06T20:40:28Z | 1.00 day |
| WhatsApp | 200 | 200 | 0 | 0 | 0 | 2026-10-06T20:42:14Z | 1.00 day |
| Total | 1000 | 998 | 2 | 2 | 0 | | |

New IDs means newly encountered by this database, not necessarily newly posted reviews. Updated is a subset of repeated; it includes changes to normalized fields such as helpful votes, review version, content, rating, or reply. Do not add updated to repeated as separate observations. All ten pages had zero within-page duplicates, rejections, and cross-page duplicates.

The database increased from 3,798 to 4,796 unique reviews. Historical page observations total 6,800 across 68 committed pages.

## Store-page comparison

The browser page was checked in English / US with Phone selected, no star filter, and the review dialog explicitly switched from Most relevant to Newest. The browser was signed in; the collector is not, so their request context is not identical. Store UI dates have day precision, not UTC second precision.

- [Duolingo](https://play.google.com/store/apps/details?id=com.duolingo&hl=en_US&gl=US): the first three visible reviews all showed September 27, 2026. Their review IDs matched records stored by this run:
  - `d322499d-8e2a-4bee-9916-65fc442ed8bb`: 2026-09-27T04:21:41Z.
  - `6ad8e50c-47df-4aeb-b35f-6bbec85589ac`: 2026-09-27T03:41:26Z.
  - `84e54a0e-e134-4fb3-a550-701a4e1cf8e4`: 2026-09-27T01:09:19Z.
- [Spotify](https://play.google.com/store/apps/details?id=com.spotify.music&hl=en_US&gl=US): the first visible reviews under Newest showed October 6, 2026, consistent at day precision with the collector.
- [Google Maps](https://play.google.com/store/apps/details?id=com.google.android.apps.maps&hl=en_US&gl=US): the page and review dialog opened and Newest was selected, but subsequent browser reads timed out twice. Its final review dates were not verified. Do not count it as a completed UI control.

No screenshot artifact was saved; the UI observations above come from the browser accessibility/DOM reads during this session. Only dates and Duolingo review IDs are included here, not reviewer names or review text.

## Interpretation

Duolingo still has a freshness warning: its newest returned review is about 11 days old, while all four collector controls are about one day old. However, the observed Duolingo store UI also returns the same dated reviews and IDs. This experiment did not reveal newer store-visible reviews missing from the collector.

This suggests an App-specific difference in the exposed review feed under the tested context, rather than an obvious general timestamp-parsing or sorting error. It does not establish why the feed lags, prove that newer reviews do not exist elsewhere, or rule out a shared upstream issue affecting both the UI and scraper.

Across all ten saved pages, transport metadata was present, NEWEST ordering had no adjacent timestamp inversions, and source HTTP clock differences were approximately 4-6 seconds. No date correction or speculative collector change was made.

## Verification and remaining work

- SQLite integrity: ok; foreign-key issues: 0.
- Saved snapshot mismatches: 0; accounting issues: 0.
- Storage verification passed. Overall source quality remains needs_attention because of Duolingo freshness; the CLI exit code was 1 for that warning, not a failed final collection.
- Existing offline suite: 85 tests passed on October 7.
- Full machine-readable evidence: [collection report](../samples/google_play_controlled_2026-10-07.json).
- Repeat the same capped protocol on October 8 and October 9 using the same database and new dated reports. These are planned runs, not completed or scheduled runs.
- Complete the Google Maps store-page control in a later manual session.
- Only after the multi-day observations should collection frequency and a simple scheduler be discussed.
