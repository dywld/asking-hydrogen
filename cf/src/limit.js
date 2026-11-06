// 사용량 제한: Gemini 를 부르는 주소를 누가 계속 불러 무료 한도를 다 쓰지 못하게 한다.
// 코드가 공개 저장소에 있어 주소는 누구나 안다. 비밀 열쇠를 앱에 넣어도 앱을 풀면 나오므로, IP 별·하루 전체 횟수로 막는다.
// 세는 곳은 D1 표 하나(usage). 워커 위치를 서울로 고정해 두어(wrangler.toml placement) 한 곳에서 센다.
// D1 이 안 되면(한도 바닥 등) 막지 않는다: 그때 채팅은 오라클판으로 넘어가고, 거기는 자체 제한이 있다.

// 묶음별 한도. per_min·per_day 는 IP 하나, total 은 하루 전체(모든 IP 합).
const RULES = [
  { re: /^\/api\/chat$/, name: 'chat', per_min: 8, per_day: 100, total: 3000 },
  // 앱 서류 폴더 검토와 웹 접수 시연은 파일을 통째로 보내 Gemini 를 크게 쓴다. 둘을 한 묶음으로 센다.
  { re: /^\/api\/(app\/review|review\/submit)$/, name: 'doc', per_min: 3, per_day: 20, total: 300 },
];

const json = (o, status) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Retry-After': '60' } });

let ready = false;
async function ensure(db) {
  if (ready) return;
  await db.prepare('CREATE TABLE IF NOT EXISTS usage (k TEXT PRIMARY KEY, n INTEGER NOT NULL, day TEXT NOT NULL)').run();
  ready = true;
}

// 한국 시간 기준 날짜·분
function stamp() {
  const t = new Date(Date.now() + 9 * 3600e3).toISOString();
  return { day: t.slice(0, 10), min: t.slice(0, 16) };
}

// 막아야 하면 429 응답, 아니면 null
export async function checkLimit(req, env, path) {
  if (req.method !== 'POST') return null;
  const rule = RULES.find(r => r.re.test(path));
  if (!rule || !env.DB) return null;
  // 배포된 워커에서는 클라우드플레어가 늘 붙여 주고 손님이 지울 수 없다. 없으면 내 컴퓨터(wrangler dev·채점기)라 세지 않는다.
  const ip = req.headers.get('cf-connecting-ip');
  if (!ip) return null;
  const { day, min } = stamp();
  const keys = [`${rule.name}|m|${min}|${ip}`, `${rule.name}|d|${day}|${ip}`, `${rule.name}|t|${day}`];
  try {
    await ensure(env.DB);
    const st = env.DB.prepare('INSERT INTO usage (k, n, day) VALUES (?1, 1, ?2) ON CONFLICT(k) DO UPDATE SET n = n + 1 RETURNING n');
    const res = await env.DB.batch(keys.map(k => st.bind(k, day)));
    const [m, d, t] = res.map(r => r.results?.[0]?.n || 0);
    // 지난 날 기록은 가끔 지운다(100번에 1번)
    if (Math.random() < 0.01) await env.DB.prepare('DELETE FROM usage WHERE day < ?1').bind(day).run();
    if (m > rule.per_min) return json({ error: '요청이 너무 잦습니다. 1분 뒤에 다시 해 주세요.' }, 429);
    if (d > rule.per_day) return json({ error: `오늘 쓸 수 있는 횟수(${rule.per_day}번)를 다 썼습니다. 내일 다시 해 주세요.` }, 429);
    if (t > rule.total) return json({ error: '오늘은 이용자가 많아 잠시 멈췄습니다. 내일 다시 해 주세요.' }, 429);
  } catch (e) { /* 세지 못하면 막지 않는다 */ }
  return null;
}
