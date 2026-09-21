from __future__ import annotations

import hashlib
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse


ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
ASIN_IN_URL_RE = re.compile(
    r"/(?:dp|gp/product|product-reviews)/([A-Z0-9]{10})(?:[/?]|$)", re.IGNORECASE
)
STAR_RE = re.compile(r"([0-5](?:\.\d+)?)\s+out of\s+5", re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass(frozen=True)
class Review:
    review_id: str
    product_asin: str
    title: str
    body: str
    rating: float | None
    review_date: str
    variation: str
    verified_purchase: bool
    source_url: str
    collected_at: str


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int | None
    final_url: str
    title: str
    page_type: str
    response_bytes: int
    response_sha256: str
    reviews_extracted: int
    error: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(parts: list[str], field: str) -> str:
    value = " ".join(" ".join(parts).split())
    if field == "body":
        for phrase in (
            "Brief content visible, double tap to read full content.",
            "Full content visible, double tap to read brief content.",
        ):
            value = value.replace(phrase, "")
        value = re.sub(r"(?:Read more\s*)?(?:Read less\s*)?$", "", value).strip()
    return value


def extract_asin(value: str) -> str:
    candidate = value.strip().upper()
    if ASIN_RE.fullmatch(candidate):
        return candidate
    match = ASIN_IN_URL_RE.search(value)
    if not match:
        raise ValueError(f"Could not find a 10-character Amazon ASIN in: {value}")
    return match.group(1).upper()


def product_url(asin: str) -> str:
    return f"https://www.amazon.com/dp/{extract_asin(asin)}"


def review_url(asin: str) -> str:
    return (
        f"https://www.amazon.com/product-reviews/{extract_asin(asin)}/"
        "?reviewerType=all_reviews&pageNumber=1"
    )


def classify_page(html: str, title: str) -> str:
    lowered = html.lower()
    normalized_title = " ".join(title.lower().split())
    if "captcha" in lowered or "enter the characters you see below" in lowered:
        return "captcha"
    if normalized_title in {"sign in", "amazon sign-in"}:
        return "sign_in"
    if 'data-hook="review"' in lowered or "data-hook='review'" in lowered:
        return "reviews_present"
    if "sorry! something went wrong" in lowered:
        return "error_page"
    return "accessible_no_reviews"


class AmazonReviewParser(HTMLParser):
    """Extract a conservative subset of fields from Amazon review blocks."""

    FIELD_HOOKS = {
        "review-star-rating": "rating_text",
        "cmps-review-star-rating": "rating_text",
        "reviewTitle": "title",
        "review-title": "title",
        "review-date": "review_date",
        "product-variation-attributes": "variation",
        "reviewText": "body",
        "review-body": "body",
        "avp-badge": "verified",
    }

    def __init__(self, asin: str, source_url: str, collected_at: str):
        super().__init__(convert_charrefs=True)
        self.asin = asin
        self.source_url = source_url
        self.collected_at = collected_at
        self.depth = 0
        self.current: dict[str, str] | None = None
        self.captures: list[dict] = []
        self.reviews: list[Review] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: (value or "") for key, value in attrs}
        hook = attr.get("data-hook", "")
        if self.current is None and hook == "review":
            self.current = {"review_id": attr.get("id", "")}
            self.depth = 1
            return
        if self.current is None:
            return
        if tag not in VOID_TAGS:
            self.depth += 1
        field = self.FIELD_HOOKS.get(hook)
        if field:
            self.captures.append({"field": field, "depth": self.depth, "text": []})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self.current is None:
            return
        for capture in self.captures:
            capture["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        closing = [capture for capture in self.captures if capture["depth"] == self.depth]
        for capture in closing:
            field = capture["field"]
            value = clean_text(capture["text"], field)
            if value and not self.current.get(field):
                self.current[field] = value
            self.captures.remove(capture)
        if self.depth == 1:
            self._finish_review()
            self.current = None
            self.captures.clear()
            self.depth = 0
        elif tag not in VOID_TAGS:
            self.depth -= 1

    def _finish_review(self) -> None:
        if not self.current:
            return
        review_id = self.current.get("review_id", "").strip()
        body = self.current.get("body", "").strip()
        if not review_id or not body:
            return
        rating_text = self.current.get("rating_text", "")
        rating_match = STAR_RE.search(rating_text)
        rating = float(rating_match.group(1)) if rating_match else None
        self.reviews.append(
            Review(
                review_id=review_id,
                product_asin=self.asin,
                title=self.current.get("title", ""),
                body=body,
                rating=rating,
                review_date=self.current.get("review_date", ""),
                variation=self.current.get("variation", ""),
                verified_purchase="verified purchase"
                in self.current.get("verified", "").lower(),
                source_url=self.source_url,
                collected_at=self.collected_at,
            )
        )


def parse_reviews(html: str, asin: str, source_url: str, collected_at: str) -> list[Review]:
    parser = AmazonReviewParser(asin, source_url, collected_at)
    parser.feed(html)
    unique: dict[str, Review] = {}
    for review in parser.reviews:
        unique.setdefault(review.review_id, review)
    return list(unique.values())


def fetch_page(url: str, user_agent: str, timeout: float = 25.0) -> tuple[int, str, bytes]:
    host = urlparse(url).hostname or ""
    if host not in {"amazon.com", "www.amazon.com"}:
        raise ValueError(f"Unsupported host: {host}")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.geturl(), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.geturl(), exc.read()


def collect_from_url(
    url: str,
    asin: str,
    user_agent: str,
    timeout: float = 25.0,
) -> tuple[FetchResult, list[Review]]:
    collected_at = utc_now()
    try:
        status, final_url, raw = fetch_page(url, user_agent=user_agent, timeout=timeout)
        html = raw.decode("utf-8", errors="replace")
        title_match = TITLE_RE.search(html)
        title = unescape(" ".join(title_match.group(1).split())) if title_match else ""
        page_type = classify_page(html, title)
        reviews = (
            parse_reviews(html, asin, final_url, collected_at)
            if page_type == "reviews_present"
            else []
        )
        return (
            FetchResult(
                url=url,
                status=status,
                final_url=final_url,
                title=title,
                page_type=page_type,
                response_bytes=len(raw),
                response_sha256=hashlib.sha256(raw).hexdigest(),
                reviews_extracted=len(reviews),
                error=None,
            ),
            reviews,
        )
    except Exception as exc:  # preserve a diagnostic run record
        return (
            FetchResult(
                url=url,
                status=None,
                final_url=url,
                title="",
                page_type="request_error",
                response_bytes=0,
                response_sha256="",
                reviews_extracted=0,
                error=f"{type(exc).__name__}: {exc}",
            ),
            [],
        )


def collect_product(
    asin: str,
    user_agent: str,
    timeout: float = 25.0,
    delay_seconds: float = 2.0,
) -> tuple[list[FetchResult], list[Review]]:
    normalized_asin = extract_asin(asin)
    results: list[FetchResult] = []
    reviews: list[Review] = []
    urls: Iterable[str] = (review_url(normalized_asin), product_url(normalized_asin))
    for index, url in enumerate(urls):
        if index:
            time.sleep(max(delay_seconds, 0.0))
        result, current_reviews = collect_from_url(
            url, normalized_asin, user_agent=user_agent, timeout=timeout
        )
        results.append(result)
        reviews.extend(current_reviews)
        if current_reviews:
            break
    unique = {review.review_id: review for review in reviews}
    return results, list(unique.values())
