import { NextResponse } from "next/server";

export const runtime = "edge";
const ASIN = /^[A-Z0-9]{10}$/;
const ASIN_IN_URL = /(?:\/dp\/|\/product-reviews\/|\/gp\/product\/)([A-Z0-9]{10})(?:[/?]|$)/i;

function extractAsin(value: string) {
  const trimmed = value.trim();
  if (ASIN.test(trimmed.toUpperCase())) return trimmed.toUpperCase();
  const match = trimmed.match(ASIN_IN_URL);
  if (!match) throw new Error("Enter a 10-character Amazon ASIN or a valid Amazon product URL.");
  return match[1].toUpperCase();
}

function decodeHtml(value: string) {
  return value.replace(/<br\s*\/?\s*>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;|&#x27;|&apos;/gi, "'").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
}

function capture(block: string, hook: string) {
  const pattern = new RegExp(`data-hook=["']${hook}["'][^>]*>([\\s\\S]*?)<\\/[^>]+>`, "i");
  return decodeHtml(block.match(pattern)?.[1] ?? "");
}

function captureReviewBody(block: string) {
  const start = block.search(/data-hook=["'](?:review-body|reviewText)["']/i);
  if (start < 0) return "";
  const segment = block.slice(start, start + 16000);
  const candidates = [...segment.matchAll(/<span[^>]*>([\s\S]*?)<\/span>/gi)]
    .map((match) => decodeHtml(match[1]))
    .map((text) => text.replace(/Brief content visible, double tap to read full content\.|Full content visible, double tap to read brief content\.|Read more|Read less/gi, "").trim())
    .filter((text) => text.length > 5)
    .sort((a, b) => b.length - a.length);
  return candidates[0] ?? "";
}

function parseReviews(html: string, asin: string, sourceUrl: string) {
  const starts = [...html.matchAll(/<[^>]+data-hook=["']review["'][^>]*>/gi)];
  const reviews = [];
  for (let index = 0; index < starts.length && reviews.length < 25; index += 1) {
    const start = starts[index].index ?? 0;
    const end = starts[index + 1]?.index ?? Math.min(html.length, start + 80000);
    const block = html.slice(start, end);
    const id = block.match(/\bid=["']([^"']+)["']/i)?.[1] ?? `${asin}-${index + 1}`;
    const body = captureReviewBody(block);
    if (!body) continue;
    const ratingText = capture(block, "review-star-rating") || capture(block, "cmps-review-star-rating");
    const parsedRating = Number(ratingText.match(/([0-5](?:\.\d)?)/)?.[1] ?? "");
    reviews.push({ reviewId: id, productAsin: asin, title: capture(block, "review-title") || capture(block, "reviewTitle"), body, rating: Number.isFinite(parsedRating) ? parsedRating : null, reviewDate: capture(block, "review-date"), verifiedPurchase: /verified purchase/i.test(capture(block, "avp-badge")), sourceUrl });
  }
  return reviews;
}

function classify(html: string) {
  const lowered = html.toLowerCase();
  if (lowered.includes("enter the characters you see below") || lowered.includes("captcha")) return "captcha";
  if (/<title[^>]*>\s*(amazon )?sign-in\s*<\/title>/i.test(html)) return "sign_in";
  if (/data-hook=["']review["']/i.test(html)) return "reviews_present";
  if (lowered.includes("sorry! something went wrong")) return "error_page";
  return "accessible_no_reviews";
}

async function requestPage(url: string, attempt: number) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(url, { headers: { "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "accept-language": attempt % 2 ? "en-US,en;q=0.8" : "en-US,en;q=0.9", accept: "text/html,application/xhtml+xml" }, redirect: "follow", cache: "no-store", signal: controller.signal });
    return { response, html: await response.text() };
  } finally { clearTimeout(timer); }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as { product?: unknown };
    if (typeof body.product !== "string") return NextResponse.json({ error: "A product ASIN or URL is required." }, { status: 400 });
    const asin = extractAsin(body.product);
    const urls = [
      `https://www.amazon.com/product-reviews/${asin}/?reviewerType=all_reviews&pageNumber=1`,
      `https://www.amazon.com/dp/${asin}?th=1`,
      `https://www.amazon.com/dp/${asin}?ref_=cm_cr_arp_d_product_top`,
    ];
    let pageType = "request_error";
    let reviews: ReturnType<typeof parseReviews> = [];
    const checkedUrls: string[] = [];
    let requestError = "";
    for (const [attempt, url] of urls.entries()) {
      try {
        const { response, html } = await requestPage(url, attempt);
        checkedUrls.push(url); pageType = response.ok ? classify(html) : `http_${response.status}`;
        if (response.ok && pageType === "reviews_present") reviews = parseReviews(html, asin, response.url || url);
        if (reviews.length) break;
      } catch (reason) {
        checkedUrls.push(url);
        pageType = "request_error";
        requestError = reason instanceof Error ? reason.name : "RequestError";
      }
    }
    const collected = reviews.length > 0;
    return NextResponse.json({ asin, status: collected ? "collected" : "limited", pageType, reviews, checkedUrls, collectedAt: new Date().toISOString(), message: collected ? `${reviews.length} review${reviews.length === 1 ? " was" : "s were"} returned after ${checkedUrls.length} source check${checkedUrls.length === 1 ? "" : "s"}.` : requestError ? `Amazon could not be reached after ${checkedUrls.length} attempts. Try again in a few minutes.` : `No reviews were returned after ${checkedUrls.length} source checks. Amazon may return a different page on another run.` });
  } catch (reason) {
    const message = reason instanceof Error ? reason.message : "The collection request failed.";
    return NextResponse.json({ error: message }, { status: /ASIN|Amazon product URL/.test(message) ? 400 : 502 });
  }
}
