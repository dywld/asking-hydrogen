// 서류 폴더 읽기. 고른 폴더 안의 파일만 읽고, 서버(Gemini 검토)로 보낼 모양으로 바꾼다.
//   PDF·사진(스캔 포함) → 파일 그대로(base64). Gemini 가 그림으로 읽는다.
//   한글(HWPX·HWP)·워드·엑셀·글 파일 → 글자만 뽑는다.
const path = require('path');
const fs = require('fs');
const JSZip = require('jszip');
const CFB = require('cfb');

const MAX_FILES = 10;                 // 한 번에 검토하는 파일 수(Gemini 무료 한도 안에서)
const MAX_BYTES = 6 * 1024 * 1024;    // 파일 하나(그대로 보내는 PDF·사진)
const MAX_TEXT = 6000;                // 글자로 보내는 파일 하나
const SKIP = /^(~\$|\.|Thumbs\.db$|desktop\.ini$)/i;

const inside = (p, base) => {
  const r = path.relative(path.resolve(base), path.resolve(String(p || '')));
  return !!r && !r.startsWith('..') && !path.isAbsolute(r);
};

function uniquePath(dir, name) {
  fs.mkdirSync(dir, { recursive: true });
  const ext = path.extname(name), stem = path.basename(name, ext);
  let p = path.join(dir, name);
  for (let i = 2; fs.existsSync(p); i++) p = path.join(dir, `${stem} (${i})${ext}`);
  return p;
}

// 폴더 안 파일 목록(하위 폴더 한 단계까지, 최대 60개)
function scan(dir) {
  const out = [];
  const walk = (d, depth) => {
    let items = [];
    try { items = fs.readdirSync(d, { withFileTypes: true }); } catch (e) { return; }
    for (const it of items) {
      if (out.length >= 60 || SKIP.test(it.name)) continue;
      const full = path.join(d, it.name);
      if (it.isDirectory()) { if (depth < 1) walk(full, depth + 1); continue; }
      let size = 0, mtime = '';
      try { const s = fs.statSync(full); size = s.size; mtime = s.mtime.toISOString(); } catch (e) { continue; }
      out.push({ rel: path.relative(dir, full), name: it.name, ext: path.extname(it.name).slice(1).toLowerCase(), size, mtime });
    }
  };
  walk(dir, 0);
  return out;
}

const decodeXml = s => s.replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&');
// 문단 끝 태그마다 줄을 바꾸고, 글자 태그(<hp:t>·<w:t>) 안만 모은다.
function xmlText(xml, textTag, paraTag) {
  return xml.split(new RegExp(`</${paraTag}>`)).map(p => {
    const m = p.match(new RegExp(`<${textTag}(?:\\s[^>]*)?>[\\s\\S]*?</${textTag}>`, 'g')) || [];
    return m.map(decodeXml).join('');
  }).filter(Boolean).join('\n');
}

async function hwpxText(buf) {
  const z = await JSZip.loadAsync(buf);
  const secs = Object.keys(z.files).filter(n => /^Contents\/section\d+\.xml$/i.test(n)).sort();
  const parts = [];
  for (const n of secs) parts.push(xmlText(await z.file(n).async('string'), 'hp:t', 'hp:p'));
  return parts.join('\n');
}

// 옛 한글(HWP 5)은 본문이 압축·암호화된 이진 형식이다. 대신 파일 안에 든 '미리보기 글자'(PrvText)를 읽는다.
// 앞부분 1천 자 남짓만 들어 있어서, 긴 서류는 앞쪽만 검토된다.
function hwpText(buf) {
  const c = CFB.read(buf, { type: 'buffer' });
  const e = CFB.find(c, 'PrvText');
  if (!e || !e.content) return '';
  return Buffer.from(e.content).toString('utf16le').replace(/\u0000/g, '').replace(/<|>/g, ' ');
}

async function docxText(buf) {
  const z = await JSZip.loadAsync(buf);
  const f = z.file('word/document.xml');
  return f ? xmlText(await f.async('string'), 'w:t', 'w:p') : '';
}

async function xlsxText(buf) {
  const z = await JSZip.loadAsync(buf);
  const ss = z.file('xl/sharedStrings.xml');
  const shared = ss ? (await ss.async('string')).split('</si>').map(s => (s.match(/<t[^>]*>[\s\S]*?<\/t>/g) || []).map(decodeXml).join('')) : [];
  const sheets = Object.keys(z.files).filter(n => /^xl\/worksheets\/sheet\d+\.xml$/.test(n)).sort();
  const out = [];
  for (const n of sheets) {
    const xml = await z.file(n).async('string');
    out.push(`[${path.basename(n, '.xml')}]`);
    for (const row of xml.split('</row>')) {
      const cells = [...row.matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)].map(([, attr, body]) => {
        const v = (body || '').match(/<v>([\s\S]*?)<\/v>/), t = (body || '').match(/<t[^>]*>([\s\S]*?)<\/t>/);
        if (/t="s"/.test(attr) && v) return shared[Number(v[1])] || '';
        return t ? decodeXml(t[1]) : v ? v[1] : '';
      }).filter(Boolean);
      if (cells.length) out.push(cells.join('\t'));
    }
  }
  return out.join('\n');
}

const MIME = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp' };

// 파일 하나를 검토용으로. warn 이 있으면 내용을 못 읽은 것(빈 파일·옛 형식·암호 등).
async function extract(dir, rel) {
  const full = path.join(dir, rel);
  const base = { rel, name: path.basename(rel), ext: path.extname(rel).slice(1).toLowerCase(), size: 0 };
  if (!inside(full, dir)) return { ...base, warn: '폴더 밖 파일' };
  let buf;
  try { buf = fs.readFileSync(full); } catch (e) { return { ...base, warn: '파일을 열 수 없음' }; }
  base.size = buf.length;
  if (!buf.length) return { ...base, warn: '빈 파일 (0바이트)' };
  const ext = base.ext;
  try {
    if (MIME[ext]) {
      if (buf.length > MAX_BYTES) return { ...base, warn: `파일이 너무 큼 (${(buf.length / 1048576).toFixed(1)}MB, 6MB까지)` };
      if (ext === 'pdf' && buf.indexOf('/Encrypt') >= 0) return { ...base, warn: '암호가 걸린 PDF' };
      return { ...base, kind: ext === 'pdf' ? 'pdf' : 'image', mime: MIME[ext], b64: buf.toString('base64') };
    }
    let text = null;
    if (ext === 'hwpx') text = await hwpxText(buf);
    else if (ext === 'hwp') text = hwpText(buf);
    else if (ext === 'docx') text = await docxText(buf);
    else if (ext === 'xlsx') text = await xlsxText(buf);
    else if (['txt', 'csv', 'md'].includes(ext)) text = buf.toString('utf8');
    else if (['doc', 'xls', 'ppt'].includes(ext)) return { ...base, warn: `옛 형식(.${ext}) - ${ext}x 나 PDF로 저장해 올려 주세요` };
    else return { ...base, warn: '검토할 수 없는 형식' };
    text = (text || '').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
    if (!text) return { ...base, warn: ext === 'hwp' ? '한글 파일에서 글자를 못 읽음 - HWPX 나 PDF로 저장해 주세요' : '글자가 없는 파일' };
    return { ...base, kind: 'text', text: text.slice(0, MAX_TEXT), cut: text.length > MAX_TEXT, note: ext === 'hwp' ? '옛 한글 파일은 앞부분만 읽었습니다' : '' };
  } catch (e) {
    return { ...base, warn: '파일이 깨졌거나 형식이 다름' };
  }
}

module.exports = { MAX_FILES, scan, extract, uniquePath, inside };
