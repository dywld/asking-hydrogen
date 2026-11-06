// 수소시설 인허가 가이드 — 윈도우 앱.
// 화면과 답변은 서버(클라우드플레어판)에서 불러온다. Gemini 키는 서버에만 있다.
// 앱이 하는 일은 서버가 못 하는 것들: 내 PC 폴더 읽기(서류 검토), 사업장 프로젝트 저장,
// 신청서 바로 저장·열기, 윈도우 알림. 앱 전용 화면(app-ui.js)도 서버에서 받아 와서
// 화면을 고쳐도 앱을 다시 깔 필요가 없다.
const { app, BrowserWindow, ipcMain, dialog, shell, Notification, session, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const projects = require('./lib/projects');
const files = require('./lib/files');

const SERVER = (process.env.H2_SERVER || 'https://hydrogen-guide.tmdfoqhdl030.workers.dev').replace(/\/$/, '');
const ORIGIN = new URL(SERVER).origin;
let win = null;
const known = new Set();     // 이번에 앱이 저장한 파일(사업장 밖에 저장해도 열기 단추가 되게)
const mine = p => files.inside(p, projects.root()) || known.has(p);

app.setAppUserModelId('kr.ac.kangwon.hydrogenpermit');   // 윈도우 알림에 앱 이름이 뜨게

function loadServer() {
  win.loadURL(SERVER).catch(() => {});                    // 실패는 did-fail-load 가 받는다
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280, height: 860, minWidth: 900, minHeight: 600,
    title: app.getName(), backgroundColor: '#ffffff', show: false,
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true },
  });
  Menu.setApplicationMenu(null);
  win.once('ready-to-show', () => win.show());

  // 인터넷이 끊기면 안내 화면. -3(ABORTED)은 다른 주소로 넘어가며 생기는 것이라 무시한다.
  win.webContents.on('did-fail-load', (e, code, desc, url, isMain) => {
    if (isMain && code !== -3) win.loadFile(path.join(__dirname, 'offline.html'));
  });

  // 서버 밖 주소(법령정보센터·정부24 등)는 기본 브라우저로 연다.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(ORIGIN)) return { action: 'allow' };
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => {
    if (url.startsWith(ORIGIN) || url.startsWith('file:')) return;
    e.preventDefault();
    if (/^https?:/.test(url)) shell.openExternal(url);
  });

  // 신청서·꾸러미 내려받기: 열린 사업장이 있으면 그 폴더의 '서류'에 바로, 없으면 저장 위치를 묻는다.
  session.defaultSession.on('will-download', (e, item) => {
    const name = item.getFilename();
    const cur = projects.current();
    if (cur) item.setSavePath(files.uniquePath(path.join(projects.dir(cur), '서류'), name));
    else item.setSaveDialogOptions({ defaultPath: path.join(app.getPath('documents'), name) });
    item.once('done', (ev, state) => {
      if (state !== 'completed') return;
      const p = item.getSavePath();
      known.add(p);
      if (cur) projects.addFile(cur, p);
      win.webContents.send('h2:downloaded', { path: p, name: path.basename(p), project: cur });
    });
  });

  if (process.env.H2_SHOT) require('./test/shot')(win);   // 화면 점검(개발용)
  loadServer();
}

// ── 화면(app-ui.js)이 부르는 기능 ──
const handle = (ch, fn) => ipcMain.handle(ch, (e, ...a) => fn(...a));

handle('app:info', () => ({ version: app.getVersion(), server: SERVER, docs: projects.root() }));
handle('app:retry', () => loadServer());
handle('app:notify', (title, body) => {
  if (!Notification.isSupported()) return false;
  const n = new Notification({ title: String(title).slice(0, 80), body: String(body).slice(0, 200) });
  n.on('click', () => { if (win) { win.show(); win.focus(); win.webContents.send('h2:notice-click'); } });
  n.show();
  return true;
});

handle('proj:list', () => projects.list());
handle('proj:create', name => projects.create(name));
handle('proj:get', id => projects.get(id));
handle('proj:save', (id, patch) => projects.save(id, patch));
handle('proj:open', id => projects.setCurrent(id));
handle('proj:close', () => projects.setCurrent(null));
handle('proj:current', () => projects.current());
handle('proj:remove', id => projects.remove(id));            // 휴지통으로 옮긴다(되살릴 수 있게)
handle('proj:folder', id => shell.openPath(projects.dir(id)));
handle('proj:dates', () => projects.allDates());

handle('file:open', p => mine(p) ? shell.openPath(p) : 'denied');
handle('file:show', p => { if (mine(p)) shell.showItemInFolder(p); });
handle('file:save', async (name, b64) => {
  const cur = projects.current();
  let p;
  if (cur) p = files.uniquePath(path.join(projects.dir(cur), '서류'), name);
  else {
    const r = await dialog.showSaveDialog(win, { defaultPath: path.join(app.getPath('documents'), name) });
    if (r.canceled || !r.filePath) return null;
    p = r.filePath;
  }
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, Buffer.from(b64, 'base64'));
  known.add(p);
  if (cur) projects.addFile(cur, p);
  return p;
});

// 서류 폴더 검토: 고른 폴더만 읽는다(앱이 아무 폴더나 뒤지지 않게, 고른 경로를 기억해 둔다).
let picked = null;
handle('review:pick', async () => {
  const cur = projects.current();
  const r = await dialog.showOpenDialog(win, {
    title: '검토할 서류 폴더 고르기', properties: ['openDirectory'],
    defaultPath: cur ? path.join(projects.dir(cur), '서류') : app.getPath('documents'),
  });
  if (r.canceled || !r.filePaths[0]) return null;
  picked = r.filePaths[0];
  return { dir: picked, files: files.scan(picked) };
});
handle('review:drop', dir => {
  // 끌어다 놓은 폴더. 화면에서 받은 경로라 폴더인지 확인만 하고 쓴다.
  try { if (!fs.statSync(dir).isDirectory()) return null; } catch (e) { return null; }
  picked = dir;
  return { dir, files: files.scan(dir) };
});
handle('review:read', async rels => {
  if (!picked) return [];
  return Promise.all(rels.slice(0, files.MAX_FILES).map(rel => files.extract(picked, rel)));
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => { if (!BrowserWindow.getAllWindows().length) createWindow(); });
});
app.on('window-all-closed', () => app.quit());
