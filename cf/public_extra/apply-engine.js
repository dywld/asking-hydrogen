// 신청 도우미가 민원 사이트 안에서 돌리는 코드. 앱은 별도 세계(isolated world)에 넣고(lib/assist.js),
// 웹 시연은 같은 출처 iframe 안에 넣는다(cf/public_extra/apply-engine.js 는 이 파일의 복사본).
// 하는 일: 칸 이름 읽기, 한 글자씩 채우기, 첨부 칸 표시. 하지 않는 일: 로그인·결제·[신청·제출] 누르기.
// 검색·페이지 넘김(tour)은 <meta name="h2a-tour"> 가 있는 예시 화면에서만 한다.
window.__h2a = window.__h2a || (() => {
  const RULES = [
    ['mgr_name', /안전\s*관리\s*(자|책임자).*(성명|이름)/], ['mgr_no', /자격.*번호/], ['mgr_qual', /자격/],
    ['bizno', /사업자.*번호|사업자\s*등록/], ['company', /상호|법인\s*명|업체\s*명|회사\s*명|명칭/],
    ['ceo', /대표자|대표\s*성명|^\s*성명/], ['site', /사업장.*(소재지|주소)|설치\s*(장소|위치)|시설.*(위치|소재지)|소재지/],
    ['office', /주소|본점/], ['tel', /전화|연락처|휴대/], ['email', /이메일|전자\s*우편|e-?mail/i],
    ['cap', /저장\s*능력|용량/], ['gas', /가스.*(종류|명)/], ['permit_no', /허가\s*번호/], ['permit_date', /허가\s*(일자|일)/],
  ];
  const txt = n => (n && (n.innerText || n.textContent) || '').replace(/\s+/g, ' ').trim();
  const vis = e => e.offsetParent !== null;
  const TOUR = !!document.querySelector('meta[name="h2a-tour"]');
  function labelOf(el) {
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l && txt(l)) return txt(l); }
    const wrap = el.closest('label'); if (wrap && txt(wrap)) return txt(wrap);
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const cell = el.closest('td,dd');
    if (cell) {
      let p = cell.previousElementSibling;
      while (p && !txt(p)) p = p.previousElementSibling;
      if (p) return txt(p);
    }
    let s = el.previousElementSibling; if (s && txt(s) && txt(s).length < 30) return txt(s);
    return el.title || el.placeholder || el.name || '';
  }
  let layer, cur;
  function ui() {
    if (layer && layer.isConnected) return;
    layer = document.createElement('div');
    layer.style.cssText = 'position:absolute;left:0;top:0;width:0;height:0;z-index:2147483646;pointer-events:none';
    document.body.appendChild(layer);
    const st = document.createElement('style');
    st.textContent = '.h2a-hl{outline:2px solid #3182f6!important;box-shadow:0 0 0 4px rgba(49,130,246,.18)!important;background:#f3f8ff!important;transition:all .2s}'
      + '.h2a-now{outline:2px solid #3182f6!important;box-shadow:0 0 0 6px rgba(49,130,246,.3)!important}'
      + '.h2a-me{outline:3px solid #e07b00!important;box-shadow:0 0 0 6px rgba(224,123,0,.25)!important}'
      + '.h2a-press{transform:scale(.96);box-shadow:0 0 0 6px rgba(49,130,246,.35)!important;transition:all .12s}'
      + '@keyframes h2aRing{from{transform:translate(-50%,-50%) scale(.3);opacity:.9}to{transform:translate(-50%,-50%) scale(1.6);opacity:0}}';
    document.head.appendChild(st);
    cur = document.createElement('div');
    cur.style.cssText = 'position:absolute;left:40px;top:40px;transition:left .42s ease,top .42s ease;pointer-events:none';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,.3))"><path d="M3 2l7 19 2.5-7.5L20 11z" fill="#3182f6" stroke="#fff" stroke-width="1.5"/></svg>'
      + '<span style="position:absolute;left:20px;top:18px;background:#3182f6;color:#fff;font:700 11px/1.6 sans-serif;border-radius:6px;padding:1px 7px;white-space:nowrap">수소문 AI</span>';
    layer.appendChild(cur);
  }
  function tag(el, text, color, above) {
    const r = el.getBoundingClientRect(), b = document.createElement('span');
    b.textContent = text;
    const pos = above ? 'left:' + (r.left + scrollX + r.width / 2 - 48) + 'px;top:' + (r.top + scrollY - 26) + 'px'
      : 'left:' + (r.right + scrollX - 66) + 'px;top:' + (r.top + scrollY + r.height / 2 - 9) + 'px';
    b.style.cssText = 'position:absolute;font:700 11px/1.5 sans-serif;color:' + color + ';background:#fff;border:1px solid ' + color + '55;border-radius:999px;padding:0 7px;white-space:nowrap;' + pos;
    layer.appendChild(b);
  }
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function point(el, center) {
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    await sleep(320);
    const r = el.getBoundingClientRect();
    cur.style.left = (r.left + scrollX + (center ? r.width / 2 - 4 : Math.min(r.width - 30, 120))) + 'px'; cur.style.top = (r.top + scrollY + r.height / 2) + 'px';
    await sleep(430);
  }
  function ring(el) {
    const r = el.getBoundingClientRect(), d = document.createElement('i');
    d.style.cssText = 'position:absolute;width:44px;height:44px;border-radius:50%;border:3px solid #3182f6;left:' + (r.left + scrollX + r.width / 2) + 'px;top:' + (r.top + scrollY + r.height / 2) + 'px;animation:h2aRing .5s ease-out forwards';
    layer.appendChild(d); setTimeout(() => d.remove(), 600);
  }
  async function typeInto(el, value) {
    el.classList.add('h2a-now'); el.focus();
    const set = Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set;
    let v = '';
    for (const ch of String(value)) { v += ch; set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); await sleep(26); }
    el.dispatchEvent(new Event('change', { bubbles: true })); el.blur();
    el.classList.remove('h2a-now');
  }
  function nextTour() {
    if (!TOUR) return null;
    const t = [...document.querySelectorAll('[data-h2a-type]')].find(e => vis(e) && !e.value);
    if (t) return { el: t, kind: 'type', label: t.dataset.h2aLabel || '검색' };
    const c = [...document.querySelectorAll('[data-h2a-click]')].find(vis);
    return c ? { el: c, kind: 'click', label: c.dataset.h2aClick } : null;
  }
  return {
    // 페이지가 바뀌면 지난 화면의 표시(배지·번호)를 지운다. 커서는 남긴다.
    clear() {
      if (layer) [...layer.children].forEach(c => { if (c !== cur) c.remove(); });
      document.querySelectorAll('[data-h2a-i],[data-h2a-f]').forEach(e => { delete e.dataset.h2aI; delete e.dataset.h2aF; });
      document.querySelectorAll('.h2a-me').forEach(e => e.classList.remove('h2a-me'));
      return 0;
    },
    busy() { return !!document.body.dataset.h2aBusy; },
    scan(memo) {
      ui();
      const used = new Set(), fields = [], files = [];
      const els = [...document.querySelectorAll('input, textarea, select')].filter(vis);
      els.forEach((el, i) => {
        const t = (el.type || '').toLowerCase(), lab = labelOf(el);
        if (el.hasAttribute('data-h2a-type')) return;
        if (t === 'file') { el.dataset.h2aF = i; files.push({ i, label: lab }); return; }
        if (/hidden|password|checkbox|radio|submit|button|image|reset|search/.test(t) || el.tagName === 'SELECT') return;
        const hit = RULES.find(([k, re]) => re.test(lab) && memo[k] && !used.has(k));
        if (!hit) { if (!el.value) fields.push({ i, label: lab, key: null }); return; }
        used.add(hit[0]); el.dataset.h2aI = i;
        fields.push({ i, label: lab, key: hit[0], has: !!el.value });
      });
      // 예시 화면에서 AI가 아직 넘어갈 화면이면 주황 표시를 하지 않는다(마지막 화면에서만).
      const submits = TOUR && nextTour() ? [] : [...document.querySelectorAll('button, input[type=submit], input[type=button], a')]
        .filter(b => vis(b) && !b.hasAttribute('data-h2a-click') && /신청|제출|접수|결제|납부/.test(txt(b) || b.value || ''));
      submits.forEach(b => { b.classList.add('h2a-me'); tag(b, '직접 눌러 주세요', '#e07b00', true); });
      return { fields, files, login: !!document.querySelector('input[type=password]'), submits: submits.length, title: document.title, tour: TOUR };
    },
    async fill(i, value) {
      const el = document.querySelector('[data-h2a-i="' + i + '"]'); if (!el || el.value) return false;
      await point(el);
      await typeInto(el, value);
      el.classList.add('h2a-hl'); tag(el, 'AI 채움', '#3182f6');
      return true;
    },
    async fileDone(i) {
      const el = document.querySelector('[data-h2a-f="' + i + '"]'); if (!el) return;
      await point(el); el.classList.add('h2a-hl'); tag(el, '서류 올림', '#12a36b');
    },
    // 예시 화면의 다음 할 일(검색어 넣기, 버튼 누르기)을 알려 주고, act()로 한다.
    tour() { const t = nextTour(); return t ? { kind: t.kind, label: t.label } : null; },
    async act() {
      const t = nextTour(); if (!t) return false;
      await point(t.el, t.kind === 'click');
      if (t.kind === 'type') { await typeInto(t.el, t.el.dataset.h2aType); t.el.classList.add('h2a-hl'); await sleep(200); return true; }
      t.el.classList.add('h2a-press'); ring(t.el); await sleep(220); t.el.classList.remove('h2a-press');
      this.clear();
      t.el.click();
      return true;
    },
    // 끝나면 사용자가 누를 제출 버튼을 화면에 보여 주고 커서를 옆에 둔다(누르지는 않는다).
    async showSubmit() {
      const b = document.querySelector('.h2a-me'); if (!b) return false;
      b.scrollIntoView({ block: 'center', behavior: 'smooth' }); await sleep(400);
      const r = b.getBoundingClientRect();
      cur.style.left = (r.right + scrollX + 14) + 'px'; cur.style.top = (r.top + scrollY + r.height / 2 + 6) + 'px';
      return true;
    },
  };
})(); 0;
