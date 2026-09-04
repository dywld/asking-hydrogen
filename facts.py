#!/usr/bin/env python3
"""확정 자료 — 수치 질문의 답을 AI 가 아니라 표에서 가져온다.

수수료·서식 번호·특례 기간·안전거리처럼 값이 정해진 것은 모델이 문장만 다듬어야지
값을 고르게 두면 안 된다(옆 칸을 읽는 일이 있다). data/fact_tables.json 에 값과
원문 인용(quote)을 두고, 질문이 그 주제면 '확정 자료' 조각으로 근거 맨 앞에 넣는다.
모델에게는 "이 값을 그대로 인용하라"고 지시한다.

quote 는 원문 조각에 글자 그대로(공백 무시) 있어야 한다. --check 가 대조한다.
옮겨 적다 틀린 값이 '확정'으로 나가는 일을 막으려는 것이다.

    python facts.py --check
    python facts.py "제조허가 수수료 얼마야?"
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
FILE = HERE / "data" / "fact_tables.json"

_topics = None


def topics():
    global _topics
    if _topics is None:
        raw = json.loads(FILE.read_text(encoding="utf-8"))["topics"]
        for t in raw:
            t["_re"] = re.compile(t["match"])
        _topics = raw
    return _topics


def match(question):
    """질문에 맞는 주제들 → 검색 결과와 같은 모양의 조각 목록(kind='확정')."""
    out = []
    for t in topics():
        if not t["_re"].search(question):
            continue
        lines = [f"{t['law']} {t['ref']} {t['title']} — 확정 자료(표에서 코드가 직접 찾음)"]
        for f in t["facts"]:
            lines.append(f"· {f['label']}: {f['value']}   (원문: \"{f['quote']}\")")
        out.append({
            "country": "한국", "law": t["law"], "article": t["ref"], "title": t["title"],
            "content": "\n".join(lines), "source": "fact_tables.json",
            "future": False, "effective_date": None, "kind": "확정",
            "score": 999.0, "facts": t["id"],
        })
    return out


def check():
    import search
    docs = search.get_index().docs
    bad = 0
    for t in topics():
        body = " ".join(
            d["content"] for d in docs
            if search.law_key(d["law"]) == search.law_key(t["law"])
            and d["article"].startswith(t["ref"]) and not d.get("future"))
        flat = re.sub(r"\s+", "", body)
        if not flat:
            print(f"✗ {t['id']}: 근거 조각을 찾지 못함 ({t['law']} {t['ref']})")
            bad += 1
            continue
        for f in t["facts"]:
            if re.sub(r"\s+", "", f["quote"]) not in flat:
                print(f"✗ {t['id']} {f['label']}: 원문에 없음 → \"{f['quote'][:40]}\"")
                bad += 1
    print("모든 인용이 원문에 있음" if not bad else f"{bad}개 어긋남")
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--check" in sys.argv:
        sys.exit(1 if check() else 0)
    q = " ".join(sys.argv[1:]) or "제조허가 수수료 얼마야?"
    for m in match(q):
        print(m["content"], "\n")
