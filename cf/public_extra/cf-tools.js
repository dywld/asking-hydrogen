/* 클라우드플레어 배포용: 자체점검표·안전관리규정 초안·저장능력 계산·제출 꾸러미를 브라우저에서 만든다.
 *
 * 파이썬 서버(app.py)에서는 annex_checklist · safety_rules · storage_calc · package 가 하던 일이다.
 * checklist.html · rules.html · package.html 이 부르는
 *   GET  /api/checklist · /api/rules · /api/package      (목록)
 *   POST /api/checklist · /api/rules · /api/storage · /api/package
 * 를 fetch 단계에서 가로채, 파이썬과 같은 모양의 응답을 만든다. AI 를 부르지 않는다.
 * 자료(별표 템플릿·거리표·서식 칸)는 cf/export_tools.py 가 뽑은 /docs/tools.json.
 * 한글 문서(HWPX)·신청서 PDF 는 cf-shim.js(window.__cfDocs)로 만든다. cf-shim.js 다음에 붙인다.
 * 파이썬과 같은 결과가 나오는지는 cf/test_tools.mjs 가 대조한다.
 */
(function (root) {
  'use strict';

  // ------------------------------------------------------------ 파이썬 흉내
  const cp = s => Array.from(String(s));
  const cut = (s, n) => cp(s).slice(0, n).join('');
  const pyStrip = s => String(s).replace(/^[\s\x1c-\x1f\x85]+|[\s\x1c-\x1f\x85]+$/g, '');
  const pystr = v => v === null || v === undefined ? 'None' : v === true ? 'True' : v === false ? 'False'
    : typeof v === 'object' ? JSON.stringify(v) : String(v);
  // 파이썬은 실수를 '정확한 십진값'에서 반올림한다(정확히 반이면 짝수 쪽). JS toFixed 는 가끔 달라서
  // (0.9×0.15×87.5 → 파이썬 11.812, toFixed 11.813) 실수의 정확한 십진값을 BigInt 로 풀어 같은 규칙으로 자른다.
  const F64 = new DataView(new ArrayBuffer(8));
  function exact(x) {                                   // |x| = digits / 10^scale (정확히)
    F64.setFloat64(0, Math.abs(x));
    const hi = F64.getUint32(0), lo = F64.getUint32(4);
    const be = (hi >>> 20) & 0x7ff;
    let m = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
    let e;
    if (be === 0) e = -1074; else { m |= 1n << 52n; e = be - 1075; }
    if (e >= 0) return {digits: m << BigInt(e), scale: 0};
    return {digits: m * 5n ** BigInt(-e), scale: -e};
  }
  function fixed(x, n) {                                // f"{x:.{n}f}"
    const {digits, scale} = exact(x);
    let q;
    if (scale <= n) q = digits * 10n ** BigInt(n - scale);
    else {
      const div = 10n ** BigInt(scale - n), r = digits % div;
      q = digits / div;
      if (r * 2n > div || (r * 2n === div && q % 2n === 1n)) q += 1n;
    }
    let s = q.toString().padStart(n + 1, '0');
    if (n) s = s.slice(0, -n) + '.' + s.slice(-n);
    return (x < 0 || Object.is(x, -0) ? '-' : '') + s;
  }
  // f"{x:g}" (유효숫자 6자리, 뒤 0 지움, 지수 -4 미만·6 이상이면 e 표기)
  function g(x) {
    x = Number(x);
    if (!isFinite(x)) return isNaN(x) ? 'nan' : (x > 0 ? 'inf' : '-inf');
    if (x === 0) return Object.is(x, -0) ? '-0' : '0';
    const trim = s => s.includes('.') ? s.replace(/0+$/, '').replace(/\.$/, '') : s;
    let exp = Math.floor(Math.log10(Math.abs(x)));
    for (const k of [exp - 1, exp, exp + 1]) if (Math.abs(x) >= 10 ** k) exp = k;     // log10 오차 보정
    let s = fixed(x, Math.max(0, 5 - exp));
    if (Math.abs(Number(s)) >= 10 ** (exp + 1)) { exp += 1; s = fixed(x, Math.max(0, 5 - exp)); }   // 999999.5 → 1e+06
    if (exp < -4 || exp >= 6) {
      const [m, e] = x.toExponential(5).split('e');
      return trim(m) + 'e' + (Number(e) < 0 ? '-' : '+') + String(Math.abs(Number(e))).padStart(2, '0');
    }
    return trim(s);
  }
  const round = (x, n) => Number(fixed(x, n));         // round(x, n)
  // f"{x:,.3f}"
  function comma3(x) {
    const s = fixed(x, 3), neg = s.startsWith('-'), [i, d] = s.replace('-', '').split('.');
    return (neg ? '-' : '') + i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + d;
  }
  const today = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  const stripBr = s => s.replace(/^[\[\]]+|[\[\]]+$/g, '');           // str.strip('[]')
  class ToolError extends Error {}

  function make(D, opts = {}) {
    const day = opts.today || today;
    const OK = '적합', BAD = '부적합', CHECK = '확인 필요', NA = '해당 없음', INFO = '참고';

    // ========================================================== 자체점검표 (annex_checklist)
    const template = tid => {
      if (!/^[a-z0-9_]+$/.test(tid || '') || !D.annex[tid]) throw new ToolError(`'${tid}'`);
      return D.annex[tid];
    };
    function lookup(tableId, capacity) {                   // distance.lookup
      const t = D.distance.find(t => t.id === tableId);
      if (!t) return null;
      for (const row of t.rows) {
        if (row.max === null || capacity <= row.max) {
          return {table: t.id, name: t.name, law: t.law, ref: t.ref, unit: t.unit, columns: t.columns, capacity,
            label: row.label, values: row.values, extra: row.extra ?? null, notes: t.notes, rows: t.rows};
        }
      }
      return null;
    }
    const num = v => {
      if (v === null || v === undefined || typeof v === 'boolean') return null;
      if (typeof v === 'number') return v;
      const s = String(v).replace(/,/g, '').replace(/[^\d.]/g, '');
      if (!s || !/^(\d+\.?\d*|\.\d+)$/.test(s)) return null;
      return Number(s);
    };
    const bool = v => {
      if (typeof v === 'boolean') return v;
      if (v === null || v === undefined) return null;
      const s = pyStrip(pystr(v)).toLowerCase();
      if (['1', 'true', 'y', 'yes', '예', '네', '있음', 'o'].includes(s)) return true;
      if (['0', 'false', 'n', 'no', '아니오', '아니요', '없음', 'x'].includes(s)) return false;
      return null;
    };
    function clean(t, vals) {
      const out = {};
      for (const inp of t.inputs) {
        let v = (vals || {})[inp.key];
        v = inp.type === 'number' ? num(v) : bool(v);
        if (v !== null && v !== undefined) out[inp.key] = v;
      }
      return out;
    }
    const mm = (x, u = 'm') => `${g(x)}${u}`;
    const M_RE = /^\s*(\d+(?:\.\d+)?)\s*m\s*$/;

    function protection(t, fac, v, a) {
      if (a.underground === 'exempt' && v.underground) return [NA, '지하에 설치한 저장설비는 이 거리 표를 적용하지 않습니다.', null];
      if (a.exempt_if && v[a.exempt_if]) return [NA, a.exempt_why ?? '적용 제외 대상입니다.', null];
      const cap = v[a.cap ?? 'capacity'];
      if (cap === undefined || cap === null) return [CHECK, '처리·저장능력을 넣으면 표에서 거리를 찾습니다.', null];
      const r = lookup(t.facilities[fac].distance, cap);
      if (!r) return [CHECK, '표 범위 밖입니다. 원문 표를 직접 확인하세요.', null];
      const need = [['제1종', 'd_prot1'], ['제2종', 'd_prot2']].map(([col, key], i) => {
        const m = M_RE.exec(r.values[i]);
        return [col, key, m ? Number(m[1]) : null, r.values[i]];
      });
      const half = (a.underground ?? 'half') === 'half' && !!v.underground;
      const parts = [];
      let verdict = OK, haveAny = false;
      for (const [col, key, base, raw] of need) {
        if (base === null) {
          parts.push(`${col} 기준 '${raw}' — 원문 표 확인`);
          verdict = verdict === OK ? CHECK : verdict;
          continue;
        }
        const req = half ? base / 2 : base;
        const d = v[key];
        const label = `${col} ${mm(req)} 이상` + (half ? ' (지하 설치 ½)' : '');
        if (d === undefined || d === null) { parts.push(`${label} — 거리 미입력(해당 보호시설이 없으면 무관)`); continue; }
        haveAny = true;
        if (d >= req) parts.push(`${label} — 실제 ${mm(d)} ✓`);
        else { parts.push(`${label} — 실제 ${mm(d)} ✗ (${mm(req - d)} 부족)`); verdict = BAD; }
      }
      if (!haveAny && verdict === OK) verdict = CHECK;
      const basis = `${r.ref} '${r.label}' 줄`;
      let note = parts.join(' · ') + `. 근거 표: ${basis}. 시장·군수·구청장이 거리를 더할 수 있습니다.`;
      if (verdict === BAD && a.hint) note += ' ' + a.hint;
      return [verdict, note, `능력 ${g(cap)}㎥ → ${r.label}`];
    }
    function boundaryProt1(t, fac, v, a) {
      if (v.underground) return [NA, '지하에 설치한 저장설비는 해당 없음.'];
      const cap = v.capacity, d = v[a.input];
      if (cap === undefined) return [CHECK, '저장능력을 넣으면 기준 거리를 계산합니다.'];
      const r = lookup(t.facilities[fac].distance, cap);
      const m = r && M_RE.exec(r.values[0]);
      if (!m) return [CHECK, '표에서 제1종 거리를 찾지 못했습니다. 원문 표를 확인하세요.'];
      const base = Number(m[1]), need = Math.min(base, 20);
      const why = `제1종 거리 ${mm(base)}` + (base > 20 ? ' → 20m 상한' : '');
      if (d === undefined) return [CHECK, `기준 ${mm(need)} 이상(${why}). 사업소 경계 거리를 넣어 주세요.`];
      if (d >= need) return [OK, `기준 ${mm(need)} 이상(${why}) — 실제 ${mm(d)} ✓`];
      return [BAD, `기준 ${mm(need)} 이상(${why}) — 실제 ${mm(d)} ✗ (${mm(need - d)} 부족)`];
    }
    function wallOrDistance(v, a) {
      const q = v[a.input];
      if (q === undefined) return [CHECK, '저장량(㎥)을 넣어 주세요.'];
      const kg = q * (a.kg_per_m3 ?? 1);
      if (kg < a.kg) return [NA, `저장량 ${g(q)}㎥ = ${g(kg)}㎏ → ${a.kg}㎏ 미만이라 대상 아님.`];
      const head = `저장량 ${g(q)}㎥ = ${g(kg)}㎏ → 방호벽 대상.`;
      if (v[a.wall]) return [OK, head + ' 용기보관실 벽을 방호벽으로 함.'];
      const [n1, n2] = a.need;
      const d1 = v.d_prot1 ?? null, d2 = v.d_prot2 ?? null;
      if ((d1 === null || d1 >= n1) && (d2 === null || d2 >= n2) && (d1 !== null || d2 !== null))
        return [OK, head + ` 방호벽 대신 보호시설 거리(제1종 ${n1}m·제2종 ${n2}m 이상)를 지킴.`];
      if (d1 === null && d2 === null)
        return [CHECK, head + ` 방호벽을 하거나 보호시설까지 제1종 ${n1}m·제2종 ${n2}m 이상을 지켜야 합니다. 보호시설 거리를 넣으면 판정합니다.`];
      return [BAD, head + ` 방호벽이 없고 보호시설 거리(제1종 ${n1}m·제2종 ${n2}m)도 못 지킴.`];
    }
    function wallIndoor(v, a) {
      const indoor = v[a.indoor];
      if (indoor === false) return [NA, '실외 설치라 해당 없음.'];
      const cap = v[a.input];
      if (cap === undefined || indoor === undefined) return [CHECK, '저장능력과 실내 설치 여부를 넣어 주세요.'];
      if (cap < a.min_cap) return [NA, `저장능력 ${g(cap)}㎥ → ${a.min_cap}㎥ 미만이라 해당 없음.`];
      const w = v[a.wall];
      if (w) return [OK, `저장능력 ${g(cap)}㎥ 실내 설치 → 벽을 방호벽으로 함.`];
      if (w === undefined) return [CHECK, `저장능력 ${g(cap)}㎥ 실내 설치 → 벽이 방호벽인지 넣어 주세요.`];
      return [BAD, `저장능력 ${g(cap)}㎥ 실내 설치인데 벽이 방호벽이 아닙니다.`];
    }
    function range(v, a) {
      const x = v[a.input], u = a.unit ?? 'm';
      if (x === undefined) return [CHECK, '값을 넣어 주세요.'];
      const ok = a.min <= x && x <= a.max;
      return [ok ? OK : BAD, `기준 ${mm(a.min, u)} 이상 ${mm(a.max, u)} 이내 — 실제 ${mm(x, u)} ${ok ? '✓' : '✗'}`];
    }
    function wall30(v) {
      const near = v.bld_30m, wall = v.wall;
      if (near === undefined) return [CHECK, '30m 안 건축물 여부를 넣어 주세요.'];
      if (!near) return [NA, '30m 안에 사람을 수용하는 건축물이 없음.'];
      if (wall) return [OK, '30m 안 건축물 있음 → 방호벽 설치 계획 있음.'];
      if (wall === undefined) return [CHECK, '30m 안 건축물 있음 → 방호벽 설치 여부를 넣어 주세요.'];
      return [BAD, '30m 안 건축물이 있는데 방호벽이 없습니다.'];
    }
    function other(v) {
      const f = v.d_flam, o = v.d_o2;
      if (f === undefined && o === undefined) return [NA, '주변에 다른 가연성가스·산소 제조시설이 없으면 해당 없음.'];
      const parts = [];
      let verdict = OK;
      for (const [d, need, name] of [[f, 5, '가연성가스 제조시설'], [o, 10, '산소 제조시설']]) {
        if (d === undefined) continue;
        const ok = d >= need;
        parts.push(`${name} ${need}m 이상 — 실제 ${mm(d)} ${ok ? '✓' : '✗'}`);
        if (!ok) verdict = BAD;
      }
      return [verdict, parts.join(' · ')];
    }
    function minRule(a, v) {
      const u = a.unit ?? 'm', d = v[a.input];
      if (d === undefined) return a.blank_na ? [NA, '해당 시설이 근처에 없으면 해당 없음.'] : [CHECK, '거리를 넣어 주세요.'];
      const alt = a.alt_if ? v[a.alt_if] : null;
      if (alt && !a.alt_min) return [OK, `${a.alt_why} → ${mm(a.min, u)} 기준 예외 — 실제 ${mm(d, u)}`];
      const need = alt ? a.alt_min : a.min;
      const why = alt ? ` (${a.alt_why} 시 ${need < a.min ? '완화' : '기준'})` : '';
      if (d >= need) return [OK, `기준 ${mm(need, u)} 이상${why} — 실제 ${mm(d, u)} ✓`];
      let msg = `기준 ${mm(need, u)} 이상${why} — 실제 ${mm(d, u)} ✗ (${mm(round(need - d, 2), u)} 부족)`;
      if (!alt && a.alt_if && a.alt_min < a.min)
        msg += a.alt_min ? `. ${a.alt_why} 시 ${mm(a.alt_min, u)} 이상이면 됩니다.` : `. ${a.alt_why} 시 예외.`;
      return [BAD, msg];
    }
    function judge(t, item, fac, v) {
      const a = item.auto;
      if (item.info) return [INFO, item.info_note ?? '거리 기준을 못 맞출 때 쓸 수 있는 예외. 한국가스안전공사와 협의가 필요합니다.', null];
      if (!a) return [CHECK, '', null];
      if (a.na_if && v[a.na_if]) return [NA, a.na_why ?? '해당 없음.', null];
      switch (a.type) {
        case 'protection': return protection(t, fac, v, a);
        case 'boundary_prot1': return [...boundaryProt1(t, fac, v, a), null];
        case 'wall_or_distance': return [...wallOrDistance(v, a), null];
        case 'wall_indoor': return [...wallIndoor(v, a), null];
        case 'range': return [...range(v, a), null];
        case 'wall30': return [...wall30(v), null];
        case 'other': return [...other(v), null];
        case 'min': return [...minRule(a, v), null];
        case 'max': {
          const n = v[a.input];
          if (n === undefined) return [CHECK, '대수를 넣어 주세요.', null];
          return [n <= a.max ? OK : BAD, `기준 ${a.max}대 이하 — 계획 ${g(n)}대`, null];
        }
        case 'flag': {
          const f = v[a.input];
          if (f === undefined) return [CHECK, '처음 설치하거나 위치·수량·용량을 늘리면 대상입니다.', null];
          return f ? [CHECK, '대상입니다 — 평가를 받고 결과대로 보완해야 합니다.', null] : [NA, '신규·증설이 아님.', null];
        }
      }
      return [CHECK, '', null];
    }
    function buildSheet(fac, vals, tid = 'gas_annex5_station', marks = null) {
      marks = marks && typeof marks === 'object' && !Array.isArray(marks) ? marks : {};
      const t = template(tid);
      if (!Object.hasOwn(t.facilities, fac)) throw new ToolError(`시설 종류는 ${Object.keys(t.facilities).join(', ')} 중 하나입니다`);
      const v = clean(t, vals), F = t.facilities[fac];
      const rows = [], count = {};
      for (const it of t.items) {
        if (it.only && it.only !== fac) continue;
        let [verdict, note, calc] = judge(t, it, fac, v);
        const manual = marks[it.id];
        if (verdict === CHECK && !it.auto && [OK, BAD, NA].includes(manual)) [verdict, note] = [manual, '사용자 확인'];
        count[verdict] = (count[verdict] || 0) + 1;
        const quote = (it.quotes || {})[fac] || (fac === '저장식' ? it.quote_s : null) || it.quote;
        rows.push({
          id: it.id, group: it.group, title: it.title, quote,
          ref: `${stripBr(t.annex)} ${it.ref[fac]}`,
          kgs: it.kgs && F.kgs ? `${F.kgs} ${it.kgs}` : '',
          mid: (it.mid || []).includes(fac),
          auto: !!it.auto,
          verdict, note, calc,
        });
      }
      return {id: t.id, title: t.title, facility: fac, facility_desc: F.desc, law: t.law, annex: t.annex,
        annex_title: t.annex_title, kgs_code: F.kgs ?? '', scope: t.scope ?? '', inputs: v, rows, count, made: day()};
    }
    function sheetBlocks(sheet, company = '') {
      const c = sheet.count;
      const names = Object.fromEntries(template(sheet.id).inputs.map(i => [i.key, i.q]));
      const inputs = Object.entries(sheet.inputs).map(([k, v]) =>
        [cut((names[k] ?? k).split(' (')[0], 28), v === true ? '예' : v === false ? '아니오' : g(v)]);
      const grid = [['번호', '점검 항목', '기준 (별표 원문)', '근거', '판정·메모']];
      sheet.rows.forEach((r, i) => {
        const basis = r.ref + (r.kgs ? `\n${r.kgs}` : '') + (r.mid ? '\n[중간검사]' : '');
        let memo = r.verdict + (r.note ? ` — ${r.note}` : '');
        if (r.verdict === CHECK && !r.auto) memo = '□ 적합  □ 부적합  □ 해당 없음';
        grid.push([String(i + 1), `[${r.group}] ${r.title}`, r.quote, basis, memo]);
      });
      const blocks = [
        ['title', `${sheet.title} (${sheet.facility})`],
        ['para', `${sheet.law} ${sheet.annex} ${sheet.annex_title} 중 시설기준 항목을 `
          + '점검표로 옮긴 것입니다. 기준 글은 별표 원문 그대로이며, 세부 수치는 '
          + (sheet.kgs_code ? `${sheet.kgs_code} 를` : 'KGS Code 를') + ' 함께 확인하세요.'
          + (sheet.scope ? ` ${sheet.scope}` : '')],
        ['table', [['사업장', company || '[직접 입력]'], ['시설 종류', `${sheet.facility} — ${sheet.facility_desc}`],
          ['작성일', sheet.made],
          ['판정 요약', [OK, BAD, CHECK, NA, INFO].filter(k => c[k]).map(k => `${k} ${c[k]}`).join(' · ')]]],
      ];
      if (inputs.length) blocks.push(['heading', '입력한 시설 정보'], ['table', inputs]);
      blocks.push(
        ['heading', '점검 항목'],
        ['grid', {rows: grid, widths: [2600, 8200, 15000, 7400, 9320]}],
        ['para', '※ 완성검사는 시설기준 전 항목이 대상입니다. '
          + (sheet.rows.some(r => r.mid) ? `[중간검사] 표시는 ${stripBr(sheet.annex)} 검사기준 표의 중간검사 항목입니다. ` : '')
          + '자동 판정은 입력값 기준의 참고용이며 법적 효력이 없습니다. 최종 판단은 한국가스안전공사·관할 관청에 확인하세요.'],
      );
      return blocks;
    }

    // ========================================================== 안전관리규정 (safety_rules)
    const NEED = '[직접 입력]';
    const INFO_KEYS = D.rule_info_keys;
    const rtemplate = tid => {
      if (!/^[a-z0-9_]+$/.test(tid || '') || !D.rules[tid]) throw new ToolError(`'${tid}'`);
      return D.rules[tid];
    };
    const dot = s => s.replace(/[ᆞㆍ]/g, '·');
    function short(s) {
      s = s.replace(/\(.*?\)/g, '');
      s = pyStrip(s).replace(/(에 관한 사항|에 관한 |에 대한 |의 관리)$/, '');
      s = pyStrip(s.replace(/\s*에\s*관한\s*사항$/, ''));
      if (cp(s).length > 26) {
        const head = cut(s, 26), i = head.lastIndexOf(' ');
        s = (i >= 0 ? head.slice(0, i) : head).replace(/[ ,·및]+$/, '') + '…';
      }
      return s;
    }
    const fmt = (tpl, kw) => tpl.replace(/\{\{|\}\}|\{(\w+)\}/g, (m, k) => m === '{{' ? '{' : m === '}}' ? '}' : (k in kw ? kw[k] : m));
    function buildRules(tid, kind, flags = {}, info = {}) {
      const t = rtemplate(tid);
      if (!Object.hasOwn(t.kinds, kind)) throw new ToolError(`사업 종류는 ${Object.keys(t.kinds).join(', ')} 중 하나입니다`);
      const fl = new Set(Object.entries(flags || {}).filter(([k, v]) => v && Object.hasOwn(t.flags, k)).map(([k]) => k));
      const inf = {};
      for (const [k, v] of Object.entries(info || {})) {
        const s = pyStrip(pystr(v));
        if (Object.hasOwn(INFO_KEYS, k) && s) inf[k] = cut(s, 60);
      }
      const annex = stripBr(t.annex);
      const chapters = [];
      let art = 0;
      const articles = ch => {
        const out = [];
        if (ch.draft) {
          art += 1;
          out.push({no: art, title: short(dot(ch.title)), text: fmt(ch.draft, {act: t.act, article: t.article,
            company: inf.company ?? NEED, facility: inf.facility ?? NEED})});
          return out;
        }
        for (const s of (ch.subs.length ? ch.subs : [ch.title])) { art += 1; out.push({no: art, title: short(dot(s)), text: NEED}); }
        return out;
      };
      const every = Object.keys(t.kinds).length;
      for (const ch of t.chapters) {
        const kinds = ch.kinds ?? null;
        let status, why;
        if (kinds !== null && !kinds.includes(kind)) [status, why] = ['제외', `기재사항 표에서 '${kind}' 칸에 ○가 없음 (해당: ${kinds.join(', ')})`];
        else if (ch.only === 'special') {
          status = fl.has('special') ? '필수' : '제외';
          why = '기재사항 표: 고압가스특정제조자만 해당' + (status === '필수' ? '' : ' — 특정제조자가 아니라 뺌');
        } else if (kinds === null || kinds.length >= every) [status, why] = ['필수', '모든 사업 종류에 포함'];
        else [status, why] = ['필수', `기재사항 표에서 '${kind}' 칸에 ○ (해당: ${kinds.join(', ')})`];
        const row = {id: ch.id, title: dot(ch.title), ref: `${annex} ${ch.ref}` + (ch.no ? ` · 기재사항 표 ${ch.no}번` : ''),
          status, why, note: ch.note ?? '', subs: ch.subs.map(dot), table: ch.table ?? null, articles: []};
        if (status !== '제외') row.articles = articles(ch);
        chapters.push(row);
      }
      if (fl.has('comprehensive')) {
        for (const ch of t.comprehensive) {
          const row = {id: ch.id, title: dot(ch.title), ref: `${annex} ${ch.ref}`, status: '필수',
            why: '종합적 안전관리대상자 항목', note: '', subs: ch.subs.map(dot), table: null};
          row.articles = articles(ch);
          chapters.push(row);
        }
      }
      let n = 0;
      for (const ch of chapters) if (ch.status !== '제외') { n += 1; ch.chapter = n; }
      return {id: t.id, title: t.title, act: t.act, article: t.article, law: t.law, annex: t.annex,
        annex_title: t.annex_title, detail: t.detail, kind, kind_desc: t.kinds[kind], flags: [...fl].sort(), info: inf,
        chapters, articles: art,
        count: Object.fromEntries(['필수', '제외'].map(s => [s, chapters.filter(c => c.status === s).length])), made: day()};
    }
    function rulesBlocks(doc) {
      const info = doc.info, live = doc.chapters.filter(c => c.status !== '제외');
      const blocks = [
        ['title', pyStrip(`${info.company ?? ''} 안전관리규정 (초안)`)],
        ['para', `「${doc.act}」 ${doc.article}에 따른 안전관리규정의 뼈대입니다. 장 제목과 '작성할 내용'은 `
          + `${doc.law} ${doc.annex} ${doc.annex_title} 원문 그대로이고, 조문 본문의 [직접 입력]은 `
          + '사업장 실정에 맞게 채워야 합니다.'],
        ['table', Object.keys(INFO_KEYS).map(k => [INFO_KEYS[k], info[k] || (k === 'date' ? doc.made : NEED)])
          .concat([['사업 종류', doc.kind_desc]])],
        ['heading', '목차'],
        ['para', live.map(c => `제${c.chapter}장 ${c.title}`).join('  ')],
      ];
      for (const c of live) {
        blocks.push(['heading', `제${c.chapter}장 ${c.title}`], ['para', `근거: ${c.ref}`]);
        if (c.status === '확인') blocks.push(['para', `※ ${c.why}`]);
        if (c.note) blocks.push(['para', `※ ${c.note}`]);
        if (c.subs.length) blocks.push(['para', '작성할 내용 (별표 원문): ' + c.subs.join(' / ')]);
        for (const a of c.articles) blocks.push(['para', `제${a.no}조(${a.title}) ${a.text}`]);
        if (c.table === 'managers')
          blocks.push(['grid', {rows: [['구분', '성명', '자격', '선임일', '직무']].concat(Array.from({length: 4}, () => [NEED, '', '', '', ''])),
            widths: [9000, 7000, 9000, 7000, 10520]}]);
      }
      const grid = [['별표 항목', '이 초안', '비고']];
      for (const c of doc.chapters)
        grid.push([`${c.ref}\n${c.title}`, c.status !== '제외' ? `제${c.chapter}장` : '제외', c.status !== '필수' ? c.why : '']);
      blocks.push(['heading', '포함 항목 대조표'], ['grid', {rows: grid, widths: [18000, 6000, 18520]}],
        ['para', '※ ' + doc.detail],
        ['para', '※ 이 문서는 작성 보조용 초안이며 법적 효력이 없습니다. 제출 전 관할 관청·한국가스안전공사 기준과 대조하세요.']);
      return blocks;
    }

    // ========================================================== 저장능력 (storage_calc)
    const Q = D.storage.quotes, REF = D.storage.ref;
    const snum = v => {
      if (v === null || v === undefined || typeof v === 'boolean') return null;
      const s = pyStrip(String(v).replace(/,/g, ''));
      if (!s || !/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(s)) return null;
      const x = Number(s);
      return x >= 0 ? x : null;
    };
    function calc(items) {
      const rows = [];
      let tq = 0, tw = 0;
      (items || []).forEach((it, i) => {
        if (!it || typeof it !== 'object' || Array.isArray(it)) return;
        const kind = it.kind === 'liq' ? 'liq' : 'comp';
        const n = snum(it.n) || 1;
        const name = cut(it.name ? pystr(it.name) : `설비 ${i + 1}`, 30);
        if (kind === 'comp') {
          const p = snum(it.p), v = snum(it.v);
          if (p === null || v === null) { rows.push({name, kind, ok: false, why: '압력·내용적을 넣어 주세요'}); return; }
          const q1 = (10 * p + 1) * v, q = q1 * n;
          tq += q;
          rows.push({name, kind, ok: true, p, v, n, each: round(q1, 3), value: round(q, 3), unit: '㎥',
            step: `Q = (10×${g(p)} + 1) × ${g(v)} = ${comma3(q1)}㎥` + (n !== 1 ? ` × ${g(n)}개 = ${comma3(q)}㎥` : '')});
        } else {
          const d = snum(it.d), v = snum(it.v);
          if (d === null || v === null) { rows.push({name, kind, ok: false, why: '비중·내용적(L)을 넣어 주세요'}); return; }
          const w1 = 0.9 * d * v, w = w1 * n;
          tw += w;
          rows.push({name, kind, ok: true, d, v, n, each: round(w1, 3), value: round(w, 3), unit: '㎏',
            step: `W = 0.9 × ${g(d)} × ${g(v)} = ${comma3(w1)}㎏` + (n !== 1 ? ` × ${g(n)}개 = ${comma3(w)}㎏` : '')});
        }
      });
      const mixed = tq > 0 && tw > 0;
      const combined = mixed ? tq + tw / 10 : (tq ? tq : null);
      return {rows, total_m3: round(tq, 3), total_kg: round(tw, 3),
        combined_m3: combined !== null ? round(combined, 3) : null, mixed, quotes: Q, ref: REF};
    }
    function storageBlocks(res, company = '', note = '') {
      const grid = [['설비', '종류', '입력값', '계산', '저장능력']];
      for (const r of res.rows) {
        const kn = r.kind === 'comp' ? '압축가스' : '액화가스';
        if (!r.ok) { grid.push([r.name, kn, '-', r.why, '-']); continue; }
        const inp = (r.kind === 'comp' ? `P ${g(r.p)}㎫ · V₁ ${g(r.v)}㎥` : `d ${g(r.d)}㎏/L · V₂ ${g(r.v)}L`)
          + (r.n !== 1 ? ` · ${g(r.n)}개` : '');
        grid.push([r.name, kn, inp, r.step, `${comma3(r.value)}${r.unit}`]);
      }
      const total = [];
      if (res.total_m3) total.push(['압축가스 합계', `${comma3(res.total_m3)}㎥`]);
      if (res.total_kg) total.push(['액화가스 합계', `${comma3(res.total_kg)}㎏`]);
      if (res.mixed) total.push(['합산 저장능력', `${comma3(res.combined_m3)}㎥ (액화가스 10㎏ = 압축가스 1㎥로 환산)`]);
      const blocks = [
        ['title', '저장능력 계산서'],
        ['table', [['사업장', company || '[직접 입력]'], ['작성일', day()], ['근거', REF + ' (저장능력 산정기준)']]],
        ['heading', '계산식 (별표 원문)'],
        ['para', `${Q.comp} — ${Q.comp_f}`],
        ['para', `${Q.liq} — ${Q.liq_f}`],
        ['para', ['Q', 'P', 'V1', 'W', 'd', 'V2'].map(k => Q[k]).join(' / ')],
        ['heading', '설비별 계산'],
        ['grid', {rows: grid, widths: [7000, 5000, 10000, 13000, 7520]}],
        ['heading', '합계'],
        ['table', total.length ? total : [['합계', '계산된 설비 없음']]],
        ['para', `※ 합산 기준: ${Q.sum} 가. ${Q.sum_a} 나. 가목의 경우를 제외한 경우로서 ${Q.sum_b} ${Q.mix}`],
      ];
      if (note) blocks.push(['para', '※ ' + note]);
      blocks.push(['para', '※ 입력값(최고충전압력·내용적)은 설비 명판·설계서 값으로 확인하세요. 이 계산서는 작성 보조용이며 법적 효력이 없습니다.']);
      return blocks;
    }

    // ========================================================== 제출 꾸러미 (package)
    // deps: {permitVals, permitPdf(fid, vals) → bytes, permitHwpx(fid, vals) → bytes, hwpx(blocks, title) → bytes, zip(files) → bytes}
    async function buildPackage(req, deps) {
      const p = req.permit && typeof req.permit === 'object' ? req.permit : {};
      const fid = p.id;
      if (typeof fid !== 'string' || !D.forms[fid]) throw new ToolError('신청서 종류(id)가 없습니다');
      const f = D.forms[fid];
      const vals = deps.permitVals(p.fields);
      for (const t of f.fields) if (t.length > 5 && t[5] && !pyStrip(vals[t[0]] || '')) vals[t[0]] = t[5];
      const company = cut(pyStrip(vals.company || (req.company ? pystr(req.company) : '')), 40);
      const files = [], notes = [], summary = {};

      const fm = p.fmt || 'both';
      if (fm === 'pdf' || fm === 'both') {
        try { files.push(['01_신청서.pdf', await deps.permitPdf(fid, Object.assign({}, vals)), `${f.title} 신청서 (공식 서식 PDF에 채움)`]); }
        catch (e) { notes.push(`공식 서식 PDF 를 받지 못해 신청서 PDF 를 넣지 못했습니다(${(e && e.message) || e}). HWPX 정리본을 참고하세요.`); }
      }
      if (fm === 'hwpx' || fm === 'both' || !files.some(([n]) => n.endsWith('.pdf')))
        files.push(['01_신청서_정리본.hwpx', await deps.permitHwpx(fid, Object.assign({}, vals)), `${f.title} 신청서 항목 정리본 (한글)`]);
      const empty = f.fields.filter(t => !pyStrip(vals[t[0]] || '')).map(t => t[2].split(' (')[0]);

      const ck = req.checklist;
      if (ck && typeof ck === 'object' && ck.id) {
        const sheet = buildSheet(pystr(ck.facility || ''), ck.inputs || {}, pystr(ck.id), ck.marks);
        files.push([`02_자체점검표_${sheet.facility}.hwpx`, await deps.hwpx(sheetBlocks(sheet, company), sheet.title),
          `${sheet.title} (${sheet.facility}) — ${sheet.law} ${stripBr(sheet.annex)}`]);
        summary.checklist = {title: sheet.title, count: sheet.count,
          bad: sheet.rows.filter(r => r.verdict === BAD).map(r => `${r.title} — ${r.note}`),
          todo: sheet.rows.filter(r => r.verdict === CHECK).length};
      }
      const ru = req.rules;
      if (ru && typeof ru === 'object' && ru.id) {
        const info = Object.assign({}, ru.info || {});
        if (!('company' in info)) info.company = company;
        const doc = buildRules(pystr(ru.id), pystr(ru.kind || ''), ru.flags || {}, info);
        files.push(['03_안전관리규정_초안.hwpx', await deps.hwpx(rulesBlocks(doc), doc.title),
          `${doc.title} 초안 — ${doc.law} ${stripBr(doc.annex)}`]);
        summary.rules = {title: doc.title, count: doc.count};
      }
      const st = req.storage;
      if (st && typeof st === 'object' && Array.isArray(st.items) && st.items.length) {
        const res = calc(st.items);
        if (res.rows.some(r => r.ok)) {
          files.push(['04_저장능력_계산서.hwpx', await deps.hwpx(storageBlocks(res, company), '저장능력 계산서'), `저장능력 계산서 — ${REF}`]);
          summary.storage = res.combined_m3;
        }
      }
      const docsRows = f.docs.length ? f.docs.map(d => [d, '직접 준비']) : [['없음', '-']];
      const blocks = [
        ['title', `${f.title} 제출 꾸러미`],
        ['table', [['사업장', company || '[직접 입력]'], ['신청서', `${f.law} 별지 제${f.no}호서식 — ${f.title}`],
          ['접수 기관', f.who], ['처리 기간', f.days], ['수수료', f.fee], ['만든 날', day()]]],
      ];
      if (f.before) blocks.push(['para', '먼저 할 일: ' + f.before]);
      blocks.push(['heading', '서식에 적힌 첨부서류'], ['table', docsRows],
        ['para', '※ 첨부서류는 서식 본문 그대로입니다. 이 꾸러미에는 만들어 넣지 않았으니 직접 준비하세요.']);
      if (empty.length) blocks.push(['heading', `신청서 빈칸 ${empty.length}곳`], ['para', empty.join(' · ')]);
      if (summary.checklist) {
        const c = summary.checklist;
        blocks.push(['heading', '자체점검 결과'],
          ['para', Object.entries(c.count).map(([k, v]) => `${k} ${v}`).join(' · ') + ` — 확인 필요 ${c.todo}행은 현장·도면으로 확인하세요.`]);
        if (c.bad.length) blocks.push(['table', c.bad.map((b, i) => [`보완 ${i + 1}`, cut(b, 120)])]);
      }
      blocks.push(['heading', '이 꾸러미에 든 파일'],
        ['grid', {rows: [['파일', '내용']].concat(files.map(([n, , d]) => [n, d])), widths: [14000, 28520]}]);
      for (const n of notes) blocks.push(['para', '※ ' + n]);
      if (f.after) blocks.push(['para', '다음 할 일: ' + f.after]);
      blocks.push(['para', '※ 이 꾸러미는 작성 보조용입니다. 자동 판정·초안은 법적 효력이 없으니 제출 전 접수 기관 기준과 대조하세요.']);
      files.unshift(['00_표지_제출체크리스트.hwpx', await deps.hwpx(blocks, '제출 꾸러미 표지'), '표지']);
      const name = `${f.title}_제출꾸러미` + (company ? `_${company}` : '') + '.zip';
      Object.assign(summary, {files: files.map(([n]) => n), empty, notes});
      return {data: await deps.zip(files), name, summary, cover: blocks};
    }

    return {buildSheet, sheetBlocks, buildRules, rulesBlocks, calc, storageBlocks, buildPackage, ToolError};
  }

  const api = {make, g, round, comma3, ToolError};
  if (typeof module === 'object' && module.exports) { module.exports = api; return; }

  // ------------------------------------------------------------ 브라우저: fetch 가로채기
  const W = root;
  const prevFetch = W.fetch.bind(W);
  let toolsP = null;
  const tools = () => toolsP || (toolsP = prevFetch('/docs/tools.json').then(r => {
    if (!r.ok) throw new Error('도구 자료를 받지 못했습니다');
    return r.json();
  }).then(D => ({D, T: make(D)})).catch(e => { toolsP = null; throw e; }));
  const json = (status, obj) => new Response(JSON.stringify(obj), {status, headers: {'Content-Type': 'application/json; charset=utf-8'}});
  const quote = s => encodeURIComponent(s).replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase());
  const file = (data, name) => new Response(data, {status: 200, headers: {
    'Content-Type': name.endsWith('.zip') ? 'application/zip' : 'application/octet-stream',
    'Content-Disposition': `attachment; filename*=UTF-8''${quote(name)}`}});
  const docs = () => {
    if (!W.__cfDocs) throw new Error('문서 도구(cf-shim.js)가 없습니다');
    return W.__cfDocs;
  };
  const hwpx = (blocks, title) => docs().makeHwpx(blocks, title);
  const isObj = x => x && typeof x === 'object' && !Array.isArray(x);
  const GETS = ['/api/checklist', '/api/rules', '/api/package'];
  const POSTS = ['/api/checklist', '/api/rules', '/api/storage', '/api/package'];

  async function handle(path, method, req) {
    const {D, T} = await tools();
    if (method === 'GET') return json(200, path === '/api/checklist' ? D.checklist_catalog : path === '/api/rules' ? D.rules_catalog : D.package_catalog);
    try {
      if (path === '/api/checklist') {
        const sheet = T.buildSheet(pystr(req.facility || ''), req.inputs || {}, pystr(req.id || 'gas_annex5_station'), req.marks);
        if (req.fmt !== 'hwpx') return json(200, sheet);
        return file(await hwpx(T.sheetBlocks(sheet, cut(pystr(req.company || ''), 40)), sheet.title), `${sheet.title}_${sheet.facility}.hwpx`);
      }
      if (path === '/api/rules') {
        const doc = T.buildRules(pystr(req.id || ''), pystr(req.kind || ''), isObj(req.flags) ? req.flags : {}, isObj(req.info) ? req.info : {});
        if (req.fmt !== 'hwpx') return json(200, doc);
        return file(await hwpx(T.rulesBlocks(doc), doc.title), `안전관리규정_초안_${doc.info.company || doc.kind}.hwpx`);
      }
      if (path === '/api/storage') {
        const res = T.calc((Array.isArray(req.items) ? req.items : []).slice(0, 50));
        if (req.fmt !== 'hwpx') return json(200, res);
        return file(await hwpx(T.storageBlocks(res, cut(pystr(req.company || ''), 40)), '저장능력 계산서'), '저장능력_계산서.hwpx');
      }
      // /api/package
      const C = docs();
      const out = await T.buildPackage(req, {
        permitVals: C.permitVals,
        permitPdf: async (fid, vals) => (await C.permitFill(fid, vals, 'black'))[0],
        permitHwpx: async (fid, vals) => (await C.permitHwpx(fid, vals))[0],
        hwpx,
        zip: async files => {
          const JSZip = await C.jszip(), z = new JSZip();
          for (const [n, data] of files) z.file(n, data);
          return z.generateAsync({type: 'uint8array', compression: 'DEFLATE'});
        },
      });
      return file(out.data, out.name);
    } catch (e) {
      const what = path === '/api/checklist' ? '점검표를' : path === '/api/rules' ? '초안을' : path === '/api/package' ? '꾸러미를' : '계산서를';
      return json(e instanceof ToolError ? 400 : 502, {error: `${what} 만들 수 없습니다: ${(e && e.message) || e}`});
    }
  }

  W.fetch = async function (input, init) {
    let url, method;
    try {
      url = new URL(typeof input === 'string' || input instanceof URL ? String(input) : input.url, location.href);
      method = ((init && init.method) || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    } catch (e) { return prevFetch(input, init); }
    const p = url.pathname;
    if (url.origin !== location.origin || !(method === 'GET' ? GETS : method === 'POST' ? POSTS : []).includes(p)) return prevFetch(input, init);
    let req = {};
    if (method === 'POST') {
      const body = init && init.body !== undefined ? init.body : (input instanceof Request ? await input.text() : '');
      try {
        req = JSON.parse(typeof body === 'string' ? body : new TextDecoder().decode(body));
        if (!isObj(req)) throw 0;
      } catch (e) { return json(400, {error: '요청 형식이 올바르지 않습니다(UTF-8 JSON)'}); }
    }
    try { return await handle(p, method, req); }
    catch (e) { return json(502, {error: (e && e.message) || String(e)}); }
  };
  W.__cfTools = api;
})(typeof window !== 'undefined' ? window : this);
