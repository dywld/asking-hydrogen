import json, math, sys
la, lo = 37.54513, 127.17
kx = 111320 * math.cos(la * math.pi / 180)
raw = json.load(open('osm_w.json', encoding='utf-8'))['elements']
ROAD_W = {'motorway': 24, 'trunk': 22, 'primary': 20, 'secondary': 14, 'tertiary': 10, 'unclassified': 6, 'residential': 6,
          'primary_link': 7, 'secondary_link': 7, 'tertiary_link': 6, 'trunk_link': 8, 'motorway_link': 8, 'service': 4, 'living_street': 5}
DEF_LV = {'house': 2, 'warehouse': 1, 'school': 4, 'kindergarten': 2, 'commercial': 3, 'retail': 2, 'office': 6, 'apartments': 15, 'shelter': 1, 'roof': 1, 'yes': 2, 'industrial': 2}
out = {'buildings': [], 'roads': [], 'areas': []}
for e in raw:
    t = e.get('tags', {}); g = e.get('geometry') or []
    pts = [[round((p['lon'] - lo) * kx, 2), round((p['lat'] - la) * 111320, 2)] for p in g]
    if len(pts) > 2 and pts[0] == pts[-1]: pts = pts[:-1]
    if 'highway' in t:
        k = t['highway']
        if k not in ROAD_W: continue
        ln = t.get('lanes'); w = float(ln) * 3.25 if ln and ln.replace('.', '').isdigit() else ROAD_W[k]
        out['roads'].append({'pts': pts, 'w': w, 'k': k}); continue
    if len(pts) < 3: continue
    if 'building' in t:
        bd = t['building']
        try: lv = int(str(t.get('building:levels', '')).split(',')[0].split(';')[0])
        except ValueError: lv = None
        h = None
        try: h = float(t.get('height', '').replace('m', ''))
        except ValueError: pass
        est = not (lv or h)
        lv = lv or (round(h / 3) if h else DEF_LV.get(bd, 2))
        h = h or (lv * 2.9 + (1.2 if bd != 'apartments' else 0.8))
        out['buildings'].append({'pts': pts, 'h': round(h, 1), 'lv': lv, 'k': bd, 'n': t.get('name', ''), 'est': est})
        continue
    k = t.get('leisure') or t.get('landuse') or t.get('natural') or ''
    if k in ('park', 'wood', 'forest', 'grass', 'playground', 'recreation_ground', 'pitch', 'meadow', 'orchard', 'farmland', 'scrub', 'garden', 'cemetery', 'water'):
        out['areas'].append({'pts': pts, 'k': k})
    elif t.get('waterway') == 'riverbank' or t.get('natural') == 'water':
        out['areas'].append({'pts': pts, 'k': 'water'})
json.dump(out, open('m3d_world.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print({k: len(v) for k, v in out.items()})
