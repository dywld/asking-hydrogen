/* 시설 배치도(초안) 만들기: 3D 부지 검토(site3d)가 남긴 배치로 A3 PDF 와 CAD 파일(DXF)을 만든다.
 *
 * 입력은 site3d.html 의 planSpec() 이 localStorage 'site3dPlan' 에 남기는 값(부지 좌표, 단위 m, x 오른쪽 y 위쪽).
 * site3d.html(배치도 받기)과 package.html(제출 꾸러미 05번 첨부)이 같이 쓴다.
 * PDF 는 cf-shim.js 가 받아 두는 pdf-lib·글꼴(window.__cfDocs.pdfKit)로 그린다. DXF 는 AutoCAD R12 글(LINE·TEXT)이라
 * 오토캐드·캐디안·LibreCAD 어디서나 열린다. 한글은 \U+XXXX 로 적는다.
 */
(function (W) {
  'use strict';
  const COL = {process: [253, 230, 138], compressed: [253, 186, 116], storage: [147, 197, 253], charger: [134, 239, 172], building: [243, 244, 246], other: [226, 232, 240]};
  const TN = {process: '처리설비', compressed: '압축가스설비', storage: '저장설비', charger: '충전설비', building: '건축물', other: '기타'};
  const SCALES = [100, 150, 200, 250, 300, 400, 500, 600, 800, 1000];
  const AREA = {x0: 14, y0: 14, x1: 298, y1: 283};            // 도면 칸(mm, A3 가로 420×297, 왼쪽 아래 원점)
  const GRN = [3, 150, 92], RED = [220, 50, 64], BLUE = [37, 110, 235], INK = [25, 31, 40], SUB = [90, 98, 110];
  const f1 = v => (Math.round(v * 10) / 10).toFixed(1);

  // ------------------------------------------------------------ 도면 요소(부지 좌표, m)
  function roundRect(x0, y0, x1, y1, R) {
    const ring = [];
    for (const [cx, cy, a0] of [[x1, y1, 0], [x0, y1, 90], [x0, y0, 180], [x1, y0, 270]])
      for (let k = 0; k <= 12; k++) { const a = (a0 + k * 7.5) * Math.PI / 180; ring.push([cx + R * Math.cos(a), cy + R * Math.sin(a)]); }
    return ring;
  }
  const bbox = its => [Math.min(...its.map(x => x.cx - x.w / 2)), Math.min(...its.map(x => x.cy - x.d / 2)), Math.max(...its.map(x => x.cx + x.w / 2)), Math.max(...its.map(x => x.cy + x.d / 2))];
  const rect = it => [[it.cx - it.w / 2, it.cy - it.d / 2], [it.cx + it.w / 2, it.cy - it.d / 2], [it.cx + it.w / 2, it.cy + it.d / 2], [it.cx - it.w / 2, it.cy + it.d / 2]];
  const cen = pts => pts.reduce((s, p) => [s[0] + p[0] / pts.length, s[1] + p[1] / pts.length], [0, 0]);
  const inside = (p, poly) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) c = !c; } return c; };
  const parea = P => Math.abs(P.reduce((t, p, i) => { const r = P[(i + 1) % P.length]; return t + p[0] * r[1] - r[0] * p[1]; }, 0)) / 2;
  function insetPoly(P, q) {          // site3d.html 의 insetPoly 와 같다(다각형 q 만큼 안쪽)
    const n = P.length, sg = Math.sign(P.reduce((t, p, i) => { const r = P[(i + 1) % n]; return t + p[0] * r[1] - r[0] * p[1]; }, 0)) || 1, Ls = [];
    for (let i = 0; i < n; i++) { const a = P[i], b = P[(i + 1) % n], ex = b[0] - a[0], ey = b[1] - a[1], l = Math.hypot(ex, ey) || 1, nx = -ey / l * sg * q, ny = ex / l * sg * q; Ls.push([[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny]]); }
    const out = [];
    for (let i = 0; i < n; i++) {
      const [p1, p2] = Ls[(i - 1 + n) % n], [p3, p4] = Ls[i], d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
      if (Math.abs(d) < 1e-9) { out.push(p3); continue; }
      const t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d, x = [p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t];
      if (Math.hypot(x[0] - P[i][0], x[1] - P[i][1]) > Math.abs(q) * 4) out.push(p2, p3); else out.push(x);
    }
    return out.length >= 3 && parea(out) > 4 && out.every(p => inside(p, P)) ? out : null;
  }

  function scaleOf(sp) {
    const need = (sp.site.w + 34), needY = (sp.site.d + 34);
    const den = SCALES.find(d => need * 1000 / d <= AREA.x1 - AREA.x0 && needY * 1000 / d <= AREA.y1 - AREA.y0) || SCALES.at(-1);
    return {den, k: 1000 / den, ox: (AREA.x0 + AREA.x1) / 2, oy: (AREA.y0 + AREA.y1) / 2 + 4};
  }
  // 보이는 범위(부지 좌표)
  const view = G => ({x0: (AREA.x0 - G.ox) / G.k, x1: (AREA.x1 - G.ox) / G.k, y0: (AREA.y0 - G.oy) / G.k, y1: (AREA.y1 - G.oy) / G.k});
  function clipSeg(a, b, v, m) {     // 선분을 보이는 범위(안쪽 m 만큼)로 자른다(Liang-Barsky)
    let t0 = 0, t1 = 1; const dx = b[0] - a[0], dy = b[1] - a[1];
    for (const [p, q] of [[-dx, a[0] - v.x0 - m], [dx, v.x1 - m - a[0]], [-dy, a[1] - v.y0 - m], [dy, v.y1 - m - a[1]]]) {
      if (p === 0) { if (q < 0) return null; continue; }
      const r = q / p; if (p < 0) { if (r > t1) return null; if (r > t0) t0 = r; } else { if (r < t0) return null; if (r < t1) t1 = r; }
    }
    return [[a[0] + dx * t0, a[1] + dy * t0], [a[0] + dx * t1, a[1] + dy * t1], t1 < 1];
  }

  function build(sp) {
    const G = scaleOf(sp), V = view(G), P = [], k = G.k, mm = v => v / k;      // mm -> m
    const pl = (pts, o) => P.push({t: 'pl', pts, ...o});
    const tx = (at, s, o) => P.push({t: 'tx', at, s: String(s), size: 2.4, al: 'c', color: INK, ...o});
    // 글자 상자(부지 좌표 m): 한글은 글자 크기만큼, 영문·숫자는 반 남짓 넓다고 어림한다
    const OB = [], estW = (s, size) => [...String(s)].reduce((w, ch) => w + (ch.charCodeAt(0) > 0x2e00 ? 0.98 : 0.56), 0) * size;
    const tbox = (at, s, o) => {
      const w = mm(estW(s, o.size || 2.4)) + mm(1), h = mm((o.size || 2.4) * 1.25), r = (o.rot || 0) * Math.PI / 180, ca = Math.cos(r), sa = Math.sin(r);
      const x0 = o.al === 'l' ? 0 : o.al === 'r' ? -w : -w / 2, y0 = o.vc ? -h / 2 : -h * 0.2, base = [at[0], at[1] + mm(o.dy || 0)];
      const cs = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]].map(([x, y]) => [base[0] + x * ca - y * sa, base[1] + x * sa + y * ca]);
      return [Math.min(...cs.map(c => c[0])), Math.min(...cs.map(c => c[1])), Math.max(...cs.map(c => c[0])), Math.max(...cs.map(c => c[1]))];
    };
    const hit = b => OB.some(q => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1]);
    const ptx = (cands, s, o) => {           // 후보 자리 중 첫 빈자리(없으면 첫 후보)
      let pick = cands[0], bb = tbox(cands[0], s, o);
      for (const c of cands) { const b = tbox(c, s, o); if (!hit(b) && c[0] > V.x0 && c[0] < V.x1 && c[1] > V.y0 && c[1] < V.y1) { pick = c; bb = b; break; } }
      OB.push(bb); tx(pick, s, o);
    };
    const W2 = sp.site.w / 2, D2 = sp.site.d / 2;
    // 주변: 학교 등 부지, 도로, 철도, 건물
    for (const z of sp.zones || []) pl(z.pts, {close: true, fill: [252, 232, 232], stroke: [228, 170, 170], lw: 0.15, layer: 'PROTECT'});
    const named = {};
    for (const r of sp.roads || []) {
      pl(r.pts, {stroke: [176, 183, 192], lw: r.w * k + 0.35, cap: 'round', layer: 'ROAD', road: r.w});
      if (r.name && r.law) for (let i = 0; i + 1 < r.pts.length; i++) {
        const c = clipSeg(r.pts[i], r.pts[i + 1], V, mm(10)); if (!c) continue;
        const L = Math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]); if (!named[r.name] || L > named[r.name].L) named[r.name] = {L, c, w: r.w};
      }
    }
    for (const r of sp.roads || []) pl(r.pts, {stroke: r.law ? [236, 239, 242] : [244, 246, 248], lw: r.w * k, cap: 'round', layer: 'ROAD_FILL', skipDxf: true});
    for (const [n, o] of Object.entries(named)) {
      if (o.L * k < 30) continue;
      let ang = Math.atan2(o.c[1][1] - o.c[0][1], o.c[1][0] - o.c[0][0]) * 180 / Math.PI; if (ang > 90) ang -= 180; if (ang < -90) ang += 180;
      tx([(o.c[0][0] + o.c[1][0]) / 2, (o.c[0][1] + o.c[1][1]) / 2], n, {size: 2.6, color: [120, 128, 138], rot: ang, vc: true, layer: 'TEXT'});
    }
    for (const r of sp.rails || []) pl(r.pts, {stroke: [140, 146, 156], lw: 0.6, dash: [3, 1.5], layer: 'RAIL'});
    const prot = [];
    for (const b of sp.blds || []) {
      const fill = b.cls === 1 ? [253, 226, 226] : b.cls === 2 ? [254, 241, 241] : [255, 255, 255], stroke = b.cls ? [214, 120, 128] : [150, 158, 168];
      pl(b.pts, {close: true, fill, stroke, lw: 0.2, layer: b.cls ? 'PROTECT' : 'BLDG'});
      if (b.cls) { const c = cen(b.pts); prot.push({b, c, d: Math.hypot(c[0], c[1])}); }
    }
    for (const {b, c} of prot.sort((a, b) => a.d - b.d).slice(0, 5)) {
      if (c[0] < V.x0 + mm(18) || c[0] > V.x1 - mm(18) || c[1] < V.y0 + mm(6) || c[1] > V.y1 - mm(6) || (Math.abs(c[0]) < W2 + 3 && Math.abs(c[1]) < D2 + 3)) continue;
      tx(c, `제${b.cls}종 보호시설`, {size: 2.1, color: [180, 60, 70], dy: 1.4, layer: 'TEXT'});
      tx(c, `${b.use || ''}${b.lv ? ' ' + b.lv + '층' : ''}`, {size: 1.9, color: [150, 90, 96], dy: -1.4, layer: 'TEXT'});
    }
    // 지적 경계(필지): 연한 선, 지번은 아래에서 빈자리에만
    for (const q of sp.parcels || []) pl(q.pts, {close: true, stroke: q.road ? [214, 219, 225] : [176, 184, 195], lw: 0.15, layer: 'PARCEL'});
    // 부지(사업소 경계): 실제 필지면 그 모양, 아니면 예시 직사각형
    const SP = sp.site.poly && sp.site.poly.length >= 3 ? sp.site.poly : null;
    const S4 = SP || [[-W2, -D2], [W2, -D2], [W2, D2], [-W2, D2]];
    pl(S4, {close: true, fill: [241, 247, 255], layer: 'SITE_FILL', skipDxf: true});
    // 기준선(점선): 지키면 초록, 걸리면 빨강
    const items = sp.items || [], danger = items.filter(x => ['process', 'compressed', 'storage'].includes(x.type));
    const rq = sp.req || {}, okOf = id => !(sp.bad || []).includes(id), Ls = sp.lines || {};
    // 글자가 피할 자리를 먼저 넣는다: 설비, 방호벽, 사업소 경계선, 거리 선(가로·세로에 가까운 선만)
    for (const it of items) OB.push([it.cx - it.w / 2 - 0.2, it.cy - it.d / 2 - 0.2, it.cx + it.w / 2 + 0.2, it.cy + it.d / 2 + 0.2]);
    for (const w of sp.walls || []) OB.push([Math.min(w.x1, w.x2) - 0.25, Math.min(w.y1, w.y2) - 0.25, Math.max(w.x1, w.x2) + 0.25, Math.max(w.y1, w.y2) + 0.25]);
    const e = mm(0.9);
    for (let i = 0; i < S4.length; i++) {        // 경계선 자리(1m 마다 작은 상자)
      const a = S4[i], b = S4[(i + 1) % S4.length], n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1])));
      for (let k = 0; k <= n; k++) { const x = a[0] + (b[0] - a[0]) * k / n, y = a[1] + (b[1] - a[1]) * k / n; OB.push([x - e, y - e, x + e, y + e]); }
    }
    for (const r of [Ls.sc, Ls.rd, Ls.bd]) {
      const c = r && r.a && clipSeg(r.a, r.b, V, 0); if (!c) continue;
      const b = [Math.min(c[0][0], c[1][0]), Math.min(c[0][1], c[1][1]), Math.max(c[0][0], c[1][0]), Math.max(c[0][1], c[1][1])];
      if (Math.min(b[2] - b[0], b[3] - b[1]) < 1.5) OB.push([b[0] - mm(0.8), b[1] - mm(0.8), b[2] + mm(0.8), b[3] + mm(0.8)]);
    }
    if (SP && rq.qb) {
      const ok = okOf('boundary');
      for (const [li, ring] of (sp.site.inner || [insetPoly(SP, rq.qb)].filter(Boolean)).entries()) {
        if (li) { pl(ring, {close: true, stroke: ok ? GRN : RED, lw: 0.3, dash: [2, 1.2], layer: 'GUIDE'}); continue; }
        pl(ring, {close: true, stroke: ok ? GRN : RED, lw: 0.3, dash: [2, 1.2], layer: 'GUIDE'});
        const c = cen(ring), cand = ring.flatMap((p, i) => { const q = ring[(i + 1) % ring.length], m = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2]; return [m, [p[0] + (c[0] - p[0]) * 0.12, p[1] + (c[1] - p[1]) * 0.12]]; }).map(p => [p[0] + (c[0] - p[0]) * 0.06, p[1] + (c[1] - p[1]) * 0.06]);
        ptx(cand.sort((a, b) => (b[1] - b[0]) - (a[1] - a[0])), `경계 ${rq.qb}m`, {size: 2.1, color: ok ? GRN : RED, al: 'c', vc: true, layer: 'GUIDE'});
      }
    } else if (rq.qb && rq.qb * 2 < Math.min(sp.site.w, sp.site.d)) {
      const hw = W2 - rq.qb, hd = D2 - rq.qb, ok = okOf('boundary');
      pl([[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]], {close: true, stroke: ok ? GRN : RED, lw: 0.3, dash: [2, 1.2], layer: 'GUIDE'});
      ptx([[-hw + mm(9), hd - mm(2.4)], [hw - mm(9), hd - mm(2.4)], [-hw + mm(9), -hd + mm(1.2)], [hw - mm(9), -hd + mm(1.2)], [-hw + mm(18), hd - mm(2.4)], [hw - mm(18), hd - mm(2.4)], [0, hd - mm(2.4)], [0, -hd + mm(1.2)]], `경계 ${rq.qb}m`, {size: 2.1, color: ok ? GRN : RED, al: 'c', layer: 'GUIDE'});
    }
    const st = items.filter(x => x.type === 'storage'), ch = items.filter(x => x.type === 'charger');
    if (st.length && ch.length && sp.fac === '저장식') {
      const [a, b, c, d] = bbox(st), ring = roundRect(a, b, c, d, 8), ok = okOf('sc_dist');
      pl(ring, {close: true, stroke: ok ? GRN : RED, lw: 0.3, dash: [2, 1.2], layer: 'GUIDE'});
      const ext = f => ring.reduce((m, q) => f(q) < f(m) ? q : m);
      ptx([ext(q => q[0]), ext(q => -q[0]), ext(q => -q[1]), ext(q => q[1]), ext(q => q[0] + q[1]), ext(q => q[0] - q[1]), ext(q => -q[0] + q[1]), ext(q => -q[0] - q[1])], '8m', {size: 2.1, color: ok ? GRN : RED, vc: true, layer: 'GUIDE', bg: true});
    }
    if (danger.length) for (const [q, nm, ln] of [[rq.q1, '제1종', Ls.p1], [rq.q2, '제2종', Ls.p2]]) {
      if (!q || !ln || !(ln.d < q + 20)) continue;          // 멀리 있으면 고리 대신 화살표 글만
      const [a, b, c, d] = bbox(danger), ring = roundRect(a, b, c, d, q), ok = okOf('prot');
      pl(ring, {close: true, stroke: ok ? GRN : RED, lw: 0.25, dash: [3, 1.5], layer: 'GUIDE'});
      const p = ring.reduce((m, r) => r[1] > m[1] ? r : m);
      if (p[1] < V.y1 - mm(4)) ptx([[p[0], p[1] + mm(1.8)], [p[0], p[1] - mm(2.2)]], `${nm} 보호시설 ${q}m`, {size: 2, color: ok ? GRN : RED, layer: 'GUIDE'});
    }
    pl(S4, {close: true, stroke: INK, lw: 0.5, dash: [6, 1.5, 1, 1.5], layer: 'SITE'});
    { const tl = S4.reduce((m, p) => (p[1] - p[0] * 0.3) > (m[1] - m[0] * 0.3) ? p : m); ptx([[tl[0], tl[1] + mm(2.4)], [tl[0], tl[1] + mm(5)], [tl[0] - mm(12), tl[1] + mm(2.4)]], '사업소 경계', {size: 2.4, al: 'l', layer: 'TEXT'}); }
    // 설비
    for (const it of items) {
      pl(rect(it), {close: true, fill: COL[it.type] || COL.other, stroke: [34, 34, 34], lw: 0.35, layer: 'EQUIP'});
      const small = it.w * k < 14 || it.d * k < 6;
      if (small) ptx([[it.cx, it.cy + it.d / 2 + mm(1.2)], [it.cx, it.cy - it.d / 2 - mm(3.4)], [it.cx + it.w / 2 + mm(2 + estW(it.name, 2.2) / 2), it.cy - mm(1)], [it.cx - it.w / 2 - mm(2 + estW(it.name, 2.2) / 2), it.cy - mm(1)]], it.name, {size: 2.2, layer: 'TEXT'});
      else {
        tx([it.cx, it.cy + mm(1.2)], it.name, {size: Math.min(2.6, it.w * k / Math.max(3, it.name.length) * 1.1), layer: 'TEXT'});
        tx([it.cx, it.cy - mm(1.8)], `${+it.w.toFixed(2)}×${+it.d.toFixed(2)}m`, {size: 1.8, color: SUB, layer: 'TEXT'});
      }
    }
    for (const w of sp.walls || []) pl([[w.x1, w.y1], [w.x2, w.y2]], {stroke: [17, 17, 17], lw: Math.max(0.15 * k, 1.0), cap: 'butt', layer: 'WALL'});
    // 부지 치수
    const dim = (a, b, off, label, o = {}) => {        // a->b 치수선, off: 바깥쪽 방향 벡터(m)
      const A = [a[0] + off[0], a[1] + off[1]], B = [b[0] + off[0], b[1] + off[1]], col = o.color || INK;
      pl([a, [A[0] + off[0] * 0.15, A[1] + off[1] * 0.15]], {stroke: col, lw: 0.12, layer: 'DIM'}); pl([b, [B[0] + off[0] * 0.15, B[1] + off[1] * 0.15]], {stroke: col, lw: 0.12, layer: 'DIM'});
      pl([A, B], {stroke: col, lw: 0.18, layer: 'DIM', arrows: true});
      const ang = Math.atan2(B[1] - A[1], B[0] - A[0]) * 180 / Math.PI, n = Math.hypot(off[0], off[1]) || 1;
      tx([(A[0] + B[0]) / 2 + off[0] / n * mm(1.6), (A[1] + B[1]) / 2 + off[1] / n * mm(1.6)], label, {size: 2.4, rot: Math.abs(ang) > 90 ? ang - 180 : ang, vc: true, color: col, layer: 'DIM'});
    };
    if (SP) {                                     // 실제 필지: 변마다 길이(바깥쪽)
      const c = cen(SP);
      SP.forEach((a, i) => {
        const b = SP[(i + 1) % SP.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 3 || L * k < 9) return;
        let nx = -(b[1] - a[1]) / L, ny = (b[0] - a[0]) / L; const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; if ((m[0] - c[0]) * nx + (m[1] - c[1]) * ny < 0) { nx = -nx; ny = -ny; }
        let rot = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI; if (rot > 90) rot -= 180; if (rot < -90) rot += 180;
        ptx([[m[0] + nx * mm(2.2), m[1] + ny * mm(2.2)], [m[0] + nx * mm(4.5), m[1] + ny * mm(4.5)]], `${f1(L)} m`, {size: 2.1, color: SUB, rot, vc: true, layer: 'DIM'});
      });
    } else {
      dim([-W2, -D2], [W2, -D2], [0, -mm(9)], `${f1(sp.site.w)} m`);
      dim([W2, -D2], [W2, D2], [mm(9), 0], `${f1(sp.site.d)} m`);
    }
    // 주요 거리: 저장↔충전, 충전기↔도로경계, 설비↔경계
    const L = Ls;
    const meas = (r, ok, label) => {
      if (!r || !r.a || !(r.d > 0.05)) return;
      const col = ok ? BLUE : RED, c = clipSeg(r.a, r.b, V, mm(4)); if (!c) return;
      pl([c[0], c[1]], {stroke: col, lw: 0.28, layer: 'DIM', arrows: true});
      const ang = Math.atan2(r.b[1] - r.a[1], r.b[0] - r.a[0]), nx = -Math.sin(ang), ny = Math.cos(ang), rot = ang * 180 / Math.PI, cand = [];
      for (const t of [0.5, 0.3, 0.7, 0.15, 0.85]) for (const sd of [1, -1]) cand.push([c[0][0] + (c[1][0] - c[0][0]) * t + nx * mm(2) * sd, c[0][1] + (c[1][1] - c[0][1]) * t + ny * mm(2) * sd]);
      ptx(cand, label, {size: 2.2, color: col, rot: rot > 90 ? rot - 180 : rot < -90 ? rot + 180 : rot, vc: true, layer: 'DIM', bg: true});
    };
    if (sp.fac === '저장식') meas(L.sc, okOf('sc_dist'), `${f1(L.sc?.d || 0)}m (기준 8m)`);
    meas(L.rd, okOf('road'), `도로경계 ${f1(L.rd?.d || 0)}m`);
    meas(L.bd, okOf('boundary'), `${f1(L.bd?.d || 0)}m`);
    // 가장 가까운 보호시설: 도면 밖이면 가장자리에서 화살표로
    for (const [r, nm, q] of [[L.p1, '제1종', rq.q1], [L.p2, '제2종', rq.q2]]) {
      if (!r || !r.a || !isFinite(r.d)) continue;
      const ok = !(q && r.d < q), col = ok ? [150, 158, 168] : RED;
      const ex = clipSeg(r.a, r.b, {x0: -W2, x1: W2, y0: -D2, y1: D2}, 0), a0 = ex && ex[2] ? ex[1] : r.a;      // 부지 밖으로 나가는 점부터
      const c = clipSeg(a0, r.b, V, mm(7)); if (!c) continue;
      pl([c[0], c[1]], {stroke: col, lw: 0.22, dash: [2.5, 1.2], layer: 'DIM', arrows: c[2] ? 'end' : true});
      tx([c[1][0], c[1][1] + mm(2.4)], `${nm} 보호시설${r.name ? '(' + r.name + ')' : ''}까지 ${f1(r.d)}m${q ? ` · 기준 ${q}m` : ''}`, {size: 2.1, color: ok ? SUB : RED, layer: 'DIM', bg: true, keepIn: true});
    }
    for (const q of sp.parcels || []) {
      if (q.road || q.mine || q.pts.length < 3 || parea(q.pts) * k * k < 160) continue;
      const c = cen(q.pts); if (!inside(c, q.pts) || c[0] < V.x0 + mm(6) || c[0] > V.x1 - mm(6) || c[1] < V.y0 + mm(6) || c[1] > V.y1 - mm(6)) continue;
      const o = {size: 1.9, color: [150, 158, 168], vc: true, layer: 'PARCEL_TXT'}, b = tbox(c, q.jb, o);
      if (!hit(b)) { OB.push(b); tx(c, q.jb, o); }
    }
    return {G, V, P};
  }

  // ------------------------------------------------------------ 오른쪽 표·표제란(종이 좌표, mm)
  function panel(sp, G) {
    const P = [], T = (x, y, s, o) => P.push({t: 'tx', at: [x, y], s: String(s), size: 2.6, al: 'l', color: INK, ...o}), R = (x, y, w, h, o) => P.push({t: 'rect', x, y, w, h, ...o});
    const X0 = 304, X1 = 408;
    R(10, 10, 400, 277, {stroke: INK, lw: 0.6}); R(X0 - 2, 10, 0, 277, {stroke: INK, lw: 0.4});
    T(X0 + 2, 276, '시설 배치도 (초안)', {size: 6.2});
    T(X0 + 2, 268.5, sp.address || '', {size: 2.8, color: SUB, max: X1 - X0 - 4});
    // 안전거리 검토표
    let y = 258; T(X0 + 2, y, '검토표 (용도지역 · 안전거리: 고압가스법 시행규칙 별표 5)', {size: 2.7}); y -= 3;
    const cols = [X0 + 2, X0 + 44, X0 + 66, X0 + 86], rh = 6.6;
    R(X0 + 1, y - rh, X1 - X0 - 3, rh, {fill: [242, 244, 246], stroke: [200, 205, 212], lw: 0.2});
    ['항목', '기준', '계획', '판정'].forEach((h, i) => T(cols[i] + 1, y - rh / 2, h, {size: 2.4, vc: true, color: SUB}));
    y -= rh;
    for (const r of sp.rows || []) {
      R(X0 + 1, y - rh, X1 - X0 - 3, rh, {stroke: [220, 224, 230], lw: 0.2});
      T(cols[0] + 1, y - rh / 2, r.t, {size: 2.3, vc: true, max: cols[1] - cols[0] - 2});
      T(cols[1] + 1, y - rh / 2, r.need, {size: 2.2, vc: true, max: cols[2] - cols[1] - 2});
      T(cols[2] + 1, y - rh / 2, r.plan, {size: 2.2, vc: true, max: cols[3] - cols[2] - 2});
      T(cols[3] + 1, y - rh / 2, r.v, {size: 2.3, vc: true, color: r.v === '적합' ? GRN : r.v === '부적합' ? RED : [200, 120, 0]});
      y -= rh;
    }
    // 범례
    y -= 6; T(X0 + 2, y, '범례', {size: 2.7}); y -= 5;
    const leg = Object.entries(TN).filter(([k]) => k !== 'other').map(([k, n]) => ['box', COL[k], n]);
    leg.push(['wall', null, '방호벽 (철근콘크리트)'], ['dash', GRN, '법정 거리 기준선 (지킴)'], ['dash', RED, '법정 거리 기준선 (못 지킴)'], ['site', null, '사업소 경계'], ['prot', null, '보호시설 (별표 2)']);
    if ((sp.parcels || []).length) leg.push(['parcel', null, '지적 경계 (필지)']);
    leg.forEach(([kind, c, n], i) => {
      const x = X0 + 2 + (i % 2) * 51, yy = y - Math.floor(i / 2) * 5.2;
      if (kind === 'box') R(x, yy - 1.6, 6, 3.2, {fill: c, stroke: [34, 34, 34], lw: 0.25});
      else if (kind === 'wall') P.push({t: 'line', a: [x, yy], b: [x + 6, yy], lw: 1.2, stroke: [17, 17, 17]});
      else if (kind === 'dash') P.push({t: 'line', a: [x, yy], b: [x + 6, yy], lw: 0.35, stroke: c, dash: [1.4, 0.9]});
      else if (kind === 'site') P.push({t: 'line', a: [x, yy], b: [x + 6, yy], lw: 0.5, stroke: INK, dash: [2.4, 0.8, 0.5, 0.8]});
      else if (kind === 'parcel') P.push({t: 'line', a: [x, yy], b: [x + 6, yy], lw: 0.2, stroke: [176, 184, 195]});
      else R(x, yy - 1.6, 6, 3.2, {fill: [253, 226, 226], stroke: [214, 120, 128], lw: 0.25});
      T(x + 8, yy, n, {size: 2.2, vc: true});
    });
    // 표제란
    const tb = [['공사명', `수소충전소 설치 (${sp.fac || '저장식'})`], ['위치', sp.address || ''], ['저장능력', sp.cap ? `${Number(sp.cap).toLocaleString()} ㎥` : '-'],
      ['부지', sp.site.poly ? `${sp.site.parcel || ''} · ${Number(sp.site.area || 0).toLocaleString()} ㎡ (${sp.site.jimok || ''}, 지적도)` : `${f1(sp.site.w)} × ${f1(sp.site.d)} m (예시 직사각형)`], ['축척', `1/${G.den} (A3)`], ['작성일', (sp.at || '').slice(0, 10)], ['배치 출처', sp.src || ''], ['작성', '수소문 AI 자동 배치 (초안)']];
    const th = 6.2, tb0 = 14 + 14;
    tb.forEach(([a, b], i) => {
      const yy = tb0 + (tb.length - 1 - i) * th;
      R(X0 + 1, yy, X1 - X0 - 3, th, {stroke: [200, 205, 212], lw: 0.2});
      T(X0 + 3, yy + th / 2, a, {size: 2.3, vc: true, color: SUB}); T(X0 + 24, yy + th / 2, b, {size: 2.4, vc: true, max: X1 - X0 - 27});
    });
    T(X0 + 2, 22, sp.site.poly ? `※ 건물·도로는 ${sp.bsrc || 'OpenStreetMap'}, 필지 경계는 연속지적도(브이월드) 기준. 실제 경계는 측량으로 확인하세요.` : `※ 주변 건물·도로는 ${sp.bsrc || 'OpenStreetMap'} 기준이며 부지 경계는 예시입니다.`, {size: 1.9, color: SUB, max: X1 - X0 - 4});
    T(X0 + 2, 18, '※ 작성 보조용 초안으로 법적 효력이 없습니다. 설계사 확인 후 제출하세요.', {size: 1.9, color: SUB, max: X1 - X0 - 4});
    // 방위·축척 막대(도면 칸 왼쪽 위/아래)
    const a = (sp.site.ang || 0) * Math.PI / 180, nx = Math.sin(a), ny = Math.cos(a), cx = 30, cy = 263;
    P.push({t: 'north', cx, cy, nx, ny});
    const seg = [5, 10, 20, 50].find(s => s * G.k >= 25) || 50, len = seg * G.k;
    P.push({t: 'rect', x: 22, y: 20, w: len / 2, h: 1.6, fill: INK}, {t: 'rect', x: 22 + len / 2, y: 20, w: len / 2, h: 1.6, stroke: INK, lw: 0.25});
    T(22, 24.2, '0', {size: 2, al: 'c'}); T(22 + len / 2, 24.2, String(seg / 2), {size: 2, al: 'c'}); T(22 + len, 24.2, `${seg} m`, {size: 2, al: 'c'});
    T(22, 15.5, `축척 1/${G.den}`, {size: 2.2, color: SUB});
    return P;
  }

  // ------------------------------------------------------------ PDF
  async function pdf(sp) {
    if (!W.__cfDocs || !W.__cfDocs.pdfKit) throw new Error('PDF 도구(cf-shim.js)가 없습니다');
    const {PDFLib, font, fk, trimFont} = await W.__cfDocs.pdfKit();
    const {G, V, P} = build(sp), Q = panel(sp, G);
    const text = [...P, ...Q].filter(o => o.t === 'tx').map(o => o.s).join('') + '0123456789.mN…',
      doc = await PDFLib.PDFDocument.create();
    doc.registerFontkit(W.fontkit);
    const F = await doc.embedFont(trimFont(font, fk, text), {subset: false});
    const pt = v => v * 72 / 25.4, rgb = c => PDFLib.rgb(c[0] / 255, c[1] / 255, c[2] / 255);
    const page = doc.addPage([pt(420), pt(297)]);
    doc.setTitle(`시설 배치도 (초안) ${sp.address || ''}`); doc.setCreator('수소문 3D 부지 검토'); doc.setProducer('pdf-lib');
    const M = p => [G.ox + p[0] * G.k, G.oy + p[1] * G.k];                    // 부지 좌표 -> 종이(mm)
    const path = pts => pts.map((p, i) => `${i ? 'L' : 'M'}${pt(p[0]).toFixed(2)} ${(-pt(p[1])).toFixed(2)}`).join(' ');
    const arrowHead = (a, b, col, lw) => {        // b 끝에 작은 화살촉
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), s = 1.6, w = 0.55;
      const p1 = [b[0] - Math.cos(ang) * s + Math.sin(ang) * w, b[1] - Math.sin(ang) * s - Math.cos(ang) * w], p2 = [b[0] - Math.cos(ang) * s - Math.sin(ang) * w, b[1] - Math.sin(ang) * s + Math.cos(ang) * w];
      page.drawSvgPath(path([b, p1, p2]) + ' Z', {x: 0, y: 0, color: rgb(col), borderWidth: 0});
    };
    const textAt = (o, at) => {
      const size = pt(o.size); let s = o.s, w = F.widthOfTextAtSize(s, size);
      if (o.max) { const mx = pt(o.max); while (w > mx && s.length > 2) { s = s.slice(0, -2) + '…'; w = F.widthOfTextAtSize(s, size); } }
      const r = (o.rot || 0) * Math.PI / 180, ca = Math.cos(r), sa = Math.sin(r);
      let x = pt(at[0]), y = pt(at[1]) + pt(o.dy || 0);
      const dx = o.al === 'c' ? -w / 2 : o.al === 'r' ? -w : 0, dy = o.vc ? -size * 0.36 : 0;
      x += dx * ca - dy * sa; y += dx * sa + dy * ca;
      if (o.bg) page.drawRectangle({x: x - 1.5 * ca + 1.2 * sa, y: y - 1.2 * ca - 1.5 * sa, width: w + 3, height: size * 1.05 + 1, rotate: PDFLib.degrees(o.rot || 0), color: PDFLib.rgb(1, 1, 1), opacity: 0.85});
      page.drawText(s, {x, y, size, font: F, color: rgb(o.color || INK), rotate: PDFLib.degrees(o.rot || 0)});
    };
    // 도면 칸만 보이게 잘라 그린다
    page.pushOperators(PDFLib.pushGraphicsState(), PDFLib.rectangle(pt(AREA.x0), pt(AREA.y0), pt(AREA.x1 - AREA.x0), pt(AREA.y1 - AREA.y0)), PDFLib.clip(), PDFLib.endPath());
    for (const o of P) {
      if (o.t === 'pl') {
        const pts = o.pts.map(M), d = path(pts) + (o.close ? ' Z' : ''), opt = {x: 0, y: 0};
        if (o.fill) opt.color = rgb(o.fill);
        if (o.stroke) { opt.borderColor = rgb(o.stroke); opt.borderWidth = pt(o.lw || 0.2); if (o.dash) opt.borderDashArray = o.dash.map(pt); opt.borderLineCap = o.cap === 'round' ? PDFLib.LineCapStyle.Round : PDFLib.LineCapStyle.Butt; }
        else opt.borderWidth = 0;
        page.drawSvgPath(d, opt);
        if (o.arrows) { if (o.arrows !== 'end') arrowHead(pts[1], pts[0], o.stroke, o.lw); arrowHead(pts[pts.length - 2], pts[pts.length - 1], o.stroke, o.lw); }
      } else if (o.t === 'tx') {
        let at = M(o.at);
        if (o.keepIn) {              // 도면 칸 안으로, 방위표(왼쪽 위)·축척 막대(왼쪽 아래)는 비켜서
          const w = F.widthOfTextAtSize(o.s, pt(o.size)) / pt(1) / 2 + 2; at = [Math.max(AREA.x0 + w, Math.min(AREA.x1 - w, at[0])), Math.max(AREA.y0 + 4, Math.min(AREA.y1 - 4, at[1]))];
          if (at[0] - w < 46 && at[1] > 248) at[0] = 46 + w;
          if (at[0] - w < 76 && at[1] < 30) at[1] = 32;
        }
        textAt(o, at);
      }
    }
    page.pushOperators(PDFLib.popGraphicsState());
    for (const o of Q) {
      if (o.t === 'rect') {
        const opt = {x: pt(o.x), y: pt(o.y), width: pt(o.w), height: pt(o.h)};
        if (o.fill) opt.color = rgb(o.fill);
        if (o.stroke) { opt.borderColor = rgb(o.stroke); opt.borderWidth = pt(o.lw || 0.2); }
        if (o.w === 0) page.drawLine({start: {x: opt.x, y: opt.y}, end: {x: opt.x, y: opt.y + opt.height}, thickness: opt.borderWidth, color: opt.borderColor});
        else page.drawRectangle(opt);
      } else if (o.t === 'line') page.drawLine({start: {x: pt(o.a[0]), y: pt(o.a[1])}, end: {x: pt(o.b[0]), y: pt(o.b[1])}, thickness: pt(o.lw), color: rgb(o.stroke), ...(o.dash ? {dashArray: o.dash.map(pt)} : {})});
      else if (o.t === 'tx') textAt(o, o.at);
      else if (o.t === 'north') {
        const {cx, cy, nx, ny} = o, L = 7, tip = [cx + nx * L, cy + ny * L], tl = [cx - nx * 2.5 - ny * 2.6, cy - ny * 2.5 + nx * 2.6], tr = [cx - nx * 2.5 + ny * 2.6, cy - ny * 2.5 - nx * 2.6];
        page.drawCircle({x: pt(cx), y: pt(cy), size: pt(8.5), borderColor: rgb(INK), borderWidth: pt(0.25)});
        page.drawSvgPath(path([tip, tl, [cx, cy]]) + ' Z', {x: 0, y: 0, color: rgb(INK), borderWidth: 0});
        page.drawSvgPath(path([tip, tr, [cx, cy]]) + ' Z', {x: 0, y: 0, borderColor: rgb(INK), borderWidth: pt(0.25)});
        textAt({s: 'N', size: 3.2, al: 'c', vc: true}, [cx + nx * 11.5, cy + ny * 11.5]);
      }
    }
    return doc.save();
  }

  // ------------------------------------------------------------ DXF (AutoCAD R12)
  function dxf(sp) {
    const {P, V} = build(sp), out = [], g = (c, v) => out.push(String(c), String(v));
    const u = s => String(s).replace(/[^\x20-\x7e]/g, ch => '\\U+' + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0'));
    const n = v => (Math.round(v * 1000) / 1000).toString();
    const LAYERS = {SITE: 7, EQUIP: 3, WALL: 8, ROAD: 9, BLDG: 252, PROTECT: 1, RAIL: 8, GUIDE: 94, DIM: 5, TEXT: 7, PARCEL: 253, PARCEL_TXT: 253};
    const G = scaleOf(sp), hm = mmv => mmv / G.k;     // 종이 mm -> 도면 m (축척 1/den 로 출력하면 같은 크기)
    g(0, 'SECTION'); g(2, 'HEADER'); g(9, '$ACADVER'); g(1, 'AC1009'); g(9, '$INSBASE'); g(10, 0); g(20, 0); g(30, 0); g(0, 'ENDSEC');
    g(0, 'SECTION'); g(2, 'TABLES');
    g(0, 'TABLE'); g(2, 'LTYPE'); g(70, 3);
    for (const [nm, desc, pat] of [['CONTINUOUS', 'Solid line', []], ['DASHED', '__ __ __', [0.6, -0.3]], ['DASHDOT', '__ . __ .', [1.2, -0.3, 0, -0.3]]]) {
      g(0, 'LTYPE'); g(2, nm); g(70, 0); g(3, desc); g(72, 65); g(73, pat.length); g(40, n(pat.reduce((s, v) => s + Math.abs(v), 0))); for (const v of pat) g(49, n(v));
    }
    g(0, 'ENDTAB');
    g(0, 'TABLE'); g(2, 'LAYER'); g(70, Object.keys(LAYERS).length + 1);
    g(0, 'LAYER'); g(2, '0'); g(70, 0); g(62, 7); g(6, 'CONTINUOUS');
    for (const [nm, c] of Object.entries(LAYERS)) { g(0, 'LAYER'); g(2, nm); g(70, 0); g(62, c); g(6, nm === 'SITE' ? 'DASHDOT' : nm === 'GUIDE' ? 'DASHED' : 'CONTINUOUS'); }
    g(0, 'ENDTAB'); g(0, 'ENDSEC');
    g(0, 'SECTION'); g(2, 'ENTITIES');
    // PDF 와 같은 범위(도면 칸)만 남긴다
    const line = (a0, b0, layer, ltype) => { const c = clipSeg(a0, b0, V, 0); if (!c) return; const [a, b] = c; g(0, 'LINE'); g(8, layer); if (ltype) g(6, ltype); g(10, n(a[0])); g(20, n(a[1])); g(30, 0); g(11, n(b[0])); g(21, n(b[1])); g(31, 0); };
    for (const o of P) {
      if (o.skipDxf) continue;
      if (o.t === 'pl') {
        const pts = o.close ? [...o.pts, o.pts[0]] : o.pts;
        if (o.road) {                                  // 도로: 양쪽 경계선
          for (let i = 0; i + 1 < pts.length; i++) {
            const a = pts[i], b = pts[i + 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, nx = -(b[1] - a[1]) / L * o.road / 2, ny = (b[0] - a[0]) / L * o.road / 2;
            line([a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], 'ROAD'); line([a[0] - nx, a[1] - ny], [b[0] - nx, b[1] - ny], 'ROAD');
          }
          continue;
        }
        const lt = o.dash && o.layer !== 'SITE' && o.layer !== 'GUIDE' ? 'DASHED' : null;
        for (let i = 0; i + 1 < pts.length; i++) line(pts[i], pts[i + 1], o.layer || '0', lt);
      } else if (o.t === 'tx') {
        const h = hm(o.size), at = [o.at[0], o.at[1] + hm(o.dy || 0)], hal = o.al === 'c' ? 1 : o.al === 'r' ? 2 : 0, val = o.vc ? 2 : 0;
        g(0, 'TEXT'); g(8, o.layer || 'TEXT'); g(10, n(at[0])); g(20, n(at[1])); g(30, 0); g(40, n(h)); g(1, u(o.s));
        if (o.rot) g(50, n(o.rot));
        if (hal || val) { g(72, hal); g(11, n(at[0])); g(21, n(at[1])); g(31, 0); g(73, val); }
      }
    }
    // 도면 아래에 표제(한 줄씩)
    const y0 = -sp.site.d / 2 - hm(26), x0 = -sp.site.w / 2;
    [`시설 배치도 (초안) - ${sp.address || ''}`, `수소충전소 (${sp.fac || ''}) 저장능력 ${sp.cap || '-'} m3 · 단위 m · 부지 중심 (0,0) · 위쪽 +y`, `작성: 수소문 AI 자동 배치 ${(sp.at || '').slice(0, 10)} · 작성 보조용 초안, 법적 효력 없음`]
      .forEach((s, i) => { g(0, 'TEXT'); g(8, 'TEXT'); g(10, n(x0)); g(20, n(y0 - i * hm(5))); g(30, 0); g(40, n(hm(i ? 2.4 : 3.6))); g(1, u(s)); });
    g(0, 'ENDSEC'); g(0, 'EOF');
    return out.join('\r\n') + '\r\n';
  }

  const fname = (sp, ext) => `시설배치도_초안${sp.address ? '_' + sp.address.replace(/\s*\(.*\)$/, '').replace(/[\\/:*?"<>|]/g, '').slice(0, 24) : ''}.${ext}`;
  W.SitePlan = {build, pdf, dxf, fname, scaleOf};
})(window);
