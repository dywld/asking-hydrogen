// /api/review/* : 공사 쪽 서류 자동 검토(review.py 를 옮김). 접수함·첨부파일은 D1.
import MISC from './misc_data.json';

const FORMS = MISC.forms;
const RED = 'red', ORG = 'org';
const CHAIN = ['gemini-3.5-flash-lite', 'gemini-flash-lite-latest', 'gemini-2.5-flash-lite'];
const API = 'https://generativelanguage.googleapis.com/v1beta/models';

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}

// 한국 시각(파이썬 서버의 time.strftime 과 같게)
function kst(offsetSec = 0) {
  const d = new Date(Date.now() + 9 * 3600e3 + offsetSec * 1000);
  const p = n => String(n).padStart(2, '0');
  return { y: String(d.getUTCFullYear()), m: p(d.getUTCMonth() + 1), d: p(d.getUTCDate()), H: p(d.getUTCHours()), M: p(d.getUTCMinutes()) };
}
const dot = t => `${t.y}. ${t.m}. ${t.d}.`.replace(/ 0/g, ' ');

export function bizOk(s) {
  const d = String(s).replace(/\D/g, '').split('').map(Number);
  if (d.length !== 10) return false;
  const w = [1, 3, 7, 1, 3, 7, 1, 3, 5];
  let t = 0;
  for (let i = 0; i < 9; i++) t += d[i] * w[i];
  t += Math.floor(d[8] * 5 / 10);
  return (10 - t % 10) % 10 === d[9];
}

const formName = f => `${f.law} 별지 제${f.no}호서식`;
const NW = '(?![\\p{L}\\p{N}_])';   // 파이썬 \b(유니코드) 흉내
const RE_AREA = new RegExp(`(시|군|구)${NW}|(시|군|구)\\s`, 'u');
const RE_UNIT = new RegExp(`㎥|m3|kg|톤|t${NW}|L|ℓ`, 'iu');

export function check(fid, vals, docs) {
  const f = FORMS[fid];
  const basis = formName(f);
  const out = [];
  const labels = {};
  for (const t of f.fields) labels[t[0]] = t[1].split(' (')[0];
  const add = (lv, key, title, why, b = basis) =>
    out.push({ lv, key, label: key in labels ? labels[key] : key, title, why, basis: b });
  for (const [key, label] of Object.entries(labels)) {
    const v = String(vals[key] || '').trim();
    if (!v) { add(RED, key, `${label} 빈칸`, '서식의 필수 기재 칸이 비어 있습니다.'); continue; }
    if (key === 'bizno') {
      const n = v.replace(/\D/g, '');
      if (n.length !== 10) add(RED, key, '사업자등록번호 자리수 오류', `${n.length}자리입니다. 10자리여야 합니다.`);
      else if (!bizOk(v)) add(RED, key, '사업자등록번호 검증 숫자 불일치', '마지막 자리 검증 숫자가 계산값과 다릅니다. 오기 가능성이 큽니다.');
    } else if (key === 'tel') {
      if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(v.replace(/ /g, ''))) add(RED, key, '전화번호 형식 오류', '지역번호-국번-번호 형식이 아닙니다.');
    } else if (key === 'email') {
      if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(v)) add(RED, key, '전자우편 형식 오류', '주소에 @ 와 도메인이 필요합니다.');
    } else if (key === 'office' || key === 'site') {
      if (!RE_AREA.test(v + ' ')) add(ORG, key, `${label} 행정구역 불명확`, '시·군·구가 보이지 않습니다. 관할 확인이 어렵습니다.');
      else if (!/\d/.test(v)) add(ORG, key, `${label} 번지 없음`, '도로명 번호나 지번이 없습니다.');
    } else if (key === 'cap') {
      const m = v.match(/[\d,.]+/);
      if (!m) add(RED, key, '저장능력 수치 없음', '숫자와 단위를 함께 적어야 합니다.');
      else if (!RE_UNIT.test(v)) add(ORG, key, '저장능력 단위 없음', '㎥·kg 등 단위가 없어 규모를 판단할 수 없습니다.');
      else if (v.includes('톤') && (parseFloat(m[0].replace(/,/g, '')) || 0) >= 1000)
        add(ORG, key, '저장능력 단위 의심', '수소 시설로는 매우 큰 값입니다. kg 오기인지 확인이 필요합니다.');
    }
  }
  if (vals.office && vals.site && vals.office.trim() === vals.site.trim())
    add(ORG, 'site', '사업소 주소가 본사와 같음', '시설이 본사 건물 안에 있는지 현장 확인이 필요합니다.');
  if (!('sign' in labels)) labels.sign = '신청인 서명';
  if (!String(vals.sign || '').startsWith('data:image'))
    add(RED, 'sign', '신청인 서명 없음', "서식 하단의 '(서명 또는 인)' 칸이 비어 있습니다. 서명이 없으면 접수할 수 없습니다.", basis + ' 신청인 서명란');
  for (const d of f.docs)
    if (!docs.includes(d)) add(RED, 'docs', `첨부 누락: ${d}`, '서식 본문의 첨부서류 목록에 있으나 제출되지 않았습니다.', basis + ' 첨부서류란');
  return out;
}

export function verdict(fs) {
  if (fs.some(x => x.lv === RED)) return '반려 예상';
  return fs.length ? '확인 필요' : '승인 가능';
}

export function letter(item) {
  const f = FORMS[item.fid];
  const ko = '가나다라마바사아자차카타파하';
  const day = dot(kst()), due = dot(kst(14 * 86400));
  const lines = [`수신  ${item.vals.company || '신청인'} 대표 ${item.vals.ceo || ''}`.trimEnd(),
    `제목  ${f.title} 신청서 보완 요청`, '',
    `1. 귀사에서 ${item.date} 신청한 ${f.title} 신청서(${formName(f)})를 검토한 결과, 아래 사항의 보완이 필요하여 알려 드립니다.`,
    '2. 보완 사항'];
  item.findings.forEach((x, i) => lines.push(`  ${ko[i % ko.length]}. ${x.title}: ${x.why}`));
  lines.push(`3. 보완 기한: ${due}까지`, '', `한국가스안전공사  ${day}`);
  return lines.join('\n');
}

// ── D1 ──
async function loadAll(env) {
  const r = await env.DB.prepare('SELECT data FROM review_items ORDER BY seq').all();
  return r.results.map(x => JSON.parse(x.data));
}
async function saveItem(env, item, seq) {
  const s = JSON.stringify(item);
  if (seq == null) await env.DB.prepare('UPDATE review_items SET data=? WHERE id=?').bind(s, item.id).run();
  else await env.DB.prepare('INSERT INTO review_items (id, seq, data) VALUES (?,?,?)').bind(item.id, seq, s).run();
}

async function submit(env, fid, vals, docs, { demo = false, files = [], ai = null, fchk = null } = {}) {
  if (!(fid in FORMS)) throw new Error('서식 id 가 없습니다');
  const fs = check(fid, vals, docs);
  const f = FORMS[fid];
  if (ai) {
    const rows = f.fields.map(t => [t[0], t[1].split(' (')[0], String(vals[t[0]] || '').trim()]);
    const names = Object.fromEntries(rows.map(r => [r[0], r[1]]));
    const seen = new Set(fs.map(x => x.key));
    try {
      for (const x of ((await ai) || []).slice(0, 3)) {
        const k = String(x.key ?? '');
        if (k in names && !seen.has(k)) {
          fs.push({ lv: ORG, key: k, label: names[k], title: String(x.title ?? '').slice(0, 40), why: String(x.why ?? '').slice(0, 120),
            basis: 'AI 내용 판단(참고, 담당자 확인)' });
          seen.add(k);
        }
      }
    } catch (e) { /* 규칙 검토만 */ }
  }
  for (const c of (await fchk) || []) {
    if (c.ok === false)
      fs.push({ lv: ORG, key: 'docs', label: '첨부서류', title: `첨부 내용 의심: ${c.doc}`.slice(0, 40),
        why: `'${c.name}' ${c.why || ''}`.trim().slice(0, 120), basis: 'AI 첨부파일 판독(참고, 담당자 확인)' });
  }
  const now = kst();
  const r = await env.DB.prepare('SELECT COUNT(*) AS n, COALESCE(MAX(seq),0) AS s FROM review_items').first();
  const n = r.n + 1;
  const item = { id: `${now.y}-${String(n).padStart(4, '0')}`, fid, title: f.title, vals, docs, findings: fs, verdict: verdict(fs),
    date: dot(now), time: `${now.H}:${now.M}`, status: '접수', letter: '', demo, files: files || [] };
  await saveItem(env, item, r.s + 1);
  return item;
}

async function seed(env) {
  const okBiz = '000-00-00015';
  const F = FORMS;
  const demo = [
    ['gas_permit', { company: '동해에너지(주)', ceo: '최민준', office: '강원 동해시 해안로 5', site: '강원 동해시 해안로 5', tel: '033-530-7788',
      bizno: '000-00-0001', email: 'safety@donghae.example' }, F.gas_permit.docs.slice(0, 2)],
    ['gas_use', { company: '춘천모빌리티', ceo: '이도윤', office: '강원 춘천시 퇴계로 88', site: '강원 춘천시 퇴계로 90', tel: '033-555-0101',
      bizno: okBiz, gas: '수소', cap: '50000 톤', purpose: '연료전지 시험', month: '200 ㎥' }, F.gas_use.docs],
    ['gas_permit', { company: '원주가스', ceo: '박서연', office: '강원 원주시 단계로 21', site: '강원 원주시 문막읍 산업로 7', tel: '033-742-1100',
      bizno: okBiz, email: 'admin@wonju.example' }, F.gas_permit.docs],
  ];
  for (const [fid, v, d] of demo) {
    const base = Object.fromEntries(F[fid].fields.map(t => [t[0], t[2]]));
    await submit(env, fid, { ...base, ...v }, d, { demo: true });
  }
}

async function listing(env) {
  const order = { '반려 예상': 0, '확인 필요': 1, '승인 가능': 2 };
  let items = await loadAll(env);
  if (!items.some(x => x.demo)) { await seed(env); items = await loadAll(env); }
  const key = x => [x.status !== '접수' ? 1 : 0, order[x.verdict] ?? 3, x.time];
  return items.sort((a, b) => {
    const ka = key(a), kb = key(b);
    for (let i = 0; i < 3; i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
    return 0;
  });
}

async function getItem(env, id) {
  const r = await env.DB.prepare('SELECT data FROM review_items WHERE id=?').bind(id).first();
  if (!r) return null;
  const x = JSON.parse(r.data);
  if (!x.letter) x.letter = letter(x);
  return x;
}

async function decide(env, id, action, text) {
  const r = await env.DB.prepare('SELECT data FROM review_items WHERE id=?').bind(id).first();
  if (!r) return null;
  const x = JSON.parse(r.data);
  x.status = action === 'approve' ? '승인' : '보완 요청';
  x.letter = text || x.letter || letter(x);
  await saveItem(env, x);
  return x;
}

// ── 첨부파일: base64 그대로 900KB 씩 나눠 D1 에 둔다 ──
const PART = 400_000;
async function saveFiles(env, items) {
  const out = [], kept = [];
  if (!Array.isArray(items)) return { out, kept };
  const box = crypto.randomUUID().replace(/-/g, '');
  const stmts = [];
  items.slice(0, 10).forEach((f, i) => {
    if (!f || typeof f !== 'object' || Array.isArray(f)) return;
    let b64 = String(f.data ?? '');
    const c = b64.indexOf(',');
    if (c >= 0) b64 = b64.slice(c + 1);
    if (/[^A-Za-z0-9+/=]/.test(b64)) b64 = b64.replace(/[^A-Za-z0-9+/]/g, '');   // 파이썬 validate=False 처럼 버린다
    const size = Math.floor(b64.length * 3 / 4);
    if (!size || size > 3_000_000) return;
    let name = String(f.name ?? 'file').replace(/[^\p{L}\p{N}_.\-가-힣 ()]/gu, '_').slice(0, 80).trim() || 'file';
    name = `${i + 1}_${name}`;
    const k = `${box}/${name}`;
    for (let p = 0, j = 0; p < b64.length; p += PART, j++)
      stmts.push(env.DB.prepare('INSERT INTO review_files (k, part, name, b64) VALUES (?,?,?,?)').bind(k, j, name, b64.slice(p, p + PART)));
    const rec = { doc: String(f.doc ?? '').slice(0, 80), name: name.slice(String(i + 1).length + 1), k };
    out.push(rec);
    kept.push({ ...rec, b64 });
  });
  for (const s of stmts) await s.run();     // 한 묶음이 너무 커지지 않게 하나씩
  return { out, kept };
}

const MIME = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif',
  txt: 'text/plain', csv: 'text/csv', md: 'text/markdown', hwp: 'application/x-hwp', hwpx: 'application/haansofthwpx',
  doc: 'application/msword', docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls: 'application/vnd.ms-excel', xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', zip: 'application/zip' };

function b64bytes(s) {
  if (Uint8Array.fromBase64) return Uint8Array.fromBase64(s);
  const bin = atob(s), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
}

async function serveFile(env, k) {
  const m = /^([0-9a-f]{32})\/([^/\\]{1,120})$/.exec(k || '');
  const r = m ? await env.DB.prepare('SELECT b64 FROM review_files WHERE k=? ORDER BY part').bind(k).all() : null;
  if (!r || !r.results.length) return json({ error: '없는 파일' }, 404);
  const data = b64bytes(r.results.map(x => x.b64).join(''));
  const ext = (m[2].split('.').pop() || '').toLowerCase();
  return new Response(data, { headers: {
    'Content-Type': MIME[ext] || 'application/octet-stream',
    'Content-Disposition': "inline; filename*=UTF-8''" + encodeURIComponent(m[2]) } });
}

// ── Gemini ──
async function gemini(env, parts, maxTok) {
  const key = env.GEMINI_API_KEY;
  const body = JSON.stringify({ contents: [{ parts }], generationConfig: { temperature: 0, maxOutputTokens: maxTok, responseMimeType: 'application/json' } });
  for (const model of CHAIN) {
    try {
      const r = await fetch(`${API}/${model}:generateContent?key=${key}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body, signal: AbortSignal.timeout(12000) });
      if (!r.ok) continue;
      const d = await r.json();
      const out = d.candidates[0].content.parts.map(p => p.text || '').join(''); return out;
    } catch (e) { /* 다음 모델 */ }
  }
  return null;
}

const AI_REVIEW_PROMPT = `너는 한국가스안전공사 접수 담당자다. 아래 신청서 칸 값이 내용상 말이 되는지만 본다.
형식(자리수·전화번호 모양)과 빈칸은 이미 다른 검사가 봤으니 보지 마라.
볼 것: 단위가 이상하거나 규모가 비현실적인 값, 신청 종류와 맞지 않는 내용, 뜻이 없는 글자, 칸끼리 서로 어긋나는 내용.
정상적인 값(예: 수소 시설에 '압축수소', 실제 같은 주소·회사명)은 절대 지적하지 마라. 애매하면 지적하지 않는다.
틀렸다고 확신하는 것만, 최대 3개. 문제가 없으면 [] 만 낸다.
JSON 배열만 출력: [{"key":"칸 key","value":"문제인 칸 값 그대로","title":"20자 이내 제목","why":"60자 이내 이유","sure":true}]

신청 종류: {title}
칸:
{rows}`;

async function aiReview(env, fid, vals) {
  const f = FORMS[fid];
  if (!f || !env.GEMINI_API_KEY) return [];
  const filled = f.fields.map(t => [t[0], t[1].split(' (')[0], String(vals[t[0]] || '').trim()]).filter(r => r[2]);
  if (!filled.length) return [];
  const prompt = AI_REVIEW_PROMPT.replace('{title}', f.title).replace('{rows}', filled.map(([k, n, v]) => `- ${k} (${n}): ${v}`).join('\n'));
  const text = await gemini(env, [{ text: prompt }], 400);
  if (!text) return [];
  try {
    const a = text.indexOf('['), b = text.lastIndexOf(']');
    const out = JSON.parse(a >= 0 && b > a ? text.slice(a, b + 1) : '[]');
    const v = Object.fromEntries(filled.map(([k, , x]) => [k, x]));
    return Array.isArray(out) ? out.filter(x => x && typeof x === 'object' && x.sure === true
      && String(x.value ?? '').trim() === String(v[x.key] ?? '').trim()) : [];
  } catch (e) { return []; }
}

// PDF 는 글자를 뽑지 않고 PDF 그대로 Gemini 에 보낸다(워커에는 pymupdf 가 없다).
async function aiCheckFiles(env, files) {
  if (!env.GEMINI_API_KEY || !files.length) return [];
  const res = await Promise.all(files.slice(0, 10).map(async f => {
    const ext = (f.k.split('.').pop() || '').toLowerCase();
    const ask = `이 첨부파일이 '${f.doc}' 서류로 보이는지 판단해라. 파일 이름: ${f.name}\n`
      + '확실히 다른 서류이거나 빈 파일일 때만 ok=false. JSON 만: {"ok":true|false,"why":"40자 이내 이유"}';
    const parts = [{ text: ask }];
    if (ext === 'pdf') parts.push({ inline_data: { mime_type: 'application/pdf', data: f.b64 } });
    else if (['png', 'jpg', 'jpeg', 'webp'].includes(ext))
      parts.push({ inline_data: { mime_type: ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' : `image/${ext}`, data: f.b64 } });
    else if (['txt', 'csv', 'md'].includes(ext)) {
      try { parts.push({ text: '파일 내용:\n' + new TextDecoder().decode(b64bytes(f.b64.slice(0, 13336))).slice(0, 2500) }); } catch (e) { return null; }
    } else return null;
    const t = await gemini(env, parts, 200);
    if (!t) return null;
    try {
      const j = JSON.parse(t.slice(t.indexOf('{'), t.lastIndexOf('}') + 1));
      return { doc: f.doc, name: f.name, ok: Boolean(j.ok ?? true), why: String(j.why ?? '').slice(0, 80) };
    } catch (e) { return null; }
  }));
  return res.filter(Boolean);
}

export async function handleReview(req, env, url) {
  const p = url.pathname;
  if (!p.startsWith('/api/review/')) return null;
  const q = url.searchParams;
  if (req.method === 'GET') {
    if (p === '/api/review/list') return json(await listing(env));
    if (p === '/api/review/item') {
      const x = await getItem(env, q.get('id') || '');
      return json(x || { error: '없는 접수번호' }, x ? 200 : 404);
    }
    if (p === '/api/review/file') return serveFile(env, q.get('k'));
    return null;
  }
  if (req.method !== 'POST' || (p !== '/api/review/submit' && p !== '/api/review/decide')) return null;
  let body;
  try {
    const n = Number(req.headers.get('Content-Length') || 0);
    if (n > (p.endsWith('submit') ? 12_000_000 : 4_000_000)) throw 0;
    body = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await req.arrayBuffer()) || '{}');
    if (body === null || typeof body !== 'object') throw 0;
  } catch (e) {
    return json({ error: '요청 형식이 올바르지 않습니다(UTF-8 JSON)' }, 400);
  }
  try {
    let x;
    if (p.endsWith('submit')) {
      const vals = {};
      const fin = body.fields && typeof body.fields === 'object' ? body.fields : {};
      for (const [k, v] of Object.entries(fin)) vals[String(k).slice(0, 20)] = (typeof v === 'string' ? v : JSON.stringify(v)).slice(0, 120);
      const docs = (Array.isArray(body.docs) ? body.docs : []).map(String).slice(0, 20);
      const fid = body.id;
      if (!(fid in FORMS)) throw new Error('서식 id 가 없습니다');
      const { out: files, kept } = await saveFiles(env, body.files);
      for (const f of files) if (!docs.includes(f.doc)) docs.push(f.doc);
      x = await submit(env, fid, vals, docs, { files, ai: aiReview(env, fid, vals), fchk: aiCheckFiles(env, kept) });
    } else {
      x = await decide(env, String(body.id), body.action, String(body.letter || '').slice(0, 4000));
    }
    return json(x || { error: '없는 접수번호' }, x ? 200 : 404);
  } catch (e) {
    return json({ error: String(e.message || e) }, 400);
  }
}
