// 답 아래에 점검표·안전관리규정 초안·저장능력 계산기·제출 꾸러미 버튼을 붙일지 정한다.
// 파이썬 annex_checklist.suggest · safety_rules.suggest · package.suggest 와 같은 규칙(정규식도 같다).
// 버튼을 누르면 /checklist · /rules · /package 화면이 열리고, 그 화면은 브라우저(cf-tools.js)가 만든다.
import T from './tools_data.json';

// ── 자체점검표 (annex_checklist.suggest) ──
const WANT = /점검|체크|완성검사|중간검사|정기검사|시설\s*기준|설치\s*기준|기준|준비|안전\s*거리|이격|떨어|거리|방호벽|설치|지어|짓|세우/;
const CHECK = [
  ['h2_annex5_use', /연료\s*전지|수소\s*연료\s*사용\s*시설|수소연료사용|입상관|가스\s*계량기/, []],
  ['gas_annex5_station', /충전소|충전\s*시설|충전\s*설비|디스펜서/,
    [[/제조식|수전해|추출|개질|온\s*사이트/, '제조식'], [/저장식|튜브\s*트레일러|오프\s*사이트/, '저장식']]],
  ['gas_annex8_storage', /저장소|저장\s*설비|저장\s*탱크|용기\s*보관|사용\s*신고|사용\s*시설|특정\s*고압가스/,
    [[/사용\s*신고|사용\s*시설|특정\s*고압가스|용기\s*보관|쓰는|사용하는/, '사용'], [/저장소|저장\s*탱크/, '저장']]],
];
const strip = s => s.replace(/^\[+|\]+$/g, '');

function checklists(q, past) {
  if (!WANT.test(q)) return [];
  const out = [];
  for (const [tid, facRe, kinds] of CHECK) {
    const here = facRe.test(q);
    if (!here && !facRe.test(past || '')) continue;
    const t = T.annex[tid];
    if (!t) continue;
    const text = here ? q : `${past} ${q}`;
    const hit = kinds.find(([rx]) => rx.test(text));
    const fac = hit ? hit[1] : null;
    const f0 = fac || t.facilities[0];
    out.push({id: tid, title: t.title, facility: fac || '', url: `/checklist?t=${tid}` + (fac ? `&f=${encodeURIComponent(fac)}` : ''),
      law: `${t.law} ${strip(t.annex)}`, rows: t.rows[f0]});
    if (here) break;
  }
  return out.slice(0, 2);
}

// ── 안전관리규정 초안 (safety_rules.suggest) ──
const ASK = /안전\s*관리\s*규정/;
const H2 = /수소법|수소경제|수소용품|연료\s*전지|수전해\s*설비\s*제조|제41조/;
function rules(q, past) {
  if (!ASK.test(q)) return [];
  const tid = H2.test(q) || (H2.test(past || '') && !/고압가스/.test(q)) ? 'h2_annex2' : 'gas_annex15';
  const t = T.rules[tid];
  if (!t) return [];
  const law = `${t.law} ${strip(t.annex)}`;
  return [{id: tid, title: `${t.title} 초안 만들기`, facility: '', url: `/rules?t=${tid}`, law,
    desc: `${law} 항목을 장·조로 세운 뼈대 · 사업장 정보 채움 · 한글(HWPX)로 받기`}];
}

// ── 저장능력 계산기·제출 꾸러미 (package.suggest) ──
const PKG = /꾸러미|서류.{0,8}(한꺼번에|한번에|한 번에|묶|모아)|제출\s*서류.{0,8}(준비|정리|챙기|목록)|첨부\s*서류.{0,8}(준비|챙기|목록|뭐)/;
const CAP = /저장\s*능력.{0,10}(계산|산정|구하|어떻게)|저장능력\s*산정/;
function pkg(q) {
  const out = [];
  if (CAP.test(q)) out.push({id: 'storage', title: '저장능력 계산기 (고압가스법 시행규칙 별표 1)', facility: '',
    url: '/checklist#calc', law: '고압가스 안전관리법 시행규칙 별표 1',
    desc: '압축가스 Q=(10P+1)V₁ — 압력·내용적을 넣으면 설비별·합계 계산, 점검표에 바로 넣기, 계산서(HWPX)'});
  if (PKG.test(q)) out.push({id: 'package', title: '제출 꾸러미 만들기', facility: '', url: '/package', law: '',
    desc: '신청서 + 자체점검표 + 안전관리규정 초안 + 저장능력 계산서를 zip 하나로, 첨부서류 체크리스트 표지 포함'});
  return out;
}

// app.py 와 같은 순서: 꾸러미·계산기 → 규정 초안 → 점검표
export function toolButtons(q, past = '') {
  try { return [...pkg(q), ...rules(q, past), ...checklists(q, past)]; }
  catch (e) { return []; }                     // 버튼이 깨져도 답변은 나가야 한다
}
