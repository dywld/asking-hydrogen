// 켤 때 새 버전 확인 -> 토스식 '업데이트가 있어요!' 화면(update.html).
//   앱 파일: electron-updater 가 설치 파일 전용 공개 저장소(GitHub Releases)의 latest.yml 을 본다.
//            [업데이트하고 시작하기] -> 내려받기(진행 막대) -> 조용히 설치 -> 새 버전으로 다시 켜짐.
//   화면:    서버의 /version.json 이 지난번에 본 것과 다르면 알린다. 화면은 서버에서 불러오므로
//            버튼을 누르면 캐시를 비우고 새 화면을 연다(내려받기 없음).
//   [나중에 할게요] -> 지금 버전 그대로 시작. 다음에 켤 때 다시 묻는다.
// 처음 깐 앱은 화면 버전만 기억하고 묻지 않는다. 인터넷이 없거나 확인이 늦으면(4초) 그냥 시작한다.
const { app, ipcMain, session, net } = require('electron');
const fs = require('fs');
const path = require('path');

const WAIT = 4000;
const seenFile = () => path.join(app.getPath('userData'), 'web-version.json');
const readSeen = () => { try { return JSON.parse(fs.readFileSync(seenFile(), 'utf8')).id || ''; } catch (e) { return ''; } };
const writeSeen = id => { try { fs.writeFileSync(seenFile(), JSON.stringify({ id, at: new Date().toISOString() })); } catch (e) {} };

function timeout(p, ms) { return Promise.race([p, new Promise(r => setTimeout(() => r(null), ms))]); }

async function webVersion(server) {
  try {
    const r = await net.fetch(server + '/version.json?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) return null;
    const d = await r.json();
    return d && d.id ? d : null;
  } catch (e) { return null; }
}

function appUpdater() {
  // 개발 중(npm start)에는 설치 파일 정보(app-update.yml)가 없어 건너뛴다. H2_UPDATE_DEV=1 이면 dev-app-update.yml 로 시험.
  if (!app.isPackaged && !process.env.H2_UPDATE_DEV) return null;
  try {
    const { autoUpdater } = require('electron-updater');
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = false;
    if (!app.isPackaged) autoUpdater.forceDevUpdateConfig = true;
    return autoUpdater;
  } catch (e) { return null; }
}

exports.start = async function start(win, { server, loadServer, page }) {
  const send = (ch, d) => { if (!win.isDestroyed()) win.webContents.send(ch, d); };
  let mode = null, info = null, web = null;
  const up = appUpdater();

  const [appRes, webRes] = await Promise.all([
    up ? timeout(up.checkForUpdates().catch(() => null), WAIT) : null,
    timeout(webVersion(server), WAIT),
  ]);
  web = webRes;
  const cur = app.getVersion();
  if (appRes && appRes.updateInfo && appRes.isUpdateAvailable !== false && appRes.updateInfo.version !== cur) {
    mode = 'app'; info = appRes.updateInfo;
  } else if (web) {
    const seen = readSeen();
    if (!seen) writeSeen(web.id);                     // 처음 깐 앱은 기억만
    else if (seen !== web.id) mode = 'web';
  }
  if (process.env.H2_FAKE_UPDATE) { mode = process.env.H2_FAKE_UPDATE; info = { version: '0.2.1' }; web = web || { id: 'x', label: '2026.11.24' }; }   // 화면 점검용

  if (!mode) return loadServer();

  ipcMain.removeHandler('upd:go');
  ipcMain.removeHandler('upd:later');
  ipcMain.handle('upd:later', () => loadServer());
  ipcMain.handle('upd:go', async () => {
    if (mode === 'web') {
      await session.defaultSession.clearCache();
      await session.defaultSession.clearStorageData({ storages: ['serviceworkers', 'cachestorage'] });
      writeSeen(web.id);
      return loadServer();
    }
    up.on('download-progress', p => send('upd:progress', p.percent || 0));
    up.once('update-downloaded', () => {
      send('upd:state', 'installing');
      if (web) writeSeen(web.id);
      setTimeout(() => up.quitAndInstall(true, true), 900);   // 조용히 설치하고 새 버전 실행
    });
    up.once('error', e => send('upd:state', 'error:' + String(e && e.message || e)));
    try { await up.downloadUpdate(); } catch (e) { send('upd:state', 'error:' + String(e && e.message || e)); }
  });

  const q = mode === 'app' ? { mode, v: info.version, cur } : { mode, v: web.label || web.id };
  win.loadFile(page, { query: q });
};
