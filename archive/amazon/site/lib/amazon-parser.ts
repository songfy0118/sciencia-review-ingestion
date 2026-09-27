import { normalizeDate, type Review } from "./review-data";

function decodeText(text: string) {
  const named: Record<string, string> = { amp: "&", quot: '"', apos: "'", lt: "<", gt: ">", nbsp: " ", ndash: "–", mdash: "—", hellip: "…", lsquo: "‘", rsquo: "’", ldquo: "“", rdquo: "”", copy: "©", reg: "®", trade: "™" };
  return text.replace(/&(#x[\da-f]+|#\d+|[a-z]+);/gi, (entity, key: string) => {
    if (!key.startsWith("#")) return named[key] ?? entity;
    const code = key[1].toLowerCase() === "x" ? parseInt(key.slice(2), 16) : Number(key.slice(1));
    return code > 0 && code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff) ? String.fromCodePoint(code) : "�";
  });
}

function clean(text: string) {
  return decodeText(text).replace(/\r\n?/g, "\n").replace(/[\t\f\v ]+/g, " ").replace(/ *\n */g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

type Field = "title" | "body" | "rich_body" | "rating" | "date" | "verified" | "variation" | "variation_raw";
type Card = { id: string; fields: Partial<Record<Field, string>> };

/** Use the platform HTML parser: text must stay inside its actual review/field element. */
export async function parseAmazonPage(html: string, asin: string, sourceUrl: string, collectedAt: string) {
  const cards: Card[] = [];
  let current: Card | null = null;
  let suppressed = 0;
  let title = "";
  let challenge = false;
  const fieldHooks: [string, Field][] = [
    ["review-title", "title"], ["reviewTitle", "title"], ["review-body", "body"],
    ["reviewText", "body"], ["reviewRichContentContainer", "rich_body"],
    ["review-star-rating", "rating"], ["cmps-review-star-rating", "rating"],
    ["review-date", "date"], ["avp-badge", "verified"], ["format-strip", "variation"],
    ["product-variation-attributes", "variation_raw"],
  ];
  const rewriter = new HTMLRewriter()
    .on("title", { text(chunk) { title += chunk.text; } })
    .on('form[action*="validateCaptcha"], input#captchacharacters', { element() { challenge = true; } })
    .on('[data-hook="review"]', { element(element) {
      current = { id: element.getAttribute("id") ?? "", fields: {} };
      const card = current;
      cards.push(card);
      element.onEndTag(() => { if (current === card) current = null; });
    } });

  // Suppress interface controls inside a field, without deleting review prose containing the same words.
  for (const selector of ["script", "style", "button", '[aria-hidden="true"]', ".a-teaser-describedby-collapsed", ".a-teaser-describedby-expanded", ".a-expander-prompt"]) {
    rewriter.on(`[data-hook="review"] ${selector}`, { element(element) {
      if (["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"].includes(element.tagName)) return;
      suppressed += 1;
      element.onEndTag(() => { suppressed -= 1; });
    } });
  }
  for (const [hook, field] of fieldHooks) {
    // A page can repeat a field in a media dialog. Keep a complete occurrence,
    // rather than concatenating separate copies of the title or body.
    const captures: { card: Card; text: string }[] = [];
    rewriter.on(`[data-hook="review"] [data-hook="${hook}"]`, {
      element(element) {
        if (!current) return;
        const capture = { card: current, text: "" };
        captures.push(capture);
        element.onEndTag(() => {
          const text = clean(capture.text);
          if (text.length > (capture.card.fields[field]?.length ?? 0)) capture.card.fields[field] = text;
          captures.splice(captures.indexOf(capture), 1);
        });
      },
      text(chunk) {
        const capture = captures[captures.length - 1];
        if (capture && !suppressed) capture.text += chunk.text;
      },
    });
    for (const tag of ["p", "br", "li"]) {
      rewriter.on(`[data-hook="review"] [data-hook="${hook}"] ${tag}`, { element() {
        const capture = captures[captures.length - 1];
        if (capture && !suppressed) capture.text += "\n";
      } });
    }
  }
  await rewriter.transform(new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } })).arrayBuffer();

  let skipped = 0;
  let duplicates = 0;
  const unique = new Map<string, Review>();
  for (const card of cards) {
    const id = card.id.trim();
    const body = card.fields.rich_body || card.fields.body || "";
    if (!/^R[A-Z0-9]+$/.test(id) || !body || /^(Sending feedback\.{0,3}|Read more|Read less|Report abuse|Helpful)$/i.test(body)) { skipped += 1; continue; }
    const ratingMatch = (card.fields.rating ?? "").match(/(?:^|\s)([1-5](?:[.,]\d+)?)\s+(?:out of|von|de)\s+5\b/i);
    const rating = ratingMatch ? Number(ratingMatch[1].replace(",", ".")) : null;
    const dateRaw = card.fields.date ?? "";
    const row: Review = {
      review_id: id, product_asin: asin,
      title: (card.fields.title ?? "").replace(/^[1-5](?:\.\d+)?\s+out of\s+5\s+stars\s*/i, ""),
      body, rating: rating != null && rating >= 1 && rating <= 5 ? rating : null,
      review_date: normalizeDate(dateRaw), review_date_raw: dateRaw,
      variation: card.fields.variation || (card.fields.variation_raw ?? "").replace(/Verified Purchase\s*$/i, "").trim(),
      verified_purchase: /verified purchase/i.test(card.fields.verified ?? "") ? true : null,
      source_url: sourceUrl, collected_at: collectedAt,
    };
    const previous = unique.get(id);
    if (previous) duplicates += 1;
    if (!previous || row.body.length > previous.body.length) unique.set(id, row);
  }
  const reviews = [...unique.values()];
  const pageTitle = clean(title);
  const outcome = challenge || /robot check|captcha/i.test(pageTitle) ? "captcha"
    : /^(?:Amazon\s*[-:.]?\s*)?sign[ -]?in$/i.test(pageTitle) ? "sign_in"
      : reviews.length ? "reviews_present" : cards.length ? "parsing_failed"
        : /sorry.*something went wrong/i.test(pageTitle) ? "error_page" : "no_reviews";
  return { reviews, outcome, quality: { cards_seen: cards.length, duplicates_removed: duplicates, records_skipped: skipped } };
}
