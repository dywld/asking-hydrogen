#!/usr/bin/env python3
"""가스안전공사 쪽 서류 자동 검토(시연용).

신청자가 챗봇에서 만든 신청서를 '공사에 제출(시연)' 하면 접수함에 쌓이고,
담당자 화면(review.html)에서 접수함 → 상세 검토 → 보완 요청 공문 순서로 처리한다.
검토는 규칙으로만 한다(형식·빈칸·첨부서류). 근거는 각 서식 본문과 서식 이름이다.
조문 번호를 지어내지 않으려고 법 조항 번호는 붙이지 않는다.
"""
import json
import re
import threading
import time
from pathlib import Path

import permit_forms

INBOX = Path(__file__).parent / "data" / "review_inbox.json"
_lock = threading.Lock()

RED, ORG = "red", "org"


def biz_ok(s):
    """사업자등록번호 검증 숫자(국세청 공개 계산식)."""
    d = [int(c) for c in re.sub(r"\D", "", s)]
    if len(d) != 10:
        return False
    w = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    t = sum(a * b for a, b in zip(d, w)) + d[8] * 5 // 10
    return (10 - t % 10) % 10 == d[9]


def form_name(f):
    return f"{f['law']} 별지 제{f['no']}호서식"


def check(fid, vals, docs):
    """→ findings [{lv, key, label, title, why, basis}]"""
    f = permit_forms.FORMS[fid]
    basis = form_name(f)
    out = []
    labels = {t[0]: t[2].split(" (")[0] for t in f["fields"]}

    def add(lv, key, title, why, b=basis):
        out.append({"lv": lv, "key": key, "label": labels.get(key, key), "title": title, "why": why, "basis": b})

    for key, label in labels.items():
        v = (vals.get(key) or "").strip()
        if not v:
            add(RED, key, f"{label} 빈칸", "서식의 필수 기재 칸이 비어 있습니다.")
            continue
        if key == "bizno":
            n = re.sub(r"\D", "", v)
            if len(n) != 10:
                add(RED, key, "사업자등록번호 자리수 오류", f"{len(n)}자리입니다. 10자리여야 합니다.")
            elif not biz_ok(v):
                add(RED, key, "사업자등록번호 검증 숫자 불일치", "마지막 자리 검증 숫자가 계산값과 다릅니다. 오기 가능성이 큽니다.")
        elif key == "tel" and not re.fullmatch(r"0\d{1,2}-?\d{3,4}-?\d{4}", v.replace(" ", "")):
            add(RED, key, "전화번호 형식 오류", "지역번호-국번-번호 형식이 아닙니다.")
        elif key == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", v):
            add(RED, key, "전자우편 형식 오류", "주소에 @ 와 도메인이 필요합니다.")
        elif key in ("office", "site"):
            if not re.search(r"(시|군|구)\b|(시|군|구)\s", v + " "):
                add(ORG, key, f"{label} 행정구역 불명확", "시·군·구가 보이지 않습니다. 관할 확인이 어렵습니다.")
            elif not re.search(r"\d", v):
                add(ORG, key, f"{label} 번지 없음", "도로명 번호나 지번이 없습니다.")
        elif key == "cap":
            m = re.search(r"[\d,.]+", v)
            if not m:
                add(RED, key, "저장능력 수치 없음", "숫자와 단위를 함께 적어야 합니다.")
            elif not re.search(r"㎥|m3|kg|톤|t\b|L|ℓ", v, re.I):
                add(ORG, key, "저장능력 단위 없음", "㎥·kg 등 단위가 없어 규모를 판단할 수 없습니다.")
            elif "톤" in v and float(m.group().replace(",", "") or 0) >= 1000:
                add(ORG, key, "저장능력 단위 의심", "수소 시설로는 매우 큰 값입니다. kg 오기인지 확인이 필요합니다.")
    if vals.get("office") and vals.get("site") and vals["office"].strip() == vals["site"].strip():
        add(ORG, "site", "사업소 주소가 본사와 같음", "시설이 본사 건물 안에 있는지 현장 확인이 필요합니다.")
    # 신청인 서명: 서식 맨 아래 '(서명 또는 인)' 칸. 없으면 효력이 없는 신청서다.
    labels.setdefault("sign", "신청인 서명")
    if not str(vals.get("sign") or "").startswith("data:image"):
        add(RED, "sign", "신청인 서명 없음", "서식 하단의 '(서명 또는 인)' 칸이 비어 있습니다. 서명이 없으면 접수할 수 없습니다.",
            basis + " 신청인 서명란")
    for d in f["docs"]:
        if d not in docs:
            add(RED, "docs", f"첨부 누락: {d}", "서식 본문의 첨부서류 목록에 있으나 제출되지 않았습니다.",
                basis + " 첨부서류란")
    return out


def verdict(fs):
    if any(x["lv"] == RED for x in fs):
        return "반려 예상"
    return "확인 필요" if fs else "승인 가능"


def letter(item):
    f = permit_forms.FORMS[item["fid"]]
    reds = [x for x in item["findings"]]
    day = time.strftime("%Y. %m. %d.").replace(" 0", " ")
    due = time.strftime("%Y. %m. %d.", time.localtime(time.time() + 14 * 86400)).replace(" 0", " ")
    ko = "가나다라마바사아자차카타파하"
    lines = [f"수신  {item['vals'].get('company') or '신청인'} 대표 {item['vals'].get('ceo') or ''}".rstrip(),
             f"제목  {f['title']} 신청서 보완 요청", "",
             f"1. 귀사에서 {item['date']} 신청한 {f['title']} 신청서({form_name(f)})를 검토한 결과, "
             "아래 사항의 보완이 필요하여 알려 드립니다.", "2. 보완 사항"]
    for i, x in enumerate(reds):
        lines.append(f"  {ko[i % len(ko)]}. {x['title']}: {x['why']}")
    lines += [f"3. 보완 기한: {due}까지", "", f"한국가스안전공사  {day}"]
    return "\n".join(lines)


def _load():
    try:
        return json.loads(INBOX.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items):
    INBOX.parent.mkdir(exist_ok=True)
    INBOX.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def submit(fid, vals, docs, demo=False, files=None, ai=None, fchk=None):
    """ai: (서식 제목, 칸 [(key, 이름, 값)]) → [{key,title,why}] 를 돌려주는 함수(선택).
    규칙이 못 보는 '내용이 말이 되는지'만 AI에 묻고, 결과는 확인 권장(주황)으로만 붙인다."""
    if fid not in permit_forms.FORMS:
        raise ValueError("서식 id 가 없습니다")
    fs = check(fid, vals, docs)
    if ai:
        f = permit_forms.FORMS[fid]
        rows = [(t[0], t[2].split(" (")[0], (vals.get(t[0]) or "").strip()) for t in f["fields"]]
        seen = {x["key"] for x in fs}
        try:
            for x in (ai(f["title"], rows) or [])[:3]:
                k = str(x.get("key", ""))
                if k in dict((r[0], 1) for r in rows) and k not in seen:
                    fs.append({"lv": ORG, "key": k, "label": dict((r[0], r[1]) for r in rows)[k],
                               "title": str(x.get("title", ""))[:40], "why": str(x.get("why", ""))[:120],
                               "basis": "AI 내용 판단(참고, 담당자 확인)"})
                    seen.add(k)
        except Exception:
            pass                                    # AI 가 실패해도 규칙 검토 결과는 그대로 낸다
    # 첨부파일 내용 확인(AI): 다른 서류로 보이면 확인 권장. 이름이 아니라 내용으로 판단한 것만 온다.
    for c in fchk or []:
        if not c.get("ok", True):
            fs.append({"lv": ORG, "key": "docs", "label": "첨부서류", "title": f"첨부 내용 의심: {c['doc']}"[:40],
                       "why": f"'{c['name']}' {c.get('why', '')}".strip()[:120], "basis": "AI 첨부파일 판독(참고, 담당자 확인)"})
    with _lock:
        items = _load()
        n = len(items) + 1
        item = {"id": f"{time.strftime('%Y')}-{n:04d}", "fid": fid, "title": permit_forms.FORMS[fid]["title"],
                "vals": vals, "docs": docs, "findings": fs, "verdict": verdict(fs),
                "date": time.strftime("%Y. %m. %d.").replace(" 0", " "), "time": time.strftime("%H:%M"),
                "status": "접수", "letter": "", "demo": demo, "files": files or []}
        items.append(item)
        _save(items)
    return item


def listing():
    order = {"반려 예상": 0, "확인 필요": 1, "승인 가능": 2}
    items = _load()
    if not any(x.get("demo") for x in items):
        seed()
        items = _load()
    return sorted(items, key=lambda x: (x["status"] != "접수", order.get(x["verdict"], 3), x["time"]))


def get(iid):
    for x in _load():
        if x["id"] == iid:
            if not x.get("letter"):
                x["letter"] = letter(x)
            return x
    return None


def decide(iid, action, text=""):
    with _lock:
        items = _load()
        for x in items:
            if x["id"] == iid:
                x["status"] = "승인" if action == "approve" else "보완 요청"
                x["letter"] = text or x.get("letter") or letter(x)
                _save(items)
                return x
    return None


def seed():
    """빈 접수함을 시연용 가상 신청 몇 건으로 채운다(회사·사람은 지어낸 이름)."""
    F = permit_forms.FORMS
    ok_biz = "000-00-00015"   # 검증 숫자만 맞춘 가짜 번호(실제 사업자와 겹치지 않게 0으로 시작)
    demo = [
        ("gas_permit", {"company": "동해에너지(주)", "ceo": "최민준", "office": "강원 동해시 해안로 5",
                        "site": "강원 동해시 해안로 5", "tel": "033-530-7788", "bizno": "000-00-0001",
                        "email": "safety@donghae.example"}, F["gas_permit"]["docs"][:2]),
        ("gas_use", {"company": "춘천모빌리티", "ceo": "이도윤", "office": "강원 춘천시 퇴계로 88",
                     "site": "강원 춘천시 퇴계로 90", "tel": "033-555-0101", "bizno": ok_biz,
                     "gas": "수소", "cap": "50000 톤", "purpose": "연료전지 시험", "month": "200 ㎥"},
         F["gas_use"]["docs"]),
        ("gas_permit", {"company": "원주가스", "ceo": "박서연", "office": "강원 원주시 단계로 21",
                        "site": "강원 원주시 문막읍 산업로 7", "tel": "033-742-1100", "bizno": ok_biz,
                        "email": "admin@wonju.example"}, F["gas_permit"]["docs"]),
    ]
    for fid, v, d in demo:
        v = {**{t[0]: (t[5] if len(t) > 5 else "") for t in F[fid]["fields"]}, **v}
        submit(fid, v, d, demo=True)
