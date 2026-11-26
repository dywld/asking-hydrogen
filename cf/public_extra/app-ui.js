// 윈도우 앱 전용 화면. 앱(desktop/preload.js)이 window.h2app 을 내주고 이 파일을 붙인다.
// 브라우저로 열면 window.h2app 이 없어서 아무것도 하지 않는다.
// 사업장(프로젝트) · 서류 폴더 검토 · 알림(일정·법령 개정·새 버전) · 내려받은 파일 열기.
(() => {
  const A = window.h2app;
  if (!A || window.__h2appUi) return;
  window.__h2appUi = true;

  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  const addDays = (d, n) => new Date(new Date(d + 'T00:00:00Z').getTime() + n * 86400e3).toISOString().slice(0, 10);
  const daysTo = d => Math.round((new Date(d + 'T00:00:00Z') - new Date(today() + 'T00:00:00Z')) / 86400e3);
  const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} } };
  const kb = n => n < 1024 ? n + 'B' : n < 1048576 ? (n / 1024).toFixed(0) + 'KB' : (n / 1048576).toFixed(1) + 'MB';
  const newer = (a, b) => { const x = String(a).split('.').map(Number), y = String(b).split('.').map(Number);
    for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); return false; };

  let info = {}, permits = [], cur = null;   // cur: 열려 있는 사업장(project.json 내용)

  // ── 모양 ──
  const css = document.createElement('style');
  css.textContent = `
  .h2a-btn{position:relative}
  .h2a-btn.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
  .h2a-badge{position:absolute;top:-5px;right:-5px;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:#f04452;color:#fff;font-size:11px;line-height:17px;text-align:center;font-weight:700}
  .h2a-cur{max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .h2a-dim{position:fixed;inset:0;background:rgba(20,30,50,.25);z-index:40;display:none}
  .h2a-dim.open{display:block}
  .h2a-drawer{position:fixed;top:0;right:0;bottom:0;width:min(460px,100vw);background:#fff;border-left:1px solid var(--line);z-index:41;
    transform:translateX(100%);transition:transform .18s ease;display:flex;flex-direction:column;box-shadow:-12px 0 32px rgba(20,30,50,.08)}
  .h2a-drawer.open{transform:none}
  .h2a-drawer>header{flex:none;height:56px;display:flex;align-items:center;gap:8px;padding:0 18px;border-bottom:1px solid var(--line)}
  .h2a-drawer>header h2{font-size:var(--fs);margin:0;flex:1}
  .h2a-body{flex:1;overflow-y:auto;overflow-x:hidden;padding:16px 18px 28px}
  .h2a-path{display:block;word-break:break-all;color:var(--ink);font-size:12.5px;margin-bottom:6px}
  .h2a-sec{margin:0 0 18px}
  .h2a-sec>h3{font-size:var(--fs-s);color:var(--ink-2);font-weight:700;margin:0 0 8px;display:flex;align-items:center;gap:8px}
  .h2a-sec>h3 .sp{flex:1}
  .h2a-row{display:flex;align-items:center;gap:8px;padding:9px 12px;border:1px solid var(--line);border-radius:10px;margin-bottom:6px;background:#fff}
  .h2a-row.click{cursor:pointer}.h2a-row.click:hover{border-color:var(--accent);background:var(--accent-soft)}
  .h2a-row .t{flex:1;min-width:0}.h2a-row .t b{display:block;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .h2a-row small{color:var(--ink-2);font-size:12px}
  .h2a-in{font:inherit;font-size:var(--fs-s);padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);min-width:0}
  .h2a-in:focus{outline:2px solid var(--accent-soft);border-color:var(--accent)}
  .h2a-b{font:inherit;font-size:var(--fs-s);font-weight:700;border-radius:8px;padding:7px 12px;cursor:pointer;border:1px solid #cfe0ff;background:#fff;color:var(--accent);white-space:nowrap}
  .h2a-b.pri{background:var(--accent);color:#fff;border-color:var(--accent)}
  .h2a-b.ghost{border-color:var(--line);color:var(--ink-2)}
  .h2a-b:disabled{opacity:.5;cursor:default}
  .h2a-x{font:inherit;background:none;border:0;color:var(--ink-2);cursor:pointer;padding:2px 6px;border-radius:6px}.h2a-x:hover{background:var(--surface)}
  .h2a-line{display:flex;gap:6px;margin-bottom:8px}.h2a-line>.h2a-in{flex:1}
  .h2a-empty{color:var(--ink-2);font-size:var(--fs-s);padding:10px 2px}
  .h2a-tag{display:inline-block;font-size:11.5px;font-weight:700;border-radius:6px;padding:1px 7px;margin-left:4px}
  .h2a-tag.ok{background:var(--ok-soft);color:var(--ok)}.h2a-tag.no{background:#ffeef0;color:#d0283c}.h2a-tag.wa{background:var(--warn-soft);color:var(--warn)}
  .h2a-drop{border:2px dashed #cfe0ff;border-radius:12px;padding:18px;text-align:center;color:var(--ink-2);font-size:var(--fs-s);background:var(--surface)}
  .h2a-drop.over{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
  .h2a-issues{margin:6px 0 0 0;padding-left:18px;font-size:var(--fs-s);color:var(--ink)}
  .h2a-sum{background:var(--accent-soft);border-radius:10px;padding:10px 12px;font-size:var(--fs-s);margin-bottom:12px}
  .h2a-toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:50;background:#1b2430;color:#fff;border-radius:12px;padding:10px 12px 10px 16px;
    display:flex;align-items:center;gap:10px;font-size:var(--fs-s);box-shadow:0 10px 30px rgba(0,0,0,.2);max-width:min(560px,calc(100vw - 32px))}
  .h2a-toast span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .h2a-toast button{font:inherit;font-weight:700;background:#ffffff1f;color:#fff;border:0;border-radius:8px;padding:6px 10px;cursor:pointer}
  .h2a-pjhd{display:flex;align-items:flex-start;gap:8px;margin:2px 0 6px}
  .h2a-pjname{flex:1;font-size:21px;font-weight:800;color:var(--ink);line-height:1.3}
  .h2a-more{position:relative}.h2a-more>.h2a-x{font-size:18px;padding:2px 8px}
  .h2a-menu{position:absolute;right:0;top:32px;z-index:3;background:#fff;border-radius:12px;box-shadow:0 8px 24px rgba(20,30,50,.18);padding:6px;width:150px}
  .h2a-menu button{display:block;width:100%;text-align:left;font:inherit;font-size:var(--fs-s);background:none;border:0;padding:9px 12px;border-radius:8px;cursor:pointer;color:var(--ink)}
  .h2a-menu button:hover{background:var(--surface)}.h2a-menu button.red{color:#d0283c}
  .h2a-chipsel{font:inherit;font-size:13px;font-weight:700;color:var(--accent);background:var(--accent-soft);border:0;border-radius:999px;padding:6px 12px;max-width:100%;cursor:pointer;appearance:none}
  .h2a-kindrow{display:flex;align-items:center;gap:8px;border:1.5px solid var(--line,#e5e8eb);border-radius:14px;padding:10px 14px;margin-top:6px;position:relative}
  .h2a-kindrow.ai{border-color:var(--accent);background:var(--accent-soft)}
  .h2a-kindrow .h2a-chipsel{flex:1;background:transparent;padding:2px 18px 2px 0;font-size:14.5px;color:var(--ink)}
  .h2a-kindrow .ar{position:absolute;right:14px;color:var(--ink-2);pointer-events:none;font-size:12px}
  .h2a-aibadge{flex:none;font-size:11.5px;font-weight:700;color:#fff;background:linear-gradient(90deg,#3182f6,#7b5cff);border-radius:999px;padding:3px 9px}
  .h2a-why{font-size:12.5px;color:var(--ink-2);margin:8px 2px 0;line-height:1.5}
  .h2a-why em{font-style:normal;color:var(--accent);font-weight:700}
  .h2a-kindinfo{font-size:12px;color:var(--ink-2);margin:6px 2px 0}
  .h2a-bigdrop{display:flex;flex-direction:column;align-items:center;gap:4px;border:2px dashed #c9d3df;border-radius:14px;background:#f8fafd;text-align:center;padding:20px 14px;margin:14px 0 4px;cursor:pointer}
  .h2a-bigdrop.over{border-color:var(--accent);background:var(--accent-soft)}
  .h2a-bigdrop .ic{font-size:26px}.h2a-bigdrop b{font-size:15px;color:var(--ink)}.h2a-bigdrop>span{font-size:12.5px;color:var(--ink-2)}
  .h2a-bigdrop .pick{margin-top:8px;color:var(--ink)}
  .h2a-prog{display:flex;align-items:center;gap:10px;margin:16px 2px 4px;font-size:var(--fs-s);font-weight:700;color:var(--ink)}
  .h2a-prog .bar{flex:1;height:7px;background:var(--surface);border-radius:7px;overflow:hidden}
  .h2a-prog .bar i{display:block;height:100%;background:var(--accent);border-radius:7px}
  .h2a-prog small{color:var(--ink-2);font-weight:500}
  .h2a-doc{display:flex;align-items:center;gap:10px;padding:11px 2px;border-bottom:1px solid var(--line)}
  .h2a-doc.over{background:var(--accent-soft)}
  .h2a-doc .st{width:22px;height:22px;border-radius:50%;border:2px solid #d1d6db;flex:none;display:grid;place-items:center;font-size:12px;color:#fff}
  .h2a-doc.ok .st{background:var(--accent);border-color:var(--accent)}
  .h2a-doc .t{flex:1;min-width:0}.h2a-doc .t b{font-weight:600;font-size:14px;color:var(--ink)}
  .h2a-doc .t b i{font-style:normal;font-size:11px;color:#d0283c;font-weight:700;margin-left:5px}
  .h2a-doc .t b i.opt{color:var(--ink-2);background:var(--surface);border-radius:5px;padding:1px 6px;font-weight:600}
  .h2a-doc .t small{display:block;font-size:12px;color:var(--ink-2);margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .h2a-doc .t small.ai{color:var(--ok)}
  .h2a-sub{font-size:var(--fs-s);color:var(--ink-2);font-weight:700;margin:16px 2px 8px}
  .h2a-work{border-radius:14px;padding:14px;margin:12px 0 4px;background:linear-gradient(#fff,#fff) padding-box,linear-gradient(90deg,#3182f6,#7b61ff,#22c3a6,#3182f6) border-box;
    border:2px solid transparent;background-size:100% 100%,300% 100%;animation:h2aflow 2.4s linear infinite;box-shadow:0 6px 20px rgba(49,130,246,.12)}
  .h2a-work.fin{animation:none;background:linear-gradient(#fff,#fff) padding-box,linear-gradient(90deg,#22c3a6,#22c3a6) border-box}
  @keyframes h2aflow{to{background-position:0 0,300% 0}}
  .h2a-work .hd{display:flex;align-items:center;gap:10px}.h2a-work .hd b{flex:1;font-size:14px;color:var(--ink)}
  .h2a-work .pct{font-size:12px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}
  .h2a-work .orb{display:inline-flex;gap:3px}.h2a-work .orb i{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:h2adot 1s ease-in-out infinite}
  .h2a-work .orb i:nth-child(2){animation-delay:.15s;background:#7b61ff}.h2a-work .orb i:nth-child(3){animation-delay:.3s;background:#22c3a6}
  .h2a-work.fin .orb i{animation:none;background:#22c3a6}
  @keyframes h2adot{0%,100%{transform:translateY(0);opacity:.5}50%{transform:translateY(-5px);opacity:1}}
  .h2a-work .bar{height:5px;border-radius:5px;background:var(--surface);margin:10px 0;overflow:hidden}
  .h2a-work .bar i{display:block;height:100%;width:6%;border-radius:5px;background:linear-gradient(90deg,#3182f6,#7b61ff);transition:width .45s ease}
  .h2a-work.fin .bar i{background:#22c3a6}
  .h2a-work .files{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .h2a-work .fc{position:relative;overflow:hidden;display:inline-flex;align-items:center;gap:6px;background:var(--surface);border-radius:8px;padding:5px 8px;font-size:12px;color:var(--ink)}
  .h2a-work .fc em{font-style:normal;font-size:10px;font-weight:800;color:#fff;background:var(--accent);border-radius:4px;padding:1px 4px}
  .h2a-work .fc u{position:absolute;top:0;bottom:0;width:40%;left:-40%;background:linear-gradient(90deg,transparent,rgba(49,130,246,.25),transparent);animation:h2ascan 1.3s ease-in-out infinite}
  .h2a-work.fin .fc u{display:none}
  @keyframes h2ascan{to{left:110%}}
  .h2a-work ol{list-style:none;margin:0;padding:0}
  .h2a-work li{display:flex;align-items:center;gap:8px;font-size:12.5px;color:#b0b8c1;padding:3px 0;transition:color .2s}
  .h2a-work li .dot{width:14px;height:14px;border-radius:50%;border:2px solid #d1d6db;flex:none}
  .h2a-work li.now{color:var(--ink);font-weight:600}.h2a-work li.now .dot{border-color:var(--accent);border-top-color:transparent;animation:spin .7s linear infinite}
  .h2a-work li.done{color:var(--ink-2)}.h2a-work li.done .dot{border-color:#22c3a6;background:#22c3a6}
  .h2a-doc.h2a-new{animation:h2aflash 1.6s ease}.h2a-doc.h2a-new .st{animation:h2apop .5s cubic-bezier(.3,1.6,.5,1)}
  @keyframes h2aflash{0%{background:#e6f9f3}100%{background:transparent}}
  @keyframes h2apop{0%{transform:scale(.2)}100%{transform:scale(1)}}
  .h2a-spin{display:inline-block;width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;vertical-align:-2px;margin-right:6px}
  `;
  document.head.appendChild(css);

  // ── 공통: 서랍 ──
  const dim = document.createElement('div'); dim.className = 'h2a-dim'; document.body.appendChild(dim);
  function drawer(id, title) {
    const d = document.createElement('div');
    d.className = 'h2a-drawer'; d.id = id;
    d.innerHTML = `<header><h2>${esc(title)}</h2><button class="h2a-x" data-close title="닫기">✕</button></header><div class="h2a-body"></div>`;
    d.querySelector('[data-close]').onclick = close;
    document.body.appendChild(d);
    return d;
  }
  function open(d) { document.querySelectorAll('.h2a-drawer.open').forEach(x => x !== d && x.classList.remove('open')); d.classList.add('open'); dim.classList.add('open'); }
  function close() { document.querySelectorAll('.h2a-drawer.open').forEach(x => x.classList.remove('open')); dim.classList.remove('open'); }
  dim.onclick = close;
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });

  function toast(msg, actions = [], ms = 7000) {
    document.querySelectorAll('.h2a-toast').forEach(t => t.remove());
    const t = document.createElement('div'); t.className = 'h2a-toast';
    t.innerHTML = `<span>${esc(msg)}</span>`;
    for (const [label, fn] of actions) { const b = document.createElement('button'); b.textContent = label; b.onclick = () => { fn(); t.remove(); }; t.appendChild(b); }
    const x = document.createElement('button'); x.textContent = '✕'; x.onclick = () => t.remove(); t.appendChild(x);
    document.body.appendChild(t);
    setTimeout(() => t.remove(), ms);
  }

  // ── 위쪽 줄 단추 ──
  const ICON = {
    proj: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    rev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/></svg>',
    bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/></svg>',
  };
  const mk = (id, icon, label, title) => {
    const b = document.createElement('button');
    b.className = 'ibtn h2a-btn'; b.id = id; b.title = title;
    b.innerHTML = icon + (label ? `<span class="lbl ${id === 'h2a-proj' ? 'h2a-cur' : ''}">${esc(label)}</span>` : '');
    return b;
  };
  const projBtn = mk('h2a-proj', ICON.proj, '내 사업장', '내 사업장');
  const revBtn = mk('h2a-rev', ICON.rev, '서류 검토', '서류 폴더 검토');
  const bellBtn = mk('h2a-bell', ICON.bell, '', '알림');
  const anchor = $('#histbtn') || $('header .sp');
  // 첫 화면 버튼은 왼쪽 사이드바(#side)에 있다. 기준 단추의 부모에 끼운다.
  if (anchor && anchor.parentNode) for (const b of [projBtn, revBtn]) anchor.parentNode.insertBefore(b, anchor);
  const gear = $('#gear');
  if (gear && gear.parentNode) {
    if (gear.closest('#side')) bellBtn.insertAdjacentHTML('beforeend', '<span class="lbl">알림</span>');
    gear.parentNode.insertBefore(bellBtn, gear);
  }

  const projD = drawer('h2a-projd', '내 사업장');
  const revD = drawer('h2a-revd', '서류 폴더 검토');
  const bellD = drawer('h2a-belld', '알림');
  projBtn.onclick = () => { renderProj(); open(projD); };
  revBtn.onclick = () => { renderRev(); open(revD); };
  bellBtn.onclick = () => { renderBell(); open(bellD); ls.set('h2aBellSeen', bellItems.map(i => i.key)); badge(); };

  function setCurLabel() {
    const l = projBtn.querySelector('.lbl');
    if (l) l.textContent = cur ? cur.name : '내 사업장';
    projBtn.classList.toggle('on', !!cur);
  }

  // ── 사업장 ──
  // 열린 사업장이 있으면: 사업 정보(h2profile)를 그 사업장 것으로 바꾸고, 대화가 저장될 때마다 사업장에도 남긴다.
  async function openProject(id) {
    cur = await A.projects.open(id);
    if (!cur) return;
    ls.set('h2aLastProject', id);
    if (cur.profile) ls.set('h2profile', cur.profile);
    else { const p = ls.get('h2profile', null); if (p) cur = await A.projects.save(cur.id, { profile: p }); }
    setCurLabel();
  }
  async function closeProject() { await A.projects.close(); cur = null; ls.set('h2aLastProject', null); setCurLabel(); }
  async function refresh() { if (cur) cur = await A.projects.get(cur.id); }

  // ── 사업장 서류 칸 ──
  // 사업자등록증(필수) 하나 + 고른 허가 종류의 첨부 서류(선택). 어느 파일이 어느 칸인지는 이 PC(localStorage h2aSlots)에 사업장별로 둔다.
  // 11/24 사용자 결정: 공통 11칸은 버리고, 고른 허가 서류만 보인다. 필수는 사업자등록증 하나.
  const BIZ_DOC = { name: '사업자등록증', req: 1, hint: '신청인 확인 · AI가 회사 정보를 채워요', re: /사업자\s*등록/ };
  const DOC_RE = [[/사업\s*계획/, /사업\s*계획/, '시설 개요와 저장능력'], [/정관/, /정관|등기/, '법인이면'], [/기술\s*검토/, /기술\s*검토/, '가스안전공사에서 미리 받는 검토 결과'],
    [/설치\s*계획/, /설치\s*계획/, '시설을 어떻게 지을지 적은 계획'], [/도면|설명서/, /도면|배치|설명서/, '배치도와 안전거리가 보이는 도면'],
    [/안전\s*관리\s*규정/, /안전\s*관리\s*규정/, '3부'], [/경력|자격/, /자격|경력/, '경력이 필요하면 경력 증명서'], [/완공|시공/, /완공|시공/, '완성검사 때']];
  function docSlots(kind) {
    const out = [{ ...BIZ_DOC }];
    for (const raw of (kind && kind.docs) || []) {
      const full = String(raw).replace(/\s+/g, ' ').trim();
      const paren = (full.match(/\(([^)]*)\)/) || [])[1] || '';
      const t = full.replace(/\(.*?\)/g, '').replace(/\s*\d+\s*부.*$/, '').trim();
      if (!t || out.some(d => d.re.test(t))) continue;
      const hit = DOC_RE.find(([k]) => k.test(t));
      const hint = paren.length && paren.length <= 24 ? paren : (hit && hit[2]) || '고른 허가에 내는 서류';
      out.push({ name: t.length > 26 ? t.slice(0, 26) + '…' : t, req: 0, hint, re: hit ? hit[1] : new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').slice(0, 8)) });
    }
    const notes = (ls.get('h2aSlotNote', {}) || {})[cur && cur.id] || {};
    out.forEach(d => { d.note = notes[d.name] || ''; });
    return out;
  }
  // AI 추천: 사업장 정보(시설 종류·지역)로 먼저 받을 허가 하나를 고른다. 사용자가 바꾸면 그 값을 따른다.
  const REC = [[/충전소|생산|제조시설|저장|운송/, 'gas_permit'], [/수소용품/, 'h2_maker'], [/연료전지|발전/, 'h2_review']];
  function recommend() {
    const prof = (cur && cur.profile) || ls.get('h2profile', {}) || {};
    const k = prof.kind || cur.name || '';      // 사업 정보가 없으면 사업장 이름(예: 강원 수소충전소)으로 짐작
    const id = (REC.find(([re]) => re.test(k)) || [, 'gas_permit'])[1];
    const p = permits.find(x => x.id === id);
    return p ? { id, why: [prof.kind, prof.region].filter(Boolean).join(' · ') || cur.name } : null;
  }
  const kindAi = () => (ls.get('h2aKindAi', {}) || {})[cur && cur.id];
  function setKindAi(why) { const m = ls.get('h2aKindAi', {}) || {}; if (why == null) delete m[cur.id]; else m[cur.id] = why; ls.set('h2aKindAi', m); }
  function slotMap() {
    const all = ls.get('h2aSlots', {}) || {}, m = { ...(all[cur.id] || {}) };
    const names = new Set((cur.files || []).map(f => f.name));
    for (const k of Object.keys(m)) if (!names.has(m[k])) delete m[k];      // 탐색기에서 지운 파일은 칸에서도 뺀다
    return m;
  }
  function setSlot(name, file, note) {
    const all = ls.get('h2aSlots', {}) || {};
    all[cur.id] = { ...(all[cur.id] || {}), [name]: file }; ls.set('h2aSlots', all);
    const ns = ls.get('h2aSlotNote', {}) || {};
    ns[cur.id] = { ...(ns[cur.id] || {}), [name]: note || '' }; ls.set('h2aSlotNote', ns);
  }
  const b64of = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1] || ''); r.onerror = no; r.readAsDataURL(f); });
  const MEMO_KEYS = ['company', 'ceo', 'bizno', 'office', 'tel', 'email', 'site', 'mgr_name', 'mgr_qual', 'mgr_no', 'permit_no', 'permit_date'];
  // AI가 일하는 모습: 서류 칸 위에 단계 카드를 띄우고 한 단계씩 넘긴다(단계마다 최소 0.5초 보여 줌).
  const justSet = new Set();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  function workCard(files) {
    const STEPS = ['서류를 사업장 폴더에 담는 중', 'AI가 서류를 한 장씩 읽는 중', '어떤 서류인지 칸에 맞추는 중', '회사 정보 빈칸 채우는 중'];
    const host = projD.querySelector('#h2a-req');
    const el = document.createElement('div'); el.className = 'h2a-work';
    el.innerHTML = `<div class="hd"><span class="orb"><i></i><i></i><i></i></span><b>AI가 서류를 정리하고 있어요</b><span class="pct">0%</span></div>
      <div class="bar"><i></i></div>
      <div class="files">${files.slice(0, 10).map(f => `<span class="fc"><em>${esc((f.name.split('.').pop() || '').toUpperCase().slice(0, 4))}</em>${esc(f.name.length > 22 ? f.name.slice(0, 20) + '…' : f.name)}<u></u></span>`).join('')}</div>
      <ol>${STEPS.map(t => `<li><span class="dot"></span>${t}</li>`).join('')}</ol>`;
    if (host) host.parentNode.insertBefore(el, host); 
    if (host) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    let t0 = Date.now();
    const set = i => {
      el.querySelectorAll('li').forEach((li, k) => li.className = k < i ? 'done' : k === i ? 'now' : '');
      const pct = Math.round(i / STEPS.length * 100);
      el.querySelector('.bar i').style.width = Math.max(6, pct) + '%'; el.querySelector('.pct').textContent = pct + '%';
    };
    return {
      async step(i) { const w = 500 - (Date.now() - t0); if (i && w > 0) await sleep(w); set(i); t0 = Date.now(); },
      async done() { const w = 500 - (Date.now() - t0); if (w > 0) await sleep(w); set(STEPS.length); el.classList.add('fin'); el.querySelector('b').textContent = '정리 끝!'; await sleep(650); },
    };
  }

  // 파일을 사업장 서류 폴더에 저장하고 칸에 꽂는다. slot 이 없으면(큰 칸) AI가 서류 종류를 읽어 맞춘다.
  async function attach(files, slot) {
    if (!cur || !files.length) return;
    const kind = permits.find(x => x.id === cur.kind), docs = docSlots(kind);
    const free = () => { const m = slotMap(); return docs.filter(d => !m[d.name]); };
    const w = workCard(files);
    await w.step(0);
    const saved = [];
    for (const f of files.slice(0, 10)) {
      try {
        const b64 = await b64of(f);
        const p = await A.files.save(f.name, b64);
        if (p) saved.push({ f, b64, name: String(p).split(/[\\/]/).pop() });
      } catch (e) { toast(`'${f.name}'을 저장하지 못했어요`); }
    }
    if (!saved.length) return renderProj();
    if (slot) { setSlot(slot, saved[0].name, ''); justSet.add(slot); }
    // AI 읽기: PDF·사진만, 18MB 안쪽. 칸을 고른 경우도 회사 정보 채우기에 쓴다.
    const send = saved.filter(s => /pdf|image\//.test(s.f.type) && s.b64.length < 18e6);
    await w.step(1);
    let got = {}, types = {};
    if (send.length) {
      try {
        const r = await fetch('/api/app/extract', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ files: send.map(s => ({ name: s.name, mime: s.f.type, b64: s.b64 })) }) });
        const d = await r.json().catch(() => ({}));
        if (r.ok && !d.error) { got = d.fields || {}; for (const x of d.docs || []) types[x.name] = x.type || ''; }
      } catch (e) {}
    }
    await w.step(2);
    const memo = ls.get('formMemo', {}) || {};
    const filled = MEMO_KEYS.filter(k => got[k] && !(memo[k] || '').trim());
    filled.forEach(k => { memo[k] = got[k]; });
    if (filled.length) { if (memo.office && !memo.address) memo.address = memo.office; if (memo.ceo && !memo.applicant) memo.applicant = memo.ceo; ls.set('formMemo', memo); }
    const note = filled.length ? `AI가 회사 정보 ${filled.length}칸을 채웠어요` : '';
    await w.step(3);
    let placed = 0;
    for (const s of saved) {
      if (slot) { if (s === saved[0] && note) setSlot(slot, s.name, note); continue; }
      const text = `${types[s.name] || ''} ${s.name}`;
      const d = free().find(x => x.re.test(text));
      if (d) { setSlot(d.name, s.name, s === saved[0] ? note : ''); justSet.add(d.name); placed++; }
    }
    await w.done();
    await renderProj();
    toast(slot ? `'${slot}' 칸에 넣었어요${note ? ' · ' + note : ''}`
      : `${saved.length}개 넣음 · ${placed}개는 칸에 맞췄어요${saved.length > placed ? `, ${saved.length - placed}개는 '그 밖의 서류'에` : ''}${note ? ' · ' + note : ''}`);
  }

  if (typeof window.saveConv === 'function') {
    const orig = window.saveConv;
    window.saveConv = function () {
      const r = orig.apply(this, arguments);
      if (cur && typeof window.loadHist === 'function') {
        const c = window.loadHist()[0];
        if (c) {
          const convs = [c, ...(cur.convs || []).filter(x => x.id !== c.id)];
          const profile = ls.get('h2profile', cur.profile);
          A.projects.save(cur.id, { convs, profile }).then(p => { if (p) cur = p; }).catch(() => {});
        }
      }
      return r;
    };
  }

  async function renderProj() {
    const body = projD.querySelector('.h2a-body');
    if (!cur) {
      const list = await A.projects.list();
      body.innerHTML = `<div class="h2a-sec"><h3>새 사업장</h3>
        <div class="h2a-line"><input class="h2a-in" id="h2a-newname" placeholder="예: 평창 수소충전소" maxlength="60"><button class="h2a-b pri" id="h2a-new">만들기</button></div>
        <small style="color:var(--ink-2)">대화·신청서·서류·일정을 사업장별로 내 PC(${esc(info.docs || '내 문서')})에 묶어 둡니다. 서버에는 보내지 않습니다.</small></div>
        <div class="h2a-sec"><h3>내 사업장</h3>${list.length ? '' : '<div class="h2a-empty">아직 사업장이 없습니다.</div>'}<div id="h2a-plist"></div></div>`;
      const box = body.querySelector('#h2a-plist');
      for (const p of list) {
        const r = document.createElement('div'); r.className = 'h2a-row click';
        const kind = permits.find(x => x.id === p.kind);
        r.innerHTML = `<div class="t"><b>${esc(p.name)}</b><small>${esc(kind ? kind.title : '허가 종류 미정')} · 서류 ${p.files} · 남은 일정 ${p.dates}</small></div><span style="color:var(--accent)">열기 ›</span>`;
        r.onclick = async () => { await openProject(p.id); renderProj(); };
        box.appendChild(r);
      }
      const make = async () => {
        const name = body.querySelector('#h2a-newname').value.trim();
        if (!name) return body.querySelector('#h2a-newname').focus();
        try { const p = await A.projects.create(name); await openProject(p.id); renderProj(); toast(`'${p.name}' 사업장을 열었습니다. 이제 내려받는 신청서는 이 사업장 폴더에 저장됩니다.`); }
        catch (e) { toast(String(e.message || e).replace(/^Error invoking remote method '[^']+': (Error: )?/, '')); }
      };
      body.querySelector('#h2a-new').onclick = make;
      body.querySelector('#h2a-newname').onkeydown = e => { if (e.key === 'Enter') make(); };
      return;
    }
    await refresh();
    if (!cur.kind && permits.length) { const r = recommend(); if (r) { cur = await A.projects.save(cur.id, { kind: r.id }); setKindAi(r.why); } }
    const kind = permits.find(x => x.id === cur.kind), ai = kind && kindAi();
    const dates = (cur.dates || []).slice().sort((a, b) => (a.done - b.done) || a.date.localeCompare(b.date));
    const docs = docSlots(kind), slots = slotMap();
    body.innerHTML = `
      <div class="h2a-pjhd"><div class="h2a-pjname">${esc(cur.name)}</div>
        <div class="h2a-more"><button class="h2a-x" id="h2a-more" title="더 보기">⋯</button>
          <div class="h2a-menu" hidden><button id="h2a-folder">폴더 열기</button><button id="h2a-close">사업장 닫기</button><button id="h2a-del" class="red">사업장 지우기</button></div></div></div>
      <div class="h2a-kindrow${ai != null ? ' ai' : ''}">${ai != null ? '<span class="h2a-aibadge">AI 추천</span>' : ''}<select class="h2a-chipsel" id="h2a-kind"><option value="">허가 종류 고르기</option>${permits.map(p => `<option value="${esc(p.id)}" ${p.id === cur.kind ? 'selected' : ''}>${esc(p.title)}</option>`).join('')}</select><span class="ar">▾</span></div>
      ${ai != null ? `<div class="h2a-why"><em>${esc(ai || '내 사업장')}</em> 사업장이라 이 허가가 먼저 필요해요. 다른 허가는 ▾ 에서 바꿀 수 있어요.</div>` : ''}
      ${kind ? `<div class="h2a-kindinfo">관할 ${esc(kind.who)} · 처리 ${esc(kind.days)}${kind.fee ? ' · 수수료 ' + esc(kind.fee) : ''}</div>` : ''}
      <label class="h2a-bigdrop" id="h2a-bigdrop"><div class="ic">📎</div><b>서류를 여기에 끌어다 놓으세요</b>
        <span>PDF·사진 모두 돼요. AI가 읽고 어떤 서류인지 맞춰 넣어요</span><span class="h2a-b ghost pick">파일 고르기</span>
        <input type="file" multiple hidden accept=".pdf,.png,.jpg,.jpeg,.webp,.hwp,.hwpx,.docx,.xlsx"></label>
      <div class="h2a-prog">${kind ? '이 허가에 낼 서류' : '낼 서류'}</div>
      ${kind && docs.length === 1 ? '<div class="h2a-kindinfo" style="margin:0 2px 6px">이 허가는 따로 붙일 서류 없이 신청서만 쓰면 돼요.</div>' : ''}
      <div id="h2a-req"></div>
      <div id="h2a-flist"></div>
      <div class="h2a-sec" style="margin-top:14px"><button class="h2a-b" id="h2a-revhere" style="width:100%;padding:11px">AI로 서류 전체 검토하기</button>${A.assist ? '<button class="h2a-b pri" id="h2a-assist" style="width:100%;padding:11px;margin-top:8px">신청 도우미로 신청하기</button>' : ''}</div>
      <div class="h2a-sec"><h3>일정 (예정일·마감일)<span class="sp"></span>${kind && /\d/.test(kind.days || '') ? `<button class="h2a-b ghost" id="h2a-due">오늘 접수 → 처리 예정일 넣기</button>` : ''}</h3>
        <div class="h2a-line"><input class="h2a-in" id="h2a-dt" placeholder="예: 보완 서류 제출 마감" maxlength="60"><input class="h2a-in" type="date" id="h2a-dd" style="flex:none;width:150px"><button class="h2a-b" id="h2a-addd">추가</button></div>
        <div id="h2a-dlist">${dates.length ? '' : '<div class="h2a-empty">일정을 넣어 두면 7일 전부터 앱을 켤 때 알려 드립니다.</div>'}</div></div>
      <div class="h2a-sec"><h3>저장한 대화 (${(cur.convs || []).length})</h3><div id="h2a-clist">${(cur.convs || []).length ? '' : '<div class="h2a-empty">이 사업장을 연 채로 물어본 대화가 자동으로 남습니다.</div>'}</div></div>
      <div class="h2a-sec"><h3>메모</h3><textarea class="h2a-in" id="h2a-notes" rows="3" style="width:100%;resize:vertical" placeholder="담당 공무원 연락처, 진행 상황 등">${esc(cur.notes || '')}</textarea></div>`;
    const q = s => body.querySelector(s);
    const menu = q('.h2a-menu');
    q('#h2a-more').onclick = e => { e.stopPropagation(); menu.hidden = !menu.hidden; };
    body.onclick = e => { if (!e.target.closest('.h2a-more')) menu.hidden = true; };
    // 서류 첨부: 큰 칸에 끌어놓기·고르기(AI가 종류를 맞춤), 줄마다 [첨부](그 칸에 바로)
    const big = q('#h2a-bigdrop'), pickIn = big.querySelector('input');
    big.ondragover = e => { e.preventDefault(); big.classList.add('over'); };
    big.ondragleave = () => big.classList.remove('over');
    big.ondrop = e => { e.preventDefault(); big.classList.remove('over'); attach([...e.dataTransfer.files], null); };
    pickIn.onchange = () => { attach([...pickIn.files], null); pickIn.value = ''; };
    const rq = q('#h2a-req'), byName = new Map((cur.files || []).map(f => [f.name, f]));
    for (const d of docs) {
      const fn = slots[d.name], f = fn && byName.get(fn);
      const r = document.createElement('div'); r.className = 'h2a-doc' + (f ? ' ok' : '') + (f && justSet.has(d.name) ? ' h2a-new' : '');
      r.innerHTML = `<span class="st">${f ? '✓' : ''}</span><div class="t"><b>${esc(d.name)}${d.req ? '<i>필수</i>' : '<i class="opt">선택</i>'}</b><small class="${f && d.note ? 'ai' : ''}">${esc(f ? (d.note || f.name) : d.hint)}</small></div>
        ${f ? '<button class="h2a-b ghost" data-open>열기</button><button class="h2a-b ghost" data-pick>바꾸기</button>' : '<button class="h2a-b" data-pick>첨부</button>'}<input type="file" hidden>`;
      const inp = r.querySelector('input');
      r.querySelector('[data-pick]').onclick = () => inp.click();
      inp.onchange = () => { if (inp.files[0]) attach([inp.files[0]], d.name); inp.value = ''; };
      if (f) r.querySelector('[data-open]').onclick = () => A.files.open(f.path);
      r.ondragover = e => { e.preventDefault(); r.classList.add('over'); };
      r.ondragleave = () => r.classList.remove('over');
      r.ondrop = e => { e.preventDefault(); r.classList.remove('over'); if (e.dataTransfer.files[0]) attach([e.dataTransfer.files[0]], d.name); };
      rq.appendChild(r);
    }
    justSet.clear();
    q('#h2a-folder').onclick = () => A.projects.folder(cur.id);
    q('#h2a-close').onclick = async () => { await closeProject(); renderProj(); };
    q('#h2a-kind').onchange = async e => { cur = await A.projects.save(cur.id, { kind: e.target.value }); setKindAi(null); renderProj(); };
    const saveDates = async ds => { cur = await A.projects.save(cur.id, { dates: ds }); renderProj(); checkNotices(); };
    q('#h2a-addd').onclick = () => {
      const title = q('#h2a-dt').value.trim(), date = q('#h2a-dd').value;
      if (!title || !date) return (title ? q('#h2a-dd') : q('#h2a-dt')).focus();
      saveDates([...(cur.dates || []), { id: Date.now().toString(36), title, date, done: false }]);
    };
    if (q('#h2a-due')) q('#h2a-due').onclick = () => {
      const n = parseInt(String(kind.days).match(/\d+/)[0], 10);
      saveDates([...(cur.dates || []), { id: Date.now().toString(36), title: `${kind.title} 처리 예정 (${today()} 접수, ${kind.days})`, date: addDays(today(), n), done: false }]);
    };
    const dl = q('#h2a-dlist');
    for (const d of dates) {
      const n = daysTo(d.date);
      const r = document.createElement('div'); r.className = 'h2a-row';
      r.innerHTML = `<input type="checkbox" ${d.done ? 'checked' : ''} title="끝남"><div class="t" style="${d.done ? 'opacity:.5;text-decoration:line-through' : ''}"><b>${esc(d.title)}</b><small>${esc(d.date)}</small></div>
        ${d.done ? '' : `<span class="h2a-tag ${n < 0 ? 'no' : n <= 7 ? 'wa' : 'ok'}">${n < 0 ? `${-n}일 지남` : n === 0 ? '오늘' : `D-${n}`}</span>`}<button class="h2a-x" title="지우기">✕</button>`;
      r.querySelector('input').onchange = e => saveDates(cur.dates.map(x => x.id === d.id ? { ...x, done: e.target.checked } : x));
      r.querySelector('.h2a-x').onclick = () => saveDates(cur.dates.filter(x => x.id !== d.id));
      dl.appendChild(r);
    }
    const fl = q('#h2a-flist'), used = new Set(Object.values(slots));
    const rest = (cur.files || []).filter(f => !used.has(f.name));
    if (rest.length) fl.insertAdjacentHTML('beforeend', `<div class="h2a-sub">그 밖의 서류 (${rest.length})</div>`);
    for (const f of rest) {
      const r = document.createElement('div'); r.className = 'h2a-row';
      r.innerHTML = `<div class="t"><b>${esc(f.name)}</b><small>${esc(f.added ? new Date(f.added).toLocaleDateString('ko-KR') : '')}</small></div><button class="h2a-b">열기</button><button class="h2a-x" title="폴더에서 보기">📂</button>`;
      r.querySelector('.h2a-b').onclick = () => A.files.open(f.path);
      r.querySelector('.h2a-x').onclick = () => A.files.show(f.path);
      fl.appendChild(r);
    }
    q('#h2a-revhere').onclick = () => { renderRev(true); open(revD); };
    const asb = q('#h2a-assist');
    if (asb) asb.onclick = () => {
      // 칸에 맞춘 서류만 경로로 넘긴다. 로그인·결제·제출은 도우미 창에서도 사용자가 직접 한다.
      const sm = slotMap(), byName = Object.fromEntries((cur.files || []).map(f => [f.name, f.path]));
      const files = Object.entries(sm).filter(([, n]) => byName[n]).map(([slot, n]) => ({ slot, path: byName[n] }));
      A.assist.open({ memo: ls.get('formMemo', {}) || {}, files, project: cur.name });
    };
    const cl = q('#h2a-clist');
    for (const c of cur.convs || []) {
      const r = document.createElement('div'); r.className = 'h2a-row click';
      r.innerHTML = `<div class="t"><b>${esc(c.title)}</b><small>${esc(c.t)} · ${(c.turns || []).length}번 물음</small></div><span style="color:var(--accent)">열기 ›</span>`;
      r.onclick = () => { if (typeof window.openConv === 'function') { close(); window.openConv(c); } };
      cl.appendChild(r);
    }
    let nt;
    q('#h2a-notes').oninput = e => { clearTimeout(nt); nt = setTimeout(async () => { cur = await A.projects.save(cur.id, { notes: e.target.value }); }, 600); };
    q('#h2a-del').onclick = async () => {
      if (!confirm(`'${cur.name}' 사업장 폴더를 휴지통으로 옮길까요? 휴지통에서 되살릴 수 있습니다.`)) return;
      const name = cur.name; await A.projects.remove(cur.id); cur = null; setCurLabel(); renderProj(); toast(`'${name}'을 휴지통으로 옮겼습니다`);
    };
  }

  // 내려받기가 끝나면 바로 열기·폴더 단추
  A.on('downloaded', d => {
    toast(d.project ? `'${cur ? cur.name : d.project}' 서류 폴더에 저장: ${d.name}` : `저장했습니다: ${d.name}`,
      [['열기', () => A.files.open(d.path)], ['폴더', () => A.files.show(d.path)]], 10000);
    if (cur && projD.classList.contains('open')) renderProj();
  });

  // ── 서류 폴더 검토 ──
  let rv = { dir: null, files: [], pick: new Set(), result: null, busy: false, local: [] };
  const READABLE = /^(pdf|png|jpe?g|webp|hwpx?|docx|xlsx|txt|csv)$/;
  async function choose(fn) {
    const r = await fn();
    if (!r) return;
    rv = { dir: r.dir, files: r.files, pick: new Set(r.files.filter(f => READABLE.test(f.ext)).slice(0, 10).map(f => f.rel)), result: null, busy: false, local: [] };
    renderRev();
  }
  async function renderRev(fromProject) {
    const body = revD.querySelector('.h2a-body');
    if (fromProject && cur) {
      // 사업장 서류 폴더를 바로 검토: 폴더 고르기 창이 사업장 서류 폴더에서 열린다.
      await choose(() => A.review.pick());
      return;
    }
    const kindId = (rv.kind) || (cur && cur.kind) || '';
    body.innerHTML = `
      <div class="h2a-sec"><h3>1. 무슨 신청인가요?</h3>
        <select class="h2a-in" id="h2a-rk" style="width:100%"><option value="">허가 종류 고르기</option>${permits.map(p => `<option value="${esc(p.id)}" ${p.id === kindId ? 'selected' : ''}>${esc(p.title)}</option>`).join('')}</select></div>
      <div class="h2a-sec"><h3>2. 서류 폴더</h3>
        <div class="h2a-drop" id="h2a-drop">${rv.dir ? `<b class="h2a-path">${esc(rv.dir)}</b>` : ''}폴더를 여기에 끌어다 놓거나 <button class="h2a-b" id="h2a-pick">폴더 고르기</button></div>
        <div id="h2a-rfiles" style="margin-top:10px"></div></div>
      <div class="h2a-sec" id="h2a-go"></div>
      <div class="h2a-sec" id="h2a-rres"></div>`;
    const q = s => body.querySelector(s);
    q('#h2a-rk').onchange = e => { rv.kind = e.target.value; rv.result = null; renderRev(); };
    q('#h2a-pick').onclick = () => choose(() => A.review.pick());
    const drop = q('#h2a-drop');
    drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); const f = e.dataTransfer.files[0]; if (f) choose(() => A.review.drop(f)); };

    const fl = q('#h2a-rfiles');
    if (rv.dir && !rv.files.length) fl.innerHTML = '<div class="h2a-empty">이 폴더에 파일이 없습니다.</div>';
    for (const f of rv.files) {
      const r = document.createElement('label'); r.className = 'h2a-row'; r.style.cursor = 'pointer';
      const can = READABLE.test(f.ext);
      r.innerHTML = `<input type="checkbox" ${rv.pick.has(f.rel) ? 'checked' : ''} ${can ? '' : 'disabled'}><div class="t"><b>${esc(f.rel)}</b><small>${kb(f.size)}${can ? '' : ' · 검토할 수 없는 형식'}</small></div>`;
      r.querySelector('input').onchange = e => {
        if (e.target.checked && rv.pick.size >= 10) { e.target.checked = false; return toast('한 번에 10개까지 검토합니다'); }
        e.target.checked ? rv.pick.add(f.rel) : rv.pick.delete(f.rel); renderGo();
      };
      fl.appendChild(r);
    }
    const renderGo = () => {
      const go = q('#h2a-go');
      if (!rv.dir) { go.innerHTML = ''; return; }
      go.innerHTML = `<button class="h2a-b pri" id="h2a-start" style="width:100%;padding:11px" ${rv.busy || !rv.pick.size || !q('#h2a-rk').value ? 'disabled' : ''}>
        ${rv.busy ? '<span class="h2a-spin"></span>AI 가 서류를 읽는 중… (최대 1분)' : `3. 고른 ${rv.pick.size}개 검토하기`}</button>
        ${!q('#h2a-rk').value ? '<small style="color:var(--ink-2)">허가 종류를 먼저 골라 주세요.</small>' : ''}`;
      const st = q('#h2a-start'); if (st) st.onclick = start;
    };
    renderGo();
    renderResult(q('#h2a-rres'));

    async function start() {
      const kind = q('#h2a-rk').value;
      rv.kind = kind; rv.busy = true; rv.result = null; renderGo(); renderResult(q('#h2a-rres'));
      try {
        const files = await A.review.read([...rv.pick]);
        rv.local = files.filter(f => f.warn);
        const send = files.filter(f => !f.warn);
        if (!send.length) { rv.result = { error: '읽을 수 있는 파일이 없습니다', files: [], missing: [] }; return; }
        const r = await fetch('/api/app/review', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ permit: kind, files: send.map(f => ({ name: f.rel, kind: f.kind, mime: f.mime, b64: f.b64, text: f.text, cut: f.cut, note: f.note })) }) });
        rv.result = await r.json().catch(() => ({ error: '서버 답을 읽지 못했습니다' }));
        rv.result.at = new Date().toLocaleString('ko-KR');
      } catch (e) { rv.result = { error: String(e.message || e) }; }
      finally { rv.busy = false; renderRev(); }
    }
  }
  function renderResult(box) {
    const r = rv.result;
    if (!r) { box.innerHTML = ''; return; }
    if (r.error) { box.innerHTML = `<div class="h2a-sum" style="background:#ffeef0;color:#d0283c">${esc(r.error)}</div>`; return; }
    const byDoc = new Map();
    for (const f of r.files) if (f.doc !== '기타') (byDoc.get(f.doc) || byDoc.set(f.doc, []).get(f.doc)).push(f);
    const okN = r.permit.docs.filter(d => (byDoc.get(d) || []).some(f => f.ok)).length;
    box.innerHTML = `<h3 style="font-size:var(--fs-s);color:var(--ink-2);margin:0 0 8px">검토 결과 · ${esc(r.permit.title)}</h3>
      <div class="h2a-sum"><b>필수 서류 ${okN}/${r.permit.docs.length} 준비됨</b>${r.missing.length ? ` · 빠진 서류 ${r.missing.length}개` : ''}<br>${esc(r.summary)}</div>
      <div id="h2a-docs"></div><div id="h2a-other"></div>
      <div style="display:flex;gap:6px;margin-top:10px"><button class="h2a-b" id="h2a-saverep">결과 저장${cur ? ' (사업장 서류 폴더)' : ''}</button><button class="h2a-b ghost" id="h2a-ask">빠진 서류 물어보기</button></div>
      <small style="color:var(--ink-2);display:block;margin-top:8px">AI 검토는 참고용입니다. 최종 판단은 관할 기관(${esc(r.permit.who)})에 확인하세요. · ${esc(r.at || '')}</small>`;
    const docs = box.querySelector('#h2a-docs');
    for (const d of r.permit.docs) {
      const fs = byDoc.get(d) || [];
      const good = fs.some(f => f.ok);
      const el = document.createElement('div'); el.className = 'h2a-row'; el.style.alignItems = 'flex-start';
      el.innerHTML = `<div class="t"><b style="white-space:normal">${esc(d)}<span class="h2a-tag ${good ? 'ok' : fs.length ? 'wa' : 'no'}">${good ? '준비됨' : fs.length ? '고칠 곳 있음' : '없음'}</span></b>
        ${fs.map(f => `<small>${esc(f.name)}</small>${f.issues.length ? `<ul class="h2a-issues">${f.issues.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}`).join('<br>')}</div>`;
      docs.appendChild(el);
    }
    const other = r.files.filter(f => f.doc === '기타');
    const oth = box.querySelector('#h2a-other');
    if (other.length || rv.local.length) {
      oth.innerHTML = `<h3 style="font-size:var(--fs-s);color:var(--ink-2);margin:12px 0 8px">그 밖의 파일</h3>`
        + other.map(f => `<div class="h2a-row" style="align-items:flex-start"><div class="t"><b>${esc(f.name)}<span class="h2a-tag wa">필수 서류 아님</span></b>${f.issues.length ? `<ul class="h2a-issues">${f.issues.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}</div></div>`).join('')
        + rv.local.map(f => `<div class="h2a-row"><div class="t"><b>${esc(f.rel)}<span class="h2a-tag no">못 읽음</span></b><small>${esc(f.warn)}</small></div></div>`).join('');
    }
    box.querySelector('#h2a-saverep').onclick = async () => {
      const lines = [`서류 폴더 검토 결과 - ${r.permit.title}`, `검토 시각: ${r.at}`, `폴더: ${rv.dir}`, '', r.summary, '',
        ...r.permit.docs.flatMap(d => { const fs = byDoc.get(d) || []; return [`[${fs.some(f => f.ok) ? '준비됨' : fs.length ? '고칠 곳 있음' : '없음'}] ${d}`, ...fs.flatMap(f => [`   - ${f.name}`, ...f.issues.map(i => `       * ${i}`)])]; }),
        '', ...other.map(f => `[필수 서류 아님] ${f.name}`), ...rv.local.map(f => `[못 읽음] ${f.rel}: ${f.warn}`),
        '', `AI 검토는 참고용입니다. 최종 판단은 ${r.permit.who}에 확인하세요.`];
      const b64 = btoa(String.fromCharCode(...new TextEncoder().encode('﻿' + lines.join('\r\n'))));
      const p = await A.files.save(`서류검토_${today()}.txt`, b64);
      if (p) toast('검토 결과를 저장했습니다', [['열기', () => A.files.open(p)]]);
    };
    box.querySelector('#h2a-ask').onclick = () => {
      const input = document.querySelector('#q');
      if (!input) return;
      close();
      input.value = r.missing.length ? `${r.permit.title}에 필요한 ${r.missing.join(', ')}는 어떻게 준비해?` : `${r.permit.title} 서류를 다 준비했어. 다음 절차는?`;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    };
  }

  // ── 알림: 일정(7일 전부터)·법령 개정·새 버전. 앱을 켤 때, 그리고 켜 둔 동안 6시간마다 ──
  let bellItems = [];
  function badge() {
    const seen = new Set(ls.get('h2aBellSeen', []));
    const n = bellItems.filter(i => !seen.has(i.key)).length;
    let b = bellBtn.querySelector('.h2a-badge');
    if (!n) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement('span'); b.className = 'h2a-badge'; bellBtn.appendChild(b); }
    b.textContent = n > 9 ? '9+' : n;
  }
  async function checkNotices() {
    const items = [];
    try {
      for (const d of await A.projects.dates()) {
        const n = daysTo(d.date);
        if (n > 7) continue;
        items.push({ key: `d:${d.project}:${d.id}:${n < 0 ? 'late' : n}`, kind: 'date', project: d.project,
          title: `${d.name} · ${d.title}`, body: n < 0 ? `${-n}일 지났습니다 (${d.date})` : n === 0 ? `오늘입니다 (${d.date})` : `${n}일 남았습니다 (${d.date})` });
      }
    } catch (e) {}
    try {
      const since = ls.get('h2aLawSince', null) || new Date(Date.now() - 30 * 86400e3).toISOString();
      const r = await fetch('/api/app/notices?since=' + encodeURIComponent(since)).then(x => x.json());
      for (const l of r.laws || []) items.push({ key: `l:${l.law}:${l.promulgated}`, kind: 'law', link: l.link,
        title: `법령 개정 · ${l.law}`, body: `${l.kind ? l.kind + ' · ' : ''}공포 ${l.promulgated}${l.effective ? ` · 시행 ${l.effective}` : ''}` });
      const v = r.version;
      if (v && newer(v.version, info.version)) items.push({ key: `v:${v.version}`, kind: 'ver', link: v.url,
        title: `새 버전 ${v.version}`, body: `${v.notes || ''} (지금 ${info.version})${v.url ? '' : ' · 새 설치 파일을 받아 설치해 주세요'}` });
    } catch (e) {}
    bellItems = items;
    // 윈도우 알림은 처음 보는 것만, 한 번에 3개까지
    const told = new Set(ls.get('h2aTold', []));
    const fresh = items.filter(i => !told.has(i.key));
    for (const i of fresh.slice(0, 3)) A.notify(i.title, i.body);
    if (fresh.length > 3) A.notify('알림 ' + (fresh.length - 3) + '개 더', '앱 위쪽 종 모양 단추에서 확인하세요');
    ls.set('h2aTold', [...told, ...fresh.map(i => i.key)].slice(-300));
    badge();
    if (bellD.classList.contains('open')) renderBell();
  }
  function renderBell() {
    const body = bellD.querySelector('.h2a-body');
    const group = (k, h) => {
      const xs = bellItems.filter(i => i.kind === k);
      return `<div class="h2a-sec"><h3>${h}</h3>${xs.length ? xs.map((i, n) => `<div class="h2a-row ${i.link || i.project ? 'click' : ''}" data-k="${esc(k)}" data-i="${n}"><div class="t"><b style="white-space:normal">${esc(i.title)}</b><small>${esc(i.body)}</small></div></div>`).join('') : '<div class="h2a-empty">없음</div>'}</div>`;
    };
    body.innerHTML = group('date', '다가오는 일정 (7일 안·지난 것)') + group('law', '법령 개정 (최근 30일)') + group('ver', '앱 업데이트')
      + `<small style="color:var(--ink-2)">앱 버전 ${esc(info.version)} · 앱을 켤 때와 켜 둔 동안 6시간마다 확인합니다.</small>`;
    body.querySelectorAll('.h2a-row.click').forEach(r => r.onclick = async () => {
      const i = bellItems.filter(x => x.kind === r.dataset.k)[Number(r.dataset.i)];
      if (i.project) { await openProject(i.project); renderProj(); open(projD); }
      else if (i.link) window.open(i.link, '_blank');
    });
  }
  A.on('noticeClick', () => { renderBell(); open(bellD); });

  // ── 시작 ──
  (async () => {
    info = await A.info().catch(() => ({}));
    permits = await fetch('/api/permit/forms').then(r => r.json()).catch(() => []);
    if (!Array.isArray(permits)) permits = [];
    const last = ls.get('h2aLastProject', null);
    if (last) { try { await openProject(last); } catch (e) {} }
    setCurLabel();
    checkNotices();
    setInterval(checkNotices, 6 * 3600e3);
  })();
})();
