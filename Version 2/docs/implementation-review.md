# Implementation review — September 27, 2026

Historical review: the public Google Play interface was deployed later on
September 27, superseding the Amazon-hosting statements below. See
[public preview](public-preview.md). The September 29 work focuses on
[controlled repeated ingestion](controlled-ingestion.md), not interface changes.

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

The current local result browser shows app names and cached app icons, searches saved review text or app names, and filters by source stars and helpful votes. Review IDs and UTC timestamps are available under record details. The collector does not capture review photos or videos, and the star filters are not sentiment classification. A colleague cannot use this machine's localhost address; a hosted read-only data source and explicit publication scope would be required before sharing a searchable link.

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

### App search and extension check

The September 27 follow-up repeated a one-page, 25-review request for each of the eight configured apps (200 returned records), then added Uber through the local web form (25 records). All records were merged into the same SQLite database, which now held 1,221 unique reviews across nine apps. Integrity checks passed, with zero foreign-key issues or source-snapshot mismatches. Duolingo still returned September 10 as its newest review, so the eight-app run retained its freshness warning.

Browser checks covered all nine exact app names, the unknown-app message, rating/helpful-vote filters, and adding an unlisted app. One bug was found and fixed: an exact app-name search could include reviews of other apps that mentioned that name. Exact names now select the matching app; other keywords still search review text and partial names. The no-results message links to collection, and custom apps can have a display name. Repeating a custom app preserves that name. Searches do not initiate upstream requests.

The CLI refresh and local panel now use the same default snapshot directory, `data/inspection`, so future command-line refreshes appear in the panel. Earlier `data/cycles` results remain preserved separately. The 46 current Google Play tests and six archived Amazon tests passed. [Aggregate evidence](../samples/google_play_search_validation_2026-09-27.json) contains counts and findings without review text or author names. Scheduling frequency, app-selection policy and shared deployment remain undecided.
