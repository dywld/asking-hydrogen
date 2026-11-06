// 화면 점검: 앱을 띄워 사업장 만들기 → 일정 → 서류 폴더 검토 → 알림 순서로 누르고 PNG 를 찍는다.
//   H2_SHOT=저장폴더 H2_SHOT_DOCS=검토할폴더 [H2_SERVER=http://localhost:8788] npx electron .
// 사업장은 임시 폴더(내 문서 대신)에 만든다. 설치 파일에는 들어가지 않는다(package.json build.files).
const { app, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');

module.exports = function shot(win) {
  const out = process.env.H2_SHOT;
  const docs = process.env.H2_SHOT_DOCS;
  fs.mkdirSync(out, { recursive: true });
  app.setPath('documents', fs.mkdtempSync(path.join(os.tmpdir(), 'h2shot-')));
  if (docs) dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [docs] });
  dialog.showSaveDialog = async () => ({ canceled: true });

  const wait = ms => new Promise(r => setTimeout(r, ms));
  const js = code => win.webContents.executeJavaScript(code, true);
  const snap = async name => {
    const img = await win.webContents.capturePage();
    fs.writeFileSync(path.join(out, name), img.toPNG());
    console.log('shot', name);
  };
  const until = async (code, ms = 120000) => {
    for (let t = 0; t < ms; t += 500) { if (await js(code).catch(() => false)) return true; await wait(500); }
    return false;
  };

  win.webContents.once('did-finish-load', async () => {
    try {
      if (process.env.H2_SHOT_ONLY === 'offline') { await wait(1500); await snap('06_offline.png'); return app.quit(); }
      await until("!!document.querySelector('#h2a-proj')", 20000);
      await wait(1500);
      await snap('01_home.png');

      await js("document.querySelector('#h2a-proj').click()");
      await until("!!document.querySelector('#h2a-newname')");
      await js("document.querySelector('#h2a-newname').value='평창 수소충전소'; document.querySelector('#h2a-new').click()");
      await until("!!document.querySelector('#h2a-kind')");
      await js("const s=document.querySelector('#h2a-kind'); s.value='gas_permit'; s.dispatchEvent(new Event('change'))");
      await until("!!document.querySelector('#h2a-due')");
      await js("document.querySelector('#h2a-due').click()");
      await wait(800);
      await js(`document.querySelector('#h2a-dt').value='보완 서류 제출 마감'; document.querySelector('#h2a-dd').value=new Date(Date.now()+3*86400e3).toISOString().slice(0,10); document.querySelector('#h2a-addd').click()`);
      await wait(1200);
      // 내려받기 → 사업장 서류 폴더
      await js("const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['시험']));a.download='시험_신청서.txt';document.body.appendChild(a);a.click()");
      await until("!!document.querySelector('.h2a-toast') && document.querySelector('.h2a-toast').innerText.includes('시험_신청서')", 15000);
      await wait(800);
      await js("document.querySelector('#h2a-projd .h2a-body').scrollTop = 400");
      await wait(300);
      await snap('02_project.png');

      await js("document.querySelector('.h2a-dim').click(); document.querySelector('#h2a-rev').click()");
      await until("!!document.querySelector('#h2a-pick')");
      await js("document.querySelector('#h2a-pick').click()");
      await until("!!document.querySelector('#h2a-start')");
      await wait(500);
      await snap('03_review_files.png');
      await js("document.querySelector('#h2a-start').click()");
      const done = await until("!!document.querySelector('#h2a-docs') || !!document.querySelector('#h2a-rres .h2a-sum')", 150000);
      console.log('review done', done);
      await wait(800);
      await js("document.querySelector('#h2a-revd .h2a-body').scrollTop = 99999");
      await wait(300);
      await snap('04_review_result.png');
      const res = await js("document.querySelector('#h2a-rres') ? document.querySelector('#h2a-rres').innerText : ''");
      fs.writeFileSync(path.join(out, 'review_result.txt'), res);

      await js("document.querySelector('.h2a-dim').click(); document.querySelector('#h2a-bell').click()");
      await wait(1200);
      await snap('05_bell.png');
    } catch (e) {
      console.error('shot error', e);
    }
    app.quit();
  });
};
