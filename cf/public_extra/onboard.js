// 처음 설정(온보딩). 처음 한 번만 뜨고, 건너뛸 수 있고, 설정(톱니)에서 다시 열 수 있다.
//   ① 내 PC 프로필(이름) → ② 서류 폴더(있으면 AI 가 읽어 회사 정보를 채움, 없으면 직접 입력)
//   → ③ 기업 정보(회사·대표·사업자번호·주소·연락처) → ④ 시설 정보(종류·위치·단계) → 완료
// 저장은 이 컴퓨터(localStorage)에만: formMemo(신청서 공통 칸), h2profile(사업 정보), h2onboard(설정 기록).
// 서류를 읽을 때만 파일 내용이 /api/app/extract 를 거쳐 Gemini 로 가고, 서버에는 남지 않는다.
(function () {
  if (window.h2onboard) return;
  const A = window.h2app || null;                 // 윈도우 앱이면 폴더를 통째로 고를 수 있다
  const ls = {
    get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // index.html 의 KINDS·STAGES·SIDO 와 같은 값(h2profile 을 같이 쓴다)
  const KINDS = ['수소충전소', '수소 생산', '저장·운송', '수소용품 제조', '연료전지 발전'];
  const STAGES = ['구상', '설계', '허가 신청', '운영 중'];
  const GASES = ['압축수소', '액화수소'];
  const SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'];
  const fmtBiz = v => { const d = String(v).replace(/\D/g, '').slice(0, 10); return d.length > 5 ? `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}` : d.length > 3 ? `${d.slice(0, 3)}-${d.slice(3)}` : d; };
  const fmtTel = v => {
    const d = String(v).replace(/\D/g, '').slice(0, 11);
    if (d.startsWith('02')) return d.length > 9 ? `02-${d.slice(2, 6)}-${d.slice(6)}` : d.length > 5 ? `02-${d.slice(2, 5)}-${d.slice(5)}` : d.length > 2 ? `02-${d.slice(2)}` : d;
    return d.length > 10 ? `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}` : d.length > 6 ? `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}` : d.length > 3 ? `${d.slice(0, 3)}-${d.slice(3)}` : d;
  };

  const LOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg>';
  const IC = {
    folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.6l2 2.2h7.4A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/></svg>',
    pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
    doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg>',
    ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  };
  const H = '<span>H<sub>2</sub></span>';

  const css = document.createElement('style');
  css.textContent = `
  .h2o{position:fixed;inset:0;z-index:9999;background:#fff;color:#191f28;display:flex;flex-direction:column;align-items:center;
    font:16px/1.55 Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;opacity:0;transition:opacity .3s ease}
  .h2o.show{opacity:1}
  .h2o *{box-sizing:border-box}
  .h2o-top{width:100%;max-width:520px;padding:18px 20px 0;display:flex;align-items:center;gap:10px;min-height:58px}
  .h2o-back{width:36px;height:36px;border:0;background:none;border-radius:10px;color:#4e5968;cursor:pointer;display:grid;place-items:center;padding:0}
  .h2o-back:hover{background:#f2f4f6} .h2o-back svg{width:22px;height:22px} .h2o-back[hidden]{visibility:hidden;display:grid}
  .h2o-bar{flex:1;display:flex;gap:6px}
  .h2o-seg{flex:1;height:5px;border-radius:5px;background:#e5e8eb;overflow:hidden}
  .h2o-seg i{display:block;height:100%;width:0;background:#3182f6;border-radius:5px;transition:width .5s cubic-bezier(.2,.8,.2,1)}
  .h2o-cnt{font-size:13px;color:#8b95a1;min-width:34px;text-align:right;font-variant-numeric:tabular-nums}
  .h2o-skip{border:0;background:none;color:#8b95a1;font:inherit;font-size:14px;cursor:pointer;padding:6px 4px}
  .h2o-skip:hover{color:#4e5968}
  .h2o-sec{width:100%;max-width:520px;padding:6px 20px 0 66px;font-size:13px;color:#3182f6;font-weight:600;min-height:26px}
  .h2o-main{flex:1;width:100%;max-width:520px;position:relative;overflow:hidden}
  .h2o-page{position:absolute;inset:0;padding:22px 24px 12px;overflow-y:auto;scrollbar-width:thin;transition:transform .42s cubic-bezier(.2,.8,.2,1),opacity .32s ease}
  .h2o-page.in{transform:translateX(36px);opacity:0} .h2o-page.out{transform:translateX(-36px);opacity:0}
  .h2o-page.in.rev{transform:translateX(-36px)} .h2o-page.out.rev{transform:translateX(36px)}
  .h2o h1{font-size:26px;line-height:1.38;margin:0 0 10px;font-weight:700;letter-spacing:-.02em;white-space:pre-line}
  .h2o .sub{color:#6b7684;margin:0 0 28px;font-size:15.5px;white-space:pre-line}
  .h2o-f{display:block;margin:0 0 22px}
  .h2o-sign{position:relative;height:220px;border:2px dashed #c9d6e8;border-radius:20px;background:#fbfcfe;margin:0 0 12px;touch-action:none}
  .h2o-sign.has{border-style:solid;border-color:#3182f6;background:#fff}
  .h2o-sign canvas{position:absolute;inset:0;width:100%;height:100%;cursor:crosshair}
  .h2o-sign .ph{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);color:#b0b8c1;font-size:18px;pointer-events:none}
  .h2o-sign.has .ph{display:none}
  .h2o-sign .clr{position:absolute;right:12px;top:12px;border:1px solid #e5e8eb;background:#fff;border-radius:10px;padding:5px 12px;font:inherit;font-size:13px;color:#4e5968;cursor:pointer}
  .h2o-f span{display:flex;align-items:center;gap:6px;font-size:13px;color:#6b7684;margin-bottom:4px}
  .h2o-f em{font-style:normal;font-size:11.5px;color:#3182f6;background:#e8f3ff;border-radius:5px;padding:1px 6px}
  .h2o-f input{width:100%;border:0;border-bottom:2px solid #e5e8eb;font:inherit;font-size:21px;padding:8px 0 9px;outline:none;background:transparent;color:#191f28;transition:border-color .2s}
  .h2o-f input:focus{border-bottom-color:#3182f6} .h2o-f input::placeholder{color:#c5ccd3}
  .h2o-chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 24px}
  .h2o-chip{border:1.5px solid #e5e8eb;background:#fff;border-radius:12px;padding:11px 16px;font:inherit;font-size:15.5px;color:#333d4b;cursor:pointer;transition:all .15s}
  .h2o-chip:hover{border-color:#b0d3ff} .h2o-chip.on{border-color:#3182f6;background:#e8f3ff;color:#1b64da;font-weight:600}
  .h2o-chip.cus{border-style:dashed;color:#6b7684} .h2o-chip.cus.on{border-style:solid}
  .h2o-tabhint{display:flex;align-items:center;gap:8px;font-size:13px;color:#8b95a1;margin:4px 0 0}
  .h2o-tabhint kbd{font:inherit;font-size:12px;font-weight:600;color:#4e5968;background:#f2f4f6;border:1px solid #e5e8eb;border-bottom-width:2px;border-radius:6px;padding:1px 7px}
  .h2o-f input.ex{animation:h2oFill .5s ease}
  @keyframes h2oFill{0%{background:#e8f3ff}100%{background:transparent}}
  .h2o-chips.sm .h2o-chip{padding:8px 13px;font-size:14.5px;border-radius:10px}
  .h2o-opt{display:flex;align-items:center;gap:16px;width:100%;text-align:left;border:1.5px solid #e5e8eb;background:#fff;border-radius:16px;padding:18px;margin:0 0 12px;font:inherit;cursor:pointer;transition:all .15s;color:#191f28}
  .h2o-opt:hover{border-color:#3182f6;background:#f7fbff;transform:translateY(-1px)}
  .h2o-opt i{flex:none;width:46px;height:46px;border-radius:14px;background:#e8f3ff;color:#3182f6;display:grid;place-items:center}
  .h2o-opt i svg{width:24px;height:24px} .h2o-opt.alt i{background:#f2f4f6;color:#6b7684}
  .h2o-opt b{display:block;font-size:17px} .h2o-opt small{display:block;color:#8b95a1;font-size:13.5px;margin-top:2px}
  .h2o-opt.drag{border-color:#3182f6;border-style:dashed;background:#f2f8ff}
  .h2o-note{background:#f9fafb;border-radius:12px;padding:12px 14px;font-size:13px;color:#6b7684;line-height:1.6}
  .h2o-note b{color:#4e5968}
  .h2o-drop{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;width:100%;min-height:170px;border:2px dashed #c9d6e8;border-radius:20px;background:#f7faff;color:#4e5968;font:inherit;cursor:pointer;transition:all .15s;margin:0 0 20px;padding:20px;text-align:center}
  .h2o-drop:hover,.h2o-drop.drag{border-color:#3182f6;background:#eef5ff}
  .h2o-drop i{width:52px;height:52px;border-radius:16px;background:#3182f6;color:#fff;display:grid;place-items:center;margin-bottom:6px}
  .h2o-drop i svg{width:26px;height:26px} .h2o-drop b{font-size:17px;color:#191f28} .h2o-drop small{font-size:13.5px;color:#8b95a1}
  .h2o-drop.busy{cursor:default;border-style:solid;border-color:#b0d3ff}
  .h2o-need{list-style:none;margin:0 0 18px;padding:0;border-top:1px solid #f2f4f6}
  .h2o-need li{display:flex;align-items:center;gap:12px;padding:12px 2px;border-bottom:1px solid #f2f4f6}
  .h2o-need .c{flex:none;width:24px;height:24px;border-radius:50%;border:2px solid #d1d6db;display:grid;place-items:center;transition:all .2s}
  .h2o-need .c svg{width:14px;height:14px;color:#fff;opacity:0}
  .h2o-need li.on .c{background:#3182f6;border-color:#3182f6} .h2o-need li.on .c svg{opacity:1}
  .h2o-need .t{flex:1;min-width:0} .h2o-need .t b{display:block;font-size:15.5px;font-weight:600} .h2o-need .t small{display:block;font-size:12.5px;color:#8b95a1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .h2o-need li.on .t small{color:#1b64da}
  .h2o-need .tag{flex:none;font-size:11.5px;font-weight:600;border-radius:6px;padding:2px 7px;background:#f2f4f6;color:#6b7684} .h2o-need .tag.req{background:#fff0f1;color:#e42939}
  .h2o-files{margin:0 0 18px;padding:0;list-style:none}
  .h2o-files li{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f2f4f6;font-size:14.5px;opacity:0;transform:translateY(6px);animation:h2oUp .35s ease forwards}
  .h2o-files li svg{flex:none;width:18px;height:18px;color:#8b95a1}
  .h2o-files li .n{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .h2o-files li .t{flex:none;font-size:12px;color:#1b64da;background:#e8f3ff;border-radius:6px;padding:2px 8px}
  .h2o-files li .t.x{color:#8b95a1;background:#f2f4f6}
  .h2o-files li .sp{flex:none;width:14px;height:14px;border:2px solid #e5e8eb;border-top-color:#3182f6;border-radius:50%;animation:h2oSpin .8s linear infinite}
  .h2o-found{background:#f2f8ff;border-radius:14px;padding:14px 16px;margin:0 0 18px}
  .h2o-found div{display:flex;gap:10px;font-size:14.5px;padding:3px 0} .h2o-found div span{color:#6b7684;width:92px;flex:none}
  .h2o-found div b{font-weight:600;min-width:0;overflow-wrap:anywhere}
  .h2o-err{background:#fff0f1;color:#e42939;border-radius:12px;padding:12px 14px;font-size:14px;margin:0 0 16px}
  .h2o-reading{display:flex;align-items:center;gap:10px;color:#3182f6;font-weight:600;margin:0 0 14px}
  .h2o-dots{display:inline-flex;gap:4px} .h2o-dots i{width:6px;height:6px;border-radius:50%;background:#3182f6;animation:h2oDot 1.2s ease-in-out infinite}
  .h2o-dots i:nth-child(2){animation-delay:.15s} .h2o-dots i:nth-child(3){animation-delay:.3s}
  .h2o-bot{width:100%;max-width:520px;padding:10px 20px 22px}
  .h2o-safe{display:flex;align-items:center;justify-content:center;gap:6px;font-size:13px;color:#6b7684;margin:0 0 10px}
  .h2o-safe svg{width:15px;height:15px;color:#3182f6}
  .h2o-go{width:100%;height:56px;border:0;border-radius:16px;background:#3182f6;color:#fff;font:inherit;font-size:17px;font-weight:600;cursor:pointer;transition:background .15s,transform .1s}
  .h2o-go:hover{background:#1b64da} .h2o-go:active{transform:scale(.985)}
  .h2o-go:disabled{background:#d1d6db;cursor:default}
  .h2o-go.ghost{background:#f2f4f6;color:#4e5968;margin-top:8px} .h2o-go.ghost:hover{background:#e5e8eb}
  .h2o-hero{display:flex;flex-direction:column;align-items:center;text-align:center;padding-top:1vh}
  .h2o-logo{width:84px;height:84px;border-radius:26px;background:linear-gradient(140deg,#4593fc,#1b64da);color:#fff;display:grid;place-items:center;
    font-size:30px;font-weight:800;margin:0 0 22px;box-shadow:0 12px 30px rgba(49,130,246,.28);animation:h2oFloat 3.2s ease-in-out infinite}
  .h2o-logo sub{font-size:16px;vertical-align:-4px}
  .h2o-steps{width:100%;margin:18px 0 0;text-align:left}
  .h2o-steps div{display:flex;align-items:center;gap:14px;padding:8px 4px;opacity:0;animation:h2oUp .45s ease forwards}
  .h2o-steps b{flex:none;width:30px;height:30px;border-radius:50%;background:#e8f3ff;color:#3182f6;font-size:14px;display:grid;place-items:center}
  .h2o-steps span{font-size:16px} .h2o-steps small{display:block;color:#8b95a1;font-size:13px}
  .h2o-done{display:flex;flex-direction:column;align-items:center;text-align:center;padding-top:7vh}
  .h2o-check{width:92px;height:92px;border-radius:50%;background:#3182f6;display:grid;place-items:center;margin:0 0 26px;transform:scale(.4);opacity:0;animation:h2oPop .5s cubic-bezier(.2,1.4,.4,1) .1s forwards}
  .h2o-check svg{width:50px;height:50px;color:#fff} .h2o-check path{stroke-dasharray:24;stroke-dashoffset:24;animation:h2oDraw .45s ease .5s forwards}
  .h2o-sum{width:100%;text-align:left;background:#f9fafb;border-radius:16px;padding:16px 18px;margin:22px 0 0;font-size:14.5px}
  .h2o-sum div{display:flex;gap:10px;padding:4px 0} .h2o-sum span{color:#8b95a1;width:76px;flex:none} .h2o-sum b{font-weight:600;min-width:0;overflow-wrap:anywhere}
  @keyframes h2oUp{to{opacity:1;transform:none}}
  @keyframes h2oSpin{to{transform:rotate(360deg)}}
  @keyframes h2oDot{0%,80%,100%{transform:scale(.6);opacity:.4}40%{transform:scale(1);opacity:1}}
  @keyframes h2oFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
  @keyframes h2oPop{to{transform:scale(1);opacity:1}}
  @keyframes h2oDraw{to{stroke-dashoffset:0}}
  @media (max-width:480px){.h2o h1{font-size:23px}.h2o-sec{padding-left:20px}.h2o-page{padding:18px 20px 12px}}
  @media (prefers-reduced-motion:reduce){.h2o *,.h2o{animation:none!important;transition:none!important}.h2o-files li,.h2o-steps div,.h2o-check{opacity:1;transform:none}.h2o-check path{stroke-dashoffset:0}}`;
  document.head.appendChild(css);

  // ── 화면 순서 ──
  // 기본 정보만 묻고 바로 챗봇으로 넘긴다(11/24 결정). 가스·안전관리자·허가번호는 신청서를 열 때 그 칸에서 채운다.
  const SECS = ['서류', '기업 정보', '시설 정보', '서명'];
  const PAGES = [
    { id: 'welcome' },
    { sec: 0, id: 'docs' },
    { sec: 1, title: '회사 이름과\n대표자를 알려 주세요', sub: '모르는 칸은 비워 두고 넘어가도 돼요.', fields: [{ k: 'company', label: '회사 이름 (상호)', ph: '예: 한빛수소 주식회사' }, { k: 'ceo', label: '대표자', ph: '예: 김대표' }] },
    { sec: 1, title: '사업자등록번호와\n회사 주소', sub: '사업자등록증에 적힌 그대로 써 주세요.', fields: [{ k: 'bizno', label: '사업자등록번호', ph: '000-00-00000', fmt: fmtBiz, mode: 'numeric' }, { k: 'office', label: '회사 주소 (사무소 소재지)', ph: '예: 서울특별시 중구 세종대로 110' }] },
    { sec: 1, title: '연락받을\n전화번호와 이메일', sub: '공사·관청이 연락할 때 쓰는 번호예요.', fields: [{ k: 'tel', label: '전화번호', ph: '02-0000-0000', fmt: fmtTel, mode: 'tel' }, { k: 'email', label: '이메일', ph: 'name@company.com', mode: 'email' }] },
    { sec: 2, title: '어떤 시설을\n준비하세요?', sub: '고르면 답이 이 시설에 맞춰져요.', chips: { k: 'kind', opts: KINDS, custom: '예: 수소 액화 플랜트' } },
    { sec: 2, title: '시설은\n어디에 짓나요?', sub: '관할 기관을 이 지역으로 안내해 드려요.', chips: { k: 'region', opts: SIDO, sm: true }, fields: [{ k: 'site', label: '시설 주소 (사업소 소재지)', ph: '예: 울산광역시 남구 ...' }] },
    { sec: 3, id: 'sign' },
    { id: 'done' },
  ];
  // 발표·시연용 예시(가상 회사). 빈칸에서 Tab 을 누르면 지금 화면만 이 값으로 채운다.
  const EX = { applicant: '김수소', company: '한빛수소 주식회사', ceo: '이한빛', bizno: '214-87-12345', office: '서울특별시 강동구 천호대로 1000',
    tel: '02-1234-5678', email: 'info@hanbit-h2.co.kr', kind: '수소충전소', region: '서울', site: '서울특별시 강동구 고덕동 123-4', stage: '설계',
    gas: '압축수소', cap: '3,000 ㎥', mgr_name: '박안전', mgr_qual: '가스산업기사', mgr_no: '20261234', permit_no: '제2027-03호', permit_date: '2027. 2. 1.' };
  const STEP_N = PAGES.length - 2;               // 환영·완료 화면은 세지 않는다

  let root, main, st;
  // 서류를 누가 읽는지 솔직하게: 서버 설정(OPENAI_API_KEY 유무)에 따라 이름을 바꾼다.
  let AI_NAME = '구글 Gemini';
  fetch('/api/status').then(r => r.json()).then(d => { if ((d.docs_provider || d.provider) === 'openai') AI_NAME = 'OpenAI ChatGPT'; }).catch(() => {});

  function open() {
    if (root) return;
    const memo = ls.get('formMemo', {}), prof = ls.get('h2profile', {}) || {}, ob = ls.get('h2onboard', {}) || {};
    let sign0 = ''; try { sign0 = localStorage.getItem('mySign') || ''; } catch (e) {}
    st = { sign: sign0, i: 0, v: { ...memo, kind: prof.kind || '', region: prof.region || '', stage: prof.stage || '' }, found: {}, docs: ob.docs || [], dir: ob.dir || '', reading: false, err: '', files: [] };
    root = document.createElement('div');
    root.className = 'h2o';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-label', '처음 설정');
    root.innerHTML = `<div class="h2o-top"><button class="h2o-back" title="뒤로" hidden>${IC.back}</button>
      <div class="h2o-bar">${SECS.map(() => '<div class="h2o-seg"><i></i></div>').join('')}</div>
      <span class="h2o-cnt"></span><button class="h2o-skip">건너뛰기</button></div>
      <div class="h2o-sec"></div><div class="h2o-main"></div>
      <div class="h2o-bot"><div class="h2o-safe">${LOCK}이 컴퓨터에만 저장돼요</div><button class="h2o-go">다음</button><div class="h2o-extra"></div></div>`;
    document.body.appendChild(root);
    main = root.querySelector('.h2o-main');
    root.querySelector('.h2o-back').onclick = () => go(st.i - 1);
    root.querySelector('.h2o-skip').onclick = () => finish(true);
    root.querySelector('.h2o-go').onclick = next;
    root.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing && e.target.tagName === 'INPUT') { e.preventDefault(); next(); } });
    requestAnimationFrame(() => root.classList.add('show'));
    render(0);
  }

  // Tab: 지금 화면의 빈칸(과 고르지 않은 칩)을 예시로 채운다. 채울 게 없으면 false -> 원래 Tab 동작.
  function example() {
    const p = PAGES[st.i];
    if (p && p.id === 'sign') return !st.sign && exampleSign();
    if (!p || p.id) return false;
    const ks = (p.fields || []).map(f => f.k).filter(k => !(st.v[k] || '').trim() && EX[k]);
    const chip = p.chips && !st.v[p.chips.k] && EX[p.chips.k];
    if (!ks.length && !chip) return false;
    if (chip) { st.v[p.chips.k] = EX[p.chips.k]; st.cus = false; }
    for (const k of ks) st.v[k] = EX[k];
    const page = main.querySelector('.h2o-page:not(.out)');
    form(page, p); buttons();
    ks.forEach(k => { const i = page.querySelector(`input[data-k="${k}"]`); if (i) i.classList.add('ex'); });
    const last = [...page.querySelectorAll('input[data-k]')].pop();
    if (last) last.focus({ preventScroll: true });
    if (chip && !(p.fields || []).length) setTimeout(() => { if (root && PAGES[st.i] === p) next(); }, 450);
    return true;
  }

  function close() {
    if (!root) return;
    root.classList.remove('show');
    const r = root; root = null;
    setTimeout(() => r.remove(), 300);
  }

  function next() {
    const p = PAGES[st.i];
    if (p.id === 'done') return close();
    if (p.id === 'docs' && st.reading) return;
    go(st.i + 1);
  }
  function go(i) {
    if (i < 0 || i >= PAGES.length || i === st.i) return;
    const back = i < st.i;
    st.i = i; st.cus = false;
    if (PAGES[i].id === 'done') save();
    render(back ? -1 : 1);
  }

  // 진행 막대: 구역 네 칸이 차례로 찬다(구역 안 화면 수만큼 나눠서).
  function bar() {
    const p = PAGES[st.i];
    const segs = root.querySelectorAll('.h2o-seg i');
    SECS.forEach((_, s) => {
      const inSec = PAGES.map((x, j) => [x, j]).filter(([x]) => x.sec === s);
      let w = 0;
      if (p.id === 'done' || (p.sec != null && p.sec > s)) w = 100;
      else if (p.sec === s) w = (inSec.findIndex(([, j]) => j === st.i) + 1) / inSec.length * 100;
      segs[s].style.width = w + '%';
    });
    const n = p.sec == null ? 0 : st.i;
    root.querySelector('.h2o-cnt').textContent = p.sec == null ? '' : `${n}/${STEP_N}`;
    root.querySelector('.h2o-sec').textContent = p.sec == null ? '' : SECS[p.sec];
    root.querySelector('.h2o-back').hidden = st.i === 0 || p.id === 'done';
    root.querySelector('.h2o-skip').style.visibility = p.id === 'done' ? 'hidden' : '';
    root.querySelector('.h2o-top').style.visibility = p.id === 'welcome' ? 'hidden' : '';
  }

  function render(dir) {
    const p = PAGES[st.i];
    const old = main.querySelector('.h2o-page:not(.out)');
    const page = document.createElement('div');
    page.className = 'h2o-page' + (dir ? ' in' + (dir < 0 ? ' rev' : '') : '');
    if (p.id === 'welcome') welcome(page);
    else if (p.id === 'docs') docs(page);
    else if (p.id === 'done') done(page);
    else if (p.id === 'sign') signPage(page);
    else form(page, p);
    main.appendChild(page);
    if (old) { old.classList.add('out'); if (dir < 0) old.classList.add('rev'); setTimeout(() => old.remove(), 450); }
    requestAnimationFrame(() => requestAnimationFrame(() => { page.classList.remove('in', 'rev'); }));
    bar();
    buttons();
    const first = page.querySelector('input');
    if (first && !matchMedia('(max-width:480px)').matches) setTimeout(() => first.focus({ preventScroll: true }), 380);
  }

  function buttons() {
    const p = PAGES[st.i], b = root.querySelector('.h2o-go'), ex = root.querySelector('.h2o-extra');
    ex.innerHTML = '';
    b.disabled = false;
    if (p.id === 'welcome') {
      b.textContent = '시작하기';
      ex.innerHTML = '<button class="h2o-go ghost">나중에 할게요</button>';
      ex.firstChild.onclick = () => finish(true);
    }
    else if (p.id === 'done') b.textContent = '질문하러 가기';
    else if (p.id === 'sign') {
      b.textContent = st.sign ? '다음' : '나중에 할게요';
      if (st.sign) { ex.innerHTML = '<button class="h2o-go ghost">다시 그리기</button>'; ex.firstChild.onclick = () => { st.sign = ''; signPage(main.querySelector('.h2o-page:not(.out)')); buttons(); }; }
    }
    else if (p.id === 'docs') {
      b.textContent = st.reading ? '서류를 읽고 있어요' : Object.keys(st.found).length ? '찾은 정보 확인하기' : st.docs.length ? '다음' : '서류 없이 직접 입력할게요';
      b.disabled = st.reading;
    } else b.textContent = filled(p) ? '다음' : '나중에 입력할게요';
  }
  const filled = p => (p.fields || []).some(f => (st.v[f.k] || '').trim()) || (p.chips && st.v[p.chips.k]);

  function welcome(page) {
    page.innerHTML = `<div class="h2o-hero"><div class="h2o-logo">${H}</div>
      <h1>사업장 정보만 알려 주시면\n답을 내 사업에 맞춰 드려요</h1>
      <p class="sub" style="margin-bottom:0">1~2분이면 끝나요.\n관할 기관·시설 기준을 내 사업장 기준으로 답하고, 신청서도 대신 채워 드려요.</p>
      <div class="h2o-steps">${[['서류', '사업자등록증을 넣으면 AI 가 읽어요 (건너뛰어도 돼요)'], ['기업 정보', '회사 이름·대표자·주소·연락처'], ['시설 정보', '어떤 시설을 어디에 짓는지'], ['서명', '한 번 그려 두면 신청서에 자동으로 들어가요']]
      .map(([t, s], i) => `<div style="animation-delay:${0.15 + i * 0.09}s"><b>${i + 1}</b><span>${t}<small>${s}</small></span></div>`).join('')}</div></div>`;
  }

  function form(page, p) {
    let h = `<h1>${esc(p.title)}</h1><p class="sub">${esc(p.sub || '')}</p>`;
    const cv = p.chips ? st.v[p.chips.k] || '' : '';
    const cusOn = p.chips && p.chips.custom && (st.cus || (cv && !p.chips.opts.includes(cv)));
    if (p.chips) h += `<div class="h2o-chips${p.chips.sm ? ' sm' : ''}">${p.chips.opts.map(o => `<button class="h2o-chip${cv === o && !cusOn ? ' on' : ''}" data-v="${esc(o)}">${esc(o)}</button>`).join('')}${p.chips.custom ? `<button class="h2o-chip cus${cusOn ? ' on' : ''}" data-cus="1">직접 입력</button>` : ''}</div>`;
    if (cusOn) h += `<label class="h2o-f"><span>시설 종류</span><input data-c="${p.chips.k}" placeholder="${esc(p.chips.custom)}" value="${esc(p.chips.opts.includes(cv) ? '' : cv)}" autocomplete="off" spellcheck="false"></label>`;
    for (const f of p.fields || []) {
      h += `<label class="h2o-f"><span>${esc(f.label)}${st.found[f.k] && st.found[f.k] === st.v[f.k] ? '<em>서류에서 찾음</em>' : ''}</span>
        <input data-k="${f.k}" placeholder="${esc(f.ph)}" value="${esc(st.v[f.k] || '')}" ${f.mode ? `inputmode="${f.mode}"` : ''} autocomplete="off" spellcheck="false"></label>`;
    }
    h += '<p class="h2o-tabhint"><kbd>Tab</kbd> 누르면 예시 정보로 채워져요</p>';
    page.innerHTML = h;
    const ci = page.querySelector('input[data-c]');
    if (ci) ci.oninput = () => { st.v[p.chips.k] = ci.value.trim().slice(0, 60); buttons(); };
    page.querySelectorAll('input[data-k]').forEach(inp => {
      const f = p.fields.find(x => x.k === inp.dataset.k);
      inp.oninput = () => {
        if (f.fmt) inp.value = f.fmt(inp.value);
        st.v[f.k] = inp.value.trim().slice(0, 120);
        const em = inp.parentElement.querySelector('em'); if (em && st.v[f.k] !== st.found[f.k]) em.remove();
        buttons();
      };
    });
    const cb = page.querySelector('[data-cus]');
    if (cb) cb.onclick = () => {
      st.cus = !cb.classList.contains('on');
      if (st.cus) st.v[p.chips.k] = '';
      form(page, p); buttons();
      const x = page.querySelector('input[data-c]'); if (x) x.focus();
    };
    page.querySelectorAll('.h2o-chip:not([data-cus])').forEach(c => c.onclick = () => {
      st.cus = false;
      const on = !c.classList.contains('on');
      page.querySelectorAll('.h2o-chip').forEach(x => x.classList.remove('on'));
      if (on) c.classList.add('on');
      st.v[p.chips.k] = on ? c.dataset.v : '';
      const old = page.querySelector('input[data-c]'); if (old) old.closest('label').remove();
      buttons();
      // 칩만 있는 화면은 고르면 잠깐 뒤 다음으로 넘어간다
      if (on && !(p.fields || []).length) setTimeout(() => { if (root && PAGES[st.i] === p) next(); }, 380);
    });
  }

  // ── 서류 ──  큰 칸 하나에 파일을 넣으면 AI 가 서류 종류를 알아서 나눠 아래 목록에 체크한다.
  const LABEL = { company: '회사 이름', ceo: '대표자', bizno: '사업자번호', office: '회사 주소', tel: '전화번호', email: '이메일', site: '시설 주소',
    mgr_name: '안전관리자', mgr_qual: '자격', mgr_no: '자격증 번호', permit_no: '허가번호', permit_date: '허가일' };
  const NEED = [
    { id: 'biz', name: '사업자등록증', req: true, hint: '회사 이름·대표자·사업자번호·주소', re: /사업자/ },
    { id: 'reg', name: '법인 등기사항증명서', hint: '법인이면 본점 주소·대표 확인', re: /등기/ },
    { id: 'mgr', name: '안전관리자 자격증', hint: '안전관리자 이름·자격·번호', re: /자격/ },
    { id: 'permit', name: '기존 허가증', hint: '이미 받은 허가가 있을 때', re: /허가/ },
  ];
  const needOf = t => (NEED.find(n => n.re.test(t || '')) || {}).id;
  function docs(page) {
    const found = Object.entries(st.found);
    let h = '<h1>갖고 있는 서류를\n넣어 주세요</h1><p class="sub">AI 가 읽고 회사 정보를 대신 채워 드려요.\n없으면 아래 버튼으로 직접 입력해도 돼요.</p>';
    h += st.reading
      ? `<div class="h2o-drop busy"><div class="h2o-reading" style="margin:0">AI 가 읽는 중<span class="h2o-dots"><i></i><i></i><i></i></span></div><small>${esc(st.files.map(f => f.name).join(', '))}</small></div>`
      : `<button class="h2o-drop" data-act="pick"><i>${IC.doc}</i><b>${st.docs.length ? '서류 더 넣기' : '여기를 눌러 파일 고르기'}</b><small>끌어다 놓아도 돼요 · 여러 개 한 번에 · PDF·사진·한글·워드</small></button>`;
    h += `<ul class="h2o-need">${NEED.map(n => { const d = st.docs.find(x => needOf(x.type) === n.id);
      return `<li class="${d ? 'on' : ''}"><span class="c">${IC.ok}</span><span class="t"><b>${n.name}</b><small>${d ? esc(d.name) : n.hint}</small></span><span class="tag${n.req ? ' req' : ''}">${n.req ? '필수' : '선택'}</span></li>`; }).join('')}</ul>`;
    const extra = st.docs.filter(d => !needOf(d.type));
    if (extra.length) h += `<ul class="h2o-files">${extra.map(d => `<li>${IC.doc}<span class="n">${esc(d.name)}</span><span class="t x">${esc(d.type)}</span></li>`).join('')}</ul>`;
    if (found.length) h += `<p class="sub" style="margin:0 0 10px">서류에서 <b style="color:#3182f6">${found.length}칸</b>을 찾았어요. 다음 화면에서 확인해 주세요.</p><div class="h2o-found">${found.map(([k, v]) => `<div><span>${LABEL[k] || k}</span><b>${esc(v)}</b></div>`).join('')}</div>`;
    if (st.err) h += `<div class="h2o-err">${esc(st.err)}</div>`;
    page.innerHTML = h;
    const pick = page.querySelector('[data-act="pick"]');
    if (pick) {
      pick.onclick = choose;
      pick.ondragover = e => { e.preventDefault(); pick.classList.add('drag'); };
      pick.ondragleave = () => pick.classList.remove('drag');
      pick.ondrop = e => { e.preventDefault(); pick.classList.remove('drag'); dropped(e.dataTransfer.files); };
    }
  }
  const rerender = () => { if (!root || PAGES[st.i].id !== 'docs') return; const pg = main.querySelector('.h2o-page:not(.out)'); docs(pg); buttons(); };

  // 이름으로 먼저 고른다: 사업자등록증·등기부·허가증이 회사 정보를 담고 있다.
  const PRIOR = /사업자|등록증|등기|법인|허가|신고|인감|회사|소개/;
  const READ_EXT = /^(pdf|png|jpe?g|webp|hwpx|hwp|docx|xlsx|txt)$/;
  const rank = f => (PRIOR.test(f.name) ? 0 : 1);

  async function choose() {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.multiple = true;
    inp.accept = '.pdf,.png,.jpg,.jpeg,.webp,.hwpx,.docx,.txt';
    inp.onchange = () => dropped(inp.files);
    inp.click();
  }
  async function dropped(list) {
    let arr = [...(list || [])];
    if (!arr.length) return;
    // 앱에서 폴더를 끌어다 놓으면 폴더째 읽는다
    if (A && A.review && A.review.drop && arr.length === 1 && !arr[0].type && !/\.\w+$/.test(arr[0].name)) {
      const r = await A.review.drop(arr[0]).catch(() => null);
      if (r) {
        st.dir = r.dir;
        const rels = r.files.filter(f => READ_EXT.test(f.ext)).sort((a, b) => rank(a) - rank(b)).slice(0, 10).map(f => f.rel);
        st.files = rels.map(rel => ({ name: rel }));
        if (rels.length) return read(() => A.review.read(rels).then(xs => xs.map(x => ({ ...x, name: x.rel }))));
      }
    }
    arr = arr.filter(f => READ_EXT.test((f.name.split('.').pop() || '').toLowerCase())).sort((a, b) => rank(a) - rank(b)).slice(0, 10);
    if (!arr.length) { st.err = '읽을 수 있는 서류(PDF·사진·한글·워드)를 골라 주세요.'; return rerender(); }
    st.dir = '';
    st.files = arr.map(f => ({ name: f.name }));
    read(() => Promise.all(arr.map(webFile)));
  }

  // 브라우저에서 파일 하나를 보낼 모양으로. 앱은 desktop/lib/files.js 가 같은 모양으로 만든다.
  const MIME = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp' };
  async function webFile(f) {
    const ext = (f.name.split('.').pop() || '').toLowerCase(), base = { name: f.name, ext, size: f.size };
    try {
      if (MIME[ext]) {
        if (f.size > 6 * 1024 * 1024) return { ...base, warn: '6MB 넘음' };
        const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.onerror = rej; r.readAsDataURL(f); });
        return { ...base, kind: ext === 'pdf' ? 'pdf' : 'image', mime: MIME[ext], b64 };
      }
      let text = '';
      if (ext === 'txt') text = await f.text();
      else if (ext === 'hwpx' || ext === 'docx') {
        const JSZip = window.JSZip || (window.__cfDocs && await window.__cfDocs.jszip());
        const z = await JSZip.loadAsync(await f.arrayBuffer());
        const names = Object.keys(z.files).filter(n => ext === 'hwpx' ? /^Contents\/section\d+\.xml$/.test(n) : n === 'word/document.xml').sort();
        const tag = ext === 'hwpx' ? 'hp:t' : 'w:t', para = ext === 'hwpx' ? 'hp:p' : 'w:p';
        const re = new RegExp(`<${tag}(?:\\s[^>]*)?>([^<]*)</${tag}>`, 'g');
        for (const n of names) {
          const xml = await z.file(n).async('string');
          text += xml.split(`</${para}>`).map(c => [...c.matchAll(re)].map(m => m[1]).join('')).filter(Boolean).join('\n') + '\n';
        }
        text = text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
      }
      text = text.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
      if (!text) return { ...base, warn: '글자를 못 읽음' };
      return { ...base, kind: 'text', text: text.slice(0, 6000) };
    } catch (e) { return { ...base, warn: '열 수 없음' }; }
  }

  async function read(load) {
    st.reading = true; st.fresh = true; st.err = '';
    rerender();
    try {
      const items = await load();
      st.files = items.map(x => ({ name: x.name, warn: x.warn }));
      rerender();
      const send = items.filter(x => !x.warn && (x.b64 || x.text));
      if (!send.length) throw new Error('읽을 수 있는 서류가 없어요. 직접 입력해 주세요.');
      const r = await fetch('/api/app/extract', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: send.map(x => ({ name: x.name, mime: x.mime, b64: x.b64, text: x.text })) }) });
      const d = await r.json().catch(() => ({ error: '서버 답을 읽지 못했어요.' }));
      if (r.status === 429) throw new Error('잠시 뒤 다시 해 주세요(서류 읽기는 1분에 3번, 하루 20번까지예요).');
      if (d.error) throw new Error(d.error);
      const got = d.fields || {};
      const add = items.map(x => ({ name: x.name, type: x.warn ? '읽지 못함' : ((d.docs || []).find(y => y.name === x.name) || {}).type || '기타' }));
      st.docs = st.docs.filter(o => !add.some(a => a.name === o.name)).concat(add);     // 더 넣으면 쌓인다
      // 찾은 값은 비어 있는 칸(또는 앞서 서류로 채운 칸)만 채운다. 직접 적은 값은 그대로.
      for (const [k, v] of Object.entries(got)) if (!(st.v[k] || '').trim() || st.found[k] === st.v[k]) { st.v[k] = v; st.found[k] = v; }
    } catch (e) {
      st.err = String(e.message || e);
    } finally {
      st.reading = false;
      rerender();
    }
  }

  // ── 저장 ──
  function save() {
    const memo = ls.get('formMemo', {}) || {};
    for (const k of ['applicant', 'company', 'ceo', 'bizno', 'office', 'tel', 'email', 'site', 'gas', 'cap', 'mgr_name', 'mgr_qual', 'mgr_no', 'permit_no', 'permit_date']) {
      const v = (st.v[k] || '').trim();
      if (v) memo[k] = v;
    }
    if (memo.office && !memo.address) memo.address = memo.office;      // 실증특례 서식의 '주소' 칸
    if (memo.ceo && !memo.applicant) memo.applicant = memo.ceo;        // 신청인 칸은 대표자로      // 실증특례 서식의 '주소' 칸
    ls.set('formMemo', memo);
    const prof = ls.get('h2profile', {}) || {};
    for (const k of ['kind', 'region', 'stage']) if (st.v[k]) prof[k] = st.v[k];
    prof.done = true;
    ls.set('h2profile', prof);
    try { if (st.sign) localStorage.setItem('mySign', st.sign); } catch (e) {}
    ls.set('h2onboard', { done: true, at: new Date().toISOString(), dir: st.dir, docs: st.docs });
    // 이미 떠 있는 첫 화면(index.html)에 바로 반영
    try { if (typeof PROFILE !== 'undefined') { PROFILE = prof; if (typeof turns !== 'undefined' && !turns.length && typeof greet === 'function') greet(); } } catch (e) {}
  }

  function done(page) {
    const v = st.v;
    const rows = [['회사', v.company], ['대표자', v.ceo], ['사업자번호', v.bizno], ['주소', v.office], ['연락처', [v.tel, v.email].filter(Boolean).join(' · ')],
      ['시설', [v.kind, v.site || v.region].filter(Boolean).join(' · ')], ['서류', st.docs.length ? `${st.docs.length}개 확인` : ''], ['서명', st.sign ? '등록됨 · 신청서에 자동으로 들어가요' : '']].filter(([, x]) => x);
    page.innerHTML = `<div class="h2o-done"><div class="h2o-check">${IC.ok}</div>
      <h1>준비가 끝났어요</h1>
      <p class="sub" style="margin:0">이제 수소 인허가, 무엇이든 물어보세요.\n답은 아래 사업장 기준으로 맞춰 드려요. 바꾸려면 설정(톱니)에서 다시 할 수 있어요.</p>
      ${rows.length ? `<div class="h2o-sum">${rows.map(([k, x]) => `<div><span>${k}</span><b>${esc(x)}</b></div>`).join('')}</div>` : ''}</div>`;
  }

  // ── 서명 ──  한 번 그려 두면 신청서를 채울 때 AI 가 서명 칸에도 넣는다(localStorage mySign, 신청서 편집 화면과 같은 키).
  let pad = null;
  function signPage(page) {
    page.innerHTML = `<h1>서명을\n미리 해 두세요</h1><p class="sub">한 번만 해 두면 신청서마다 AI 가 서명 칸에 넣어 드려요.\n마우스로 아래 칸에 대표자 서명을 그려 주세요.</p>
      <div class="h2o-sign${st.sign ? ' has' : ''}"><canvas></canvas><span class="ph">여기에 서명</span><button class="clr" type="button">지우기</button></div>
      <p class="h2o-tabhint"><kbd>Tab</kbd> 누르면 예시 서명이 그려져요</p>`;
    const box = page.querySelector('.h2o-sign'), cv = box.querySelector('canvas');
    requestAnimationFrame(() => {
      const dpr = window.devicePixelRatio || 1;
      cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
      const g = cv.getContext('2d');
      g.scale(dpr, dpr); g.lineWidth = 3; g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = '#111';
      pad = { cv, g, dpr, box };
      if (st.sign) { const im = new Image(); im.onload = () => { const W = cv.clientWidth, H = cv.clientHeight, k = Math.min((W - 40) / im.width, (H - 30) / im.height, 1.4);
        g.drawImage(im, (W - im.width * k) / 2, (H - im.height * k) / 2, im.width * k, im.height * k); }; im.src = st.sign; }
    });
    let drawing = false;
    const pt = e => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    cv.onpointerdown = e => { drawing = true; cv.setPointerCapture(e.pointerId); pad.g.beginPath(); pad.g.moveTo(...pt(e)); box.classList.add('has'); };
    cv.onpointermove = e => { if (!drawing) return; pad.g.lineTo(...pt(e)); pad.g.stroke(); };
    cv.onpointerup = cv.onpointercancel = () => { if (!drawing) return; drawing = false; st.sign = cropSign(); buttons(); };
    box.querySelector('.clr').onclick = () => { pad.g.clearRect(0, 0, cv.width, cv.height); box.classList.remove('has'); st.sign = ''; buttons(); };
  }
  // 잉크가 있는 부분만 잘라 PNG 로(서식 칸 안에 원래 비율로 들어가게). index.html signPad 와 같은 방식.
  function cropSign() {
    const { cv, g, dpr } = pad;
    const im = g.getImageData(0, 0, cv.width, cv.height).data;
    let x0 = cv.width, y0 = cv.height, x1 = -1, y1 = -1;
    for (let y = 0; y < cv.height; y++) for (let x = 0; x < cv.width; x++)
      if (im[(y * cv.width + x) * 4 + 3] > 20) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    if (x1 < 0) return '';
    const m = 4 * dpr;
    x0 = Math.max(0, x0 - m); y0 = Math.max(0, y0 - m); x1 = Math.min(cv.width - 1, x1 + m); y1 = Math.min(cv.height - 1, y1 + m);
    const out = document.createElement('canvas');
    out.width = x1 - x0 + 1; out.height = y1 - y0 + 1;
    out.getContext('2d').drawImage(cv, x0, y0, out.width, out.height, 0, 0, out.width, out.height);
    return out.toDataURL('image/png');
  }
  // 발표용 예시 서명: 대표자 이름을 붓글씨처럼 비스듬히 쓰고 밑줄 한 번.
  function exampleSign() {
    if (!pad) return false;
    const { cv, g, box } = pad, W = cv.clientWidth, H = cv.clientHeight;
    const name = (st.v.ceo || EX.ceo || '이한빛').slice(0, 6);
    g.save(); g.clearRect(0, 0, W, H);
    g.translate(W / 2, H / 2); g.rotate(-0.08);
    g.fillStyle = '#111'; g.font = 'italic 700 58px "Nanum Pen Script","Gungsuh","궁서",cursive,serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(name, 0, -4);
    g.beginPath(); g.lineWidth = 3; g.moveTo(-90, 34); g.bezierCurveTo(-30, 46, 40, 22, 110, 30); g.stroke();
    g.restore();
    box.classList.add('has'); st.sign = cropSign(); buttons();
    return true;
  }

  // 건너뛰기: 다시 안 뜨게만 하고, 그때까지 입력한 값은 남긴다.
  function finish(skip) {
    if (skip) {
      if (Object.values(st.v).some(x => String(x || '').trim()) && st.i > 0) save();
      else { const ob = ls.get('h2onboard', {}) || {}; ob.skipped = true; ob.done = true; ls.set('h2onboard', ob); }
    }
    close();
  }

  // 설정(톱니) 메뉴에 다시 하기
  function addSetting() {
    const pop = document.getElementById('pop');
    if (!pop || pop.querySelector('.h2o-again')) return;
    const b = document.createElement('button');
    b.className = 'h2o-again';
    b.type = 'button';
    b.textContent = '내 정보·서류 다시 설정';
    b.style.cssText = 'display:block;width:100%;margin:10px 0 0;padding:9px 12px;border:1px solid var(--line,#e4e8ee);border-radius:10px;background:#fff;font:inherit;font-size:13px;color:var(--accent,#2f6fed);cursor:pointer;text-align:left';
    b.onclick = e => { e.stopPropagation(); pop.classList.remove('open'); open(); };
    pop.appendChild(b);
  }

  // 화면이 넘어가면 포커스가 창 밖(body)에 있을 수 있어 문서 전체에서 Tab 을 받는다.
  document.addEventListener('keydown', e => { if (root && e.key === 'Tab' && !e.shiftKey && !e.isComposing && example()) e.preventDefault(); }, true);
  window.h2onboard = { open, close };
  const boot = () => {
    addSetting();
    const ob = ls.get('h2onboard', null);
    const shared = /^\/s\//.test(location.pathname);
    if (!ob && !shared && /^\/(index\.html)?$/.test(location.pathname)) open();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
