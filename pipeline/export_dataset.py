#!/usr/bin/env python3
"""팀에 넘길 배포용 파일을 만든다.

세 벌을 만든다.
  1) 팀원 원본 그대로 (건드리지 않았음을 보이려고 따로 둔다)
  2) 우리가 추가한 것만
  3) 둘을 합친 것 (실제로 챗봇이 쓰는 것)
합친 파일에는 조각마다 origin(팀원본/추가)을 달아 언제든 되가를 수 있게 한다.
"""
import json
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # 최상위의 search.py 를 찾도록
from search import DATA, load_docs

OUT_DIR = Path(__file__).parent.parent / "배포"

# 어느 원본 파일에서 온 조각인지 → 누가 만든 것인지
ORIGIN = {
    "korea_laws.jsonl": "팀원본",
    "japan_laws.jsonl": "팀원본",
    "korea_laws_extra.jsonl": "추가",
    "korea_annexes.jsonl": "추가",
    "gangwon_zone.jsonl": "추가",
}


def origin_of(doc):
    """조각이 어느 파일에서 왔는지 되짚는다(load_docs 는 출처를 남기지 않는다)."""
    if doc["country"] == "일본":
        return "팀원본"
    if doc.get("kind"):                       # 별표·별지서식은 전부 우리가 넣은 것
        return "추가"
    if doc["law"] in EXTRA_LAWS or doc["source"] in GANGWON:
        return "추가"
    return "팀원본"


def row(i, d):
    return {
        "id": i,
        "origin": origin_of(d),                # 팀원본 / 추가
        "country": d["country"],
        "law": d["law"],                       # 법령명
        "article": d["article"],               # 제○조 또는 [별표 ○]
        "title": d["title"],
        "kind": d.get("kind") or "조문",        # 조문 / 별표 / 별지서식
        "facility": d.get("facility") or [],   # 생산·저장·운반·충전·사용·판매
        "related_articles": d.get("related") or [],   # 별표를 부르는 조문
        "content": d["content"],
        "source": d["source"],
    }


def write(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + chr(10))
    return f"{path.name}  {len(rows):,}조각  {path.stat().st_size / 1048576:.1f} MB"


def main():
    OUT_DIR.mkdir(exist_ok=True)
    global EXTRA_LAWS, GANGWON
    EXTRA_LAWS = {json.loads(l)["file_name"].replace(".pdf", "")
                  for l in (DATA / "korea_laws_extra.jsonl").open(encoding="utf-8")}
    GANGWON = {json.loads(l)["file_name"]
               for l in (DATA / "gangwon_zone.jsonl").open(encoding="utf-8")}

    rows = [row(i, d) for i, d in enumerate(load_docs(), 1)]
    team = [r for r in rows if r["origin"] == "팀원본"]
    ours = [r for r in rows if r["origin"] == "추가"]

    print(write(OUT_DIR / "1_팀원본_법령DB.jsonl", team))
    print(write(OUT_DIR / "2_추가분_별표및법령.jsonl", ours))
    print(write(OUT_DIR / "3_전체_합본.jsonl", rows))


if __name__ == "__main__":
    sys.exit(main())
