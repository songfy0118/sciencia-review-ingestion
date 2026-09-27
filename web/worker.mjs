import {fetchPage, parseApp, InputError} from './google-play.mjs';

const fields = ['app_id','review_id','content','score','thumbs_up_count','review_at','collected_at','review_created_version','reply_content','replied_at'];
const reviewSQL = `INSERT INTO reviews (${fields.join(',')}) VALUES (${fields.map(()=>'?').join(',')})
 ON CONFLICT(app_id,review_id) DO UPDATE SET ${fields.slice(2).map(k=>`${k}=excluded.${k}`).join(',')}
 WHERE excluded.collected_at >= reviews.collected_at`;
const json = (data, status = 200) => Response.json(data, {status, headers: {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
const statement = (db, sql, args = []) => db.prepare(sql).bind(...args);

async function rateLimit(db, bucket, limit, expiresAt) {
  const result = await statement(db, `INSERT INTO request_limits(bucket,used,expires_at) VALUES (?,1,?)
    ON CONFLICT(bucket) DO UPDATE SET used=used+1 WHERE used < ? RETURNING used`, [bucket, expiresAt, limit]).first();
  return Boolean(result);
}
export async function collect(request, env, fetcher = fetch) {
  const url = new URL(request.url);
  if (request.headers.get('Origin') !== url.origin) return json({error:'Start collection from this website.'},403);
  if (!(request.headers.get('Content-Type') || '').includes('application/json')) return json({error:'Use a JSON request.'},415);
  const text = await request.text();
  if (text.length > 4096) return json({error:'Request is too large.'},413);
  let input;
  try { input = JSON.parse(text); } catch { return json({error:'Invalid request.'},400); }
  if (!input || typeof input !== 'object' || Array.isArray(input)) return json({error:'Invalid request.'},400);
  const db = env.DB;
  let previous = null, appId, label;
  if (input.resume) {
    if (typeof input.resume !== 'string' || !/^[a-f0-9-]{36}$/.test(input.resume)) throw new InputError('Invalid saved run.');
    previous = await statement(db, 'SELECT * FROM runs WHERE run_id=?', [input.resume]).first();
    if (!previous || !previous.cursor || previous.pages >= 3) throw new InputError('This run has no next page available in the preview. Start a new collection.');
    appId = previous.app_id; label = previous.label;
  } else {
    appId = parseApp(input.app);
    if (input.label != null && (typeof input.label !== 'string' || input.label.length > 80)) throw new InputError('Use an app name of at most 80 characters.');
    const saved = await statement(db, 'SELECT label FROM apps WHERE app_id=?', [appId]).first();
    label = saved?.label || input.label?.trim() || appId;
  }
  const now = Date.now(), hour = Math.floor(now / 3600000);
  if (!await rateLimit(db, `hour:${hour}`, 60, now + 3600000)) return json({error:'The shared preview has reached its hourly collection limit. Saved reviews are still available.'},429);
  const owner = crypto.randomUUID();
  const lock = await statement(db, `INSERT INTO app_locks(app_id,owner,expires_at) VALUES (?,?,?)
    ON CONFLICT(app_id) DO UPDATE SET owner=excluded.owner,expires_at=excluded.expires_at
    WHERE app_locks.expires_at < ? RETURNING owner`, [appId,owner,now+60000,now]).first();
  if (!lock) return json({error:'This app was just requested. Wait about a minute, then try again.'},429);
  const runId = previous?.run_id || crypto.randomUUID(), started = new Date().toISOString();
  let committed = false;
  try {
    if (previous) {
      // Re-read under the per-app lease so two clients cannot save the same next page.
      previous = await statement(db, 'SELECT * FROM runs WHERE run_id=?', [runId]).first();
      if (!previous.cursor || previous.pages >= 3) throw new InputError('No next page remains for this run.');
    } else {
      await statement(db, 'INSERT INTO runs(run_id,app_id,label,started_at,status) VALUES (?,?,?,?,?)', [runId,appId,label,started,'running']).run();
    }
    const page = await fetchPage(appId, previous?.cursor || null, fetcher);
    if (!page.records.length) throw new Error('Google Play returned no usable review text. This does not prove the app has no reviews.');
    if (previous?.cursor && page.cursor === previous.cursor) throw new Error('Google Play repeated the page token. Progress was not advanced.');
    const newest = page.records.reduce((latest,r)=>r.review_at>latest?r.review_at:latest,'');
    const ageDays = (Date.now()-Date.parse(newest))/86400000;
    const warning = ageDays > 7 ? 'The newest returned review is over seven days old. Source freshness needs checking.' : null;
    const pageNumber = (previous?.pages || 0) + 1;
    const batch = [statement(db, 'INSERT INTO apps(app_id,label,updated_at) VALUES (?,?,?) ON CONFLICT(app_id) DO UPDATE SET updated_at=excluded.updated_at', [appId,label,started]),
      ...page.records.map(record=>statement(db, reviewSQL, fields.map(k=>record[k]))),
      statement(db, 'INSERT INTO pages(run_id,page,observed_at,records_json) VALUES (?,?,?,?)', [runId,pageNumber,started,JSON.stringify(page.records)]),
      statement(db, 'UPDATE runs SET completed_at=?,status=?,pages=?,observed=observed+?,cursor=?,warning=?,error=NULL WHERE run_id=?',
        [new Date().toISOString(),warning?'warning':'ready',pageNumber,page.observed,page.cursor,warning,runId])];
    await db.batch(batch);
    committed = true;
    return json({run_id:runId,app_id:appId,label,observed:page.observed,saved:page.records.length,pages:pageNumber,
      can_resume:Boolean(page.cursor)&&pageNumber<3,warning,message:`Saved ${page.records.length} reviews from ${label}. Existing IDs were updated, not added twice.`});
  } catch (error) {
    console.error('collection',runId,error.message);
    await statement(db, 'UPDATE runs SET status=?,completed_at=?,error=? WHERE run_id=?', ['failed',new Date().toISOString(),error.message.slice(0,500),runId]).run();
    return json({error:error.message,run_id:runId,can_resume:Boolean(previous?.cursor),saved:0},error instanceof InputError?400:502);
  } finally {
    // Leave a short cooldown after both success and failure. Do not let a second client remove a newer lease.
    await statement(db, 'UPDATE app_locks SET expires_at=? WHERE app_id=? AND owner=?', [Date.now()+15000,appId,owner]).run();
    if (committed) await statement(db,'DELETE FROM request_limits WHERE expires_at < ?', [Date.now()]).run();
  }
}

export async function api(request, env) {
  const url = new URL(request.url), db=env.DB;
  if (url.pathname === '/api/collect' && request.method === 'POST') return collect(request,env);
  if (request.method !== 'GET') return json({error:'Method not allowed.'},405);
  if (url.pathname === '/api/apps') {
    const {results} = await statement(db, `SELECT a.app_id,a.label,a.updated_at,count(r.review_id) AS reviews,max(r.review_at) AS newest_review
      FROM apps a LEFT JOIN reviews r ON a.app_id=r.app_id GROUP BY a.app_id ORDER BY a.label COLLATE NOCASE`).all();
    return json({apps:results,total:results.reduce((sum,a)=>sum+a.reviews,0),version:env.VERSION || 'development'});
  }
  if (url.pathname === '/api/reviews' || url.pathname === '/api/export') {
    const q=(url.searchParams.get('q')||'').trim().slice(0,200), app=url.searchParams.get('app')||'';
    const rating=url.searchParams.get('rating')||'', votes=Number(url.searchParams.get('helpful')||0);
    const page=Math.min(50000,Math.max(0,parseInt(url.searchParams.get('page')||'0',10)||0));
    if (!['','high','mid','low'].includes(rating) || ![0,1,10].includes(votes)) throw new InputError('Invalid filters.');
    const clauses=[],args=[];
    if(app){clauses.push('r.app_id=?');args.push(parseApp(app));}
    if(q){
      const exact=await statement(db,'SELECT app_id FROM apps WHERE lower(label)=lower(?)',[q]).first();
      if(exact){clauses.push('r.app_id=?');args.push(exact.app_id);}
      else{clauses.push('(instr(lower(a.label),lower(?))>0 OR instr(lower(r.content),lower(?))>0)');args.push(q,q);}
    }
    if(rating){clauses.push(rating==='high'?'r.score>=4':rating==='low'?'r.score<=2':'r.score=3');}
    if(votes){clauses.push('r.thumbs_up_count>=?');args.push(votes);}
    const where=clauses.length?' WHERE '+clauses.join(' AND '):'';
    const total=await statement(db,'SELECT count(*) AS total FROM reviews r JOIN apps a ON a.app_id=r.app_id'+where,args).first();
    const exporting=url.pathname==='/api/export', limit=exporting?1000:20;
    const {results}=await statement(db,'SELECT r.*,a.label FROM reviews r JOIN apps a ON a.app_id=r.app_id'+where+' ORDER BY r.review_at DESC,r.app_id,r.review_id LIMIT ? OFFSET ?',[...args,limit,page*limit]).all();
    const response=json({total:total.total,page,page_size:limit,has_more:(page+1)*limit<total.total,reviews:results});
    if(exporting)response.headers.set('Content-Disposition','attachment; filename="app-reviews.json"');
    return response;
  }
  if(url.pathname==='/api/runs'){
    const {results}=await statement(db,'SELECT run_id,app_id,label,started_at,completed_at,status,pages,observed,warning,error,(cursor IS NOT NULL AND pages<3) AS can_resume FROM runs ORDER BY started_at DESC LIMIT 12').all();
    return json({runs:results});
  }
  return json({error:'Not found.'},404);
}
export default {
  async fetch(request,env){
    try{
      if(new URL(request.url).pathname.startsWith('/api/'))return await api(request,env);
      const response=await env.ASSETS.fetch(request);
      const secured=new Response(response.body,response);
      secured.headers.set('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
      secured.headers.set('X-Content-Type-Options','nosniff');secured.headers.set('Referrer-Policy','no-referrer');
      return secured;
    }catch(error){console.error('request',error.message);return json({error:error instanceof InputError?error.message:'The service could not complete the request. Please try again.'},error instanceof InputError?400:500);}
  }
};
