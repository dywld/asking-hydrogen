/* 용도지역별 수소충전소 허용 여부. site3d.html(부지 3D 검토)과 index.html(채팅 주소 카드)이 같이 쓴다.
 * 수소충전소 = 건축법 시행령 별표 1 제19호 위험물 저장 및 처리 시설 중 고압가스 충전소,
 *              환경친화적자동차법 제2조제9호 수소연료공급시설.
 * 국토계획법 시행령 별표 2~22(2026. 9. 18. 시행본)를 읽고 정리했다.
 *   ok : 건축할 수 있는 건축물(제1호)에 있음
 *   okc: 건축할 수 없는 건축물 목록에서 빠져 있으나 도시·군계획조례로 막을 수 있음(제2호)
 *   ord: 도시·군계획조례가 정하면 건축할 수 있음(제2호)
 *   no : 어느 목록에도 없음
 */
window.ZONE_RULES = (() => {
  const HY = {제1종전용주거지역: ['no', '별표 2'], 제2종전용주거지역: ['no', '별표 3'], 제1종일반주거지역: ['ord', '별표 4 제2호'], 제2종일반주거지역: ['ord', '별표 5 제2호'], 제3종일반주거지역: ['ord', '별표 6 제2호'],
    준주거지역: ['okc', '별표 7'], 중심상업지역: ['okc', '별표 8'], 일반상업지역: ['okc', '별표 9'], 근린상업지역: ['okc', '별표 10'], 유통상업지역: ['okc', '별표 11'],
    전용공업지역: ['ok', '별표 12 제1호'], 일반공업지역: ['ok', '별표 13 제1호'], 준공업지역: ['ok', '별표 14'],
    보전녹지지역: ['ord', '별표 15 제2호'], 생산녹지지역: ['ok', '별표 16 제1호'], 자연녹지지역: ['ord', '별표 17 제2호'],
    보전관리지역: ['ord', '별표 18 제2호'], 생산관리지역: ['ord', '별표 19 제2호'], 계획관리지역: ['okc', '별표 20'], 농림지역: ['ord', '별표 21 제2호'], 자연환경보전지역: ['ord', '별표 22 제2호']};
  const HY_TXT = {ok: '지을 수 있어요', okc: '지을 수 있어요 (시·군 조례로 막을 수 있어 조례 확인)', ord: '시·군 조례가 허용하면 지을 수 있어요', no: '지을 수 없어요'};
  const HY_SHORT = {ok: '지을 수 있어요', okc: '지을 수 있어요 (조례 확인)', ord: '조례가 허용하면 가능', no: '못 지어요'};
  // 점이 용도지역 면(바깥 고리 + 구멍)에 들어 있나. 좌표는 [x, y] 아무 단위
  const inRing = (p, r) => { let c = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++) { const [xi, yi] = r[i], [xj, yj] = r[j]; if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) c = !c; } return c; };
  const inPoly = (p, poly) => inRing(p, poly[0]) && !poly.slice(1).some(h => inRing(p, h));
  // 서버 /api/site/parcel/zone 결과({zones:[{layer, name, polys}]})에서 [경도, 위도] 점의 용도지역과 개발제한구역 여부
  function at(zones, lon, lat) {
    const p = [lon, lat], hit = z => (z.polys || []).some(poly => inPoly(p, poly));
    const z = (zones || []).find(z => z.layer !== 'UD801' && HY[z.name] && hit(z));
    return {name: z ? z.name : '', gb: (zones || []).some(z => z.layer === 'UD801' && hit(z))};
  }
  return {HY, HY_TXT, HY_SHORT, inPoly, at};
})();
