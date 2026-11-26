// 신청 도우미 점검: 예시 신청서를 열고 [채우기 시작]을 눌러 단계별로 PNG(패널·사이트 따로)를 찍는다.
//   H2_ASSIST_SHOT=저장폴더 H2_ASSIST_DOCS=견본서류폴더 npx electron .
// 설치 파일에는 들어가지 않는다(package.json build.files).
const { app, screen } = require('electron');
const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const assist = require('../lib/assist');

module.exports = function shot(win) {
  const out = process.env.H2_ASSIST_SHOT, docs = process.env.H2_ASSIST_DOCS || '';
  fs.mkdirSync(out, { recursive: true });
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const pick = re => { try { const f = fs.readdirSync(docs).find(n => re.test(n) && /\.pdf$/i.test(n)); return f ? path.join(docs, f) : null; } catch (e) { return null; } };
  const files = [
    ['사업계획서', pick(/허가증/)], ['가스안전공사 기술검토서', pick(/자격증/)],
    ['법인 등기·정관', pick(/등기/)], ['사업자등록증', pick(/사업자/)],
  ].filter(x => x[1]).map(([slot, p]) => ({ slot, path: p }));
  const memo = { company: '한빛수소 주식회사', ceo: '이한빛', bizno: '214-87-12345', office: '서울특별시 강동구 천호대로 1000',
    tel: '02-123-4567', email: 'info@hanbit-h2.co.kr', site: '서울특별시 강동구 고덕동 123-4', gas: '압축수소', cap: '3,000㎥' };
  const snap = async name => {
    // 창 안에 사이트 창(WebContentsView)이 따로 있어 capturePage 로는 한 장에 안 나온다 -> 화면에서 창 자리를 찍는다.
    const w = assist._win(); if (w.isMinimized()) w.restore(); w.show(); w.setAlwaysOnTop(true); w.moveTop(); await wait(500);
    const b = w.getContentBounds(), k = screen.getDisplayMatching(b).scaleFactor, r = v => Math.round(v * k);
    execFileSync('python', ['-c', `from PIL import ImageGrab; ImageGrab.grab(bbox=(${r(b.x)},${r(b.y)},${r(b.x + b.width)},${r(b.y + b.height)}), all_screens=True).save(r"${path.join(out, name + '.png')}")`]);
    console.log('shot', name);
  };
  // 실제 사이트 점검: H2_ASSIST_URL 을 열고, 사용자가 직접 로그인해 신청서 화면에 닿을 때까지 기다렸다가 채운다.
  const real = process.env.H2_ASSIST_URL;
  const frameInfo = async () => {
    const v = assist._view().webContents, out = [];
    for (const f of v.mainFrame.framesInSubtree) {
      try {
        const n = await f.executeJavaScript("[...document.querySelectorAll('input,select,textarea')].filter(e=>e.type!=='hidden'&&e.offsetParent).length");
        out.push({ url: f.url.slice(0, 120), inputs: n, top: f === v.mainFrame });
      } catch (e) { out.push({ url: f.url.slice(0, 120), err: String(e).slice(0, 60) }); }
    }
    return out;
  };
  if (real) return win.webContents.once('did-finish-load', async () => {
    try {
      assist.open(win, { memo, files, project: '강원 수소충전소', url: real });
      await wait(4000); await snap('r1_open');
      let ready = false;
      for (let t = 0; t < 600 && !ready; t++) {           // 최대 20분
        await wait(2000);
        const u = assist._view().webContents.getURL();
        const fi = await frameInfo().catch(() => []);
        if (t % 15 === 0) console.log('wait', u.slice(0, 100), JSON.stringify(fi));
        ready = !/login|Login|certif/i.test(u) && fi.some(f => f.inputs >= 4);
        if (ready) console.log('ready', u, JSON.stringify(fi));
      }
      await wait(3000); await snap('r2_form');
      assist._win().webContents.executeJavaScript("document.querySelector('#go').click()");
      for (let t = 0; t < 120; t++) {
        const done = await assist._win().webContents.executeJavaScript("document.querySelector('#ait').textContent").catch(() => '');
        if (t % 10 === 0) console.log('ait', done);
        if (/다 채웠|직접|못 찾/.test(done) && t > 4) break;
        await wait(500);
      }
      await wait(1500); await snap('r3_after');
      const panel = await assist._win().webContents.executeJavaScript("document.querySelector('#now').textContent + ' || ' + [...document.querySelectorAll('li[data-k]')].map(l=>l.dataset.k+':'+l.className+':'+l.innerText.replace(/\\s+/g,' ')).join(' | ')");
      console.log('panel', panel);
      console.log('frames', JSON.stringify(await frameInfo()));
      fs.writeFileSync(path.join(out, 'page.html'), await assist._view().webContents.executeJavaScript('document.documentElement.outerHTML'));
    } catch (e) { console.log('ERR', e && e.stack || e); }
    await wait(60000); app.quit();
  });
  win.webContents.once('did-finish-load', async () => {
    try {
      assist.open(win, { memo, files, project: '강원 수소충전소' });
      await wait(800); assist._win().show(); assist._win().focus(); assist._win().moveTop();
      await wait(2200);
      await snap('a1_open');
      assist._win().webContents.executeJavaScript("document.querySelector('#go').click()");
      const t0 = Date.now();
      for (const [ms, name] of [[3500, 'a2_search'], [8500, 'a3_login'], [14000, 'a4_form'], [21500, 'a5_files']]) {
        await wait(Math.max(0, ms - (Date.now() - t0))); await snap(name);
      }
      for (let t = 0; t < 120; t++) {
        const done = await assist._win().webContents.executeJavaScript("document.querySelector('[data-k=me]').className==='me' && document.querySelector('#ait').textContent==='다 채웠어요'");
        if (done) break;
        await wait(500);
      }
      await wait(800);
      console.log('elapsed', Date.now() - t0);
      await snap('a6_done');
      const r = await assist._view().webContents.executeJavaScript("[...document.querySelectorAll('input')].map(i=>i.type==='file'?(i.files.length?i.files[0].name:''):i.value)");
      console.log('values', JSON.stringify(r));
    } catch (e) { console.log('ERR', e && e.stack || e); }
    app.quit();
  });
};
