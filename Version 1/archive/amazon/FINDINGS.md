# Amazon Feasibility Findings

Test date: 2026-09-21  
Test product: Sony WH-1000XM5 (`B09XS7JWHH`)

## What was tested

The collector received one defined product identifier and made a limited request to:

1. the dedicated Amazon review page; and
2. the corresponding product page as a fallback.

It did not perform category discovery, pagination, CAPTCHA handling, login automation, or access-control bypassing. Raw HTML was not retained.

## Result

The dedicated review endpoint returned HTTP 200 but displayed a sign-in page on every automated run.

The same anonymous product-page request was then run twice in immediate succession:

- run 1: the product page loaded, but no review records were present;
- run 2: the product page loaded and 13 review records were extracted.

A third run after parser cleanup also extracted 13 records. A signed-in interactive browser displayed review records, but the collector does not reuse personal browser cookies or credentials.

The parser stored review ID, title, body, rating, date, variation, verified-purchase flag, product ASIN, source URL, and collection timestamp. It intentionally does not store reviewer names.

## Conclusion

The prototype proves that the parsing, cleaning, CSV export, SQLite storage, and run diagnostics work. It does not prove that direct Amazon HTML is a stable recurring source. The two consecutive runs produced different review availability, and the dedicated review endpoint required sign-in.

Recommendation: keep Amazon as a documented feasibility test, not the primary production source. Before expanding the pipeline, confirm an authorized and stable access method or test another source with clearer API access.

## Alternatives worth evaluating

1. **Best Buy Developer API** — an official keyed API with product identifiers, review averages, and review counts. Confirm whether the current authorized API exposes individual review text before selecting it. Documentation: https://bestbuyapis.github.io/api-documentation/
2. **PowerReviews Read API** — an official API designed to return reviews, questions, and answers. It requires the appropriate merchant/client credentials and permission. Documentation: https://developers.powerreviews.com/Content/reference/read.html

Static public datasets can be used to test schema and cleaning logic, but they would not satisfy the requirement for repeatable ingestion from a live source.

## Evidence files

- `samples/amazon_run_1.json`
- `samples/amazon_run_2.json`
- `samples/repeatability_summary.json`
- `samples/amazon_latest_run.json`
- `samples/reviews_sample.csv`

