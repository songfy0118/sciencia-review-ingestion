# John requirements and acceptance: October 2, 2026

This milestone addresses John's September 28 email: run a controlled, somewhat
larger recurring-ingestion experiment across several Apps and report database
behavior. It is not a production launch or a promise to collect all reviews.
John's own review/acceptance has not yet been obtained.

## Requested deliverables

| Requirement | Verified evidence | Result |
| --- | --- | --- |
| Several Apps, larger bounded volume, repeated collection | Five fixed Apps; three September 29 rounds, one September 30 round, one October 2 catch-up | Implemented and tested live |
| Central database updated programmatically | One persistent SQLite store; 58 committed pages, 5,800 source observations, 3,798 unique reviews | Audit passed |
| New and existing reviews | Per-page new/repeated and changed/unchanged/stale counts; October 2: 1,796 new IDs, three changed existing, one unchanged | Recorded, not inferred from current totals |
| Duplicates | Composite review key, within-page duplicate counts and cross-page overlap; snapshot/observation reconciliation | Tested without duplicate stored rows |
| Failures and repeatability | Durable attempt/commit errors, atomic rollback/checkpoints, bounded retry and resume | Tested with controlled failure fixtures; no live failure in October 2 run |
| Public, inspectable code and findings | Code, tests and aggregate reports; raw reviews and databases stay local | Prepared for GitHub review |
| App reviews only; pause website and scheduling | No new UI, product categories, sentiment model or scheduler | Scope preserved |

## Final engineering checks

The Python test suite has 79 tests. The new five-App acceptance fixture uses two
pages of 100 per App over three rounds: 1,000 new IDs, then five edits plus 995
unchanged observations, then 1,000 unchanged observations. Stored unique count
stays 1,000. A fourth fixture run fails one second-page source request; resume
retries that page, preserves the recorded failure and recovers without increasing
the unique count. These are offline fixtures, not additional live collection.

Additional regression coverage includes rejected rows, stalled pagination,
incompatible/failed baselines, storage rollback and failure-log errors, stale
overwrite protection, CLI/report-path safety, atomic report replacement, UTC
source epochs, and false passing source assessments.

Resolved in this pass:

- Resume invalidates previous assessments before any fetch, so interrupted or
  unchecked data cannot keep an old passing quality result.
- `latest_play_source_quality` exposes current per-App status in the database.
- Assessment publication uses an immediate transaction and rejects changed runs;
  audits/evaluations read a coherent SQLite snapshot.
- New page transport metadata commits atomically with reviews and checkpoints.
- Evaluation checks NEWEST date inversions, request sort and HTTP/local clock skew.
- Audit reconstructs record counts, update counts, observation hashes and saved
  page numbering instead of trusting counters that merely add up.
- Failed runs cannot be comparison inputs or catch-up baselines. Missing App
  evaluation and failed storage audits cannot produce passing source quality.

The existing real database was re-audited after these changes: integrity/foreign
keys passed, zero snapshot mismatches and zero accounting/checkpoint issues.
See [aggregate reassessment](../samples/google_play_acceptance_2026-10-02.json).
No extra source requests were made for this acceptance pass. Existing review
records and source timestamps were not rewritten. The database received only
additive operational schema and refreshed quality assessments.

## Remaining source limitations

Duolingo's observed latest review was about 11 days old; US/GB probing returned
the same window. Three Apps exhausted the catch-up budget without reaching the
September 30 window. These conditions remain visible as `needs_attention`, not
silenced or converted into passing results. Historical pages lack the transport
metadata now collected for new pages; the old evidence is not retroactively
described as verified transport.

These findings satisfy the purpose of this experiment: show what repeated
collection actually does and what must be considered before choosing automation.
They do not establish guaranteed source freshness, complete history, production
readiness or a suitable daily/weekly cadence. Increasing request budgets without
a coverage target would not by itself solve source freshness. A cadence or
source-access decision should follow John's review, not an unlimited crawler.

Within this bounded milestone, the final checks found no remaining known blocker
in the local ingestion/accounting/recovery behavior. That is not a claim of
bug-free code or external source reliability.

## Reproduce

From `Version 2`, using the existing pinned environment:

```powershell
../.venv/Scripts/python.exe -m unittest discover -s tests -q
../.venv/Scripts/python.exe -m review_ingestion.audit_play --db data/controlled-2026-09-29.sqlite3 --report data/final-audit.json
```

The database is local and intentionally not on GitHub. Reviewers can run the
offline test suite without downloading private source snapshots. Live commands
and budgets are in [controlled ingestion](controlled-ingestion.md) and
[source-quality findings](source-quality-2026-10-02.md).
