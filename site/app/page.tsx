"use client";

import { FormEvent, useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, Database, Download, Loader2, Search, ShieldAlert } from "lucide-react";

type Review = { reviewId: string; productAsin: string; title: string; body: string; rating: number | null; reviewDate: string; verifiedPurchase: boolean; sourceUrl: string };
type CollectResult = { asin: string; status: "collected" | "limited" | "error"; pageType: string; reviews: Review[]; checkedUrls: string[]; message: string; collectedAt: string };
const EXAMPLE = "B09XS7JWHH";

function csvCell(value: unknown) {
  const content = value == null ? "" : String(value);
  return `"${content.replaceAll('"', '""')}"`;
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
    event.preventDefault(); setLoading(true); setError(""); setResult(null);
    try {
      const response = await fetch("/api/collect", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ product: input }) });
      const data = (await response.json()) as CollectResult & { error?: string };
      if (!response.ok) throw new Error(data.error || "The collection request failed.");
      setResult(data);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The collection request failed."); }
    finally { setLoading(false); }
  }

  function downloadCsv() {
    if (!result?.reviews.length) return;
    const headers = ["review_id", "product_asin", "title", "body", "rating", "review_date", "verified_purchase", "source_url"];
    const rows = result.reviews.map((r) => [r.reviewId, r.productAsin, r.title, r.body, r.rating, r.reviewDate, r.verifiedPurchase, r.sourceUrl]);
    const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `${result.asin}-reviews.csv`; link.click(); URL.revokeObjectURL(url);
  }

  return <main>
    <header className="topbar"><div className="brand"><span className="brandMark">S</span><span>Sciencia Review Ingestion</span></div><div className="prototypeTag"><span /> Feasibility prototype</div></header>
    <section className="workspace">
      <div className="intro"><p className="eyebrow">LIVE SOURCE TEST · AMAZON US</p><h1>Turn a product ID into structured review data.</h1><p className="lede">Enter one Amazon ASIN or product URL. The workflow checks the live source, extracts available reviews, and returns a clean inspection table.</p></div>
      <form className="collector" onSubmit={collect}>
        <label htmlFor="product">Product ASIN or URL</label>
        <div className="inputRow"><div className="inputWrap"><Search size={19} /><input id="product" value={input} onChange={(event) => setInput(event.target.value)} placeholder="B09XS7JWHH or an amazon.com/dp/... URL" /></div><button type="submit" disabled={loading || !input.trim()}>{loading ? <><Loader2 className="spin" size={18} />Checking source</> : <>Collect reviews <ArrowRight size={18} /></>}</button></div>
        <div className="formMeta"><span>Source: Amazon.com</span><span>One product per run</span><span>No login or CAPTCHA bypass</span></div>
      </form>
      {error && <div className="notice error"><ShieldAlert size={21} /><div><strong>Request failed</strong><p>{error}</p></div></div>}
      {!result && !error && !loading && <section className="emptyState"><div className="pipeline"><div><span>01</span><strong>Identify</strong><small>Normalize ASIN or URL</small></div><div><span>02</span><strong>Collect</strong><small>Request the live source</small></div><div><span>03</span><strong>Structure</strong><small>Clean review fields</small></div><div><span>04</span><strong>Inspect</strong><small>Review and export CSV</small></div></div></section>}
      {result && <section className="results">
        <div className={`notice ${result.status === "collected" ? "success" : "warning"}`}>{result.status === "collected" ? <CheckCircle2 size={21} /> : <ShieldAlert size={21} />}<div><strong>{result.status === "collected" ? "Live reviews collected" : "Live access limitation detected"}</strong><p>{result.message}</p></div></div>
        <div className="metrics"><article><small>PRODUCT</small><strong>{result.asin}</strong></article><article><small>REVIEWS FOUND</small><strong>{result.reviews.length}</strong></article><article><small>AVERAGE RATING</small><strong>{average == null ? "—" : average.toFixed(1)}</strong></article><article><small>PAGE RESULT</small><strong>{result.pageType.replaceAll("_", " ")}</strong></article></div>
        <div className="tablePanel"><div className="tableHeader"><div><Database size={18} /><strong>Structured output</strong></div><button className="secondary" onClick={downloadCsv} disabled={!result.reviews.length}><Download size={16} />Download CSV</button></div>
          {result.reviews.length ? <div className="tableScroll"><table><thead><tr><th>Rating</th><th>Title &amp; review</th><th>Date</th><th>Verified</th></tr></thead><tbody>{result.reviews.map((review) => <tr key={review.reviewId}><td className="rating">{review.rating ?? "—"}</td><td><strong>{review.title || "Untitled review"}</strong><p>{review.body}</p></td><td>{review.reviewDate || "—"}</td><td>{review.verifiedPurchase ? "Yes" : "—"}</td></tr>)}</tbody></table></div> : <div className="noRows"><ShieldAlert size={26} /><strong>No review rows were exposed to this anonymous request.</strong><p>This is a valid feasibility result. Amazon can return sign-in, CAPTCHA, or review-free variants depending on the request context.</p></div>}
        </div>
      </section>}
    </section>
    <footer><span>Prototype scope: collection and structuring only.</span><span>CSV is for inspection; the repository includes SQLite storage.</span></footer>
  </main>;
}
