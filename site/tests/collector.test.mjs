import { test, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { Miniflare } from "miniflare";
import ts from "typescript";

const compiled = ["review-data", "amazon-parser", "collector"].map((name) => {
  const source = readFileSync(new URL(`../lib/${name}.ts`, import.meta.url), "utf8");
  return ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText.replace(/^import .*?;\s*$/gm, "");
}).join("\n");

const worker = new Miniflare({ modules: true, compatibilityDate: "2026-05-15", script: compiled + `
export default { async fetch(request) {
  const data = await request.json();
  try {
    if (data.op === 'input') return Response.json({ asin: extractAsin(data.input) });
    if (data.op === 'date') return Response.json({ date: normalizeDate(data.raw) });
    if (data.op === 'csv') return new Response(toCsv(data.reviews));
    if (data.op === 'collect') {
      let index = 0;
      const mockFetch = async () => {
        const item = data.responses[index++];
        if (item.error) throw new TypeError('Connection failed');
        return new Response(item.html || '', { status: item.status || 200, headers: item.headers || {} });
      };
      const result = await collectReviews(data.input, mockFetch);
      return Response.json({ ...result, message: resultMessage(result) });
    }
    return Response.json(await parseAmazonPage(data.html, 'B09XS7JWHH', 'https://www.amazon.com/dp/B09XS7JWHH', '2026-09-21T00:00:00.000Z'));
  } catch(error) { return Response.json({error:error.message}, {status:400}); }
} };` });
after(() => worker.dispose());

async function call(data) {
  const response = await worker.dispatchFetch("https://test.invalid", { method: "POST", body: JSON.stringify(data) });
  return response.json();
}
function card(id, text, extra = "") { return `<div id="${id}" data-hook="review">${extra}<div data-hook="reviewText">${text}</div><span>Sending feedback...</span></div>`; }

test("accepts only supported ASINs and Amazon.com URLs", async () => {
  for (const input of [" b09xs7jwhh ", "https://www.amazon.com/name/dp/B09XS7JWHH?th=1", "https://amazon.com/gp/product/B09XS7JWHH#reviews"]) assert.equal((await call({op:"input",input})).asin,"B09XS7JWHH");
  for (const input of ["Sony headphones", "https://evil.example/dp/B09XS7JWHH", "https://amazon.com.evil.example/dp/B09XS7JWHH", "https://amazon.co.uk/dp/B09XS7JWHH", "https://evil@amazon.com/dp/B09XS7JWHH", "ftp://amazon.com/dp/B09XS7JWHH"]) assert.ok((await call({op:"input",input})).error, input);
});

test("keeps every paragraph and short reviews, excludes text outside the body", async () => {
  const html = card("RFULL", '<p><span>First &amp; best.</span></p><p><span>Second paragraph.</span></p><p>Last &#x1F44D; &lt;3.</p><button>Read more</button>') + card("RSHORT", "OK") + card("REMPTY", "");
  const result = await call({html});
  assert.equal(result.reviews.length, 2);
  assert.equal(result.reviews[0].body, "First & best.\nSecond paragraph.\nLast 👍 <3.");
  assert.equal(result.reviews[1].body, "OK");
  assert.equal(result.quality.records_skipped, 1);
});

test("extracts rich content, excludes accessibility controls and does not remove prose", async () => {
  const html = card("RRICH", '<div class="a-teaser-describedby-collapsed">Brief content visible, double tap to read full content.</div><div data-hook="reviewRichContentContainer"><p>Read more books.</p><p>I like it.</p></div><button>Read less</button>');
  const result = await call({html});
  assert.equal(result.reviews[0].body, "Read more books.\nI like it.");
});

test("normalizes ratings and dates, preserves unknown values", async () => {
  const extra = '<a data-hook="review-title"><i>4.0 out of 5 stars</i><span>Works well</span></a><i data-hook="review-star-rating"><span>4.0 out of 5 stars</span></i><span data-hook="review-date">Reviewed in the United States on September 1, 2026</span><span data-hook="avp-badge">Verified Purchase</span>';
  const result = await call({html:card("RKNOWN","Good.",extra)+card("RUNKNOWN","Fine.")});
  assert.equal(result.reviews[0].rating, 4);
  assert.equal(result.reviews[0].title, "Works well");
  assert.equal(result.reviews[0].review_date, "2026-09-01");
  assert.equal(result.reviews[0].verified_purchase, true);
  assert.equal(result.reviews[1].rating, null);
  assert.equal(result.reviews[1].review_date, null);
  assert.equal(result.reviews[1].verified_purchase, null);
  for(const raw of ["February 30, 2026", "2026-02-30", "Reviewed on 01/02/2026", "Unknown 3, 2026"]) assert.equal((await call({op:"date",raw})).date,null);
});

test("deduplicates real IDs, rejects missing IDs and UI-only text", async () => {
  const result=await call({html:card("RDUP","Short.")+card("RDUP","A longer, complete review.")+card("","Missing ID.")+card("RUI","Sending feedback...")});
  assert.equal(result.reviews.length,1);
  assert.equal(result.reviews[0].body,"A longer, complete review.");
  assert.equal(result.quality.duplicates_removed,1);
  assert.equal(result.quality.records_skipped,2);
});

test("does not mistake captcha script references for an access barrier", async () => {
  assert.equal((await call({html:'<script src="captcha.js"></script>'+card("ROK","Valid.")})).outcome,"reviews_present");
  assert.equal((await call({html:'<title>Amazon Sign-In</title>'})).outcome,"sign_in");
  assert.equal((await call({html:'<form action="/errors/validateCaptcha"><input id="captchacharacters"></form>'})).outcome,"captcha");
});

test("does not truncate at 25 records", async () => {
  const html=Array.from({length:30},(_,i)=>card(`R${i}`,`Review ${i}.`)).join("");
  assert.equal((await call({html})).reviews.length,30);
});

test("repeated field elements do not duplicate titles or variation values", async () => {
  const extra='<h5 data-hook="reviewTitle">My title</h5><h5 data-hook="reviewTitle">My title</h5><div data-hook="product-variation-attributes"><a data-hook="format-strip">Color: Black</a><span data-hook="avp-badge">Verified Purchase</span></div>';
  const result=await call({html:card("RREPEAT","Body &amp;lt; stays encoded once.",extra)});
  assert.equal(result.reviews[0].title,"My title");
  assert.equal(result.reviews[0].variation,"Color: Black");
  assert.equal(result.reviews[0].body,"Body &lt; stays encoded once.");
});

test("records each outcome and stops when actual reviews are found", async () => {
  const result=await call({op:"collect",input:"B09XS7JWHH",responses:[{status:302,headers:{location:"/ap/signin"}},{html:card("RLIVE","Valid review.")}]});
  assert.equal(result.checks.length,2);
  assert.equal(result.checks[0].outcome,"sign_in");
  assert.equal(result.reviews.length,1);
  assert.equal(result.coverage,"available_sample");
});

test("mixed failures never claim every request failed", async () => {
  const result=await call({op:"collect",input:"B09XS7JWHH",responses:[{error:true},{html:"<h1>Product</h1>"},{html:"<h1>Product</h1>"}]});
  assert.equal(result.status,"limited");
  assert.equal(result.message.title,"No reviews retrieved");
  const failed=await call({op:"collect",input:"B09XS7JWHH",responses:[{error:true},{error:true},{error:true}]});
  assert.equal(failed.status,"error");
  assert.equal(failed.message.title,"Could not reach Amazon");
});

test("CSV preserves quotes and line breaks and neutralizes spreadsheet formulas", async () => {
  const parsed=await call({html:card("RCSV",'<p>=1+1, "quoted"</p><p>Second line.</p>')});
  const response=await worker.dispatchFetch("https://test.invalid",{method:"POST",body:JSON.stringify({op:"csv",reviews:parsed.reviews})});
  const csv=await response.text();
  assert.ok(csv.includes(`"'=1+1, ""quoted""\nSecond line."`));
  assert.equal(parsed.reviews[0].body,'=1+1, "quoted"\nSecond line.');
  const output=resolve(".sites-runtime/audit"); mkdirSync(output,{recursive:true});
  writeFileSync(resolve(output,"fixture-export.json"),JSON.stringify(parsed.reviews));
  writeFileSync(resolve(output,"fixture-export.csv"),csv);
});

test("live HTML audit: all paragraphs stay within the review text", {skip:!existsSync(resolve(".sites-runtime/audit/source.html"))}, async () => {
  const html=readFileSync(resolve(".sites-runtime/audit/source.html"),"utf8");
  const result=await call({html});
  assert.ok(result.reviews.length>0);
  assert.ok(result.reviews.every((row)=>row.body!=="Sending feedback..."));
  const first=result.reviews.find((row)=>row.review_id==="R296H0MM1B5KU8");
  if(first) { assert.ok(first.body.includes("Greetings")); assert.ok(first.body.includes("Weight")); assert.ok(first.body.includes("Bluetooth")); }
  writeFileSync(resolve(".sites-runtime/audit/live-export.json"),JSON.stringify(result.reviews,null,2));
  console.log("Live source audit:", result.reviews.length, "records; first body", result.reviews[0].body.length, "characters;", result.quality);
});
