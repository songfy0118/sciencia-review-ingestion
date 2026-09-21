import { extractAsin, type CollectResult, type SourceCheck } from "./review-data";
import { parseAmazonPage } from "./amazon-parser";

export async function collectReviews(input: string, fetchPage: typeof fetch = fetch): Promise<CollectResult> {
  let asin: string;
  try { asin = extractAsin(input); } catch (reason) { throw new RangeError((reason as Error).message); }
  const collectedAt = new Date().toISOString();
  const urls = [
    `https://www.amazon.com/product-reviews/${asin}/?reviewerType=all_reviews&pageNumber=1`,
    `https://www.amazon.com/dp/${asin}?th=1`,
    `https://www.amazon.com/dp/${asin}?ref_=cm_cr_arp_d_product_top`,
  ];
  const checks: SourceCheck[] = [];
  const quality = { cards_seen: 0, duplicates_removed: 0, records_skipped: 0 };
  let reviews: CollectResult["reviews"] = [];
  for (const url of urls) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetchPage(url, {
        headers: { "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "accept-language": "en-US,en;q=0.9", accept: "text/html" },
        redirect: "manual", cache: "no-store", signal: controller.signal,
      });
      let outcome = `http_${response.status}`;
      if (response.status >= 300 && response.status < 400) {
        const location = response.headers.get("location") ?? "";
        outcome = /\/ap\/signin(?:[/?]|$)/i.test(location) ? "sign_in" : "redirect_blocked";
        await response.body?.cancel();
      } else if (response.ok) {
        const parsed = await parseAmazonPage(await response.text(), asin, response.url || url, collectedAt);
        outcome = parsed.outcome;
        quality.cards_seen += parsed.quality.cards_seen;
        quality.records_skipped += parsed.quality.records_skipped;
        quality.duplicates_removed += parsed.quality.duplicates_removed;
        if (outcome === "reviews_present") reviews = parsed.reviews;
      } else { await response.body?.cancel(); }
      checks.push({ url, http_status: response.status, outcome, reviews_found: reviews.length });
    } catch (reason) {
      if (!(reason instanceof Error)) throw reason;
      checks.push({ url, http_status: null, outcome: controller.signal.aborted ? "timeout" : "request_error", reviews_found: 0 });
    } finally { clearTimeout(timer); }
    if (reviews.length) break;
    if (checks.length < urls.length) await new Promise((resolve) => setTimeout(resolve, 350));
  }
  const failed = checks.every((check) => ["request_error", "timeout"].includes(check.outcome));
  return {
    schema_version: "1.0", run_id: crypto.randomUUID(), asin,
    status: reviews.length ? "collected" : failed ? "error" : "limited", coverage: "available_sample",
    reviews, checks, quality, collected_at: collectedAt,
  };
}
