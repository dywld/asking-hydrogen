"""신청 도우미 웹 시연 페이지를 만든다(앱 화면을 그대로 웹에서 보여 주기용).

  desktop/assist.html       -> cf/public_extra/apply-demo.html (오른쪽 패널 + 왼쪽 iframe, window.assist 를 웹용으로 바꿔 끼움)
  desktop/assist-demo.html  -> cf/public_extra/apply-site.html (가상 민원24)
  desktop/assist-site.js    -> cf/public_extra/apply-engine.js (사이트 안에서 도는 코드)

앱 쪽을 고친 뒤 python desktop/test/web_demo.py 로 다시 만들고 cf 를 배포한다.
"""
from pathlib import Path

D = Path(__file__).resolve().parents[1]
OUT = D.parent / "cf" / "public_extra"

SHIM = r"""
<iframe id="site" title="민원24 (예시)" src="/apply-site.html"></iframe>
<script>
// 웹 시연용 window.assist: 앱(lib/assist.js run)과 같은 순서로 iframe 안 가상 민원24 를 채운다. 파일은 이름만 있는 견본이다.
window.assist = (() => {
  let fn = () => {}, paused = false, running = false;
  const send = s => fn(s), sleep = ms => new Promise(r => setTimeout(r, ms));
  const frame = document.getElementById('site');
  const memo = { company: '한빛수소 주식회사', ceo: '이한빛', bizno: '214-87-12345', office: '서울특별시 강동구 천호대로 1000',
    tel: '02-123-4567', email: 'info@hanbit-h2.co.kr', site: '서울특별시 강동구 고덕동 123-4', gas: '압축수소', cap: '3,000㎥' };
  const FILES = [[/사업\s*계획/, '사업계획서_한빛수소.pdf'], [/기술\s*검토/, '기술검토서_가스안전공사.pdf'], [/등기|정관/, '법인정관_한빛수소.pdf'], [/사업자\s*등록/, '사업자등록증_한빛수소.pdf']];
  let W = null;
  const load = () => new Promise(ok => { frame.onload = () => { W = frame.contentWindow; ok(); }; frame.src = '/apply-site.html?t=' + Date.now(); });
  const inject = () => W.__h2a ? Promise.resolve() : new Promise((ok, no) => { const s = W.document.createElement('script'); s.src = '/apply-engine.js'; s.onload = ok; s.onerror = no; W.document.head.appendChild(s); });
  const hold = async () => { while (paused) await sleep(300); };
  async function run() {
    if (running) return; running = true; paused = false;
    try {
      await load(); await sleep(400); await inject();
      const H = W.__h2a, tot = { fill: 0, fillT: 0, file: 0, fileT: 0, empty: [], missing: [], submits: 0, auto: false };
      const scanMsg = () => send({ scan: { login: false, auto: tot.auto, fill: tot.fillT, files: tot.fileT, fileSlots: tot.fileT + tot.missing.length, submits: tot.submits } });
      for (let page = 0; page < 15; page++) {
        await hold(); H.clear();
        const r = H.scan(memo), todo = r.fields.filter(f => f.key && !f.has);
        const fj = r.files.map(f => ({ ...f, doc: (FILES.find(([re]) => re.test(f.label)) || [])[1] })), up = fj.filter(f => f.doc);
        const next = H.tour();
        tot.fillT += todo.length; tot.fileT += up.length; tot.submits = r.submits;
        tot.empty.push(...r.fields.filter(f => !f.key).map(f => f.label).filter(Boolean));
        tot.missing.push(...fj.filter(f => !f.doc).map(f => f.label));
        scanMsg();
        for (const f of todo) { await hold(); send({ step: 'fill', done: tot.fill, total: tot.fillT, now: f.label }); if (await H.fill(f.i, memo[f.key])) tot.fill++; send({ step: 'fill', done: tot.fill, total: tot.fillT }); }
        for (const f of up) {
          await hold(); send({ step: 'files', done: tot.file, total: tot.fileT, now: f.label + ' ← ' + f.doc });
          const el = W.document.querySelector('[data-h2a-f="' + f.i + '"]');
          if (el) { const dt = new W.DataTransfer(); dt.items.add(new W.File(['예시'], f.doc, { type: 'application/pdf' })); el.files = dt.files; el.dispatchEvent(new W.Event('change', { bubbles: true })); await H.fileDone(f.i); tot.file++; }
          send({ step: 'files', done: tot.file, total: tot.fileT });
        }
        if (!next) break;
        const login = /인증|로그인/.test(next.label);
        send({ step: login ? 'login' : 'tour', auto: true, now: next.label });
        if (login) { tot.auto = true; scanMsg(); }
        await H.act(); await sleep(500);
        for (let t = 0; t < 40 && H.busy(); t++) await sleep(250);
        if (login) send({ step: 'loginDone' });
      }
      send({ step: 'check', empty: [...new Set(tot.empty)].slice(0, 8), missing: [...new Set(tot.missing)] });
      await H.showSubmit();
      send({ step: 'me', submits: tot.submits });
    } catch (e) { send({ error: String(e && e.message || e) }); }
    running = false;
  }
  frame.addEventListener('load', () => { W = frame.contentWindow; send({ url: 'file:demo', loaded: true, title: frame.contentDocument.title }); });
  return {
    onState: f => { fn = f; setTimeout(() => send({ init: { company: memo.company, project: '강원 수소충전소 (예시)', demo: 'demo' }, url: 'file:demo' }), 0); },
    go: u => { if (u === 'demo') load(); else window.open(u, '_blank', 'noopener'); },
    start: () => run(), pause: p => { paused = !!p; return paused; },
    back: () => { try { frame.contentWindow.history.back(); } catch (e) {} },
  };
})();
if (/[?&]auto=1/.test(location.search)) setTimeout(() => document.getElementById('go').click(), 1200);
</script>
"""

CSS = """
#site{position:fixed;left:0;top:52px;right:400px;bottom:0;width:calc(100% - 400px);height:calc(100% - 52px);border:0;background:#fff}
"""


def main():
    h = (D / "assist.html").read_text(encoding="utf-8")
    h = h.replace('<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; style-src \'self\' \'unsafe-inline\'; script-src \'self\' \'unsafe-inline\'">\n', "")
    h = h.replace("<title>신청 도우미</title>", '<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>신청 도우미 시연</title>')
    h = h.replace("</style>", CSS + "</style>", 1)
    i = h.index("<script>")
    h = h[:i] + SHIM.strip() + "\n" + h[i:]
    h = h.replace('<button data-u="https://www.gov.kr">정부24</button>', '')
    h = h.replace('readonly', '')
    OUT.joinpath("apply-demo.html").write_text(h, encoding="utf-8", newline="\n")
    OUT.joinpath("apply-site.html").write_text((D / "assist-demo.html").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    OUT.joinpath("apply-engine.js").write_text((D / "assist-site.js").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    print("ok", OUT)


if __name__ == "__main__":
    main()
