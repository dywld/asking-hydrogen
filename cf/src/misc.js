// /api/share·feedback·distance·sandbox/cases·byl (app.py·distance.py·forms.py 를 옮김)
import MISC from './misc_data.json';

function json(obj, status = 200) {
  return new Response(typeof obj === 'string' ? obj : JSON.stringify(obj),
    { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}
function kstStamp() {
  return new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 19).replace('T', ' ');
}
const lawQuote = s => encodeURIComponent(s).replace(/%2F/g, '/');

// ── 안전거리 ──
function distanceLookup(tid, cap) {
  const t = MISC.distance.find(t => t.id === tid);
  if (!t) return null;
  for (const row of t.rows) {
    if (row.max === null || cap <= row.max)
      return { table: t.id, name: t.name, law: t.law, ref: t.ref, unit: t.unit, columns: t.columns, capacity: cap,
        label: row.label, values: row.values, extra: row.extra ?? null, notes: t.notes, rows: t.rows };
  }
  return null;
}

function distance(q) {
  const tid = q.get('table') || '';
  if (!tid) return json({ tables: MISC.distance.map(t => ({ id: t.id, name: t.name, law: t.law, ref: t.ref, unit: t.unit, columns: t.columns })) });
  const digits = (q.get('cap') || '').replace(/\D/g, '');
  if (!digits) return json({ error: '용량은 숫자여야 합니다' }, 400);
  const r = distanceLookup(tid, parseInt(digits, 10));
  if (!r) return json({ error: '표 범위 밖이거나 없는 표입니다' }, 404);
  r.link = r.law.startsWith('KGS')
    ? `https://cyber.kgs.or.kr/kgscode.codeSearch.listV2.ex.do?pblcCd=${r.law.replace('KGS ', '')}`
    : 'https://www.law.go.kr/' + lawQuote(`법령/${r.law.replace(/ /g, '')}`);
  return json(r);
}

// ── 대화 공유 ──
const SHARE_KEYS = ['q', 'text', 'sources', 'cited', 'followups', 'warnings', 'nums', 'refs', 'lowconf', 'model', 'cached', 'regs', 'sandbox'];
async function share(req, env) {
  const turns = req.turns || [];
  if (!Array.isArray(turns) || !turns.length || turns.length > 30) return json({ error: '저장할 대화가 없습니다' }, 400);
  const keep = turns.map(t => Object.fromEntries(SHARE_KEYS.map(k => [k, t && typeof t === 'object' && t[k] !== undefined ? t[k] : null])));
  const raw = JSON.stringify({ t: kstStamp(), turns: keep });
  const bytes = new TextEncoder().encode(raw);
  if (bytes.length > 400_000) return json({ error: '대화가 너무 깁니다' }, 413);
  const h = new Uint8Array(await crypto.subtle.digest('SHA-1', bytes));
  const sid = [...h.slice(0, 4)].map(b => b.toString(16).padStart(2, '0')).join('');
  await env.DB.prepare('INSERT OR REPLACE INTO shares (id, data) VALUES (?, ?)').bind(sid, raw).run();
  return json({ id: sid, path: `/s/${sid}` });
}

// ── 법령정보센터 별지·별표 (forms.py) ──
const BASE = 'https://www.law.go.kr/LSW';
const KIND_CODE = { '별표': '110201', '서식': '110202' };
const HDR = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://www.law.go.kr/', 'X-Requested-With': 'XMLHttpRequest' };
const lawKey = law => law.replace(/\s+/g, '').replace(/·/g, 'ㆍ');

class Sess {          // 쿠키를 이어 붙이는 작은 세션(파이썬 CookieJar 대신)
  constructor() { this.c = {}; }
  async go(u, body) {
    const headers = { ...HDR };
    const ck = Object.entries(this.c).map(([k, v]) => `${k}=${v}`).join('; ');
    if (ck) headers.Cookie = ck;
    if (body) headers['Content-Type'] = 'application/x-www-form-urlencoded';
    const r = await fetch(u, { method: body ? 'POST' : 'GET', headers, body: body ? new URLSearchParams(body).toString() : undefined,
      signal: AbortSignal.timeout(40000) });
    const sc = r.headers.getSetCookie ? r.headers.getSetCookie() : [];
    for (const s of sc) { const m = /^([^=;]+)=([^;]*)/.exec(s); if (m) this.c[m[1].trim()] = m[2]; }
    return r;
  }
  async text(u, body) { return (await this.go(u, body)).text(); }
}

async function listing(s, lsi) {
  let page = await s.text(`${BASE}/lsBylInfoPLinkR.do?lsiSeq=${lsi}&bylCls=BF`);
  let m = /id="bylSeq"[^>]*value="(\d+)"/.exec(page);
  if (!m) { page = await s.text(`${BASE}/lsBylInfoPLinkR.do?lsiSeq=${lsi}`); m = /id="bylSeq"[^>]*value="(\d+)"/.exec(page); }
  if (!m) return [];
  const html = await s.text(`${BASE}/lsBylInfoR.do`, { bylSeq: m[1], lsiSeq: lsi, vSct: '*', efYd: '' });
  const inv = Object.fromEntries(Object.entries(KIND_CODE).map(([k, v]) => [v, k]));
  const items = [];
  for (const [, val, label] of html.matchAll(/<option value="([^"]*)"[^>]*>\s*([^<]*)<\/option>/g)) {
    const parts = val.split(',');
    if (parts.length < 4 || !/^\d+$/.test(parts[0])) continue;
    const kind = inv[parts[3]];
    if (!kind) continue;
    const title = label.replace(/^\[[^\]]*\]\s*/, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim();
    items.push({ seq: parts[0], kind, no: parseInt(parts[1], 10), br: parseInt(parts[2] || '0', 10), title });
  }
  return items;
}

async function lawEntry(env, s, law) {
  const key = lawKey(law);
  const row = await env.DB.prepare('SELECT data FROM byl_cache WHERE key=?').bind(key).first();
  if (row) return { key, e: JSON.parse(row.data) };
  if (MISC.byl[key]) return { key, e: structuredClone(MISC.byl[key]) };
  const page = await s.text('https://www.law.go.kr/' + lawQuote(`법령/${key}`));
  const m = /lsiSeq=(\d+)/.exec(page);
  if (!m) return null;
  const e = { lsiSeq: m[1], items: await listing(s, m[1]), files: {} };
  await env.DB.prepare('INSERT OR REPLACE INTO byl_cache (key, data, t) VALUES (?,?,?)').bind(key, JSON.stringify(e), Date.now()).run();
  return { key, e };
}

async function resolve(env, law, kind, no, br) {
  const s = new Sess();
  const got = await lawEntry(env, s, law);
  if (!got) return null;
  const { key, e } = got;
  const hit = e.items.find(i => i.kind === kind && i.no === no && i.br === br);
  if (!hit) return null;
  let f = e.files[hit.seq];
  if (!f) {
    const html = await s.text(`${BASE}/lsBylContentsInfoR.do`, { bylSeq: hit.seq });
    const ids = {};
    for (const [, k, v] of html.matchAll(/id="(hanFlSeq|pdfFlSeq|govLnkUrl)"[^>]*value="([^"]*)"/g)) ids[k] = v;
    f = { han: ids.hanFlSeq || '', pdf: ids.pdfFlSeq || '', gov: (ids.govLnkUrl || '').trim() };
    e.files[hit.seq] = f;
    await env.DB.prepare('INSERT OR REPLACE INTO byl_cache (key, data, t) VALUES (?,?,?)').bind(key, JSON.stringify(e), Date.now()).run();
  }
  return { law, kind, no, br, title: hit.title, link: `${BASE}/lsBylInfoPLinkR.do?bylSeq=${hit.seq}&lsiSeq=${e.lsiSeq}`,
    han: Boolean(f.han), pdf: Boolean(f.pdf), gov: f.gov, _han: f.han, _pdf: f.pdf };
}

async function fetchFile(fl, ext) {
  const r = await fetch(`${BASE}/flDownload.do?flSeq=${fl}`, { headers: HDR, signal: AbortSignal.timeout(40000) });
  const data = new Uint8Array(await r.arrayBuffer());
  const head = String.fromCharCode(...data.slice(0, 4));
  if (ext === 'pdf' && head !== '%PDF') return [null, null];
  if (ext === 'hwp' && !['\xd0\xcf\x11\xe0', 'HWP ', 'PK\x03\x04'].includes(head)) return [null, null];
  let name = `${fl}.${ext}`;
  const m = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '');
  if (m) { try { name = decodeURIComponent(m[1]); } catch (e) { name = m[1]; } }
  return [data, name];
}

async function byl(p, q, env, ctx) {
  const law = (q.get('law') || '').trim(), kind = q.get('kind') || '', no = q.get('no') || '', br = q.get('br') || '0';
  if (!law || !(kind in KIND_CODE) || !/^\d+$/.test(no) || !/^\d+$/.test(br)) return json({ error: 'law·kind·no 가 필요합니다' }, 400);
  if (law.includes('요약자료') || law.startsWith('KGS')) return json({ error: '법령이 아닙니다' }, 404);
  let r;
  try { r = await resolve(env, law, kind, parseInt(no, 10), parseInt(br, 10)); } catch (e) {
    return json({ error: `법령정보센터 응답 없음: ${e.message || e}` }, 502);
  }
  if (!r) return json({ error: '법령정보센터에 없는 서식·별표입니다' }, 404);
  if (p === '/api/byl') return json(Object.fromEntries(Object.entries(r).filter(([k]) => !k.startsWith('_'))));
  const fmt = q.get('fmt') || 'pdf';
  const fl = fmt === 'pdf' ? r._pdf : r._han;
  if (!['pdf', 'hwp'].includes(fmt) || !fl) return json({ error: '그 형식의 파일이 없습니다' }, 404);
  // 한 번 받은 파일은 엣지 캐시에 둔다(파이썬은 data/forms/ 에 둔다)
  const cache = caches.default, ck = new Request(`https://byl-cache.local/${fl}.${fmt}`);
  const hitc = await cache.match(ck);
  if (hitc) return hitc;
  let data, name;
  try { [data, name] = await fetchFile(fl, fmt); } catch (e) { return json({ error: `파일을 받지 못했습니다: ${e.message || e}` }, 502); }
  if (!data || !data.length) return json({ error: '파일이 비어 있습니다' }, 404);
  const res = new Response(data, { headers: {
    'Content-Type': fmt === 'pdf' ? 'application/pdf' : 'application/x-hwp',
    'Content-Disposition': (fmt === 'pdf' ? 'inline' : 'attachment') + `; filename*=UTF-8''${encodeURIComponent(name)}`,
    'Cache-Control': 'public, max-age=86400' } });
  const put = cache.put(ck, res.clone()).catch(() => {});
  if (ctx && ctx.waitUntil) ctx.waitUntil(put); else await put;
  return res;
}

export async function handleMisc(req, env, url, ctx) {
  const p = url.pathname, q = url.searchParams;
  if (req.method === 'GET') {
    if (p === '/api/distance') return distance(q);
    if (p === '/api/sandbox/cases') return json(MISC.sandbox);
    if (p.startsWith('/api/share/')) {
      const sid = p.slice(p.lastIndexOf('/') + 1);
      const row = /^[A-Za-z0-9]{6,12}$/.test(sid) ? await env.DB.prepare('SELECT data FROM shares WHERE id=?').bind(sid).first() : null;
      return row ? json(row.data) : json({ error: '없는 공유 주소입니다' }, 404);
    }
    if (p === '/api/byl' || p === '/api/byl/file') return byl(p, q, env, ctx);
    return null;
  }
  if (req.method !== 'POST' || (p !== '/api/share' && p !== '/api/feedback')) return null;
  let body;
  try {
    if (Number(req.headers.get('Content-Length') || 0) > 4_000_000) throw 0;
    body = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await req.arrayBuffer()) || '{}');
    if (body === null || typeof body !== 'object') throw 0;
  } catch (e) { return json({ error: '요청 형식이 올바르지 않습니다(UTF-8 JSON)' }, 400); }
  if (p === '/api/share') return share(body, env);
  const vote = body.vote;
  if (vote !== 'up' && vote !== 'down') return json({ error: 'vote 는 up/down' }, 400);
  try {
    const t = kstStamp();
    const rec = { t, vote, q: String(body.q || '').slice(0, 300), reason: String(body.reason || '').slice(0, 500),
      answer: String(body.answer || '').slice(0, 1500), sources: (Array.isArray(body.sources) ? body.sources : []).slice(0, 8) };
    await env.DB.prepare('INSERT INTO feedback (t, data) VALUES (?, ?)').bind(t, JSON.stringify(rec)).run();
  } catch (e) { /* 파이썬처럼 저장 실패는 무시 */ }
  return json({ ok: true });
}
