import { NextResponse } from "next/server";
import { collectReviews } from "../../../lib/collector";

export const runtime = "edge";

export async function POST(request: Request) {
  let body: unknown;
  try { body = await request.json(); } catch {
    return NextResponse.json({ error: "Send a JSON object with a product ASIN or URL." }, { status: 400 });
  }
  if (!body || typeof body !== "object" || !("product" in body) || typeof body.product !== "string" || body.product.length > 2048) {
    return NextResponse.json({ error: "Enter one Amazon ASIN or product URL." }, { status: 400 });
  }
  try {
    return NextResponse.json(await collectReviews(body.product), { headers: { "cache-control": "no-store" } });
  } catch (reason) {
    if (reason instanceof RangeError) return NextResponse.json({ error: reason.message }, { status: 400 });
    console.error("Review collection failed", reason);
    return NextResponse.json({ error: "The run could not be completed. Please try again later." }, { status: 500 });
  }
}
