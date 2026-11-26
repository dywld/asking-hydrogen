// 신청 도우미: 민원 사이트를 앱 안 창(왼쪽)에 열고, 오른쪽 패널에서 AI가 하는 일을 단계로 보여 준다.
// 하는 일: 신청서 칸 이름을 읽어 내 사업장 정보(formMemo)로 빈칸을 한 글자씩 채우고, 첨부 칸에 사업장 서류를 올린다.
// 하지 않는 일: 로그인(공동인증서·간편인증), 수수료 결제, 마지막 [신청·제출] 버튼. 이 셋은 사용자가 직접 한다.
// 사이트 안 스크립트와 섞이지 않게 별도 세계(isolated world)에서 돌린다. iframe 안 신청서는 아직 못 채운다.
const { BrowserWindow, WebContentsView, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

const PANEL_W = 400, BAR_H = 52, WORLD = 1207;
const DEMO = 'file:///' + path.join(__dirname, '..', 'assist-demo.html').replace(/\\/g, '/');
// 첨부 칸 이름 -> 사업장 서류 칸(app-ui.js BASE_DOCS 이름)
const FILE_KEYS = [
  ['사업계획서', /사업\s*계획/], ['시설 설치계획서', /설치\s*계획/], ['시설 도면·설명서', /도면|설명서|배치/],
  ['가스안전공사 기술검토서', /기술\s*검토/], ['사업자등록증', /사업자\s*등록/], ['법인 등기·정관', /등기|정관/],
  ['부지 사용 권원', /토지|임대|권원|승낙/], ['건축 설계도서', /건축/], ['완공도면·시공현황', /완공|시공/],
  ['안전관리규정(안)', /안전\s*관리\s*규정/], ['안전관리자 자격증', /자격|경력/],
];

// 사이트 안에서 도는 코드는 assist-site.js 한 곳에 둔다(웹 시연도 같은 파일을 쓴다).
const SITE_LIB = fs.readFileSync(path.join(__dirname, '..', 'assist-site.js'), 'utf8');

let w = null, view = null, job = null;

function open(win, data) {
  if (w && !w.isDestroyed()) { w.focus(); job = { ...job, data }; send({ reset: true }); return; }
  w = new BrowserWindow({
    width: 1440, height: 900, minWidth: 1000, minHeight: 640, parent: undefined, title: '신청 도우미',
    backgroundColor: '#ffffff', icon: path.join(__dirname, '..', 'build', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, '..', 'assist-preload.js'), contextIsolation: true, sandbox: true },
  });
  w.setMenuBarVisibility(false);
  view = new WebContentsView({ webPreferences: { contextIsolation: true, sandbox: true } });
  w.contentView.addChildView(view);
  const fit = () => { const [cw, ch] = w.getContentSize(); view.setBounds({ x: 0, y: BAR_H, width: cw - PANEL_W, height: ch - BAR_H }); };
  w.on('resize', fit); fit();
  job = { data, paused: false, running: false };
  view.webContents.setWindowOpenHandler(({ url }) => { view.webContents.loadURL(url); return { action: 'deny' }; });
  view.webContents.on('did-navigate', (e, url) => send({ url }));
  view.webContents.on('did-navigate-in-page', (e, url) => send({ url }));
  view.webContents.on('did-finish-load', () => send({ loaded: true, title: view.webContents.getTitle() }));
  w.loadFile(path.join(__dirname, '..', 'assist.html'));
  w.webContents.once('did-finish-load', () => { send({ init: { company: data.memo.company || '', project: data.project || '', demo: DEMO } }); go(data.url || DEMO); });
  w.on('closed', () => { w = null; view = null; job = null; });
  return true;
}

const send = s => { if (w && !w.isDestroyed()) w.webContents.send('assist:state', s); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const site = code => view.webContents.executeJavaScriptInIsolatedWorld(WORLD, [{ code }], true);

function go(url) {
  if (!view) return;
  if (!/^(https?:|file:)/.test(url)) url = 'https://' + url;
  view.webContents.loadURL(url).catch(() => {});
}

// 한 화면씩: 칸 채우기 -> 서류 올리기 -> (예시 화면이면) 검색·다음 버튼으로 넘어가기. 제출 버튼은 끝까지 누르지 않는다.
async function run() {
  if (!view || job.running) return;
  job.running = true; job.paused = false;
  const hold = async () => { while (job && job.paused) await sleep(300); return !!job; };
  const dbg = view.webContents.debugger;
  try {
    const memo = job.data.memo || {}, files = job.data.files || [];
    const tot = { fill: 0, fillT: 0, file: 0, fileT: 0, empty: [], missing: [], submits: 0, login: false, auto: false };
    const scanMsg = () => send({ scan: { login: tot.login, auto: tot.auto, fill: tot.fillT, files: tot.fileT, fileSlots: tot.fileT + tot.missing.length, submits: tot.submits } });
    for (let page = 0; page < 15; page++) {
      if (!(await hold())) return;
      await site(SITE_LIB);
      await site('__h2a.clear()');
      const r = await site('__h2a.scan(' + JSON.stringify(memo) + ')');
      const todo = r.fields.filter(f => f.key && !f.has);
      const fileJobs = r.files.map(f => {
        const k = FILE_KEYS.find(([, re]) => re.test(f.label));
        return { ...f, doc: k && files.find(x => x.slot === k[0] && fs.existsSync(x.path)) };
      });
      const up = fileJobs.filter(f => f.doc);
      const next = await site('__h2a.tour()');
      tot.fillT += todo.length; tot.fileT += up.length; tot.submits = r.submits;
      tot.empty.push(...r.fields.filter(f => !f.key).map(f => f.label).filter(Boolean));
      tot.missing.push(...fileJobs.filter(f => !f.doc).map(f => f.label));
      if (r.login) tot.login = true;
      scanMsg();
      if (r.login && !todo.length && !r.files.length && !next) { send({ step: 'login' }); return; }
      for (const f of todo) {
        if (!(await hold())) return;
        send({ step: 'fill', done: tot.fill, total: tot.fillT, now: f.label });
        if (await site('__h2a.fill(' + f.i + ',' + JSON.stringify(memo[f.key]) + ')')) tot.fill++;
        send({ step: 'fill', done: tot.fill, total: tot.fillT });
      }
      for (const f of up) {
        if (!(await hold())) return;
        send({ step: 'files', done: tot.file, total: tot.fileT, now: f.label + ' ← ' + path.basename(f.doc.path) });
        try {
          if (!dbg.isAttached()) dbg.attach('1.3');
          const { root } = await dbg.sendCommand('DOM.getDocument', { depth: 0 });
          const { nodeId } = await dbg.sendCommand('DOM.querySelector', { nodeId: root.nodeId, selector: '[data-h2a-f="' + f.i + '"]' });
          if (nodeId) { await dbg.sendCommand('DOM.setFileInputFiles', { nodeId, files: [f.doc.path] }); await site('__h2a.fileDone(' + f.i + ')'); tot.file++; }
        } catch (e) { /* 이 칸은 건너뛴다 */ }
        send({ step: 'files', done: tot.file, total: tot.fileT });
      }
      if (!next) break;
      const login = /인증|로그인/.test(next.label);
      send({ step: login ? 'login' : 'tour', auto: true, now: next.label });
      if (login) { tot.auto = true; scanMsg(); }
      await site('__h2a.act()');
      await sleep(500);
      for (let t = 0; t < 40; t++) {            // 화면이 바뀔 때까지(시연 인증 대기·실제 페이지 이동)
        let b = view.webContents.isLoading();
        if (!b) { try { await site(SITE_LIB); b = await site('__h2a.busy()'); } catch (e) { b = true; } }
        if (!b) break;
        await sleep(250);
      }
      if (login) send({ step: 'loginDone' });
    }
    send({ step: 'check', empty: [...new Set(tot.empty)].slice(0, 8), missing: [...new Set(tot.missing)] });
    try { await site('__h2a.showSubmit()'); } catch (e) {}
    send({ step: 'me', submits: tot.submits });
  } catch (e) {
    send({ error: String(e && e.message || e) });
  } finally {
    try { if (dbg.isAttached()) dbg.detach(); } catch (e) {}
    if (job) job.running = false;
  }
}
function setup(win, guard) {
  ipcMain.handle('assist:open', (e, data) => {
    data = data || {};
    data.files = (data.files || []).filter(f => f && f.path && guard(f.path));   // 사업장 폴더 안 파일만
    data.memo = data.memo || {};
    return open(win, data);
  });
  ipcMain.handle('assist:go', (e, url) => go(String(url || '')));
  ipcMain.handle('assist:start', () => run());
  ipcMain.handle('assist:pause', (e, p) => { if (job) job.paused = !!p; return job && job.paused; });
  ipcMain.handle('assist:back', () => { if (view && view.webContents.navigationHistory.canGoBack()) view.webContents.navigationHistory.goBack(); });
}

module.exports = { setup, open, run, DEMO, _view: () => view, _win: () => w };
