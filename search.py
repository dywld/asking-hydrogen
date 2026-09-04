#!/usr/bin/env python3
"""법령 조문 검색 — 외부 라이브러리 없이 BM25로 찾는다.

임베딩 모델을 쓰지 않는 이유: 조문이 3,184개뿐이라 키워드 검색만으로도
'수소', '고압가스', '충전소' 같은 법령 용어는 정확히 걸린다. API 키가 없어도
검색까지는 그냥 돌아가야 MVP 확인이 쉽다.
"""
import json
import math
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path

DATA = Path(__file__).parent / "data"

# ── 뜻으로 찾기(임베딩) ────────────────────────────────────────────
# BM25 는 글자가 겹치는지만 본다. '처벌'로 물으면 '벌칙' 조문을 못 찾는다.
# embed_index.py 로 미리 만들어 둔 숫자와 견줘서 뜻이 가까운 것도 끌어온다.
# 파일이 없으면 이 기능만 조용히 꺼지고 나머지는 그대로 돈다.
EMB = DATA / "embeddings.npy"
HAVE = DATA / "embeddings_have.npy"
EMB_META = DATA / "embeddings.json"
EMB_WEIGHT = float(os.environ.get("BOT_EMB_WEIGHT", "0.45"))
COVER_MIN = float(os.environ.get("BOT_EMB_COVER", "0.98"))

HANGUL = re.compile(r"[가-힣]+")
CJK = re.compile(r"[一-鿿ぁ-ゟ゠-ヿ]+")
WORD = re.compile(r"[A-Za-z0-9]+")


def tokenize(text):
    """한국어·일본어는 띄어쓰기가 못 미더워 글자 2개씩 잘라 색인한다.

    '수소충전소'를 검색해도 '수소 충전소'가 걸리게 하려면 이 방법이 가장 싸다.
    """
    text = text.lower()
    out = []
    for m in HANGUL.findall(text) + CJK.findall(text):
        if len(m) == 1:
            out.append(m)
        else:
            out += [m[i:i + 2] for i in range(len(m) - 1)]
    out += WORD.findall(text)
    return out


# 대화체 질문("~세우려면 어떤 게 필요해?")은 조사·의문어가 잡음이 된다.
# 법령 본문에는 없는 말들이라 지우고 검색해야 조문이 제대로 걸린다.
FILLER = re.compile(
    r"(어떤|무엇|뭐가|뭔가|어떻게|얼마나|필요해요?|필요한가요?|필요합니까|알려줘|알려주세요|"
    r"인가요|입니까|되나요|하나요|해야|하려면|하는지|관련|대해|대한|주세요|줘|좀|그럼|"
    r"저는|제가|우리|합니까|건가요|건지|건데|같은|경우|절차가|무슨)")

# 실무 용어 ↔ 법령 용어가 달라서 그대로는 안 걸린다.
# (실측: '충전소'로는 고압가스법 '제조허가' 조문이 안 나왔다.)
EXPAND = {
    # 충전은 법률상 '제조'다(고압가스법 제4조① 괄호). 조문에 '충전소'라는 말이
    # 없어서 그대로는 안 걸린다. 다만 '충전사업'을 넣으면 액화석유가스법
    # 제5조(충전사업 허가)가 제목 가산점으로 상위를 독점한다(실측). 그래서 뺐다.
    "충전소": "충전시설 제조허가 제조신고 제조소 고압가스",
    "수소차": "수소연료 자동차 충전",
    "수소버스": "수소연료 충전시설",
    "세우": "설치 시설 허가",
    "짓": "설치 시설 허가",
    "만들": "설치 제조",
    "허가": "허가 신고 등록 승인",
    "검사": "검사 완성검사 정기검사 중간검사",
    # "검사는 누가 하나?" 의 답은 두 조각에 나뉘어 있다.
    # 법 제16조가 '허가관청의 검사'라 하고, 시행령 제25조가 그 업무를
    # 한국가스안전공사에 위탁한다. 위탁 조문을 못 찾으면 "주체가 없다"고 답한다(실측).
    "누가": "업무의 위탁 한국가스안전공사 허가관청",
    "누구": "업무의 위탁 한국가스안전공사 허가관청",
    "주체": "업무의 위탁 한국가스안전공사 허가관청",
    "안전거리": "이격거리 시설기준 기술기준 보호시설",
    # 규제특례는 우산 같은 말이다. 아래로 실증특례·임시허가·규제 신속확인이 있고
    # 근거법도 둘(산업융합촉진법·규제자유특구법)이다. '실증특례'만 넣어 두었더니
    # 답변이 실증특례 하나로만 좁아졌다(실측). 셋을 모두 끌어온다.
    "규제특례": "실증을 위한 특례 실증특례 임시허가 신속확인",
    "실증특례": "실증을 위한 특례 실증특례",
    "비용": "수수료 부담금",
    "기간": "기간 처리기간 유효기간",
    # 아래는 50문항 점검에서 엉뚱한 법이 나오던 것들이다.
    # 벌칙 조문은 "제4조에 따른 허가를 받지 아니하고…" 식이라 '충전'·'처벌' 같은
    # 실무 용어가 한 글자도 안 들어 있다. 그래서 그대로는 절대 안 걸린다.
    "처벌": "벌칙 징역 벌금",
    "벌칙": "벌칙 징역 벌금",
    "과태료": "과태료 부과기준",
    "폐업": "사업 개시 폐지 신고 폐기",
    "폐지": "사업 개시 폐지 신고 폐기",
    "휴업": "사업 개시 중단 재개 신고",
    "쉬려": "사업 개시 중단 재개 신고",
    "교육": "안전교육",
    "취소": "허가 등록의 취소 사업정지",
    "보험": "보험금액 책임보험 가입",
    "양도": "지위의 승계 양수",
    # 아래 둘은 78문항 채점에서 남아 있던 실패다.
    # "기준이 없는 새 기술" — 답은 실증특례·임시허가·신속확인인데 질문에 그 말이 없다.
    "기준이 없": "실증을 위한 규제특례 임시허가 규제 신속확인 기준ㆍ규격ㆍ요건 등이 없는 경우",
    "새 기술": "신기술 실증을 위한 규제특례 임시허가 산업융합 신제품",
    "새로운 기술": "신기술 실증을 위한 규제특례 임시허가 산업융합 신제품",
    # "사업 시작 전후 절차" — 산업안전보건법·환경영향평가법이 '절차'로 걸려 올라왔다.
    "사업 시작": "사업 개시 신고 제조허가 기술검토 완성검사 고압가스",
    "사업을 시작": "사업 개시 신고 제조허가 기술검토 완성검사 고압가스",
    "순서대로": "허가 기술검토 중간검사 완성검사 사업 개시 신고 고압가스",
}


# 일본 법령은 일본어 원문뿐이라, 한국어 질문으로는 글자가 하나도 안 겹친다.
# ('일본은 어떻게 인정받아?' → 일본 조문 0건. 실측)
# 질문에 '일본'이 있으면 일본어 대역어를 함께 넣어 검색한다.
JP_WORDS = {
    "수소": "水素", "저탄소": "低炭素", "인정": "認定", "허가": "許可",
    "신고": "届出", "공급": "供給", "이용": "利用", "사업자": "事業者",
    "계획": "計画", "지원": "支援", "기준": "基準", "안전": "安全",
    "제조": "製造", "저장": "貯蔵", "판매": "販売", "충전": "充填",
    "설비": "設備", "가격": "価格", "절차": "手続", "신청": "申請",
}

# 절차를 묻는 질문("어디에 신고해?")에 시설기준 상세조항이 올라오면 답이 어긋난다.
# KGS Code 조각이 2만 개라 그냥 두면 절차 질문까지 뒤덮는다(실측).
PROCEDURE = re.compile(
    r"(허가|신고|등록|승인|절차|신청|접수|서류|서식|처리기간|며칠|누가|누구|"
    r"어디에|어디서|받아야|해야 하나|밟)")

# 조문 본문 안의 "제10조의3" 같은 참조. 같은 법 안에서만 따라간다.
XREF = re.compile(r"제(\d{1,3})조(?:의(\d{1,2}))?")

# 우산 개념 → 갈래. 질문에 우산 말이 있으면 갈래마다 1등을 보장한다.
BUNDLES = {
    "규제특례": ["실증을 위한 규제특례", "임시허가", "규제 신속확인"],
    "특례": ["실증을 위한 규제특례", "임시허가", "규제 신속확인"],
    "검사": ["완성검사", "정기검사", "중간검사"],
    "안전관리자": ["안전관리자의 자격과 선임 인원", "안전관리자 선임 신고"],
}

# 개정 내용을 묻는 말. 시행 예정판을 앞세우고 현행판을 짝으로 붙인다.
CHANGE = re.compile(r"(바뀌|바뀐|개정|변경|달라지|달라진|신설|새로 생긴|바뀔)")

# 재순위(크로스인코더). rerank.py 참고. 기본은 끔 — 서버(CPU)에서 1~3초가 더 든다.
RERANK_ON = os.environ.get("BOT_RERANK", "0") == "1"
RERANK_N = int(os.environ.get("BOT_RERANK_N", "24"))


# ── 시설유형 분류 ────────────────────────────────────────────────
# 연구계획서가 요구한 "시설 유형별 DB"(생산·저장·운반·충전·사용).
# 조각마다 꼬리표를 달아두면, 질문이 유형을 가리킬 때 그쪽을 끌어올릴 수 있다.
FACILITY = {
    "생산": ["제조소", "생산시설", "개질", "수전해", "제조시설", "특정제조", "일반제조"],
    "저장": ["저장설비", "저장소", "저장시설", "저장탱크", "용기보관실", "저장능력"],
    "운반": ["운반", "운반차량", "탱크로리", "배관", "이송", "튜브트레일러", "차량에 고정된 탱크"],
    "충전": ["충전소", "충전시설", "충전사업", "충전설비", "수소연료 충전"],
    "사용": ["사용시설", "연료사용", "특정고압가스 사용", "사용신고"],
    "판매": ["판매시설", "판매사업", "수입업"],
}


# 이 챗봇의 주제는 수소시설 인허가다. 같은 내용을 여러 법이 비슷하게 규정할 때
# (벌칙·행정처분·사업개시 신고 등) 질문이 법을 특정하지 않으면 아무 법이나 올라온다.
# 실측: "허가 없이 충전사업을 하면 처벌은?" → 액법·도시가스법 벌칙만 나왔다.
# 그래서 주제법에 약한 가산점을 준다. 배제가 아니라 가산이라 액법 질문도 그대로 걸린다.
# KGS 는 넣지 않는다. 코드 188종에 액법·도시가스법 것이 섞여 있어
# 통째로 올리면 수소 질문에 액법 코드가 딸려 온다(실측).
CORE_LAWS = ("고압가스", "수소경제")


# 가스 종류가 섞이는 것이 오답의 큰 축이었다.
# "수소충전소 안전거리"를 물으면 액화석유가스 충전 코드(FP331~334)가 먼저 올라온다.
# 조문 구조가 똑같아서 점수가 비슷하기 때문이다.
# 질문이 가스를 지목했는데 조각이 다른 가스를 다루면 뒤로 민다.
# KGS Code 는 앞 두 글자가 성격을 가른다.
#   AA·AB·AC — 기기·설비를 '만드는' 기준
#   FP·FU·FS — 시설을 '설치·운영하는' 기준
# "긴급차단장치는 어떤 경우에 설치하나요?" 에 제조 기준(AA317)이 1위로 올라왔다.
# 이름이 같아서다. 설치를 물었으면 시설 쪽 코드를 앞세운다.
MAKE_CODE = ("KGS AA", "KGS AB", "KGS AC", "KGS AH")
INSTALL = re.compile(r"(설치|시설|충전소|이격|거리|배치|갖춰|갖추)")

GAS = {
    "수소": ("수소",),
    "액화석유가스": ("액화석유가스", "액화 석유", "LPG"),
    "도시가스": ("도시가스",),
}


_LAW_NOISE = re.compile(r"[\s·ㆍᆞ・]")
NOISE_TITLE = re.compile(r"다른 법령의 개정|다른 법률의 개정")


def law_key(law):
    """법령명 비교용. '수소경제 육성 및 … 시행규칙' 과 '수소경제육성및…시행규칙' 을 같게 본다."""
    return _LAW_NOISE.sub("", law)


def gas_of(text):
    return {k for k, words in GAS.items() if any(w in text for w in words)}


def facility_tags(text):
    """조각 하나가 어떤 시설 유형을 다루는지 표시한다(여러 개 가능)."""
    return [k for k, words in FACILITY.items() if any(w in text for w in words)]


def expand(query):
    q = FILLER.sub(" ", query)
    extra = [v for k, v in EXPAND.items() if k in query]
    if "일본" in query:
        extra += [v for k, v in JP_WORDS.items() if k in query]
        extra.append("水素 日本")          # 아무 단어도 안 걸릴 때의 최소 실마리
    return q + " " + " ".join(extra)


def load_docs():
    docs = []

    kr = DATA / "korea_laws.jsonl"
    if kr.exists():
        for line in kr.open(encoding="utf-8"):
            r = json.loads(line)
            law = r.get("file_name", "").split("(")[0].strip()
            docs.append({
                "country": "한국",
                "law": law,
                "article": r.get("article") or "",
                "title": r.get("title") or "",
                "content": r.get("content") or "",
                "source": r.get("file_name", ""),
                # 시행 예정 조문은 답변에서 구분해 줘야 실무자가 헷갈리지 않는다.
                "future": r.get("version") == "future",
                "effective_date": r.get("effective_date"),
            })

    # 규제특례 근거법(산업융합촉진법·규제자유특구법). 팀 원본에는 없어서 따로 받았다.
    ex = DATA / "korea_laws_extra.jsonl"
    if ex.exists():
        for line in ex.open(encoding="utf-8"):
            r = json.loads(line)
            docs.append({
                "country": "한국",
                "law": r.get("file_name", "").replace(".pdf", ""),
                "article": r.get("article") or "",
                "title": r.get("title") or "",
                "content": r.get("content") or "",
                "source": r.get("file_name", ""),
                "future": False,
                "effective_date": None,
            })

    # 강원 액화수소 특구 요약(법령이 아니라 공식 누리집 정리본 — 본문에 그렇게 밝혀 둔다)
    gw = DATA / "gangwon_zone.jsonl"
    if gw.exists():
        for line in gw.open(encoding="utf-8"):
            r = json.loads(line)
            docs.append({
                "country": "한국", "law": r["file_name"],
                "article": r["article"], "title": r["title"],
                "content": r["content"], "source": r["file_name"],
                "future": False, "effective_date": None,
            })

    an = DATA / "korea_annexes.jsonl"
    if an.exists():
        for line in an.open(encoding="utf-8"):
            r = json.loads(line)
            part = f" {r['part']}" if r.get("part") else ""
            docs.append({
                "country": "한국",
                "law": r.get("law") or "",
                "article": r.get("annex") + part,
                "title": r.get("title") or "",
                "content": r.get("content") or "",
                "source": r.get("source", ""),
                "future": False,
                "effective_date": None,
                "kind": r.get("kind"),                    # 별표 / 별지서식
                "related": r.get("related_articles") or [],
            })

    # KGS Code(상세기준). 법 → 별표 → 여기가 마지막 칸이라, 실제 수치는 여기 있다.
    kgs = DATA / "kgs_code.jsonl"
    if kgs.exists():
        for line in kgs.open(encoding="utf-8"):
            r = json.loads(line)
            item = f" {r['item']}" if r.get("item") else ""
            docs.append({
                "country": "한국",
                "law": r["law"],                       # 예: KGS FP216
                "article": f"[{r['law']}{item}]",
                "title": r.get("title") or "",
                "content": r.get("content") or "",
                "source": r.get("source", ""),
                "future": False,
                "effective_date": None,
                "kind": "상세기준",
                "base_law": r.get("base_law") or "",
            })

    jp = DATA / "japan_laws.jsonl"
    if jp.exists():
        for line in jp.open(encoding="utf-8"):
            r = json.loads(line)
            m = r.get("metadata") or {}
            docs.append({
                "country": "일본",
                "law": m.get("law_name") or "",
                "article": m.get("article") or "",
                "title": m.get("article_title") or "",
                "content": r.get("content") or "",
                "source": m.get("file_name", ""),
                "future": False,
                "effective_date": None,
            })

    for d in docs:
        d["facility"] = facility_tags(f"{d['title']} {d['content'][:600]}")

    return docs


_LOCAL_MODEL = None


def embed_query_local(name, text):
    """공개 모델을 이 컴퓨터에서 돌려 질문을 숫자로 바꾼다(embed_local.py 와 같은 모델).

    처음 한 번은 모델을 읽느라 몇 초 걸리고, 그 뒤로는 CPU 에서도 1초 안쪽이다.
    라이브러리가 없으면 None 을 돌려 글자 검색만 한다.
    """
    global _LOCAL_MODEL
    try:
        if _LOCAL_MODEL is None:
            from sentence_transformers import SentenceTransformer
            m = SentenceTransformer(name, device="cpu")
            m.max_seq_length = 128          # 질문은 짧다
            _LOCAL_MODEL = m
        v = _LOCAL_MODEL.encode(text[:600], normalize_embeddings=True,
                                convert_to_numpy=True)
        return v.tolist()
    except Exception:
        return None


def embed_query(text):
    """질문을 같은 방식으로 숫자로 바꾼다. 실패하면 None(=글자 검색만)."""
    if not EMB_META.exists():
        return None
    meta = json.loads(EMB_META.read_text(encoding="utf-8"))
    if meta["model"].startswith("local:"):
        return embed_query_local(meta["model"][6:], text)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        f = Path(__file__).parent / "key.txt"
        key = f.read_text(encoding="utf-8").strip() if f.exists() else ""
    if not key:
        return None
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{meta['model']}:embedContent?key={key}")
    body = json.dumps({"model": f"models/{meta['model']}",
                       "content": {"parts": [{"text": text[:600]}]},
                       "taskType": "RETRIEVAL_QUERY",
                       "outputDimensionality": meta["dim"]}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())["embedding"]["values"]
    except Exception:
        return None                      # 한도·장애 시 조용히 글자 검색만


class Index:
    """BM25. 문서 수가 적어 통째로 메모리에 올린다(약 20MB)."""

    K1 = 1.5
    B = 0.75

    def __init__(self, docs):
        self.docs = docs
        self.tf = []
        self.len = []
        df = Counter()
        for d in docs:
            toks = tokenize(f"{d['law']} {d['article']} {d['title']} {d['content']}")
            c = Counter(toks)
            self.tf.append(c)
            self.len.append(len(toks) or 1)
            df.update(c.keys())
        self.n = len(docs) or 1
        self.avglen = sum(self.len) / self.n
        self.idf = {t: math.log(1 + (self.n - v + 0.5) / (v + 0.5))
                    for t, v in df.items()}

        # (법령명, 제○조) → 그 조문이 부르는 별표 조각들.
        # 본문은 "기준에 적합할 것(별표 8 관련)"에서 끝나므로,
        # 조문이 걸리면 별표를 같이 딸려 보내야 실제 수치까지 답할 수 있다.
        # 별표 쪽 법령명은 띄어쓰기가 없고(수소경제육성및…시행규칙) 조문 쪽은 있다.
        # 가운뎃점도 ㆍ/ᆞ/· 로 제각각이다. 그대로 열쇠로 쓰면 별표 절반(3,081조각)이
        # 영영 연결되지 않는다(실측). 공백·점을 지운 이름으로 맞춘다.
        self.linked = {}
        for i, d in enumerate(docs):
            for art in d.get("related", []):
                self.linked.setdefault((law_key(d["law"]), art), []).append(i)

        # (법령명, 제○조) → 시행 예정 판 조각. '기준일'로 물으면 그날 기준으로
        # 현행/예정 중 맞는 쪽을 앞세우고, "뭐가 바뀌어?" 에는 둘을 나란히 준다.
        self.future_of = {}
        self.current_of = {}
        for i, d in enumerate(docs):
            if d.get("kind") or d["country"] != "한국":
                continue
            k = (law_key(d["law"]), d["article"])
            if d.get("future"):
                self.future_of.setdefault(k, []).append(i)
            else:
                self.current_of.setdefault(k, []).append(i)

        # (법령명, 제○조) → 조각 번호. 조문이 "제10조의3에 따른"처럼 부르는 다른 조문을
        # 같이 딸려 보내려고 만든다(조문→별표 연결과 같은 이유).
        self.by_article = {}
        for i, d in enumerate(docs):
            if not d.get("kind") and d["country"] == "한국" and not d.get("future"):
                self.by_article.setdefault((law_key(d["law"]), d["article"]), i)

        self.vecs = self.have = None
        self.coverage = 0.0
        self.load_vectors()

    def xrefs_of(self, i, limit=2):
        """조각 i 의 본문이 부르는 같은 법의 다른 조문(있는 것만)."""
        d = self.docs[i]
        if d.get("kind") or d["country"] != "한국":
            return []
        out = []
        for m in XREF.finditer(d["content"][:1500]):
            art = f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "")
            if art == d["article"]:
                continue
            j = self.by_article.get((law_key(d["law"]), art))
            if j is not None and j != i and j not in out:
                out.append(j)
            if len(out) >= limit:
                break
        return out

    def search_forms(self, query, n=4):
        """체크리스트용 — 질문과 관련된 별지 서식(신청서·신고서)만 따로 찾는다.

        평소 검색은 서식을 0.3 배로 눌러 두어 잘 안 올라온다(빈 양식이라 근거가 못 된다).
        그런데 "뭐가 필요해?" 에는 제출 서류 이름이 곧 답이라, 따로 뽑아 뒤에 붙인다.
        """
        q = list(dict.fromkeys(tokenize(expand(query))))
        scores = {}
        for i, tf in enumerate(self.tf):
            if self.docs[i].get("kind") != "별지서식":
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                denom = f + self.K1 * (1 - self.B + self.B * self.len[i] / self.avglen)
                s += self.idf.get(t, 0.0) * f * (self.K1 + 1) / denom
            if s > 0:
                if any(k in self.docs[i]["law"] for k in CORE_LAWS):
                    s *= 1.3
                scores[i] = s
        best = sorted(scores.items(), key=lambda kv: -kv[1])[:n]
        return [dict(self.docs[i], score=round(s, 2)) for i, s in best]

    def load_vectors(self):
        """미리 만들어 둔 뜻 벡터를 읽는다. 아직 만드는 중이면 만든 만큼만 쓴다."""
        if not (EMB.exists() and HAVE.exists()):
            return
        try:
            import numpy as np
            vecs = np.load(EMB)
            have = np.load(HAVE)
            if len(vecs) != len(self.docs):
                return                       # 자료가 바뀌었으면 다시 만들어야 한다
            # 절반만 만들어진 상태에서 켜면, 벡터가 있는 조각만 계속 이긴다.
            # (실측: 250개만 만든 상태에서 모든 질문에 건축법이 1등으로 나왔다)
            # 거의 다 만들어졌을 때만 켠다.
            cover = float(have.mean())
            if cover < COVER_MIN:
                self.coverage = cover
                return
            norm = np.linalg.norm(vecs.astype("float32"), axis=1, keepdims=True)
            norm[norm == 0] = 1
            self.vecs = (vecs.astype("float32") / norm)
            self.have = have
            self.coverage = cover
            embed_query("수소")               # 모델을 미리 읽어 첫 질문이 안 늦게
        except Exception:
            self.vecs = self.have = None     # 없으면 글자 검색만으로 돈다

    def search(self, query, top_k=8, country=None, facility=None,
               as_of=None, rerank=None, _inner=False):
        """as_of: 'YYYY-MM-DD'. 그날 기준으로 시행 중인 판을 앞세운다(없으면 구분 안 함).
        rerank: None 이면 환경변수(BOT_RERANK)를 따른다."""
        # 같은 조각이 질문에 두 번 나온다고 점수를 두 배 주면
        # '허가'가 반복되는 긴 정의 조문이 계속 1등으로 올라온다.
        q = list(dict.fromkeys(tokenize(expand(query))))
        want_jp = "일본" in query                 # 일본을 물으면 일본 조문을 끌어올린다
        procedural = bool(PROCEDURE.search(query))
        want_change = bool(CHANGE.search(query))  # "뭐가 바뀌어?" → 개정판을 끌어올린다
        # 질문 자체가 유형을 가리키면("충전소 …") 그 유형 조각을 끌어올린다.
        want = set(facility_tags(query)) | ({facility} if facility else set())
        want_gas = gas_of(query)
        want_install = bool(INSTALL.search(query))
        scores = {}
        for i, tf in enumerate(self.tf):
            if country and self.docs[i]["country"] != country:
                continue
            if facility and facility not in (self.docs[i].get("facility") or []):
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                denom = f + self.K1 * (1 - self.B + self.B * self.len[i] / self.avglen)
                s += self.idf.get(t, 0.0) * f * (self.K1 + 1) / denom
            if s <= 0:
                continue
            # 조문 제목·법령명에 질문 단어가 있으면 본문에만 있는 것보다 훨씬 정확하다.
            head = tokenize(f"{self.docs[i]['law']} {self.docs[i]['title']}")
            s *= 1 + 0.5 * len(set(q) & set(head)) / max(len(q), 1)
            # 별지 서식은 빈 양식이라 근거로 쓸 내용이 없다. 이름값만 하게 뒤로 민다.
            if self.docs[i].get("kind") == "별지서식":
                s *= 0.3
            # 유형이 맞으면 30% 가산. 배제가 아니라 가산이라 놓치는 게 없다.
            if want & set(self.docs[i].get("facility") or []):
                s *= 1.3
            if any(k in self.docs[i]["law"] for k in CORE_LAWS):
                s *= 1.15
            # 부칙의 '다른 법령의 개정'은 다른 법 이름을 줄줄이 나열한 조문이라
            # 아무 질문에나 걸린다(실측: 인사말에 1등). 근거가 될 일이 없으니 뒤로 민다.
            if NOISE_TITLE.search(self.docs[i]["title"]):
                s *= 0.2
            if want_install and self.docs[i]["law"].startswith(MAKE_CODE):
                s *= 0.6                  # 만드는 기준은 설치 질문의 답이 아니다
            if want_gas:
                d = self.docs[i]
                doc_gas = gas_of(f"{d['law']} {d['title']}")
                if doc_gas and not (doc_gas & want_gas):
                    s *= 0.5              # 다른 가스를 다루는 조각
            if want_jp:
                s *= 3.0 if self.docs[i]["country"] == "일본" else 0.5
            # 절차를 물었으면 조문을, 수치를 물었으면 상세기준을 앞세운다.
            if procedural and self.docs[i].get("kind") == "상세기준":
                s *= 0.55
            d = self.docs[i]
            if d.get("future"):
                if want_change:
                    s *= 2.0                  # 개정 내용을 물었으니 예정판이 답이다
                elif as_of and (d.get("effective_date") or "9999") > as_of:
                    s *= 0.15                 # 기준일에 아직 시행 전인 판
            elif as_of and not d.get("kind") and d["country"] == "한국":
                # 기준일에 이미 시행된 개정판이 있으면 옛 판은 뒤로 민다.
                fut = self.future_of.get((law_key(d["law"]), d["article"]), ())
                if any((self.docs[j].get("effective_date") or "9999") <= as_of
                       for j in fut):
                    s *= 0.3
            scores[i] = s

        # ── 뜻 점수 섞기 ────────────────────────────────────────────
        # 글자 점수(BM25)는 상한이 없어 그대로 더할 수 없다. 그래서 각각
        # 자기 최고점 기준으로 0~1 로 맞춘 뒤 가중치를 두고 합친다.
        # 벡터가 아직 없는 조각(만드는 중)은 글자 점수만으로 겨룬다.
        if self.vecs is not None and scores:
            qv = embed_query(query)
            if qv:
                import numpy as np
                q = np.asarray(qv, dtype="float32")
                q /= (np.linalg.norm(q) or 1)
                # 글자 점수 상위 200개 + 뜻으로 가까운 상위 200개를 후보로 본다.
                # 전체를 곱하면 3만 줄이라 느리지만, 이 정도면 0.01초다.
                sims = self.vecs @ q
                sims[~self.have] = -1
                top_sem = np.argpartition(-sims, min(200, len(sims) - 1))[:200]
                bm_max = max(scores.values()) or 1
                merged = {}
                # 뜻으로만 걸린 후보에도 같은 잣대를 댄다.
                # 안 그러면 수소 질문에 액법 조각이 옆문으로 들어온다.
                extra = set()
                for x in top_sem:
                    x = int(x)
                    if sims[x] <= 0 or x in scores:
                        continue
                    d = self.docs[x]
                    if country and d["country"] != country:
                        continue
                    if want_gas:
                        dg = gas_of(f"{d['law']} {d['title']}")
                        if dg and not (dg & want_gas):
                            continue
                    if d.get("kind") == "별지서식":
                        continue
                    extra.add(x)
                for i in set(scores) | extra:
                    bm = scores.get(i, 0.0) / bm_max
                    # 코사인은 그 자체로 0~1 눈금이다. 최고점으로 다시 나누면
                    # 어쩌다 걸린 조각 하나가 만점이 되어 버린다.
                    sem = max(float(sims[i]), 0.0) if self.have[i] else 0.0
                    merged[i] = (1 - EMB_WEIGHT) * bm + EMB_WEIGHT * sem
                # 화면에 보이는 점수는 원래 눈금(0~100대)에 맞춰 되돌린다.
                scores = {i: v * bm_max for i, v in merged.items()}

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])

        # ── 재순위(크로스인코더) ───────────────────────────────────
        # 글자·뜻 점수는 질문과 조각을 따로 숫자로 만들어 견준다. 재순위 모델은
        # 둘을 한 번에 읽고 "이 조각이 이 질문의 답인가"를 직접 매긴다. 느려서
        # 상위 후보에만 건다. 켜져 있지 않거나 모델이 없으면 그대로 지나간다.
        use_rr = RERANK_ON if rerank is None else rerank
        if use_rr and ranked:
            try:
                import rerank as _rr
                cand = ranked[:RERANK_N]
                rs = _rr.score(query, [self.docs[i] for i, _ in cand])
                if rs is not None:
                    top = max(s for _, s in cand) or 1
                    # 원래 점수 눈금을 지키려고, 재순위 결과는 순서만 바꾼다.
                    # (화면의 '점수 40 미만 = 자료 없음' 판단이 그대로 살아야 한다)
                    order = sorted(range(len(cand)), key=lambda k: -rs[k])
                    vals = sorted((s for _, s in cand), reverse=True)
                    ranked = [(cand[k][0], vals[r]) for r, k in enumerate(order)] \
                        + ranked[RERANK_N:]
                    scores = dict(ranked)
            except Exception:
                pass

        best = ranked[:top_k]
        picked = [i for i, _ in best]
        out = [dict(self.docs[i], score=round(s, 2)) for i, s in best]
        # 기준일에 이미 시행된 개정판은 '예정'이 아니라 '현행'으로 보인다.
        if as_of:
            for o in out:
                if o.get("future") and (o.get("effective_date") or "9999") <= as_of:
                    o["future"] = False
                    o["revised"] = o.get("effective_date")

        # 개정 내용을 물었으면 예정판 옆에 현행판을 나란히 붙인다(비교용).
        if want_change:
            for i, _ in best[:4]:
                d = self.docs[i]
                if not d.get("future"):
                    continue
                for c in self.current_of.get((law_key(d["law"]), d["article"]), ())[:1]:
                    if c not in picked:
                        picked.append(c)
                        out.append(dict(self.docs[c], score=round(scores.get(c, 0), 2),
                                        pair_of=d["article"]))

        # 우산 개념(규제특례 = 실증특례 + 임시허가 + 신속확인)은 한 조문에 다 없다.
        # 하나만 걸리면 답이 "두 가지"로 좁아진다(실측: 신속확인 누락). 갈래마다
        # 따로 찾아 각각의 1등을 반드시 넣는다.
        # 갈래 검색은 안쪽에서 다시 갈래를 타지 않는다("완성검사" 안에 "검사"가 있어
        # 끝없이 되풀이됐다 — 실측으로 채점이 5분 넘게 안 끝났다).
        for key, subs in ([] if _inner else BUNDLES.items()):
            if key not in query:
                continue
            for sub in subs:
                if any(sub.replace(" ", "") in (self.docs[i]["title"] + self.docs[i]["content"][:200]).replace(" ", "")
                       for i in picked):
                    continue
                for h in self.search(sub, top_k=1, country=country, rerank=False, _inner=True):
                    j = next((k for k, d in enumerate(self.docs)
                              if d["law"] == h["law"] and d["article"] == h["article"]), None)
                    if j is not None and j not in picked:
                        picked.append(j)
                        out.append(dict(self.docs[j], score=round(scores.get(j, h["score"] * 0.5), 2),
                                        bundle=key))

        # 뽑힌 조문이 부르는 다른 조문을 붙인다("제10조의3에 따른 특례" → 제10조의3).
        # 정의·요건이 다른 조문에 있는 경우가 많아, 이게 없으면 답이 반쪽이 된다.
        for i, _ in best[:3]:
            for j in self.xrefs_of(i):
                if j not in picked:
                    picked.append(j)
                    out.append(dict(self.docs[j], score=round(scores.get(j, 0), 2),
                                    xref_from=self.docs[i]["article"]))

        # 뽑힌 조문이 부르는 별표를 뒤에 붙인다(질문과 가장 가까운 조각 우선).
        for i, _ in best[:5]:
            d = self.docs[i]
            if d.get("kind"):                     # 이미 별표면 건너뛴다
                continue
            cand = self.linked.get((law_key(d["law"]), d["article"]), [])
            cand = [c for c in cand if c not in picked]
            for c in sorted(cand, key=lambda c: -scores.get(c, 0))[:2]:
                picked.append(c)
                out.append(dict(self.docs[c], score=round(scores.get(c, 0), 2),
                                linked_from=d["article"]))
        return out


_index = None


def get_index():
    global _index
    if _index is None:
        _index = Index(load_docs())
    return _index


if __name__ == "__main__":
    import sys
    idx = get_index()
    print(f"{len(idx.docs)}개 조문 색인 완료")
    q = " ".join(sys.argv[1:]) or "수소충전소 설치 허가"
    for r in idx.search(q, top_k=5):
        print(f"\n[{r['score']}] {r['country']} {r['law']} {r['article']}({r['title']})")
        print(r["content"][:200].replace("\n", " "))
