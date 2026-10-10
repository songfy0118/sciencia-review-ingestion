# October 10: comparison with mature ingestion tools

This is a focused improvement to existing offline reporting, not a framework migration. No dependency installation, new collection, scheduler or cloud database change was made.

## References and engineering choices

[Scrapy's official Stats Collection documentation](https://docs.scrapy.org/en/latest/topics/stats.html) exposes runtime, request, error and duplicate metrics separately. We already persist request attempts and page accounting; the missing reporting detail was elapsed time between observations, not another crawler.

[dlt's official cursor-based incremental loading documentation](https://dlthub.com/docs/general-usage/incremental/cursor) describes cursor state, primary-key deduplication and ordering considerations. Our existing review-ID upserts and durable checkpoints remain in place. Bounded windows are not equivalent to complete incremental history, so overlap evidence must remain visible and comparable request modes must not be mixed.

The following changes are our own implementation decisions informed by these references, not claims that either project requires the same thresholds.

## Implemented improvements

1. **Observation cadence visibility.** Per-App summary groups now report elapsed hours, missing UTC observation dates and a 20-28-hour diagnostic band around daily observation. A date streak alone no longer hides a nine-hour or two-day interval. The band is a reporting convention, not John's requirement or a recommendation to enable daily scheduling.
2. **Separate collection and source quality.** Rows retain valid_collection for collection/storage accounting but expose source_quality_ok separately. Stale-source warnings and zero overlap with a preceding bounded window prevent a clean source-quality signal. Zero overlap is not labeled proven data loss. Missing comparison stays null rather than being invented as zero.
3. **Stricter report validation and comparability.** Negative, boolean and noninteger counts cannot pass accounting; inconsistent evaluation status, pages, review counts or missing newest timestamp cannot count as a valid observation. Duplicate App IDs are rejected. Offset timestamps sort by actual instants. overlap_run is included in protocol grouping so overlap-stopping and fixed-window experiments are not silently combined.

## Evidence

- Seven existing summary tests plus eight new regression tests pass (15 focused tests).
- Full offline suite: 100 tests passed.
- The three real recent reports were reprocessed; [enhanced summary](../samples/john_multiday_quality_2026-10-10.json) shows 9.21 and 48.79 hours and October 9 as missing for every App.
- Original experimental reports and earlier summary artifacts are unchanged; the enhanced summary is a new artifact.

## Second review pass

Two additional validation gaps were closed before publication: duplicate App evaluations now raise an error instead of silently overwriting evidence, and newest review timestamps must parse, include a timezone and not occur after collection. Invalid timestamps cannot contribute valid observation days. Two additional regression tests cover these cases. No new live collection was performed.

## Remaining limitations

These changes improve evidence quality, not review-source coverage. The current 200-record cap can produce disjoint windows; it cannot establish complete history. Duolingo's previously stale feed has recently advanced, but its underlying delay remains unknown. The experiment is not fixed-daily or three-consecutive-day testing. The centralized production database, deployment and scheduler remain outside this milestone.
