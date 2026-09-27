// Wire format and field paths correspond to google-play-scraper 1.2.7.
// See THIRD_PARTY.md. This adapter uses Workers fetch; the Python pipeline remains intact.
export class InputError extends Error {}
export function parseApp(value) {
  if (typeof value !== 'string' || value.length > 1000) throw new InputError('Enter a Google Play link or app ID.');
  let id = value.trim();
  if (id.includes('://')) {
    let url;
    try { url = new URL(id); } catch { throw new InputError('Use a valid Google Play app link.'); }
    if (url.protocol !== 'https:' || url.host !== 'play.google.com' || url.pathname !== '/store/apps/details' || url.searchParams.getAll('id').length !== 1) {
      throw new InputError('Use a Google Play app link, such as https://play.google.com/store/apps/details?id=com.ubercab');
    }
    id = url.searchParams.get('id');
  }
  if (id.length > 200 || !/^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$/.test(id)) throw new InputError('Use the app ID from its Google Play link, not just its name. Example: com.ubercab');
  return id;
}
const clean = value => typeof value === 'string' ? value.replaceAll('\0', '').normalize('NFC').trim() : '';
function timestamp(value) {
  if (!Number.isFinite(value) || value < 0) throw new Error('Review timestamp is missing or invalid.');
  return new Date(value * 1000).toISOString();
}
export function requestBody(appId, cursor = null) {
  const size = cursor ? [25, null, cursor] : [25];
  const args = [null, [2, 2, size, null, [null, null, null, null, null, null, null, null, null]], [appId, 7]];
  return new URLSearchParams({'f.req': JSON.stringify([[['oCPfdb', JSON.stringify(args), null, 'generic']]])}).toString();
}
export function parseResponse(body, appId, observedAt) {
  const prefix = ")]}'\n\n";
  if (!body.startsWith(prefix)) throw new Error('Google Play returned an unexpected response. No records were saved.');
  let payload;
  try { payload = JSON.parse(JSON.parse(body.slice(prefix.length))[0][2]); }
  catch { throw new Error('Google Play response could not be read. No records were saved.'); }
  if (!Array.isArray(payload) || payload.length !== 3 || !Array.isArray(payload[0]) || !Array.isArray(payload[1]) || payload[1].length !== 2) {
    throw new Error('Google Play pagination format changed. Source completion cannot be confirmed.');
  }
  const cursor = payload[1][1];
  if (cursor !== null && (typeof cursor !== 'string' || !cursor || cursor.length > 20000)) throw new Error('Google Play returned an invalid next-page token.');
  if (payload[0].length > 100) throw new Error('Google Play returned more records than this bounded preview accepts.');
  const seen = new Map();
  for (const raw of payload[0]) {
    const id = clean(raw?.[0]), content = clean(raw?.[4]), score = raw?.[2];
    if (!id || id.length > 200 || !content || content.length > 50000 || !Number.isInteger(score) || score < 1 || score > 5) {
      throw new Error('A source record failed validation. The page was not saved; earlier data is unchanged.');
    }
    const record = {app_id: appId, review_id: id, content, score,
      thumbs_up_count: Number.isInteger(raw[6]) && raw[6] >= 0 ? raw[6] : 0,
      review_at: timestamp(raw?.[5]?.[0]), collected_at: observedAt,
      review_created_version: clean(raw[10]) || null, reply_content: clean(raw?.[7]?.[1]) || null,
      replied_at: raw?.[7]?.[2]?.[0] == null ? null : timestamp(raw[7][2][0])};
    const previous = seen.get(id);
    if (previous && JSON.stringify(previous) !== JSON.stringify(record)) throw new Error('Conflicting duplicate review IDs in a source page.');
    seen.set(id, record);
  }
  return {records: [...seen.values()], cursor, observed: payload[0].length};
}
export async function fetchPage(appId, cursor, fetcher = fetch) {
  const response = await fetcher('https://play.google.com/_/PlayStoreUi/data/batchexecute?hl=en&gl=us', {
    method: 'POST', headers: {'content-type': 'application/x-www-form-urlencoded'},
    body: requestBody(appId, cursor), signal: AbortSignal.timeout(20000), redirect: 'manual',
  });
  if (!response.ok) throw new Error(`Google Play returned HTTP ${response.status}. Try again later.`);
  const text = await response.text();
  if (text.length > 2_000_000) throw new Error('Google Play response exceeded the preview size limit.');
  return parseResponse(text, appId, new Date().toISOString());
}
