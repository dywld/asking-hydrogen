#!/usr/bin/env python3
"""수소시설 인허가 가이드 챗봇 — MVP.

구조: 질문 → BM25로 법령 조문 검색(무료·즉시) → 제미나이가 조문만 보고 답변.
API 키가 없어도 검색 결과는 그대로 보여준다(키 없이 화면 확인이 가능해야 해서).
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import distance
import facts
import forms
import ollama_fallback
import search

# ── 발표 잠금 ─────────────────────────────────────────────────────
# demo_prepare.py 로 미리 돌려 사람이 확인(approved: true)한 답만 그대로 내보낸다.
# BOT_DEMO_LOCK=1 이면 그 질문에는 모델을 부르지 않는다. 다른 질문은 평소대로.
DEMO_FILE = Path(__file__).parent / "data" / "demo_answers.json"
DEMO_LOCK = os.environ.get("BOT_DEMO_LOCK", "0") == "1"
# 답변 뒤 다른 모델이 문장마다 근거 유무를 채점한다. 발표 모드에서는 항상, 평소에는 BOT_JUDGE=1 일 때.
JUDGE_ALWAYS = os.environ.get("BOT_JUDGE", "0") == "1"
JUDGE_MODEL = os.environ.get("BOT_JUDGE_MODEL", "gemini-3.1-flash-lite")

HERE = Path(__file__).parent

# ── 답변 캐시 ─────────────────────────────────────────────────────
# 같은 질문이 다시 오면 제미나이를 부르지 않고 저장해 둔 답을 그대로 흘린다.
# 하루 무료 한도를 아끼고, 발표 때 미리 던져 본 질문은 0.1초에 뜬다.
# 첫 질문(앞 대화가 없는 것)만 저장한다. 이어지는 질문은 앞 얘기에 따라 답이 달라서.
CACHE_FILE = HERE / "data" / "answer_cache.json"
CACHE_TTL = int(os.environ.get("BOT_CACHE_DAYS", "30")) * 86400
CACHE_MAX = 2000
_cache = {}
_cache_lock = threading.Lock()


def _cache_load():
    global _cache
    try:
        if CACHE_FILE.exists():
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        _cache = {}


def _cache_key(q, country, facility, as_of, checklist):
    norm = re.sub(r"[\s?？!.~,]+", "", q).lower()
    raw = f"{norm}|{country or ''}|{facility or ''}|{as_of or ''}|{int(bool(checklist))}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def cache_get(key):
    rec = _cache.get(key)
    if not rec:
        return None
    if time.time() - rec.get("ts", 0) > CACHE_TTL:
        with _cache_lock:
            _cache.pop(key, None)
        return None
    return rec


def cache_put(key, rec):
    with _cache_lock:
        rec["ts"] = time.time()
        _cache[key] = rec
        if len(_cache) > CACHE_MAX:              # 오래된 것부터 버린다
            for k in sorted(_cache, key=lambda k: _cache[k].get("ts", 0))[:200]:
                _cache.pop(k, None)
        try:
            CACHE_FILE.parent.mkdir(exist_ok=True)
            CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False),
                                  encoding="utf-8")
        except Exception:
            pass                                 # 저장 실패가 답변을 막으면 안 된다


# ── 피드백 ───────────────────────────────────────────────────────
# 답변마다 👍👎. 👎 는 정답셋 후보가 된다(eval_candidates.py 가 읽는다).
FEEDBACK = HERE / "data" / "feedback.jsonl"

# ── 예열 ─────────────────────────────────────────────────────────
# 자주 묻는 질문을 서버가 뜰 때 미리 돌려 캐시에 넣는다. 발표 때 첫 질문이 0.2초에 뜬다.
# BOT_WARM=1 이면 warm_questions.txt 의 질문을 한 줄씩(느리게) 돌린다. 무료 한도를 쓴다.
WARM_FILE = HERE / "warm_questions.txt"
WARM = os.environ.get("BOT_WARM", "0") == "1"


def warm_cache(port):
    """자기 자신에게 질문을 던져 캐시를 채운다. 실패해도 조용히 넘어간다."""
    if not WARM_FILE.exists():
        return
    time.sleep(3)
    for q in [l.strip() for l in WARM_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]:
        if cache_get(_cache_key(q, None, None, None, bool(CHECKLIST_RE.search(q)))):
            continue
        try:
            body = json.dumps({"messages": [{"role": "user", "text": q}]}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                for _ in r:
                    pass
        except Exception:
            pass
        time.sleep(5)                              # 분당 한도를 안 건드리게


# ── 되묻기 ───────────────────────────────────────────────────────
# 조건이 빠진 수치 질문("안전거리?")은 답을 주되, 조건을 고르는 단추를 함께 준다.
CLARIFY = [
    (re.compile(r"(안전거리|이격거리|떨어져)"), re.compile(r"\d|제조식|저장식|저장설비|산소"),
     "처리·저장능력과 방식을 알려주면 표의 정확한 칸을 짚어 드립니다.",
     ["제조식 수소충전소 처리능력 1만 이하 안전거리는?",
      "저장식 수소충전소 처리능력 3만 안전거리는?",
      "고압가스 저장설비(가연성) 저장능력 2만 안전거리는?"]),
    (re.compile(r"(수수료|비용이 얼마)"), re.compile(r"(제조|저장소|판매|변경|등록|재발급|수소용품)"),
     "어떤 허가·등록의 수수료인지 고르면 그 값만 드립니다.",
     ["고압가스 제조허가 수수료는?", "저장소 설치허가 수수료는?", "수소용품 제조사업 허가 수수료는?"]),
    (re.compile(r"(처벌|벌금|벌칙)"), re.compile(r"(허가 없이|무허가|신고 없이|손괴|안전관리자|미선임)"),
     "무엇을 위반한 경우인지 고르면 해당 조문만 드립니다.",
     ["허가 없이 제조하면 처벌은?", "신고 없이 제조하면 처벌은?", "안전관리자를 선임하지 않으면?"]),
]


def clarify_for(q):
    for need, has, text, opts in CLARIFY:
        if need.search(q) and not has.search(q):
            return {"type": "clarify", "text": text, "options": opts}
    return None


# ── 대화 공유 ─────────────────────────────────────────────────────
# 답변을 서버에 저장하고 짧은 주소(/s/아이디)로 연다. 멘토·팀원에게 결과를 보여줄 때.
SHARE_DIR = HERE / "data" / "shares"
SHARE_MAX_BYTES = 400_000

# ── PDF 원문 페이지 ──────────────────────────────────────────────
# KGS Code 조각 끝에는 원본 PDF 의 쪽 번호가 붙어 있다("KGS FP216 2025 8").
# PDF 가 있는 서버(BOT_PDF_DIR)에서는 그 쪽을 그림으로 잘라 보여준다. 없으면 버튼이 안 뜬다.
PDF_DIR = Path(os.environ.get("BOT_PDF_DIR") or (Path.home() / "Desktop" / "KGS_Code"))
PAGE_DIR = HERE / "data" / "pages"
PAGE_RE = re.compile(r"KGS\s+([A-Z]{2}\d{3})\s+\d{4}\s+(\d+)\s*$")


def pdf_page_of(doc):
    """KGS 조각 → (코드, 쪽 번호). 못 찾으면 None."""
    if doc.get("kind") != "상세기준":
        return None
    m = PAGE_RE.search(doc.get("content", "").rstrip())
    return (m.group(1), int(m.group(2))) if m else None


def pdf_file_of(code):
    if not PDF_DIR.exists():
        return None
    for p in PDF_DIR.glob(f"{code}_*.pdf"):
        return p
    return None


def render_page(code, page):
    """PDF 한 쪽을 PNG 로. 만든 것은 파일로 남겨 두 번째부터는 바로 준다."""
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    out = PAGE_DIR / f"{code}_{page}.png"
    if out.exists():
        return out.read_bytes()
    pdf = pdf_file_of(code)
    if not pdf:
        return None
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        if page < 1 or page > len(doc):
            return None
        pix = doc[page - 1].get_pixmap(dpi=110)
        data = pix.tobytes("png")
        out.write_bytes(data)
        return data
    except Exception:
        return None
# 서버(오라클)에서는 BOT_PORT·BOT_HOST 를 환경변수로 준다.
# 로컬에서는 그냥 8000/내부 접속만.
PORT = int(os.environ.get("BOT_PORT") or 8000)
HOST = os.environ.get("BOT_HOST") or "127.0.0.1"

# 무료 한도(2026-08 실측, AI Studio 대시보드 기준)
#   gemini-3.7-flash      분당 5 · 하루  20   ← 제일 똑똑, 아껴 쓴다
#   gemini-2.5-flash      분당 5 · 하루  20
#   gemini-3-flash        분당 5 · 하루  20
#   gemini-3.1-flash-lite 분당 15 · 하루 500  ← 평소 테스트는 이걸로
#
# 하루 20번은 개발 중에 반나절이면 동난다. 그래서 평소(daily)와
# 발표(demo)를 나눠 두고, 앞 모델이 막히면 자동으로 뒤로 넘어간다.
# 무료 한도는 모델마다 따로 센다. 그래서 앞이 막히면 다음으로 넘어가면 살아난다.
# 목록은 실제로 불러서 확인한 것만 넣는다 — 'gemini-3-flash' 는 존재하지 않는
# 이름이라 404 가 났고, 그 자리가 한 칸 죽어 있었다(실측).
# 순서: 가벼운 것 먼저(평소) / 좋은 것 먼저(발표).
MODEL_SETS = {
    "daily": ["gemini-3.1-flash-lite", "gemini-flash-lite-latest",
              "gemini-3.5-flash-lite", "gemini-2.5-flash-lite",
              "gemini-3.5-flash", "gemini-3.6-flash",
              "gemini-3-flash-preview", "gemini-2.5-flash",
              "gemini-3.7-flash"],
    "demo":  ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
              "gemini-2.5-flash", "gemini-3-flash-preview",
              "gemini-3.1-flash-lite", "gemini-3.5-flash-lite",
              "gemini-flash-lite-latest", "gemini-2.5-flash-lite"],
}
MODE = os.environ.get("BOT_MODE", "daily")      # daily | demo

# 서버에 올리면 주소를 아는 사람은 누구나 쓸 수 있고, 그만큼 무료 한도가 샌다.
# 코드가 설정돼 있으면 맞는 사람만 답변을 받는다(로컬에서는 비워 두면 그대로 열린다).
ACCESS_CODE = os.environ.get("BOT_CODE", "").strip()

# 코드를 없앤 대신 두는 안전장치. 주소를 아는 사람은 누구나 쓸 수 있으므로,
# 한 사람이 몰아 쓰면 하루 무료 한도(약 560회)가 순식간에 빈다.
# 사람이 대화하는 속도로는 걸릴 일이 없는 선(시간당 30회)으로 잡는다.
RATE_PER_HOUR = int(os.environ.get("BOT_RATE", "30"))
_hits = {}


def rate_ok(ip):
    if RATE_PER_HOUR <= 0:                   # BOT_RATE=0 이면 제한 없음(로컬 시험용)
        return True
    if ip in ("127.0.0.1", "::1"):            # 같은 컴퓨터의 채점기는 세지 않는다(실측: 55문항 채점이 30번째에서 429)
        return True
    now = time.time()
    q = [t for t in _hits.get(ip, []) if now - t < 3600]
    if len(q) >= RATE_PER_HOUR:
        _hits[ip] = q
        return False
    q.append(now)
    _hits[ip] = q
    if len(_hits) > 500:                     # 오래된 기록은 버린다
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
            _hits.pop(k, None)
    return True
MODELS = MODEL_SETS[MODE]
MODEL = MODELS[0]
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

SYSTEM = """당신은 수소시설 인허가 실무를 돕는 상담원입니다.

질문은 두 갈래입니다. 먼저 어느 쪽인지 정하고 답합니다.
① 수치를 묻는 질문(거리·용량·기간·금액 등):
- 조문에 수치나 표가 있으면 그 값을 그대로 옮겨 적습니다. 표는 표로 만듭니다.
- "별표 8에서 정한 거리 이상", "기준에 적합해야 합니다" 처럼 가리키기만 하는 답변은 금지입니다.
  자료에 표가 들어와 있는데도 이렇게 답하면 잘못된 답변입니다.
- 자료에 그 수치가 정말 없을 때만 "제공된 자료에는 수치가 없습니다"라고 밝힙니다.
② 절차·주체·종류를 묻는 질문(누가·어디에·무엇을·어떻게):
- 첫 줄은 결론 한 문장입니다. 예) "시장·군수·구청장에게 제조허가를 받아야 합니다."
- 수치가 없다는 말로 시작하지 않습니다. 묻지 않은 수치는 없어도 됩니다.

답변 형식:
- 첫 문단은 사람에게 말하듯 2~3문장입니다. 결론과 근거 하나만. 제목·번호·표를 여기 두지 않습니다.
- 그 뒤에 필요할 때만 항목(5개 이내)이나 표를 붙입니다. 수치가 여럿일 때는 표가 맞습니다.
- 조문 문장을 그대로 베껴 쓰지 않고 실무자 말로 줄입니다. 예외·단서는 짧게 한 줄씩만.
- 전체 길이는 질문의 크기에 맞춥니다. 한 줄로 끝날 질문은 한 줄로 끝냅니다.

답변이 끝나면 마지막에 이어질 만한 질문 3개를 답니다:
- 형식은 정확히 아래와 같습니다. 이 표시가 없으면 화면에 버튼이 뜨지 않습니다.
###다음질문
- (질문 1)
- (질문 2)
- (질문 3)
- 방금 답변에서 자연스럽게 이어지는 것, 실무자가 다음에 궁금해할 것으로 만듭니다.
- 짧은 한 문장, 20자 안팎으로 씁니다. 이미 답한 내용은 다시 묻지 않습니다.

정확성:
- 제시된 자료에 있는 내용만 씁니다. 조문·별표 번호를 지어내지 않습니다.
- 사실을 담은 문장마다 문장 끝에 자료 번호를 [3] 처럼 답니다(자료 목록의 [n] 번호).
  표에서는 각 행의 마지막 칸이나 표 바로 아래에 답니다. 번호가 없는 사실 문장은
  근거 없는 문장으로 취급되어 화면에서 지워지니, 반드시 답니다.
- "확정 자료"라고 표시된 조각의 값은 그대로 옮겨 적습니다. 다른 조각과 값이 다르면 확정 자료를 따릅니다.
- 조문·별표를 이름으로 부를 때는 [법령명 별표 8], [법령명 제8조], [KGS FP216 2.1.1.1] 형식으로 답니다.
- 일본 조문도 같은 형식으로, 조문 번호는 아라비아 숫자로 답니다. 第七条 → [일본 수소사회추진법 제7조].
  법령명이 길면 줄여 써도 되지만 조문 번호는 반드시 답니다.
- KGS Code(상세기준)는 법이 별표로, 별표가 다시 넘긴 최종 기준입니다.
  같은 사항에 법·별표·KGS Code 가 함께 있으면 KGS Code 의 수치를 우선해 답합니다.
- 일본어 조문은 한국어로 옮겨 설명합니다.
- 시행 예정 조문은 "○○부터 시행 예정"이라고 덧붙입니다."""


def api_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    f = HERE / "key.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return ""


def build_context(hits, groups=None):
    """모델에게 주는 자료. groups 가 있으면 화면의 근거 번호와 같은 [n] 을 붙인다.

    번호가 화면과 같아야 답변의 [3] 이 근거 카드 3번을 가리킨다.
    """
    num = {}
    if groups:
        num = {(g["law"], g["ref"]): g["n"] for g in groups}
    parts = []
    for i, h in enumerate(hits, 1):
        n = num.get((h["law"], article_ref(h["article"])), i)
        tag = ""
        if h["future"]:
            tag = f" (시행 예정: {h['effective_date']})"
        elif h.get("revised"):
            tag = f" (개정판, {h['revised']} 시행)"
        elif h.get("pair_of"):
            tag = " (현행판 — 개정 전 내용, 비교용)"
        elif h.get("kind") == "별지서식":
            tag = " (별지 서식 — 제출 서류 이름과 용도)"
        elif h.get("kind") == "확정":
            tag = " ★확정 자료 — 이 값을 그대로 인용"
        parts.append(f"[{n}] {h['country']} · {h['law']} {h['article']}"
                     f"({h['title']}){tag}\n{h['content']}")
    return "\n\n".join(parts)


# ── 자기교정 · 삭제 · 이중 검사 ─────────────────────────────────
# 검증에서 어긋난 표기가 나오면 (1) 모델에게 고치게 하고 (2) 그래도 남으면 그 줄을 지운다.
# 틀린 숫자를 '경고 딱지'만 붙여 내보내는 것과, 아예 안 내보내는 것은 다르다.
CORRECT_PROMPT = """아래 답변에서 표시된 수치·조문 번호는 제시된 자료에 없습니다.
자료에 있는 값으로 고치거나, 자료에 없으면 그 문장을 빼십시오. 새 수치를 만들지 마십시오.
형식·문체·길이는 그대로 두고, 고친 답변 전문만 출력합니다(설명 없이). '###다음질문' 블록도 그대로 둡니다.

=== 자료에 없는 표기 ===
{bad}

=== 자료 ===
{context}

=== 답변 ===
{answer}"""


def correct_answer(model, answer, context, bad, key):
    """어긋난 표기를 모델에게 고치게 한다. 실패하면 None."""
    prompt = CORRECT_PROMPT.format(bad=", ".join(bad), context=context, answer=answer)
    text, err = call_model(model, prompt, key)
    if not text or len(text.strip()) < 40:
        return None
    return text


SENT_SPLIT = re.compile(r"(?<=[.다요])\s+(?=[가-힣A-Z(\[「])")


def strip_unverified(body, bad):
    """어긋난 표기가 든 줄·문장을 지우고 그 자리를 한 줄로 알린다."""
    if not bad:
        return body, []
    pat = re.compile("|".join(re.escape(b).replace(r"\ ", r"\s*") for b in bad))
    removed = []
    out_lines = []
    for line in body.split("\n"):
        if not pat.search(line):
            out_lines.append(line)
            continue
        if line.lstrip().startswith("|"):            # 표는 그 행만 뺀다
            removed.append(line.strip())
            continue
        kept = []
        for s in SENT_SPLIT.split(line):
            if pat.search(s):
                removed.append(s.strip())
            elif re.fullmatch(r"[\s\[\]\d,.]*", s):
                continue                          # 문장을 지우고 남은 '[3], [6].' 조각
            else:
                kept.append(s)
        if kept:
            out_lines.append(" ".join(kept))
    if removed:
        out_lines.append("\n(근거 조문에서 확인되지 않아 뺀 내용이 "
                         f"{len(removed)}곳 있습니다. 원문을 직접 확인해 주세요.)")
    return "\n".join(out_lines).strip(), removed


JUDGE_PROMPT = """당신은 검수자입니다. 아래 '자료'만 보고, '답변'의 각 문장이 자료로 뒷받침되는지 판정합니다.
자료에 없는 내용, 자료와 다른 수치·주체·조문이 든 문장은 '불일치'입니다.
일반적인 안내 문장("확인해 주세요")이나 자료 번호만 있는 줄은 판정하지 않습니다.
출력은 불일치 문장의 번호만 JSON 배열로. 예: [2, 5]  없으면 []

=== 자료 ===
{context}

=== 답변(문장 번호) ===
{numbered}"""


def pick_judge(answer_model):
    """검수는 답변과 다른 계열 모델이 한다. 같은 모델은 같은 착각을 같이 통과시킨다."""
    if os.environ.get("BOT_JUDGE_MODEL"):
        return JUDGE_MODEL
    return "gemini-2.5-flash" if answer_model.startswith("gemini-3") else "gemini-3.1-flash-lite"


CITE_ANY = re.compile(r"\[\d{1,2}(?:\s*,\s*\d{1,2})*\]|\[[^\[\]\n]{2,70}?(?:제\d+조|별표\s*\d|KGS\s*[A-Z]{2}\d{3})[^\[\]\n]*\]")
FACTY = re.compile(r"\d|조문|별표|서식|허가|신고|검사|공사|장관|구청장|이내|이상|이하")


def uncited_sentences(body):
    """근거 번호도 조문 이름도 없는 사실 문장. 화면에서 회색으로 보인다(지우지는 않는다)."""
    out = []
    for line in body.split("\n"):
        s0 = line.strip()
        if not s0 or s0.startswith(("|", "#", "(근거", "•", "*", "-")) and "|" in s0:
            continue
        if s0.startswith("|"):                    # 표 행은 행 전체에 번호 하나면 된다
            # 머리글·구분선 행은 사실이 아니다. 숫자가 든 행만 본다.
            if re.search(r"\d", s0) and not re.fullmatch(r"[\s|:\-]+", s0) and not CITE_ANY.search(s0):
                out.append(s0)
            continue
        for s in SENT_SPLIT.split(line):
            s = s.strip().lstrip("•*- ")
            if len(s) > 12 and FACTY.search(s) and not CITE_ANY.search(s) and not s.endswith(("?", "：", ":")):
                out.append(s)
    return out[:30]


def judge_answer(body, context, key, answer_model=""):
    """다른 호출로 문장마다 근거 유무를 채점한다. (불일치 문장 목록) 또는 None."""
    sents = [s.strip() for line in body.split("\n") for s in SENT_SPLIT.split(line)
             if len(s.strip()) > 8 and not s.strip().startswith(("|", "#", "(근거"))]
    if not sents:
        return None
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sents[:40]))
    text, err = call_model(pick_judge(answer_model),
                           JUDGE_PROMPT.format(context=context, numbered=numbered), key)
    if not text:
        return None
    m = re.search(r"\[[\d,\s]*\]", text)
    if not m:
        return None
    try:
        idxs = json.loads(m.group(0))
    except ValueError:
        return None
    return [sents[i - 1] for i in idxs if isinstance(i, int) and 1 <= i <= len(sents)]


def demo_lookup(q):
    """발표 잠금 — 승인된 답만. 없으면 None."""
    if not DEMO_LOCK or not DEMO_FILE.exists():
        return None
    try:
        data = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    key = re.sub(r"[\s?？!.~,]+", "", q).lower()
    rec = data.get(key)
    return rec if rec and rec.get("approved") else None


def call_model(model, prompt, key):
    """한 모델에 한 번 물어본다. (성공 텍스트, 오류코드) 를 돌려준다."""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        # 법령 답변에서 창의성은 해가 된다. 온도를 낮춰 조문에 붙어 있게 한다.
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/{model}:generateContent?key={key}", data=body,
        headers={"Content-Type": "application/json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return None, (e.code, e.read().decode("utf-8", "replace")[:200])
    except Exception as e:
        return None, (0, str(e))
    try:
        parts = d["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts), None
    except Exception:
        return None, (0, json.dumps(d, ensure_ascii=False)[:200])


def ask_gemini(question, context, key):
    prompt = (f"{SYSTEM}\n\n=== 검색된 법령 조문 ===\n{context}\n\n"
              f"=== 질문 ===\n{question}")
    last = None
    for model in MODELS:
        # 503(붐빔)·429(한도)는 잠깐 뒤 같은 모델이 풀리는 경우가 많아 두 번 시도한다.
        for attempt in range(2):
            text, err = call_model(model, prompt, key)
            if text:
                return text
            last = (model, err)
            # 429(한도 소진)는 같은 모델을 다시 불러도 소용없다. 바로 다음 모델로.
            # 503(붐빔)만 잠깐 쉬었다 한 번 더 해본다.
            if err[0] in (503, 500, 0):
                time.sleep(2 * (attempt + 1))
                continue
            break  # 429(한도)·400·403(키 오류)은 재시도해도 똑같다
    model, (code, detail) = last
    if code == 400 or code == 403:
        return f"[API 키 문제 {code}] {detail}"
    return ("지금 구글 서버가 붐벼서 답변을 못 받았습니다(모두 재시도 실패).\n"
            "아래 근거 조문은 정상적으로 찾았습니다. 잠시 뒤 다시 질문해 주세요.\n\n"
            f"마지막 오류: {model} → {code} {detail}")


# ── 질의 재작성 ──────────────────────────────────────────────────
# 단어가 겹치는 걸 찾는 방식이라, 실무자 말투("규제특례 언제 신청해?")로는
# 엉뚱한 조문이 1등으로 올라온다(실측: 건축법 '규제의 재검토').
# 그래서 검색 전에 가벼운 모델로 법령 용어를 뽑아 붙인다. 실패하면 원문 그대로 쓴다.
REWRITE_MODEL = "gemini-3.1-flash-lite"
REWRITE_PROMPT = """다음 질문을 한국 법령 검색어로 바꿔줘.
- 법령에서 실제 쓰는 용어만 공백으로 나열. 설명·문장 금지.
- 8단어 이내. 질문에 없는 법령명은 지어내지 마.
예) "규제특례 언제 신청해?" -> 규제특례 실증특례 규제자유특구 신청 요건 특례
질문: """

_rewrite_cache = {}

# ── 체크리스트 모드 ──────────────────────────────────────────────
# "충전소 지을 건데 뭐가 필요해?" 에는 문장 답변보다 표가 맞다.
# 허가·신고·검사를 순서대로 놓고, 근거·제출 서식·관할을 칸으로 나눈다.
CHECKLIST_RE = re.compile(
    r"(체크리스트|뭐가 필요|무엇이 필요|뭐뭐 필요|어떤 (허가|서류|절차|신고)|"
    r"필요한 (허가|서류|절차|신고)|전체 절차|처음부터|순서대로|단계별)")

CHECKLIST_SYSTEM = """
[체크리스트 모드]
이번 질문은 인허가 전체 흐름을 묻는 것입니다. 아래 형식으로 답합니다.
1) 첫 줄: 결론 한 문장(어떤 법의 어떤 허가가 핵심인지).
2) 그 다음 표. 열은 정확히 이 다섯 개: | 단계 | 해야 할 것 | 근거 | 제출 서류 | 어디에 |
   - 단계: 사업 준비 → 허가 → 시공 → 검사 → 운영 순서로 번호를 매깁니다.
   - 해야 할 것: 허가·신고·기술검토·완성검사·안전관리자 선임 같은 행위.
   - 근거: [법령명 제○조] 형식. 자료에 있는 조문만.
   - 제출 서류: 자료의 별지 서식 이름과 호수(예: 별지 제1호서식 제조허가신청서). 없으면 "-".
   - 어디에: 허가관청(시장·군수·구청장), 한국가스안전공사 등. 자료에 없으면 "-".
3) 표 아래에 주의할 점을 3줄 이내로.
자료에 없는 단계를 상식으로 채우지 않습니다. 자료에 없으면 그 칸은 "-" 로 둡니다."""


def rewrite_query(question, key):
    if not key or len(question) < 4:
        return question
    if question in _rewrite_cache:
        return _rewrite_cache[question]
    if len(_rewrite_cache) > 2000:            # 서버가 오래 떠 있어도 메모리가 안 늘게
        _rewrite_cache.clear()
    body = json.dumps({
        "contents": [{"parts": [{"text": REWRITE_PROMPT + question}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 300},
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/{REWRITE_MODEL}:generateContent?key={key}", data=body,
        headers={"Content-Type": "application/json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=20))
        parts = d["candidates"][0]["content"]["parts"]
        terms = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        return question                     # 한도·오류 시 원래 질문으로 검색
    terms = " ".join(terms.split())[:120]
    # 법령과 무관한 질문에는 모델이 "변환할 수 없습니다" 같은 문장을 돌려준다.
    # 그걸 검색어에 섞으면 엉뚱한 조문이 걸리므로 버린다.
    if "없습니다" in terms or "않습니다" in terms or len(terms) > 90:
        terms = ""
    # 원문도 같이 넣는다. 재작성이 엉뚱해도 원래 단어로는 걸리게.
    out = f"{question} {terms}" if terms else question
    _rewrite_cache[question] = out
    return out


# 인사·감사·시험 입력. 법령 검색 없이 안내만 돌려준다.
SMALLTALK = re.compile(
    r"^\s*(안녕|하이|헬로|반가|고마워|고맙|감사|수고|잘가|ㅎㅎ|ㅋㅋ|테스트|test|hello|hi|hey|ok|응|네|넵|굿)")

# 자기소개·사용법 질문. 법령이 아니라 이 도구에 대한 물음이다.
META = re.compile(
    r"(정체|누구야|누구니|넌 뭐|너는 뭐|너 뭐|무슨 봇|어떤 봇|뭐 하는|뭘 할 수|뭐 할 수|무엇을 할 수|"
    r"어떻게 쓰|사용법|어떻게 사용|자기소개|소개해|누가 만들|어떤 자료|무슨 자료|자료가 뭐|뭘 알아|뭐 알아)")

INTRO = (
    "저는 수소시설 인허가를 돕는 법령 검색 챗봇입니다.\n\n"
    "질문을 받으면 국내외 법령 32,217조각(한국 법령 본문 · 별표 · KGS Code 상세기준 · 일본 법령)에서 "
    "관련 조문을 찾아, 그 조문만 읽고 답합니다. 답변에는 근거 번호가 붙고, 수치와 조문 번호는 "
    "근거와 대조해 확인되지 않은 것은 표시하거나 뺍니다. 자료에 없는 내용은 없다고 말합니다.\n\n"
    "할 수 있는 것: 허가 종류·절차, 안전거리·시설기준 수치, 검사·안전관리자, 규제특례, 벌칙·과태료, "
    "기준일에 따른 개정 전후 비교, 안전거리 계산기(오른쪽 위).\n"
    "참고용 안내이며 실제 인허가는 관할 관청과 원문을 확인해 주세요.")

FOLLOW_MARK = "###다음질문"
# 모델이 '### 다음질문' 처럼 띄어 쓰기도 한다. 그대로 두면 표시가 답변에 섞여 나온다.
FOLLOW_RE = re.compile(r"#{2,4}\s*다음\s*질문\s*")


def split_followups(text):
    """답변 본문과 '다음 질문' 블록을 가른다. (본문, 시작위치)"""
    m = FOLLOW_RE.search(text)
    return (text[:m.start()], m.start()) if m else (text, -1)


def parse_followups(text):
    """답변 꼬리에 붙은 '다음 질문' 3개를 뽑아낸다."""
    m = FOLLOW_RE.search(text)
    if not m:
        return []
    out = []
    for line in text[m.end():].splitlines():
        line = line.strip().lstrip("-*•").strip()
        line = re.sub(r"^\d+[.)]\s*", "", line).strip()
        # 모델이 예시 형식을 따라 '(질문 1)' 처럼 쓰는 경우가 있다.
        # 통째로 감싼 것도, 앞에만 붙인 것도 둘 다 걷어낸다.
        if line.startswith("(") and line.endswith(")"):
            line = line[1:-1].strip()
        line = re.sub(r"^\(?\s*질문\s*\d*\s*\)?\s*", "", line).strip()
        if 4 <= len(line) <= 60:
            out.append(line)
    return out[:3]



# ── 답변 검증 ────────────────────────────────────────────────────
# 근거를 넣어줘도 모델은 가끔 없는 수치를 만든다. 법령 답변에서 이건 치명적이라,
# 답변에 나온 숫자와 조문 번호가 실제로 근거 안에 있는지 기계적으로 대조한다.
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:m|㎡|㎥|kg|㎏|톤|일|개월|년|원|%|미터|퍼센트)")
# 주체(기관)도 대조한다. "산업통상부장관에게 신청"처럼 주체를 바꿔 말하는 오답은 수치 검사로는 안 잡힌다.
ORG_RE = re.compile(
    r"(한국가스안전공사|산업통상(?:자원)?부장관|기후에너지환경부장관|중소벤처기업부장관|국토교통부장관|"
    r"환경부장관|소방서장|시ㆍ도지사|시·도지사|시장ㆍ군수|시장·군수|구청장|허가관청|신고관청|등록관청|"
    r"규제자유특구위원회|규제특례심의위원회|한국산업안전보건공단|한국에너지공단|가스기술기준위원회)")
REF_RE = re.compile(r"제\d+조(?:의\d+)?|별표\s*\d+(?:의\d+)?|별지\s*제\d+호\s*서식|"
                    r"KGS\s*[A-Z]{2}\d{3}(?:\s+\d[\d.]*)?")


def article_ref(article):
    """'[별표 8] 19/30' → '[별표 8]'. 같은 별표의 조각끼리 묶는 열쇠."""
    return article[:article.index("]") + 1] if "]" in article else article


_KGS_ITEM = re.compile(r"^\[(KGS [A-Z]{2}\d{3}) (\d+\.\d+)")


def verify_key(doc):
    """검증용 묶음 열쇠. KGS 는 항목 2단계(2.7)까지 같으면 한 묶음으로 본다.

    방호벽 규격은 2.7.2.1.1 · 2.7.2.1.2 · 2.7.2.2 에 나뉘어 있는데, 검색에 하나만
    걸리면 나머지 항목의 수치가 '근거 없음'으로 지워졌다(실측: 200mm·580mm 행 삭제).
    """
    m = _KGS_ITEM.match(doc.get("article", ""))
    if doc.get("kind") == "상세기준" and m:
        return (doc["law"], m.group(1) + " " + m.group(2))
    return (doc["law"], article_ref(doc["article"]))


_SIBLINGS = None

# 일본 조문은 '第七条'인데 답변은 '제7조'로 쓴다. 그대로 대조하면 일본 답변마다
# '근거에 없는 조문 번호' 경고가 잘못 뜬다(실측). 한자 숫자를 풀어 함께 넣는다.
_KANJI = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}
_JP_ART = re.compile(r"第([〇零一二三四五六七八九十百]+)条(?:の([〇零一二三四五六七八九十]+))?")


def kanji_num(s):
    total, cur = 0, 0
    for ch in s:
        if ch == "十":
            total += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
        else:
            cur = _KANJI.get(ch, 0)
    return total + cur


def jp_refs_as_korean(text):
    """'第七条の二' → '제7조의2'. 검증용 건초더미에 덧붙인다."""
    out = []
    for m in _JP_ART.finditer(text):
        ref = f"제{kanji_num(m.group(1))}조"
        if m.group(2):
            ref += f"의{kanji_num(m.group(2))}"
        out.append(ref)
    return " ".join(out)


def siblings_of(hits):
    """검색에 걸린 조각과 같은 별표·조문에 속한 나머지 조각을 모두 가져온다.

    긴 별표는 30조각으로 잘려 들어가는데, 안전거리 표처럼 값이 몰린 부분이
    검색에 안 걸리는 일이 있다. 그러면 답변의 숫자가 실제로는 근거에 있는데도
    '확인 안 됨'으로 뜬다(별표 8 안전거리 9m·11m·13m 이 그랬다).
    검증할 때만 같은 별표 전체를 펼쳐 본다. 모델에게 주는 조각은 그대로다.
    """
    global _SIBLINGS
    if _SIBLINGS is None:
        # 다 채운 뒤에 대입한다. 스레드 둘이 동시에 들어와 반쯤 찬 사전을 읽지 않게.
        table = {}
        for d in search.get_index().docs:
            text = f"{d['article']} {d['content']}"
            if d["country"] == "일본":
                text += " " + jp_refs_as_korean(text)
            table.setdefault(verify_key(d), []).append(text)
        _SIBLINGS = table
    keys = {verify_key(h) for h in hits}
    out = []
    for k in keys:
        out.extend(_SIBLINGS.get(k, ()))
    return out


def verify(answer, hits):
    """근거에서 확인되지 않은 수치·조문번호를 찾아낸다."""
    body = split_followups(answer)[0]
    # 같은 별표의 다른 조각 + 넘긴 조각 자체(확정 자료처럼 색인에 없는 것도 있다)
    haystack = " ".join(siblings_of(hits) + [h["content"] for h in hits])
    flat = re.sub(r"\s+", "", haystack)

    bad_nums = []
    for n in dict.fromkeys(NUM_RE.findall(body)):
        if re.sub(r"\s+", "", n) not in flat:
            bad_nums.append(n)
    bad_refs = []
    for r in dict.fromkeys(REF_RE.findall(body)):
        if re.sub(r"\s+", "", r) not in flat:
            bad_refs.append(r)
    # 주체 대조. 가운뎃점 표기(ㆍ/·)가 제각각이라 지우고 견준다.
    flat_org = re.sub(r"[ㆍ·]", "", flat)
    for o in dict.fromkeys(ORG_RE.findall(body)):
        if re.sub(r"[ㆍ·\s]", "", o) not in flat_org:
            bad_refs.append(o)

    # 예전에는 3개 이상 어긋날 때만 알렸다. 이제는 하나라도 어긋나면 먼저 고치고,
    # 못 고치면 지우므로 경고는 남은 것 전부에 대해 낸다.
    warn = []
    if bad_refs:
        warn.append("근거에 없는 조문 번호: " + ", ".join(bad_refs[:5]))
    if bad_nums:
        warn.append("근거에서 확인 안 된 수치: " + ", ".join(bad_nums[:5]))
    # 경고 문구와 별개로, 어긋난 것 자체를 화면에 넘긴다.
    # 화면은 그 수치에 밑줄을 긋고, 누르면 근거로 내려가게 한다.
    return {"warnings": warn, "nums": bad_nums[:20], "refs": bad_refs[:20]}


LOG = HERE / "data" / "chat_log.jsonl"


def log_turn(rec):
    """질문·답변을 한 줄씩 남긴다.

    두 가지 용도다. 시연 중 사고가 나면 돌아볼 기록이 되고,
    어떤 질문에서 '자료에 없음'이 자주 뜨는지 보면 다음에 채울 법령이 보인다.
    """
    try:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass                      # 기록 실패가 답변을 막으면 안 된다


def group_sources(hits):
    """화면용 근거 목록. AI 에게는 조각 그대로 주고, 사람에게만 묶어서 보인다.

    한 별표를 여러 조각으로 잘라 넣다 보니 '별표 8'이 11번 나열되는 일이 생겼다.
    같은 법령·같은 별표(조문)는 하나로 합치고, 조각은 그 안에 접어 넣는다.
    """
    groups = {}
    for h in hits:
        # '[별표 8] 19/30' → '[별표 8]'. 공백으로 자르면 '[별표' 가 되어
        # 별표 4·5·8 이 한 덩어리로 뭉친다(실제로 그렇게 나왔다).
        ref = article_ref(h["article"])
        key = (h["law"], ref)
        g = groups.get(key)
        if not g:
            g = groups[key] = {
                "law": h["law"], "ref": ref, "title": h["title"],
                "country": h["country"], "score": h["score"],
                "future": h.get("future"), "effective_date": h.get("effective_date"),
                "kind": h.get("kind"), "parts": [],
            }
        g["score"] = max(g["score"], h["score"])
        g["parts"].append(h["content"])
        if h["country"] == "일본":          # 화면에서 '제7조' 인용과 짝을 맞추려고
            g["jp"] = jp_refs_as_korean(ref)

    # 원문 확인용 링크. 법령 첫 화면이 아니라 해당 조문·별표로 바로 가게 만든다.
    # 국가법령정보센터는 '/법령/법령명/제8조' 형태의 주소를 받아준다.
    for g in groups.values():
        # 특구 요약처럼 법령이 아닌 자료는 법령정보센터로 보내면 안 된다.
        if "요약자료" in g["law"]:
            g["link"] = "https://rfz.go.kr/?menuno=234"
            continue
        # KGS Code 는 법령이 아니라 가스기술기준정보시스템에서 본다.
        if g.get("kind") == "상세기준":
            g["link"] = ("https://cyber.kgs.or.kr/kgscode.codeSearch.listV2.ex.do"
                         f"?pblcCd={g['law'].replace('KGS ', '')}")
            # PDF 가 서버에 있으면 원문 쪽 그림을 볼 수 있게 쪽 번호를 준다.
            for h in hits:
                if h["law"] == g["law"] and article_ref(h["article"]) == g["ref"]:
                    pg = pdf_page_of(h)
                    if pg and pdf_file_of(pg[0]):
                        g["page"] = pg[1]
                        g["code"] = pg[0]
                        break
            continue
        law = g["law"].strip().replace(" ", "")
        path = f"법령/{law}"
        ref = g["ref"]
        if ref.startswith("제") and "조" in ref:
            path += f"/{ref}"                       # 제8조 → 그 조문으로
        g["link"] = "https://www.law.go.kr/" + urllib.parse.quote(path)

    out = sorted(groups.values(), key=lambda g: -g["score"])
    # 모델이 [n] 으로 인용할 번호. 모델에게 준 조각은 전부 번호가 있어야 하므로
    # 여기서 자르지 않는다(화면은 3개만 펼치고 나머지는 접는다).
    for i, g in enumerate(out[:12], 1):
        g["n"] = i
    return out[:12]


def stream_model(model, contents, key, system=SYSTEM):
    """한 글자씩 흘려보내기. 답변을 다 기다리지 않아 대화하는 느낌이 난다.

    성공하면 조각 문자열을 하나씩 내보내고, 실패하면 첫 줄에 오류를 던진다.
    """
    body = json.dumps({
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system}]},
        # 8192 인 이유: 최신 모델은 '생각'에 쓴 분량도 이 한도에 포함된다.
        # 2048 로 뒀더니 안전거리 표를 쓰기 직전에 한도가 바닥나 문장이 잘렸다.
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/{model}:streamGenerateContent?alt=sse&key={key}",
        data=body, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=180)   # HTTPError 는 호출자가 받는다
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        try:
            d = json.loads(line[5:])
            cand = d["candidates"][0]
            for p in cand.get("content", {}).get("parts", []):
                if p.get("text"):
                    yield p["text"]
            # 한도에 걸려 문장이 끊긴 경우, 화면에 그대로 두면 사용자가
            # 답이 다 나온 줄 안다. 잘렸다는 사실을 답변 끝에 붙여준다.
            if cand.get("finishReason") == "MAX_TOKENS":
                yield "\n\n…(답변이 길어 여기서 끊겼습니다. 더 좁혀서 물어봐 주세요)"
        except Exception:
            continue


def history_to_contents(messages, context):
    """지난 대화 + 이번에 찾은 조문을 제미나이가 읽는 형식으로 만든다.

    앞 대화를 같이 넘겨야 '그럼 그건 얼마나 걸려?' 같은 이어지는 질문이 통한다.
    """
    contents = []
    for m in messages[:-1][-8:]:      # 최근 4턴만. 너무 길면 느려지고 한도만 먹는다
        role = "user" if m.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m.get("text", "")}]})
    last = messages[-1].get("text", "")
    contents.append({"role": "user", "parts": [{"text":
        f"=== 검색된 법령 조문 ===\n{context}\n\n=== 질문 ===\n{last}"}]})
    return contents


class Handler(BaseHTTPRequestHandler):
    # 기본값(HTTP/1.0)이면 브라우저가 답을 통째로 모았다가 한 번에 그린다.
    # 한 글자씩 흘러나오게 하려면 1.1 + chunked 가 필요하다.
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        # 브라우저가 법령 사이트에서 이 서버로 본문을 보낼 때 필요한 사전 요청.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        path = u.path
        qs = urllib.parse.parse_qs(u.query)
        if path in ("/", "/index.html") or re.fullmatch(r"/s/[A-Za-z0-9]{6,12}", path):
            self._send(200, (HERE / "index.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif path == "/api/status":
            idx = search.get_index()
            kr = sum(1 for d in idx.docs if d["country"] == "한국")
            self._send(200, json.dumps({
                "articles": len(idx.docs), "korea": kr,
                "japan": len(idx.docs) - kr,
                "has_key": bool(api_key()), "model": MODEL, "mode": MODE,
                "need_code": bool(ACCESS_CODE),
                "semantic": idx.vecs is not None, "rerank": search.RERANK_ON,
                "cache": len(_cache), "ollama": ollama_fallback.enabled(),
                "pdf": PDF_DIR.exists(),
            }, ensure_ascii=False))
        elif path == "/api/distance":
            # 안전거리 계산기. 표 목록 또는 (표, 용량) → 해당 줄. AI 를 거치지 않는다.
            tid = (qs.get("table") or [""])[0]
            cap = (qs.get("cap") or [""])[0]
            if not tid:
                return self._send(200, json.dumps({"tables": distance.summary()},
                                                  ensure_ascii=False))
            try:
                cap = int(re.sub(r"[^\d]", "", cap))
            except ValueError:
                return self._send(400, json.dumps({"error": "용량은 숫자여야 합니다"},
                                                  ensure_ascii=False))
            r = distance.lookup(tid, cap)
            if not r:
                return self._send(404, json.dumps({"error": "표 범위 밖이거나 없는 표입니다"},
                                                  ensure_ascii=False))
            r["link"] = (f"https://cyber.kgs.or.kr/kgscode.codeSearch.listV2.ex.do"
                         f"?pblcCd={r['law'].replace('KGS ', '')}"
                         if r["law"].startswith("KGS") else
                         "https://www.law.go.kr/" + urllib.parse.quote(
                             f"법령/{r['law'].replace(' ', '')}"))
            self._send(200, json.dumps(r, ensure_ascii=False))
        elif path.startswith("/api/share/"):
            sid = path.rsplit("/", 1)[1]
            f = SHARE_DIR / f"{sid}.json"
            if not re.fullmatch(r"[A-Za-z0-9]{6,12}", sid) or not f.exists():
                return self._send(404, json.dumps({"error": "없는 공유 주소입니다"},
                                                  ensure_ascii=False))
            self._send(200, f.read_bytes())
        elif path in ("/api/byl", "/api/byl/file"):
            # 별지 서식·별표의 원문 주소와 HWP·PDF 파일. 법령정보센터에서 받아 와 서버에 둔다.
            law = (qs.get("law") or [""])[0].strip()
            kind = (qs.get("kind") or [""])[0]
            no = (qs.get("no") or [""])[0]
            br = (qs.get("br") or ["0"])[0]
            if not law or kind not in forms.KIND_CODE or not no.isdigit() or not br.isdigit():
                return self._send(400, json.dumps({"error": "law·kind·no 가 필요합니다"},
                                                  ensure_ascii=False))
            if "요약자료" in law or law.startswith("KGS"):
                return self._send(404, json.dumps({"error": "법령이 아닙니다"}, ensure_ascii=False))
            try:
                r = forms.resolve(law, kind, int(no), int(br))
            except Exception as e:                       # 법령정보센터가 느리거나 막힘
                return self._send(502, json.dumps({"error": f"법령정보센터 응답 없음: {e}"},
                                                  ensure_ascii=False))
            if not r:
                return self._send(404, json.dumps({"error": "법령정보센터에 없는 서식·별표입니다"},
                                                  ensure_ascii=False))
            if path == "/api/byl":
                return self._send(200, json.dumps(
                    {k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False))
            fmt = (qs.get("fmt") or ["pdf"])[0]
            fl = r["_pdf"] if fmt == "pdf" else r["_han"]
            if fmt not in ("pdf", "hwp") or not fl:
                return self._send(404, json.dumps({"error": "그 형식의 파일이 없습니다"},
                                                  ensure_ascii=False))
            try:
                data, name = forms.fetch_file(fl, fmt)
            except Exception as e:
                return self._send(502, json.dumps({"error": f"파일을 받지 못했습니다: {e}"},
                                                  ensure_ascii=False))
            if not data:
                return self._send(404, json.dumps({"error": "파일이 비어 있습니다"},
                                                  ensure_ascii=False))
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf" if fmt == "pdf" else "application/x-hwp")
            self.send_header("Content-Disposition",
                             ("inline" if fmt == "pdf" else "attachment")
                             + f"; filename*=UTF-8''{urllib.parse.quote(name)}")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/page":
            code = (qs.get("code") or [""])[0]
            page = (qs.get("page") or ["0"])[0]
            if not re.fullmatch(r"[A-Z]{2}\d{3}", code) or not page.isdigit():
                return self._send(400, json.dumps({"error": "code·page 가 필요합니다"}))
            data = render_page(code, int(page))
            if not data:
                return self._send(404, json.dumps({"error": "이 서버에는 PDF 원문이 없습니다"},
                                                  ensure_ascii=False))
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_share(self, req):
        """대화를 저장하고 짧은 주소를 돌려준다."""
        turns = req.get("turns") or []
        if not turns or len(turns) > 30:
            return self._send(400, json.dumps({"error": "저장할 대화가 없습니다"},
                                              ensure_ascii=False))
        keep = []
        for t in turns:
            keep.append({k: t.get(k) for k in
                         ("q", "text", "sources", "cited", "followups",
                          "warnings", "nums", "refs", "lowconf", "model", "cached")})
        rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "turns": keep}
        raw = json.dumps(rec, ensure_ascii=False).encode()
        if len(raw) > SHARE_MAX_BYTES:
            return self._send(413, json.dumps({"error": "대화가 너무 깁니다"},
                                              ensure_ascii=False))
        sid = hashlib.sha1(raw).hexdigest()[:8]
        SHARE_DIR.mkdir(parents=True, exist_ok=True)
        (SHARE_DIR / f"{sid}.json").write_bytes(raw)
        self._send(200, json.dumps({"id": sid, "path": f"/s/{sid}"}))

    def _event(self, obj):
        """줄 단위 JSON 을 chunked 로 흘려보낸다. 브라우저가 받는 즉시 그린다."""
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def _done(self, **extra):
        """마지막 신호를 보내고 스트림을 닫는다."""
        self._event(dict({"type": "done"}, **extra))
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    # ── /api/chat ── 흐름: 요청 풀기 → 인사·소개 → 캐시 → 검색 → 발표 잠금 → 모델 → 마무리
    # 한 함수가 290줄이라 단계별로 나눴다. 각 단계는 self._event 로 화면에 흘리고,
    # 흐름을 끝내야 하면 self._done() 의 결과를 돌려준다(호출한 쪽에서 그대로 return).

    def do_chat(self, req):
        p = self._chat_parse(req)
        if p is None:
            return
        q = p["q"]

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        if self._chat_canned(q):
            return

        # ── 캐시 ── 같은 첫 질문은 저장해 둔 답을 그대로 흘린다(모델 호출 없음).
        ckey = (_cache_key(q, p["country"], p["facility"], p["as_of"], p["checklist"])
                if p["first_turn"] else None)
        hit = cache_get(ckey) if (ckey and not req.get("nocache")) else None
        if hit:
            return self._chat_from_cache(q, hit)

        t_start = time.time()
        hits = self._chat_retrieve(p)
        shown = group_sources(hits)
        self._event({"type": "sources", "sources": shown})
        cl = clarify_for(q)
        if cl:
            self._event(cl)

        # ── 발표 잠금 ── 사람이 확인한 답이 있으면 그것만 내보낸다.
        demo = demo_lookup(q) if p["first_turn"] else None
        if demo:
            self._event({"type": "text", "t": demo["body"]})
            self._event({"type": "cited", "refs": demo.get("cited", [])})
            self._event({"type": "followups", "items": demo.get("followups", [])})
            self._event({"type": "verify", "warnings": [], "nums": [], "refs": []})
            log_turn({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "q": q, "model": "demo-lock"})
            return self._done(model=demo.get("model"), cached=True, approved=True)

        key = api_key()
        if not key and not ollama_fallback.enabled():
            self._event({"type": "text", "t":
                "API 키가 없습니다. 폴더에 key.txt 를 만들고 키를 넣어주세요."})
            return self._done()
        if not hits:
            self._event({"type": "text", "t":
                "관련 조문을 찾지 못했습니다. 다른 용어로 물어봐 주세요."})
            return self._done()

        weak, note = self._chat_note(q, hits, p["as_of"])
        context = build_context(hits, shown) + note
        contents = history_to_contents(p["messages"], context)
        if weak:
            self._event({"type": "lowconf"})
        system = SYSTEM + (CHECKLIST_SYSTEM if p["checklist"] else "")

        # 시도 순서: 화면에서 고른 모드(평소/발표)의 제미나이 목록 → 마지막으로 로컬 LLM.
        attempts = [("gemini", m) for m in MODEL_SETS.get(req.get("mode"), MODELS)] \
            if key else []
        if ollama_fallback.enabled():
            attempts.append(("ollama", ollama_fallback.MODEL))
        last_err = None
        for kind, model in attempts:
            for attempt in range(2):
                try:
                    if kind == "ollama" and (attempt or not ollama_fallback.alive()):
                        last_err = (model, 0, "로컬 LLM 이 꺼져 있음")
                        break
                    got = self._chat_stream(kind, model, system, contents, key)
                    if got is None:
                        last_err = (model, 0, "빈 응답")
                    elif got == "short":
                        last_err = (model, 0, "응답이 끊김")
                        continue
                    else:
                        self._chat_finish(
                            req, p, hits, shown, context, kind, model, key, got,
                            weak=weak, ckey=ckey, t_start=t_start)
                        return self._done(model=model, kind=kind)
                except urllib.error.HTTPError as e:
                    last_err = (model, e.code,
                                e.read().decode("utf-8", "replace")[:200])
                    if e.code not in (500, 503):
                        break          # 429(한도)·키 오류는 재시도해도 같다
                except Exception as e:
                    last_err = (model, 0, str(e))
                    import traceback
                    traceback.print_exc()        # 서버 로그에 남긴다. 화면에는 한 줄만 간다.
                time.sleep(2 * (attempt + 1))

        model, code, detail = last_err or ("-", 0, "시도할 모델이 없음")
        self._event({"type": "text", "t":
            "지금 구글 서버가 붐벼서 답변을 받지 못했습니다. "
            "아래 근거 조문은 정상이니 잠시 뒤 다시 물어봐 주세요.\n"
            f"(마지막 오류: {model} {code} {detail})"})
        self._done()

    def _chat_parse(self, req):
        """요청에서 질문·옵션을 꺼낸다. 막아야 하면 오류를 보내고 None."""
        if ACCESS_CODE and (req.get("code") or "").strip() != ACCESS_CODE:
            self._send(401, json.dumps(
                {"error": "접근 코드가 필요합니다"}, ensure_ascii=False))
            return None
        # 중계(워커·터널)를 거치므로 원래 접속자 주소는 헤더에서 본다.
        ip = (self.headers.get("CF-Connecting-IP")
              or self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
              or self.client_address[0])
        if not rate_ok(ip):
            self._send(429, json.dumps(
                {"error": "잠시 후 다시 시도해 주세요 (시간당 30회 제한)"},
                ensure_ascii=False))
            return None
        messages = req.get("messages") or []
        if not messages or not (messages[-1].get("text") or "").strip():
            self._send(400, json.dumps({"error": "질문이 비었습니다"}))
            return None
        q = messages[-1]["text"].strip()
        # 기준일(YYYY-MM-DD). 그날 시행 중인 판으로 답한다. 형식이 틀리면 무시.
        as_of = (req.get("as_of") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
            as_of = None
        # 이어지는 질문("그럼 기간은?")은 그 말만으로 검색이 안 되니
        # 바로 앞 질문을 검색어에 같이 넣는다.
        prev = [m["text"] for m in messages[:-1] if m.get("role") == "user"]
        return {
            "ip": ip, "q": q, "messages": messages,
            "query": (prev[-1] + " " + q) if (prev and len(q) < 15) else q,
            "country": req.get("country") or None,
            "facility": req.get("facility") or None,
            "as_of": as_of,
            "checklist": bool(req.get("checklist")) or bool(CHECKLIST_RE.search(q)),
            "first_turn": not any(m.get("role") == "user" for m in messages[:-1]),
        }

    def _chat_canned(self, q):
        """인사·자기소개는 법령을 뒤지지 않고 정해진 말로 답한다. 답했으면 True."""
        # 인사·잡담을 검색하면 부칙 조문이 근거랍시고 붙는다(실측).
        if SMALLTALK.match(q) and len(q) <= 12:
            self._event({"type": "sources", "sources": []})
            self._event({"type": "text", "t":
                "안녕하세요! 수소시설 인허가에 대해 물어봐 주세요.\n"
                "예) 수소충전소 안전거리는? · 제조허가는 누구에게 받아? · 규제특례 종류는?"})
            self._done()
            return True
        # "너 정체가 뭐야?" 같은 자기소개 질문도 마찬가지. 검색을 돌리면 소방기본법 제1조가
        # 근거로 붙고 "자료에 없을 수 있다" 경고까지 떴다(실측).
        if META.search(q) and len(q) <= 30:
            self._event({"type": "sources", "sources": []})
            self._event({"type": "text", "t": INTRO})
            self._event({"type": "followups", "items": [
                "수소충전소를 세우려면 어떤 허가가 필요해?",
                "수소충전소는 제1종보호시설에서 몇 미터 떨어져야 해?",
                "규제특례에는 어떤 종류가 있어?"]})
            self._done()
            return True
        return False

    def _chat_from_cache(self, q, hit):
        """저장해 둔 답을 그대로 흘린다."""
        self._event({"type": "sources", "sources": hit["sources"]})
        if hit.get("lowconf"):
            self._event({"type": "lowconf"})
        self._event({"type": "text", "t": hit["body"]})
        self._event({"type": "cited", "refs": hit["cited"]})
        self._event({"type": "followups", "items": hit["followups"]})
        self._event({"type": "verify", "warnings": hit["warnings"],
                     "nums": hit.get("nums", []), "refs": hit.get("refs", [])})
        log_turn({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "q": q,
                  "model": "cache", "cached": True})
        return self._done(model=hit.get("model"), cached=True, cached_at=hit.get("t"))

    def _chat_retrieve(self, p):
        """조문을 찾는다: 검색 → (약하면) 재작성 검색 → 서식 → 확정 자료."""
        q, query = p["q"], p["query"]
        idx = search.get_index()
        opts = dict(country=p["country"], facility=p["facility"], as_of=p["as_of"])
        hits = idx.search(query, top_k=12, **opts)
        # 검색어 재작성(모델 호출)은 원문 검색이 약할 때만 한다.
        # 매번 하면 질문 하나에 모델을 두 번 불러 하루 한도가 반으로 준다.
        if (hits[0]["score"] if hits else 0) < 55:
            better = rewrite_query(query, api_key())
            if better != query:
                hits2 = idx.search(better, top_k=12, **opts)
                if hits2 and hits2[0]["score"] > (hits[0]["score"] if hits else 0):
                    hits = hits2
        # 체크리스트에는 제출 서류 이름이 곧 답이라 별지 서식을 따로 붙인다.
        if p["checklist"] and hits:
            have = {(h["law"], h["article"]) for h in hits}
            hits += [f for f in idx.search_forms(query, 4)
                     if (f["law"], f["article"]) not in have]
        # 확정 자료(수수료·서식·기간·안전거리)는 맨 앞에 넣는다. 값은 코드가 표에서 가져온다.
        fixed = facts.match(q)
        if fixed:
            hits = fixed + hits
        return hits

    def _chat_note(self, q, hits, as_of):
        """모델에게 붙일 주의문을 만든다. (자료 없음 판정, 기준일, 개정 비교, 갈래 확인)"""
        # 검색 점수가 바닥이면 그 주제 법령이 자료에 아예 없다는 뜻이다.
        # (실측: '규제특례' 최고점 21.8 — 규제자유특구법이 데이터에 0건)
        # 이때 그냥 두면 비슷해 보이는 엉뚱한 조문을 끌어다 답한다.
        # 기준 40: 실측으로 갈렸다. 자료가 있는 질문은 70 안팎(안전거리 71.8),
        # 자료가 없는 질문은 30 안팎(규제특례 31.2, 엉뚱한 잡담 26.3).
        # 개정 질문("뭐가 바뀌어?")은 질문 단어가 조문에 없어 점수가 낮게 나온다.
        # 시행 예정판이 걸렸으면 자료가 있는 것이니 '없음' 판정을 하지 않는다.
        weak = (hits[0]["score"] if hits else 0) < 40 and not (
            search.CHANGE.search(q) and any(h.get("future") for h in hits[:4]))
        note = ("\n\n[주의] 검색 점수가 낮습니다. 질문 주제의 법령이 자료에 "
                "없을 가능성이 큽니다. 비슷해 보이는 다른 조문으로 대체하지 말고, "
                "'이 주제의 법령은 현재 자료에 없습니다'라고 먼저 밝힌 뒤 "
                "무엇이 필요한지만 짧게 안내하세요.") if weak else ""
        if as_of:
            note += (f"\n\n[기준일 {as_of}] 이 날짜에 시행 중인 조문으로 답합니다. "
                     "'개정판'이라 표시된 조문이 현행이고, '시행 예정'은 아직 효력이 없으니 "
                     "'○○부터 시행 예정'이라고 구분해 적습니다.")
        if search.CHANGE.search(q):
            note += ("\n\n[개정 비교] '현행판(비교용)'과 '시행 예정' 조문이 짝으로 들어 있습니다. "
                     "무엇이 어떻게 달라지는지 전·후를 나란히 적고, 시행일을 밝힙니다.")
        # 우산 개념은 갈래를 빠뜨리지 않게 이름을 못 박는다(실측: 신속확인 조문이 자료에
        # 있어도 답변은 '두 가지'로 끝났다).
        for umbrella, subs in search.BUNDLES.items():
            if umbrella in q:
                present = [s for s in subs if any(
                    s.replace(" ", "") in (h["title"] + h["content"][:300]).replace(" ", "")
                    for h in hits)]
                if len(present) >= 2:
                    note += (f"\n\n[갈래 확인] '{umbrella}'는 자료에 {len(present)}갈래가 있습니다: "
                             + " · ".join(present) + ". 종류를 물었으면 이 갈래를 모두 다룹니다.")
                break
        return weak, note

    def _chat_stream(self, kind, model, system, contents, key):
        """모델 하나를 불러 답을 화면에 흘린다.

        돌려주는 값: 전체 답 문자열 / None(빈 응답) / "short"(토막이라 다시 시도).
        """
        if kind == "ollama":
            self._event({"type": "text", "t": ""})      # 화면의 '읽는 중'을 답변 모드로 넘긴다
            gen = ollama_fallback.stream(system, contents)
        else:
            gen = stream_model(model, contents, key, system)
        got = False
        buf, sent = "", 0
        for chunk in gen:
            got = True
            buf += chunk
            # 꼬리에 붙는 '###다음질문' 블록은 화면에 글로 흘리지 않고
            # 버튼으로 만든다. 표시가 반쯤 도착한 상태에서 잘못 내보내지
            # 않도록, 표시 길이만큼은 항상 손에 쥐고 있다가 흘린다.
            _, cut = split_followups(buf)
            stop = cut if cut >= 0 else max(0, len(buf) - 12)
            if stop > sent:
                self._event({"type": "text", "t": buf[sent:stop]})
                sent = stop
        if not got:
            return None
        body, cut = split_followups(buf)
        if cut < 0 and len(buf) > sent:
            self._event({"type": "text", "t": buf[sent:]})
        # 상류에서 스트림이 끊기면 "고압" 두 글자만 나오고 끝난 적이 있다.
        # 이런 토막을 정상 답변으로 넘기면 안 되니 다음 모델로 다시 시도한다.
        if len(body.strip()) < 40:
            self._event({"type": "text", "t": "\n\n…(답변이 끊겨 다시 시도합니다)\n\n"})
            return "short"
        return buf

    def _chat_finish(self, req, p, hits, shown, context, kind, model, key, text,
                     *, weak, ckey, t_start):
        """답이 다 온 뒤: 검증 → 자기교정 → 삭제 → 근거 표시 → 검수 → 기록 → 캐시."""
        q = p["q"]
        body = split_followups(text)[0]
        body_text = body
        follow = parse_followups(text)
        v = verify(text, hits)
        removed = []
        # ── 자기교정 ── 어긋난 표기가 있으면 화면에 굳히기 전에 고친다.
        bad = v["nums"] + v["refs"]
        if bad and kind == "gemini":
            fixed_text = correct_answer(model, text, context, bad, key)
            if fixed_text:
                v2 = verify(fixed_text, hits)
                if len(v2["nums"]) + len(v2["refs"]) < len(bad):
                    text, v = fixed_text, v2
                    body_text = split_followups(text)[0]
                    follow = parse_followups(text) or follow
        # ── 그래도 남으면 그 줄을 지운다 ──
        bad = v["nums"] + v["refs"]
        if bad:
            body_text, removed = strip_unverified(body_text, bad)
            v = verify(body_text, hits)
        if body_text != body:
            self._event({"type": "replace", "t": body_text})
        # 답변이 실제로 인용한 근거를 알려준다. [3] 번호와 이름 둘 다 본다.
        # 일본 조문은 근거가 '第七条'이고 답변은 '제7조'다. 둘 다 본다.
        # [3] 도 [7, 8] 도 인용이다.
        nums_cited = {int(x) for grp in re.findall(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]", body_text)
                      for x in re.findall(r"\d+", grp)}
        cited = [s["ref"] for s in shown
                 if s.get("n") in nums_cited
                 or s["ref"].strip("[]") in body_text
                 or (jp_refs_as_korean(s["ref"]) or "\0") in body_text]
        self._event({"type": "cited", "refs": cited})
        self._event({"type": "followups", "items": follow})
        warns = v["warnings"] + (
            [f"근거 확인이 안 되어 뺀 내용 {len(removed)}곳"] if removed else [])
        self._event({"type": "verify", "warnings": warns,
                     "nums": v["nums"], "refs": v["refs"], "removed": removed})
        # ── 근거 번호 없는 사실 문장 ── 회색으로 보인다.
        uncited = uncited_sentences(body_text) if kind == "gemini" else []
        if uncited:
            self._event({"type": "uncited", "items": uncited})
        # ── 이중 검사 ── 다른 계열 모델이 문장마다 근거 유무를 본다(발표 모드).
        judged = None
        if (JUDGE_ALWAYS or req.get("mode") == "demo") and kind == "gemini":
            judged = judge_answer(body_text, context, key, model)
            if judged is not None:
                self._event({"type": "judge", "bad": judged})
        log_turn({
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            # 주소 끝 두 자리는 가린다. 시간당 30회 제한이 사람마다
            # 따로 세는지(워커 너머 주소가 제대로 오는지) 확인하려는 용도다.
            "ip": re.sub(r"[\d a-f]+$", "x", p["ip"])[:24],
            "q": q, "model": model, "mode": req.get("mode"),
            "kind": kind, "checklist": p["checklist"], "as_of": p["as_of"],
            "top_score": hits[0]["score"] if hits else 0,
            "weak": weak, "cited": cited, "warnings": warns,
            "removed": removed, "judged": judged, "uncited": len(uncited),
            "sec": round(time.time() - t_start, 1),
            "sources": [f"{s2['law']} {s2['ref']}" for s2 in shown],
            "answer": body_text.strip(),
        })
        # 검증 경고가 없는 첫 질문만 저장한다. 의심스러운 답을 굳히면 안 된다.
        if ckey and not warns and not weak and not judged:
            cache_put(ckey, {
                "t": time.strftime("%Y-%m-%d %H:%M"), "model": model,
                "q": q, "sources": shown, "body": body_text,
                "cited": cited, "followups": follow,
                "warnings": [], "nums": v["nums"], "refs": v["refs"],
                "lowconf": weak,
            })

    def do_ingest(self, req):
        """법령 사이트에서 긁은 본문을 파일로 받아둔다.

        법제처는 조문을 자바스크립트로 그려서 서버에서 직접 못 받는다.
        그래서 브라우저가 읽은 본문을 여기로 넘기고, 이후 처리는 평소대로 한다.
        """
        # 수집용 뒷문이라 공개 서버에서는 잠근다. 누구나 디스크에 파일을 쓸 수 있으면 안 된다.
        if ACCESS_CODE and (req.get("code") or "").strip() != ACCESS_CODE:
            return self._send(401, json.dumps(
                {"error": "접근 코드가 필요합니다"}, ensure_ascii=False))
        if not ACCESS_CODE and HOST != "127.0.0.1":
            return self._send(403, json.dumps(
                {"error": "공개 서버에서는 수집 기능을 막아 두었습니다"}, ensure_ascii=False))
        name = re.sub(r'[\\/:*?"<>|]', "_", (req.get("law") or "unknown"))[:80]
        text = (req.get("text") or "")[:2_000_000]
        d = HERE / "data" / "raw"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.txt").write_text(text, encoding="utf-8")
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        body = json.dumps({"saved": name, "chars": len(text)}).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        """본문을 읽어 JSON 으로 푼다. 깨진 요청 하나가 연결을 끊지 않게 한다.

        (실측: 인코딩이 어긋난 요청 하나에 처리 스레드가 죽으면서
         터널 너머에서는 502 로 보였다.)
        """
        n = int(self.headers.get("Content-Length", 0))
        if n > 4_000_000:                    # 대화 8턴이어도 100KB 안팎. 그 이상은 공격이다
            return None
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def do_POST(self):
        req = self._read_json()
        if req is None:
            return self._send(400, json.dumps(
                {"error": "요청 형식이 올바르지 않습니다(UTF-8 JSON)"},
                ensure_ascii=False))
        if self.path == "/api/ingest":
            return self.do_ingest(req)
        if self.path == "/api/chat":
            return self.do_chat(req)
        if self.path == "/api/share":
            return self.do_share(req)
        if self.path == "/api/feedback":
            vote = req.get("vote")
            if vote not in ("up", "down"):
                return self._send(400, json.dumps({"error": "vote 는 up/down"}))
            try:
                FEEDBACK.parent.mkdir(exist_ok=True)
                with FEEDBACK.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "t": time.strftime("%Y-%m-%d %H:%M:%S"), "vote": vote,
                        "q": (req.get("q") or "")[:300], "reason": (req.get("reason") or "")[:500],
                        "answer": (req.get("answer") or "")[:1500],
                        "sources": (req.get("sources") or [])[:8],
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass
            return self._send(200, json.dumps({"ok": True}))
        if self.path != "/api/ask":
            return self._send(404, json.dumps({"error": "not found"}))
        # 본문은 위에서 이미 읽었다. 여기서 다시 읽으면 남은 게 없어 타임아웃까지 멈춘다.
        q = (req.get("question") or "").strip()
        country = req.get("country") or None
        if not q:
            return self._send(400, json.dumps({"error": "질문이 비었습니다"}))

        # 12개까지 넉넉히 넘긴다. 키워드 검색이라 순위가 완벽하지 않아도
        # 제미나이가 조문을 읽고 관련 없는 것을 걸러내는 편이 정확하다.
        hits = search.get_index().search(q, top_k=int(req.get("top_k", 12)),
                                         country=country)
        key = api_key()
        if not key:
            answer = ("API 키가 아직 없습니다. 아래 검색된 조문은 정상입니다.\n"
                      "키를 넣으면 이 자리에 요약 답변이 나옵니다.\n\n"
                      "넣는 법: 이 폴더에 key.txt 파일을 만들고 키만 붙여넣기.")
        elif not hits:
            answer = "관련 조문을 찾지 못했습니다. 다른 용어로 검색해 보세요."
        else:
            answer = ask_gemini(q, build_context(hits), key)

        self._send(200, json.dumps({"answer": answer, "sources": hits},
                                   ensure_ascii=False))

    def log_message(self, fmt, *a):
        pass


if __name__ == "__main__":
    idx = search.get_index()
    _cache_load()
    print(f"조문 {len(idx.docs)}개 색인 완료 · 답변 캐시 {len(_cache)}건")
    print(f"API 키: {'있음' if api_key() else '없음 (검색만 동작)'}")
    print(f"뜻 검색 {'켬' if idx.vecs is not None else '끔'} · 재순위 {'켬' if search.RERANK_ON else '끔'}"
          f" · 로컬 LLM {'켬' if ollama_fallback.enabled() else '끔'}"
          f" · PDF 원문 {'있음' if PDF_DIR.exists() else '없음'}")
    if search.RERANK_ON:
        import rerank
        threading.Thread(target=rerank.warm, daemon=True).start()
    if WARM:
        threading.Thread(target=warm_cache, args=(PORT,), daemon=True).start()
    print(f"→ http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
