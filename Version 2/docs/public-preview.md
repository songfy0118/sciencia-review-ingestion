# Public preview

URL: https://product-review-data.review-data-lab.workers.dev/

The previous Amazon site at this address has been replaced by the Google Play preview. Amazon code and findings remain in `Version 1/archive/amazon/`.

## What a visitor can do

- Search saved app names and review text, filter by star rating or helpful votes, and page through results.
- Select a saved app or paste another Google Play app link/ID to request a sample from Google Play.
- Continue a saved online run for up to three pages. A failed page does not advance the saved cursor or replace earlier committed data.
- Download JSON containing up to 1,000 matching review records. Response metadata includes the total and whether further pages remain; this is not a complete database export.

Search does not initiate collection. App names work for saved-library search; a new app needs a Google Play link or package ID. Reviews of the Google Maps app are not place reviews. No physical-product source is enabled.

## Storage and provenance

The public Worker uses a shared D1 SQLite database, independent of the user's computer. Initial data: 1,221 unique reviews across nine apps, copied from the local prototype without reviewer names, avatars, local logs or credentials. Local and cloud databases are separate after this seed; neither automatically mirrors the other.

`web/google-play.mjs` uses the request format and field mapping of `google-play-scraper` 1.2.7, with Workers-native fetch. It is a separate adapter, not the Python package running in the cloud. The original Python package remains the source tool for the local research pipeline. See `web/THIRD_PARTY.md` for attribution.

Each online page is validated before an atomic D1 batch stores normalized reviews, the page snapshot and the updated checkpoint. Existing `(app_id, review_id)` records are updated. Source page observations and unique saved reviews are different counts. Snapshots omit author names and retain the normalized fields needed to inspect saved records.

## Limits

English/US requests, newest sort, 25 requested reviews per page, three pages per run, 60 shared page requests per hour, and a short per-app cooldown. The site has no login and is intended for small research demonstrations, not high-volume production use. The public collection quota is shared and may be exhausted by other visitors. There is no automatic schedule, full-history backfill or completeness guarantee. Old returned dates produce a freshness warning. Google can change or restrict this unofficial endpoint.

App metadata names for newly added apps may be visitor supplied. No uploads, arbitrary URL fetches, or database administration are exposed. Database growth, ongoing operational monitoring, scheduled collection and retention require a separate deployment policy before expanding usage.

## Deploy and test

Run these commands from **Version 2**. Use the project's already-installed Wrangler CLI or an existing compatible Wrangler installation; no new runtime dependency was added. Configuration is `web/wrangler.jsonc`; credentials remain outside this repository.

```powershell
node --test web/worker.test.mjs
node --check web/public/app.js
../.venv/Scripts/python.exe web/seed.py
node "../Version 1/archive/amazon/site/node_modules/wrangler/bin/wrangler.js" d1 execute app-review-data --remote --file web/schema.sql --config web/wrangler.jsonc
node "../Version 1/archive/amazon/site/node_modules/wrangler/bin/wrangler.js" d1 execute app-review-data --remote --file data/deployment/seed.sql --config web/wrangler.jsonc
node "../Version 1/archive/amazon/site/node_modules/wrangler/bin/wrangler.js" deploy --config web/wrangler.jsonc
```

Seed SQL is ignored by Git and uses conflict-do-nothing semantics so rerunning it cannot overwrite a newer cloud review. Initial schema setup and seeding are one-time deployment steps; ordinary releases only need testing and deployment.

Tests cover source-shape failures, URL validation, duplicate updates, atomic rollback, failed-page recovery, exact-app search, filters, shared quota and cross-origin rejection. The live deployment also needs checking because the Workers runtime differs from Node: the initial `redirect: error` setting failed on Workers and was replaced with `manual`, with a regression test that rejects redirects. The failed live run is retained in the run history as evidence.

The previous Amazon Worker version is `7ff43204-6ed7-45ae-95ef-ac3be88ce1b5` if deployment rollback is needed; the D1 database is a separate resource. Do not delete it as part of a code rollback.
