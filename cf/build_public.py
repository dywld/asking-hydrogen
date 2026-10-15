#!/usr/bin/env python3
"""cf/public 을 만든다: 루트의 화면 파일 + cf/public_extra(서류 만들기 shim·서식 자료).

  1) 루트 index.html·review.html·demo.html 을 cf/public 에 복사하면서,
     첫 <script> 앞에 <script src="/cf-shim.js"></script> 를 넣는다
     (fetch 를 감싸 서류 만들기 요청을 브라우저에서 처리한다. 화면 파일은 고치지 않는다).
  2) cf/public_extra/* 를 cf/public 에 그대로 복사한다.

서식 자료가 없으면 먼저 python cf/export_docs.py 를 돌린다.
"""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PUB = HERE / "public"
EXTRA = HERE / "public_extra"
TAG = '<script src="/cf-shim.js"></script>'
LIMIT = 25 * 1024 * 1024          # 워커 정적 자산 한 파일 한도


def inject(html):
    if TAG in html:
        return html
    i = html.find("<script")
    if i < 0:
        j = html.lower().find("</head>")
        i = j if j >= 0 else 0
    return html[:i] + TAG + "\n" + html[i:]


def main():
    PUB.mkdir(exist_ok=True)
    for name in ("index.html", "review.html", "demo.html"):
        src = ROOT / name
        if src.exists():
            (PUB / name).write_text(inject(src.read_text(encoding="utf-8")), encoding="utf-8", newline="")
            print("html", name)
    if not (EXTRA / "docs" / "layout.json").exists():
        raise SystemExit("cf/public_extra/docs/layout.json 이 없습니다. 먼저 python cf/export_docs.py")
    n = 0
    for p in EXTRA.rglob("*"):
        if p.is_file():
            if p.stat().st_size > LIMIT:
                raise SystemExit(f"자산 한도(25MB) 초과: {p}")
            dst = PUB / p.relative_to(EXTRA)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            n += 1
    print("extra files", n)


if __name__ == "__main__":
    main()
