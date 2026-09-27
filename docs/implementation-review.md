# Implementation review — September 27, 2026

The current milestone is a small, repeated Google Play collection across several apps, with persistent relational storage and an honest source assessment. Amazon work is paused. Classification, labeling and model training are later consumers of this data, not current deliverables.

## Requirement checks

| Requirement | Implementation and evidence | Boundary |
| --- | --- | --- |
| Defined app set and configurable acquisition | App IDs or Google Play links; bounded page size and page count; CLI and local control panel | No broad crawler or arbitrary website fetching |
| Clean, consistent records | Required IDs, nonempty text, 1–5 integer scores, UTC dates and Unicode normalization; invalid rows retain rejection reasons | Original language is preserved; stars are not sentiment labels |
| Relational, queryable storage | Apps, reviews, runs, observations, pages and attempts; composite review key and foreign keys | SQLite is the local prototype destination; PostgreSQL deployment is not implemented |
| Repeatable loading | Upsert by app/review ID; repeated requests do not duplicate rows; raw page snapshots are retained | Sampling recent pages is not full historical coverage |
| Failure recovery | Page data and cursor commit together; retries for transient errors; continue action uses saved run configuration | An upstream cursor can expire; no claim that expired cursors can be recovered |
| Basic quality checks | Source snapshot reconciliation, DB integrity, rejection counts and per-run freshness warnings | Checks cannot prove upstream completeness or correctness |
| Inspectable results | Preserved refresh results, source evaluation, JSON and actual SQLite backup; local collection controls | The old public website remains the Amazon demonstration |

The project brief permits SQLite for local prototyping and treats scheduling as a future iteration. Its learning resources cover acquisition, relational design, normalization and later text classification; they do not require using every linked framework. No new dependency was added in this iteration.

## Comparison with established projects

- [JoMingyu/google-play-scraper](https://github.com/JoMingyu/google-play-scraper): continuation tokens and bounded requests are useful primitives. We retain the pinned Python adapter but add durable state, atomic loading and explicit error reports around it. The upstream private interface remains a maintenance dependency.
- [facundoolano/google-play-scraper](https://github.com/facundoolano/google-play-scraper#reviews): documents review pagination and warns that the store's rating count is not a count of written reviews. We avoid displaying a misleading coverage percentage. Neither adapter establishes a completeness guarantee for this project.
- [Scrapy job persistence](https://docs.scrapy.org/en/latest/topics/jobs.html): separates persistent job state and duplicate detection and documents resume limitations. We keep each run's checkpoint separate and preserve its request configuration; the existing SQLite transaction is our recovery boundary.
- [dlt incremental loading](https://dlthub.com/docs/general-usage/incremental-loading): distinguishes append, replace and merge. Reviews can change, so we keep the existing upsert behavior and immutable source snapshots instead of blindly appending copies or replacing the database with a small sample.

These are design comparisons, not claims of feature parity or measured superiority. The frameworks were not installed or incorporated.

## Issues fixed in this iteration

1. The review filter selected every table body, accidentally counting or hiding the summary rows. It now targets only the review table, with an executable JavaScript regression check.
2. A non-object source response could abort the entire batch. It now records an app failure and allows other apps to finish. Malformed worker errors also become diagnostic source failures.
3. Damaged old status files could block a new refresh. They are surfaced as warnings without stopping valid new collection.
4. Starting or resuming required shell commands. A local control panel now starts bounded collection, shows progress, protects against duplicate starts and loads saved checkpoints after restart.

The control panel binds only to 127.0.0.1. Collection requests require the local origin and a per-server token. Downloads are restricted to known snapshot filenames. It is not a public multi-user server.

## Validation and open findings

The live control-panel test repeated the three-app, 50-review sample: 150 observations, no added duplicates, 773 unique stored records. Continuing that same run retrieved another page for each app and increased the database to 923 unique records. Both snapshots passed storage reconciliation. [Saved evidence](../samples/google_play_control_panel_2026-09-27.json) contains the separate reports. All 47 local tests passed, including the generated JavaScript pagination regression. The browser checks covered starting, continuing, filtering, pagination, no matches, clearing filters, duplicate input and return navigation. Desktop and 390-pixel viewport layouts were inspected; the narrow layout had no document-wide horizontal overflow.

Duolingo remains flagged: the newest returned review is still September 10. The earlier US/GB comparison did not resolve this. This is an unresolved source suitability finding, not a fixed freshness guarantee. Additional collection dates and an independent source comparison are needed before a deployment decision. Long-term uptime, all-review coverage, public hosting and an always-on scheduler have not been validated or delivered.

See [cross-day evidence](google-play-cross-day-findings.md) and [the data contract](google-play-data-contract.md).
