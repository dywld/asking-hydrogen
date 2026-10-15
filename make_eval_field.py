#!/usr/bin/env python3
"""현장 질문 채점 세트 — 가스신문 '실무질의'(사업자 질문 + 가스안전공사 답변)에서 만든다.

공사 답변에 나온 법령(「…」)·KGS 코드 중 우리 자료에 있는 것을 정답 근거(ref)로 삼는다.
근거를 하나도 못 짚는 문항은 뺀다(채점할 기준이 없으니까).

    python make_eval_field.py      # → eval_set_field.json
    python eval_run.py eval_set_field.json --retrieval
"""
import json
import re
import sys
from pathlib import Path

import openpyxl

import search

HERE = Path(__file__).parent
SRC = HERE / "문서" / "수소사업자_질문애로_수집.xlsx"
OUT = HERE / "eval_set_field.json"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    laws = {d["law"] for d in search.get_index().docs}
    ws = openpyxl.load_workbook(SRC, read_only=True)["실무질의_공사답변"]
    items = []
    for row in list(ws.iter_rows(min_row=2, values_only=True)):
        _, kind, title, q, a = (row + (None,) * 5)[:5]
        if not (title and a):
            continue
        refs = set()
        for name in re.findall(r"「([^」]{2,40})」", a):
            name = re.sub(r"\s+", " ", name).strip()
            if name in laws:
                refs.add(name)
        for code in re.findall(r"KGS\s?([A-Z]{2}\d{3})", a):
            if any(code in l for l in laws):
                refs.add(code)
        if not refs:
            continue
        body = re.sub(r"\s+", " ", q or "").strip()
        question = f"{title.strip()} {body[:160]}".strip()
        arts = re.findall(r"제\d+조(?:의\d+)?", a)
        items.append({"n": len(items) + 1, "type": kind or "실무", "q": question,
                      "must": sorted(set(arts))[:3] or sorted(refs)[:1],
                      "ref": sorted(refs)})
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)}문항 → {OUT.name}")


if __name__ == "__main__":
    main()
