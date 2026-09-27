from __future__ import annotations

import argparse
import json
from pathlib import Path

from .storage import write_json


def summarize(reports: list[dict]) -> dict:
    if len(reports) < 2:
        raise ValueError("At least two run reports are required.")
    run_summaries = []
    signatures = []
    for report in reports:
        fetch_signature = []
        for product in report.get("products", []):
            for fetch in product.get("fetches", []):
                fetch_signature.append(
                    {
                        "requested_url": fetch.get("url"),
                        "status": fetch.get("status"),
                        "page_type": fetch.get("page_type"),
                        "reviews_extracted": fetch.get("reviews_extracted", 0),
                    }
                )
        signature = {
            "reviews_extracted": report.get("reviews_extracted", 0),
            "fetches": fetch_signature,
        }
        signatures.append(signature)
        run_summaries.append(
            {
                "run_id": report.get("run_id"),
                "started_at": report.get("started_at"),
                **signature,
            }
        )
    repeatable = all(signature == signatures[0] for signature in signatures[1:])
    return {
        "runs_compared": len(reports),
        "repeatable": repeatable,
        "runs": run_summaries,
        "finding": (
            "The tested responses were consistent across runs."
            if repeatable
            else "The same input produced different review availability across consecutive runs."
        ),
        "recommendation": (
            "Continue only as a controlled prototype and add more scheduled checks."
            if repeatable
            else "Do not use anonymous Amazon HTML as the primary recurring source without "
            "authorized, stable access; evaluate an approved API/provider or alternative source."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two or more ingestion run reports.")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    summary = summarize(reports)
    write_json(args.output, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

