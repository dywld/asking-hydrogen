#!/usr/bin/env python3
"""cf/public 을 만든다: 루트의 화면 파일 + cf/public_extra(서류 만들기 shim·서식 자료).

  1) 루트 index.html·review.html·demo.html·checklist.html·rules.html·package.html 을 cf/public 에 복사하면서,
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
# 팀원 도구 화면(자체점검표·안전관리규정·제출 꾸러미)은 cf-tools.js 도 붙인다(cf-shim 다음).
TOOLS = '<script src="/cf-tools.js"></script>'
TOOL_PAGES = ("checklist.html", "rules.html", "package.html", "site3d.html")
# 첫 화면은 처음 설정(온보딩) 화면도 붙인다. 화면 코드가 다 돈 뒤에 뜨도록 defer.
ONBOARD = '<script src="/onboard.js" defer></script>'
ICON = '<link rel="icon" href="/brand/favicon.png"><link rel="apple-touch-icon" href="/brand/apple-touch-icon.png">'
LIMIT = 25 * 1024 * 1024          # 워커 정적 자산 한 파일 한도


def inject(html, tools=False):
    tag = TAG + ("\n" + TOOLS if tools else "")
    if TAG in html:
        return html
    i = html.find("<script")
    if i < 0:
        j = html.lower().find("</head>")
        i = j if j >= 0 else 0
    return html[:i] + tag + "\n" + html[i:]


def main():
    PUB.mkdir(exist_ok=True)
    for name in ("index.html", "review.html", "demo.html") + TOOL_PAGES:
        src = ROOT / name
        if src.exists():
            html = inject(src.read_text(encoding="utf-8"), name in TOOL_PAGES)
            # 탭 아이콘(마스코트). 화면 파일에 이미 있으면 두지 않는다.
            if 'rel="icon"' not in html and "</head>" in html:
                html = html.replace("</head>", ICON + "\n</head>", 1)
            if name == "index.html" and ONBOARD not in html:
                html = html.replace("</body>", ONBOARD + "\n</body>", 1) if "</body>" in html else html + ONBOARD
            (PUB / name).write_text(html,
                                    encoding="utf-8", newline="")
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
    # 윈도우 앱이 켤 때 보는 화면 버전. 공개 파일 내용이 바뀌면 id 가 바뀌고, 앱이 '업데이트가 있어요!'를 띄운다.
    import hashlib, json, datetime
    h = hashlib.sha256()
    for p in sorted(PUB.rglob("*")):
        if p.is_file() and p.name != "version.json":
            h.update(str(p.relative_to(PUB)).encode()); h.update(p.read_bytes())
    vid = h.hexdigest()[:12]
    old = {}
    try:
        old = json.loads((PUB / "version.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    label = old.get("label") if old.get("id") == vid else datetime.date.today().strftime("%Y.%m.%d")
    (PUB / "version.json").write_text(json.dumps({"id": vid, "label": label}), encoding="utf-8")
    print("version", vid, label)


if __name__ == "__main__":
    main()
