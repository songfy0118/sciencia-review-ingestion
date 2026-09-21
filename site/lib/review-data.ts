export type Review = {
  review_id: string;
  product_asin: string;
  title: string;
  body: string;
  rating: number | null;
  review_date: string | null;
  review_date_raw: string;
  variation: string;
  verified_purchase: boolean | null;
  source_url: string;
  collected_at: string;
};

export type SourceCheck = {
  url: string;
  http_status: number | null;
  outcome: string;
  reviews_found: number;
};

export type CollectResult = {
  schema_version: "1.0";
  run_id: string;
  asin: string;
  status: "collected" | "limited" | "error";
  coverage: "available_sample";
  reviews: Review[];
  checks: SourceCheck[];
  quality: { cards_seen: number; duplicates_removed: number; records_skipped: number };
  collected_at: string;
};

export const REVIEW_FIELDS = [
  "review_id", "product_asin", "title", "body", "rating", "review_date",
  "review_date_raw", "variation", "verified_purchase", "source_url", "collected_at",
] as const;

export function extractAsin(value: string) {
  const trimmed = value.trim();
  if (/^[A-Z0-9]{10}$/i.test(trimmed)) return trimmed.toUpperCase();
  let url: URL;
  try { url = new URL(trimmed); } catch { throw new Error("Enter a 10-character ASIN or a full Amazon.com product URL."); }
  if (!/^https?:$/.test(url.protocol) || !["amazon.com", "www.amazon.com"].includes(url.hostname) || url.username || url.password) {
    throw new Error("Use an Amazon.com product URL. Other stores and Amazon regions are not supported yet.");
  }
  const match = url.pathname.match(/\/(?:dp|gp\/product|product-reviews)\/([A-Z0-9]{10})(?:\/|$)/i);
  if (!match) throw new Error("This URL does not contain a product ASIN. Copy the product page URL from Amazon.com.");
  return match[1].toUpperCase();
}

export function normalizeDate(raw: string): string | null {
  const months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
  const iso = raw.match(/^([12]\d{3})-(\d{2})-(\d{2})$/);
  const english = raw.match(/(?:^|\bon\s+)([A-Za-z]+)\s+(\d{1,2}),\s+([12]\d{3})$/i);
  if (!iso && !english) return null;
  const year = Number(iso?.[1] ?? english?.[3]);
  const month = iso ? Number(iso[2]) - 1 : months.indexOf(english![1].toLowerCase());
  const day = Number(iso?.[3] ?? english?.[2]);
  if (month < 0 || month > 11) return null;
  const date = new Date(Date.UTC(year, month, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month && date.getUTCDate() === day ? date.toISOString().slice(0, 10) : null;
}

// CSV is spreadsheet-safe; JSON retains the exact normalized text.
export function toCsv(reviews: Review[]) {
  function cell(value: unknown) {
    let text = value == null ? "" : String(value);
    if (typeof value === "string" && /^[\s]*[=+@-]/.test(text)) text = "'" + text;
    return `"${text.replaceAll('"', '""')}"`;
  }
  return "\ufeff" + [REVIEW_FIELDS, ...reviews.map((review) => REVIEW_FIELDS.map((field) => review[field]))]
    .map((row) => row.map(cell).join(",")).join("\r\n") + "\r\n";
}

export function sourceLabel(outcome: string) {
  const labels: Record<string, string> = {
    reviews_present: "Reviews available", no_reviews: "No reviews on this page",
    request_error: "Connection failed", timeout: "Request timed out", sign_in: "Sign-in required",
    captcha: "Verification required", error_page: "Amazon returned an error",
    parsing_failed: "Review layout not recognized", redirect_blocked: "Unexpected redirect",
  };
  return labels[outcome] ?? (outcome.startsWith("http_") ? `HTTP ${outcome.slice(5)}` : "Source unavailable");
}

export function resultMessage(result: CollectResult) {
  if (result.reviews.length) return { title: "Reviews collected", text: "This is a sample from the pages Amazon returned, not the full review history." };
  const outcomes = result.checks.map((check) => check.outcome);
  if (outcomes.every((outcome) => ["request_error", "timeout"].includes(outcome))) return { title: "Could not reach Amazon", text: "The connection failed or timed out. Please try again later." };
  if (outcomes.includes("parsing_failed")) return { title: "Could not read the reviews", text: "The page contained review cards, but their fields could not be read reliably. No records were exported." };
  if (outcomes.includes("sign_in") || outcomes.includes("captcha")) return { title: "Amazon limited review access", text: "Amazon requested sign-in or verification on one or more pages. No usable reviews were available from this run." };
  return { title: "No reviews retrieved", text: "The pages returned no usable reviews. This does not mean the product has no reviews. You can try again later." };
}
