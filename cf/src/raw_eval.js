// 모델 비교 채점용: 검색 근거 없이 ChatGPT 에 질문만 그대로 보낸다(팀 비교표의 "그냥 ChatGPT" 칸).
// 아무 질문이나 받으면 공짜 ChatGPT 통로가 되므로, 팀 30문항과 글자까지 같은 질문만 받는다.
const QS = new Set([
"수소충전소를 새로 지으려면 어떤 인허가 절차를 거쳐야 하나요? 순서대로 알려주세요.",
"수소충전소 허가 신청 전에 반드시 먼저 받아야 하는 것은?",
"수소충전소 설비를 시공하는 도중에 받아야 하는 검사는?",
"수소충전소 완공 후 정기검사는 어떤 근거로, 얼마마다 받나요?",
"국내에서 연료전지나 수전해 설비를 제조하려면 어떤 허가를 받아야 하나요?",
"외국 제조사가 만든 수소용품을 국내에 들여오려면 제조사는 어떤 절차를 거치나요?",
"수소연료전지를 설치해 전기·열을 쓰는 시설(수소연료사용시설)은 어떤 검사를 받나요?",
"수소용품 제조자나 수입자는 제품을 팔기 전에 무엇을 해야 하나요?",
"수소충전소의 시설·기술·검사 기준은 어디에 규정되어 있나요?",
"수소충전소 안에 사무실이나 편의시설이 수소설비에서 30m 이내에 있으면 어떻게 해야 하나요?",
"수소충전소를 신설할 때 주변 인구 밀집도는 어떻게 반영되나요?",
"수소연료사용시설의 시설기준과 기술기준은 어디에 있나요?",
"수소법상 '수소용품'에는 무엇이 포함되나요?",
"수소충전소 안전관리책임자는 어떤 자격이 있어야 하나요?",
"저장식 수소충전소도 고압가스 품질검사를 받아야 하나요?",
"수소용품 제조사업자의 안전관리규정에는 어떤 내용이 들어가야 하나요?",
"고정형 연료전지의 설계단계검사 수수료는 얼마인가요?",
"정격수소생산량 30 N㎥/h인 수전해설비의 생산단계검사 수수료는?",
"저장능력 500㎥인 압축수소가스 제조(저장)시설의 완성검사·정기검사 수수료는?",
"수소용품 생산공정검사와 종합공정검사의 최초 검사수수료는 각각 얼마인가요?",
"허가 없이 수소용품을 제조하면 어떤 처벌을 받나요?",
"검사를 받지 않은 수소용품을 제조·수입하면 어떤 처벌을 받나요?",
"현재 수소 안전관리를 담당하는 주무부처는 어디인가요?",
"액화수소 충전소를 규제특례(실증)로 설치할 때 안전관리 절차는?",
"고압가스 충전(수소충전소) 허가 신청서는 어떤 서식이고, 무엇을 첨부해야 하나요?",
"수소용품 제조허가 신청 시 제출해야 하는 서류는?",
"수소연료사용시설 완성검사를 신청하려면 어떤 서식에 무엇을 첨부하나요?",
"일본에서는 수소충전소와 주거지 사이 이격거리가 몇 m인가요?",
"수소차 구매 보조금은 얼마인가요?",
"수소법 제150조에 따른 신고 절차를 알려주세요."
]);
const MODELS = new Set(['gpt-5.2', 'gemini-2.5-flash', 'gpt-6-luna', 'gemini-3.8-flash', 'gemini-3.5-flash-lite']);

export async function rawAnswer(env, q, model) {
  if (!QS.has(q) || !MODELS.has(model)) return null;
  if (model.startsWith('gemini')) {
    if (!env.GEMINI_API_KEY) return null;
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'x-goog-api-key': env.GEMINI_API_KEY },
      body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: q }] }] }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return { error: `${r.status} ${d.error?.message || ''}`.slice(0, 200) };
    return { text: (d.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join(''), usage: d.usageMetadata || null, model: d.modelVersion };
  }
  if (!env.OPENAI_API_KEY) return null;
  const r = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.OPENAI_API_KEY}` },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: q }] }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return { error: `${r.status} ${d.error?.message || ''}`.slice(0, 200) };
  return { text: d.choices?.[0]?.message?.content || '', usage: d.usage || null, model: d.model };
}
