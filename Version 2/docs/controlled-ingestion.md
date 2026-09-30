# Controlled repeated ingestion

This experiment follows John's September 28 request: measure repeated App review
collection before choosing an unattended schedule. No scheduler is enabled.

## Run

From Version 2, with the existing pinned requirements installed:

```powershell
../.venv/Scripts/python.exe -m review_ingestion.google_play_cli --input config/google_play_controlled.json --db data/controlled-2026-09-29.sqlite3 --report data/controlled-2026-09-29.json --runs 3 --count 100 --pages 2 --delay 2 --interval 30 --timeout 20 --retries 0
```

Five fixed Apps, en/us, NEWEST, two pages of 100 requested records per App,
three rounds: at most 30 page requests without retries. Every round restarts at
the recent window and merges into the same database. A resume continues an old
cursor instead; it is not a new round. Actual returned counts can be lower.

The database at --db is the source of truth for this experiment. The public D1
database remains separate. These findings cannot establish cloud reliability.

## Read the report

Each round includes its collection report, source evaluation and database audit:

`status` retains the collection outcome stored in SQLite. `verification_status`
is separately pending, passed or failed; CLI success requires both bounded_success
collection and passed verification. Source freshness warnings remain in evaluation
even when storage verification passes. A pending report is saved before checks;
check exceptions are recorded in verification_errors and produce a nonzero exit.
Reports replace the previous file atomically after writing and flushing a temporary
file in the same directory. An interrupted process may leave a temporary file, but
does not partially overwrite the prior report.

- new_records: IDs absent from the database before a page was written. This does
  not mean newly published reviews.
- repeated_records: IDs already stored, including overlap between pages.
- changed_records / unchanged_records: accepted existing records with or without
  a change in any normalized stored field, excluding collection time.
- stale_records: existing records whose older collection time prevents overwrite.
- duplicates: extra valid occurrences of the same ID within one page. The first
  valid occurrence wins, consistently in storage, audit and evaluation.
- cross_page_duplicates: accepted page IDs already observed in this run. These
  are a subset of repeated_records, not an additional disjoint category.
- rejected_records: invalid source rows retained with rejection reasons.
- failed_attempts: failed source requests, including transient errors. Database
  commit failures appear in each App's error and set the round to needs_attention.
  storage_failures retains page, time and error history even after a successful
  resume clears the current error. Failures predating this log cannot be reconstructed.
- unclassified_pages: historical pages created before change accounting existed;
  their update counts are unknown rather than retroactively treated as zero.

For fully classified rounds, accepted_records equals new_records + changed_records
+ unchanged_records + stale_records. Raw records equal accepted + duplicates +
rejected. Counts describe page observations, not necessarily unique IDs per run.

Per-run evaluation compares matching request settings and page counts; the audit
reconciles committed source snapshots with stored rows and checks SQLite integrity
and foreign keys. A failed page rolls back its reviews, metrics and checkpoint.
If the database can still record the failure, other Apps continue and the failed
App can resume. If even failure logging cannot be committed, the exception is
propagated; earlier committed pages remain in SQLite.

Short-interval rounds test overlap and idempotency, not daily arrival rates.
Repeat the same command manually on a later date with the same database and a
different report filename to study cross-day changes. Old or future source dates
remain warnings even when all storage checks pass.

Only aggregate reports belong in samples/. Raw review snapshots and database files
remain in the ignored data/ directory. No author names or review text are needed
in the evidence shared with John.
