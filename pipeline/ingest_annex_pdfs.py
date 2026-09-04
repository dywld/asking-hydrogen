#!/usr/bin/env python3
"""개별 별표 PDF(액법 등)를 잘라서 기존 별표 데이터에 합친다.

법령 본문 PDF 안에 별표가 들어 있는 법(고압가스·수소·도시가스)은 extract_annex.py 가
처리한다. 여기서는 별표를 파일 하나씩 따로 주는 법(액화석유가스법)을 다룬다.
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

from extract_annex import chunk, clean, RELATED, ARTICLE

SRC = Path.home() / "Desktop" / "액법_별표"
OUT = Path(__file__).parent.parent / "data" / "korea_annexes.jsonl"
LAW_GROUP = "액화석유가스 안전관리 및 사업법"

# 파일 첫 줄이 '■액화석유가스의안전관리및사업법시행규칙[별표1] <개정 …> 제목(제○조 관련)'
HEAD = re.compile(r"■\s*(?P<law>[^\[]+)\[(?P<kind>별표|별지)\s*(?P<no>[\d의]+)"
                  r"\s*호?\s*(?P<form>서식)?\]\s*(?:<[^>]*>)?\s*(?P<title>.*)")


def spaced(law):
    """'액화석유가스의안전관리및사업법시행규칙' → 기존 데이터와 같은 띄어쓰기로."""
    law = law.strip()
    law = law.replace("액화석유가스의안전관리및사업법", "액화석유가스의 안전관리 및 사업법")
    for suffix in ("시행규칙", "시행령"):
        law = law.replace(suffix, " " + suffix)
    return " ".join(law.split())


def main():
    rows = []
    for pdf in sorted(SRC.glob("*.pdf")):
        doc = pymupdf.open(pdf)
        text = "\n".join(p.get_text() for p in doc)
        doc.close()

        head = HEAD.search(text)
        if not head:
            print(f"  건너뜀(형식 불일치): {pdf.name[:40]}", flush=True)
            continue
        h = head.groupdict()
        law = spaced(h["law"])
        label = f"[{h['kind']} " + (f"제{h['no']}호서식]" if h["form"]
                                    else f"{h['no']}]")
        title = clean(h["title"])[:150]
        body = clean(text[head.end():])

        m = RELATED.search(h["title"] + " " + body[:400])
        related = sorted(set(ARTICLE.findall(m.group(1)))) if m else []

        pieces = chunk(body)
        for i, piece in enumerate(pieces, 1):
            rows.append({
                "law": law, "law_group": LAW_GROUP,
                "kind": "별지서식" if h["form"] else "별표",
                "annex": label, "title": title,
                "part": f"{i}/{len(pieces)}",
                "related_articles": related,
                "content": f"{law} {label} {title}\n{piece}",
                "source": pdf.name,
            })
        print(f"  {label} {title[:40]} → {len(pieces)}조각", flush=True)

    # 기존 파일 뒤에 이어 붙인다(고압가스·수소·도시가스 별표는 그대로 둔다).
    old = OUT.read_text(encoding="utf-8").splitlines() if OUT.exists() else []
    old = [l for l in old if l.strip() and LAW_GROUP not in l]   # 재실행 대비
    with OUT.open("w", encoding="utf-8") as f:
        for l in old:
            f.write(l + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n액법 별표 {len({r['annex'] for r in rows})}종 / {len(rows)}조각 추가")
    print(f"전체 별표 조각: {len(old) + len(rows)}")


if __name__ == "__main__":
    sys.exit(main())
