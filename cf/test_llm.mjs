// llm.js 변환 점검(네트워크 없이). node cf/test_llm.mjs
import { setLlm, llmFetch } from './src/llm.js';
let sent = null, bad = 0;
const ok = (c, m) => { if (!c) { bad++; console.log('✗', m); } };
globalThis.fetch = async (url, init) => {
  sent = { url, body: JSON.parse(init.body), auth: init.headers?.Authorization };
  if (sent.body.stream) {
    const chunks = ['data: {"choices":[{"delta":{"content":"안녕"}}]}\n\n', 'data: {"choices":[{"delta":{"content":"하세요"},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n'];
    return new Response(new ReadableStream({ start(c) { chunks.forEach(x => c.enqueue(new TextEncoder().encode(x))); c.close(); } }), { status: 200 });
  }
  if (sent.body.messages?.[0]?.content === 'fail') return new Response('{"error":{"message":"bad key"}}', { status: 401 });
  return new Response(JSON.stringify({ choices: [{ message: { content: '{"a":1}' }, finish_reason: 'stop' }] }), { status: 200 });
};
const G = 'https://generativelanguage.googleapis.com/v1beta/models';
setLlm({});                                   // 키 없음 → Gemini 그대로
await llmFetch(`${G}/m:generateContent?key=x`, { method: 'POST', body: '{"contents":[]}' });
ok(sent.url.startsWith(G), 'no key keeps gemini');
setLlm({ OPENAI_API_KEY: 'sk-test', OPENAI_SCOPE: 'all' });
let r = await llmFetch(`${G}/gemini-x:generateContent?key=openai`, { method: 'POST', body: JSON.stringify({
  contents: [{ parts: [{ text: 'hi' }, { inline_data: { mime_type: 'application/pdf', data: 'QUJD' } }, { inline_data: { mime_type: 'image/png', data: 'UE5H' } }] }],
  generationConfig: { temperature: 0, maxOutputTokens: 300, responseMimeType: 'application/json' } }) });
let d = await r.json();
ok(sent.url === 'https://api.openai.com/v1/chat/completions' && sent.auth === 'Bearer sk-test', 'endpoint/auth');
ok(sent.body.model === 'gpt-6-luna' && sent.body.max_completion_tokens === 300 && !('temperature' in sent.body), 'body ' + JSON.stringify(sent.body).slice(0, 200));
const c = sent.body.messages[0].content;
ok(c[1].type === 'file' && c[1].file.file_data === 'data:application/pdf;base64,QUJD' && c[2].image_url.url === 'data:image/png;base64,UE5H', 'parts');
ok(d.candidates[0].content.parts[0].text === '{"a":1}', 'non-stream back');
r = await llmFetch(`${G}/m:streamGenerateContent?alt=sse&key=openai`, { method: 'POST', body: JSON.stringify({ systemInstruction: { parts: [{ text: 'SYS' }] },
  contents: [{ role: 'user', parts: [{ text: 'q' }] }, { role: 'model', parts: [{ text: 'a' }] }] }) });
ok(sent.body.messages[0].role === 'system' && sent.body.messages[2].role === 'assistant' && sent.body.stream, 'stream body');
const txt = await r.text();
const parts = txt.split('\n').filter(l => l.startsWith('data:')).map(l => JSON.parse(l.slice(5)).candidates[0]);
ok(parts.map(p => p.content.parts[0].text).join('') === '안녕하세요' && parts.at(-1).finishReason === 'MAX_TOKENS', 'stream back ' + txt);
r = await llmFetch(`${G}/m:generateContent`, { method: 'POST', body: JSON.stringify({ contents: [{ parts: [{ text: 'fail' }] }] }) });
ok(r.status === 401 && (await r.text()).includes('"message":"OpenAI: bad key"'), 'error');

// Claude: 요청 모양(system·assistant·effort·fallback)과 스트리밍 되돌리기, 토큰 기록
import { resetUsage, usageList, llmName } from './src/llm.js';
let csent = null;
globalThis.fetch = async (url, init) => {
  csent = { url: String(url), body: JSON.parse(init.body), headers: init.headers };
  const evs = [
    ['message_start', { type: 'message_start', message: { id: 'm1', type: 'message', role: 'assistant', model: 'claude-opus-5-5', content: [], stop_reason: null, usage: { input_tokens: 120, output_tokens: 1 } } }],
    ['content_block_start', { type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } }],
    ['content_block_delta', { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: '수소' } }],
    ['content_block_delta', { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: '법' } }],
    ['content_block_stop', { type: 'content_block_stop', index: 0 }],
    ['message_delta', { type: 'message_delta', delta: { stop_reason: 'end_turn' }, usage: { output_tokens: 7 } }],
    ['message_stop', { type: 'message_stop' }],
  ].map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('');
  return new Response(evs, { status: 200, headers: { 'content-type': 'text/event-stream' } });
};
setLlm({ LLM: 'claude', ANTHROPIC_API_KEY: 'sk-ant-test', GEMINI_API_KEY: 'g' });
ok(llmName() === 'claude:claude-opus-5-5', 'claude name');
resetUsage();
r = await llmFetch(`${G}/gemini-x:streamGenerateContent?alt=sse&key=g`, { method: 'POST', body: JSON.stringify({
  systemInstruction: { parts: [{ text: 'SYS' }] }, generationConfig: { maxOutputTokens: 100 },
  contents: [{ role: 'user', parts: [{ text: 'a' }] }, { role: 'model', parts: [{ text: 'b' }] }, { role: 'user', parts: [{ text: 'c' }] }] }) });
const ctxt = await r.text();
const cparts = ctxt.split('\n').filter(l => l.startsWith('data:')).map(l => JSON.parse(l.slice(5)).candidates[0]);
ok(csent.url.includes('api.anthropic.com') && csent.body.system === 'SYS' && csent.body.messages[1].role === 'assistant'
   && csent.body.output_config.effort === 'low' && csent.body.fallbacks === 'default', 'claude body ' + JSON.stringify(csent.body).slice(0, 300));
ok(cparts.map(p => p.content.parts[0].text).join('') === '수소법' && cparts.at(-1).finishReason === 'STOP', 'claude stream back ' + ctxt.slice(0, 200));
const u = usageList();
ok(u.length === 1 && u[0].in === 120 && u[0].out === 7, 'claude usage ' + JSON.stringify(u));
console.log(bad ? `실패 ${bad}` : 'llm.js 변환 점검 통과'); process.exit(bad ? 1 : 0);
