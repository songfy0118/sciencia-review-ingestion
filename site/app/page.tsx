"use client";

import { FormEvent, useMemo, useState } from "react";
import { CheckCircle2, Database, Download, Loader2, Search, ShieldAlert } from "lucide-react";

type Review = {
  reviewId: string;
  productAsin: string;
  title: string;
  body: string;
  rating: number | null;
  reviewDate: string;
  verifiedPurchase: boolean;
  sourceUrl: string;
};

type CollectResult = {
  asin: string;
  status: "collected" | "limited" | "error";
  pageType: string;
  reviews: Review[];
  checkedUrls: string[];
  message: string;
  collectedAt: string;
};

const EXAMPLE = "B09XS7JWHH";

function csvCell(value: unknown) {
  const content = value == null ? "" : String(value);
  return `"${content.replaceAll('"', '""')}"`;
}

function downloadFile(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function sourceLabel(pageType: string) {
  const labels: Record<string, string> = {
    reviews_present: "Reviews available",
    accessible_no_reviews: "No reviews returned",
    request_error: "Request failed",
    sign_in: "Sign-in page returned",
    captcha: "Verification page returned",
    error_page: "Source error",
  };
  return labels[pageType] ?? pageType.replaceAll("_", " ");
}

export default function Home() {
  const [input, setInput] = useState(EXAMPLE);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CollectResult | null>(null);
  const [error, setError] = useState("");

  const average = useMemo(() => {
    const ratings = result?.reviews.map((review) => review.rating).filter((rating): rating is number => rating != null) ?? [];
    return ratings.length ? ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length : null;
  }, [result]);

  async function collect(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch("/api/collect", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ product: input }),
      });
      const data = (await response.json()) as CollectResult & { error?: string };
      if (!response.ok) throw new Error(data.error || "The run could not be completed.");
      setResult(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The run could not be completed.");
    } finally {
      setLoading(false);
    }
  }

  function downloadCsv() {
    if (!result?.reviews.length) return;
    const headers = ["review_id", "product_asin", "title", "body", "rating", "review_date", "verified_purchase", "source_url"];
    const rows = result.reviews.map((review) => [review.reviewId, review.productAsin, review.title, review.body, review.rating, review.reviewDate, review.verifiedPurchase, review.sourceUrl]);
    const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
    downloadFile(`${result.asin}-reviews.csv`, `\ufeff${csv}`, "text/csv;charset=utf-8");
  }

  function downloadJson() {
    if (!result?.reviews.length) return;
    downloadFile(`${result.asin}-reviews.json`, JSON.stringify(result.reviews, null, 2), "application/json");
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brandMark">S</span><span>Sciencia</span><span className="brandSection">Review Collector</span></div>
        <span className="prototypeTag">Prototype</span>
      </header>

      <section className="workspace">
        <div className="intro">
          <p className="eyebrow">AMAZON US</p>
          <h1>Collect product reviews</h1>
          <p className="lede">Enter an Amazon ASIN or product URL to retrieve the reviews currently available and export them as structured data.</p>
        </div>

        <form className="collector" onSubmit={collect}>
          <label htmlFor="product">Amazon ASIN or product URL</label>
          <div className="inputRow">
            <div className="inputWrap"><Search size={18} /><input id="product" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Example: B09XS7JWHH" /></div>
            <button type="submit" disabled={loading || !input.trim()}>{loading ? <><Loader2 className="spin" size={17} />Running</> : "Run collection"}</button>
          </div>
          <p className="inputHelp">Accepts a 10-character ASIN or an amazon.com product URL.</p>
        </form>

        {error && <div className="notice error"><ShieldAlert size={20} /><div><strong>Run failed</strong><p>{error}</p></div></div>}

        {!result && !error && !loading && (
          <section className="aboutPanel">
            <div><strong>Output fields</strong><p>Review ID, ASIN, rating, title, review text, date, verified purchase status, and source URL.</p></div>
            <div><strong>Current scope</strong><p>One product per run. Results can be downloaded as CSV or JSON.</p></div>
            <div><strong>Source access</strong><p>Uses public Amazon pages. The collector does not sign in or bypass access controls.</p></div>
          </section>
        )}

        {result && (
          <section className="results">
            <div className={`notice ${result.status === "collected" ? "success" : "warning"}`}>
              {result.status === "collected" ? <CheckCircle2 size={20} /> : <ShieldAlert size={20} />}
              <div><strong>{result.status === "collected" ? "Collection complete" : "No reviews returned"}</strong><p>{result.message}</p></div>
            </div>

            <div className="runMeta">
              <span>Run completed {new Date(result.collectedAt).toLocaleString("en-US")}</span>
              <span>{result.checkedUrls.length} source check{result.checkedUrls.length === 1 ? "" : "s"}</span>
            </div>

            <div className="metrics">
              <article><small>ASIN</small><strong>{result.asin}</strong></article>
              <article><small>REVIEWS RETURNED</small><strong>{result.reviews.length}</strong></article>
              <article><small>AVERAGE RATING</small><strong>{average == null ? "—" : `${average.toFixed(1)} / 5`}</strong></article>
              <article><small>SOURCE STATUS</small><strong>{sourceLabel(result.pageType)}</strong></article>
            </div>

            <div className="tablePanel">
              <div className="tableHeader">
                <div><Database size={18} /><strong>Review records</strong></div>
                <div className="downloadGroup">
                  <button className="secondary" onClick={downloadJson} disabled={!result.reviews.length}><Download size={15} />JSON</button>
                  <button className="secondary" onClick={downloadCsv} disabled={!result.reviews.length}><Download size={15} />CSV</button>
                </div>
              </div>
              {result.reviews.length ? (
                <div className="tableScroll"><table><thead><tr><th>Rating</th><th>Review</th><th>Date</th><th>Verified purchase</th></tr></thead><tbody>{result.reviews.map((review) => <tr key={review.reviewId}><td className="rating">{review.rating == null ? "—" : review.rating.toFixed(1)}</td><td><strong>{review.title || "Untitled review"}</strong><p>{review.body}</p><small className="reviewId">{review.reviewId}</small></td><td>{review.reviewDate || "—"}</td><td>{review.verifiedPurchase ? "Yes" : "No"}</td></tr>)}</tbody></table></div>
              ) : (
                <div className="noRows"><strong>No review records were returned.</strong><p>Amazon may return a different page depending on the request. Wait a moment and run the same product again.</p></div>
              )}
            </div>
          </section>
        )}
      </section>

      <footer><span>Sciencia Review Collector</span><span>Collection and structured export prototype</span></footer>
    </main>
  );
}
