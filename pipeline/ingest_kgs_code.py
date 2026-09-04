#!/usr/bin/env python3
"""KGS Code(상세기준) PDF 를 조각내어 데이터에 넣는다.

법 → 별표 → KGS Code 로 이어지는 마지막 칸이다.
별표가 "상세기준은 KGS Code 에 따른다"에서 끝나므로, 여기까지 있어야
실제 수치로 답할 수 있다.

KGS Code 는 법령과 번호 체계가 다르다(제○조가 아니라 1.1.2 꼴).
그래서 항목 번호를 기준으로 자르고, 조각마다 그 번호를 붙여 인용할 수 있게 한다.
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

from extract_annex import MAX_CHARS, MIN_CHARS, clean

SRC = Path.home() / "Desktop" / "KGS_Code"
OUT = Path(__file__).parent.parent / "data" / "kgs_code.jsonl"

# 파일명: FP216_2026_제조식 수소연료 충전의 시설·기술·검사 기준.pdf
NAME = re.compile(r"^(?P<code>[A-Z]{2}\d{3})_(?P<year>\d{4})_(?P<title>.+)\.pdf$")

# KGS Code 본문 항목 번호: '1.', '2.1', '3.1.2', '4.2.3.1' …
ITEM = re.compile(r"(?m)^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(?=\S)")

# 어느 법의 상세기준인지 — 본문 앞머리에 근거 법령이 적혀 있다.
LAWS = [
    ("수소경제 육성 및 수소 안전관리에 관한 법률", ["수소경제 육성", "수소법"]),
    ("고압가스 안전관리법", ["고압가스 안전관리법", "고압가스안전관리법"]),
    ("액화석유가스의 안전관리 및 사업법", ["액화석유가스의 안전관리", "액화석유가스법"]),
    ("도시가스사업법", ["도시가스사업법"]),
]


# 목차 줄('1.1 적용범위 ……… 1')은 내용이 없다. 점선을 단서로 걸러 낸다.
DOTS = re.compile(r"[·．.]{3,}|…{2,}")


def base_law(text):
    """근거 법령. 앞머리에는 개정 이력만 있어서, 본문 전체에서 가장 많이
    언급된 법을 고른다(코드마다 근거법이 하나씩이라 이걸로 충분하다)."""
    counts = [(sum(text.count(w) for w in words), law) for law, words in LAWS]
    best = max(counts)
    return best[1] if best[0] else ""


def is_toc(body):
    return len(DOTS.findall(body)) >= 3


def split_items(text):
    """항목 번호 단위로 자르고, 너무 길면 더 쪼갠다."""
    marks = list(ITEM.finditer(text))
    if not marks:
        return [(None, text)]
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end].strip()
        if len(body) < MIN_CHARS and out:                # 짧으면 앞에 붙인다
            out[-1] = (out[-1][0], out[-1][1] + " " + body)
            continue
        while len(body) > MAX_CHARS:                     # 너무 길면 잘라 낸다
            cut = body.rfind(" ", 0, MAX_CHARS) or MAX_CHARS
            out.append((m.group(1), body[:cut]))
            body = body[cut:].lstrip()
        out.append((m.group(1), body))
    return out


def main():
    rows = []
    files = sorted(SRC.glob("*.pdf"))
    for n, pdf in enumerate(files, 1):
        m = NAME.match(pdf.name)
        if not m:
            print(f"  건너뜀(이름 형식): {pdf.name[:40]}", flush=True)
            continue
        code, year, title = m.group("code"), m.group("year"), m.group("title")

        doc = pymupdf.open(pdf)
        text = "\n".join(p.get_text() for p in doc)
        doc.close()
        text = clean(text)
        law = base_law(text)

        pieces = [(i, b) for i, b in split_items(text) if not is_toc(b)]
        for item, body in pieces:
            ref = f"[KGS {code} {item}]" if item else f"[KGS {code}]"
            rows.append({
                "code": code, "year": year, "title": title,
                "law": f"KGS {code}", "base_law": law,
                "item": item or "",
                "content": f"KGS {code} {title} {ref}\n{body}",
                "source": pdf.name,
            })
        print(f"  [{n}/{len(files)}] {code} {title[:34]} → {len(pieces)}조각",
              flush=True)

    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nKGS Code {len(files)}종 / {len(rows):,}조각 → {OUT}")


if __name__ == "__main__":
    sys.exit(main())
