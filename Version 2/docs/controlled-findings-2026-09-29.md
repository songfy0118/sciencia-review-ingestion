# Controlled ingestion findings: September 29, 2026

Source: three live Google Play collection rounds on this computer, using the
[fixed protocol](controlled-ingestion.md). Evidence:
[aggregate JSON](../samples/google_play_controlled_2026-09-29.json).

## Results

| Round | Returned observations | New to database | Existing, changed | Existing, unchanged | Unique stored total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,000 | 1,000 | 0 | 0 | 1,000 |
| 2 | 1,000 | 3 | 0 | 997 | 1,003 |
| 3 | 1,000 | 0 | 0 | 1,000 | 1,003 |

Spotify, Duolingo, Google Maps, WhatsApp and Netflix each returned 200 reviews
per round. All three newly observed IDs in round 2 came from WhatsApp. There
were 30 successful page requests, zero failed requests, zero rejected records,
and zero within-page or cross-page duplicate occurrences. Existing IDs across
rounds were merged, not inserted again.

Every round passed SQLite integrity, foreign-key and source-snapshot reconciliation
checks. These checks concern the local experiment database, not Cloudflare D1.
The database was fresh at the start; historical local and cloud data were not imported.

## Remaining source questions

Duolingo's newest returned timestamp was September 22 at 04:53:03 UTC, about
7.7 days old when collected. The other four Apps' newest timestamps were about
one day old. This experiment does not establish the reason for that delay or
prove that NEWEST returns the freshest available reviews.

New IDs mean newly observed by this database, not newly posted. No changed
existing reviews or source failures occurred in the live sample. Update handling,
conflicting duplicates, failed writes, rollback and resume were checked separately
with deterministic fixtures; they are not live failure or update observations.

## Code and validation

- Page-level change counts commit with reviews and checkpoints. Existing historical
  pages without counts are explicitly marked unclassified.
- Database page failures roll back the page and mark the App failed. Other Apps
  continue when failure logging remains writable. Successful resume clears the
  current job error; retain the failed run report as historical evidence.
- Evaluation now uses the same first-valid-occurrence rule as storage and audit
  for conflicting duplicate IDs within a page.
- Repeated CLI runs include source evaluation and database audit in each report.
- 50 Python tests and 10 JavaScript tests passed. Python compilation checks passed.

The next useful experiment is another manual collection on a later date with
the same settings and database, saving a new report filename. Short-interval
overlap alone cannot determine a daily schedule. No scheduler, model training,
web redesign, cloud deployment or GitHub push was performed.

## Local source provenance

The base is GitHub's main-branch archive at commit prefix 93856d5, downloaded
September 29. The bundled Git lacked its HTTPS remote helper, so this is an
editable source snapshot, not a clone with Git history. The original archive and
an untouched extracted baseline are preserved in the workspace for comparison.

## Follow-up self-review, September 29

Three failure-path weaknesses were corrected after the live experiment:

- Database page errors now also enter play_storage_failures, preserving their
  history after resume clears the current job error.
- CLI reports are saved before verification, retain separate collection and
  verification states, and record check exceptions without losing the round.
- JSON reports use flushed temporary files and atomic replacement so a failed
  replacement leaves the previous report intact.

57 Python tests passed, including seven new fault-injection regressions. These
changes were checked offline. The original live evidence JSON is unchanged and
predates the new verification_status and storage_failures fields; missing fields
in that historical report must not be interpreted as newly measured results.
