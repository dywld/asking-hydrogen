import os, sys
from playwright.sync_api import sync_playwright
S = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else S
BASE = 'https://hydrogen-guide.tmdfoqhdl030.workers.dev'
html = open(os.path.join(S, 'm3d.html'), encoding='utf-8').read()
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    pg = br.new_page(viewport={'width': 1440, 'height': 860}, device_scale_factor=1)
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: m.type == 'error' and errs.append(m.text))
    pg.route(BASE + '/_mockc/m3d*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=html))
    pg.route(BASE + '/_mockc/m3d_world.json', lambda r: r.fulfill(status=200, content_type='application/json', body=open(os.path.join(S,'m3d_world.json'),encoding='utf-8').read()))
    pg.route(BASE + '/_mockc/st_*', lambda r: r.fulfill(status=200, content_type='application/json', body=open(os.path.join(S, r.request.url.rsplit('/', 1)[1]), encoding='utf-8').read()))
    for v in (sys.argv[2] if len(sys.argv)>2 else '123'):
        for st in ((sys.argv[3],) if len(sys.argv)>3 else ('bad','ok')):
            pg.goto(f'{BASE}/_mockc/m3d?v={v}&st={st}'); pg.wait_for_selector('body[data-ready="1"]', timeout=60000); pg.wait_for_timeout(1200)
            pg.screenshot(path=os.path.join(OUT, f'm3d_{v}_{st}.png'))
    print('errs', errs[:4]); br.close()
