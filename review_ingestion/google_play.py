from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable


APP_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")


@dataclass(frozen=True)
class GooglePlayApp:
    app_id: str
    label: str
    title: str
    developer: str
    genre: str
    source_url: str


@dataclass(frozen=True)
class GooglePlayReview:
    app_id: str
    review_id: str
    author_name: str
    content: str
    score: int
    thumbs_up_count: int
    review_created_version: str | None
    review_at: str
    reply_content: str | None
    replied_at: str | None
    source_url: str
    collected_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def content_hash(self) -> str:
        value = f"{self.score}\n{self.content}\n{self.reply_content or ''}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_app_id(value: str) -> str:
    app_id = value.strip()
    if not APP_ID_PATTERN.fullmatch(app_id):
        raise ValueError(f"Invalid Google Play app ID: {value!r}")
    return app_id


def app_url(app_id: str, lang: str = "en", country: str = "us") -> str:
    return f"https://play.google.com/store/apps/details?id={validate_app_id(app_id)}&hl={lang}&gl={country}"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value).replace("\x00", "")).strip()


def optional_text(value: Any) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def datetime_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    text = clean_text(value)
    return text or None


def normalize_review(
    raw: dict[str, Any],
    *,
    app_id: str,
    source_url: str,
    collected_at: str,
) -> GooglePlayReview:
    review_id = clean_text(raw.get("reviewId"))
    content = clean_text(raw.get("content"))
    score = raw.get("score")
    if not review_id:
        raise ValueError("Review is missing reviewId.")
    if not content:
        raise ValueError(f"Review {review_id} has no content.")
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
        raise ValueError(f"Review {review_id} has an invalid score.")
    review_at = datetime_text(raw.get("at"))
    if not review_at:
        raise ValueError(f"Review {review_id} has no timestamp.")
    thumbs = raw.get("thumbsUpCount", 0)
    if isinstance(thumbs, bool) or not isinstance(thumbs, int) or thumbs < 0:
        thumbs = 0
    return GooglePlayReview(
        app_id=app_id,
        review_id=review_id,
        author_name=clean_text(raw.get("userName")),
        content=content,
        score=score,
        thumbs_up_count=thumbs,
        review_created_version=optional_text(raw.get("reviewCreatedVersion") or raw.get("appVersion")),
        review_at=review_at,
        reply_content=optional_text(raw.get("replyContent")),
        replied_at=datetime_text(raw.get("repliedAt")),
        source_url=source_url,
        collected_at=collected_at,
    )


def collect_app(
    app_id: str,
    *,
    label: str = "",
    lang: str = "en",
    country: str = "us",
    count: int = 100,
    app_fetcher: Callable[..., dict[str, Any]] | None = None,
    review_fetcher: Callable[..., tuple[list[dict[str, Any]], Any]] | None = None,
    newest_sort: Any = None,
) -> tuple[GooglePlayApp, list[GooglePlayReview], bool, int]:
    app_id = validate_app_id(app_id)
    if not 1 <= count <= 200:
        raise ValueError("count must be between 1 and 200 for one bounded request.")
    if app_fetcher is None or review_fetcher is None:
        try:
            from google_play_scraper import Sort, app, reviews
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -r requirements.txt") from exc
        app_fetcher = app
        review_fetcher = reviews
        newest_sort = Sort.NEWEST

    collected_at = utc_now()
    source_url = app_url(app_id, lang, country)
    metadata = app_fetcher(app_id, lang=lang, country=country)
    raw_reviews, continuation_token = review_fetcher(
        app_id,
        lang=lang,
        country=country,
        sort=newest_sort,
        count=count,
    )

    normalized: list[GooglePlayReview] = []
    skipped = 0
    seen: set[str] = set()
    for raw in raw_reviews:
        try:
            review = normalize_review(
                raw,
                app_id=app_id,
                source_url=source_url,
                collected_at=collected_at,
            )
        except (TypeError, ValueError):
            skipped += 1
            continue
        if review.review_id in seen:
            skipped += 1
            continue
        seen.add(review.review_id)
        normalized.append(review)

    app_record = GooglePlayApp(
        app_id=app_id,
        label=clean_text(label) or clean_text(metadata.get("title")) or app_id,
        title=clean_text(metadata.get("title")) or app_id,
        developer=clean_text(metadata.get("developer")),
        genre=clean_text(metadata.get("genre")),
        source_url=source_url,
    )
    return app_record, normalized, continuation_token is not None, skipped
