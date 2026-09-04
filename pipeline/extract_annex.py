#!/usr/bin/env python3
"""법령 PDF에서 별표·별지 서식을 뽑아 조각내고, 조문과 짝지어 저장한다.

배경: 기존 데이터(korea_laws.jsonl)는 본문(제○조)만 담고 별표를 통째로 버렸다.
인허가 실무에 필요한 수치(안전거리 17m 등)는 전부 별표에 있어서 답변이 막혔다.

원칙: 기존 파일은 건드리지 않는다. 별표만 새 파일(korea_annexes.jsonl)로 만든다.
문제가 생기면 이 파일만 지우면 원래대로 돌아간다.
"""
import os
import json
import re
import sys
from pathlib import Path

import pymupdf

SRC = Path(os.environ.get("LAW_PDF_DIR", str(Path.home() / "Downloads" / "한국")))  # 법령 PDF 폴더
OUT = Path(__file__).parent.parent / "data" / "korea_annexes.jsonl"

# 수소시설 인허가에 직접 걸리는 4개 법부터. 나머지는 팀 협의 후 확장.
TARGET_DIRS = [
    # 수소 인허가 직결 4법 (검색 우선순위 높음)
    "수소법", "고압가스법", "도시가스사업법", "액화석유가스 안전관리 및 사업법",
    # 인허가 과정에서 함께 걸리는 법들
    "건축법", "국토계획법", "대기환경보전법", "소방기본법", "소방시설법",
    "위험물안전관리법", "산업안전보건법", "소음진동법", "에너지이용 합리화법",
    "전기사업법", "환경영향평가법",
]

# 별표 본문 페이지는 '■ ○○법 시행규칙 [별표 8] <개정 …>제목(제8조 관련)' 로 시작한다.
# 별표는 '[별표 8]', 서식은 '[별지 제42호서식]' 처럼 '제'와 '호'가 붙는다.
HEAD = re.compile(r"^■\s*(?P<law>.+?)\s*\[(?P<kind>별표|별지)\s*제?(?P<no>[\d의]+)"
                  r"\s*호?\s*(?P<form>서식)?\]\s*(?:<[^>]*>)?\s*(?P<title>.*)")

# 제목 끝의 '(제8조제1항제4호, 제28조… 관련)' → 어떤 조문이 이 별표를 부르는지
RELATED = re.compile(r"\(([^()]*?제\d+조[^()]*?)\s*관련\)")
ARTICLE = re.compile(r"제\d+조(?:의\d+)?")

# 자를 지점: '1.' → '가.' → '1)' → '가)' 순으로 법령 특유의 번호 체계를 탄다.
SPLIT = re.compile(r"(?=(?:^|\s)(?:\d{1,2}\.\s|[가-힣]\.\s|\d{1,2}\)\s))")

MAX_CHARS = 1400          # 한 조각 최대 길이. 너무 길면 AI 가 통째로 못 읽는다
MIN_CHARS = 120           # 너무 짧은 조각은 앞 조각에 붙인다


def page_texts(pdf):
    doc = pymupdf.open(pdf)
    out = [p.get_text() for p in doc]
    doc.close()
    return out


def collect_blocks(pages):
    """별표·별지가 시작되는 페이지부터 다음 별표 전까지를 한 덩어리로 모은다."""
    blocks, cur = [], None
    for t in pages:
        head = HEAD.match(t.lstrip())
        if head:
            if cur:
                blocks.append(cur)
            cur = {"head": head.groupdict(), "text": t.lstrip()}
        elif cur:
            cur["text"] += "\n" + t
    if cur:
        blocks.append(cur)
    return blocks


def clean(t):
    # 법제처 PDF 는 쪽마다 '법제처  47  국가법령정보센터' 머리글이 박혀 있다.
    t = re.sub(r"법제처\s*\d+\s*국가법령정보센터", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{2,}", "\n", t).strip()


def chunk(body):
    """소제목 단위로 자르되, 조각이 너무 길면 문장 단위로 한 번 더 자른다."""
    parts = [p.strip() for p in SPLIT.split(body) if p.strip()]
    merged = []
    for p in parts:
        if merged and len(merged[-1]) < MIN_CHARS:
            merged[-1] += " " + p
        else:
            merged.append(p)

    out = []
    for p in merged:
        while len(p) > MAX_CHARS:
            cut = p.rfind(" ", 0, MAX_CHARS)
            out.append(p[:cut if cut > MAX_CHARS // 2 else MAX_CHARS])
            p = p[cut if cut > MAX_CHARS // 2 else MAX_CHARS:].strip()
        if p:
            out.append(p)
    return out


def process(pdf, law_group):
    rows = []
    blocks = collect_blocks(page_texts(pdf))
    for b in blocks:
        h = b["head"]
        kind = "별지서식" if h["form"] else h["kind"]
        label = f"[{h['kind']} " + (f"제{h['no']}호서식]" if h["form"]
                                    else f"{h['no']}]")

        body = clean(b["text"])
        # 머리말(■ … 제목) 을 잘라내고 실제 내용만 남긴다
        body = HEAD.sub("", body, count=1).strip()

        title = clean(h["title"])[:150]
        # '(제8조제1항제4호 … 관련)' 은 제목이 길면 다음 줄로 넘어간다.
        # 첫 줄만 보면 연결이 통째로 비어서, 앞부분 400자를 함께 살핀다.
        m = RELATED.search(h["title"] + " " + body[:400])
        related = sorted(set(ARTICLE.findall(m.group(1)))) if m else []

        if "삭제" in title and len(body) < 80:
            continue                        # 삭제된 별표는 담지 않는다

        # 별지 서식은 빈 양식이라 내용이 의미 없다. 이름만 남기고 짧게 유지한다.
        if kind == "별지서식":
            rows.append({
                "law": h["law"], "law_group": law_group, "kind": kind,
                "annex": label, "title": title, "part": "",
                "related_articles": related,
                "content": f"{h['law']} {label} {title}"[:300],
                "source": pdf.name,
            })
            continue

        pieces = chunk(body)
        for i, piece in enumerate(pieces, 1):
            rows.append({
                "law": h["law"], "law_group": law_group, "kind": kind,
                "annex": label, "title": title,
                # 몇 번째 조각인지 남겨야 답변에서 위치를 짚어줄 수 있다
                "part": f"{i}/{len(pieces)}",
                "related_articles": related,
                "content": f"{h['law']} {label} {title}\n{piece}",
                "source": pdf.name,
            })
    return rows


def main():
    all_rows = []
    for d in TARGET_DIRS:
        for pdf in sorted((SRC / d).glob("*.pdf")):
            rows = process(pdf, d)
            all_rows += rows
            n_tbl = len({r["annex"] for r in rows if r["kind"] == "별표"})
            n_frm = len({r["annex"] for r in rows if r["kind"] == "별지서식"})
            print(f"{pdf.name[:40]:42s} 별표 {n_tbl:3d}종 · 서식 {n_frm:3d}종 "
                  f"· 조각 {len(rows):4d}", flush=True)

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    tbl = [r for r in all_rows if r["kind"] == "별표"]
    print(f"\n총 {len(all_rows)}조각 저장 → {OUT.name}")
    print(f"  별표 {len({r['annex'] + r['law'] for r in tbl})}종 / {len(tbl)}조각")
    print(f"  조문 연결이 있는 조각 {sum(1 for r in all_rows if r['related_articles'])}개")


if __name__ == "__main__":
    sys.exit(main())
