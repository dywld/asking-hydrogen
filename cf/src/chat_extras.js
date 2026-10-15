// 노트북 서버(app.py do_chat · search.py · facts.py)의 곁가지를 워커로 옮긴 것.
// 검색: search.py 의 점수 규칙(제목 가산·시설 유형·가스 종류·절차/설치·기준일·일본)을
//       D1 SQL 한 번으로 계산한다. 무거운 계산은 D1 이 하고 워커 CPU 는 결과 몇 줄만 만진다.
// 답변 곁가지: 캐시(D1 answer_cache)·발표 잠금·규제 사례·확정 자료·체크리스트·재작성·검증·근거 없는 문장.
import DATA from './data.json';

const S = DATA.search, C = DATA.chat;
const API = 'https://generativelanguage.googleapis.com/v1beta/models';
const HANGUL = /[가-힣]+/g, CJK = /[一-鿿ぁ-ゟ゠-ヿ]+/g, WORD = /[A-Za-z0-9]+/g;
const FILLER = new RegExp(DATA.filler, 'g');
const PROCEDURE = new RegExp(S.procedure), CHANGE = new RegExp(S.change), INSTALL = new RegExp(S.install);
const NOISE = S.noise_title.split('|');
const CHECKLIST_RE = new RegExp(C.checklist_re), SMALLTALK = new RegExp(C.smalltalk), META = new RegExp(C.meta);
const FOLLOW_RE = /#{2,4}\s*다음\s*질문\s*/;
// FTS5 bm25 는 search.py 의 BM25(k1 1.5, idf 하한 없음)보다 눈금이 작다. 화면·판정(40·55)이 같은 눈금을 쓰도록 맞춘다.
const CAL = 1.11;

export function tokenize(text) {
  const t = String(text).toLowerCase(), out = [];
  for (const m of [...(t.match(HANGUL) || []), ...(t.match(CJK) || [])]) {
    if (m.length === 1) out.push(m);
    else for (let i = 0; i < m.length - 1; i++) out.push(m.slice(i, i + 2));
  }
  return out.concat(t.match(WORD) || []);
}
function expand(query) {
  const extra = Object.entries(DATA.expand).filter(([k]) => query.includes(k)).map(([, v]) => v);
  if (query.includes('일본')) {
    for (const [k, v] of Object.entries(S.jp_words)) if (query.includes(k)) extra.push(v);
    extra.push('水素 日本');
  }
  return query.replace(FILLER, ' ') + ' ' + extra.join(' ');
}
const lawKey = s => String(s).replace(/[\s·ㆍᆞ・]/g, '');
const articleRef = a => a.includes(']') ? a.slice(0, a.indexOf(']') + 1) : a;
const lit = s => "'" + String(s).replace(/'/g, "''") + "'";
const anyIn = (col, words) => '(' + words.map(w => `instr(${col}, ${lit(w)}) > 0`).join(' OR ') + ')';
const gasOf = text => Object.entries(S.gas).filter(([, ws]) => ws.some(w => text.includes(w))).map(([k]) => k);
const facilityTags = text => Object.entries(S.facility).filter(([, ws]) => ws.some(w => text.includes(w))).map(([k]) => k);
const COLS = 'id, country, law, article, title, future, effective_date, kind, ref, link';

// search.py Index.search 의 점수식을 SQL 로. opts.ids 가 있으면 그 조각만 점수를 매긴다(별표 딸림용).
function scoreSql(query, opts = {}) {
  const q = [...new Set(tokenize(expand(query)))].slice(0, 90);
  if (!q.length) return null;
  let q0 = [...new Set(tokenize(query.replace(FILLER, ' ')))];
  if (!q0.length) q0 = q;
  q0 = q0.slice(0, 60);
  const n0 = q0.length;
  const head = "lower(d.law || ' ' || d.title)";
  const ov = q0.map((_, i) => `(instr(${head}, ?${i + 2}) > 0)`).join(' + ');
  const want = new Set(facilityTags(query));
  if (opts.facility) want.add(opts.facility);
  const wantGas = new Set(gasOf(query));
  if (wantGas.has('수소')) wantGas.add('고압가스');
  const where = [];
  if (opts.country) where.push(`d.country = ${lit(opts.country)}`);
  if (opts.facility && S.facility[opts.facility]) where.push(anyIn("(d.title || ' ' || substr(d.content, 1, 600))", S.facility[opts.facility]));
  if (opts.kind) where.push(`d.kind = ${lit(opts.kind)}`);
  if (opts.ids) where.push(`d.id IN (${opts.ids.map(Number).join(',')})`);
  const fac = want.size ? `, ${anyIn("(d.title || ' ' || substr(d.content, 1, 600))", [...want].flatMap(k => S.facility[k] || []))} AS fac` : ', 0 AS fac';
  const m = [`(1 + 0.5 * ov / ${n0}.0)`];
  if (opts.forms) {
    m.length = 0;
    m.push(`(CASE WHEN ${anyIn('law', S.core)} THEN 1.3 ELSE 1 END)`);
  } else {
    if (n0 >= 4) m.push(`(CASE WHEN law LIKE 'KGS%' AND ov * 1.0 / ${n0} >= 0.8 THEN 1.8 ELSE 1 END)`);
    m.push("(CASE WHEN kind = '별지서식' THEN 0.3 ELSE 1 END)");
    if (want.size) m.push('(CASE WHEN fac THEN 1.3 ELSE 1 END)');
    m.push(`(CASE WHEN ${anyIn('law', S.core)} THEN 1.15 ELSE 1 END)`);
    m.push(`(CASE WHEN ${anyIn('title', NOISE)} THEN 0.2 ELSE 1 END)`);
    if (INSTALL.test(query)) m.push(`(CASE WHEN substr(law, 1, 6) IN (${S.make_code.map(lit).join(',')}) THEN 0.6 ELSE 1 END)`);
    if (wantGas.size) {
      const all = Object.values(S.gas).flat(), mine = [...wantGas].flatMap(k => S.gas[k]);
      m.push(`(CASE WHEN ${anyIn("(law || ' ' || title)", all)} AND NOT ${anyIn("(law || ' ' || title)", mine)} THEN 0.5 ELSE 1 END)`);
    }
    if (query.includes('일본')) m.push("(CASE WHEN country = '일본' THEN 3.0 ELSE 0.5 END)");
    if (PROCEDURE.test(query)) m.push("(CASE WHEN kind = '상세기준' THEN 0.55 ELSE 1 END)");
    const asOf = opts.as_of;
    const fut = CHANGE.test(query) ? 'WHEN future = 1 THEN 2.0'
      : asOf ? `WHEN future = 1 AND COALESCE(NULLIF(effective_date, ''), '9999') > ${lit(asOf)} THEN 0.15` : '';
    let old = '';
    if (asOf) {
      const keys = S.cur_fut.filter(([, , e]) => e <= asOf).map(([l, a]) => lit(l + '|' + a));
      if (keys.length) old = `WHEN future = 0 AND (law || '|' || article) IN (${keys.join(',')}) THEN 0.3`;
    }
    if (fut || old) m.push(`(CASE ${fut} ${old} ELSE 1 END)`);
  }
  const sql = `WITH mm AS (SELECT rowid AS id, bm25(docs_fts) AS b FROM docs_fts WHERE docs_fts MATCH ?1${opts.ids ? '' : ' ORDER BY b LIMIT 400'}),
c AS (SELECT d.id, d.country, d.law, d.article, d.title, d.future, d.effective_date, d.kind, d.ref, d.link,
  -mm.b AS b, (${ov}) AS ov ${fac} FROM mm JOIN docs d ON d.id = mm.id ${where.length ? 'WHERE ' + where.join(' AND ') : ''})
SELECT ${COLS}, b * ${m.join(' * ')} AS s FROM c ORDER BY s DESC LIMIT ${Number(opts.limit) || 12}`;
  const CM = S.common || {};
  let mq = q.filter(t => !CM[t]);
  if (mq.length < 3) mq = mq.concat(q.filter(t => CM[t]).sort((a, b) => CM[a] - CM[b]).slice(0, 3 - mq.length));
  return { sql, binds: [mq.map(t => `"${t}"`).join(' OR '), ...q0] };
}

async function runScore(env, query, opts) {
  const x = scoreSql(query, opts);
  if (!x) return [];
  const { results } = await env.DB.prepare(x.sql).bind(...x.binds).all();
  return results.map(r => ({ ...r, score: Math.round(r.s * CAL * 100) / 100 }));
}
async function withContent(env, hits) {
  const ids = [...new Set(hits.filter(h => h.id && h.content === undefined).map(h => h.id))];
  if (ids.length) {
    const { results } = await env.DB.prepare(`SELECT id, content FROM docs WHERE id IN (${ids.join(',')})`).all();
    const by = new Map(results.map(r => [r.id, r.content]));
    for (const h of hits) if (h.content === undefined) h.content = by.get(h.id) || '';
  }
  return hits;
}
const clean = r => ({ ...r, future: !!r.future, kind: r.kind || null, effective_date: r.effective_date || null });

// search.py Index.search 와 같은 결과(상위 top_k + 개정 짝 + 갈래 + 참조 조문 + 딸린 별표).
export async function search(env, query, opts = {}) {
  const k = opts.top_k || 12;
  const best = (await runScore(env, query, { ...opts, limit: k })).map(clean);
  if (opts.inner || opts.bare) return withContent(env, best);
  const out = best.map(h => ({ ...h }));
  const picked = new Set(out.map(h => h.id));
  const scoreOf = new Map(out.map(h => [h.id, h.score]));
  if (opts.as_of) for (const o of out) if (o.future && (o.effective_date || '9999') <= opts.as_of) { o.future = false; o.revised = o.effective_date; }
  await withContent(env, out);
  const add = (rows, extra) => { for (const r of rows) if (!picked.has(r.id)) { picked.add(r.id); out.push({ ...clean(r), score: scoreOf.get(r.id) || 0, ...extra(r) }); } };
  // 개정 비교: 예정판 옆에 현행판
  if (CHANGE.test(query)) {
    for (const d of best.slice(0, 4).filter(d => d.future)) {
      const { results } = await env.DB.prepare(`SELECT ${COLS}, content FROM docs WHERE future = 0 AND kind = '' AND country = '한국' AND law = ?1 AND article = ?2 ORDER BY id LIMIT 1`).bind(d.law, d.article).all();
      add(results, () => ({ pair_of: d.article }));
    }
  }
  // 우산 개념(규제특례·검사·안전관리자): 갈래마다 1등을 넣는다.
  for (const [key, subs] of Object.entries(S.bundles)) {
    if (!query.includes(key)) continue;
    for (const sub of subs) {
      const s0 = sub.replace(/ /g, '');
      if (out.some(h => (h.title + (h.content || '').slice(0, 200)).replace(/ /g, '').includes(s0))) continue;
      const [h] = await search(env, sub, { top_k: 1, country: opts.country, inner: true });
      if (!h) continue;
      const { results } = await env.DB.prepare(`SELECT ${COLS}, content FROM docs WHERE law = ?1 AND article = ?2 ORDER BY id LIMIT 1`).bind(h.law, h.article).all();
      for (const r of results) scoreOf.set(r.id, scoreOf.get(r.id) || Math.round(h.score * 50) / 100);
      add(results, () => ({ bundle: key }));
    }
  }
  // 뽑힌 조문이 부르는 같은 법의 다른 조문(제10조의3에 따른 …)
  const xre = new RegExp(S.xref, 'g');
  for (const d of best.slice(0, 3)) {
    if (d.kind || d.country !== '한국') continue;
    const arts = [];
    for (const m of (out.find(o => o.id === d.id)?.content || '').slice(0, 1500).matchAll(xre)) {
      const art = `제${m[1]}조` + (m[2] ? `의${m[2]}` : '');
      if (art !== d.article && !arts.includes(art)) arts.push(art);
    }
    if (!arts.length) continue;
    const { results } = await env.DB.prepare(`SELECT ${COLS}, content FROM docs WHERE kind = '' AND future = 0 AND country = '한국' AND law = ?1 AND article IN (${arts.slice(0, 20).map(lit).join(',')}) ORDER BY id`).bind(d.law).all();
    const first = new Map();
    for (const r of results) if (!first.has(r.article)) first.set(r.article, r);
    add(arts.map(a => first.get(a)).filter(r => r && r.id !== d.id).slice(0, 2), () => ({ xref_from: d.article }));
  }
  // 뽑힌 조문이 부르는 별표(질문과 가까운 조각 두 개)
  const want = [];
  for (const d of best.slice(0, 5)) {
    if (d.kind) continue;
    const cand = (S.linked[lawKey(d.law) + '|' + d.article] || []).filter(c => !picked.has(c));
    if (cand.length) want.push([d, cand]);
  }
  if (want.length) {
    const all = [...new Set(want.flatMap(([, c]) => c))].slice(0, 400);
    const sc = new Map((await runScore(env, query, { ...opts, ids: all, limit: all.length })).map(r => [r.id, r.score]));
    const take = [];
    for (const [d, cand] of want) {
      const two = cand.filter(c => !picked.has(c) && !take.some(t => t[0] === c))
        .map((c, i) => [c, sc.get(c) || 0, i]).sort((a, b) => b[1] - a[1] || a[2] - b[2]).slice(0, 2);
      for (const [c, s] of two) { take.push([c, d.article]); scoreOf.set(c, s); }
    }
    if (take.length) {
      const { results } = await env.DB.prepare(`SELECT ${COLS}, content FROM docs WHERE id IN (${take.map(t => t[0]).join(',')})`).all();
      const by = new Map(results.map(r => [r.id, r]));
      for (const [c, from] of take) if (by.get(c)) add([by.get(c)], () => ({ linked_from: from }));
    }
  }
  return out;
}

// 체크리스트용 별지 서식만(search_forms). 평소 검색이 0.3 배로 누른 것을 따로 뽑는다.
export async function searchForms(env, query, n = 4) {
  return withContent(env, (await runScore(env, query, { kind: '별지서식', forms: true, limit: n })).map(clean));
}

// ── 질의 재작성(rewrite_query) ──
const rewriteCache = new Map();
const exhausted = { day: '', models: new Set() };
const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
function isExhausted(m) { if (exhausted.day !== today()) { exhausted.day = today(); exhausted.models.clear(); } return exhausted.models.has(m); }
function markExhausted(m) { isExhausted(m); exhausted.models.add(m); }

export async function rewriteQuery(question, key) {
  if (!key || question.length < 4) return question;
  if (rewriteCache.has(question)) return rewriteCache.get(question);
  if (rewriteCache.size > 2000) rewriteCache.clear();
  let terms = null;
  for (const model of C.rewrite_chain) {
    if (isExhausted(model)) continue;
    try {
      const r = await fetch(`${API}/${model}:generateContent?key=${key}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contents: [{ parts: [{ text: C.rewrite_prompt + question }] }], generationConfig: { temperature: 0, maxOutputTokens: 300 } }),
        signal: AbortSignal.timeout(20000),
      });
      if (r.status === 429) { markExhausted(model); continue; }
      if (!r.ok) continue;
      const d = await r.json();
      terms = (d.candidates[0].content.parts || []).map(p => p.text || '').join('').trim();
      break;
    } catch (e) { /* 다음 모델 */ }
  }
  if (terms === null) return question;
  terms = terms.split(/\s+/).join(' ').slice(0, 120);
  if (terms.includes('없습니다') || terms.includes('않습니다') || terms.length > 90) terms = '';
  const head = question.length > C.long_q ? question.slice(0, 40) : question;
  const out = terms ? `${head} ${terms}` : question;
  rewriteCache.set(question, out);
  return out;
}

// ── 캐시(app.py _cache_key·cache_get·cache_put). 자리는 D1 answer_cache ──
const CACHE_TTL = 30 * 86400, CACHE_MAX = 2000;
export async function cacheKey(q, country, facility, asOf, checklist) {
  const norm = q.replace(/[\s?？!.~,]+/g, '').toLowerCase();
  const raw = `${norm}|${country || ''}|${facility || ''}|${asOf || ''}|${checklist ? 1 : 0}`;
  const h = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(raw));
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
}
let cacheReady = false;
async function cacheTable(env) {
  if (cacheReady) return;
  await env.DB.prepare('CREATE TABLE IF NOT EXISTS answer_cache (key TEXT PRIMARY KEY, rec TEXT NOT NULL, ts INTEGER)').run();
  cacheReady = true;
}
export async function cacheGet(env, key) {
  try {
    await cacheTable(env);
    const row = await env.DB.prepare('SELECT rec, ts FROM answer_cache WHERE key = ?1').bind(key).first();
    if (!row) return null;
    if (Date.now() / 1000 - (row.ts || 0) > CACHE_TTL) {
      await env.DB.prepare('DELETE FROM answer_cache WHERE key = ?1').bind(key).run();
      return null;
    }
    return JSON.parse(row.rec);
  } catch (e) { return null; }
}
export async function cachePut(env, key, rec) {
  try {
    await cacheTable(env);
    rec.ts = Date.now() / 1000;
    await env.DB.prepare('INSERT OR REPLACE INTO answer_cache VALUES (?1, ?2, ?3)').bind(key, JSON.stringify(rec), Math.floor(rec.ts)).run();
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM answer_cache').first();
    if (n && n.n > CACHE_MAX)
      await env.DB.prepare('DELETE FROM answer_cache WHERE key IN (SELECT key FROM answer_cache ORDER BY ts LIMIT 200)').run();
  } catch (e) { /* 저장 실패가 답변을 막으면 안 된다 */ }
}

// ── 발표 잠금(demo_lookup). BOT_DEMO_LOCK=1 일 때 승인된 답만 ──
export function demoLookup(env, q) {
  if (String(env.BOT_DEMO_LOCK || '') !== '1') return null;
  const rec = C.demo[q.replace(/[\s?？!.~,]+/g, '').toLowerCase()];
  return rec && rec.approved ? rec : null;
}

// ── 규제 애로 사례(reg_cases_for) ──
const REG_STOP = new Set(C.reg_stop);
function words(q) {
  const out = new Set();
  for (let w of q.match(/[가-힣A-Za-z0-9]{2,}/g) || []) {
    w = w.replace(/(으로|에서|에게|까지|부터|이나|하고|은|는|이|가|을|를|의|에|도|로|와|과)$/, '');
    if (w.length >= 2 && !REG_STOP.has(w)) out.add(w);
  }
  return out;
}
export function regCasesFor(q, n = 2) {
  const ws = [...words(q)];
  if (ws.length < 2) return [];
  const scored = [];
  for (const c of C.reg_cases) {
    const title = c.title + ' ' + c.field, body = title + ' ' + c.pain + ' ' + c.law;
    const t = ws.filter(w => title.includes(w)).length, b = ws.filter(w => body.includes(w)).length;
    if (t >= 2 || (t >= 1 && b >= 3)) scored.push([t * 2 + b, c]);
  }
  return scored.sort((a, b) => b[0] - a[0]).slice(0, n).map(x => x[1]);
}

// ── 확정 자료(facts.match) ──
const FACTS = C.facts.map(t => ({ ...t, re: new RegExp(t.match) }));
export function factsMatch(q) {
  return FACTS.filter(t => t.re.test(q)).map(t => ({
    country: '한국', law: t.law, article: t.ref, title: t.title,
    content: [`${t.law} ${t.ref} ${t.title} — 확정 자료(표에서 코드가 직접 찾음)`,
      ...t.facts.map(f => `· ${f.label}: ${f.value}   (원문: "${f.quote}")`)].join('\n'),
    source: 'fact_tables.json', future: false, effective_date: null, kind: '확정', score: 999.0, facts: t.id,
  }));
}

// ── 화면용 근거 묶기(group_sources) ──
const KANJI = { '〇': 0, '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9 };
function kanjiNum(s) {
  let total = 0, cur = 0;
  for (const ch of s) {
    if (ch === '十') { total += (cur || 1) * 10; cur = 0; }
    else if (ch === '百') { total += (cur || 1) * 100; cur = 0; }
    else cur = KANJI[ch] || 0;
  }
  return total + cur;
}
export function jpRefsAsKorean(text) {
  const out = [];
  for (const m of String(text).matchAll(/第([〇零一二三四五六七八九十百]+)条(?:の([〇零一二三四五六七八九十]+))?/g))
    out.push(`제${kanjiNum(m[1])}조` + (m[2] ? `의${kanjiNum(m[2])}` : ''));
  return out.join(' ');
}
function linkOf(g, h) {
  if (h && h.link) return h.link;
  if (g.law.includes('요약자료')) return 'https://rfz.go.kr/?menuno=234';
  if (g.kind === '상세기준') return `https://cyber.kgs.or.kr/kgscode.codeSearch.listV2.ex.do?pblcCd=${g.law.replace('KGS ', '')}`;
  let path = `법령/${g.law.trim().replace(/ /g, '')}`;
  if (g.ref.startsWith('제') && g.ref.includes('조')) path += `/${g.ref}`;
  return 'https://www.law.go.kr/' + encodeURIComponent(path).replace(/%2F/g, '/');
}
export function groupSources(hits) {
  const groups = new Map();
  for (const h of hits) {
    const ref = articleRef(h.article), key = h.law + '\u0000' + ref;
    let g = groups.get(key);
    if (!g) {
      g = { law: h.law, ref, title: h.title, country: h.country, score: h.score, future: h.future,
        effective_date: h.effective_date, kind: h.kind, parts: [] };
      groups.set(key, g);
      g.link = linkOf(g, h);
    }
    g.score = Math.max(g.score, h.score);
    g.parts.push(h.content);
    if (h.country === '일본') g.jp = jpRefsAsKorean(ref);
  }
  const out = [...groups.values()].sort((a, b) => b.score - a.score).slice(0, 12);
  out.forEach((g, i) => g.n = i + 1);
  return out;
}
export function buildContext(hits, groups) {
  const num = new Map((groups || []).map(g => [g.law + '\u0000' + g.ref, g.n]));
  return hits.map((h, i) => {
    const n = num.get(h.law + '\u0000' + articleRef(h.article)) || i + 1;
    let tag = '';
    if (h.future) tag = ` (시행 예정: ${h.effective_date})`;
    else if (h.revised) tag = ` (개정판, ${h.revised} 시행)`;
    else if (h.pair_of) tag = ' (현행판 — 개정 전 내용, 비교용)';
    else if (h.kind === '별지서식') tag = ' (별지 서식 — 제출 서류 이름과 용도)';
    else if (h.kind === '확정') tag = ' ★확정 자료 — 이 값을 그대로 인용';
    return `[${n}] ${h.country} · ${h.law} ${h.article}(${h.title})${tag}\n${h.content}`;
  }).join('\n\n');
}

// ── 답변 검증(verify) ──
const NUM_RE = /\d+(?:\.\d+)?\s*(?:m|㎡|㎥|kg|㎏|톤|일|개월|년|원|%|미터|퍼센트)/g;
const ORG_RE = /(한국가스안전공사|산업통상(?:자원)?부장관|기후에너지환경부장관|중소벤처기업부장관|국토교통부장관|환경부장관|소방서장|시ㆍ도지사|시·도지사|시장ㆍ군수|시장·군수|구청장|허가관청|신고관청|등록관청|규제자유특구위원회|규제특례심의위원회|한국산업안전보건공단|한국에너지공단|가스기술기준위원회)/g;
const REF_RE = /제\d+조(?:의\d+)?|별표\s*\d+(?:의\d+)?|별지\s*제\d+호\s*서식|KGS\s*[A-Z]{2}\d{3}(?:\s+\d[\d.]*)?/g;
const NAMED_REF = /\[([가-힣][가-힣\s·ㆍ]{3,60}?)\s*(제\d+조(?:의\d+)?|별표\s*\d+(?:의\d+)?)\]/g;
const KGS_ITEM = /^\[(KGS [A-Z]{2}\d{3}) (\d+\.\d+)/;
const noWs = s => String(s).replace(/\s+/g, '');
const uniq = a => [...new Set(a)];
export const splitFollowups = text => { const m = text.match(FOLLOW_RE); return m ? [text.slice(0, m.index), m.index] : [text, -1]; };

function verifyKey(d) {
  const m = (d.article || '').match(KGS_ITEM);
  if (d.kind === '상세기준' && m) return d.law + '\u0000' + m[1] + ' ' + m[2];
  return d.law + '\u0000' + articleRef(d.article || '');
}
// 같은 별표·조문(KGS 는 2단계 항목)의 나머지 조각까지 펼쳐 본다(siblings_of).
async function siblings(env, hits) {
  const keys = new Map();
  for (const h of hits) if (h.kind !== '확정') keys.set(verifyKey(h), h);
  if (!keys.size) return [];
  const conds = [], binds = [];
  for (const h of [...keys.values()].slice(0, 30)) {
    const m = (h.article || '').match(KGS_ITEM);
    const pre = h.kind === '상세기준' && m ? `[${m[1]} ${m[2]}` : articleRef(h.article || '');
    binds.push(h.law, pre.replace(/[%_]/g, '') + '%');
    conds.push(`(law = ?${binds.length - 1} AND article LIKE ?${binds.length})`);
  }
  try {
    const { results } = await env.DB.prepare(`SELECT law, article, kind, country, content FROM docs WHERE ${conds.join(' OR ')}`).bind(...binds).all();
    return results.filter(d => keys.has(verifyKey({ ...d, kind: d.kind || null }))).map(d => {
      let t = `${d.article} ${d.content}`;
      if (d.country === '일본') t += ' ' + jpRefsAsKorean(t);
      return t;
    });
  } catch (e) { return []; }
}
function lawKind(k) { return k.endsWith('시행규칙') ? '규칙' : k.endsWith('시행령') ? '령' : '법'; }
function lawInHits(law, ref, hits) {
  let lk = lawKey(law);
  for (const [short, full] of Object.entries(C.law_short)) if (lk.startsWith(short)) { lk = full + lk.slice(short.length); break; }
  if (lk.length < 4) return true;
  return hits.some(h => {
    const hk = lawKey(h.law || '');
    const same = lk.includes(hk) || hk.includes(lk) || (lk.slice(0, 4) === hk.slice(0, 4) && lawKind(lk) === lawKind(hk));
    return same && noWs(h.article || '').includes(ref);
  });
}
// sib: siblings() 결과. 한 답변에 여러 번 검증해도 D1 은 한 번만 부른다.
export function verify(answer, hits, userText, sib) {
  const body = splitFollowups(answer)[0];
  const flat = noWs([...sib, ...hits.map(h => h.content), userText || ''].join(' '));
  const badNums = uniq(body.match(NUM_RE) || []).filter(n => !flat.includes(noWs(n)));
  const badRefs = uniq(body.match(REF_RE) || []).filter(r => !flat.includes(noWs(r)));
  for (const m of body.matchAll(NAMED_REF)) {
    const law = m[1].trim(), ref = noWs(m[2]);
    if (!lawInHits(law, ref, hits)) badRefs.push(`${law} ${m[2]}`);
  }
  const flatOrg = flat.replace(/[ㆍ·]/g, '');
  for (const o of uniq(body.match(ORG_RE) || [])) if (!flatOrg.includes(o.replace(/[ㆍ·\s]/g, ''))) badRefs.push(o);
  const warn = [];
  if (badRefs.length) warn.push('근거에 없는 조문 번호: ' + badRefs.slice(0, 5).join(', '));
  if (badNums.length) warn.push('근거에서 확인 안 된 수치: ' + badNums.slice(0, 5).join(', '));
  return { warnings: warn, nums: badNums.slice(0, 20), refs: badRefs.slice(0, 20) };
}
export { siblings };

const SENT_SPLIT = /(?<=[.다요])\s+(?=[가-힣A-Z(\[「])/;
const reEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
export function stripUnverified(body, bad) {
  if (!bad.length) return [body, []];
  const pat = new RegExp(bad.map(b => reEsc(b).replace(/ /g, '\\s*')).join('|'));
  const removed = [], lines = [];
  for (const line of body.split('\n')) {
    if (!pat.test(line)) { lines.push(line); continue; }
    if (line.trimStart().startsWith('|')) { removed.push(line.trim()); continue; }
    const kept = [];
    for (const s of line.split(SENT_SPLIT)) {
      if (pat.test(s)) removed.push(s.trim());
      else if (/^[\s\[\]\d,.]*$/.test(s)) continue;
      else kept.push(s);
    }
    if (kept.length) lines.push(kept.join(' '));
  }
  if (removed.length) lines.push(`\n(근거 조문에서 확인되지 않아 뺀 내용이 ${removed.length}곳 있습니다. 원문을 직접 확인해 주세요.)`);
  return [lines.join('\n').trim(), removed];
}

const CITE_ANY = /\[\d{1,2}(?:\s*,\s*\d{1,2})*\]|\[[^\[\]\n]{2,70}?(?:제\d+조|별표\s*\d|KGS\s*[A-Z]{2}\d{3})[^\[\]\n]*\]/;
const FACTY = /\d|조문|별표|서식|허가|신고|검사|공사|장관|구청장|이내|이상|이하/;
export function uncitedSentences(body) {
  const out = [];
  for (const line of body.split('\n')) {
    const s0 = line.trim();
    if (!s0 || (['|', '#', '(근거', '•', '*', '-'].some(p => s0.startsWith(p)) && s0.includes('|'))) continue;
    if (s0.startsWith('|')) {
      if (/\d/.test(s0) && !/^[\s|:\-]+$/.test(s0) && !CITE_ANY.test(s0)) out.push(s0);
      continue;
    }
    for (let s of line.split(SENT_SPLIT)) {
      s = s.trim().replace(/^[•*\- ]+/, '');
      if (s.length > 12 && FACTY.test(s) && !CITE_ANY.test(s) && !s.endsWith('?') && !s.endsWith('：') && !s.endsWith(':')) out.push(s);
    }
  }
  return out.slice(0, 30);
}
export function citedRefs(body, shown) {
  const nums = new Set();
  for (const g of body.matchAll(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]/g)) for (const x of g[1].match(/\d+/g)) nums.add(+x);
  return shown.filter(s => nums.has(s.n) || body.includes(s.ref.replace(/^[\[\]]+|[\[\]]+$/g, ''))
    || body.includes(jpRefsAsKorean(s.ref) || '\u0000')).map(s => s.ref);
}

// ── 모델 부르기 ──
export async function callModel(model, prompt, key) {
  try {
    const r = await fetch(`${API}/${model}:generateContent?key=${key}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.2, maxOutputTokens: 2048 } }),
      signal: AbortSignal.timeout(120000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    return (d.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join('') || null;
  } catch (e) { return null; }
}
export async function correctAnswer(model, answer, context, bad, key) {
  const prompt = C.correct_prompt.replace('{bad}', bad.join(', ')).replace('{context}', context).replace('{answer}', answer);
  const t = await callModel(model, prompt, key);
  return t && t.trim().length >= 40 ? t : null;
}
export async function judgeAnswer(body, context, key, answerModel) {
  const sents = body.split('\n').flatMap(l => l.split(SENT_SPLIT)).map(s => s.trim())
    .filter(s => s.length > 8 && !s.startsWith('|') && !s.startsWith('#') && !s.startsWith('(근거'));
  if (!sents.length) return null;
  const numbered = sents.slice(0, 40).map((s, i) => `${i + 1}. ${s}`).join('\n');
  const judge = answerModel.startsWith('gemini-3') ? 'gemini-2.5-flash' : 'gemini-3.1-flash-lite';
  const text = await callModel(judge, C.judge_prompt.replace('{context}', context).replace('{numbered}', numbered), key);
  const m = text && text.match(/\[[\d,\s]*\]/);
  if (!m) return null;
  try { return JSON.parse(m[0]).filter(i => Number.isInteger(i) && i >= 1 && i <= sents.length).map(i => sents[i - 1]); } catch (e) { return null; }
}
export async function* streamModel(model, contents, key, system) {
  const r = await fetch(`${API}/${model}:streamGenerateContent?alt=sse&key=${key}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents, systemInstruction: { parts: [{ text: system }] },
      generationConfig: { temperature: 0.2, maxOutputTokens: 8192 } }),
  });
  if (!r.ok) { if (r.status === 429) markExhausted(model); const e = new Error(`${model} ${r.status}`); e.status = r.status; throw e; }
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line.startsWith('data:')) continue;
      try {
        const cand = JSON.parse(line.slice(5)).candidates[0];
        const t = (cand.content?.parts || []).map(p => p.text || '').join('');
        if (t) yield t;
        if (cand.finishReason === 'MAX_TOKENS') yield '\n\n…(답변이 길어 여기서 끊겼습니다. 더 좁혀서 물어봐 주세요)';
      } catch (e) { /* 조각이 덜 왔다 */ }
    }
  }
}
export function parseFollowups(text) {
  const m = text.match(FOLLOW_RE);
  if (!m) return [];
  const out = [];
  for (let line of text.slice(m.index + m[0].length).split(/\r?\n/)) {
    line = line.trim().replace(/^[-*•]+/, '').trim().replace(/^\d+[.)]\s*/, '').trim();
    if (line.startsWith('(') && line.endsWith(')')) line = line.slice(1, -1).trim();
    line = line.replace(/^\(?\s*질문\s*\d*\s*\)?\s*/, '').trim();
    if (line.length >= 4 && line.length <= 60) out.push(line);
  }
  return out.slice(0, 3);
}

export const chatExtras = {
  search, searchForms, rewriteQuery, cacheKey, cacheGet, cachePut, demoLookup, regCasesFor, factsMatch,
  groupSources, buildContext, siblings, verify, stripUnverified, uncitedSentences, citedRefs, correctAnswer,
  judgeAnswer, streamModel, parseFollowups, splitFollowups, isExhausted,
  CHECKLIST_RE, CHANGE, SMALLTALK, META, BUNDLES: S.bundles,
};
