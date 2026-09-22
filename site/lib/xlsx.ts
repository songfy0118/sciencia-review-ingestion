import type { CollectResult, Review } from "./review-data";

const encoder = new TextEncoder();

function xml(value: unknown) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function columnName(index: number) {
  let name = "";
  for (let value = index + 1; value; value = Math.floor((value - 1) / 26)) {
    name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
  }
  return name;
}

function inlineCell(reference: string, value: unknown, style: number) {
  return `<c r="${reference}" t="inlineStr" s="${style}"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
}

function numberCell(reference: string, value: number, style: number) {
  return `<c r="${reference}" s="${style}"><v>${value}</v></c>`;
}

function reviewRow(review: Review, row: number) {
  const shaded = row % 2 === 1;
  const textStyle = shaded ? 7 : 2;
  const centerStyle = shaded ? 8 : 3;
  const numberStyle = shaded ? 9 : 4;
  const values = [
    review.product_asin,
    review.review_id,
    review.rating,
    review.review_date ?? "Not available",
    review.verified_purchase == null ? "Not stated" : review.verified_purchase ? "Yes" : "No",
    review.variation || "Not stated",
    review.title || "Untitled review",
    review.body,
    review.review_date_raw,
    review.source_url,
    review.collected_at,
  ];
  const cells = values.map((value, index) => {
    const ref = `${columnName(index)}${row}`;
    if (index === 2 && typeof value === "number") return numberCell(ref, value, numberStyle);
    return inlineCell(ref, value, index < 6 || index === 10 ? centerStyle : textStyle);
  }).join("");
  return `<row r="${row}" ht="72" customHeight="1">${cells}</row>`;
}

function reviewsSheet(result: CollectResult) {
  const headers = ["Product ASIN", "Review ID", "Rating", "Review date", "Verified purchase", "Variation", "Title", "Review text", "Original date text", "Source URL", "Collected at"];
  const header = headers.map((value, index) => inlineCell(`${columnName(index)}1`, value, 1)).join("");
  const rows = result.reviews.map((review, index) => reviewRow(review, index + 2)).join("");
  const lastRow = Math.max(1, result.reviews.length + 1);
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:K${lastRow}"/>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="18"/>
  <cols><col min="1" max="1" width="14" customWidth="1"/><col min="2" max="2" width="19" customWidth="1"/><col min="3" max="3" width="10" customWidth="1"/><col min="4" max="4" width="14" customWidth="1"/><col min="5" max="5" width="18" customWidth="1"/><col min="6" max="6" width="26" customWidth="1"/><col min="7" max="7" width="34" customWidth="1"/><col min="8" max="8" width="76" customWidth="1"/><col min="9" max="9" width="35" customWidth="1"/><col min="10" max="10" width="48" customWidth="1"/><col min="11" max="11" width="25" customWidth="1"/></cols>
  <sheetData><row r="1" ht="38" customHeight="1">${header}</row>${rows}</sheetData>
  <autoFilter ref="A1:K${lastRow}"/>
</worksheet>`;
}

function summarySheet(result: CollectResult) {
  const rated = result.reviews.flatMap((review) => review.rating == null ? [] : [review.rating]);
  const average = rated.length ? rated.reduce((sum, value) => sum + value, 0) / rated.length : null;
  const summaryRows: Array<[string, string | number]> = [
    ["Product ASIN", result.asin],
    ["Run ID", result.run_id],
    ["Status", result.status],
    ["Coverage", "Available sample; completeness not verified"],
    ["Reviews collected", result.reviews.length],
    ["Sample average", average == null ? "Not available" : Number(average.toFixed(2))],
    ["Pages checked", result.checks.length],
    ["Review cards found", result.quality.cards_seen],
    ["Duplicates removed", result.quality.duplicates_removed],
    ["Invalid records skipped", result.quality.records_skipped],
    ["Collected at", result.collected_at],
  ];
  const rows = summaryRows.map(([label, value], index) => {
    const row = index + 3;
    const valueCell = typeof value === "number" ? numberCell(`B${row}`, value, 4) : inlineCell(`B${row}`, value, 2);
    return `<row r="${row}" ht="23" customHeight="1">${inlineCell(`A${row}`, label, 6)}${valueCell}</row>`;
  }).join("");
  const checkStart = summaryRows.length + 5;
  const checkHeaders = ["Request", "Outcome", "HTTP status", "Reviews found", "URL"]
    .map((value, index) => inlineCell(`${columnName(index)}${checkStart}`, value, 1)).join("");
  const checks = result.checks.map((check, index) => {
    const row = checkStart + index + 1;
    return `<row r="${row}" ht="34" customHeight="1">${inlineCell(`A${row}`, index + 1, 3)}${inlineCell(`B${row}`, check.outcome, 3)}${inlineCell(`C${row}`, check.http_status ?? "Not available", 3)}${numberCell(`D${row}`, check.reviews_found, 4)}${inlineCell(`E${row}`, check.url, 2)}</row>`;
  }).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:E${Math.max(checkStart, checkStart + result.checks.length)}"/>
  <sheetViews><sheetView workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="18"/>
  <cols><col min="1" max="1" width="25" customWidth="1"/><col min="2" max="2" width="52" customWidth="1"/><col min="3" max="4" width="16" customWidth="1"/><col min="5" max="5" width="76" customWidth="1"/></cols>
  <sheetData>
    <row r="1" ht="26" customHeight="1">${inlineCell("A1", "Collection run summary", 5)}</row>
    ${rows}
    <row r="${checkStart - 1}" ht="24" customHeight="1">${inlineCell(`A${checkStart - 1}`, "Source checks", 5)}</row>
    <row r="${checkStart}" ht="34" customHeight="1">${checkHeaders}</row>${checks}
  </sheetData>
  <autoFilter ref="A${checkStart}:E${Math.max(checkStart, checkStart + result.checks.length)}"/>
</worksheet>`;
}

function crc32(data: Uint8Array) {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function join(parts: Uint8Array[]) {
  const output = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) { output.set(part, offset); offset += part.length; }
  return output;
}

function zip(files: Array<[string, string]>) {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;
  for (const [path, content] of files) {
    const name = encoder.encode(path);
    const data = encoder.encode(content);
    const checksum = crc32(data);
    const local = new Uint8Array(30 + name.length + data.length);
    const localView = new DataView(local.buffer);
    localView.setUint32(0, 0x04034b50, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0x0800, true);
    localView.setUint32(14, checksum, true);
    localView.setUint32(18, data.length, true);
    localView.setUint32(22, data.length, true);
    localView.setUint16(26, name.length, true);
    local.set(name, 30);
    local.set(data, 30 + name.length);
    localParts.push(local);

    const central = new Uint8Array(46 + name.length);
    const centralView = new DataView(central.buffer);
    centralView.setUint32(0, 0x02014b50, true);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0x0800, true);
    centralView.setUint32(16, checksum, true);
    centralView.setUint32(20, data.length, true);
    centralView.setUint32(24, data.length, true);
    centralView.setUint16(28, name.length, true);
    centralView.setUint32(42, offset, true);
    central.set(name, 46);
    centralParts.push(central);
    offset += local.length;
  }
  const locals = join(localParts);
  const central = join(centralParts);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, files.length, true);
  endView.setUint16(10, files.length, true);
  endView.setUint32(12, central.length, true);
  endView.setUint32(16, locals.length, true);
  return join([locals, central, end]);
}

export function toXlsx(result: CollectResult) {
  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`;
  const relationships = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`;
  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Reviews" sheetId="1" r:id="rId1"/><sheet name="Run summary" sheetId="2" r:id="rId2"/></sheets></workbook>`;
  const workbookRelationships = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`;
  const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="4"><font><sz val="10"/><name val="Times New Roman"/></font><font><b/><sz val="12"/><name val="Times New Roman"/></font><font><b/><sz val="10"/><name val="Times New Roman"/></font><font><b/><sz val="14"/><name val="Times New Roman"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE2E8EF"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD9D9D9"/></left><right style="thin"><color rgb="FFD9D9D9"/></right><top style="thin"><color rgb="FFD9D9D9"/></top><bottom style="thin"><color rgb="FFD9D9D9"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="10"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf><xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;
  return zip([
    ["[Content_Types].xml", contentTypes],
    ["_rels/.rels", relationships],
    ["xl/workbook.xml", workbook],
    ["xl/_rels/workbook.xml.rels", workbookRelationships],
    ["xl/styles.xml", styles],
    ["xl/worksheets/sheet1.xml", reviewsSheet(result)],
    ["xl/worksheets/sheet2.xml", summarySheet(result)],
  ]);
}
