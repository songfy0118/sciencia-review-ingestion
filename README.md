# Review Ingestion Feasibility Test

This repository is a small feasibility test for a repeatable review-ingestion workflow. It accepts a defined set of Amazon product identifiers or URLs, makes a limited request, detects common access barriers, extracts review fields when they are present, and stores the result in SQLite.

The current scope is intentionally narrow:

- input: a small list of product ASINs or URLs;
- collected fields: review ID, text, rating, date, product identifier, variation, verification flag, source URL, and collection time;
- intermediate output: CSV and a JSON run report;
- final local storage: SQLite;
- excluded for now: category-wide discovery, product comparison, sentiment analysis, and model training.

## Public web demo

The `site/` directory contains the public Review Collector. Enter one Amazon.com ASIN or product URL, collect an available sample, inspect full review text, search/filter the sample, and download CSV or JSON. The parser uses Cloudflare's native HTMLRewriter to read text within each review field. It preserves paragraphs, removes duplicate IDs, keeps unknown ratings and purchase verification as null, and retains raw dates alongside normalized dates. The web route makes at most three page requests. It does not log in, solve CAPTCHA, paginate, or claim to retrieve all historical reviews. Per-request outcomes and data-quality counts are included in the downloadable run report.

The website does not persist visitor queries or review text. Download the JSON records and load them into a local relational SQLite database with the importer below. This closes the export-to-storage path without claiming that the public website saves runs in the cloud.

```powershell
python -m review_ingestion.import_web --input B09XS7JWHH-reviews.json --db data/web-reviews.sqlite3
```

The importer validates every row before loading, uses products/reviews/ingestion_runs tables, enforces foreign keys and rating constraints, preserves nulls, and upserts on `(product_asin, review_id)`. Re-importing the same file does not duplicate review rows. Older exports cannot overwrite newer observations. Use a new database for web exports; the legacy CLI database is not silently migrated. See [data contract](docs/data-contract.md) and [quality review](docs/quality-review.md).

Run the website locally with:

```powershell
cd site
npm ci
npm run dev
```

## Run

Python 3.11 or newer is recommended. The prototype uses only the Python standard library.

```powershell
python -m review_ingestion.cli `
  --input config/products.example.json `
  --db data/reviews.sqlite3 `
  --csv data/reviews.csv `
  --report data/run_report.json
```

The collector makes a small bounded set of requests per product: the dedicated review page first, followed by limited product-page checks when no review records are exposed. It does not attempt to bypass sign-in, CAPTCHA, or other access controls.

## Output

- `data/reviews.sqlite3` contains `ingestion_runs`, `products`, and `reviews` tables.
- `data/reviews.csv` is an inspection export and may contain zero rows when access is restricted.
- `data/run_report.json` records HTTP status, page classification, response size, extracted record count, and errors without saving raw page HTML.

## Initial Amazon finding

The live feasibility check found that the dedicated Amazon review page returned an HTTP 200 response whose page content was a sign-in screen. Two consecutive anonymous requests to the same product page then produced different results: one exposed no review records and the next exposed 13. A signed-in interactive browser also displayed review records. This indicates that review availability depends on request/session context and was not repeatable in this small test.

Recommendation: do not treat direct anonymous Amazon HTML collection as a reliable recurring source yet. Keep this adapter as a documented feasibility test. If approved, evaluate an authorized API/data provider or a small number of alternative live review sources before expanding the pipeline.

Compare repeated runs with:

```powershell
python -m review_ingestion.repeatability `
  samples/amazon_run_1.json samples/amazon_run_2.json `
  --output samples/repeatability_summary.json
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

The tests use local fixtures and do not contact Amazon.

Web parser and collection regression tests run in the same Worker runtime as production, using the already installed Miniflare dependency of Wrangler. No new packages are required:

```powershell
cd site
npm test
npm run typecheck
npm run lint
npm run build
```
