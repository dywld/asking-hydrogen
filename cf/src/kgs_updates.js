// KGS 원문 수집기는 오라클 서버에서 실행한다. 워커는 검증된 검색 조각을 D1에 반영한다.
const CODE = /^[A-Z]{2}\d{3}$/;
const SHA = /^[a-f0-9]{64}$/;
const encoder = new TextEncoder();
const LIMIT = 400_000;
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
});
const koreanDate = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);

async function authorized(req, key) {
  const given = req.headers.get('x-kgs-push-key') || '';
  if (!key || !given || given.length > 512) return false;
  const hash = async text => new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(text)));
  const [a, b] = await Promise.all([hash(given), hash(key)]);
  let mismatch = 0;
  for (let i = 0; i < a.length; i++) mismatch |= a[i] ^ b[i];
  return mismatch === 0;
}

export async function readKgsState(db) {
  const { results } = await db.prepare(
    'SELECT a.law, a.version, a.blocked_version, a.updated_at, v.effective_date ' +
    'FROM kgs_active a LEFT JOIN kgs_versions v ON v.law=a.law AND v.version=a.version ORDER BY a.law'
  ).all();
  return results;
}

async function readBody(req) {
  if (Number(req.headers.get('Content-Length') || 0) > LIMIT || !req.body) throw new Error('요청 크기 오류');
  const reader = req.body.getReader();
  const buf = new Uint8Array(LIMIT);
  let length = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (length + value.length > LIMIT) {
      await reader.cancel();
      throw new Error('요청 크기 오류');
    }
    buf.set(value, length);
    length += value.length;
  }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(buf.subarray(0, length)));
}

function validDate(s) {
  return typeof s === 'string' && /^20\d{2}-\d{2}-\d{2}$/.test(s)
    && Number.isFinite(Date.parse(s)) && new Date(s).toISOString().startsWith(s);
}

async function stage(db, law, b, tokenize) {
  const { version, total, start, rows, effective_date: date, release_hash: releaseHash } = b;
  if (typeof version !== 'string' || !SHA.test(version) || typeof releaseHash !== 'string' || !SHA.test(releaseHash)
      || !validDate(date) || !Number.isInteger(total) || total < 1 || total > 10000
      || !Number.isInteger(start) || start < 0 || !Array.isArray(rows) || !rows.length
      || rows.length > 48 || start + rows.length > total) return json({ error: '잘못된 버전 또는 자료 범위' }, 400);
  const validText = (v, max) => typeof v === 'string' && v.trim().length > 0 && v.length <= max && !v.includes('\0');
  if (rows.some(r => !r || !validText(r.article, 240) || !(r.article.startsWith(`[${law} `) || r.article.startsWith(`[${law}]`))
      || !validText(r.ref, 240) || r.ref !== r.article.split(']')[0] + ']'
      || !validText(r.title, 1000) || !validText(r.content, 32000))) return json({ error: '잘못된 검색 조각' }, 400);

  const values = rows.map(r => [r.article, r.title, r.content, r.ref, tokenize(`${law} ${r.title} ${r.content}`).join(' ')]);
  const payload = JSON.stringify(values);
  if (encoder.encode(payload).length > 1_500_000) return json({ error: '색인 크기 초과' }, 413);
  const create = db.prepare('INSERT OR IGNORE INTO kgs_versions VALUES (?,?,?,?,?)').bind(law, version, date, total, releaseHash);
  const insert = db.prepare(`
    INSERT OR IGNORE INTO kgs_docs (law, version, seq, article, title, content, ref, bg)
    SELECT ?1, ?2, ?3 + CAST(j.key AS INTEGER), j.value ->> 0, j.value ->> 1,
           j.value ->> 2, j.value ->> 3, j.value ->> 4
    FROM json_each(?4) j
    WHERE EXISTS (SELECT 1 FROM kgs_versions WHERE law=?1 AND version=?2
                  AND effective_date=?5 AND expected=?6 AND release_hash=?7)
  `).bind(law, version, start, payload, date, total, releaseHash);
  const confirm = db.prepare(`
    SELECT COUNT(*) AS matched FROM json_each(?4) j
    JOIN kgs_docs d ON d.law=?1 AND d.version=?2 AND d.seq=?3 + CAST(j.key AS INTEGER)
      AND d.article=j.value ->> 0 AND d.title=j.value ->> 1 AND d.content=j.value ->> 2 AND d.ref=j.value ->> 3
    WHERE EXISTS (SELECT 1 FROM kgs_versions WHERE law=?1 AND version=?2
                  AND effective_date=?5 AND expected=?6 AND release_hash=?7)
  `).bind(law, version, start, payload, date, total, releaseHash);
  const [, , result] = await db.batch([create, insert, confirm]);
  return result.results[0].matched === rows.length
    ? json({ staged: rows.length }) : json({ error: '같은 버전의 메타데이터 또는 조각이 다릅니다' }, 409);
}

async function activate(db, law, b, rollback) {
  const { version, expected_version: expected } = b;
  const validSha = s => typeof s === 'string' && SHA.test(s);
  if (!(validSha(version) || (rollback && version === null))
      || !(validSha(expected) || expected === null) || (rollback && (!expected || expected === version))) {
    return json({ error: '잘못된 버전 지정' }, 400);
  }
  // 적용일, 전체 조각 수, 현재 버전 비교와 교체를 한 SQL 문에서 확인한다.
  const r = await db.prepare(`
    INSERT INTO kgs_active (law, version, blocked_version)
    SELECT ?1, ?2, CASE WHEN ?5=1 THEN ?3 ELSE NULL END
    WHERE (SELECT version FROM kgs_active WHERE law=?1) IS ?3
      AND (?5=1 OR COALESCE((SELECT blocked_version FROM kgs_active WHERE law=?1), '') IS NOT ?2)
      AND (?2 IS NULL OR EXISTS (
        SELECT 1 FROM kgs_versions v
        WHERE v.law=?1 AND v.version=?2 AND v.effective_date <= ?4
          AND (SELECT COUNT(*) FROM kgs_docs d WHERE d.law=v.law AND d.version=v.version) = v.expected
          AND (?5=1 OR v.effective_date >= COALESCE(
            (SELECT effective_date FROM kgs_versions WHERE law=?1 AND version=?3), ''))
      ))
    ON CONFLICT(law) DO UPDATE SET version=excluded.version, blocked_version=excluded.blocked_version,
      updated_at=CURRENT_TIMESTAMP
    RETURNING version
  `).bind(law, version, expected, koreanDate(), rollback ? 1 : 0).first();
  if (r) return json({ version: r.version });
  const current = await db.prepare('SELECT version, blocked_version FROM kgs_active WHERE law=?').bind(law).first();
  if (current?.version === version && (!rollback || current.blocked_version === expected)) return json({ version });
  return json({ error: '조각 누락, 시행일 미도래, 보류 중인 버전 또는 현재 버전 불일치' }, 409);
}

export async function handleKgsUpdates(req, env, tokenize) {
  try {
    if (req.method === 'GET') {
      const state = await readKgsState(env.DB);
      return json({ active: state.filter(r => r.version).map(({ law, version, effective_date, updated_at }) => (
        { code: law.slice(4), version, effective_date, updated_at }
      )) });
    }
    if (req.method !== 'POST') return json({ error: '허용되지 않은 요청' }, 405);
    if (!await authorized(req, env.KGS_PUSH_KEY)) return json({ error: '관리 키가 필요합니다' }, 401);
    let b;
    try { b = await readBody(req); } catch { return json({ error: '잘못된 요청 본문' }, 400); }
    if (typeof b?.code !== 'string' || !CODE.test(b.code)) return json({ error: '코드 형식 오류' }, 400);
    const law = 'KGS ' + b.code;
    if (b.action === 'state') return json({ state: await readKgsState(env.DB) });
    if (b.action === 'stage') return await stage(env.DB, law, b, tokenize);
    if (b.action === 'activate' || b.action === 'rollback') return await activate(env.DB, law, b, b.action === 'rollback');
    return json({ error: '알 수 없는 작업' }, 400);
  } catch (error) {
    console.error('KGS 갱신 DB 오류', error.message);
    return json({ error: 'KGS 갱신 DB 오류' }, 503);
  }
}

export function kgsTableCurrent(table, state = []) {
  const active = state.find(row => row.law === table.law && row.version);
  return !active || table.version_sha256 === active.version;
}
