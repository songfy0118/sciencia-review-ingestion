from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from .amazon import collect_product, extract_asin, product_url, utc_now
from .storage import connect, export_csv, save_run, upsert_product, upsert_reviews, write_json


DEFAULT_USER_AGENT = (
    "ScienciaReviewFeasibility/0.1 (limited academic feasibility test)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a limited Amazon review-ingestion test.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--delay", type=float, default=2.0)
    return parser.parse_args()


def load_products(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Input must be a non-empty JSON list.")
    products = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each product must be a JSON object.")
        source = str(item.get("asin") or item.get("url") or "")
        asin = extract_asin(source)
        products.append({"asin": asin, "label": str(item.get("label") or asin)})
    return products


def main() -> int:
    args = parse_args()
    products = load_products(args.input)
    user_agent = os.getenv("REVIEW_INGESTION_USER_AGENT", DEFAULT_USER_AGENT)
    run_id = str(uuid.uuid4())
    started_at = utc_now()
    all_reviews = []
    product_reports = []

    connection = connect(args.db)
    try:
        for product in products:
            asin = product["asin"]
            fetches, reviews = collect_product(
                asin,
                user_agent=user_agent,
                timeout=args.timeout,
                delay_seconds=args.delay,
            )
            updated_at = utc_now()
            upsert_product(
                connection,
                asin=asin,
                label=product["label"],
                source_url=product_url(asin),
                updated_at=updated_at,
            )
            upsert_reviews(connection, reviews)
            all_reviews.extend(reviews)
            product_reports.append(
                {
                    "asin": asin,
                    "label": product["label"],
                    "reviews_extracted": len(reviews),
                    "fetches": [fetch.to_dict() for fetch in fetches],
                }
            )

        completed_at = utc_now()
        page_types = {
            fetch["page_type"]
            for product in product_reports
            for fetch in product["fetches"]
        }
        if all_reviews and "sign_in" in page_types:
            status = "collected_with_limits"
            recommendation = (
                "The product-page fallback yielded reviews, but the dedicated review endpoint "
                "required sign-in. Continue only as a controlled prototype and verify repeatability."
            )
        elif all_reviews:
            status = "collected"
            recommendation = "Proceed with a controlled ingestion prototype."
        else:
            status = "limited"
            recommendation = (
                "Do not rely on anonymous Amazon HTML for recurring collection; evaluate an "
                "authorized source or alternative live review source."
            )
        report = {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "status": status,
            "products_requested": len(products),
            "reviews_extracted": len(all_reviews),
            "page_types_seen": sorted(page_types),
            "products": product_reports,
            "recommendation": recommendation,
        }
        export_csv(args.csv, all_reviews)
        write_json(args.report, report)
        save_run(connection, run_id, started_at, completed_at, status, report)
        connection.commit()
    finally:
        connection.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
