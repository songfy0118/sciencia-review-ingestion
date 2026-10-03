# Public review snapshot: October 3, 2026

This is a downloadable snapshot of 3,798 unique reviews across five Google Play
Apps, collected in English/US bounded experiments. It is not a live database,
complete review history, or evidence that every returned review is recent.

- [Full dataset](reviews.json.gz): gzip-compressed UTF-8 JSON array, 3,798 records.
- [Preview](preview.json): the first ten exported records, not an additional dataset.
- [Manifest](manifest.json): counts, SHA-256 hashes, privacy exclusions and quality status.

Fields include App ID/name, review ID/text, rating, helpful votes, source/reply
timestamps, version, source URL and collection time. Collection time does not mean
the review was published at that time.

Reviewer names, avatars, original source pages, operational logs and credentials
are excluded. Six contact/secret-pattern occurrences in text were replaced with
redaction markers. This is pattern-based minimization, not a guarantee of complete
anonymization; ordinary dates/numbers can also be over-redacted. The local source
database remains unchanged and private.

Duolingo remains flagged for source freshness. Three Apps remain flagged because
bounded catch-up did not reach the previous window. The export does not remove
these warnings or turn the sample into a training-ready dataset.

Reviews are third-party Google Play content. Public visibility does not establish
unrestricted reuse rights; this snapshot does not grant a blanket license over
review text. Evaluate source terms and your intended use separately.

Read with standard Python:

```python
import gzip
import json

with gzip.open("reviews.json.gz", "rt", encoding="utf-8") as stream:
    reviews = json.load(stream)
assert len(reviews) == 3798
```

Code: `../../web/export_public.py`. Export/privacy regression tests are included
in the 85-test Python suite. The existing public website's D1 database is separate
and was not changed by this GitHub publication. No scheduled update is enabled.
