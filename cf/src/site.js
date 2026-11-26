// 3D 부지·배치 검토(site3d.html)의 서버 쪽: 배치도 그림을 AI 가 읽어 설비 목록(JSON)으로 바꾼다.
//   POST /api/site/drawing  {image: 'data:image/png;base64,...'}
//   -> {items:[{name,type,cx,cy,w,d}], walls:[{x1,y1,x2,y2}], site:{w,d}, notes, model, cached}
// 판정(거리 기준)은 AI 가 하지 않는다. AI 는 도면의 위치·치수만 읽고, 판정은 브라우저의 점검표 코드(cf-tools.js)가 한다.
// 같은 그림은 Cache API 에 하루 보관해 시연 중 같은 도면을 다시 올려도 즉시·같은 답이 나온다.

const OPENAI = 'https://api.openai.com/v1/chat/completions';
const TYPES = ['process', 'compressed', 'storage', 'charger', 'building', 'other'];
const PROMPT = `너는 수소충전소 배치도를 읽는 도면 검토자다. 그림은 부지 배치도(평면)이다.
좌표계: 부지 중심이 (0,0), 오른쪽이 +x, 위쪽이 +y, 단위 m. 도면 가장자리의 격자 숫자(5m 간격)와 치수선을 기준으로 위치를 읽어라.
할 일:
1) 사업소 경계(부지)의 가로(w)·세로(d) 길이.
2) 설비·건축물마다 이름, 종류, 중심 좌표(cx, cy), 가로(w)·세로(d). 도면에 적힌 치수(예: 6×4 m)가 있으면 그 값을 그대로 쓴다.
   종류: process(처리설비: 압축기·프리쿨러 등), compressed(압축가스설비: 축압기), storage(저장설비: 튜브트레일러·저장용기),
   charger(충전설비: 충전기·디스펜서), building(건축물: 관리동 등), other(그 밖).
3) 방호벽 선분마다 양 끝 좌표(x1,y1,x2,y2).
도면에 없는 것은 지어내지 마라. 읽기 어려운 값은 notes 에 적어라.`;
const SCHEMA = {
  type: 'object', additionalProperties: false, required: ['site', 'items', 'walls', 'notes'],
  properties: {
    site: { type: 'object', additionalProperties: false, required: ['w', 'd'], properties: { w: { type: 'number' }, d: { type: 'number' } } },
    items: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['name', 'type', 'cx', 'cy', 'w', 'd'],
      properties: { name: { type: 'string' }, type: { type: 'string', enum: TYPES }, cx: { type: 'number' }, cy: { type: 'number' },
        w: { type: 'number' }, d: { type: 'number' } } } },
    walls: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['x1', 'y1', 'x2', 'y2'],
      properties: { x1: { type: 'number' }, y1: { type: 'number' }, x2: { type: 'number' }, y2: { type: 'number' } } } },
    notes: { type: 'string' },
  },
};

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'Content-Type': 'application/json; charset=utf-8' } });

async function sha(s) {
  const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, '0')).join('');
}

// 지적도: AZZAS3D 서버(azzas3d.com/api/kgs-parcel)가 브이월드에서 받아 준다. 키는 그 서버에만 있고, 여기서는 토큰만 붙인다.
//   GET /api/site/parcel/geocode?q=주소, GET /api/site/parcel/around?lat=&lon=&r=, GET /api/site/parcel/zone?lat=&lon=&r= (용도지역)
//   GET /api/site/parcel/site?lat=&lon=&r=600 (주변 건물·도로·철도·학교·공원: 3D 모형용, 브이월드)
async function handleParcel(req, env, p) {
  if (!env.KGS_PARCEL_TOKEN) return json({ error: '지적도 통로가 설정되지 않았어요' }, 503);
  const url = new URL(req.url), kind = p.slice('/api/site/parcel/'.length);
  if (!['geocode', 'around', 'zone', 'search', 'site'].includes(kind) || req.method !== 'GET') return json({ error: '없는 주소' }, 404);
  const t = new URL(`https://azzas3d.com/api/kgs-parcel/${kind}`);
  for (const k of ['q', 'lat', 'lon', 'r']) if (url.searchParams.has(k)) t.searchParams.set(k, url.searchParams.get(k).slice(0, 120));
  const key = new Request('https://site-parcel.cache/v2/' + (kind === 'search' ? 's4/' : kind === 'site' ? 'b3/' : '') + await sha(t.search + kind));
  const hit = await caches.default.match(key);
  if (hit) return new Response(hit.body, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  const r = await fetch(t, { headers: { 'X-Kgs-Token': env.KGS_PARCEL_TOKEN }, signal: AbortSignal.timeout(40000) }).catch(() => null);
  if (!r || !r.ok) return json({ error: `지적도를 못 받았어요 (${r ? r.status : '연결 실패'})` }, 502);
  const body = await r.text();
  await caches.default.put(key, new Response(body, { headers: { 'Cache-Control': 'max-age=604800' } }));
  return new Response(body, { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}

// 주변 건물·도로(OpenStreetMap Overpass): 공개 서버 여러 곳에 함께 묻고 먼저 온 답을 쓴다. 같은 자리는 7일 동안 캐시에서 바로 준다.
//   GET /api/site/osm?lat=&lon=&r=600   (응답 머리 X-Osm-Cache: hit|miss)
const OSM_EPS = ['https://maps.mail.ru/osm/tools/overpass/api/interpreter', 'https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter'];
export const osmQuery = (R, la, lo) => `[out:json][timeout:60];(way["building"](around:${R},${la},${lo});nwr["amenity"~"^(school|kindergarten|hospital|childcare|university|college|clinic|library|social_facility)$"](around:${R + 30},${la},${lo});way["highway"](around:${R},${la},${lo});way["railway"](around:${R + 100},${la},${lo});way["landuse"](around:${R},${la},${lo});way["leisure"~"park|pitch|playground|garden"](around:${R},${la},${lo});way["natural"~"wood|water|scrub|grassland"](around:${R},${la},${lo}););out geom tags;`;
async function handleOsm(req) {
  const url = new URL(req.url), la = +url.searchParams.get('lat'), lo = +url.searchParams.get('lon'), R = +url.searchParams.get('r') === 380 ? 380 : 600;
  if (!(la > 32 && la < 39.5 && lo > 124 && lo < 132)) return json({ error: '국내 좌표가 아니에요' }, 400);
  const lat = la.toFixed(6), lon = lo.toFixed(6), key = new Request(`https://site-osm.cache/v1/${R}/${lat},${lon}`);
  const hdr = c => ({ 'Content-Type': 'application/json; charset=utf-8', 'X-Osm-Cache': c, 'Access-Control-Expose-Headers': 'X-Osm-Cache' });
  const hit = await caches.default.match(key);
  if (hit) return new Response(hit.body, { headers: hdr('hit') });
  const ac = new AbortController(), q = 'data=' + encodeURIComponent(osmQuery(R, lat, lon));
  const one = (ep, delay) => new Promise(r => setTimeout(r, delay)).then(async () => {
    if (ac.signal.aborted) throw new Error('끝남');
    const r = await fetch(ep, { method: 'POST', body: q, signal: ac.signal, headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'hydrogen-guide-site3d/1.0 (+https://hydrogen-guide.tmdfoqhdl030.workers.dev)' } });
    if (!r.ok) throw new Error(String(r.status));
    const buf = await r.arrayBuffer(), tail = new TextDecoder().decode(buf.slice(-600));
    if (/"remark"\s*:\s*"[^"]*(error|timed out)/i.test(tail) || !/\]\s*\}\s*$/.test(tail)) throw new Error('불완전');   // 시간 초과로 잘린 답은 버린다
    return buf;
  });
  let buf;
  try { buf = await Promise.any([one(OSM_EPS[0], 0), one(OSM_EPS[1], 0), one(OSM_EPS[2], 3000)]); }
  catch (e) { return json({ error: '공개 지도 서버가 바빠요' }, 502); }
  finally { ac.abort(); }
  await caches.default.put(key, new Response(buf, { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'max-age=604800' } }));
  return new Response(buf, { headers: hdr('miss') });
}

export async function handleSite(req, env, p) {
  if (p.startsWith('/api/site/parcel/')) return handleParcel(req, env, p);
  if (p === '/api/site/osm' && req.method === 'GET') return handleOsm(req);
  if (p !== '/api/site/drawing' || req.method !== 'POST') return json({ error: '없는 주소' }, 404);
  if (!env.OPENAI_API_KEY) return json({ error: 'AI 키가 없어 도면을 읽을 수 없습니다' }, 503);
  const b = await req.json().catch(() => ({}));
  const img = String(b.image || '');
  if (!/^data:image\/(png|jpeg);base64,[A-Za-z0-9+/=]+$/.test(img) || img.length > 6_000_000) return json({ error: 'PNG·JPEG 그림(6MB 이하)만 받습니다' }, 400);
  const key = new Request(`https://site-drawing.cache/${await sha(img)}`);
  const cache = caches.default;
  const hit = await cache.match(key);
  if (hit) return json({ ...(await hit.json()), cached: true });
  const model = env.OPENAI_MODEL || 'gpt-6.1-sol';
  const r = await fetch(OPENAI, {
    method: 'POST', signal: AbortSignal.timeout(90000),
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.OPENAI_API_KEY}` },
    body: JSON.stringify({
      model, reasoning_effort: env.OPENAI_EFFORT || 'low', max_completion_tokens: 8000,
      messages: [{ role: 'user', content: [{ type: 'text', text: PROMPT }, { type: 'image_url', image_url: { url: img, detail: 'high' } }] }],
      response_format: { type: 'json_schema', json_schema: { name: 'layout', strict: true, schema: SCHEMA } },
    }),
  }).catch(e => ({ ok: false, status: 0, text: async () => String(e) }));
  if (!r.ok) return json({ error: `AI 도면 읽기 실패 (${r.status})`, detail: (await r.text()).slice(0, 300) }, 502);
  const d = await r.json();
  let out;
  try { out = JSON.parse(d.choices[0].message.content); } catch (e) { return json({ error: 'AI 답을 해석하지 못했습니다' }, 502); }
  out.model = model;
  out.usage = { in: d.usage?.prompt_tokens, out: d.usage?.completion_tokens };
  await cache.put(key, new Response(JSON.stringify(out), { headers: { 'Cache-Control': 'max-age=86400' } }));
  return json({ ...out, cached: false });
}
