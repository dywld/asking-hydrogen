// 브라우저판 도구(cf/public_extra/cf-tools.js)와 워커 버튼(cf/src/tools_suggest.js)이
// 파이썬 원본(annex_checklist·safety_rules·storage_calc·package)과 같은 답을 내는지 대조한다.
//   node cf/test_tools.mjs
// 기대값은 cf/test_tools_gen.py 가 만든다(무작위 입력, 씨앗 고정). 한글 문서는 블록과 section0.xml 을 대조한다.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const exp = JSON.parse(execFileSync('python', [path.join(HERE, 'test_tools_gen.py')],
  { encoding: 'utf-8', maxBuffer: 512 * 1024 * 1024, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }));
const D = JSON.parse(fs.readFileSync(path.join(HERE, 'public_extra/docs/tools.json'), 'utf-8'));
const { make } = require('./public_extra/cf-tools.js');
const T = make(D);

let bad = 0, n = 0;
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function diff(a, b, at = '') {          // 처음 어긋난 곳
  if (same(a, b)) return null;
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) { const d = diff(a[k], b[k], `${at}.${k}`); if (d) return d; }
  }
  return `${at}: js=${JSON.stringify(a)?.slice(0, 300)} py=${JSON.stringify(b)?.slice(0, 300)}`;
}
function check(name, js, py) {
  n++;
  const d = diff(js, py);
  if (d) { bad++; if (bad <= 15) console.log(`✗ ${name} ${d}`); }
}
const noMade = o => { const c = { ...o }; delete c.made; return c; };

for (const c of exp.checklist) {
  const [fac, vals, tid, marks] = c.args;
  const s = T.buildSheet(fac, vals, tid, marks);
  check(`점검표 ${tid}/${fac}`, noMade(s), noMade(c.sheet));
  check(`점검표 문서 ${tid}/${fac}`, { title: s.title, blocks: T.sheetBlocks({ ...s, made: c.sheet.made }, c.company) }, c.hwpx);
}
for (const c of exp.rules) {
  const [tid, kind, fl, info] = c.args;
  const d = T.buildRules(tid, kind, fl, info);
  check(`규정 ${tid}/${kind}`, noMade(d), noMade(c.doc));
  check(`규정 문서 ${tid}/${kind}`, { title: d.title, blocks: T.rulesBlocks({ ...d, made: c.doc.made }) }, c.hwpx);
}
for (const c of exp.storage) {
  const r = T.calc(c.items);
  check('저장능력', r, c.res);
  const b = T.storageBlocks(r, c.company);
  b[1][1][1][1] = c.hwpx.blocks[1][1][1][1];          // 작성일
  check('저장능력 문서', { title: '저장능력 계산서', blocks: b }, c.hwpx);
}
for (const c of exp.package) {
  const deps = {
    permitVals: f => {                                 // app.permit_vals (cf-shim 과 같은 규칙)
      const out = {};
      if (!f || typeof f !== 'object') return out;
      for (const [k, v] of Object.entries(f)) out[Array.from(String(k)).slice(0, 20).join('')] = Array.from(v === null ? 'None' : String(v)).slice(0, 120).join('');
      return out;
    },
    permitPdf: async () => { if (c.summary.notes.length) throw new Error('법령정보센터 응답 없음'); return 'PDF'; },
    permitHwpx: async () => 'HWPX', hwpx: async () => 'HWPX', zip: async () => 'ZIP',
  };
  const out = await T.buildPackage(c.req, deps);
  const day = c.cover.blocks[1][1][5][1];
  out.cover[1][1][5][1] = day;
  check(`꾸러미 ${c.req.permit.id}`, { name: out.name, summary: out.summary, cover: { title: '제출 꾸러미 표지', blocks: out.cover } },
    { name: c.name, summary: c.summary, cover: c.cover });
}

// 워커 버튼: import 줄만 바꿔 node 에서 돈다
const src = fs.readFileSync(path.join(HERE, 'src/tools_suggest.js'), 'utf-8')
  .replace(/import T from '\.\/tools_data\.json';/, `const T = ${fs.readFileSync(path.join(HERE, 'src/tools_data.json'), 'utf-8')};`);
const { toolButtons } = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
for (const c of exp.suggest) check(`버튼 '${c.q}' / '${c.past}'`, toolButtons(c.q, c.past), c.items);

// section0.xml: cf-shim 의 hwpxSection 이 hwpx_doc._section 과 같은 글을 내는지
globalThis.window = { fetch: async () => { throw new Error('no fetch'); } };
globalThis.location = { href: 'http://x/', origin: 'http://x' };
new Function(fs.readFileSync(path.join(HERE, 'public_extra/cf-shim.js'), 'utf-8'))();
const H = JSON.parse(fs.readFileSync(path.join(HERE, 'public_extra/docs/layout.json'), 'utf-8')).hwpx;
for (const c of exp.sections) {
  const js = window.__cfDocs.hwpxSection(H, c.blocks);
  n++;
  if (!js.endsWith(c.xml) && js !== c.xml) {
    bad++;
    let i = 0; const a = js.slice(js.length - c.xml.length);
    while (i < a.length && a[i] === c.xml[i]) i++;
    console.log(`✗ section0.xml 다름 @${i}: js=${a.slice(i, i + 120)} | py=${c.xml.slice(i, i + 120)}`);
  }
}
console.log(`${n}건 대조, 어긋남 ${bad}건`);
process.exit(bad ? 1 : 0);
