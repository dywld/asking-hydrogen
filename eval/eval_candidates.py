#!/usr/bin/env python3
"""이용자 질문 기록(chat_log.jsonl)에서 정답셋 후보를 골라낸다.

정답셋 20문항은 손으로 만들었다. 100문항으로 키우려면 실제로 들어온 질문에서
고르는 편이 빠르고, 특히 '검색이 약했다'·'수치가 안 맞았다'·'자료 없음' 이 붙은
질문이 회귀 테스트로 값어치가 있다(고친 뒤 다시 틀리지 않는지 봐야 하니까).

만드는 것: eval_candidates.json — eval_set.json 과 같은 모양이되
  must  : 답변에 있던 수치·기관명을 채워 두었다(사람이 다듬는다)
  ref   : 답변이 실제 인용한 근거 법령
  why   : 왜 후보인지(약함 / 경고 / 반복)
  answer: 그때 답변(대조용)

    python eval_candidates.py            # 후보 뽑기
    python eval_candidates.py --stats    # 기록 통계만
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent   # 프로젝트 최상위(data/, search.py)
LOG = ROOT / "data" / "chat_log.jsonl"
OUT = HERE / "eval_candidates.json"
EXISTING = ["eval_set.json", "eval_set50.json"]

NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:m|㎡|㎥|kg|㎏|톤|일|개월|년|원|%)")
ORG = re.compile(r"(한국가스안전공사|시장|군수|구청장|산업통상자원부|시·도지사|허가관청|중소벤처기업부)")
SKIP = re.compile(r"^(안녕|하이|테스트|test|ㅎㅎ|ㅋㅋ|응|네)")


def load_log():
    if not LOG.exists():
        return []
    rows = []
    for line in LOG.open(encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def known_questions():
    qs = set()
    for name in EXISTING:
        p = HERE / name
        if p.exists():
            qs.update(it["q"].strip() for it in json.loads(p.read_text(encoding="utf-8")))
    return qs


def norm(q):
    return re.sub(r"[\s?？!.~]+", "", q)


def main():
    rows = load_log()
    if "--stats" in sys.argv:
        n = len(rows)
        weak = sum(1 for r in rows if r.get("weak"))
        warn = sum(1 for r in rows if r.get("warnings"))
        models = Counter(r.get("model") for r in rows)
        print(f"기록 {n}건 · 자료없음 {weak} · 경고 {warn}")
        print("모델:", dict(models.most_common(5)))
        return

    known = {norm(q) for q in known_questions()}
    seen = Counter(norm(r.get("q", "")) for r in rows)
    # 👎 받은 질문은 무조건 후보. 사람이 틀렸다고 한 것이니 회귀 테스트 1순위다.
    fb = ROOT / "data" / "feedback.jsonl"
    downs = {}
    if fb.exists():
        for line in fb.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("vote") == "down" and r.get("q"):
                downs[norm(r["q"])] = r.get("reason") or ""
                rows.append({"q": r["q"], "answer": r.get("answer", ""), "t": r.get("t"),
                             "sources": r.get("sources") or [], "warnings": []})
    out, used = [], set()
    for r in rows:
        q = (r.get("q") or "").strip()
        k = norm(q)
        if not q or len(q) < 6 or SKIP.match(q) or k in known or k in used:
            continue
        why = []
        if k in downs:
            why.append("👎 " + (downs[k][:40] or "사유 없음"))
        if r.get("weak"):
            why.append("자료없음 판정")
        if r.get("warnings"):
            why.append("검증 경고")
        if seen[k] >= 2:
            why.append(f"{seen[k]}번 물어봄")
        if not why:
            continue
        used.add(k)
        ans = r.get("answer") or ""
        must = list(dict.fromkeys(NUM.findall(ans)))[:3] or \
            list(dict.fromkeys(ORG.findall(ans)))[:2]
        refs = [re.sub(r"\s*\[.*", "", c).strip() for c in (r.get("cited") or [])]
        laws = list(dict.fromkeys(s.split(" [")[0].split(" 제")[0]
                                  for s in (r.get("sources") or [])[:3]))
        out.append({
            "n": len(out) + 1, "type": "후보", "q": q,
            "must": must, "any": [], "ref": laws[:1],
            "why": " · ".join(why), "answer": ans[:300],
            "warnings": r.get("warnings") or [], "t": r.get("t"),
        })
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"후보 {len(out)}개 → {OUT.name} (must/ref 를 손으로 다듬은 뒤 eval_set 에 옮긴다)")
    for it in out[:15]:
        print(f"  - {it['q'][:40]}  ← {it['why']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
