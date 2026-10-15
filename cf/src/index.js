// hydrogen-guide: 노트북·오라클 없이 클라우드플레어에서만 도는 수소 인허가 챗봇.
// 화면(index.html·review.html)은 정적 파일로 나가고, /api/* 만 이 워커가 받는다.
// 검색: D1 FTS5(본문을 글자 2개씩 자른 색인) → bm25 순 → 제목 가산 → 상위 12조각.
// 답변: Gemini 스트리밍. 노트북 서버(app.py)와 같은 지침·같은 NDJSON 이벤트를 쓴다.
import DATA from './data.json';
import { handleReview } from './review.js';     // /api/review/*  (D1)
import { handleMisc } from './misc.js';         // /api/share·feedback·distance·sandbox/cases·byl
import { handleDocs } from './docs.js';         // /api/permit/*·sandbox/file·preview·editor (문서 만들기)
import { chatExtras } from './chat_extras.js'; // 캐시·발표 잠금·규제 사례·확정 자료

const HANGUL = /[가-힣]+/g, CJK = /[一-鿿ぁ-ゟ゠-ヿ]+/g, WORD = /[A-Za-z0-9]+/g;
const FILLER = new RegExp(DATA.filler, 'g');
const PERMIT_RE = new RegExp(DATA.permit_re), SANDBOX_RE = new RegExp(DATA.sandbox_re);
const FOLLOW_RE = /#{2,4}\s*다음\s*질문\s*/;
const API = 'https://generativelanguage.googleapis.com/v1beta/models';

function tokenize(text) {
  const t = text.toLowerCase(), out = [];
  for (const m of [...(t.match(HANGUL) || []), ...(t.match(CJK) || [])]) {
    if (m.length === 1) out.push(m);
    else for (let i = 0; i < m.length - 1; i++) out.push(m.slice(i, i + 2));
  }
  return out.concat(t.match(WORD) || []);
}
function expand(q) {
  const extra = Object.entries(DATA.expand).filter(([k]) => q.includes(k)).map(([, v]) => v);
  return q.replace(FILLER, ' ') + ' ' + extra.join(' ');
}
const articleRef = a => a.includes(']') ? a.slice(0, a.indexOf(']') + 1) : a;

// 검색은 chat_extras.js 가 맡는다(search.py 의 점수 규칙을 D1 SQL 로 옮김).
async function search(env, query, k = 12, opts = {}) {
  return chatExtras.search(env, query, { ...opts, top_k: k });
}


function groupSources(hits) {
  const groups = new Map();
  for (const h of hits) {
    const key = h.law + '|' + h.ref;
    let g = groups.get(key);
    if (!g) groups.set(key, g = { law: h.law, ref: h.ref, title: h.title, country: h.country, score: h.score,
      future: !!h.future, effective_date: h.effective_date || null, kind: h.kind || null, parts: [], link: h.link });
    g.score = Math.max(g.score, h.score);
    g.parts.push(h.content);
  }
  const out = [...groups.values()].sort((a, b) => b.score - a.score).slice(0, 12);
  out.forEach((g, i) => g.n = i + 1);
  return out;
}

function buildContext(hits, groups) {
  const num = new Map(groups.map(g => [g.law + '|' + g.ref, g.n]));
  return hits.map((h, i) => {
    const n = num.get(h.law + '|' + h.ref) || i + 1;
    const tag = h.future ? ` (시행 예정: ${h.effective_date})` : h.kind === '별지서식' ? ' (별지 서식 — 제출 서류 이름과 용도)' : '';
    return `[${n}] ${h.country} · ${h.law} ${h.article}(${h.title})${tag}\n${h.content}`;
  }).join('\n\n');
}

function parseFollowups(text) {
  const m = text.match(FOLLOW_RE);
  if (!m) return [];
  return text.slice(m.index + m[0].length).split('\n').map(l => l.replace(/^\s*[-*\d.)]+\s*/, '').trim())
    .filter(Boolean).slice(0, 3);
}

function guessForm(q) {
  for (const [fid, words] of DATA.guess) if (words.some(w => q.includes(w))) return fid;
  return null;
}

// 모델 하나에 스트리밍으로 묻는다. 성공하면 글 조각을 차례로 넘긴다.
async function* streamGemini(model, contents, key) {
  const r = await fetch(`${API}/${model}:streamGenerateContent?alt=sse&key=${key}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents, systemInstruction: { parts: [{ text: DATA.system }] },
      generationConfig: { temperature: 0.2, maxOutputTokens: 2048 } }),
  });
  if (!r.ok) { const e = new Error(`${model} ${r.status}`); e.status = r.status; throw e; }
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
        const d = JSON.parse(line.slice(5));
        const t = (d.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join('');
        if (t) yield t;
      } catch (e) { /* 조각이 덜 왔다 */ }
    }
  }
}


// ── 답하기 전에 조건부터 묻기(app.py ask_for·clarify_for·profile_note·sandbox_note 를 옮긴 것) ──
const ASK = DATA.ask.map(([need, steps]) => [new RegExp(need), steps.map(([k, t, o, h]) => [k, t, o, new RegExp(h)])]);
const DIST_OTHER = new RegExp(DATA.dist_other);
const CLARIFY = DATA.clarify.map(([n, h, t, o]) => [new RegExp(n), new RegExp(h), t, o]);
const PROFILE_KEYS = ['kind', 'stage', 'region', 'facility', 'capacity', 'near', 'zone'];
const SB_KEYS = ['kind', 'name', 'what', 'area', 'period', 'scale', 'company'];

function cleanObj(p, keys, n = 30) {
  const out = {};
  if (!p || typeof p !== 'object') return out;
  for (const k of keys) if (typeof p[k] === 'string' && p[k].trim() && p[k] !== '모름') out[k] = p[k].trim().slice(0, n);
  return out;
}
function askFor(q, profile) {
  for (const [need, steps] of ASK) {
    if (!need.test(q)) continue;
    if (steps[0][0] === 'dist' && DIST_OTHER.test(q)) return null;
    const todo = steps.filter(([k, , , has]) => !has.test(q) && !(k in profile))
      .map(([k, t, o]) => typeof o === 'string' ? { key: k, q: t, text: o } : { key: k, q: t, options: [...o, '모름'] });
    for (const s of todo) {
      if (s.key === 'dist') s.stop = '보호시설';
      if (s.key === 'facility' && profile.kind === '수소충전소') s.options = ['제조식 수소충전소', '저장식 수소충전소', DATA.other, '모름'];
    }
    return todo.length ? todo : null;
  }
  return null;
}
function clarifyFor(q) {
  for (const [need, has, text, options] of CLARIFY) if (need.test(q) && !has.test(q)) return { type: 'clarify', text, options };
  return null;
}
function profileNote(p) {
  const names = { kind: '사업', stage: '단계', region: '지역', facility: '시설', capacity: '처리·저장능력', near: '주변 건물', zone: '용도지역' };
  const ks = Object.keys(p);
  if (!ks.length) return '';
  let note = `

[사용자 사업 정보] ${ks.map(k => `${names[k]}: ${p[k]}`).join(' · ')}
답을 이 사업에 맞춥니다. 질문과 상관없는 정보는 언급하지 않습니다.`;
  if (p.region) note += `
허가·신고 관청을 물으면 '${p.region}'의 시장·군수·구청장으로 안내합니다. 입지·건축처럼 지자체 조례로 정하는 사항은 '${p.region} 조례 확인 필요'라고 덧붙입니다.`;
  return note;
}
function sandboxNote(q, info) {
  if (!SANDBOX_RE.test(q)) return '';
  const kind = info.kind || (q.includes('임시허가') ? '임시허가' : '실증특례');
  const [form, art, plan, loss] = DATA.sandbox_docs[kind] || DATA.sandbox_docs['실증특례'];
  const attach = ['사업실시계획서(아래 1장)', '산업융합 신제품·서비스에 해당함을 설명하는 자료',
    '현행 법령으로 안 되는 사유(기준 없음·맞지 않음·불합리) 설명 자료', '혁신성 및 이용자 편익 증진 설명자료',
    ...(kind === '실증특례' ? ['향후 시장 성장 가능성 자료'] : []), ...loss, '생명·건강·안전·환경·개인정보 저해 여부 자료'];
  let note = `

[신청서 초안] 사용자는 산업융합 규제샌드박스 ${kind} 신청을 준비합니다. 공식 제출 서류(${art}) 순서 그대로 초안을 씁니다. 칸을 더하거나 빼지 않습니다.
`
    + `첫 줄: 제출처 산업통상부장관, 신청서 ${form}.
`
    + '1장 사업실시계획서 — ' + plan.map((t, i) => `(${i + 1}) ${t}`).join(' / ') + '\n'
    + '2장 첨부 서류 목록 — ' + attach.map((t, i) => `${i + 1}. ${t}`).join(' / ') + '\n'
    + "채우는 법: '관련 법령' 칸은 근거의 조문으로 법령명·조문·막히는 이유를 쓰고 근거 번호를 답니다. 안전 관련 칸은 근거의 KGS Code 를 듭니다. 기간·규모·장소·시장성·보험처럼 사업자만 아는 칸은 '[직접 입력: 무엇을 쓰는 칸인지]'로 남깁니다. 근거에 없는 조문은 지어내지 않습니다. 마지막 줄에 '서식 원본과 세부 고시는 산업통상부·KIAT 규제샌드박스 안내에서 확인'을 적습니다.";
  const names = { name: '명칭', what: '주요 내용', area: '구역', period: '기간', scale: '규모', company: '신청인' };
  const given = Object.entries(info).filter(([k, v]) => k !== 'kind' && v);
  if (given.length) note += '\n[사업자가 답한 값] ' + given.map(([k, v]) => `${names[k] || k}: ${v}`).join(' · ')
    + ". 이 값은 해당 칸(구역·기간·규모는 (4)번 칸)에 글자 그대로 옮겨 쓰고, 답하지 않은 칸만 '[직접 입력: …]'으로 남깁니다. 1장은 3~5쪽 분량의 사업실시계획서 초안으로, 목차마다 2~4문단을 씁니다.";
  return note;
}

async function chat(req, env) {
  const X = chatExtras;
  const body = await req.json().catch(() => ({}));
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const q = String(messages.at(-1)?.text || '').trim().slice(0, 2000);
  const enc = new TextEncoder();
  const { readable, writable } = new TransformStream();
  const w = writable.getWriter();
  const ev = o => w.write(enc.encode(JSON.stringify(o) + '\n'));
  const done = extra => ev({ type: 'done', ...extra });
  const country = ['한국', '일본'].includes(body.country) ? body.country : null;
  const facility = typeof body.facility === 'string' && body.facility ? body.facility.slice(0, 10) : null;
  const asOf = /^\d{4}-\d{2}-\d{2}$/.test(String(body.as_of || '').trim()) ? String(body.as_of).trim() : null;

  (async () => {
    try {
      // 채점용(cf/eval_cf.py): 모델을 부르지 않고 첫 검색 결과만 돌려준다. 읽기만 한다.
      if (body.debug === 'search') {
        const hits = await search(env, q, 12, { country, facility, as_of: asOf, bare: true });
        ev({ type: 'debug', hits: hits.map(h => ({ law: h.law, article: h.article, score: h.score })) });
        return done();
      }
      if (!q) { ev({ type: 'text', t: '질문이 비었습니다' }); return done(); }
      const checklist = !!body.checklist || X.CHECKLIST_RE.test(q);
      const prevMsgs = messages.slice(0, -1);
      const firstTurn = !prevMsgs.some(m => m.role === 'user');
      const prev = prevMsgs.filter(m => m.role === 'user').map(m => String(m.text || ''));
      let query = prev.length && q.length < 15 ? prev.at(-1) + ' ' + q : q;

      // 인사·잡담·자기소개는 법령을 뒤지지 않는다.
      if (X.SMALLTALK.test(q) && q.length <= 12) {
        ev({ type: 'sources', sources: [] });
        ev({ type: 'text', t: '안녕하세요! 수소시설 인허가에 대해 물어봐 주세요.\n예) 수소충전소 안전거리는? · 제조허가는 누구에게 받아? · 규제특례 종류는?' });
        return done();
      }
      if (X.META.test(q) && q.length <= 30) {
        ev({ type: 'sources', sources: [] });
        ev({ type: 'text', t: DATA.chat.intro });
        ev({ type: 'followups', items: ['수소충전소를 세우려면 어떤 허가가 필요해?', '수소충전소는 제1종보호시설에서 몇 미터 떨어져야 해?', '규제특례에는 어떤 종류가 있어?'] });
        return done();
      }
      // 허가·신고·검사 신청서 채우기: 서식 목록을 보내고, 앞선 대화에서 시설을 짐작한다.
      if (PERMIT_RE.test(q) && !SANDBOX_RE.test(q)) {
        ev({ type: 'sources', sources: [] });
        const past = messages.slice(-7, -1).filter(m => m.role === 'user').map(m => m.text || '').join(' ');
        ev({ type: 'permit', forms: DATA.permit, guess: guessForm(q) || guessForm(past) });
        return done({ kind: 'permit' });
      }
      // 조건에 따라 답이 갈리면 답하기 전에 버튼·칸으로 묻는다.
      const profile = cleanObj(body.profile, PROFILE_KEYS);
      if (!body.no_ask) {
        const steps = askFor(q, profile);
        if (steps) { ev({ type: 'sources', sources: [] }); ev({ type: 'ask', q, steps }); return done({ kind: 'ask' }); }
      }
      const kw = DATA.kind_words[profile.kind];
      if (kw && !query.includes(kw)) query += ' ' + kw;
      const regs = X.regCasesFor(q);
      if (regs.length) ev({ type: 'regs', items: regs });

      // 캐시: 같은 첫 질문은 저장해 둔 답을 그대로(모델 호출 없음). 사업 정보·신청서 초안은 쓰지 않는다.
      const ckey = firstTurn && !Object.keys(profile).length && !SANDBOX_RE.test(q)
        ? await X.cacheKey(q, country, facility, asOf, checklist) : null;
      const hit = ckey && !body.nocache ? await X.cacheGet(env, ckey) : null;
      if (hit) {
        ev({ type: 'sources', sources: hit.sources });
        if (hit.lowconf) ev({ type: 'lowconf' });
        ev({ type: 'text', t: hit.body });
        ev({ type: 'cited', refs: hit.cited });
        ev({ type: 'followups', items: hit.followups });
        ev({ type: 'verify', warnings: hit.warnings, nums: hit.nums || [], refs: hit.refs || [] });
        return done({ model: hit.model, cached: true, cached_at: hit.t });
      }

      const key = env.GEMINI_API_KEY;
      // 검색어 재작성은 첫 검색과 동시에 걸어 두고, 원문 검색이 약할 때만 쓴다.
      const longQ = query.length > DATA.chat.long_q;
      const rw = key ? X.rewriteQuery(query, key) : null;
      const opts = { country, facility, as_of: asOf };
      let hits = await search(env, query, 12, opts);
      const top = () => (hits.length ? hits[0].score : 0);
      if (rw && (longQ || top() < 55)) {
        const better = await Promise.race([rw, new Promise(r => setTimeout(() => r(query), 8000))]);
        if (better !== query) {
          const hits2 = await search(env, better, 12, opts);
          if (hits2.length && (longQ || hits2[0].score > top())) hits = hits2;
        }
      }
      if (checklist && hits.length) {
        const have = new Set(hits.map(h => h.law + '|' + h.article));
        hits = hits.concat((await X.searchForms(env, query, 4)).filter(f => !have.has(f.law + '|' + f.article)));
      }
      const fixed = X.factsMatch(q);
      if (fixed.length) hits = fixed.concat(hits);
      const shown = X.groupSources(hits);
      ev({ type: 'sources', sources: shown });
      const cl = clarifyFor(q);
      if (cl) ev(cl);

      // 발표 잠금: 사람이 확인한 답이 있으면 그것만.
      const demo = firstTurn ? X.demoLookup(env, q) : null;
      if (demo) {
        ev({ type: 'text', t: demo.body });
        ev({ type: 'cited', refs: demo.cited || [] });
        ev({ type: 'followups', items: demo.followups || [] });
        ev({ type: 'verify', warnings: [], nums: [], refs: [] });
        return done({ model: demo.model, cached: true, approved: true });
      }
      if (!key) { ev({ type: 'text', t: 'API 키가 없습니다. 폴더에 key.txt 를 만들고 키를 넣어주세요.' }); return done(); }
      if (!hits.length) { ev({ type: 'text', t: '관련 조문을 찾지 못했습니다. 다른 용어로 물어봐 주세요.' }); return done(); }

      const weak = top() < 40 && !(X.CHANGE.test(q) && hits.slice(0, 4).some(h => h.future));
      let note = weak ? "\n\n[주의] 검색 점수가 낮습니다. 질문 주제의 법령이 자료에 없을 가능성이 큽니다. 비슷해 보이는 다른 조문으로 대체하지 말고, '이 주제의 법령은 현재 자료에 없습니다'라고 먼저 밝힌 뒤 무엇이 필요한지만 짧게 안내하세요." : '';
      if (asOf) note += `\n\n[기준일 ${asOf}] 이 날짜에 시행 중인 조문으로 답합니다. '개정판'이라 표시된 조문이 현행이고, '시행 예정'은 아직 효력이 없으니 '○○부터 시행 예정'이라고 구분해 적습니다.`;
      if (X.CHANGE.test(q)) note += "\n\n[개정 비교] '현행판(비교용)'과 '시행 예정' 조문이 짝으로 들어 있습니다. 무엇이 어떻게 달라지는지 전·후를 나란히 적고, 시행일을 밝힙니다.";
      for (const [umbrella, subs] of Object.entries(X.BUNDLES)) {
        if (!q.includes(umbrella)) continue;
        const present = subs.filter(s => hits.some(h => (h.title + h.content.slice(0, 300)).replace(/ /g, '').includes(s.replace(/ /g, ''))));
        if (present.length >= 2) note += `\n\n[갈래 확인] '${umbrella}'는 자료에 ${present.length}갈래가 있습니다: ${present.join(' · ')}. 종류를 물었으면 이 갈래를 모두 다룹니다.`;
        break;
      }
      const sb = cleanObj(body.sandbox, SB_KEYS, 120);
      note += profileNote(profile) + sandboxNote(q, sb);
      const userFacts = q + ' ' + Object.values(sb).join(' ');
      const context = X.buildContext(hits, shown) + note;
      const contents = prevMsgs.slice(-8).map(m => ({ role: m.role === 'user' ? 'user' : 'model', parts: [{ text: String(m.text || '').slice(0, 4000) }] }));
      contents.push({ role: 'user', parts: [{ text: `=== 검색된 법령 조문 ===\n${context}\n\n=== 질문 ===\n${q}` }] });
      if (weak) ev({ type: 'lowconf' });
      const system = DATA.system + (checklist ? DATA.chat.checklist_system : '');
      const useJudge = body.mode === 'demo';
      const models = (DATA.chat.model_sets[body.mode] || DATA.models).filter(m => !X.isExhausted(m));
      let last = null;
      for (const model of models) {
        let buf = '', sent = 0;
        try {
          for await (const t of X.streamModel(model, contents, key, system)) {
            buf += t;
            const cut = X.splitFollowups(buf)[1];
            const stop = cut >= 0 ? cut : Math.max(0, buf.length - 12);
            if (stop > sent) { ev({ type: 'text', t: buf.slice(sent, stop) }); sent = stop; }
          }
        } catch (e) {
          last = e.message;
          if (!buf) continue;            // 첫 글자 전에 실패하면 다음 모델
        }
        if (!buf) { last = `${model} 빈 응답`; continue; }
        let [bodyText, cut] = X.splitFollowups(buf);
        if (cut < 0 && buf.length > sent) ev({ type: 'text', t: buf.slice(sent) });
        if (bodyText.trim().length < 40) {
          last = `${model} 응답이 ${bodyText.trim().length}자에서 끊김`;
          ev({ type: 'text', t: '\n\n…(답변이 끊겨 다시 시도합니다)\n\n' });
          continue;
        }
        const body0 = bodyText;
        let text = buf, follow = X.parseFollowups(text);
        ev({ type: 'phase', p: 'check' });
        const sib = await X.siblings(env, hits);
        let v = X.verify(text, hits, userFacts, sib), removed = [];
        let bad = v.nums.concat(v.refs);
        if (bad.length) {
          const fixedText = await X.correctAnswer(model, text, context, bad, key);
          if (fixedText) {
            const v2 = X.verify(fixedText, hits, userFacts, sib);
            if (v2.nums.length + v2.refs.length < bad.length) {
              text = fixedText; v = v2;
              bodyText = X.splitFollowups(text)[0];
              const f2 = X.parseFollowups(text);
              if (f2.length) follow = f2;
            }
          }
        }
        bad = v.nums.concat(v.refs);
        if (bad.length) {
          [bodyText, removed] = X.stripUnverified(bodyText, bad);
          v = X.verify(bodyText, hits, userFacts, sib);
        }
        if (bodyText !== body0) ev({ type: 'replace', t: bodyText });
        const cited = X.citedRefs(bodyText, shown);
        ev({ type: 'cited', refs: cited });
        ev({ type: 'followups', items: follow });
        const warns = v.warnings.concat(removed.length ? [`근거 확인이 안 되어 뺀 내용 ${removed.length}곳`] : []);
        ev({ type: 'verify', warnings: warns, nums: v.nums, refs: v.refs, removed });
        const uncited = X.uncitedSentences(bodyText);
        if (uncited.length) ev({ type: 'uncited', items: uncited });
        let judged = null;
        if (useJudge) {
          judged = await X.judgeAnswer(bodyText, context, key, model);
          if (judged !== null) ev({ type: 'judge', bad: judged });
        }
        if (ckey && !warns.length && !weak && !(judged && judged.length)) {
          const t = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 16).replace('T', ' ');
          await X.cachePut(env, ckey, { t, model, q, sources: shown, body: bodyText, cited, followups: follow,
            warnings: [], nums: v.nums, refs: v.refs, lowconf: weak });
        }
        return done({ model, kind: 'gemini' });
      }
      ev({ type: 'text', t: `지금 구글 서버가 붐벼서 답변을 받지 못했습니다. 아래 근거 조문은 정상이니 잠시 뒤 다시 물어봐 주세요.\n(마지막 오류: ${last || '시도할 모델이 없음'})` });
      done();
    } catch (e) {
      ev({ type: 'text', t: '⚠️ ' + (e.message || e) });
      done();
    } finally {
      w.close();
    }
  })();
  return new Response(readable, { headers: { 'Content-Type': 'application/x-ndjson; charset=utf-8', 'Cache-Control': 'no-cache' } });
}


const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });

// D1 무료 한도(하루 읽기 500만 행)가 바닥나면 오라클 서버(hydrogen-bot 통로)로 넘긴다.
// 확인 결과는 이 인스턴스에서 1분 기억한다(요청마다 묻지 않게).
const D1_PATHS = /^\/api\/(chat|review\/|share|feedback|byl)/;
let d1State = { ok: true, at: 0 };
async function d1Down(env) {
  if (Date.now() - d1State.at < 60000) return !d1State.ok;
  try { await env.DB.prepare('SELECT id FROM docs LIMIT 1').all(); d1State = { ok: true, at: Date.now() }; }
  catch (e) { d1State = { ok: !/limit|exceeded/i.test(String(e && e.message)), at: Date.now() }; }
  return !d1State.ok;
}
function toBackup(req, env, url) {
  const t = new URL('https://hydrogen-bot.tmdfoqhdl030.workers.dev');
  t.pathname = url.pathname; t.search = url.search;
  return (env.BACKUP ? env.BACKUP.fetch.bind(env.BACKUP) : fetch)(new Request(t.toString(), req));
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    if (D1_PATHS.test(p) && await d1Down(env)) {
      try { return await toBackup(req, env, url); } catch (e) { /* 오라클도 안 되면 아래로 그대로 */ }
    }
    if (p === '/api/status') {
      return json({ articles: DATA.articles, korea: DATA.korea, japan: DATA.articles - DATA.korea,
        has_key: !!env.GEMINI_API_KEY, model: DATA.models[0], mode: 'daily', need_code: false,
        semantic: false, rerank: false, cache: 0, ollama: false, pdf: false, host: 'cloudflare' });
    }
    if (p === '/api/chat' && req.method === 'POST') {
      // 검색 중 D1 한도에 걸리면 첫 이벤트에 오류가 실려 온다. 그 경우만 오라클로 다시 묻고, 아니면 그대로 흘려보낸다.
      const copy = req.clone();
      const r = await chat(req, env);
      const rd = r.body.getReader(), dec = new TextDecoder(), head = [];
      let txt = '';
      while (!/"type":\s*"(sources|text|ask|permit|debug|done)"/.test(txt)) {
        const { value, done } = await rd.read();
        if (done) break;
        head.push(value); txt += dec.decode(value, { stream: true });
      }
      if (/D1_ERROR|row read limit/i.test(txt)) {
        d1State = { ok: false, at: Date.now() };
        try { return await toBackup(copy, env, url); } catch (e) { /* 오라클도 안 되면 원래 답(오류)을 낸다 */ }
      }
      const body = new ReadableStream({
        start(c) { head.forEach(v => c.enqueue(v)); },
        async pull(c) { const { value, done } = await rd.read(); done ? c.close() : c.enqueue(value); },
      });
      return new Response(body, { status: r.status, headers: r.headers });
    }
    if (p === '/api/permit/forms') return json(DATA.permit);
    for (const h of [handleReview, handleMisc, handleDocs]) {
      const r = await h(req, env, url);
      if (r) return r;
    }
    if (p.startsWith('/api/')) return json({ error: '클라우드플레어판에서는 아직 준비 중인 기능입니다.' }, 501);
    return env.ASSETS.fetch(req);
  },
};
