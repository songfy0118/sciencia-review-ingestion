"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDownToLine, Check, ChevronRight, CircleAlert, Database, ExternalLink, Loader2, Search } from "lucide-react";
import { extractAsin, resultMessage, sourceLabel, toSqliteSql, type CollectResult } from "../lib/review-data";
import { toXlsx } from "../lib/xlsx";

const EXAMPLE = "B09XS7JWHH";

function download(filename: string, data: BlobPart, type: string) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Home() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CollectResult | null>(null);
  const [error, setError] = useState("");
  const [inputError, setInputError] = useState("");
  const [query, setQuery] = useState("");
  const [ratingFilter, setRatingFilter] = useState("all");
  const [downloadNote, setDownloadNote] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLHeadingElement>(null);

  const visibleReviews = useMemo(() => (result?.reviews ?? []).filter((review) =>
    (ratingFilter === "all" || review.rating === Number(ratingFilter)) &&
    (review.title + " " + review.body + " " + review.review_id).toLowerCase().includes(query.trim().toLowerCase()),
  ), [result, query, ratingFilter]);
  const average = useMemo(() => {
    const ratings = (result?.reviews ?? []).flatMap((review) => review.rating == null ? [] : [review.rating]);
    return ratings.length ? (ratings.reduce((sum, value) => sum + value, 0) / ratings.length).toFixed(1) : null;
  }, [result]);
  const message = result ? resultMessage(result) : null;

  async function collect(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    setError("");
    setInputError("");
    let asin: string;
    try { asin = extractAsin(input); } catch (reason) {
      setInputError((reason as Error).message);
      inputRef.current?.focus();
      return;
    }
    setLoading(true);
    setResult(null);
    setQuery("");
    setRatingFilter("all");
    setDownloadNote("");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch("/api/collect", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ product: asin }), signal: controller.signal });
      const data = await response.json() as CollectResult & { error?: string };
      if (!response.ok) throw new Error(data.error || "The run could not be completed. Please try again.");
      setResult(data as CollectResult);
      requestAnimationFrame(() => resultRef.current?.focus({ preventScroll: true }));
    } catch (reason) {
      setError(controller.signal.aborted ? "This run took too long. Please try again later." : reason instanceof TypeError ? "Could not connect to the server. Check your connection and try again." : reason instanceof Error ? reason.message : "The run could not be completed. Please try again.");
    } finally { clearTimeout(timer); setLoading(false); }
  }

  function exportExcel() {
    if (!result?.reviews.length) return;
    download(`${result.asin}-review-workbook.xlsx`, toXlsx(result), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    setDownloadNote(`Excel download started. The Reviews and Run summary sheets include all ${result.reviews.length} records.`);
  }

  function exportJson() {
    if (!result?.reviews.length) return;
    download(`${result.asin}-reviews.json`, JSON.stringify(result.reviews, null, 2) + "\n", "application/json");
    setDownloadNote(`Review JSON download started. All ${result.reviews.length} records are included.`);
  }

  function exportSql() {
    if (!result?.reviews.length) return;
    download(`${result.asin}-sqlite-import.sql`, toSqliteSql(result), "application/sql;charset=utf-8");
    setDownloadNote(`SQLite import download started. It creates the products, reviews, and ingestion_runs tables.`);
  }

  return (
    <>
      <a className="skipLink" href="#workspace">Skip to collection</a>
      <header className="topbar">
        <Link className="brand" href="/" aria-label="Sciencia Product Review Data home"><Database size={21} aria-hidden="true" /><strong>Sciencia</strong><span>Product Review Data</span></Link>
        <span className="tag">Research preview</span>
      </header>
      <main id="workspace" className="workspace">
        <div className="pageHeading">
          <p className="eyebrow">PRODUCT DATA / AMAZON US</p>
          <h1>Amazon review data</h1>
          <p>Collect available reviews for one product. Inspect the records, then download your data.</p>
        </div>

        <div className="setupGrid">
          <section className="panel inputPanel" aria-labelledby="input-heading">
            <h2 id="input-heading">Product</h2>
            <form onSubmit={collect} noValidate>
              <label htmlFor="product">Amazon ASIN or product URL</label>
              <div className="inputRow">
                <div className={`inputWrap ${inputError ? "invalid" : ""}`}><Search size={18} aria-hidden="true" /><input ref={inputRef} id="product" name="product" autoComplete="off" autoCapitalize="off" spellCheck={false} value={input} disabled={loading} aria-invalid={!!inputError} aria-describedby={inputError ? "product-error product-help" : "product-help"} onChange={(event) => { setInput(event.target.value); setInputError(""); }} placeholder="Paste an ASIN or https://www.amazon.com/dp/..." /></div>
                <button type="submit" className="primary" disabled={loading}>{loading ? <><Loader2 size={17} className="spin" aria-hidden="true" />Collecting…</> : "Collect reviews"}</button>
              </div>
              <p id="product-help" className="help">An ASIN is Amazon’s 10-character product ID. Amazon.com links only.</p>
              {inputError && <p id="product-error" className="fieldError" role="alert">{inputError}</p>}
              <button className="textButton" type="button" disabled={loading} onClick={() => { setInput(EXAMPLE); setInputError(""); inputRef.current?.focus(); }}>Use example: {EXAMPLE}</button>
            </form>
          </section>
          <aside className="scopePanel" aria-labelledby="scope-heading">
            <h2 id="scope-heading">What to expect</h2>
            <p>A sample of publicly available reviews. This preview does not collect the full review history.</p>
            <ul><li>One product per run</li><li>Up to three page requests</li><li>Original review text and language</li></ul>
          </aside>
        </div>

        <div className="liveStatus" role="status" aria-live="polite">
          {loading && <div className="loadingState"><Loader2 size={19} className="spin" aria-hidden="true" /><div><strong>Checking Amazon for available reviews</strong><p>This can take up to 40 seconds.</p></div></div>}
        </div>
        {error && <div className="notice error" role="alert"><CircleAlert size={19} aria-hidden="true" /><div><strong>Collection failed</strong><p>{error}</p></div></div>}

        {!result && !loading && <section className="panel readyPanel" aria-labelledby="ready-heading"><Database size={26} aria-hidden="true" /><h2 id="ready-heading">Your results will appear here</h2><p>Enter a product above to get started. Each record includes the review text, rating, date, and source.</p></section>}

        {result && message && <section aria-labelledby="results-heading" className="results">
          <div className="sectionHeading"><h2 ref={resultRef} tabIndex={-1} id="results-heading">Collection results</h2><span>{new Date(result.collected_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })}</span></div>
          <div role="status" className={`notice ${result.status === "collected" ? "success" : result.status === "error" ? "error" : "warning"}`}>
            {result.reviews.length ? <Check size={19} aria-hidden="true" /> : <CircleAlert size={19} aria-hidden="true" />}
            <div><strong>{message.title}</strong><p>{message.text}</p></div>
          </div>
          <dl className="metrics">
            <div><dt>Product ASIN</dt><dd><a href={`https://www.amazon.com/dp/${result.asin}`} target="_blank" rel="noreferrer">{result.asin}<ExternalLink size={13} aria-hidden="true" /><span className="srOnly"> on Amazon (opens in a new tab)</span></a></dd></div>
            <div><dt>Reviews collected</dt><dd>{result.reviews.length}<small> in this run</small></dd></div>
            <div><dt>Sample average</dt><dd>{average ?? "—"}{average && <small> / 5 stars</small>}</dd></div>
            <div><dt>Pages checked</dt><dd>{result.checks.length}<small> of 3 maximum</small></dd></div>
          </dl>

          <section className="panel recordsPanel" aria-labelledby="records-heading">
            <div className="tableHeader">
              <div><h3 id="records-heading">Review records <span className="count">{result.reviews.length}</span></h3><p>Choose the file that matches how you will use the data.</p></div>
              <div className="exportControls" aria-label="Download collected review data">
                <button className="secondary" onClick={exportExcel} disabled={!result.reviews.length}><ArrowDownToLine size={16} aria-hidden="true" />Excel workbook</button>
                <button className="secondary" onClick={exportJson} disabled={!result.reviews.length}><ArrowDownToLine size={16} aria-hidden="true" />Review JSON</button>
                <button className="secondary" onClick={exportSql} disabled={!result.reviews.length}><ArrowDownToLine size={16} aria-hidden="true" />SQLite import</button>
              </div>
            </div>
            <div className="exportGuide"><span><strong>Excel</strong> formatted for review</span><span><strong>JSON</strong> normalized review records</span><span><strong>SQL</strong> creates and fills a SQLite database</span></div>
            <p className="srOnly" role="status">{downloadNote}</p>
            {result.reviews.length > 0 ? <>
              <div className="tableTools">
                <label className="filterSearch"><Search size={16} aria-hidden="true" /><span className="srOnly">Search collected reviews</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search these reviews" /></label>
                <label className="ratingFilter">Rating<select value={ratingFilter} onChange={(event) => setRatingFilter(event.target.value)}><option value="all">All ratings</option>{[5, 4, 3, 2, 1].map((rating) => <option key={rating} value={rating}>{rating} {rating === 1 ? "star" : "stars"}</option>)}</select></label>
                <span role="status">{visibleReviews.length} of {result.reviews.length} shown</span>
              </div>
              {visibleReviews.length ? <div className="tableScroll" tabIndex={0} role="region" aria-label="Collected reviews table, scroll horizontally on small screens"><table>
                <caption className="srOnly">Reviews collected for {result.asin}. Average and count describe this sample only.</caption>
                <thead><tr><th scope="col">Rating</th><th scope="col">Review</th><th scope="col">Review date</th><th scope="col">Verified purchase</th></tr></thead>
                <tbody>{visibleReviews.map((review) => <tr key={review.review_id}>
                  <td className="rating">{review.rating == null ? <span title="Rating was not available">—</span> : <>{review.rating.toFixed(1)}<small> / 5</small></>}</td>
                  <td className="reviewCell"><details className="reviewDetail"><summary><strong>{review.title || "Untitled review"}</strong><span className="reviewPreview">{review.body.slice(0, 180)}{review.body.length > 180 ? "…" : ""}</span><span className="readLink"><ChevronRight size={13} aria-hidden="true" />Full review</span></summary><p className="reviewBody">{review.body}</p>{review.variation && <p className="help">{review.variation}</p>}</details><div className="reviewMeta"><code>{review.review_id}</code><a href={review.source_url} target="_blank" rel="noreferrer">Source<span className="srOnly"> for {review.review_id} (opens in a new tab)</span><ExternalLink size={11} aria-hidden="true" /></a></div></td>
                  <td className="dateCell">{review.review_date ? <time dateTime={review.review_date} title={review.review_date_raw}>{review.review_date}</time> : review.review_date_raw || "Not available"}</td>
                  <td><span className={review.verified_purchase ? "verified" : "muted"}>{review.verified_purchase ? "Verified" : "Not stated"}</span></td>
                </tr>)}</tbody>
              </table></div> : <div className="noRows"><h3>No matching reviews</h3><p>Try a different search or rating.</p><button className="textButton" onClick={() => { setQuery(""); setRatingFilter("all"); }}>Clear filters</button></div>}
            </> : <div className="noRows"><Database size={24} aria-hidden="true" /><h3>No records to download</h3><p>{message.text}</p></div>}
          </section>

          <details className="runDetails"><summary>Run details and data checks</summary>
            <p className="help">Run ID: <code>{result.run_id}</code></p>
            <ul className="checkList">{result.checks.map((check, index) => <li key={check.url}><span>Page {index + 1}: {sourceLabel(check.outcome)}</span><a href={check.url} target="_blank" rel="noreferrer">View page<span className="srOnly"> {index + 1} (opens in a new tab)</span></a></li>)}</ul>
            <p>{result.quality.cards_seen} review cards found · {result.quality.duplicates_removed} duplicate records removed · {result.quality.records_skipped} records skipped because the ID or text was missing or invalid.</p>
            <p className="help"><strong>Technical log:</strong> this file records page checks and quality counts. It is not the review-data file and is not used for database import.</p>
            <button className="textButton" onClick={() => download(`${result.asin}-technical-run-log.json`, JSON.stringify(result, null, 2) + "\n", "application/json")}>Download technical run log</button>
          </details>
        </section>}

        <details className="fieldGuide"><summary>About the data and exports</summary>
          <div className="guideGrid">
            <div><h3>Files for people and programs</h3><p>The Excel workbook follows the supplied research-table style: clear headers, fixed widths, wrapped text, filters, a frozen header row, and a separate run-summary sheet.</p><p>The Review JSON contains only normalized review records. The technical run log is separate so it cannot be confused with data intended for import.</p></div>
            <div><h3>SQLite storage</h3><p>The SQLite import is a readable SQL script. Import it into SQLite to create three related tables: products, reviews, and ingestion_runs. Review IDs and ASINs prevent duplicate rows.</p><p>This site does not retain visitor data. Download a file before leaving. Coverage remains an available sample until pagination and source-total checks are implemented.</p></div>
          </div>
        </details>
      </main>
      <footer><span>Sciencia · Product Review Data</span><span>Amazon.com · Available reviews only</span></footer>
    </>
  );
}
