#!/usr/bin/env python3
"""확정 자료(fact_tables.json)와 안전거리 표(distance_tables.json)에서 정답셋을 자동으로 만든다.

정답셋을 손으로 쓰면 정답 자체가 틀릴 수 있다. 여기서 만드는 문항은 값이 원문 대조를
통과한 표에서 나오므로 정답이 보증된다. 질문은 값마다 한 개("○○는 얼마야?").

    python eval_from_facts.py          # eval_set_facts.json 생성 + eval_set_all.json 에 합침
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent   # 프로젝트 최상위(data/, search.py)
FACTS = ROOT / "data" / "fact_tables.json"
DIST = ROOT / "data" / "distance_tables.json"
OUT = HERE / "eval_set_facts.json"
ALL = HERE / "eval_set_all.json"

# 주제별 질문 틀. {label} 자리에 값의 이름이 들어간다.
TEMPLATES = {
    "fee_kgs": "{label} 수수료는 얼마야?",
    "fee_h2": "{label} 수수료는 얼마야?",
    "forms_kgs": "{label}은 몇 호 서식으로 해?",
    "special_period": "실증특례 {label}은 어떻게 돼?",
    "special_review": "실증특례 신청 시 {label}은 며칠이야?",
    "distance_fp216": "제조식 수소충전소 처리능력 {label}일 때 보호시설 안전거리는?",
}


def variants(value):
    """'2만 5천원' 이 '2만5천원'·'25,000원' 으로도 나올 수 있다. 어느 하나만 맞아도 인정."""
    v = value.strip()
    out = {v, v.replace(" ", "")}
    m = re.fullmatch(r"(\d)만\s*(\d)천원", v.replace(" ", ""))
    if m:
        out.add(f"{m.group(1)}{m.group(2)},000원")
        out.add(f"{m.group(1)}{m.group(2)}000원")
    m = re.fullmatch(r"(\d)만원", v.replace(" ", ""))
    if m:
        out.add(f"{m.group(1)}0,000원")
    # '제1종 17m · 제2종 12m' → 둘 다 있어야 하니 첫 값만 must 로, 둘째는 any 로
    return sorted(out)


def main():
    items = []
    facts = json.loads(FACTS.read_text(encoding="utf-8"))["topics"]
    for t in facts:
        tpl = TEMPLATES.get(t["id"])
        if not tpl:
            continue
        for f in t["facts"]:
            val = f["value"]
            if not re.search(r"\d", val):        # 수치가 없는 값("표 거리의 2분의 1")은 문항으로 만들지 않는다
                continue
            must, any_ = [], []
            parts = [p.strip() for p in re.split(r"[·,]", val) if p.strip()]
            first = parts[0]
            nums = re.findall(r"\d[\d,.]*\s*(?:m|㎡|㎥|kg|톤|일|개월|년|원|호서식|호 서식)", first)
            must = variants(nums[0]) if nums else variants(first[:12])
            if len(parts) > 1:
                n2 = re.findall(r"\d[\d,.]*\s*(?:m|㎡|㎥|kg|톤|일|개월|년|원)", parts[1])
                any_ = variants(n2[0]) if n2 else []
            items.append({"type": "확정", "q": tpl.format(label=f["label"]),
                          "must": must, "any": any_, "ref": [t["law"]], "src": t["id"]})
    dist = json.loads(DIST.read_text(encoding="utf-8"))["tables"]
    for t in dist:
        if not t["id"].startswith("FP21"):
            continue
        name = "제조식" if t["id"] == "FP216" else "저장식"
        for row in t["rows"][:5]:
            cap = row["max"]
            q = f"{name} 수소충전소 처리능력 {cap:,}일 때 제1종보호시설 안전거리는?"
            items.append({"type": "확정", "q": q, "must": variants(row["values"][0]),
                          "any": variants(row["values"][1]), "ref": [t["law"]], "src": t["id"]})
    for i, it in enumerate(items, 1):
        it["n"] = i
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    # eval_set_all 에 합친다(중복 질문은 건너뜀).
    base = json.loads(ALL.read_text(encoding="utf-8")) if ALL.exists() else []
    base = [b for b in base if b.get("type") != "확정"]
    seen = {re.sub(r"[\s?？!.~,]+", "", b["q"]) for b in base}
    for it in items:
        k = re.sub(r"[\s?？!.~,]+", "", it["q"])
        if k in seen:
            continue
        seen.add(k)
        base.append(dict(it))
    for i, it in enumerate(base, 1):
        it["n"] = i
    ALL.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"확정 문항 {len(items)}개 → {OUT.name} · 합본 {len(base)}문항 → {ALL.name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
