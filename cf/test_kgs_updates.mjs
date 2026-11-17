import { DatabaseSync } from 'node:sqlite';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { registerHooks } from 'node:module';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';

registerHooks({ load(url, context, nextLoad) {
  if (url.startsWith('file:') && url.endsWith('.json')) {
    return { format: 'module', source: 'export default ' + readFileSync(new URL(url), 'utf8'), shortCircuit: true };
  }
  return nextLoad(url, context);
}});
const { tokenize, search, cacheKey, factsMatch } = await import('./src/chat_extras.js');
const { readKgsState } = await import('./src/kgs_updates.js');
const { default: worker } = await import('./src/index.js');

const db = new DatabaseSync(':memory:');
db.exec(`
  CREATE TABLE docs (id INTEGER PRIMARY KEY, country TEXT, law TEXT, article TEXT, title TEXT, content TEXT,
    future INTEGER, effective_date TEXT, kind TEXT, ref TEXT, link TEXT);
  CREATE VIRTUAL TABLE docs_fts USING fts5(bg, content='', tokenize='unicode61');
  CREATE INDEX docs_law_article ON docs(law, article);
  CREATE TABLE answer_cache (key TEXT PRIMARY KEY, rec TEXT NOT NULL, ts INTEGER);
`);
const add = db.prepare('INSERT INTO docs VALUES (?,?,?,?,?,?,0,?,?,?,?)');
const addFts = db.prepare('INSERT INTO docs_fts(rowid,bg) VALUES (?,?)');
function seed(id, law, article, title, content, kind) {
  add.run(id, '한국', law, article, title, content, '', kind, article, 'https://example.com/');
  addFts.run(id, tokenize(`${law} ${title} ${content}`).join(' '));
}
seed(1, 'KGS FP216', '[KGS FP216 2.1]', '수소충전소 보호시설', '수소충전소 보호시설 가상옛기준 11m', '상세기준');
seed(2, '고압가스 안전관리법', '제1조', '법률 시행', '이 법의 목적과 절차', '');
for (let id = 3; id < 30; id++) seed(id, '다른 법', `제${id}조`, '기타', '이 법의 목적과 운영', '');
const migration = readFileSync(new URL('./migrations/0001_kgs_updates.sql', import.meta.url), 'utf8');
db.exec(migration);
db.exec(migration);

function statement(sql, binds = []) {
  const stmt = db.prepare(sql);
  const input = /\?\d/.test(sql) ? [Object.fromEntries(binds.map((b, i) => [String(i + 1), b]))] : binds;
  return {
    bind: (...b) => statement(sql, b),
    async all() { return { results: stmt.all(...input), meta: { rows_read: 0 } }; },
    async first() { return stmt.get(...input) || null; },
    async run() { return { meta: stmt.run(...input) }; },
  };
}
const DB = {
  prepare: statement,
  async batch(stmts) {
    db.exec('BEGIN');
    try {
      const result = [];
      for (const stmt of stmts) result.push(await stmt.all());
      db.exec('COMMIT');
      return result;
    } catch (e) { db.exec('ROLLBACK'); throw e; }
  },
};
const env = { DB, KGS_PUSH_KEY: 'testing' };
const url = 'https://local.example/api/kgs-updates';
const v1 = '1'.repeat(64), v2 = '2'.repeat(64), future = '3'.repeat(64);
const row = (n, text) => ({ article: `[KGS FP216 2.${n}]`, ref: `[KGS FP216 2.${n}]`,
  title: '수소충전소 보호시설', content: text });
const first = row(1, '수소충전소 보호시설 새로운개정조항 22m');
const second = row(2, '수소충전소 보호시설 새로운개정조항 다른 부분 33m');
async function send(action, fields, key = 'testing') {
  return worker.fetch(new Request(url, { method: 'POST', headers: { 'x-kgs-push-key': key },
    body: JSON.stringify({ action, code: 'FP216', ...fields }) }), env);
}
const stage = (version, total, start, rows, date = '2026-01-01') =>
  send('stage', { version, total, start, rows, effective_date: date, release_hash: '9'.repeat(64) });
const activate = (version, expected_version = null) => send('activate', { version, expected_version });
async function hits(q, options = {}) {
  const KGS = await readKgsState(DB);
  return (await search({ DB, KGS }, q, { top_k: 12, bare: true, ...options })).filter(r => r.law === 'KGS FP216');
}
async function debug(q) {
  const req = new Request('https://local.example/api/chat', { method: 'POST',
    body: JSON.stringify({ debug: 'search', messages: [{ text: q }] }) });
  const events = (await (await worker.fetch(req, env)).text()).trim().split('\n').map(JSON.parse);
  return events.find(e => e.type === 'debug')?.hits;
}
assert.equal((await send('state', {}, 'wrong')).status, 401);
assert.equal((await stage(v1, 2, 0, [first])).status, 200);
assert.equal((await hits('새로운개정조항')).length, 0);
assert.equal((await activate(v1)).status, 409);
assert.equal((await hits('가상옛기준'))[0].id, 1);
assert.equal((await stage(v1, 2, 0, [first])).status, 200);
assert.equal((await stage(v1, 2, 0, [second])).status, 409);
assert.equal((await stage(v1, 2, 1, [second])).status, 200);
const oldKey = await cacheKey('질문', null, null, null, false);
assert.equal((await activate(v1)).status, 200);
assert.equal((await activate(v1)).status, 200);
assert.equal((await hits('가상옛기준')).length, 0);
assert((await hits('새로운개정조항')).some(r => r.content === first.content && r.id < 0));
assert((await debug('새로운개정조항')).some(r => r.law === 'KGS FP216'));
assert.equal((await hits('새로운개정조항', { as_of: '2025-12-31' })).length, 0);
assert.equal((await hits('새로운개정조항', { country: '일본' })).length, 0);
assert.notEqual(await cacheKey('질문', null, null, null, false, await readKgsState(DB)), oldKey);
assert.equal((await stage(future, 1, 0, [second], '2099-01-01')).status, 200);
assert.equal((await activate(future, v1)).status, 409);
assert.equal((await stage(v2, 1, 0, [row(1, '재개정검색어 44m')], '2026-02-01')).status, 200);
assert.equal((await activate(v2, null)).status, 409);
assert.equal((await activate(v2, v1)).status, 200);
assert.equal((await hits('새로운개정조항')).length, 0);
assert((await hits('재개정검색어')).some(r => r.content.includes('44m')));
assert.equal((await send('rollback', { version: v1, expected_version: v2 })).status, 200);
assert.equal((await activate(v2, v1)).status, 409);
assert((await hits('새로운개정조항')).some(r => r.content === first.content));
const status = await (await worker.fetch(new Request(url), env)).json();
assert.equal(status.active[0].version, v1);
assert(!('blocked_version' in status.active[0]));
assert.equal((await send('rollback', { version: null, expected_version: v1 })).status, 200);
assert.equal((await hits('가상옛기준'))[0].id, 1);
assert.equal((await hits('새로운개정조항')).length, 0);
assert((await debug('법률 시행')).some(r => r.law === '고압가스 안전관리법'));
for (const topic of factsMatch('수소충전소 안전거리')) {
  if (topic.law === 'KGS FP216') {
    assert(!factsMatch('수소충전소 안전거리', [{ law: topic.law, version: v1 }]).some(t => t.law === topic.law));
  }
}

// Python이 보관한 자료를 실제 HTTP로 게시하고 Worker 검색에서 확인한다.
const script = `
import os
from pathlib import Path
from kgs_cloud import Cloud, batches, publish, search_rows
from kgs_watch import Watcher, atomic_write, digest, encode_rows, semantic_hash, write_json
root = Path(os.environ['TEST_KGS_ROOT'])
w = Watcher(root)
pdf = b'%PDF test artifact'
sha = digest(pdf)
folder = w.version_dir('GC205', sha)
rows = [{'code':'GC205','item':'2.1','title':'제목','content':'전송연동확인기준 22m',
         'version_sha256':sha,'effective_on':'2026-01-01'}]
assert search_rows('GC205', rows)[0]['article'] == '[KGS GC205 2.1]'
assert [(s, len(r)) for s,r in batches(search_rows('GC205', rows * 50))] == [(0,48),(48,2)]
atomic_write(folder / 'document.pdf', pdf)
write_json(folder / 'metadata.json', {'chunks':1,'semantic_sha256':semantic_hash(rows)})
atomic_write(w.data, encode_rows(rows))
cloud = Cloud(os.environ['TEST_KGS_URL'], 'testing')
report = publish(w, cloud)
assert [r['code'] for r in report['published']] == ['GC205'], report
assert not publish(w, cloud)['published']
`;
const server = createServer(async (req, res) => {
  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const response = await worker.fetch(new Request(url, {
      method: req.method, headers: req.headers, body: Buffer.concat(chunks),
    }), env);
    res.writeHead(response.status, Object.fromEntries(response.headers));
    res.end(await response.text());
  } catch (error) {
    res.writeHead(500);
    res.end(error.message);
  }
});
const root = mkdtempSync(join(tmpdir(), 'kgs-integration-'));
try {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const publisher = spawn('python', ['-c', script], { cwd: new URL('..', import.meta.url),
    env: {...process.env, TEST_KGS_ROOT: root, TEST_KGS_URL: `http://127.0.0.1:${server.address().port}/api/kgs-updates`},
    stdio: ['ignore', 'pipe', 'pipe'] });
  let err = '';
  publisher.stderr.on('data', chunk => { err += chunk; });
  const [code] = await once(publisher, 'close');
  assert.equal(code, 0, err);
  assert((await debug('전송연동확인기준')).some(r => r.law === 'KGS GC205'));
  db.exec('DROP TABLE docs_fts; CREATE VIRTUAL TABLE docs_fts USING fts5(bg, content="");');
  const restore = readFileSync(new URL('./kgs_restore_index.sql', import.meta.url), 'utf8');
  db.exec(restore);
  db.exec(restore);
  assert((await debug('전송연동확인기준')).some(r => r.law === 'KGS GC205'));
} finally {
  server.close();
  rmSync(root, { recursive: true, force: true });
}
console.log('KGS Cloudflare: publishing, search, activation, cache, failure handling and rollback passed');
