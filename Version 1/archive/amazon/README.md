# Amazon prototype — archived

This was the first source-feasibility experiment. Some requests returned real reviews: the saved September 21 test extracted 13 records. Other requests for the same product returned no reviews or a sign-in page. The result was useful, but access was not reliable enough for recurring collection.

Amazon development is paused. The active Google Play pipeline is described in the [Version 2 README](../../../Version%202/README.md). No new Amazon requests were made during this reorganization.

## What is preserved

| Location | Contents |
| --- | --- |
| [FINDINGS.md](FINDINGS.md) | Tested behavior, results and source decision |
| [samples/](samples/) | Historical run reports and the review CSV sample |
| `amazon.py`, `cli.py`, `storage.py`, `repeatability.py` | Original Python collector, database writer and run comparison |
| `import_web.py` | Validates the old website's review JSON and imports it into SQLite |
| [site/](site/) | Original Amazon website, parser and Excel/JSON/SQL exports |
| [docs/](docs/) | Amazon data contract and prior quality checks |
| [tests/](tests/) | Python fixtures and regression tests |
| [config/](config/) | Original product input example |

The archive preserves the original limitations. Its code and reports do not establish complete review coverage or reliable current Amazon access. The website's build-tool documentation remains in `site/README.md` for historical reproducibility.

## Local checks

Run from the **Version 1** folder using the existing Python environment:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s archive/amazon/tests -v
..\.venv\Scripts\python.exe -m archive.amazon.cli --help
..\.venv\Scripts\python.exe -m archive.amazon.import_web --help
```

The Python module prefix is now `archive.amazon`, replacing the old `review_ingestion` prefix for Amazon commands. Relative input and output paths are resolved from your working directory. Do not use the Google Play database for Amazon imports.

Website checks run from `archive/amazon/site` with its existing Node dependencies: `npm test` and `npm run typecheck`. The main public website now serves Version 2; this source remains available for historical review.
