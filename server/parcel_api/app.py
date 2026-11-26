# 수소 인허가 도우미용 지적도 통로 (azzas3d.com/api/kgs-parcel/*)
# AZZAS3D 서버(/opt/parcel_api)에서 따로 돈다. AZZAS3D 본체(/opt/mcmap)는 건드리지 않고 브이월드 키만 읽는다.
# 수소 사이트 서버(Cloudflare Worker)만 부르도록 X-Kgs-Token 머리말을 확인한다. 키 값은 밖으로 내보내지 않는다.
#   GET /api/kgs-parcel/geocode?q=주소           -> {lat, lon, text, type}
#   GET /api/kgs-parcel/around?lat=&lon=&r=150   -> {parcels: [{pnu, jibun, jimok, addr, rings: [[[lon, lat], ...]]}]}
#   GET /api/kgs-parcel/search?q=화곡동 1000     -> {items: [{text, sub, kind, lat, lon}]}  (검색창 후보)
#   GET /api/kgs-parcel/zone?lat=&lon=&r=80      -> {zones: [{layer, name, polys: [[outer, hole...]]}]}  (용도지역 4층 + 개발제한구역)
#   GET /api/kgs-parcel/site?lat=&lon=&r=600     -> {o, unit, bld, roads, rails, areas, subway}  (주변 건물·도로·철도·학교·공원, 3D 모형용, 좌표는 o 에서 0.1m 정수)
import hashlib, hmac, json, os, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open('/opt/mcmap/config.json', encoding='utf-8'))
KEY, DOMAIN = CFG.get('vworld_key') or '', CFG.get('vworld_domain') or 'https://azzas3d.com'
TOKEN = open(os.path.join(HERE, 'token'), encoding='utf-8').read().strip()
CACHE = os.path.join(HERE, 'cache'); os.makedirs(CACHE, exist_ok=True)
PORT = int(os.environ.get('PORT', '5181'))
UA = {'User-Agent': 'kgs-parcel/1.0'}
LOCK, HITS = threading.Lock(), []


def vw(path, params, timeout=30):
    q = {**params, 'key': KEY, 'domain': DOMAIN}
    return json.loads(urllib.request.urlopen(urllib.request.Request(f'https://api.vworld.kr/req/{path}?' + urllib.parse.urlencode(q), headers=UA), timeout=timeout).read())


def cached(name, fn, ttl=30 * 86400):
    p = os.path.join(CACHE, hashlib.sha1(name.encode()).hexdigest() + '.json')
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        return json.load(open(p, encoding='utf-8'))
    out = fn()
    if out is not None:
        tmp = p + '.tmp'; json.dump(out, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False); os.replace(tmp, p)
    return out


def geocode(q):
    # 도로명(…로·길 + 번호)이면 도로명부터, 아니면 지번부터. 브이월드가 엉뚱한 지역을 맞추는 일이 있어
    # 주소에 적힌 구·군·동·읍·면·리·로·길 이름이 결과에 모두 들어 있을 때만 받아들인다.
    import re
    toks = [t for t in re.findall(r'[가-힣0-9]+', q) if re.search(r'[가-힣](구|군|동|읍|면|리|로|길|가)$', t) and not re.match(r'^\d', t)]
    road = bool(re.search(r'[가-힣0-9](로|길)\s*\d', q))
    for t in (('road', 'parcel') if road else ('parcel', 'road')):
        j = vw('address', {'service': 'address', 'request': 'getcoord', 'version': '2.0', 'crs': 'epsg:4326', 'refine': 'true', 'simple': 'false', 'format': 'json', 'type': t, 'address': q})
        r = j.get('response', {})
        if r.get('status') != 'OK': continue
        txt = (r.get('refined') or {}).get('text') or ''
        if toks and not all(k in txt for k in toks): continue
        pt = r['result']['point']
        return {'lat': float(pt['y']), 'lon': float(pt['x']), 'text': txt or q, 'type': t}
    return {'error': 'not_found'}


def rings_of(g):
    cs = g.get('coordinates') or []
    if g.get('type') == 'Polygon': cs = [cs]
    return [[[round(x, 7), round(y, 7)] for x, y in poly[0]] for poly in cs if poly and poly[0]]


def around(lat, lon, r):
    kx, ky = 111320 * __import__('math').cos(lat * 3.14159265 / 180), 111320
    w, e, s, n = lon - r / kx, lon + r / kx, lat - r / ky, lat + r / ky
    out, seen, page = [], set(), 1
    while page <= 6:
        j = vw('data', {'service': 'data', 'version': '2.0', 'request': 'getfeature', 'format': 'json', 'size': '1000', 'page': str(page), 'geometry': 'true', 'attribute': 'true',
                        'crs': 'EPSG:4326', 'geomfilter': f'BOX({w},{s},{e},{n})', 'data': 'LP_PA_CBND_BUBUN'})
        resp = j.get('response', {})
        if resp.get('status') == 'NOT_FOUND': break
        if resp.get('status') != 'OK': return None          # 실패는 캐시하지 않는다
        feats = resp.get('result', {}).get('featureCollection', {}).get('features', [])
        for f in feats:
            pr = f.get('properties', {}); pnu = str(pr.get('pnu') or '')
            if pnu in seen: continue
            seen.add(pnu); jb = (pr.get('jibun') or '').strip()
            out.append({'pnu': pnu, 'jibun': jb, 'jimok': jb[-1:] if jb and not jb[-1].isdigit() else '', 'addr': pr.get('addr') or '', 'rings': rings_of(f.get('geometry') or {})})
        tot = int((resp.get('page') or {}).get('total') or 1)
        if page >= tot or len(feats) < 1000: break
        page += 1
    return {'parcels': out}


def _vsearch(q, typ, cat, n):
    p = {'service': 'search', 'request': 'search', 'version': '2.0', 'crs': 'EPSG:4326', 'size': str(n), 'page': '1', 'query': q, 'type': typ, 'format': 'json', 'errorformat': 'json'}
    if cat: p['category'] = cat
    r = vw('search', p).get('response', {})
    if r.get('status') not in ('OK', 'NOT_FOUND'): raise RuntimeError(r.get('status'))
    out = []
    for it in (r.get('result') or {}).get('items', []):
        a, pt = it.get('address') or {}, it.get('point') or {}
        try: la, lo = round(float(pt['y']), 6), round(float(pt['x']), 6)
        except Exception: continue
        if typ == 'place': text, sub = it.get('title') or '', a.get('road') or a.get('parcel') or ''
        elif typ == 'district': text, sub = it.get('title') or '', '행정구역'
        elif cat == 'road': text, sub = a.get('road') or '', ('지번 ' + a['parcel']) if a.get('parcel') else ''
        else: text, sub = a.get('parcel') or '', ''
        if text: out.append({'text': text, 'sub': sub, 'kind': 'place' if typ == 'place' else 'district' if typ == 'district' else cat, 'lat': la, 'lon': lo})
    return out


def search(q):
    # 검색창 자동완성: 동네 이름(행정구역), 장소·건물 이름, 도로명·지번 주소를 함께 보여 준다.
    # 숫자가 있으면 주소부터, 없으면 이름부터. 같은 글자·같은 자리는 한 번만.
    import re
    addr_like = bool(re.search(r'\d', q))
    plan = [('district', 'L4', 3), ('address', 'road', 6), ('address', 'parcel', 6), ('place', None, 10)] if addr_like else \
           [('district', 'L4', 3), ('place', None, 10), ('address', 'road', 5), ('address', 'parcel', 4)]
    found, fail = [], 0
    nq = re.sub(r'\s+', '', q)
    def rank(it):                     # 이름이 똑같은 것 > 이름이 그걸로 시작 > 주소 있는 것 > 짧은 이름
        t = re.sub(r'\s+', '', it['text'])
        return (t != nq, not t.startswith(nq), not it['sub'], len(t))
    for typ, cat, n in plan:
        try: got = _vsearch(q, typ, cat, n)
        except Exception: fail += 1; continue
        found += sorted(got, key=rank) if typ == 'place' else got
    if fail == len(plan): return None
    # 여러 낱말("강원대학교 춘천캠퍼스")이 통째로 안 맞으면 앞 낱말로 찾고, 나머지 낱말이 이름·주소에 든 것을 위로
    words = q.split()
    if not found and len(words) > 1:
        rest = [re.sub(r'(캠퍼스|지점|본점|점|역|센터)$', '', w) for w in words[1:]]
        rest = [w for w in rest if len(w) >= 2]
        for head in (' '.join(words[:-1]), words[0], ''.join(words)):
            try: got = _vsearch(head, 'place', None, 20) + _vsearch(head, 'address', 'road', 5)
            except Exception: got = []
            if got:
                score = lambda it: (-sum(w in it['text'] + ' ' + it['sub'] for w in rest), it['kind'] != 'place', not it['text'].replace(' ', '').startswith(head.replace(' ', '')), not it['sub'], len(it['text']))
                found = sorted(got, key=score)
                break
    out, seen = [], set()
    for it in found:
        k1, k2 = re.sub(r'\s+', '', it['text'] + '|' + it['sub']), (round(it['lat'], 4), round(it['lon'], 4), it['kind'] == 'place' and it['text'])
        if k1 in seen or k2 in seen: continue
        seen.add(k1); seen.add(k2); out.append(it)
    return {'items': out[:12]}


# 용도지역: 도시지역(UQ111) + 관리(UQ112)·농림(UQ113)·자연환경보전(UQ114). 개발제한구역(UD801)은 따로 표시
ZONE_LAYERS = ('LT_C_UQ111', 'LT_C_UQ112', 'LT_C_UQ113', 'LT_C_UQ114', 'LT_C_UD801')


def zones(lat, lon, r):
    kx, ky = 111320 * __import__('math').cos(lat * 3.14159265 / 180), 111320
    w, e, s, n = lon - r / kx, lon + r / kx, lat - r / ky, lat + r / ky
    out = []
    for lay in ZONE_LAYERS:
        page = 1
        while page <= 3:
            j = vw('data', {'service': 'data', 'version': '2.0', 'request': 'getfeature', 'format': 'json', 'size': '1000', 'page': str(page), 'geometry': 'true', 'attribute': 'true',
                            'crs': 'EPSG:4326', 'geomfilter': f'BOX({w},{s},{e},{n})', 'data': lay})
            resp = j.get('response', {})
            if resp.get('status') == 'NOT_FOUND': break
            if resp.get('status') != 'OK': return None
            feats = resp.get('result', {}).get('featureCollection', {}).get('features', [])
            for f in feats:
                pr = f.get('properties', {})
                nm = (pr.get('uname') or pr.get('dgm_nm') or '').strip()
                g = f.get('geometry') or {}; cs = g.get('coordinates') or []
                if g.get('type') == 'Polygon': cs = [cs]
                # 구멍(안쪽 고리)까지 넘긴다: 일반주거 한가운데 준주거가 뚫려 있는 식이 흔하다
                polys = [[[[round(x, 7), round(y, 7)] for x, y in ring] for ring in poly if len(ring) >= 4] for poly in cs if poly]
                out.append({'layer': lay[-5:], 'name': nm, 'polys': [p for p in polys if p]})
            tot = int((resp.get('page') or {}).get('total') or 1)
            if page >= tot or len(feats) < 1000: break
            page += 1
    return {'zones': out}


def feats(lay, w, s, e, n, pages=8):
    # 첫 쪽에서 전체 쪽수를 보고 나머지 쪽은 함께 받는다(건물이 빽빽한 동네는 4~5쪽)
    from concurrent.futures import ThreadPoolExecutor
    def one(page):
        # 브이월드가 가끔 한 요청을 십수 초 붙잡는다. 5초 넘으면 끊고 한 번 더(12초) 묻는다
        try: return one_(page, 5)
        except Exception: return one_(page, 12)
    def one_(page, to):
        j = vw('data', {'service': 'data', 'version': '2.0', 'request': 'getfeature', 'format': 'json', 'size': '1000', 'page': str(page), 'geometry': 'true', 'attribute': 'true',
                        'crs': 'EPSG:4326', 'geomfilter': f'BOX({w},{s},{e},{n})', 'data': lay}, timeout=to)
        resp = j.get('response', {})
        if resp.get('status') == 'NOT_FOUND': return [], 0
        if resp.get('status') != 'OK': raise RuntimeError(lay + ' ' + str(resp.get('status')))
        return resp.get('result', {}).get('featureCollection', {}).get('features', []), int((resp.get('page') or {}).get('total') or 1)
    out, tot = one(1)
    if tot > 1:
        with ThreadPoolExecutor(min(pages, tot) - 1) as ex:
            for fs, _ in ex.map(one, range(2, min(pages, tot) + 1)): out += fs
    return out


def parts_of(g):
    cs = g.get('coordinates') or []
    if g.get('type') in ('Polygon', 'LineString'): cs = [cs]
    return cs


def num(v):
    try: return float(v)
    except Exception: return 0.0


def inside(x, y, ring):
    c = False
    for i in range(len(ring)):
        x1, y1 = ring[i][0], ring[i][1]; x2, y2 = ring[i - 1][0], ring[i - 1][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c


# 도시·군계획시설의 결정·구조 및 설치기준에 관한 규칙의 도로 규모별 폭(구간 가운데 값, m)
GRADE_W = {'광로1류': 70, '광로2류': 60, '광로3류': 45, '대로1류': 37.5, '대로2류': 32.5, '대로3류': 27.5, '중로1류': 22.5, '중로2류': 17.5, '중로3류': 13.5, '소로1류': 11, '소로2류': 9, '소로3류': 6}
AREA_KIND = ('학교', '사회복지시설', '공원', '녹지', '유원지', '공공공지', '광장', '도서관', '청소년수련시설', '문화시설', '체육시설')


def site(lat, lon, r):
    # 3D 모형용 주변 자료. 건물은 GIS건물통합정보(용도코드·층수·연면적), 도로는 도로명 중심선(폭은 도시계획 도로 등급, 없으면 이름의 대로·로·길),
    # 고속도로는 표준노드링크, 철도·학교·공원은 도시계획시설 면. 일곱 층을 함께 받는다.
    import math
    from concurrent.futures import ThreadPoolExecutor
    kx, ky = 111320 * math.cos(lat * math.pi / 180), 111320
    w, e, s, n = lon - r / kx, lon + r / kx, lat - r / ky, lat + r / ky
    # 좌표는 가운데(o)에서 잰 0.1m 단위 정수로 보낸다(경위도 소수보다 절반 이하 크기)
    loc = lambda ring: [[round((x - lon) * kx * 10), round((y - lat) * ky * 10)] for x, y in (q[:2] for q in ring)]
    lays = {'bld': 'LT_C_BLDGINFO', 'rd': 'LT_L_SPRD', 'moct': 'LT_L_MOCTLINK', 'grade': 'LT_C_UPISUQ151', 'traf': 'LT_C_UPISUQ152', 'space': 'LT_C_UPISUQ153', 'pub': 'LT_C_UPISUQ155'}
    with ThreadPoolExecutor(len(lays)) as ex:
        fut = {k: ex.submit(feats, v, w, s, e, n) for k, v in lays.items()}
        got = {k: f.result() for k, f in fut.items()}
    bld, seen = [], set()
    for f in got['bld']:
        p = f.get('properties') or {}
        for poly in parts_of(f.get('geometry') or {}):
            if not poly or len(poly[0]) < 4: continue
            ring = loc(poly[0]); k = (ring[0][0], ring[0][1], len(ring), p.get('usability'))
            if math.hypot(ring[0][0], ring[0][1]) > (r + 30) * 10: continue     # 네모 귀퉁이는 버리고 둥글게
            if k in seen: continue                 # 같은 건물이 대장 여러 장으로 겹쳐 오는 일이 있다
            seen.add(k)
            bld.append({'ring': ring, 'nm': (p.get('bld_nm') or '').strip(), 'use': p.get('usability') or '', 'fl': int(num(p.get('grnd_flr'))), 'h': num(p.get('height')), 'ta': num(p.get('totalarea'))})
    grades = []
    for f in got['grade']:
        nm = ((f.get('properties') or {}).get('lcl_nam') or '').strip()
        if nm in GRADE_W:
            for poly in parts_of(f.get('geometry') or {}):
                if poly and len(poly[0]) >= 4:
                    xs, ys = [q[0] for q in poly[0]], [q[1] for q in poly[0]]
                    grades.append((GRADE_W[nm], nm, poly[0], (min(xs), min(ys), max(xs), max(ys))))
    def width(line, name):
        best = None
        for t in (0.25, 0.5, 0.75):                 # 선 위 세 점 가운데 도시계획 도로 면 안에 드는 것
            x, y = line[min(len(line) - 1, int(t * (len(line) - 1)))][:2]
            for gw, gn, ring, bb in grades:
                if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and inside(x, y, ring) and (best is None or gw > best[0]): best = (gw, gn)
        if best: return best
        # 도로명주소법 시행령의 도로 구분(대로: 폭 40m 이상, 로: 12~40m, 길: 그 밖)으로 어림
        return (35, '') if name.endswith('대로') else (15, '') if name.endswith('로') else (6, '')
    roads = []
    for f in got['rd']:
        nm = ((f.get('properties') or {}).get('rn') or '').strip()
        for line in parts_of(f.get('geometry') or {}):
            if len(line) < 2: continue
            wd, gn = width(line, nm)
            roads.append({'line': loc(line), 'name': nm, 'w': wd, 'grade': gn})
    for f in got['moct']:
        p = f.get('properties') or {}
        if '고속' not in (p.get('rd_rank_h') or ''): continue
        for line in parts_of(f.get('geometry') or {}):
            if len(line) >= 2: roads.append({'line': loc(line), 'name': (p.get('road_name') or '').strip(), 'w': 24, 'grade': '고속도로'})
    rails, areas, sub = [], [], 0
    for k in ('traf', 'space', 'pub'):
        for f in got[k]:
            p = f.get('properties') or {}; kind = (p.get('lcl_nam') or '').strip(); nm = (p.get('dgm_nm') or '').strip()
            for poly in parts_of(f.get('geometry') or {}):
                if not poly or len(poly[0]) < 4: continue
                if kind == '철도':
                    # 일반철도·고속철도만 철도 거리 검사에 쓴다. 도시철도(대부분 지하)·역사·환기구는 수만 센다
                    if (p.get('mls_nam') or '') in ('일반철도', '고속철도'): rails.append({'ring': loc(poly[0]), 'name': nm})
                    else: sub += 1
                elif kind in AREA_KIND: areas.append({'ring': loc(poly[0]), 'kind': kind, 'name': nm})
    return {'o': [lon, lat], 'unit': 0.1, 'bld': bld, 'roads': roads, 'rails': rails, 'areas': areas, 'subway': sub}


class H(BaseHTTPRequestHandler):
    def send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if not hmac.compare_digest(self.headers.get('X-Kgs-Token', ''), TOKEN): return self.send(403, {'error': 'forbidden'})
        now = time.time()
        with LOCK:
            HITS[:] = [t for t in HITS if now - t < 60]
            if len(HITS) > 240: return self.send(429, {'error': 'busy'})
            HITS.append(now)
        u = urllib.parse.urlparse(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path == '/api/kgs-parcel/geocode':
                s = (q.get('q') or '').strip()[:120]
                if not s: return self.send(400, {'error': 'q'})
                return self.send(200, cached('g:' + s, lambda: geocode(s)))
            if u.path == '/api/kgs-parcel/around':
                la, lo, r = float(q['lat']), float(q['lon']), max(30, min(250, float(q.get('r', 150))))
                if not (33 < la < 39 and 124 < lo < 132): return self.send(400, {'error': 'range'})
                la, lo = round(la, 4), round(lo, 4)
                out = cached(f'a:{la},{lo},{int(r)}', lambda: around(la, lo, r))
                return self.send(200, out) if out is not None else self.send(502, {'error': 'vworld'})
            if u.path == '/api/kgs-parcel/search':
                s = (q.get('q') or '').strip()[:60]
                if len(s) < 2: return self.send(400, {'error': 'q'})
                out = cached('s3:' + s, lambda: search(s), ttl=7 * 86400)
                return self.send(200, out) if out is not None else self.send(502, {'error': 'vworld'})
            if u.path == '/api/kgs-parcel/zone':
                la, lo, r = float(q['lat']), float(q['lon']), max(20, min(200, float(q.get('r', 80))))
                if not (33 < la < 39 and 124 < lo < 132): return self.send(400, {'error': 'range'})
                la, lo = round(la, 4), round(lo, 4)
                out = cached(f'z:{la},{lo},{int(r)}', lambda: zones(la, lo, r))
                return self.send(200, out) if out is not None else self.send(502, {'error': 'vworld'})
            if u.path == '/api/kgs-parcel/site':
                la, lo, r = float(q['lat']), float(q['lon']), max(100, min(700, float(q.get('r', 600))))
                if not (33 < la < 39 and 124 < lo < 132): return self.send(400, {'error': 'range'})
                la, lo = round(la, 4), round(lo, 4)
                def go():
                    try: return site(la, lo, r)
                    except Exception: return None          # 한 층이라도 실패하면 캐시하지 않고 502
                out = cached(f'site3:{la},{lo},{int(r)}', go, ttl=14 * 86400)
                return self.send(200, out) if out is not None else self.send(502, {'error': 'vworld'})
            return self.send(404, {'error': 'path'})
        except Exception as ex:
            return self.send(500, {'error': type(ex).__name__})

    def log_message(self, *a): pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
