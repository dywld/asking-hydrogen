#!/usr/bin/env python3
"""안전거리 계산기 — AI 없이 표에서 바로 찾는다.

"처리능력 1만 5천 ㎥, 제1종보호시설" 처럼 조건이 정해져 있으면 답은 표의 한 칸이다.
모델에게 시키면 가끔 옆 칸을 읽는다. 여기서는 data/distance_tables.json 의 표를
숫자로 찾기만 한다. 표의 값은 원문 조각에서 옮겨 적었고, --check 가 그 값이
원문에 실제로 있는지 대조한다(옮겨 적다 틀리는 것을 막으려고).

    python distance.py --check           # 표의 모든 값이 원문 조각에 있는지 확인
    python distance.py FP216 15000       # 한 번 찾아보기
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
FILE = HERE / "data" / "distance_tables.json"

_tables = None


def tables():
    global _tables
    if _tables is None:
        _tables = json.loads(FILE.read_text(encoding="utf-8"))["tables"]
    return _tables


def summary():
    """화면의 선택 목록용."""
    return [{"id": t["id"], "name": t["name"], "law": t["law"], "ref": t["ref"],
             "unit": t["unit"], "columns": t["columns"]} for t in tables()]


def lookup(table_id, capacity):
    """(표, 용량) → 해당 줄. 용량이 표 밖이면 None."""
    t = next((t for t in tables() if t["id"] == table_id), None)
    if not t:
        return None
    for row in t["rows"]:
        if row["max"] is None or capacity <= row["max"]:
            return {
                "table": t["id"], "name": t["name"], "law": t["law"], "ref": t["ref"],
                "unit": t["unit"], "columns": t["columns"], "capacity": capacity,
                "label": row["label"], "values": row["values"],
                "extra": row.get("extra"), "notes": t["notes"],
                "rows": t["rows"],
            }
    return None


def check():
    """표의 값이 원문 조각에 실제로 있는지 대조한다. 어긋나면 파일명·값을 찍는다."""
    import search
    docs = search.get_index().docs
    bad = 0
    for t in tables():
        # 근거 조각을 모은다: KGS 는 [KGS FP216 2.1.1.1] 항목과 그 다음 항목까지
        # (표가 다음 조각으로 넘어가 있는 경우가 있다 — FP217 이 그랬다).
        if t["law"].startswith("KGS"):
            body = " ".join(d["content"] for d in docs
                            if d["law"] == t["law"]
                            and d["article"].startswith(f"[{t['law']} 2.1.1."))
        else:
            body = " ".join(d["content"] for d in docs
                            if search.law_key(d["law"]) == search.law_key(t["law"])
                            and d["article"].startswith(t["annex"]))
        flat = re.sub(r"\s+", "", body)
        for row in t["rows"]:
            for v in row["values"]:
                if re.sub(r"\s+", "", v) not in flat:
                    print(f"✗ {t['id']} {row['label']}: '{v}' 가 원문에 없음")
                    bad += 1
    print("모든 값이 원문에 있음" if not bad else f"{bad}개 어긋남")
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--check" in sys.argv:
        sys.exit(1 if check() else 0)
    tid = sys.argv[1] if len(sys.argv) > 1 else "FP216"
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 15000
    r = lookup(tid, cap)
    print(json.dumps(r, ensure_ascii=False, indent=1) if r else "표 범위 밖")
