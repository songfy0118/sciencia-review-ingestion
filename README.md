# Review Ingestion Feasibility Test

This repository is a small feasibility test for a repeatable review-ingestion workflow. It accepts a defined set of Amazon product identifiers or URLs, makes a limited request, detects common access barriers, extracts review fields when they are present, and stores the result in SQLite.

The current scope is intentionally narrow:

- input: a small list of product ASINs or URLs;
- collected fields: review ID, text, rating, date, product identifier, variation, verification flag, source URL, and collection time;
- intermediate output: CSV and a JSON run report;
- final local storage: SQLite;
- excluded for now: category-wide discovery, product comparison, sentiment analysis, and model training.

## Public web demo

The `site/` directory contains a small public interface for the same feasibility test. A visitor can enter one Amazon ASIN or product URL, run a limited live-source check, inspect any review records exposed to the request, and download the normalized rows as CSV. The web route makes no attempt to log in, solve CAPTCHA, paginate, or bypass an access control. A blocked or unreachable request is displayed as a documented feasibility result rather than treated as collected data.

The web demo does not persist public visitor queries or review text. Durable structured storage remains in the Python prototype's SQLite output so anonymous visitors cannot use the deployment as a public data-writing service.

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

The collector makes at most two requests per product: the dedicated review page first, then the product page if the first response contains no review records. It waits between requests and does not attempt to bypass sign-in, CAPTCHA, or other access controls.

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
