#!/usr/bin/env python3
"""OSM 원자료(osm_raw_*.json) -> 3D 부지 검토 화면용 자료(cf/public_extra/site/<이름>.json).

  python site3d/prep_site.py gangdong "H강동수소충전소 (서울 강동구 천호대로, 상일동)"

좌표는 중심점 기준 미터(x 동쪽, y 북쪽)로 바꾼다. 보호시설 구분은 고압가스 안전관리법 시행규칙 별표 2:
  제1종: 학교·유치원·어린이집·어린이놀이터·학원·병원(의원)·도서관·청소년수련시설·경로당·시장·공중목욕탕·
         호텔·여관·극장·교회·공회당, 또는 사람을 수용하는 건축물로서 연면적 1천㎡ 이상
  제2종: 주택, 또는 연면적 100㎡ 이상 1천㎡ 미만
OSM 은 용도·층수가 빠진 건물이 많으므로 추정한 값에는 est 표시를 붙여 화면에 '추정'으로 보인다.
지도 자료: (c) OpenStreetMap contributors, ODbL.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRST_AMENITY = {'school', 'kindergarten', 'childcare', 'hospital', 'clinic', 'library', 'marketplace',
                 'place_of_worship', 'theatre', 'community_centre', 'public_bath', 'social_facility',
                 'university', 'college'}
FIRST_BUILDING = {'school', 'kindergarten', 'hospital', 'church', 'hotel', 'university', 'college'}
HOUSE = {'house', 'detached', 'residential', 'semidetached_house', 'terrace', 'bungalow'}
ROAD_W = {'motorway': 24, 'trunk': 22, 'primary': 20, 'secondary': 14, 'tertiary': 10, 'unclassified': 6,
          'residential': 6, 'primary_link': 7, 'secondary_link': 7, 'tertiary_link': 6, 'service': 4}
LABEL = {'school': '학교', 'kindergarten': '유치원', 'childcare': '어린이집', 'hospital': '병원', 'clinic': '의원',
         'library': '도서관', 'university': '대학', 'college': '대학', 'apartments': '공동주택', 'house': '주택',
         'commercial': '상업시설', 'retail': '상가', 'office': '업무시설', 'industrial': '공장', 'shelter': '정자'}


def area(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


def main(name, address):
    raw = json.load(open(ROOT / f'site3d/osm_raw_{name}.json', encoding='utf-8'))
    la, lo = raw['center']
    kx, ky = 111320 * math.cos(math.radians(la)), 111320.0
    xy = lambda p: [round((p['lon'] - lo) * kx, 2), round((p['lat'] - la) * ky, 2)]
    feats, zones, roads, rails = [], [], [], []
    for e in raw['elements']:
        t, g = e.get('tags', {}), e.get('geometry') or []
        pts = [xy(p) for p in g]
        if len(pts) > 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if 'highway' in t and len(pts) >= 2:
            hw = t['highway']
            lanes = t.get('lanes', '')
            w = float(lanes) * 3.25 if lanes.replace('.', '').isdigit() else ROAD_W.get(hw, 2.5)
            roads.append({'pts': pts, 'kind': hw, 'name': t.get('name', ''), 'w': round(w, 1),
                          'road_law': hw in ROAD_W and hw != 'service', 'w_est': not lanes})
            continue
        if 'railway' in t and len(pts) >= 2:
            rails.append({'pts': pts, 'kind': t['railway'], 'name': t.get('name', '')})
            continue
        if len(pts) < 3:
            continue
        am, bd = t.get('amenity', ''), t.get('building', '')
        if 'building' in t:
            a = area(pts)
            lv = t.get('building:levels', '')
            h = t.get('height', '')
            try:
                height = float(h)
            except ValueError:
                height = None
            levels = int(float(lv)) if lv.replace('.', '').isdigit() else (max(1, round(height / 3.3)) if height else None)
            est = levels is None
            levels = levels or (1 if bd in ('shelter', 'roof') else 2)
            height = height or levels * 3.3
            floor = a * levels
            if am in FIRST_AMENITY or bd in FIRST_BUILDING:
                cls, why = 1, f"{LABEL.get(bd) or LABEL.get(am) or '시설'}(별표 2 제1호가목)"
            elif bd in ('shelter', 'roof', 'garage', 'carport'):
                cls, why = 0, '사람을 수용하지 않는 구조물'
            elif floor >= 1000:
                cls, why = 1, f'연면적 약 {floor:,.0f}㎡ ≥ 1천㎡(별표 2 제1호나목)'
            elif bd in HOUSE:
                cls, why = 2, '주택(별표 2 제2호가목)'
            elif floor >= 100:
                cls, why = 2, f'연면적 약 {floor:,.0f}㎡, 100~1천㎡(별표 2 제2호나목)'
            else:
                cls, why = 0, f'연면적 약 {floor:,.0f}㎡ < 100㎡'
            feats.append({'id': e['id'], 'pts': pts, 'h': round(height, 1), 'levels': levels, 'est': est,
                          'name': t.get('name', ''), 'use': LABEL.get(bd) or LABEL.get(am) or '용도 미상',
                          'cls': cls, 'why': why, 'floor': round(floor)})
        elif am in FIRST_AMENITY:
            zones.append({'id': e['id'], 'pts': pts, 'kind': am, 'name': t.get('name', ''), 'cls': 1,
                          'why': f"{LABEL.get(am, am)} 부지(별표 2 제1호가목, 부지 경계로 재서 보수적)"})
        elif t.get('leisure') or t.get('landuse') or t.get('natural'):
            zones.append({'id': e['id'], 'pts': pts, 'kind': t.get('leisure') or t.get('landuse') or t.get('natural'),
                          'name': t.get('name', ''), 'cls': 0, 'why': ''})
    # 부지 방향: 가장 가까운 도로법 도로(간선)의 방향에 맞춘다
    best = None
    for r in roads:
        if r['kind'] not in ('primary', 'secondary', 'trunk'):
            continue
        for (x1, y1), (x2, y2) in zip(r['pts'], r['pts'][1:]):
            d = min(math.hypot(x1, y1), math.hypot(x2, y2))
            if best is None or d < best[0]:
                best = (d, math.degrees(math.atan2(y2 - y1, x2 - x1)))
    ang = round(best[1] % 180, 1) if best else 0
    out = {'name': name, 'address': address, 'center': [la, lo], 'angle': ang,
           'site': {'w': 40, 'd': 30, 'note': '부지 경계는 예시(40×30m). 실제 지적 경계는 토지대장으로 확인'},
           'buildings': feats, 'zones': zones, 'roads': roads, 'rails': rails,
           'attribution': '지도 자료 © OpenStreetMap contributors (ODbL)'}
    dst = ROOT / f'cf/public_extra/site/{name}.json'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    c = [0, 0, 0]
    for f in feats:
        c[f['cls']] += 1
    print(dst, '건물', len(feats), '1종', c[1], '2종', c[2], '기타', c[0], '구역', len(zones), '도로', len(roads), '각도', ang)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
