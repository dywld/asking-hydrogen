/* 클라우드플레어 배포용: 서류 만들기(PDF·HWPX·DOCX·미리보기)를 브라우저에서 한다.
 *
 * 무료 워커는 요청마다 CPU 10ms 라 PDF 를 채울 수 없다. 그래서 index.html 이 부르는
 *   /api/permit/file · /api/permit/preview · /api/permit/editor
 *   /api/sandbox/file · /api/sandbox/preview · /api/sandbox/editor
 * 를 이 파일이 fetch 단계에서 가로채, 파이썬 서버(app.py)와 같은 모양의 응답을 브라우저에서 만든다.
 * 칸 자리는 cf/export_docs.py 가 서버 코드(permit_forms·sandbox_doc)를 그대로 돌려 기록한 /docs/layout.json.
 * 라이브러리: pdf-lib 1.17.1, @pdf-lib/fontkit 1.1.1, JSZip 3.10.1, pdf.js 3.11.174 (필요할 때만 받는다).
 */
(function () {
  'use strict';
  const LIBS = {
    pdflib: 'https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js',
    fontkit: 'https://cdn.jsdelivr.net/npm/@pdf-lib/fontkit@1.1.1/dist/fontkit.umd.min.js',
    jszip: 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js',
    pdfjs: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js',
    pdfjsWorker: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js',
  };
  const BASE = '/docs/';
  const origFetch = window.fetch.bind(window);
  const ROUTES = ['/api/permit/file', '/api/permit/preview', '/api/permit/editor',
    '/api/sandbox/file', '/api/sandbox/preview', '/api/sandbox/editor'];

  // ------------------------------------------------------------ 받아 두기
  const once = {};
  const memo = (k, fn) => once[k] || (once[k] = fn().catch(e => { delete once[k]; throw e; }));
  const script = url => memo(url, () => new Promise((ok, no) => {
    const s = document.createElement('script');
    s.src = url; s.async = true; s.crossOrigin = 'anonymous';
    s.onload = () => ok(); s.onerror = () => no(new Error('라이브러리를 받지 못했습니다: ' + url));
    document.head.appendChild(s);
  }));
  const bytes = path => memo('b:' + path, async () => {
    const r = await origFetch(BASE + path);
    if (!r.ok) throw new Error('자료를 받지 못했습니다: ' + path);
    return new Uint8Array(await r.arrayBuffer());
  });
  const layout = () => memo('layout', async () => {
    const r = await origFetch(BASE + 'layout.json');
    if (!r.ok) throw new Error('서식 자리 자료가 없습니다');
    return r.json();
  });
  const pdfLib = () => memo('pdflib', async () => {
    await script(LIBS.pdflib); await script(LIBS.fontkit);
    return window.PDFLib;
  });
  const jszip = () => script(LIBS.jszip).then(() => window.JSZip);

  // ------------------------------------------------------------ 파이썬 흉내
  const cp = s => Array.from(s);                         // 파이썬 문자열 자르기는 코드포인트 단위
  const cut = (s, n) => cp(s).slice(0, n).join('');
  const pystr = v => v === null || v === undefined ? 'None' : v === true ? 'True' : v === false ? 'False'
    : typeof v === 'object' ? JSON.stringify(v) : String(v);
  const strip = s => s.replace(/^[\s\x1c-\x1f\x85]+|[\s\x1c-\x1f\x85]+$/g, '');
  const rstrip = s => s.replace(/[\s\x1c-\x1f\x85]+$/, '');
  const splitlines = s => {
    const out = s.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/);
    if (out.length && out[out.length - 1] === '') out.pop();
    return out;
  };
  const pad2 = n => String(n);
  const today = () => {
    const d = new Date();
    return {date_y: String(d.getFullYear()), date_m: pad2(d.getMonth() + 1), date_d: pad2(d.getDate())};
  };
  const ymd = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  // urllib.parse.quote(safe='/')
  const quote = s => encodeURIComponent(s).replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase())
    .replace(/%2F/g, '/');

  function permitVals(fields) {                          // app.permit_vals
    const out = {};
    if (!fields || typeof fields !== 'object') return out;
    for (const [k0, v0] of Object.entries(fields)) {
      const k = cut(String(k0), 20), v = pystr(v0);
      if (k === 'sign') {
        if (v.startsWith('data:image/png;base64,') && v.length < 400000) out[k] = v;
      } else out[k] = cut(v, 120);
    }
    return out;
  }

  function cleanSandbox(d) {                             // app.clean_sandbox
    if (!d || typeof d !== 'object' || Array.isArray(d)) return {};
    const out = {};
    for (const k of ['kind', 'name', 'what', 'area', 'period', 'scale', 'company', 'laws', 'bizno', 'address',
      'ceo', 'tel', 'email', 'applicant', 'date_y', 'date_m', 'date_d', 'type', 'why']) {
      const v = d[k];
      if (typeof v === 'string' && strip(v) && v !== '모름') out[k] = cut(strip(v), 120);
    }
    const sig = d.sign;
    if (typeof sig === 'string' && sig.startsWith('data:image/png;base64,') && sig.length < 400000) out.sign = sig;
    if (!['실증특례', '임시허가'].includes(out.kind)) delete out.kind;
    return out;
  }

  const b64 = u8 => {
    let s = '';
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  };
  const unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

  // ------------------------------------------------------------ PDF 에 글 얹기
  async function openForm(L, lay) {
    const PDFLib = await pdfLib();
    const [src, font] = await Promise.all([bytes(lay.pdf), bytes('font.ttf')]);
    const doc = await PDFLib.PDFDocument.load(src);
    doc.registerFontkit(window.fontkit);
    const fk = await fontkitFont(font);
    const ops = [];                                     // 글자는 모았다가 save 때 쓴 글자만 담은 글꼴로 그린다
    const pages = doc.getPages();
    const M = L.metrics;
    const tx = (pg, x, y) => {                          // pymupdf 좌표 → PDF 좌표
      const [a, b, c, d, e, g] = lay.page.mat[pg];
      return [a * x + c * y + e, b * x + d * y + g];
    };
    const rgb = c => PDFLib.rgb(c[0], c[1], c[2]);
    // 글꼴에 없는 글자는 빈 네모 대신 '?' (맑은 고딕에 있고 본문 글꼴에 없는 한자 등)
    const safe = s => cp(s).map(ch => fk.hasGlyphForCodePoint(ch.codePointAt(0)) ? ch : '?').join('');
    // Page.insert_text: 줄바꿈이 있으면 (ascender-descender)*크기 만큼 내려 쓴다
    const text = (pg, x, y, s, fs, color) => {
      splitlines(s).forEach((line, i) => {
        if (!line) return;
        const [X, Y] = tx(pg, x, y + i * fs * (M.ascender - M.descender));
        ops.push([pg, X, Y, safe(line), fs, color]);
      });
    };
    // Page.insert_textbox(align 0, rotate 0) 그대로: 낱말로 나누고, 넘치면 아무것도 쓰지 않는다
    const width = ch => {
      const c = ch.codePointAt(0);
      if (c < 0x3400) return M.low[c];
      if (c >= 0xAC00 && c < 0xD7A4) return M.hangul;
      const o = M.other[String(c)];
      return o === undefined ? 1 : o;
    };
    const textbox = (pg, rect, buffer, fs, lh, color) => {
      if (!buffer) return;
      const pix = s => cp(s).reduce((a, ch) => a + width(ch), 0) * fs;
      const blen = width(' ') * fs;
      const maxw = rect[2] - rect[0], maxh = rect[3] - rect[1];
      const t0 = splitlines(buffer.replace(/\t/g, ' '));
      let out = '';
      t0.forEach((line, i) => {
        const words = line.split(' ');
        let lbuff = '', rest = maxw;
        for (const word of words) {
          const pl = pix(word);
          if (rest >= pl) { lbuff += word + ' '; rest -= pl + blen; continue; }
          if (lbuff) out += rstrip(lbuff) + '\n';
          lbuff = ''; rest = maxw;
          if (pl <= maxw) { lbuff = word + ' '; rest = maxw - pl - blen; continue; }
          for (const ch of cp(word)) {
            if (pix(lbuff) <= maxw - pix(ch)) lbuff += ch;
            else { out += lbuff + '\n'; lbuff = ch; }
          }
          lbuff += ' '; rest = maxw - pix(lbuff);
        }
        if (lbuff) out += rstrip(lbuff);
        if (i < t0.length - 1) out += '\n';
      });
      if (out.endsWith('\n')) out = out.slice(0, -1);
      const lines = out.split('\n');
      const lfac = lh || (M.ascender - M.descender);
      if (fs * lfac * lines.length - M.descender * fs - maxh > 1e-5) return;   // 넘치면 쓰지 않는다(pymupdf 와 같음)
      lines.forEach((ln, i) => {
        if (!ln) return;
        const y = rect[1] + fs * M.ascender + fs * M.ascender * i * lfac;
        const [X, Y] = tx(pg, rect[0], y);
        ops.push([pg, X, Y, safe(ln), fs, color]);
      });
    };
    // insert_image(keep_proportion=True): 칸 안에 비율대로 줄여 가운데
    const image = async (pg, rect, dataUrl) => {
      const img = await doc.embedPng(unb64(dataUrl.split(',', 2)[1]));
      const rw = rect[2] - rect[0], rh = rect[3] - rect[1];
      const k = Math.min(rw / img.width, rh / img.height);
      const w = img.width * k, h = img.height * k;
      const x0 = rect[0] + (rw - w) / 2, y0 = rect[1] + (rh - h) / 2;
      const [X, Y] = tx(pg, x0, y0 + h);
      pages[pg].drawImage(img, {x: X, y: Y, width: w, height: h});
    };
    const save = async () => {
      if (ops.length) {
        const f = await doc.embedFont(trimFont(font, fk, ops.map(o => o[3]).join('')), {subset: false});
        for (const [pg, X, Y, t, fs, color] of ops) pages[pg].drawText(t, {x: X, y: Y, size: fs, font: f, color: rgb(color)});
      }
      return doc.save();
    };
    return {doc, text, textbox, image, save};
  }

  // 글꼴 줄이기: pdf-lib(fontkit) 의 subset 은 이 글꼴의 글자 모양을 깨뜨린다(실측: 한글 대부분이 안 보임).
  // 그래서 글리프 번호는 그대로 두고, 쓰지 않는 글자의 모양(glyf)만 비운 TrueType 을 직접 만들어 통째로 넣는다.
  const fontkitFont = font => memo('fk', async () => window.fontkit.create(font));
  function trimFont(font, fk, text) {
    const dv = new DataView(font.buffer, font.byteOffset, font.byteLength);
    const n = dv.getUint16(4), tables = {};
    for (let i = 0; i < n; i++) {
      const o = 12 + i * 16;
      const tag = String.fromCharCode(font[o], font[o + 1], font[o + 2], font[o + 3]);
      tables[tag] = [dv.getUint32(o + 8), dv.getUint32(o + 12)];
    }
    const longLoca = dv.getInt16(tables.head[0] + 50) === 1;
    const ng = dv.getUint16(tables.maxp[0] + 4);
    const loca = i => longLoca ? dv.getUint32(tables.loca[0] + i * 4) : dv.getUint16(tables.loca[0] + i * 2) * 2;
    const keep = new Set([0]);
    for (const ch of cp(text + '?')) keep.add(fk.glyphForCodePoint(ch.codePointAt(0)).id);
    const parts = [], offs = new Uint32Array(ng + 1);
    let pos = 0;
    for (let g = 0; g < ng; g++) {
      offs[g] = pos;
      if (keep.has(g)) {
        const a = loca(g), b = loca(g + 1);
        if (b > a) { parts.push(font.subarray(tables.glyf[0] + a, tables.glyf[0] + b)); pos += b - a; if (pos % 4) { parts.push(new Uint8Array(4 - pos % 4)); pos += 4 - pos % 4; } }
      }
    }
    offs[ng] = pos;
    const glyf = new Uint8Array(pos);
    let q = 0;
    for (const p of parts) { glyf.set(p, q); q += p.length; }
    const locaB = new Uint8Array((ng + 1) * 4);
    const lv = new DataView(locaB.buffer);
    offs.forEach((v, i) => lv.setUint32(i * 4, v));
    const head = font.slice(tables.head[0], tables.head[0] + tables.head[1]);
    new DataView(head.buffer).setInt16(50, 1);
    new DataView(head.buffer).setUint32(8, 0);
    const out = {glyf, loca: locaB, head};
    for (const t of ['OS/2', 'cmap', 'hhea', 'hmtx', 'maxp', 'name', 'post']) {
      if (tables[t]) out[t] = font.subarray(tables[t][0], tables[t][0] + tables[t][1]);
    }
    const tags = Object.keys(out).sort();
    let size = 12 + tags.length * 16;
    const at = {};
    for (const t of tags) { at[t] = size; size += (out[t].length + 3) & ~3; }
    const res = new Uint8Array(size), rv = new DataView(res.buffer);
    rv.setUint32(0, 0x00010000); rv.setUint16(4, tags.length);
    let es = 0; while ((1 << (es + 1)) <= tags.length) es++;
    rv.setUint16(6, (1 << es) * 16); rv.setUint16(8, es); rv.setUint16(10, tags.length * 16 - (1 << es) * 16);
    const sum = (u8, off, len) => {
      let s = 0;
      for (let i = 0; i < len; i += 4) s = (s + rv.getUint32(off + i)) >>> 0;
      return s;
    };
    tags.forEach((t, i) => {
      res.set(out[t], at[t]);
      const o = 12 + i * 16;
      for (let k = 0; k < 4; k++) res[o + k] = t.charCodeAt(k);
      rv.setUint32(o + 4, sum(res, at[t], (out[t].length + 3) & ~3));
      rv.setUint32(o + 8, at[t]); rv.setUint32(o + 12, out[t].length);
    });
    rv.setUint32(at.head + 8, (0xB1B0AFBA - sum(res, 0, size)) >>> 0);
    return res;
  }

  // permit_forms.fill
  async function permitFill(fid, vals, ink, dynamic = true) {
    const L = await layout();
    const lay = L.permit[fid];
    const P = await openForm(L, lay);
    const INK = ink === 'blue' ? L.colors.blue : [0, 0, 0];
    const at = (m, s, color, fs) => P.text(m.page, m.x, m.y, s, fs || m.fs, color);
    lay.checks.forEach(m => at(m, '√', INK));
    if (lay.choose) {
      const v = vals[lay.choose.key] || '';
      lay.choose.names.forEach(nm => { if (v.startsWith(nm)) lay.choose.marks[nm].forEach(m => at(m, '√', INK)); });
    }
    for (const key of lay.field_order) {
      const m = lay.fields[key];
      if (!m) continue;
      const v = strip(vals[key] || '');
      if (!v && ink !== 'blue') continue;
      const [t, c] = v ? [v, INK] : [L.need, L.colors.orange];
      at(m, cut(t, m.max), c);
    }
    if (dynamic) {
      const td = today();
      for (const key of ['date_y', 'date_m', 'date_d']) {
        const m = lay.dates[key];
        if (m) at(m, cut(strip(vals[key] || td[key]), 4), INK);
      }
      if (lay.name && strip(vals.applicant || '')) at(lay.name, cut(strip(vals.applicant), 20), INK);
      const sig = vals.sign || '';
      if (lay.sign && sig.startsWith('data:image/png;base64,')) await P.image(lay.sign.page, lay.sign.rect, sig);
    }
    if (ink === 'blue' && lay.note) at(lay.note, lay.note.text, L.colors.orange);
    const data = await P.save();
    return [data, `${lay.info.title}_신청서.pdf`];
  }

  // sandbox_doc.fill_pdf
  async function sandboxFill(f, ink = 'black', dynamic = true) {
    const L = await layout();
    const kind = f.kind in L.sandbox_form_no ? f.kind : '실증특례';
    const lay = L.sandbox[kind];
    const P = await openForm(L, lay);
    const blue = ink === 'blue';
    const INK = blue ? L.colors.blue : [0, 0, 0];
    for (const key of lay.field_order) {
      const m = lay.fields[key];
      if (!m) continue;
      const v = strip(f[key] || '');
      if (!v && !blue) continue;
      const [t, c] = v ? [v, INK] : [L.need, L.colors.orange];
      if (m.box) P.textbox(m.page, m.box, t, m.fs, m.lh, c);
      else P.text(m.page, m.x, m.y, cut(t, m.max), m.fs, c);
    }
    if (dynamic) {
      const td = today();
      for (const key of ['date_y', 'date_m', 'date_d']) {
        const m = lay.dates[key];
        if (m) P.text(m.page, m.x, m.y, cut(strip(f[key] || td[key]), 4), m.fs, INK);
      }
      const sig = f.sign || '';
      if (lay.sign && sig.startsWith('data:image/png;base64,')) await P.image(lay.sign.page, lay.sign.rect, sig);
    }
    for (const [key, ms] of Object.entries(lay.chk || {})) {   // 유형·신청사유 √ (sandbox_doc.fill_pdf)
      const on = new Set((String(f[key] || '').match(/[0-9]/g) || []).map(Number));
      ms.forEach((m, i) => { if (on.has(i)) P.text(m.page, m.x, m.y, '√', m.fs, INK); });
    }
    if (blue && lay.note) P.text(lay.note.page, lay.note.x, lay.note.y, lay.note.text, lay.note.fs, L.colors.orange);
    return P.save();
  }

  // app.pdf_pages_png: 110dpi PNG(base64), 10쪽까지
  async function pagesPng(data) {
    await script(LIBS.pdfjs);
    const pdfjs = window.pdfjsLib;
    pdfjs.GlobalWorkerOptions.workerSrc = LIBS.pdfjsWorker;
    const doc = await pdfjs.getDocument({data, isEvalSupported: false}).promise;
    const out = [];
    for (let i = 1; i <= Math.min(doc.numPages, 10); i++) {
      const pg = await doc.getPage(i);
      const vp = pg.getViewport({scale: 110 / 72});
      const cv = document.createElement('canvas');
      cv.width = Math.ceil(vp.width); cv.height = Math.ceil(vp.height);
      const cx = cv.getContext('2d');
      cx.fillStyle = '#fff'; cx.fillRect(0, 0, cv.width, cv.height);
      await pg.render({canvasContext: cx, viewport: vp}).promise;
      out.push(cv.toDataURL('image/png').split(',', 2)[1]);
    }
    await doc.destroy();
    return out;
  }

  // 편집기 응답: 미리 그린 바탕 그림 + 상자(값만 채운다)
  async function editorReply(ed, vals) {
    const td = today();
    const pages = await Promise.all(ed.pages.map(async p => b64(await bytes(p))));
    const boxes = ed.boxes.map(b => {
      const value = b.kind === 'sign' ? '' : /^date_[ymd]$/.test(b.key) ? strip(vals[b.key] || td[b.key])
        : strip(vals[b.key] || '');
      return Object.assign({}, b, {value});
    });
    return {pages, w: ed.w, h: ed.h, boxes};
  }

  // ------------------------------------------------------------ HWPX (hwpx_doc.make_hwpx)
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  function hwpxSection(H, blocks) {
    const run = (t, c = 0) => `<hp:run charPrIDRef="${c}"><hp:t>${esc(t)}</hp:t></hp:run>`;
    const para = (runs, p = 0, pid = 0) => `<hp:p id="${pid}" paraPrIDRef="${p}" styleIDRef="0" pageBreak="0" `
      + `columnBreak="0" merged="0">${runs}`
      + '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" '
      + 'textheight="1000" baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/>'
      + '</hp:linesegarray></hp:p>';
    const cell = (text, col, row, width, fill, ch = 0) => {
      const body = para(run(text, ch), 2);
      return `<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="${fill}">`
        + `<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" `
        + `linkListIDRef="0" linkListNextIDRef="0" textWidth="${width}" textHeight="${H.ROW_H}" hasTextRef="0" hasNumRef="0">`
        + `${body}</hp:subList>`
        + `<hp:cellAddr colAddr="${col}" rowAddr="${row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>`
        + `<hp:cellSz width="${width}" height="${H.ROW_H}"/>`
        + '<hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>';
    };
    const table = rows => {
      const lw = 12000, vw = H.TEXT_W - lw;
      const trs = rows.map(([label, value], i) => '<hp:tr>' + cell(label, 0, i, lw, 3, 3) + cell(value, 1, i, vw, 2) + '</hp:tr>');
      return `<hp:tbl id="0" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" `
        + `textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="0" `
        + `rowCnt="${rows.length}" colCnt="2" cellSpacing="0" borderFillIDRef="2" noAdjust="0">`
        + `<hp:sz width="${H.TEXT_W}" widthRelTo="ABSOLUTE" height="${H.ROW_H * rows.length}" heightRelTo="ABSOLUTE" protect="0"/>`
        + '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
        + 'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        + '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        + '<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
        + trs.join('') + '</hp:tbl>';
    };
    const out = [];
    for (const [kind, val] of blocks) {
      if (kind === 'title') out.push(para(run(val, 1), 1));
      else if (kind === 'heading') out.push(para(run(val, 2), 2));
      else if (kind === 'para') out.push(para(run(val, 0), 0));
      else if (kind === 'table') {
        out.push(para(`<hp:run charPrIDRef="0">${table(val)}</hp:run>`, 0));
        out.push(para(run(''), 0));
      } else throw new Error('알 수 없는 블록: ' + kind);
    }
    const secpr = '<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" '
      + 'tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="0" memoShapeIDRef="0" '
      + 'textVerticalWidthHead="0" masterPageCnt="0">'
      + '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/>'
      + '<hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>'
      + '<hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY">'
      + '<hp:margin header="4252" footer="4252" gutter="0" left="5669" right="5669" top="5669" bottom="4252"/>'
      + '</hp:pagePr></hp:secPr>';
    const head = para(`<hp:run charPrIDRef="0">${secpr}<hp:t></hp:t></hp:run>`, 0);
    let n = 0;
    const body = (head + out.join('')).replace(/<hp:p id="0"/g, () => `<hp:p id="${n++}"`);
    return H.XML_DECL + `<hs:sec ${H.NS}>` + body + '</hs:sec>';
  }

  async function makeHwpx(blocks, title) {
    const L = await layout(), H = L.hwpx, JSZip = await jszip();
    const z = new JSZip();
    const D = {compression: 'DEFLATE', createFolders: false};
    z.file('mimetype', 'application/hwp+zip', {compression: 'STORE', createFolders: false});
    z.file('META-INF/container.xml', H.CONTAINER, D);
    z.file('version.xml', H.VERSION, D);
    z.file('settings.xml', H.SETTINGS, D);
    z.file('Contents/content.hpf', H.MANIFEST.replace('{title}', esc(title)), D);
    z.file('Contents/header.xml', H.HEADER, D);
    z.file('Contents/section0.xml', hwpxSection(H, blocks), D);
    return z.generateAsync({type: 'uint8array', compression: 'DEFLATE'});
  }

  // permit_forms.fill_hwpx
  async function permitHwpx(fid, vals) {
    const L = await layout(), I = L.permit[fid].info;
    const rows = I.field_labels.map(([k, label]) => [label, strip(vals[k] || '') || '[직접 입력]']);
    const lawShort = I.law.replace(' 시행규칙', '');
    const blocks = [
      ['title', `${I.title} 신청서`],
      ['para', `${lawShort} 시행규칙 별지 제${I.no}호서식 기준으로 정리한 문서입니다. 공식 서식 PDF 와 내용을 대조한 뒤 제출하세요.`],
      ['heading', '신청 내용'],
      ['table', rows],
      ['heading', '신청 정보'],
      ['table', [['접수 기관', I.who], ['처리 기간', I.days], ['수수료', I.fee]]],
      ['heading', '같이 낼 서류'],
      ['para', I.docs.length ? I.docs.join(' · ') : '없음'],
    ];
    if (I.after) blocks.push(['heading', '다음 할 일'], ['para', I.after]);
    blocks.push(['para', '주민등록번호·생년월일·서명은 직접 적으세요. 작성일: ' + ymd()]);
    return [await makeHwpx(blocks, I.title), `${I.title}_신청서.hwpx`];
  }

  const BOLD = /\*\*(.+?)\*\*/g;
  const CITE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
  const NEED = '[직접 입력]';
  const PLAN_ROWS = [['company', '신청인'], ['name', '명칭'], ['what', '주요 내용'], ['area', '구역'], ['period', '기간'], ['scale', '규모']];

  // sandbox_doc.make_hwpx
  async function sandboxHwpx(f, text) {
    const L = await layout();
    const kind = f.kind in L.sandbox_form_no ? f.kind : '실증특례';
    const blocks = [
      ['title', `사업실시계획서 (${kind})`],
      ['para', `산업융합촉진법 제10조의${kind === '실증특례' ? '3' : '6'}제6항제1호 · 신청서 별지 제${L.sandbox_form_no[kind]}호서식 붙임서류 1`],
      ['table', PLAN_ROWS.map(([k, label]) => [label, f[k] || NEED])],
    ];
    for (const raw of splitlines(text || '')) {
      const line = rstrip(raw).replace(CITE, '');
      if (!strip(line) || strip(line) === '---') continue;
      const m = line.match(/^(#{1,4})\s+(.*)/);
      if (m) { blocks.push(['heading', m[2].replace(BOLD, '$1')]); continue; }
      const bl = line.match(/^\s*[-*•]\s+(.*)/);
      const body = (bl ? bl[1] : line).replace(BOLD, '$1');
      blocks.push(['para', (bl ? '· ' : '') + body]);
    }
    blocks.push(['para', '이 문서는 AI가 만든 초안입니다. 근거 조문은 원문과 대조하고, [직접 입력] 칸을 채운 뒤 제출하세요. 계획서 세부 양식은 KIAT 안내를 확인하세요.']);
    return makeHwpx(blocks, `사업실시계획서 (${kind})`);
  }

  // ------------------------------------------------------------ DOCX (sandbox_doc.make_docx)
  // 바탕은 python-docx 기본 서식으로 만든 plan_template.docx(본문 글꼴 맑은 고딕 10.5pt). 본문 XML 만 같은 모양으로 짠다.
  const wt = s => {
    const parts = s.split(/(\n|\t)/);
    return parts.map(p => p === '\n' ? '<w:br/>' : p === '\t' ? '<w:tab/>' : !p ? ''
      : `<w:t${/^\s|\s$/.test(p) ? ' xml:space="preserve"' : ''}>${esc(p)}</w:t>`).join('');
  };
  const wr = (s, {bold, color} = {}) => {
    const pr = (bold ? '<w:b/>' : '') + (color ? `<w:color w:val="${color}"/>` : '');
    return `<w:r>${pr ? `<w:rPr>${pr}</w:rPr>` : ''}${wt(s)}</w:r>`;
  };
  const wp = (runs, style) => `<w:p>${style ? `<w:pPr><w:pStyle w:val="${style}"/></w:pPr>` : ''}${runs}</w:p>`;
  const heading = (s, level) => wp(s ? wr(s) : '', level === 0 ? 'Title' : 'Heading' + level);

  async function sandboxDocx(f, text, refs) {
    const L = await layout(), JSZip = await jszip();
    const kind = f.kind in L.sandbox_form_no ? f.kind : '실증특례';
    const out = [];
    out.push(heading(`사업실시계획서 (${kind})`, 0));
    out.push(wp(wr(`산업융합촉진법 제10조의${kind === '실증특례' ? '3' : '6'}제6항제1호 · 신청서 별지 제${L.sandbox_form_no[kind]}호서식 붙임서류 1`, {color: '555555'})));
    const tc = s => `<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="4320"/></w:tcPr><w:p>${s ? wr(s) : ''}</w:p></w:tc>`;
    out.push('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:type="auto" w:w="0"/>'
      + '<w:tblLook w:firstColumn="1" w:firstRow="1" w:lastColumn="0" w:lastRow="0" w:noHBand="0" w:noVBand="1" w:val="04A0"/>'
      + '</w:tblPr><w:tblGrid><w:gridCol w:w="4320"/><w:gridCol w:w="4320"/></w:tblGrid>'
      + PLAN_ROWS.map(([k, label]) => `<w:tr>${tc(label)}${tc(f[k] || NEED)}</w:tr>`).join('') + '</w:tbl>');
    const cite = (_, g) => {
      const names = g.split(',').map(n => refs[strip(n)]).filter(Boolean);
      return names.length ? ` (근거: ${names.join('; ')})` : '';
    };
    for (const raw of splitlines(text || '')) {
      let line = rstrip(raw);
      if (!strip(line) || strip(line) === '---') continue;
      line = line.replace(CITE, cite);
      const m = line.match(/^(#{1,4})\s+(.*)/);
      if (m) { out.push(heading(m[2].replace(BOLD, '$1'), Math.min(m[1].length, 3))); continue; }
      const bl = line.match(/^\s*[-*•]\s+(.*)/);
      const body = bl ? bl[1] : line;
      const runs = body.split(/(\*\*.+?\*\*|\[직접 입력[^\]]*\])/).filter(Boolean).map(part => {
        const isB = part.startsWith('**');
        return wr(isB ? part.replace(/^\*+|\*+$/g, '') : part,
          {bold: isB, color: part.startsWith('[직접 입력') ? 'B45309' : null});
      });
      out.push(wp(runs.join(''), bl ? 'ListBullet' : null));
    }
    out.push('<w:p><w:r><w:br w:type="page"/></w:r></w:p>');
    out.push(heading('붙임서류 작성 틀', 1));
    const name = f.name || '[직접 입력: 제품·서비스 이름]';
    const tpl = [
      ['산업융합 신제품·서비스 해당 설명', [`${name}의 핵심 기술·구성`, '기존 제품·서비스와 다른 점', '융합된 기술·분야']],
      ['현행 법령으로 안 되는 사유', ['막히는 법령·조문: ' + (f.laws || '[직접 입력]'),
        '사유: 기준 없음 / 기준이 맞지 않음 / 불합리 중 해당', '필요한 특례 내용']],
      ['혁신성 및 이용자 편익', ['혁신성(새로운 점)', '이용자·국민이 얻는 이득', '산업·지역 파급효과']],
      ...(kind === '실증특례' ? [['향후 시장 성장 가능성', ['시장 규모·성장률(출처)', '수요처·고객', '사업화 계획']]] : []),
      ['손해 및 손해배상 방안', ['가입할 책임보험(보험사·보상한도)', '사고 시 배상 절차']],
      ['생명·건강·안전·환경·개인정보 영향', ['위험요소와 안전대책(KGS Code 등 근거)', '시험·인증 결과', '환경·개인정보 영향과 대책']],
    ];
    tpl.forEach(([title, items], i) => {
      out.push(heading(`붙임 ${i + 2}. ${title}`, 2));
      items.forEach(it => out.push(wp(wr(it + ' : ') + wr('[직접 입력]', {color: 'B45309'}), 'ListBullet')));
    });
    out.push(wp(wr('이 문서는 AI가 만든 초안입니다. 근거 조문은 원문과 대조하고, [직접 입력] 칸을 채운 뒤 제출하세요. 계획서 세부 양식은 KIAT 안내를 확인하세요.', {color: '555555'})));
    const z = await JSZip.loadAsync(await bytes('plan_template.docx'));
    const xml = await z.file('word/document.xml').async('string');
    const i = xml.indexOf('<w:body>') + '<w:body>'.length;
    z.file('word/document.xml', xml.slice(0, i) + out.join('') + xml.slice(i));
    return z.generateAsync({type: 'uint8array', compression: 'DEFLATE'});
  }

  // ------------------------------------------------------------ 응답
  const json = (status, obj) => new Response(JSON.stringify(obj), {status, headers: {'Content-Type': 'application/json; charset=utf-8'}});
  const file = (data, name, ctype) => new Response(data, {status: 200, headers: {
    'Content-Type': ctype, 'Content-Disposition': `attachment; filename*=UTF-8''${quote(name)}`}});
  const errMsg = e => (e && e.message) || String(e);

  async function handle(path, req) {
    const L = await layout();
    if (path.startsWith('/api/permit/')) {
      const fid = req.id;
      if (typeof fid !== 'string' || !(fid in L.permit)) return json(400, {error: '서식 id 가 없습니다'});
      const vals = permitVals(req.fields);
      if (path === '/api/permit/file') {
        const hwpx = req.fmt === 'hwpx';
        try {
          const [data, name] = hwpx ? await permitHwpx(fid, vals) : await permitFill(fid, vals, req.ink === 'blue' ? 'blue' : 'black');
          return file(data, name, hwpx ? 'application/octet-stream' : 'application/pdf');
        } catch (e) { return json(502, {error: '파일을 만들지 못했습니다: ' + errMsg(e)}); }
      }
      if (path === '/api/permit/preview') {
        try {
          const [data] = await permitFill(fid, vals, 'black');
          return json(200, {pages: await pagesPng(data)});
        } catch (e) { return json(502, {error: '미리보기를 만들지 못했습니다: ' + errMsg(e)}); }
      }
      // editor: permit_forms.edit_layout — 선택 칸(√)만 바탕에 찍힌 그림을 고른다
      try {
        const lay = L.permit[fid];
        let v = '0';
        if (lay.choose && vals[lay.choose.key]) {
          const val = vals[lay.choose.key];
          const hit = lay.choose.names.findIndex(nm => val.startsWith(nm));
          if (hit >= 0) v = String(hit + 1);
        }
        return json(200, await editorReply(lay.editor[v], vals));
      } catch (e) { return json(502, {error: '미리보기를 만들지 못했습니다: ' + errMsg(e)}); }
    }
    const f = cleanSandbox(req.fields);
    if (path === '/api/sandbox/editor') {
      try {
        const kind = f.kind in L.sandbox_form_no ? f.kind : '실증특례';
        return json(200, await editorReply(L.sandbox[kind].editor['0'], f));
      } catch (e) { return json(502, {error: '미리보기를 만들지 못했습니다: ' + errMsg(e)}); }
    }
    if (path === '/api/sandbox/preview') {
      try { return json(200, {pages: await pagesPng(await sandboxFill(f))}); }
      catch (e) { return json(502, {error: '미리보기를 만들지 못했습니다: ' + errMsg(e)}); }
    }
    // /api/sandbox/file
    const fmt = req.fmt;
    let data, name, ctype;
    try {
      if (fmt === 'pdf') {
        [data, name, ctype] = [await sandboxFill(f), '신청서.pdf', 'application/pdf'];
      } else if (fmt === 'docx') {
        const refs = {};
        const r0 = req.refs && typeof req.refs === 'object' ? req.refs : {};
        for (const [k, v] of Object.entries(r0)) refs[String(k)] = cut(pystr(v), 120);
        data = await sandboxDocx(f, cut(req.text ? pystr(req.text) : '', 30000), refs);
        name = '사업실시계획서.docx';
        ctype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      } else if (fmt === 'hwpx') {
        data = await sandboxHwpx(f, cut(req.text ? pystr(req.text) : '', 30000));
        name = '사업실시계획서.hwpx';
        ctype = 'application/octet-stream';
      } else return json(400, {error: 'fmt 는 pdf/docx/hwpx'});
    } catch (e) { return json(502, {error: '파일을 만들지 못했습니다: ' + errMsg(e)}); }
    return file(data, `${f.kind || '실증특례'}_${name}`, ctype);
  }

  window.fetch = async function (input, init) {
    let url, method, body;
    try {
      url = new URL(typeof input === 'string' || input instanceof URL ? String(input) : input.url, location.href);
      method = ((init && init.method) || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    } catch (e) { return origFetch(input, init); }
    if (url.origin !== location.origin || method !== 'POST' || !ROUTES.includes(url.pathname)) return origFetch(input, init);
    body = init && init.body !== undefined ? init.body : (input instanceof Request ? await input.text() : '');
    let req;
    try {
      req = JSON.parse(typeof body === 'string' ? body : new TextDecoder().decode(body));
      if (!req || typeof req !== 'object' || Array.isArray(req)) throw 0;
    } catch (e) { return json(400, {error: '요청 형식이 올바르지 않습니다(UTF-8 JSON)'}); }
    try { return await handle(url.pathname, req); }
    catch (e) { return json(502, {error: '파일을 만들지 못했습니다: ' + errMsg(e)}); }
  };
  // 시험용: 화면 없이 바로 부를 수 있게 둔다
  window.__cfDocs = {permitFill, sandboxFill, permitHwpx, sandboxHwpx, sandboxDocx, pagesPng, layout};
})();
