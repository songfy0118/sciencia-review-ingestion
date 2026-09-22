# Review export contract (version 1.0)

The review-only JSON is an array of normalized records. The formatted Excel workbook presents the same review fields on a `Reviews` sheet and puts run metadata and page checks on a separate `Run summary` sheet. The SQLite import is a readable SQL script that creates and fills `products`, `reviews`, and `ingestion_runs`. The technical run log is a separate object containing the records, source checks, coverage, run ID, collection timestamp, and quality counts.

| Field | JSON type | Meaning |
| --- | --- | --- |
| review_id | string | ID found on the source review card; never invented from row order. |
| product_asin | string | Requested Amazon.com product ID. Amazon can combine reviews across variations. |
| title | string | Review heading; empty when absent. |
| body | string | Full text available inside the review body element, with paragraph breaks. Original language retained. |
| rating | number or null | Source star rating from 1 to 5. Missing/unrecognized is null, never zero. |
| review_date | string or null | YYYY-MM-DD, only when the date can be interpreted unambiguously. |
| review_date_raw | string | Original source date text, including location when present. |
| variation | string | Available product variation text, otherwise empty. |
| verified_purchase | boolean or null | True only when an explicit Verified Purchase badge is present. Absence is unknown, not false. |
| source_url | string | Page from which the record was collected. |
| collected_at | string | Collection timestamp in ISO 8601 UTC format. |

## Quality and coverage

- Records without a real review ID or nonempty review body are skipped and counted.
- Duplicate IDs within a product run are collapsed; the longer available text wins. SQLite keys on `(product_asin, review_id)` so reviews shared across product variants do not overwrite another product's association.
- Text extraction stays inside each field's HTML element. It does not pick the longest span, include feedback controls outside the body, truncate at 25 records, translate reviews, or infer sentiment from stars.
- Known UI-only bodies are rejected. Paragraphs, short reviews, quotes, and numeric HTML entities are preserved. The bounded collector is still source-layout-dependent; an unavailable page is not evidence that a product has zero reviews.
- Coverage is always `available_sample`: there is no pagination or promise of completeness. Sample average describes retrieved, rated records only.
- For unrecognized date formats, the normalized date is null and the original string remains available. Empty descriptive strings and unknown scalar values have distinct representations.

## Export and storage

The Excel workbook uses wrapped text, fixed widths, filtering, frozen headers, typed ratings, and a separate run summary. JSON preserves normalized text exactly and remains the recommended input for the strict Python importer. The SQL script escapes text values and uses the same relational keys and constraints as the SQLite importer.

`python -m review_ingestion.import_web --input <export.json> --db data/web-reviews.sqlite3` validates all rows, loads products and reviews in a transaction, records each import, and checks SQLite integrity and foreign keys. Re-import is idempotent for review rows, while import history records each operation. The earlier feasibility CLI uses its original schema; incompatible existing databases are rejected rather than modified.

Example inspection queries:

```sql
SELECT product_asin, COUNT(*) AS reviews, AVG(rating) AS sample_average
FROM reviews GROUP BY product_asin;
SELECT SUM(rating IS NULL) AS missing_ratings,
       SUM(review_date IS NULL) AS unparsed_dates,
       SUM(verified_purchase IS NULL) AS verification_not_stated
FROM reviews;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```
