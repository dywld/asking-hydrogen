// 윈도우 앱(desktop/) 전용 API. 앱 밖 브라우저에서도 부를 수는 있지만 화면은 앱에만 뜬다.
//   GET  /api/app/version            최신 앱 버전
//   GET  /api/app/notices?since=…    법령 개정 소식 + 최신 버전 (앱이 켜질 때 묻는다)
//   POST /api/app/laws               법령 개정 소식 넣기 (고정 IP 서버의 law_watch.py 가 보낸다, APP_PUSH_KEY)
//   POST /api/app/review             서류 폴더 검토: 파일 여러 개를 Gemini 한 번에 보내 서류 대조·내용 검토
//   POST /api/app/extract            처음 설정(온보딩): 사업자등록증 등에서 회사 정보 칸을 뽑는다. 파일·결과를 저장하지 않는다
import { llmFetch, llmName, llmAll } from './llm.js';            // OPENAI_API_KEY 가 있으면 ChatGPT 로
import DATA from './data.json';

// 새 설치 파일을 낼 때 이 값을 올리고 배포하면, 옛 앱이 켜질 때 "새 버전" 알림을 띄운다.
const APP_LATEST = { version: '0.1.0', notes: '첫 버전', url: '' };
const API = 'https://generativelanguage.googleapis.com/v1beta/models';
const CHAIN = ['gemini-3.5-flash-lite', 'gemini-flash-lite-latest', 'gemini-2.5-flash-lite', 'gemini-2.5-flash'];
// 서식·견본에서 흔히 남는 자리표시
const PLACEHOLDER = /\[직접 입력[^\]]*\]|○○+|◯◯+|_{4,}/g;
const MAX_FILES = 10, MAX_B64 = 18 * 1024 * 1024;   // Gemini 한 번 요청은 20MB 까지

const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });

let tableReady = false;
async function ensureTable(env) {
  if (tableReady) return;
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS law_changes (id INTEGER PRIMARY KEY AUTOINCREMENT,
    law TEXT NOT NULL, promulgated TEXT, effective TEXT, kind TEXT, link TEXT, seen TEXT NOT NULL, UNIQUE(law, promulgated))`).run();
  tableReady = true;
}

async function notices(env, url) {
  await ensureTable(env);
  const since = /^\d{4}-\d{2}-\d{2}/.test(url.searchParams.get('since') || '') ? url.searchParams.get('since') : '0000';
  const { results } = await env.DB.prepare('SELECT law, promulgated, effective, kind, link, seen FROM law_changes WHERE seen > ?1 ORDER BY seen DESC LIMIT 30')
    .bind(since).all();
  return json({ version: APP_LATEST, laws: results, now: new Date().toISOString() });
}

async function pushLaws(req, env) {
  if (!env.APP_PUSH_KEY || req.headers.get('x-push-key') !== env.APP_PUSH_KEY) return json({ error: '권한 없음' }, 403);
  const body = await req.json().catch(() => ({}));
  const rows = (Array.isArray(body.changes) ? body.changes : []).slice(0, 100)
    .filter(c => c && typeof c.law === 'string' && c.law.trim());
  await ensureTable(env);
  const now = new Date().toISOString();
  const st = env.DB.prepare('INSERT OR IGNORE INTO law_changes (law, promulgated, effective, kind, link, seen) VALUES (?1, ?2, ?3, ?4, ?5, ?6)');
  if (rows.length) await env.DB.batch(rows.map(c => st.bind(c.law.slice(0, 100), String(c.promulgated || '').slice(0, 10),
    String(c.effective || '').slice(0, 10), String(c.kind || '').slice(0, 20), String(c.link || '').slice(0, 300), now)));
  return json({ ok: true, n: rows.length });
}

const REVIEW_PROMPT = `너는 한국가스안전공사 인허가 접수 담당자다. 사업자가 '{title}' 신청을 위해 서류 폴더를 올렸다.
이 신청에 내야 하는 서류(번호):
{docs}
관할: {who} · 처리 기간: {days} · 수수료: {fee}
{before}
아래 파일을 하나씩 읽고 판단해라.
1. 각 파일이 위 서류 중 몇 번인지(doc, 숫자). 어느 것도 아니면 0.
2. 그 서류로서 내용에 문제가 있는지(issues). 볼 것: 빈칸으로 남은 필수 칸, 서명·날인 칸이 비어 있음, 회사명·주소·대표자가 파일끼리 서로 다름,
   '[직접 입력]'·'○○' 같은 자리표시가 남음, 날짜가 앞뒤가 안 맞거나 오래됨, 신청 종류와 맞지 않는 내용, 단위·규모가 비현실적인 값, 다른 서류인데 이름만 바꾼 경우.
   확실한 것만 최대 4개, 각 60자 이내. 문제 없으면 [].
3. ok: 그 서류로 그대로 내도 되면 true.
정상적인 내용은 지적하지 마라. 애매하면 지적하지 않는다. 읽지 못한 파일은 doc 0, ok false, issues ["내용을 읽지 못함"].
JSON 만 출력:
{"files":[{"name":"파일 이름 그대로","doc":1,"ok":true,"issues":[]}],"summary":"전체 한두 문장(100자 이내)"}`;

async function gemini(env, parts) {
  const body = JSON.stringify({ contents: [{ parts }], generationConfig: { temperature: 0, maxOutputTokens: 2048, responseMimeType: 'application/json' } });
  let last = '';
  for (const model of CHAIN) {
    try {
      const r = await llmFetch(`${API}/${model}:generateContent?key=${env.GEMINI_API_KEY}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: AbortSignal.timeout(90000) });
      if (!r.ok) { last = `${model} ${r.status}${r.status === 400 ? ' ' + ((await r.text().catch(() => '')).match(/"message":\s*"([^"]{0,100})/)?.[1] || '') : ''}`; continue; }
      const d = await r.json();
      const t = (d.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join('');
      if (t) return { text: t, model };
      last = `${model} 빈 응답`;
    } catch (e) { last = `${model} ${e.name === 'TimeoutError' ? '시간 초과' : '오류'}`; }
  }
  return { error: last || '모델 없음' };
}

async function review(req, env) {
  if (!env.GEMINI_API_KEY) return json({ error: '서버에 API 키가 없습니다' }, 500);
  const body = await req.json().catch(() => ({}));
  const permit = (DATA.permit || []).find(p => p.id === body.permit);
  if (!permit) return json({ error: '허가 종류를 골라 주세요' }, 400);
  const files = (Array.isArray(body.files) ? body.files : []).slice(0, MAX_FILES)
    .filter(f => f && typeof f.name === 'string' && !f.warn && (f.text || f.b64));
  if (!files.length) return json({ error: '읽을 수 있는 파일이 없습니다' }, 400);
  if (files.reduce((n, f) => n + (f.b64 ? f.b64.length : 0), 0) > MAX_B64) return json({ error: '파일이 너무 큽니다. 한 번에 18MB 안으로 골라 주세요' }, 413);

  // 신청서 자체도 내야 하는 서류로 센다(permit.docs 는 붙임 서류만 적혀 있다).
  const docs = [`신청서 (${permit.form || permit.title})`, ...permit.docs];
  const prompt = REVIEW_PROMPT.replace('{title}', permit.title).replace('{docs}', docs.map((d, i) => `${i + 1}. ${d}`).join('\n'))
    .replace('{who}', permit.who || '-').replace('{days}', permit.days || '-').replace('{fee}', permit.fee || '-')
    .replace('{before}', permit.before ? '미리 할 일: ' + permit.before : '');
  const parts = [{ text: prompt }];
  for (const f of files) {
    parts.push({ text: `\n=== 파일: ${f.name.slice(0, 120)}${f.cut ? ' (길어서 앞부분만)' : ''}${f.note ? ' (' + f.note + ')' : ''} ===` });
    if (f.b64 && /^(application\/pdf|image\/(png|jpeg|webp))$/.test(f.mime || '')) parts.push({ inline_data: { mime_type: f.mime, data: f.b64 } });
    else parts.push({ text: String(f.text || '').slice(0, 6000) });
  }
  const g = await gemini(env, parts);
  if (g.error) return json({ error: `AI 검토를 못 했습니다 (${g.error}). 잠시 뒤 다시 해 주세요.` }, 502);
  let out;
  try { const t = g.text; out = JSON.parse(t.slice(t.indexOf('{'), t.lastIndexOf('}') + 1)); } catch (e) { return json({ error: 'AI 답을 읽지 못했습니다. 다시 해 주세요.' }, 502); }

  // 모델 답은 그대로 믿지 않는다: 파일 이름·서류 이름은 보낸 것 안에서만, 빠진 서류는 여기서 센다.
  const names = new Set(files.map(f => f.name));
  const res = (Array.isArray(out.files) ? out.files : []).filter(x => x && names.has(x.name)).map(x => ({
    name: x.name,
    doc: docs[Number(x.doc) - 1] || '기타',
    ok: x.ok === true,
    issues: (Array.isArray(x.issues) ? x.issues : []).map(s => String(s).slice(0, 80)).slice(0, 4),
  }));
  for (const f of files) if (!res.some(r => r.name === f.name)) res.push({ name: f.name, doc: '기타', ok: false, issues: ['AI 가 이 파일을 판단하지 않았습니다'] });
  // 자리표시가 남은 글 파일은 AI 판단과 상관없이 고칠 곳으로 센다(AI 는 실행마다 놓치기도 한다).
  for (const r of res) {
    const f = files.find(x => x.name === r.name);
    const left = f && f.text ? [...new Set(String(f.text).match(PLACEHOLDER) || [])] : [];
    if (left.length) { r.ok = false; r.issues = [`채우지 않은 칸이 남아 있음: ${left.slice(0, 3).join(', ')}`, ...r.issues].slice(0, 4); }
  }
  const have = new Set(res.filter(r => r.doc !== '기타').map(r => r.doc));
  return json({
    permit: { id: permit.id, title: permit.title, docs, who: permit.who, days: permit.days, form: permit.form },
    files: res,
    missing: docs.filter(d => !have.has(d)),
    summary: String(out.summary || '').slice(0, 200),
    model: llmAll() ? llmName() : g.model,
  });
}

// ── 처음 설정(온보딩): 서류에서 회사 정보 뽑기 ──
// 사업자등록증·법인등기부·허가증 등을 읽어 신청서 공통 칸(formMemo)을 채운다.
// 파일과 결과는 어디에도 저장하지 않고 답만 돌려준다(저장은 손님 컴퓨터의 localStorage).
const EXTRACT_PROMPT = `아래는 한 회사가 가진 서류 파일들이다(사업자등록증, 법인 등기사항증명서, 기존 허가증, 회사 소개서 등).
서류에 실제로 적힌 값만 옮겨라. 추측하거나 만들어 내지 마라. 없으면 빈 문자열.
- company: 상호(법인명)
- ceo: 대표자 성명
- bizno: 사업자등록번호 (000-00-00000)
- office: 사업장(본점) 소재지 주소
- tel: 회사 전화번호
- email: 회사 이메일
- site: 수소 시설(충전소·제조소 등)이 따로 적혀 있으면 그 주소
- mgr_name, mgr_qual, mgr_no: 안전관리자 자격증이 있으면 성명, 자격 종목(예: 가스산업기사), 자격증 번호
- permit_no, permit_date: 기존 허가증이 있으면 허가번호, 허가 일자
각 파일이 무슨 서류인지도 15자 이내로 적어라(예: 사업자등록증, 법인 등기사항증명서, 고압가스 제조허가증, 기타).
JSON 만 출력:
{"fields":{"company":"","ceo":"","bizno":"","office":"","tel":"","email":"","site":"","mgr_name":"","mgr_qual":"","mgr_no":"","permit_no":"","permit_date":""},"docs":[{"name":"파일 이름 그대로","type":"사업자등록증"}]}`;
const FIELD_KEYS = ['company', 'ceo', 'bizno', 'office', 'tel', 'email', 'site', 'mgr_name', 'mgr_qual', 'mgr_no', 'permit_no', 'permit_date'];

async function extract(req, env) {
  if (!env.GEMINI_API_KEY) return json({ error: '서버에 API 키가 없습니다' }, 500);
  const body = await req.json().catch(() => ({}));
  const files = (Array.isArray(body.files) ? body.files : []).slice(0, MAX_FILES)
    .filter(f => f && typeof f.name === 'string' && (f.text || f.b64));
  if (!files.length) return json({ error: '읽을 수 있는 파일이 없습니다' }, 400);
  if (files.reduce((n, f) => n + (f.b64 ? String(f.b64).length : 0), 0) > MAX_B64) return json({ error: '파일이 너무 큽니다. 한 번에 18MB 안으로 골라 주세요' }, 413);
  const parts = [{ text: EXTRACT_PROMPT }];
  for (const f of files) {
    parts.push({ text: `\n=== 파일: ${f.name.slice(0, 120)} ===` });
    if (f.b64 && /^(application\/pdf|image\/(png|jpeg|webp))$/.test(f.mime || '')) parts.push({ inline_data: { mime_type: f.mime, data: String(f.b64) } });
    else parts.push({ text: String(f.text || '').slice(0, 6000) });
  }
  const g = await gemini(env, parts);
  if (g.error) return json({ error: `AI 가 서류를 읽지 못했습니다 (${g.error}). 직접 입력하거나 잠시 뒤 다시 해 주세요.` }, 502);
  let out;
  try { const t = g.text; out = JSON.parse(t.slice(t.indexOf('{'), t.lastIndexOf('}') + 1)); } catch (e) { return json({ error: 'AI 답을 읽지 못했습니다. 다시 해 주세요.' }, 502); }
  const fields = {};
  for (const k of FIELD_KEYS) {
    const v = String(out.fields?.[k] ?? '').replace(/\s+/g, ' ').trim().slice(0, 120);
    if (v && !/^(없음|모름|null|undefined|-)$/i.test(v)) fields[k] = v;
  }
  if (fields.bizno) {                                  // 숫자 10자리가 아니면 버린다
    const d = fields.bizno.replace(/\D/g, '');
    if (d.length === 10) fields.bizno = `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`; else delete fields.bizno;
  }
  if (fields.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(fields.email)) delete fields.email;
  const names = new Set(files.map(f => f.name));
  const docs = (Array.isArray(out.docs) ? out.docs : []).filter(d => d && names.has(d.name))
    .map(d => ({ name: d.name, type: String(d.type || '기타').slice(0, 20) }));
  return json({ fields, docs, model: llmAll() ? llmName() : g.model });
}

export async function handleApp(req, env, url) {
  const p = url.pathname;
  if (!p.startsWith('/api/app/')) return null;
  if (p === '/api/app/version') return json(APP_LATEST);
  // D1 한도가 바닥나도 버전 알림은 나가게
  if (p === '/api/app/notices') return notices(env, url).catch(() => json({ version: APP_LATEST, laws: [], now: new Date().toISOString() }));
  if (p === '/api/app/laws' && req.method === 'POST') return pushLaws(req, env);
  if (p === '/api/app/review' && req.method === 'POST') return review(req, env);
  if (p === '/api/app/extract' && req.method === 'POST') return extract(req, env);
  return json({ error: '없는 주소' }, 404);
}
