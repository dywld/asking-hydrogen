#!/usr/bin/env python3
"""추가로 받은 시행령 별표 PDF 를 데이터에 합친다.

액법 시행령·산업융합촉진법 시행령·규제자유특구법 시행령은 본문 PDF 에 별표가
없어 빠져 있었다. fetch_annex_by_lsiseq.py 로 받은 파일을 여기서 조각낸다.
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

from extract_annex import chunk, clean, RELATED, ARTICLE

SRC = Path.home() / "Desktop" / "추가_별표"
OUT = Path(__file__).parent.parent / "data" / "korea_annexes.jsonl"

# 파일명 앞머리 → 기존 본문 데이터와 똑같은 법령명 표기로 맞춘다.
NAMES = {
    "액화석유가스의안전관리및사업법시행령": (
        "액화석유가스의 안전관리 및 사업법 시행령", "액화석유가스 안전관리 및 사업법"),
    "산업융합촉진법시행령": ("산업융합촉진법시행령", "산업융합촉진법"),
    "규제자유특구및지역특화발전특구에관한규제특례법시행령": (
        "규제자유특구및지역특화발전특구에관한규제특례법시행령", "규제자유특구법"),
}
MARK = "추가시행령별표"        # 재실행할 때 이전 결과만 골라 지우는 표시

# 제목은 PDF 본문보다 파일명이 정확하다(본문 첫 줄은 대개 <개정 …> 표시라서).
NAME = re.compile(r"\[별표\s*(?P<no>[\d의]*)\s*\]\s*(?P<title>.*?)\.pdf$")
BODY = re.compile(r"\[별표\s*[\d의]*\s*\]")


def main():
    rows = []
    for pdf in sorted(SRC.glob("*.pdf")):
        key = next((k for k in NAMES if pdf.name.startswith(k)), None)
        if not key:
            print(f"  건너뜀(법령 모름): {pdf.name[:40]}", flush=True)
            continue
        law, group = NAMES[key]

        doc = pymupdf.open(pdf)
        text = "\n".join(p.get_text() for p in doc)
        doc.close()

        head = NAME.search(pdf.name)
        if not head:
            print(f"  건너뜀(형식 불일치): {pdf.name[:40]}", flush=True)
            continue
        no = head.group("no")
        label = f"[별표 {no}]" if no else "[별표]"
        title = clean(head.group("title").replace("_", " "))[:150]
        b = BODY.search(text)
        body = clean(text[b.end():] if b else text)
        if "삭제" in title and len(body) < 200:
            print(f"  건너뜀(삭제된 별표): {label}", flush=True)
            continue

        m = RELATED.search(title + " " + body[:400])
        related = sorted(set(ARTICLE.findall(m.group(1)))) if m else []

        pieces = chunk(body)
        for i, piece in enumerate(pieces, 1):
            rows.append({
                "law": law, "law_group": group, "kind": "별표",
                "annex": label, "title": title,
                "part": f"{i}/{len(pieces)}",
                "related_articles": related,
                "content": f"{law} {label} {title}\n{piece}",
                "source": MARK + "/" + pdf.name,
            })
        print(f"  {law} {label} {title[:35]} → {len(pieces)}조각", flush=True)

    old = OUT.read_text(encoding="utf-8").splitlines() if OUT.exists() else []
    old = [l for l in old if l.strip() and MARK not in l]      # 재실행 대비
    with OUT.open("w", encoding="utf-8") as f:
        for l in old:
            f.write(l + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n별표 {len({(r['law'], r['annex']) for r in rows})}종 / {len(rows)}조각 추가")
    print(f"전체 별표 조각: {len(old) + len(rows)}")


if __name__ == "__main__":
    sys.exit(main())
