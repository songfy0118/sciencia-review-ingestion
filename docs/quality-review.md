# Review Collector quality review

Reviewed against the supplied Data Ingestion System project brief and Learning Materials: acquisition, structured fields, cleaning/validation, relational storage, and repeatable loading. Sentiment classification remains downstream. This is a bounded feasibility prototype, not a completed production ingestion platform.

## References

- [PlanetScale: relational schema design](https://planetscale.com/blog/schema-design-101-relational-databases), listed in the learning materials: separate entities, keys, relationships, and consistent fields.
- [Datasette on GitHub](https://github.com/simonw/datasette): inspectable records, filtering, and data export. This is a workflow reference; no code or visual assets were copied.
- [Apify dataset documentation](https://docs.apify.com/storage/dataset): structured records and distinct CSV/JSON export formats.
- [W3C form notifications](https://www.w3.org/WAI/tutorials/forms/notifications/): concise error guidance, associated field errors, and announced status updates.
- [Cloudflare HTMLRewriter](https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/): HTML element-scoped extraction in the deployment runtime.

## Corrections

The previous website selected the longest span after a review body marker. This could lose most paragraphs, exclude short comments, and capture unrelated “Sending feedback...” text. It also mapped missing ratings to zero, guessed purchase verification from an absent badge, used inconsistent JSON/CSV names, accepted unrelated hosts as product URLs, and could misreport an entire run as a network failure after just one failed request.

The new parser is separate from retrieval and export code. It uses the platform HTML parser with field selectors, retains full available paragraphs, skips invalid records with diagnostic counts, deduplicates real IDs, preserves unknown values, and normalizes recognized dates while keeping source text. The collection report records each attempted page independently.

The interface now separates product input, collection scope, results, records, and expandable run details. It supports keyboard navigation, accessible labels/statuses, clear validation, reduced motion, full-text expansion, search/rating filters, original-source links, and responsive layouts. Export buttons clearly download all collected rows regardless of table filters.

## Verification scope

Automated Worker-runtime tests cover multi-paragraph/short reviews, nested markup, UI contamination, missing values, date validity, duplicate IDs, more than 25 rows, misleading CAPTCHA references, host validation, mixed source failures, and CSV quoting/formula handling. SQLite tests cover repeated import, identity across products, validation failures, missing values, foreign keys, and stale exports. Live-source availability is checked separately; passing parser tests does not establish stable Amazon access.

## Executed checks (2026-09-21)

- 12 Worker-runtime tests passed, including one against a freshly retrieved Amazon product page; 6 Python tests passed.
- TypeScript checking, ESLint, and production build passed.
- Browser exercise: empty-input validation, example input, live collection, rating filter, no-match search, filter reset, and CSV/JSON downloads.
- The actual downloaded files each contained 13 records with identical columns and body text. The first full review contained 2,332 characters, including the opening and all available paragraphs; the short review previously replaced by feedback UI text was correctly read as the source's short comment.
- Actual downloaded JSON was loaded into SQLite twice: 13 stored review rows after each run, integrity_check = ok, zero foreign-key errors.
- Desktop and 390 px mobile layouts were inspected. The page did not overflow horizontally; the wide review table scrolls inside its own region.

## Remaining limits

- Amazon's anonymous responses vary. Some runs return reviews and others require sign-in/verification or contain no usable review cards.
- No full-history pagination, scheduled collection, multilingual sentiment classification, or hosted database persistence is implemented.
- Website JSON can be loaded into SQLite using the supplied importer. An export file alone is not a database, and the UI explicitly says runs are not saved on the website.
- Future production work still requires a stable source, repeated collection measurements, storage appropriate to the deployment, and broader source-layout coverage. Unknown named HTML entities outside the supported common set are preserved rather than guessed.
