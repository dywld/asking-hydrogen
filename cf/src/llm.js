// AI 공급자 바꾸기. 기존 코드는 Gemini 모양 요청을 만들고, 여기서 공급자에 맞게 바꿔 부른 뒤 답을 Gemini 모양으로 되돌려 준다.
// 그래서 부르는 곳(채팅·스트리밍·서류 검토·온보딩)은 fetch 만 llmFetch 로 바꿨다.
//   공급자: wrangler.toml [vars] LLM = "openai" | "claude" | "gemini"
//           비워 두면 OPENAI_API_KEY 가 있으면 openai, 없으면 gemini (예전 동작 그대로)
//   OpenAI : 비밀값 OPENAI_API_KEY, 모델 OPENAI_MODEL(기본 gpt-6-luna), 생각 깊이 OPENAI_EFFORT(기본 none)
//   Claude : 비밀값 ANTHROPIC_API_KEY, 모델 CLAUDE_MODEL(기본 claude-opus-5-5), 생각 깊이 CLAUDE_EFFORT(기본 low)
//   키는 사람이 직접 넣는다:  npx wrangler secret put ANTHROPIC_API_KEY   (내 PC 서버는 cf/.dev.vars)
// OpenAI 형식 근거: developers.openai.com/api/reference (chat/completions)
// Claude 형식 근거: 공식 SDK @anthropic-ai/sdk (messages.stream / messages.create, usage.input_tokens·output_tokens)
// 토큰 기록: 요청마다 resetUsage() 로 비우고, 부른 모델별 입력·출력 토큰을 usageList() 로 꺼낸다(채점에서 비용 계산용).
import Anthropic from '@anthropic-ai/sdk';

const OPENAI = 'https://api.openai.com/v1/chat/completions';
let cfg = null;                                  // { provider, key, model, effort, all } 요청마다 setLlm(env) 로 정한다
let used = [];                                   // [{ model, in, out, cached }]

export function resetUsage() { used = []; }
export const usageList = () => used.slice();
const note = (model, i, o, c = 0) => { used.push({ model, in: i || 0, out: o || 0, cached: c || 0 }); };

export function setLlm(env) {
  const want = env.LLM || (env.OPENAI_API_KEY ? 'openai' : 'gemini');
  // OPENAI_SCOPE: 'answer'(기본) = 사용자가 보는 답(스트리밍)만 바꾼 공급자, 질문 다듬기·검증·서류 읽기는 Gemini(무료·빠름).
  //               'all' = 전부 바꾼 공급자. Gemini 키가 없으면 늘 전부.
  const all = env.OPENAI_SCOPE === 'all' || !env.GEMINI_API_KEY;
  if (want === 'claude' && env.ANTHROPIC_API_KEY)
    cfg = { provider: 'claude', key: env.ANTHROPIC_API_KEY, model: env.CLAUDE_MODEL || 'claude-opus-5-5', effort: env.CLAUDE_EFFORT || 'low', all };
  else if (want === 'openai' && env.OPENAI_API_KEY)
    cfg = { provider: 'openai', key: env.OPENAI_API_KEY, model: env.OPENAI_MODEL || 'gpt-6-luna', effort: env.OPENAI_EFFORT || 'none', all };
  else cfg = null;
}
export const llmProvider = () => (cfg ? cfg.provider : 'gemini');
export const llmName = () => (cfg ? `${cfg.provider}:${cfg.model}` : 'gemini');
// 답에 붙일 모델 이름. 'oa:모델' 로 부른 경우 그 OpenAI 모델
export const llmLabel = model => (!cfg ? model : String(model).startsWith('oa:') ? `openai:${String(model).slice(3)}` : llmName());
export const llmAll = () => !!(cfg && cfg.all);   // 서류 읽기까지 바꾼 공급자인가

// Gemini 요청 → OpenAI messages
function toMessages(g) {
  const msgs = [];
  const sys = (g.systemInstruction?.parts || []).map(p => p.text || '').join('');
  if (sys) msgs.push({ role: 'system', content: sys });
  for (const c of g.contents || []) {
    const parts = [];
    for (const p of c.parts || []) {
      if (typeof p.text === 'string') parts.push({ type: 'text', text: p.text });
      const d = p.inline_data || p.inlineData;
      if (d) {
        const mime = d.mime_type || d.mimeType, url = `data:${mime};base64,${d.data}`;
        if (mime === 'application/pdf') parts.push({ type: 'file', file: { filename: 'document.pdf', file_data: url } });
        else parts.push({ type: 'image_url', image_url: { url } });
      }
    }
    const role = c.role === 'model' ? 'assistant' : 'user';
    // 글만 있으면 문자열로(assistant 는 문자열만 받는다)
    const content = parts.every(x => x.type === 'text') ? parts.map(x => x.text).join('\n') : parts;
    msgs.push({ role, content });
  }
  return msgs;
}

function toBody(g, stream, c = cfg) {
  const gc = g.generationConfig || {};
  const b = { model: c.model, messages: toMessages(g) };
  // 생각하는 모델은 temperature 를 못 바꾸는 경우가 있어 보내지 않는다. 생각 토큰도 한도에 들어가 넉넉히 둔다.
  if (c.effort) b.reasoning_effort = c.effort;
  if (gc.maxOutputTokens) b.max_completion_tokens = c.effort === 'none' ? gc.maxOutputTokens : gc.maxOutputTokens + 4096;
  // response_format(json_object)은 넣지 않는다: 배열 [..] 로 답하라는 프롬프트(review.js)가 있고, 프롬프트마다 'JSON 만 출력'이 이미 있다.
  if (stream) { b.stream = true; b.stream_options = { include_usage: true }; }
  return JSON.stringify(b);
}

// Gemini 요청 → Claude Messages 요청. 같은 역할이 이어지면 API 가 한 차례로 합쳐 준다.
function toClaude(g, c) {
  const gc = g.generationConfig || {};
  const system = (g.systemInstruction?.parts || []).map(p => p.text || '').join('');
  const messages = [];
  for (const m of g.contents || []) {
    const content = [];
    for (const p of m.parts || []) {
      const d = p.inline_data || p.inlineData;
      if (d) {
        const mime = d.mime_type || d.mimeType;
        if (mime === 'application/pdf') content.push({ type: 'document', source: { type: 'base64', media_type: mime, data: d.data } });
        else content.push({ type: 'image', source: { type: 'base64', media_type: mime, data: d.data } });
      }
      if (typeof p.text === 'string' && p.text) content.push({ type: 'text', text: p.text });
    }
    if (content.length) messages.push({ role: m.role === 'model' ? 'assistant' : 'user', content });
  }
  // claude-opus-5-5 는 생각을 끌 수 없다(adaptive). 깊이는 effort 로만 낮춘다. 생각 토큰도 max_tokens 에 들어가 넉넉히 둔다.
  const b = { model: c.model, max_tokens: (gc.maxOutputTokens || 8192) + 8192, messages, output_config: { effort: c.effort } };
  if (system) b.system = system;
  // 안전 분류기가 거절하면 서버가 다른 Claude 모델로 이어서 답한다(server-side fallback, 거절 종류에 맞춰 자동 선택).
  b.betas = ['server-side-fallback-2026-07-01'];
  b.fallbacks = 'default';
  return b;
}

const geminiJson = (text, finish) => ({ candidates: [{ content: { role: 'model', parts: [{ text }] }, finishReason: finish }] });
const FINISH = { length: 'MAX_TOKENS', stop: 'STOP', content_filter: 'SAFETY' };
const CFINISH = { max_tokens: 'MAX_TOKENS', end_turn: 'STOP', stop_sequence: 'STOP', refusal: 'SAFETY' };
const sse = (enc, text, finish) => enc.encode(`data: ${JSON.stringify(geminiJson(text, finish))}\n\n`);

// 오류 답은 Gemini 처럼 "message" 를 담아 돌려준다(부르는 곳이 그 문구를 잘라 보여 준다).
async function errorResponse(r) {
  const t = await r.text().catch(() => '');
  let msg = '';
  try { msg = JSON.parse(t).error?.message || ''; } catch (e) { msg = t.slice(0, 100); }
  return new Response(JSON.stringify({ error: { code: r.status, message: `OpenAI: ${msg}`.slice(0, 200) } }),
    { status: r.status, headers: { 'Content-Type': 'application/json' } });
}
const claudeError = e => new Response(JSON.stringify({ error: { code: e.status || 500, message: `Claude: ${e.message || e}`.slice(0, 200) } }),
  { status: e.status || 500, headers: { 'Content-Type': 'application/json' } });

// Gemini 를 그대로 부를 때도 토큰을 적는다(usageMetadata). 스트리밍은 마지막 조각의 합계를 쓴다.
async function geminiFetch(url, init) {
  const r = await fetch(url, init);
  if (!r.ok) return r;
  const model = (String(url).match(/\/models\/([^:]+):/) || [])[1] || 'gemini';
  const um = u => u && note(model, u.promptTokenCount, (u.candidatesTokenCount || 0) + (u.thoughtsTokenCount || 0), u.cachedContentTokenCount);
  if (!String(url).includes(':streamGenerateContent')) {
    r.clone().json().then(d => um(d.usageMetadata)).catch(() => {});
    return r;
  }
  const [a, b] = r.body.tee();
  (async () => {
    const rd = b.getReader(), dec = new TextDecoder();
    let buf = '', last = null;
    for (;;) {
      const { done, value } = await rd.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (line.startsWith('data:')) { try { last = JSON.parse(line.slice(5)).usageMetadata || last; } catch (e) { /* 덜 온 조각 */ } }
      }
    }
    um(last);
  })().catch(() => {});
  return new Response(a, { status: r.status, headers: r.headers });
}

async function claudeFetch(g, stream, init) {
  const client = new Anthropic({ apiKey: cfg.key, maxRetries: 1 });
  const body = toClaude(g, cfg);
  if (!stream) {
    try {
      const m = await client.beta.messages.create(body, { signal: init.signal });
      note(cfg.model, m.usage?.input_tokens, m.usage?.output_tokens, m.usage?.cache_read_input_tokens);
      const text = m.content.filter(b => b.type === 'text').map(b => b.text).join('');
      return new Response(JSON.stringify(geminiJson(text, CFINISH[m.stop_reason] || 'STOP')),
        { status: 200, headers: { 'Content-Type': 'application/json' } });
    } catch (e) { return claudeError(e); }
  }
  // 스트리밍: 첫 이벤트가 올 때까지 기다려 연결 오류는 오류 응답으로 돌려준다(부르는 곳이 다음 모델로 넘어간다).
  const s = client.beta.messages.stream(body, { signal: init.signal });
  const it = s[Symbol.asyncIterator]();
  let first;
  try { first = await it.next(); } catch (e) { return claudeError(e); }
  const enc = new TextEncoder();
  const rs = new ReadableStream({
    async start(ctl) {
      try {
        for (let r = first; !r.done; r = await it.next()) {
          const ev = r.value;
          if (ev.type === 'content_block_delta' && ev.delta.type === 'text_delta' && ev.delta.text) ctl.enqueue(sse(enc, ev.delta.text));
        }
        const m = await s.finalMessage();
        note(cfg.model, m.usage?.input_tokens, m.usage?.output_tokens, m.usage?.cache_read_input_tokens);
        ctl.enqueue(sse(enc, '', CFINISH[m.stop_reason] || 'STOP'));
      } catch (e) { /* 중간에 끊기면 받은 데까지만 */ }
      ctl.close();
    },
  });
  return new Response(rs, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

export async function llmFetch(url, init = {}) {
  const isGemini = String(url).includes('generativelanguage.googleapis.com');
  if (!isGemini) return fetch(url, init);
  const stream = String(url).includes(':streamGenerateContent');
  // 부르는 곳이 모델 이름을 'oa:모델' 로 주면 그 OpenAI 모델을 쓴다(간단한 질문은 빠른 모델로). 생각 없이 바로 답한다.
  const pick = String(url).match(/\/models\/oa:([A-Za-z0-9._-]+)/);
  if (!cfg || (!stream && !cfg.all) || (pick && cfg.provider !== 'openai')) return geminiFetch(url, init);   // 곁가지 호출은 Gemini 로
  let g;
  try { g = JSON.parse(init.body || '{}'); } catch (e) { return geminiFetch(url, init); }
  if (cfg.provider === 'claude') return claudeFetch(g, stream, init);
  const use = pick ? { ...cfg, model: pick[1], effort: 'none' } : cfg;
  const r = await fetch(OPENAI, {
    method: 'POST', signal: init.signal,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${cfg.key}` },
    body: toBody(g, stream, use),
  });
  if (!r.ok) return errorResponse(r);
  const ou = u => u && note(use.model, u.prompt_tokens, u.completion_tokens, u.prompt_tokens_details?.cached_tokens);
  if (!stream) {
    const d = await r.json();
    const ch = d.choices?.[0] || {};
    if (d.usage) { console.log('llm usage', use.model, JSON.stringify(d.usage)); ou(d.usage); }
    return new Response(JSON.stringify(geminiJson(ch.message?.content || '', FINISH[ch.finish_reason] || 'STOP')),
      { status: 200, headers: { 'Content-Type': 'application/json' } });
  }
  // 스트리밍: OpenAI 조각(data: {choices:[{delta:{content}}]}) → Gemini 조각(data: {candidates:[...]})
  const enc = new TextEncoder(), dec = new TextDecoder();
  let buf = '';
  const ts = new TransformStream({
    transform(chunk, ctl) {
      buf += dec.decode(chunk, { stream: true });
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (!line.startsWith('data:')) continue;
        const data = line.slice(5).trim();
        if (data === '[DONE]') continue;
        try {
          const j = JSON.parse(data);
          if (j.usage) { console.log('llm usage', use.model, 'stream', JSON.stringify(j.usage)); ou(j.usage); }
          const ch = j.choices?.[0];
          if (!ch) continue;
          const text = ch.delta?.content || '';
          const finish = ch.finish_reason ? FINISH[ch.finish_reason] || 'STOP' : undefined;
          if (text || finish) ctl.enqueue(sse(enc, text, finish));
        } catch (e) { /* 덜 온 조각 */ }
      }
    },
  });
  return new Response(r.body.pipeThrough(ts), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}
