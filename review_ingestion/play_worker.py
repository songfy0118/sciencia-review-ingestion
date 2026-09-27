"""Isolated, version-pinned upstream adapter: one request, no swallowed errors.

Run only through play_pipeline.fetch_page. The subprocess isolates upstream SSL
side effects and allows the parent to enforce an overall wall-clock timeout.
"""
from __future__ import annotations

import importlib
import json
import ssl
import sys
from importlib.metadata import version
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .google_play import datetime_text


def validate_response(body: str, pattern) -> None:
    """Reject unknown pagination shapes before upstream's silent fallback."""
    try:
        envelope = json.loads(pattern.findall(body)[0])
        payload = json.loads(envelope[0][2])
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise ValueError('Unrecognized Google Play review response') from exc
    if (not isinstance(payload, list) or len(payload) != 3
            or not isinstance(payload[0], list)
            or not isinstance(payload[1], list) or len(payload[1]) != 2):
        raise ValueError('Unrecognized pagination structure; source end is not confirmed')
    token = payload[1][1]
    if token is not None and (not isinstance(token, str) or not token):
        raise ValueError('Invalid continuation token; source end is not confirmed')


def fetch(request: dict) -> dict:
    if version("google-play-scraper") != "1.2.7":
        raise RuntimeError("Adapter requires google-play-scraper==1.2.7")
    original_context = ssl._create_default_https_context
    try:
        module = importlib.import_module("google_play_scraper.features.reviews")
    finally:
        ssl._create_default_https_context = original_context
    context = ssl.create_default_context()

    def post(url, data, headers):
        if isinstance(data, str):
            data = data.encode("utf-8")
        with urlopen(Request(url, data=data, headers=headers),
                     timeout=request["timeout"], context=context) as response:
            body = response.read().decode("utf-8")
        if "com.google.play.gateway.proto.PlayGatewayError" in body:
            raise RuntimeError("Google Play gateway rejected this request")
        # _fetch_review_items() also swallows token parsing errors, converting
        # them into None. Validate the observed response shape before it runs.
        validate_response(body, module.Regex.REVIEWS)
        return body

    # The public reviews() catches transport/parser errors and returns an empty
    # list. Use its single-page primitive so failures reach our job log instead.
    module.post = post
    items, token = module._fetch_review_items(
        module.Formats.Reviews.build(lang=request["lang"], country=request["country"]),
        request["app_id"], module.Sort.NEWEST.value, request["count"],
        None, None, request.get("cursor"),
    )
    if token is not None and not isinstance(token, str):
        raise ValueError("Unexpected continuation-token shape")
    records = []
    for item in items:
        record = {key: spec.extract_content(item)
                  for key, spec in module.ElementSpecs.Review.items()}
        for field in ("at", "repliedAt"):
            record[field] = datetime_text(record[field])
        records.append(record)
    return {"records": records, "cursor": token or None}


def main() -> None:
    try:
        result = fetch(json.load(sys.stdin))
        output = {"ok": True, **result}
    except Exception as exc:
        retryable = isinstance(exc, (TimeoutError, URLError))
        if isinstance(exc, HTTPError):
            retryable = exc.code in (408, 429, 500, 502, 503, 504)
        output = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                  "retryable": retryable}
    sys.stdout.write(json.dumps(output, ensure_ascii=True))


if __name__ == "__main__":
    main()
