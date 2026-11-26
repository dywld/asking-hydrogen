// 수소문 WE-Meet 예선 발표자료 (10분, 20장). 흐름은 탄탄대로 발표(목차 01~05 + 06 성찰), 겉모습은 미리캔버스 판(맥 창 틀).
const pptxgen = require('pptxgenjs');
const React = require('react');
const RDS = require('react-dom/server');
const sharp = require('sharp');
const fa = require('react-icons/fa6');
const path = require('path');
const { applyTheme } = require(process.env.PPTX_SKILL + '/scripts/apply_theme.js');

const FONT = process.env.DECK_FONT || 'Noto Sans KR';
const THEME = {
  name: 'Sosomun', headFontFace: FONT, bodyFontFace: FONT,
  colors: { dk1: '191F28', lt1: 'FFFFFF', dk2: '4E5968', lt2: 'F2F4F6', accent1: '3182F6', accent2: '1B64DA',
    accent3: 'E8F3FF', accent4: 'F04452', accent5: '00A86B', accent6: '8B95A1', hlink: '3182F6', folHlink: '1B64DA' },
};
const HEX = { ink: '191F28', sub: '4E5968', mute: '8B95A1', line: 'E5E8EB', soft: 'F2F4F6', blue: '3182F6', deep: '1B64DA', sky: 'E8F3FF', red: 'F04452', green: '00A86B', gray: 'C9CED6', frame: '5B5E66' };

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';          // 13.333 x 7.5
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
pres.title = '수소문 WE-Meet 발표자료';
pres.author = '수소문 팀';
const C = pres.SchemeColor;
const IMG = f => path.join(__dirname, 'img', f);

async function icon(Comp, color = '#3182F6', size = 256) {
  const svg = RDS.renderToStaticMarkup(React.createElement(Comp, { color, size }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return 'image/png;base64,' + buf.toString('base64');
}

// ── 창 틀(미리캔버스 판의 맥 창) ──
const WIN = { x: 0.4, y: 0.32, w: 12.533, h: 6.86 };
function frameObjects() {
  return [
    { rect: { x: 0, y: 0, w: 13.333, h: 7.5, fill: { color: HEX.frame } } },
    { roundRect: { x: WIN.x, y: WIN.y, w: WIN.w, h: WIN.h, fill: { color: 'FFFFFF' }, rectRadius: 0.16 } },
    { roundRect: { x: WIN.x, y: WIN.y, w: WIN.w, h: 0.6, fill: { color: 'F1F2F4' }, rectRadius: 0.16 } },
    { rect: { x: WIN.x, y: WIN.y + 0.3, w: WIN.w, h: 0.22, fill: { color: 'F1F2F4' } } },
    { ellipse: { x: 0.66, y: 0.48, w: 0.15, h: 0.15, fill: { color: 'FF5F57' } } },
    { ellipse: { x: 0.89, y: 0.48, w: 0.15, h: 0.15, fill: { color: 'FEBC2E' } } },
    { ellipse: { x: 1.12, y: 0.48, w: 0.15, h: 0.15, fill: { color: '28C840' } } },
    { roundRect: { x: 4.87, y: 0.415, w: 3.6, h: 0.28, fill: { color: 'FFFFFF' }, rectRadius: 0.14 } },
    { text: { text: '수소문', options: { x: 4.87, y: 0.415, w: 3.6, h: 0.28, fontSize: 10, color: HEX.mute, align: 'center', valign: 'middle', margin: 0 } } },
  ];
}
// pptxgenjs 의 master objects 는 rect/text/image/line 만 받는다. 둥근 상자·원은 shape 이름으로 바꿔 넣는다.
function toMaster(objs) {
  return objs.map(o => {
    if (o.roundRect) return { rect: { ...o.roundRect, rectRadius: o.roundRect.rectRadius } , _shape: 'roundRect' };
    return o;
  });
}
pres.defineSlideMaster({
  title: 'FRAME', background: { color: HEX.frame },
  objects: [{ rect: { x: 0, y: 0, w: 13.333, h: 7.5, fill: { color: HEX.frame } } }],
  slideNumber: { x: 12.05, y: 6.78, w: 0.6, h: 0.3, fontSize: 10, color: HEX.mute, align: 'right' },
});

function drawFrame(s) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: WIN.x, y: WIN.y, w: WIN.w, h: WIN.h, fill: { color: 'FFFFFF' }, line: { type: 'none' }, rectRadius: 0.16,
    shadow: { type: 'outer', color: '000000', opacity: 0.28, blur: 18, offset: 4, angle: 90 }, objectName: 'window' });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: WIN.x, y: WIN.y, w: WIN.w, h: 0.6, fill: { color: 'F1F2F4' }, line: { type: 'none' }, rectRadius: 0.16, objectName: 'titlebar' });
  s.addShape(pres.shapes.RECTANGLE, { x: WIN.x, y: WIN.y + 0.32, w: WIN.w, h: 0.28, fill: { color: 'F1F2F4' }, line: { type: 'none' }, objectName: 'titlebar-base' });
  [['FF5F57', 0.66], ['FEBC2E', 0.89], ['28C840', 1.12]].forEach(([c, x], i) =>
    s.addShape(pres.shapes.OVAL, { x, y: 0.545, w: 0.15, h: 0.15, fill: { color: c }, line: { type: 'none' }, objectName: 'dot' + i }));
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.87, y: 0.48, w: 3.6, h: 0.28, fill: { color: 'FFFFFF' }, line: { type: 'none' }, rectRadius: 0.14, objectName: 'urlbar' });
  s.addText('수소문', { x: 4.87, y: 0.48, w: 3.6, h: 0.28, fontSize: 10, color: HEX.mute, align: 'center', valign: 'middle', margin: 0, isTextBox: true, objectName: 'urltext' });
}

// 섹션 표시(작은 알약) + 제목. 모든 본문 장에서 같은 자리.
function head(s, no, sec, title) {
  const w = 0.55 + sec.length * 0.17;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 1.0, y: 1.12, w, h: 0.34, fill: { color: HEX.sky }, line: { type: 'none' }, rectRadius: 0.17, objectName: 'sec-pill' });
  s.addText([{ text: no + '  ', options: { bold: true, color: C.accent1 } }, { text: sec, options: { color: C.accent2, bold: true } }],
    { x: 1.0, y: 1.12, w, h: 0.34, fontSize: 12, align: 'center', valign: 'middle', margin: 0, isTextBox: true, objectName: 'sec-label' });
  s.addText(title, { x: 1.0, y: 1.55, w: 11.3, h: 0.7, fontSize: 28, bold: true, color: C.text1, margin: 0, valign: 'middle', isTextBox: true, objectName: 'title' });
}
function card(s, x, y, w, h, fill = HEX.soft, name = 'card') {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { type: 'none' }, rectRadius: 0.14, objectName: name });
}
function shadowCard(s, x, y, w, h, name = 'card') {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: 'FFFFFF' }, line: { color: HEX.line, width: 0.75 }, rectRadius: 0.14,
    shadow: { type: 'outer', color: '1B2A44', opacity: 0.12, blur: 10, offset: 2, angle: 90 }, objectName: name });
}
function txt(s, text, o) { s.addText(text, { margin: 0, isTextBox: true, color: C.text1, ...o }); }
function iconDot(s, data, x, y, d, fill = HEX.sky, name = 'icon') {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: 'none' }, objectName: name + '-bg' });
  const p = d * 0.26;
  s.addImage({ data, x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, objectName: name });
}
function shot(s, file, x, y, w, h, name) {
  shadowCard(s, x - 0.06, y - 0.06, w + 0.12, h + 0.12, name + '-frame');
  s.addImage({ path: IMG(file), x, y, w, h, objectName: name, altText: name });
}
function arrow(s, x, y, w = 0.4, color = HEX.gray) {
  s.addShape(pres.shapes.RIGHT_ARROW, { x, y, w, h: 0.32, fill: { color }, line: { type: 'none' }, objectName: 'arrow' });
}
function source(s, t) { txt(s, t, { x: 1.0, y: 6.72, w: 10.5, h: 0.3, fontSize: 10, color: C.accent6 }); }

(async () => {
  const I = {};
  const B = '#3182F6', W = '#FFFFFF';
  const list = { scale: fa.FaScaleBalanced, search: fa.FaMagnifyingGlass, sign: fa.FaFileSignature, cube: fa.FaCube, check: fa.FaClipboardCheck,
    db: fa.FaDatabase, shield: fa.FaShieldHalved, rocket: fa.FaRocket, server: fa.FaServer, coins: fa.FaCoins, rotate: fa.FaArrowsRotate,
    building: fa.FaBuilding, user: fa.FaUserTie, landmark: fa.FaLandmark, bulb: fa.FaLightbulb, users: fa.FaUsers, robot: fa.FaRobot,
    warn: fa.FaTriangleExclamation, file: fa.FaFileLines, book: fa.FaBookOpen, chat: fa.FaComments, chart: fa.FaChartLine, code: fa.FaCode,
    hand: fa.FaHandshake, list: fa.FaListCheck, pen: fa.FaPenToSquare, layers: fa.FaLayerGroup, gauge: fa.FaGaugeHigh };
  for (const [k, Comp] of Object.entries(list)) { I[k] = await icon(Comp, B); I[k + 'W'] = await icon(Comp, W); }

  const sec = t => pres.addSection({ title: t });
  const slide = st => { const s = pres.addSlide({ masterName: 'FRAME', sectionTitle: st }); drawFrame(s); return s; };

  // 1 표지
  sec('표지');
  let s = slide('표지');
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.17, y: 1.2, w: 5.0, h: 0.38, fill: { color: HEX.sky }, line: { type: 'none' }, rectRadius: 0.19, objectName: 'event' });
  txt(s, '2026 WE-Meet 프로젝트 · 에너지신산업 혁신융합대학', { x: 4.17, y: 1.2, w: 5.0, h: 0.38, fontSize: 13, bold: true, color: C.accent2, align: 'center', valign: 'middle' });
  txt(s, '국내외 수소시설 도입 절차 분석과\nAI 기반 맞춤형 인허가 프로세스 구축', { x: 1.2, y: 1.8, w: 10.93, h: 1.6, fontSize: 38, bold: true, align: 'center', valign: 'middle', lineSpacingMultiple: 1.1, objectName: 'cover-title' });
  s.addImage({ path: IMG('mascot.png'), x: 5.67, y: 3.55, w: 2.0, h: 2.0, objectName: 'mascot' });
  txt(s, [{ text: 'AI 인허가 에이전트 ', options: { color: C.text2 } }, { text: '수소문', options: { color: C.accent1, bold: true } }],
    { x: 3.67, y: 5.55, w: 6.0, h: 0.42, fontSize: 18, align: 'center', valign: 'middle' });
  card(s, 1.0, 6.12, 11.33, 0.56, HEX.soft, 'team-bar');
  txt(s, '팀원: 최여진, 박민혁, 박승래, 박민혁     |     담당 교수: 김상현 교수     |     기업 멘토: 한국가스안전공사 유성현 차장',
    { x: 1.0, y: 6.12, w: 11.33, h: 0.56, fontSize: 13, color: C.text2, align: 'center', valign: 'middle' });
  s.addNotes('안녕하십니까. 수소시설 인허가 AI 에이전트 수소문 팀입니다. 수소충전소 같은 수소시설을 지으려는 사업자가 복잡한 인허가를 혼자 헤매지 않도록, 법령 근거로 답하고 신청서까지 채워 주는 AI를 만들었습니다.');

  // 2 목차
  sec('목차');
  s = slide('목차');
  txt(s, 'INDEX', { x: 1.0, y: 1.35, w: 3, h: 0.35, fontSize: 14, bold: true, color: C.accent1, charSpacing: 2 });
  txt(s, '목차', { x: 1.0, y: 1.72, w: 3, h: 0.8, fontSize: 40, bold: true });
  s.addImage({ path: IMG('mascot.png'), x: 1.15, y: 3.6, w: 2.5, h: 2.5, objectName: 'mascot' });
  const TOC = [['01', '아이디어 소개', '왜 수소문이 필요한가'], ['02', '이론적 배경', '인허가 절차와 RAG'], ['03', '개발 과정 및 결과', '4단계 개발과 30문항 평가'],
    ['04', '실현 가능성 및 기대효과', '운영 현황과 효과'], ['05', '결론 및 제언', '정리와 발전 방안'], ['06', '성찰 및 배운 점', '실패와 개선, 직무 역량']];
  TOC.forEach(([n, t, d], i) => {
    const y = 1.3 + i * 0.86;
    card(s, 4.6, y, 7.7, 0.68, i === 5 ? HEX.sky : HEX.soft, 'toc' + n);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.75, y: y + 0.13, w: 0.78, h: 0.42, fill: { color: HEX.blue }, line: { type: 'none' }, rectRadius: 0.1, objectName: 'toc-no' + n });
    txt(s, n, { x: 4.75, y: y + 0.13, w: 0.78, h: 0.42, fontSize: 16, bold: true, color: C.background1, align: 'center', valign: 'middle' });
    txt(s, t, { x: 5.8, y, w: 3.6, h: 0.68, fontSize: 18, bold: true, valign: 'middle' });
    txt(s, d, { x: 9.2, y, w: 2.95, h: 0.68, fontSize: 13, color: C.accent6, align: 'right', valign: 'middle' });
  });
  s.addNotes('발표는 아이디어 소개, 이론적 배경, 개발 과정과 결과, 실현 가능성과 기대효과, 결론, 그리고 프로젝트를 하며 배운 점 순서로 말씀드리겠습니다.');

  // 3 규정 다섯 겹
  sec('01 아이디어 소개');
  s = slide('01 아이디어 소개');
  head(s, '01', '아이디어 소개', '수소충전소 하나에 읽어야 할 규정이 다섯 겹입니다');
  const LAY = [['법률', '고압가스 안전관리법\n수소법'], ['시행령', '허가 대상·종류'], ['시행규칙', '절차·서식·수수료'], ['별표', '시설·기술·검사 기준'], ['KGS Code', '상세기준\n(항목 번호 단위)']];
  LAY.forEach(([t, d], i) => {
    const x = 1.0 + i * 2.33;
    shadowCard(s, x, 2.55, 1.95, 1.75, 'layer' + i);
    txt(s, String(i + 1), { x: x + 0.18, y: 2.68, w: 0.4, h: 0.3, fontSize: 12, bold: true, color: C.accent1 });
    txt(s, t, { x, y: 3.0, w: 1.95, h: 0.5, fontSize: 19, bold: true, align: 'center', valign: 'middle', color: i === 4 ? C.accent1 : C.text1 });
    txt(s, d, { x: x + 0.1, y: 3.5, w: 1.75, h: 0.7, fontSize: 12, color: C.text2, align: 'center', valign: 'top' });
    if (i < 4) arrow(s, x + 1.98, 3.26, 0.32);
  });
  card(s, 1.0, 4.65, 11.33, 1.85, HEX.sky, 'stats-bg');
  txt(s, '산업부가 정한 기준만 세어도', { x: 1.35, y: 4.8, w: 5, h: 0.35, fontSize: 14, bold: true, color: C.accent2 });
  [['229', '조문', '시행규칙 본문'], ['2,667', '항목', '시행규칙 별표'], ['1,574', '항목', '고시']].forEach(([n, u, l], i) => {
    const x = 1.35 + i * 3.75;
    txt(s, [{ text: n, options: { fontSize: 40, bold: true, color: C.accent1 } }, { text: ' ' + u, options: { fontSize: 18, bold: true, color: C.accent2 } }],
      { x, y: 5.15, w: 3.5, h: 0.75, valign: 'bottom' });
    txt(s, l, { x, y: 5.92, w: 3.5, h: 0.35, fontSize: 14, color: C.text2 });
  });
  source(s, '출처: 한국가스안전공사 멘토링 자료(상세기준 KGS Code 체계)');
  s.addNotes('수소충전소 하나를 지으려면 법률, 시행령, 시행규칙을 읽고, 시행규칙이 별표를 가리키면 별표를, 별표가 다시 KGS Code를 가리키면 코드까지 찾아야 합니다. 멘토링 자료로 세어 보니 시행규칙 본문 229조문, 별표 2,667항목, 고시 1,574항목입니다. 사업자가 혼자 따라가기에는 너무 깊습니다.');

  // 4 사업자가 묻는 것
  s = slide('01 아이디어 소개');
  head(s, '01', '아이디어 소개', '사업자가 실제로 막히는 곳: 검사, 거리, 허가 대상');
  shadowCard(s, 1.0, 2.5, 7.0, 4.05, 'chart-card');
  txt(s, '실무 질의 117건 주제 분포', { x: 1.3, y: 2.65, w: 6, h: 0.4, fontSize: 15, bold: true });
  const QS = [['검사', 28], ['거리·배치·설치장소', 21], ['용기·운송·저장', 20], ['허가·신고 대상 여부', 16], ['안전관리자·교육', 13], ['수소용품·인증', 7]];
  s.addChart(pres.charts.BAR, [{ name: '건수', labels: QS.map(q => q[0]).reverse(), values: QS.map(q => q[1]).reverse() }], {
    x: 1.2, y: 3.05, w: 6.6, h: 3.4, barDir: 'bar', chartColors: ['3182F6'], barGapWidthPct: 55,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 12, dataLabelColor: '4E5968', dataLabelFontFace: '+mn-lt',
    catAxisLabelFontSize: 12, catAxisLabelColor: '191F28', catAxisLabelFontFace: '+mn-lt', valAxisHidden: true, valGridLine: { style: 'none' },
    catGridLine: { style: 'none' }, catAxisLineShow: false, showLegend: false, showTitle: false, objectName: 'topic-chart' });
  shadowCard(s, 8.35, 2.5, 3.98, 1.95, 'stat-a');
  txt(s, [{ text: '40', options: { fontSize: 44, bold: true, color: C.accent1 } }, { text: ' / 127건', options: { fontSize: 18, bold: true, color: C.text2 } }], { x: 8.65, y: 2.65, w: 3.5, h: 0.9, valign: 'bottom' });
  txt(s, '규제 애로 127건 중\n수소충전소 관련이 가장 많음', { x: 8.65, y: 3.55, w: 3.5, h: 0.75, fontSize: 14, color: C.text2 });
  shadowCard(s, 8.35, 4.6, 3.98, 1.95, 'stat-b');
  iconDot(s, I.warn, 8.6, 4.85, 0.62, 'FDECEE', 'warn');
  txt(s, '같은 정보를 서류마다\n다시 쓰고, 근거 조문은\n직접 찾아야 함', { x: 9.4, y: 4.86, w: 2.8, h: 1.4, fontSize: 14, color: C.text1, valign: 'top' });
  source(s, '출처: 가스신문 Q&A(가스안전공사 사이버지사 답변) 117건, 수소경제 종합정보포털 규제개선 현황 127건 (2026-09-23 수집)');
  s.addNotes('사업자가 실제로 무엇에서 막히는지 공개 자료를 모아 보았습니다. 가스안전공사 실무 질의 117건을 보면 검사, 안전거리, 허가 대상 여부 질문이 가장 많고, 규제 애로 127건 중 40건이 수소충전소였습니다. 답이 법령 깊숙이 있어서 찾기 어려운 질문들입니다.');

  // 5 아이디어
  s = slide('01 아이디어 소개');
  head(s, '01', '아이디어 소개', '수소문: 묻고, 확인하고, 채워 주는 AI 인허가 에이전트');
  card(s, 1.0, 2.5, 3.6, 4.05, HEX.sky, 'mascot-bg');
  s.addImage({ path: IMG('mascot.png'), x: 1.35, y: 2.75, w: 2.9, h: 2.9, objectName: 'mascot' });
  txt(s, '수소 + 수소문(搜所聞)\n널리 찾아 알려 준다', { x: 1.0, y: 5.65, w: 3.6, h: 0.75, fontSize: 13, color: C.accent2, bold: true, align: 'center' });
  const IDEA = [[I.chat, '근거로 답하는 상담', '질문하면 법령 조문과 KGS Code\n항목 번호를 붙여 답합니다'], [I.sign, '신청서 16종 자동 채움', '사업장 정보를 한 번만 넣으면\n공식 서식이 차례로 채워집니다'],
    [I.cube, '3D 부지 검토', '주소만 넣으면 주변 보호시설과\n안전거리를 3D로 판정합니다'], [I.check, '제출 전 점검', '빈칸·누락 서류·형식 오류를\n제출 전에 걸러 냅니다']];
  IDEA.forEach(([ic, t, d], i) => {
    const x = 4.95 + (i % 2) * 3.73, y = 2.5 + Math.floor(i / 2) * 2.1;
    shadowCard(s, x, y, 3.5, 1.9, 'idea' + i);
    iconDot(s, ic, x + 0.25, y + 0.25, 0.62, HEX.sky, 'idea-icon' + i);
    txt(s, t, { x: x + 1.0, y: y + 0.25, w: 2.4, h: 0.62, fontSize: 16, bold: true, valign: 'middle' });
    txt(s, d, { x: x + 0.25, y: y + 1.0, w: 3.15, h: 0.8, fontSize: 13, color: C.text2 });
  });
  s.addNotes('그래서 만든 것이 수소문입니다. 질문하면 근거 조문과 함께 답하고, 사업장 정보로 신청서 16종을 자동으로 채우고, 주소만 넣으면 안전거리를 3D로 검토하고, 제출 전 빠진 것을 점검합니다. 상담부터 제출 준비까지 한 흐름입니다.');

  // 6 인허가 절차
  sec('02 이론적 배경');
  s = slide('02 이론적 배경');
  head(s, '02', '이론적 배경', '고압가스 시설 인허가: 기관 세 곳, 단계 네 번');
  const STEPS = [['기술검토', '안전성향상 계획서', '한국가스안전공사'], ['사업허가', '허가·등록·신고', '시·군·구청장'], ['완성검사', '결과 통보·필증 발급', '한국가스안전공사'], ['운영 준비', '안전관리규정 제출\n안전관리자 선임신고', '허가관청']];
  STEPS.forEach(([t, d, org], i) => {
    const x = 1.0 + i * 2.95;
    shadowCard(s, x, 2.55, 2.55, 2.2, 'step' + i);
    txt(s, 'STEP ' + (i + 1), { x: x + 0.25, y: 2.72, w: 2, h: 0.3, fontSize: 12, bold: true, color: C.accent1 });
    txt(s, t, { x: x + 0.25, y: 3.02, w: 2.1, h: 0.5, fontSize: 21, bold: true });
    txt(s, d, { x: x + 0.25, y: 3.55, w: 2.15, h: 0.7, fontSize: 13, color: C.text2 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.25, y: 4.28, w: 2.05, h: 0.32, fill: { color: i === 1 || i === 3 ? HEX.soft : HEX.sky }, line: { type: 'none' }, rectRadius: 0.16, objectName: 'org' + i });
    txt(s, org, { x: x + 0.25, y: 4.28, w: 2.05, h: 0.32, fontSize: 12, bold: true, color: i === 1 || i === 3 ? C.text2 : C.accent2, align: 'center', valign: 'middle' });
    if (i < 3) arrow(s, x + 2.6, 3.5, 0.3);
  });
  card(s, 1.0, 5.05, 5.5, 1.5, HEX.soft, 'perf');
  txt(s, '성능기준 → 시행규칙 별표', { x: 1.3, y: 5.2, w: 5, h: 0.4, fontSize: 16, bold: true });
  txt(s, '안전에 필요한 최소 기준. 기술이 바뀌어도 유지', { x: 1.3, y: 5.65, w: 5, h: 0.7, fontSize: 13, color: C.text2 });
  card(s, 6.83, 5.05, 5.5, 1.5, HEX.sky, 'detail');
  txt(s, '상세기준 → KGS Code', { x: 7.13, y: 5.2, w: 5, h: 0.4, fontSize: 16, bold: true, color: C.accent2 });
  txt(s, '성능기준을 만족하는 구체적 방법. 수시로 개정', { x: 7.13, y: 5.65, w: 5, h: 0.7, fontSize: 13, color: C.text2 });
  source(s, '출처: 한국가스안전공사 멘토링 자료(시설별 허가·신고·등록 절차, 상세기준 KGS Code)');
  s.addNotes('멘토링으로 배운 실제 절차입니다. 가스안전공사 기술검토, 시군구 허가, 공사 완성검사, 허가관청 신고까지 기관 세 곳을 네 번 오갑니다. 기준도 둘로 나뉘어 최소 기준은 시행규칙 별표에, 구체적 방법은 KGS Code에 있습니다. 그래서 AI가 별표와 코드 항목 번호까지 정확히 짚어야 쓸모가 있습니다.');

  // 7 RAG
  s = slide('02 이론적 배경');
  head(s, '02', '이론적 배경', 'RAG(검색 증강 생성): AI가 외우지 않고 찾아 읽고 답합니다');
  const FLOW = [[I.chat, '질문', '학교 근처에\n지을 수 있나요?'], [I.search, '검색', '법령·KGS Code\n32,229조각'], [I.list, '근거 선별', '맞는 조각만\n골라 전달'], [I.robot, '생성', '"이 근거만 읽고\n답하라"'], [I.check, '답 + 근거 번호', '문장마다\n출처 표시']];
  FLOW.forEach(([ic, t, d], i) => {
    const x = 1.0 + i * 2.33;
    shadowCard(s, x, 2.55, 1.95, 2.25, 'flow' + i);
    iconDot(s, i === 1 ? I.searchW : ic, x + 0.62, 2.75, 0.7, i === 1 ? HEX.blue : HEX.sky, 'flow-icon' + i);
    txt(s, t, { x, y: 3.55, w: 1.95, h: 0.42, fontSize: 16, bold: true, align: 'center' });
    txt(s, d, { x: x + 0.1, y: 4.0, w: 1.75, h: 0.7, fontSize: 12, color: C.text2, align: 'center' });
    if (i < 4) arrow(s, x + 1.98, 3.5, 0.32);
  });
  [[I.rotate, '법이 바뀌면 자료만 교체', 'AI 재학습 없이 바로 새 기준으로 답합니다'], [I.book, '모든 문장에 근거 번호', '누르면 법령 원문을 바로 확인할 수 있습니다']].forEach(([ic, t, d], i) => {
    const x = 1.0 + i * 5.83;
    card(s, x, 5.1, 5.5, 1.45, HEX.soft, 'benefit' + i);
    iconDot(s, ic, x + 0.25, 5.42, 0.8, 'FFFFFF', 'benefit-icon' + i);
    txt(s, t, { x: x + 1.25, y: 5.28, w: 4.1, h: 0.45, fontSize: 16, bold: true });
    txt(s, d, { x: x + 1.25, y: 5.75, w: 4.1, h: 0.65, fontSize: 13, color: C.text2 });
  });
  s.addNotes('핵심 이론은 검색 증강 생성, RAG입니다. 일반 AI는 학습한 기억으로 답하지만, 수소문은 질문이 오면 먼저 법령 자료 3만 2천 조각에서 맞는 근거를 찾고, AI에게 이 근거만 읽고 답하라고 시킵니다. 그래서 법이 바뀌면 자료만 바꾸면 되고, 모든 문장에 근거 번호를 붙일 수 있습니다.');

  // 8 환각
  s = slide('02 이론적 배경');
  head(s, '02', '이론적 배경', '환각: 없는 조문을 자신 있게 말하는 문제를 막습니다');
  card(s, 1.0, 2.5, 4.9, 4.05, 'FDF1F2', 'bad');
  iconDot(s, I.warn, 1.3, 2.75, 0.62, 'FFFFFF', 'bad-icon');
  txt(s, '범용 AI의 답', { x: 2.1, y: 2.75, w: 3.5, h: 0.62, fontSize: 16, bold: true, color: C.accent4, valign: 'middle' });
  card(s, 1.3, 3.6, 4.3, 1.35, 'FFFFFF', 'bad-quote');
  txt(s, '"그 기준은 시행규칙 별표 9에\n규정되어 있습니다."', { x: 1.5, y: 3.6, w: 3.95, h: 1.35, fontSize: 15, bold: true, valign: 'middle' });
  txt(s, '그럴듯하지만 틀린 번호. 인허가에서는\n틀린 숫자 하나가 곧 반려로 이어집니다.', { x: 1.3, y: 5.15, w: 4.4, h: 1.0, fontSize: 13, color: C.text2 });
  const GUARD = [['1', '문장마다 근거 번호 필수', '번호 없는 문장은 화면에 따로 표시'], ['2', '숫자·조문·기관명 자동 대조', '답의 숫자를 프로그램이 원문과 한 글자씩 비교'], ['3', '어긋나면 다시 쓰기', '그래도 틀리면 내보내지 않고 경고']];
  GUARD.forEach(([n, t, d], i) => {
    const y = 2.5 + i * 1.38;
    shadowCard(s, 6.25, y, 6.08, 1.2, 'guard' + i);
    s.addShape(pres.shapes.OVAL, { x: 6.5, y: y + 0.3, w: 0.6, h: 0.6, fill: { color: HEX.blue }, line: { type: 'none' }, objectName: 'guard-no' + i });
    txt(s, n, { x: 6.5, y: y + 0.3, w: 0.6, h: 0.6, fontSize: 18, bold: true, color: C.background1, align: 'center', valign: 'middle' });
    txt(s, t, { x: 7.35, y: y + 0.17, w: 4.8, h: 0.45, fontSize: 16, bold: true });
    txt(s, d, { x: 7.35, y: y + 0.62, w: 4.8, h: 0.42, fontSize: 13, color: C.text2 });
  });
  s.addNotes('AI가 없는 조문을 자신 있게 말하는 것을 환각이라고 합니다. 인허가에서는 틀린 숫자 하나가 반려로 이어지기 때문에, 수소문은 답을 내보내기 전에 세 번 검사합니다. 문장마다 근거 번호를 요구하고, 숫자와 조문 번호를 프로그램이 원문과 대조하고, 어긋나면 다시 쓰게 합니다. 틀린 것을 표시하는 데서 그치지 않고 아예 내보내지 않는 것이 목표입니다.');

  // 9 개발 4단계
  sec('03 개발 과정 및 결과');
  s = slide('03 개발 과정 및 결과');
  head(s, '03', '개발 과정 및 결과', '개발은 4단계로 진행했습니다');
  const DEV = [[I.db, '자료 구축', '법령·별표·KGS Code를\n항목 번호 단위로 쪼개기'], [I.search, '검색 설계', 'BM25 검색 +\n인허가 용어 사전'], [I.shield, '답변 검증', '근거 번호·숫자 대조\n111문항 자동 채점'], [I.rocket, '서비스화', '신청서 자동 채움·3D 검토\n웹 + 윈도우 앱 배포']];
  DEV.forEach(([ic, t, d], i) => {
    const x = 1.0 + i * 2.95;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.55, w: 2.55, h: 0.45, fill: { color: i === 3 ? HEX.blue : HEX.ink }, line: { type: 'none' }, rectRadius: 0.1, objectName: 'dev-tag' + i });
    txt(s, 'STEP ' + (i + 1), { x, y: 2.55, w: 2.55, h: 0.45, fontSize: 14, bold: true, color: C.background1, align: 'center', valign: 'middle' });
    shadowCard(s, x, 3.15, 2.55, 3.3, 'dev' + i);
    iconDot(s, ic, x + 0.73, 3.45, 1.1, HEX.sky, 'dev-icon' + i);
    txt(s, t, { x, y: 4.75, w: 2.55, h: 0.5, fontSize: 19, bold: true, align: 'center' });
    txt(s, d, { x: x + 0.15, y: 5.3, w: 2.25, h: 0.95, fontSize: 13, color: C.text2, align: 'center' });
    if (i < 3) s.addText('»', { x: x + 2.58, y: 4.4, w: 0.35, h: 0.5, fontSize: 26, bold: true, color: C.accent6, align: 'center', valign: 'middle', margin: 0, isTextBox: true });
  });
  s.addNotes('개발은 네 단계였습니다. 자료를 항목 번호 단위로 쪼개 쌓고, 맞는 근거를 찾는 검색을 설계하고, 답을 검증하는 장치와 자동 채점을 만들고, 마지막으로 신청서 채우기와 3D 검토를 붙여 웹과 윈도우 앱으로 배포했습니다.');

  // 10 자료와 검색
  s = slide('03 개발 과정 및 결과');
  head(s, '03', '개발 과정 및 결과', '자료와 검색: 3만 2천 조각에서 맞는 근거를 찾습니다');
  [['466', '건', '시행규칙 별표'], ['188', '종', 'KGS Code'], ['55', '건', '검증된 핵심 수치표']].forEach(([n, u, l], i) => {
    const x = 1.0 + i * 2.55;
    shadowCard(s, x, 2.55, 2.25, 1.75, 'src' + i);
    txt(s, [{ text: n, options: { fontSize: 34, bold: true, color: C.text1 } }, { text: ' ' + u, options: { fontSize: 16, bold: true, color: C.text2 } }], { x: x + 0.25, y: 2.7, w: 1.9, h: 0.85, valign: 'bottom' });
    txt(s, l, { x: x + 0.25, y: 3.6, w: 1.9, h: 0.5, fontSize: 13, color: C.text2 });
  });
  arrow(s, 8.72, 3.27, 0.45, HEX.blue);
  card(s, 9.35, 2.55, 2.98, 1.75, HEX.blue, 'total');
  txt(s, [{ text: '32,229', options: { fontSize: 36, bold: true, color: C.background1 } }], { x: 9.35, y: 2.7, w: 2.98, h: 0.85, align: 'center', valign: 'bottom' });
  txt(s, '검색용 조각', { x: 9.35, y: 3.6, w: 2.98, h: 0.45, fontSize: 14, bold: true, color: C.background1, align: 'center' });
  [[I.search, 'BM25 검색 + 인허가 용어 사전', '드문 핵심 단어에 가중치, 사업자 말은 법령 용어로 바꿔 찾음\n예: "충전소를 짓고 싶다" → 고압가스 제조허가'], [I.gauge, '회귀 평가 111문항', '코드를 고칠 때마다 111문항 자동 채점\n현재 111/111, 95% 미만이면 반영 자체를 막음']].forEach(([ic, t, d], i) => {
    const x = 1.0 + i * 5.83;
    card(s, x, 4.6, 5.5, 1.95, HEX.soft, 'search' + i);
    iconDot(s, ic, x + 0.25, 4.82, 0.7, 'FFFFFF', 'search-icon' + i);
    txt(s, t, { x: x + 1.15, y: 4.82, w: 4.2, h: 0.7, fontSize: 16, bold: true, valign: 'middle' });
    txt(s, d, { x: x + 0.3, y: 5.6, w: 5.0, h: 0.85, fontSize: 12.5, color: C.text2 });
  });
  s.addNotes('처음에는 별표가 하나도 없어 "별표 8에 규정되어 있다"는 답만 나왔습니다. 그래서 별표 466건과 KGS Code 188종을 모으고, 틀리면 안 되는 수치 55건은 원문과 대조한 표로 만들어, 모두 3만 2천여 조각으로 쪼갰습니다. 검색은 드문 핵심 단어에 가중치를 주는 BM25에 인허가 용어 사전을 더했고, 111문항 자동 채점으로 품질을 지킵니다.');

  // 11 결과 1
  s = slide('03 개발 과정 및 결과');
  head(s, '03', '개발 과정 및 결과', '결과 ①: 팀 30문항 97점, 최신 범용 AI의 2배');
  shadowCard(s, 1.0, 2.5, 7.6, 4.05, 'score-card');
  const MODELS = ['수소문 (우리)', 'Claude Opus 5.5', 'Gemini 4 Hydrogen', 'GPT-6 luna'];
  s.addChart(pres.charts.BAR, [{ name: '총점', labels: MODELS.slice().reverse(), values: [97, 48, 47, 42].reverse() }], {
    x: 1.25, y: 2.7, w: 7.15, h: 3.7, barDir: 'bar', chartColors: ['C9CED6', 'C9CED6', 'C9CED6', '3182F6'], barGapWidthPct: 45,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 16, dataLabelFontBold: true, dataLabelColor: '191F28', dataLabelFontFace: '+mn-lt',
    catAxisLabelFontSize: 14, catAxisLabelColor: '191F28', catAxisLabelFontFace: '+mn-lt', valAxisHidden: true, valAxisMaxVal: 112, valAxisMinVal: 0,
    valGridLine: { style: 'none' }, catGridLine: { style: 'none' }, catAxisLineShow: false, showLegend: false, showTitle: false, objectName: 'score-chart' });
  card(s, 8.95, 2.5, 3.38, 4.05, HEX.sky, 'score-call');
  txt(s, '100점 만점', { x: 9.25, y: 2.75, w: 2.8, h: 0.4, fontSize: 14, bold: true, color: C.accent2 });
  txt(s, [{ text: '97', options: { fontSize: 72, bold: true, color: C.accent1 } }, { text: '점', options: { fontSize: 24, bold: true, color: C.accent2 } }], { x: 9.25, y: 3.15, w: 2.8, h: 1.4, valign: 'bottom' });
  txt(s, '같은 질문을 범용 AI 3종에\n그대로 묻고, 법령 원문과\n대조해 채점했습니다', { x: 9.25, y: 4.75, w: 2.9, h: 1.4, fontSize: 13.5, color: C.text2 });
  source(s, '팀 30문항, 문항당 0~3점(90점)을 100점 만점으로 환산, 법령 원문 대조 채점 · 범용 AI는 검색 없이 질문만 · Gemini 4 Hydrogen 은 생각 단계 Low · 2026-11-24');
  s.addNotes('결과입니다. 팀이 만든 실무 30문항을 최신 범용 AI 세 종류에도 똑같이 묻고, 법령 원문과 대조해 문항당 3점으로 채점해 100점 만점으로 환산했습니다. 수소문은 97점, 범용 AI는 48점 이하였습니다.');

  // 12 결과 2
  s = slide('03 개발 과정 및 결과');
  head(s, '03', '개발 과정 및 결과', '결과 ②: 틀린 내용을 단정한 답 0건');
  shadowCard(s, 1.0, 2.5, 5.6, 4.05, 'hal-card');
  txt(s, '없는 조문·틀린 금액을 확신하며 답한 수 (30문항 중)', { x: 1.3, y: 2.65, w: 5.1, h: 0.4, fontSize: 13, bold: true, color: C.text2 });
  s.addChart(pres.charts.BAR, [{ name: '환각', labels: ['수소문', 'Opus 5.5', 'Gemini 4', 'GPT-6 luna'], values: [0, 1, 3, 10] }], {
    x: 1.2, y: 3.1, w: 5.2, h: 3.35, barDir: 'col', chartColors: ['3182F6', 'C9CED6', 'C9CED6', 'C9CED6'], barGapWidthPct: 60,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontSize: 16, dataLabelFontBold: true, dataLabelColor: '191F28', dataLabelFontFace: '+mn-lt',
    catAxisLabelFontSize: 13, catAxisLabelColor: '191F28', catAxisLabelFontFace: '+mn-lt', valAxisHidden: true, valAxisMaxVal: 12, valAxisMinVal: 0,
    valGridLine: { style: 'none' }, catGridLine: { style: 'none' }, showLegend: false, showTitle: false, objectName: 'hal-chart' });
  shadowCard(s, 6.9, 2.5, 5.43, 4.05, 'cat-card');
  txt(s, '질문 유형별 득점률 (%)', { x: 7.2, y: 2.65, w: 4.9, h: 0.4, fontSize: 13, bold: true, color: C.text2 });
  const CAT = [['수수료', 100, 0], ['벌칙', 100, 33], ['절차', 100, 67], ['시설기준', 93, 53]];
  const hdr = [{ text: '유형', options: { bold: true, color: '8B95A1' } }, { text: '수소문', options: { bold: true, color: '3182F6', align: 'center' } }, { text: '범용 AI 최고', options: { bold: true, color: '8B95A1', align: 'center' } }];
  const rows = [hdr].concat(CAT.map(([c, a, b]) => [{ text: c, options: { bold: true } }, { text: String(a), options: { bold: true, color: '3182F6', align: 'center' } }, { text: String(b), options: { color: '4E5968', align: 'center' } }]));
  s.addTable(rows, { x: 7.2, y: 3.15, w: 4.85, colW: [1.85, 1.4, 1.6], rowH: 0.5, fontSize: 15, color: '191F28', fontFace: FONT,
    border: { type: 'solid', pt: 0.75, color: 'E5E8EB' }, valign: 'middle', objectName: 'cat-table' });
  txt(s, '수수료는 범용 AI 3종 모두 0%\n고시 금액을 모르면 지어냅니다', { x: 7.2, y: 5.85, w: 4.95, h: 0.6, fontSize: 12.5, color: C.accent4, bold: true });
  source(s, '범용 AI 최고 = Opus 5.5·Gemini 4 Hydrogen·GPT-6 luna 중 유형별 최고 득점률 · 2026-11-24 채점');
  s.addNotes('더 중요한 것은 틀린 내용을 확신하며 말한 답입니다. GPT-6 luna는 10건, 수소문은 0건이었습니다. 특히 수수료 문제는 범용 AI 세 종류 모두 0점이었는데, 고시 금액을 모르면 그럴듯한 숫자를 지어내기 때문입니다.');

  // 13 서비스 1
  s = slide('03 개발 과정 및 결과');
  head(s, '03', '개발 과정 및 결과', '서비스 ①: 내 사업장 기준으로, 근거와 함께 답합니다');
  shot(s, 'answer.png', 1.0, 2.5, 6.53, 4.08, 'shot-answer');
  [[I.book, '근거 번호를 누르면 원문', 'KGS FP216 2.1.1.1처럼 항목 번호까지 표시'], [I.building, '내 사업장 기준', '서울 강동구 수소충전소 기준으로 답을 맞춤'], [I.layers, '표로 정리', '처리능력별 보호시설 이격거리를 한눈에']].forEach(([ic, t, d], i) => {
    const y = 2.5 + i * 1.4;
    shadowCard(s, 7.95, y, 4.38, 1.22, 'feat' + i);
    iconDot(s, ic, 8.17, y + 0.27, 0.68, HEX.sky, 'feat-icon' + i);
    txt(s, t, { x: 9.05, y: y + 0.18, w: 3.15, h: 0.42, fontSize: 15, bold: true });
    txt(s, d, { x: 9.05, y: y + 0.6, w: 3.15, h: 0.5, fontSize: 12, color: C.text2 });
  });
  s.addNotes('실제 화면입니다. 이격거리를 물으면 처리능력별 표로 정리하고, 숫자마다 KGS Code 항목 번호가 붙어 누르면 원문으로 갑니다. 처음 설정한 사업장, 여기서는 서울 강동구 수소충전소 기준으로 답을 맞춥니다.');

  // 14 서비스 2
  s = slide('03 개발 과정 및 결과');
  head(s, '03', '개발 과정 및 결과', '서비스 ②: 신청서는 자동으로, 부지는 3D로 검토합니다');
  shot(s, 'form.png', 1.0, 2.55, 5.12, 3.2, 'shot-form');
  shot(s, 'site3d.png', 6.64, 2.55, 5.69, 3.2, 'shot-3d');
  txt(s, [{ text: '신청서 16종 자동 채움  ', options: { bold: true, color: C.text1 } }, { text: '직접 넣을 칸만 남김', options: { color: C.text2 } }], { x: 1.0, y: 5.98, w: 5.12, h: 0.45, fontSize: 13 });
  txt(s, [{ text: '3D 부지 검토  ', options: { bold: true, color: C.text1 } }, { text: '거리 계산은 코드, 배치도 읽기는 AI', options: { color: C.text2 } }], { x: 6.64, y: 5.98, w: 5.69, h: 0.45, fontSize: 13 });
  s.addNotes('답에서 끝나지 않고 신청까지 이어집니다. 사업장 정보를 한 번 넣으면 신청서 16종의 칸이 차례로 채워지고, 직접 넣을 칸만 남습니다. 주소를 넣으면 주변 학교와 주택 같은 보호시설을 불러와 안전거리를 3D로 판정합니다. 거리 계산은 AI가 아니라 좌표 코드가 하고, AI는 배치도를 읽는 일만 합니다.');

  // 15 실현 가능성
  sec('04 실현 가능성 및 기대효과');
  s = slide('04 실현 가능성 및 기대효과');
  head(s, '04', '실현 가능성 및 기대효과', '실현 가능성: 이미 배포되어 돌아가는 서비스입니다');
  [[I.server, '운영 중', '웹 서비스 + 윈도우 앱(0.2.3)\n새 버전은 켤 때 자동 업데이트'], [I.coins, '낮은 운영 비용', '답변 1건 약 24원\n(30문항 약 720원, 2026-11 추정)'], [I.rotate, '쉬운 유지보수', '법이 바뀌면 자료만 교체\n111문항 자동 채점으로 품질 확인']].forEach(([ic, t, d], i) => {
    const y = 2.5 + i * 1.38;
    shadowCard(s, 1.0, y, 5.2, 1.22, 'feas' + i);
    iconDot(s, ic, 1.25, y + 0.25, 0.72, HEX.sky, 'feas-icon' + i);
    txt(s, t, { x: 2.2, y: y + 0.14, w: 3.85, h: 0.42, fontSize: 16, bold: true });
    txt(s, d, { x: 2.2, y: y + 0.55, w: 3.85, h: 0.6, fontSize: 12.5, color: C.text2 });
  });
  shot(s, 'home.png', 6.65, 2.5, 5.68, 3.55, 'shot-home');
  txt(s, '첫 화면: 사업장 정보를 넣으면 "한빛수소 님"처럼 맞춤 인사와 추천 질문', { x: 6.65, y: 6.2, w: 5.68, h: 0.4, fontSize: 12, color: C.accent6 });
  s.addNotes('실현 가능성입니다. 수소문은 계획이 아니라 이미 배포되어 돌아가고 있습니다. 웹과 윈도우 앱이 있고, 새 버전은 앱을 켤 때 자동으로 업데이트됩니다. 답변 한 건 비용은 약 24원으로 추정되고, 법이 바뀌면 자료만 바꾸면 됩니다.');

  // 16 기대효과
  s = slide('04 실현 가능성 및 기대효과');
  head(s, '04', '실현 가능성 및 기대효과', '기대효과: 사업자, 가스안전공사, 정책 모두에게');
  [[I.user, '사업자', ['규정 찾는 시간 단축', '같은 정보 반복 입력 제거', '형식 오류로 인한 반려 감소']], [I.shield, '한국가스안전공사', ['빈칸·누락 서류 자동 확인', '근거 조문이 붙은 보완 요청', '검토 인력은 기술 판단에 집중']], [I.landmark, '정책', ['인허가 기간 단축', '수소충전소 보급 확대 기여', '법 개정 내용의 빠른 전달']]].forEach(([ic, t, items], i) => {
    const x = 1.0 + i * 3.83;
    shadowCard(s, x, 2.5, 3.5, 4.05, 'eff' + i);
    iconDot(s, i === 1 ? I.shieldW : ic, x + 0.3, 2.78, 0.85, i === 1 ? HEX.blue : HEX.sky, 'eff-icon' + i);
    txt(s, t, { x: x + 0.3, y: 3.8, w: 3.0, h: 0.5, fontSize: 19, bold: true });
    txt(s, items.map((it, k) => ({ text: it, options: { bullet: true, breakLine: k < items.length - 1 } })), { x: x + 0.3, y: 4.4, w: 3.0, h: 1.9, fontSize: 14, color: C.text2, paraSpaceAfter: 8, valign: 'top' });
  });
  s.addNotes('기대효과입니다. 사업자는 규정을 찾고 같은 정보를 반복해 쓰는 시간을 줄이고, 가스안전공사는 빈칸이나 누락 서류 같은 형식 검토를 자동으로 걸러 기술 판단에 집중할 수 있습니다. 결과적으로 인허가 기간이 줄어 수소충전소 보급에 기여할 수 있습니다.');

  // 17 결론
  sec('05 결론 및 제언');
  s = slide('05 결론 및 제언');
  head(s, '05', '결론 및 제언', '결론: 근거 있는 답이 인허가를 바꿉니다');
  shadowCard(s, 1.0, 2.5, 6.0, 4.05, 'concl');
  txt(s, '결론', { x: 1.35, y: 2.7, w: 3, h: 0.45, fontSize: 18, bold: true, color: C.accent1 });
  const CON = ['법령 32,229조각을 근거로 답하는 RAG 구현', '30문항 97/100점, 틀린 단정 0건 (범용 AI의 2배)', '상담부터 신청서·3D 검토·제출 점검까지 한 흐름', '웹·윈도우 앱으로 배포, 바로 현장에 투입 가능'];
  txt(s, CON.map((c, k) => ({ text: c, options: { bullet: true, breakLine: k < CON.length - 1 } })), { x: 1.35, y: 3.3, w: 5.4, h: 3.1, fontSize: 16, paraSpaceAfter: 26, valign: 'top' });
  card(s, 7.33, 2.5, 5.0, 4.05, HEX.sky, 'next');
  txt(s, '발전 방안', { x: 7.68, y: 2.7, w: 3, h: 0.45, fontSize: 18, bold: true, color: C.accent2 });
  [[I.building, '건축물대장 연계', '3D 검토의 건물 용도 정확도 향상'], [I.rotate, '법령 개정 자동 반영', '법제처 공식 API로 자료 자동 갱신'], [I.hand, '공사 접수 시스템 연계', '보완 요청까지 한 화면에서 처리']].forEach(([ic, t, d], i) => {
    const y = 3.3 + i * 1.03;
    iconDot(s, ic, 7.68, y + 0.05, 0.66, 'FFFFFF', 'next-icon' + i);
    txt(s, t, { x: 8.55, y, w: 3.6, h: 0.4, fontSize: 15, bold: true });
    txt(s, d, { x: 8.55, y: y + 0.4, w: 3.6, h: 0.4, fontSize: 12.5, color: C.text2 });
  });
  s.addNotes('정리하면, 수소문은 법령 근거로 답하는 AI로 범용 AI보다 두 배 정확하고 틀린 단정이 없었으며, 상담부터 제출 준비까지 한 흐름으로 이미 배포되어 있습니다. 앞으로 건축물대장을 연계해 3D 검토를 더 정확하게 하고, 법령 개정을 자동으로 반영하고, 가스안전공사 접수 시스템과 연결하는 것이 목표입니다.');

  // 18 성찰 1
  sec('06 성찰 및 배운 점');
  s = slide('06 성찰 및 배운 점');
  head(s, '06', '성찰 및 배운 점', '성찰 ①: 측정하고, 원인을 찾고, 고친 기록');
  const TL = [['51', '첫 채점', '별표가 없어 "별표 8에 있다"는 답뿐'], ['69', '검색 확장', '근거 법령명 표시, 되묻기 오작동 수정'], ['97', '자료 보강·버그 수정', '수수료 고시·해석례 추가, 지난 답 캐시 문제 발견']];
  TL.forEach(([n, t, d], i) => {
    const x = 1.0 + i * 3.9;
    shadowCard(s, x, 2.5, 3.4, 2.15, 'tl' + i);
    txt(s, [{ text: n, options: { fontSize: 40, bold: true, color: i === 2 ? C.accent1 : C.text1 } }, { text: ' / 100', options: { fontSize: 16, bold: true, color: C.accent6 } }], { x: x + 0.3, y: 2.62, w: 2.9, h: 0.85, valign: 'bottom' });
    txt(s, t, { x: x + 0.3, y: 3.52, w: 2.9, h: 0.4, fontSize: 15, bold: true });
    txt(s, d, { x: x + 0.3, y: 3.92, w: 2.9, h: 0.65, fontSize: 12.5, color: C.text2 });
    if (i < 2) arrow(s, x + 3.47, 3.4, 0.38, HEX.blue);
  });
  [[I.gauge, '측정하지 않으면 고칠 수 없다', '감으로 고치면 다른 곳이 망가졌습니다.\n111문항 자동 채점을 만든 뒤에야 안심하고 고쳤습니다'], [I.code, '숫자는 코드, 읽기는 AI', 'AI에게 계산을 맡기면 틀립니다.\n거리·수수료 같은 계산은 프로그램이 맡도록 나눴습니다']].forEach(([ic, t, d], i) => {
    const x = 1.0 + i * 5.83;
    card(s, x, 4.9, 5.5, 1.68, HEX.sky, 'lesson' + i);
    iconDot(s, ic, x + 0.25, 5.15, 0.7, 'FFFFFF', 'lesson-icon' + i);
    txt(s, t, { x: x + 1.15, y: 5.1, w: 4.2, h: 0.45, fontSize: 16, bold: true, color: C.accent2 });
    txt(s, d, { x: x + 1.15, y: 5.55, w: 4.2, h: 0.95, fontSize: 12.5, color: C.text2 });
  });
  s.addNotes('[초안] 처음 채점은 100점 환산 51점이었습니다. 별표 자료가 없어서 별표 8에 있다는 답만 했습니다. 검색을 넓히고 근거 법령명을 보여 주며 69점, 수수료 고시와 법제처 해석례를 보강하고 지난 답을 그대로 내보내던 캐시 문제를 찾아 고치며 97점이 되었습니다. 감으로 고치면 다른 곳이 망가진다는 것, 그리고 틀리면 안 되는 계산은 AI가 아니라 프로그램에 맡겨야 한다는 것을 배웠습니다.');

  // 19 성찰 2
  s = slide('06 성찰 및 배운 점');
  head(s, '06', '성찰 및 배운 점', '성찰 ②: 프로젝트로 키운 첨단 분야 직무 역량');
  [[I.scale, '인허가 실무 이해', '멘토링으로 기술검토 → 허가 → 완성검사 흐름과\n성능기준·상세기준 구조를 직접 정리'], [I.search, 'AI 검색·평가 설계', 'RAG·BM25 검색, 환각 검증, 회귀 평가로\n"믿을 수 있는 AI"의 조건을 체득'],
    [I.users, '사용자 중심 설계', '사업자 질문 117건으로 기능 우선순위를 정하고\n한 화면 한 질문 방식으로 화면을 다듬음'], [I.hand, '협업과 피드백', '4파트로 나눠 개발하고\n멘토 피드백과 채점 결과로 매주 방향을 수정']].forEach(([ic, t, d], i) => {
    const x = 1.0 + (i % 2) * 5.83, y = 2.5 + Math.floor(i / 2) * 1.75;
    shadowCard(s, x, y, 5.5, 1.55, 'comp' + i);
    iconDot(s, ic, x + 0.28, y + 0.38, 0.8, HEX.sky, 'comp-icon' + i);
    txt(s, t, { x: x + 1.3, y: y + 0.18, w: 4.0, h: 0.45, fontSize: 16, bold: true });
    txt(s, d, { x: x + 1.3, y: y + 0.63, w: 4.0, h: 0.8, fontSize: 12.5, color: C.text2 });
  });
  card(s, 1.0, 6.05, 11.33, 0.55, HEX.soft, 'quote');
  txt(s, '"AI를 똑똑하게 만드는 것보다, 틀리지 않게 만드는 것이 훨씬 어려웠고 더 중요했다."', { x: 1.0, y: 6.05, w: 11.33, h: 0.55, fontSize: 14, bold: true, color: C.text1, align: 'center', valign: 'middle' });
  s.addNotes('[초안, 팀원별 소감으로 바꿔 주세요] 이번 프로젝트로 인허가 실무 구조를 직접 이해했고, 믿을 수 있는 AI를 만드는 검색과 평가 방법을 익혔습니다. 사업자 질문을 분석해 기능을 정하는 사용자 중심 설계와, 멘토 피드백으로 방향을 고치는 협업도 배웠습니다. 한 문장으로 말하면, AI를 똑똑하게 만드는 것보다 틀리지 않게 만드는 것이 더 어렵고 더 중요했습니다.');

  // 20 Q&A
  sec('Q&A');
  s = slide('Q&A');
  s.addImage({ path: IMG('mascot.png'), x: 5.42, y: 1.45, w: 2.5, h: 2.5, objectName: 'mascot' });
  txt(s, 'Q & A', { x: 1.0, y: 4.05, w: 11.33, h: 1.0, fontSize: 48, bold: true, align: 'center', valign: 'middle' });
  txt(s, '감사합니다', { x: 1.0, y: 5.05, w: 11.33, h: 0.5, fontSize: 18, color: C.text2, align: 'center' });
  card(s, 3.67, 5.85, 6.0, 0.5, HEX.sky, 'url');
  txt(s, 'hydrogen-guide.tmdfoqhdl030.workers.dev', { x: 3.67, y: 5.85, w: 6.0, h: 0.5, fontSize: 14, bold: true, color: C.accent2, align: 'center', valign: 'middle' });
  s.addNotes('들어 주셔서 감사합니다. 질문 받겠습니다.');

  const out = path.join(__dirname, 'sosomun_wemeet.pptx');
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log('written', out);
})().catch(e => { console.error(e); process.exit(1); });
