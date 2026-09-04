#!/usr/bin/env python3
"""국가법령정보센터에서 별표 파일을 직접 받아온다.

왜 필요한가: 액화석유가스법은 다른 법과 제공 방식이 다르다.
고압가스법·수소법은 별표가 본문 PDF 안에 들어 있지만, 액법은 본문 36쪽에
별표가 아예 없고 별표마다 개별 PDF 로 따로 준다. 그래서 PDF 를 아무리 다시
받아도 별표가 안 나온다(팀이 받은 파일도 정상이었다).

동작: 법령 본문 페이지에서 별표 링크 번호를 긁고 → 각 별표 상세에서 PDF 파일
번호를 찾아 → 내려받아 저장한다.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = "https://www.law.go.kr/LSW"
OUT_DIR = Path.home() / "Desktop" / "액법_별표"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# 대상 법령 (lsiSeq 는 법령 주소에서 얻은 고유번호)
TARGETS = [
    ("액화석유가스의 안전관리 및 사업법", 276549),
    ("액화석유가스의 안전관리 및 사업법 시행령", 278387),
    ("액화석유가스의 안전관리 및 사업법 시행규칙", 282369),
]

# fncLsLawPop('1031500315','BE','') → BE=별표, BF=별지서식
POP = re.compile(r"fncLsLawPop\('(\d+)','(B[EF])'")
PDF_SEQ = re.compile(r'id="pdfFlSeq"[^>]*value="(\d+)"')
TITLE = re.compile(r"<title>([^<]*)</title>")

opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(CookieJar()))
opener.addheaders = [("User-Agent", UA), ("Referer", "https://www.law.go.kr/")]


def get(url, binary=False):
    with opener.open(url, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def annex_links(lsi_seq):
    """별표 링크 목록. 본문 HTML 에는 없고 자바스크립트가 그려 넣기 때문에,
    브라우저에서 한 번 긁어 둔 목록 파일을 읽어 쓴다."""
    f = Path(__file__).parent / "seqs" / f"seqs_{lsi_seq}.txt"
    if not f.exists():
        return []
    out = []
    for tok in f.read_text(encoding="utf-8").split():
        seq, _, kind = tok.partition(",")
        if seq.isdigit():
            out.append((seq, kind))
    return out


def fetch_one(link_seq, law, kind):
    """별표 하나: 링크 → 상세(AJAX) → PDF 번호 → 파일 저장.

    pdfFlSeq 는 첫 페이지에 없고 lsBylInfoR.do 응답에 들어 있다.
    (첫 페이지만 긁으면 0개가 나온다 — 실제로 그렇게 헛돌았다.)
    """
    page = get(f"{BASE}/lsLawLinkInfo.do?lsJoLnkSeq={link_seq}")
    byl = re.search(r'id="bylSeq"[^>]*value="(\d+)"', page)
    lsi = re.search(r'id="lsiSeq"[^>]*value="(\d+)"', page)
    if not byl:
        return None, None
    t = TITLE.search(page)
    title = html.unescape(t.group(1)) if t else f"별표_{link_seq}"
    title = title.replace("| 국가법령정보센터", "").replace("별표·서식 >", "").strip()

    data = urllib.parse.urlencode({
        "bylSeq": byl.group(1), "lsiSeq": lsi.group(1) if lsi else "",
        "vSct": "", "efYd": ""}).encode()
    req = urllib.request.Request(f"{BASE}/lsBylInfoR.do", data=data)
    with opener.open(req, timeout=60) as r:
        detail = r.read().decode("utf-8", "replace")

    m = PDF_SEQ.search(detail)
    if not m:
        return None, None                       # 한글파일만 있는 별표
    blob = get(f"{BASE}/flDownload.do?flSeq={m.group(1)}", binary=True)
    if not blob.startswith(b"%PDF"):
        return None, None
    safe = re.sub(r'[\/:*?"<>|]', "_", title)[:120]
    path = OUT_DIR / f"{safe}.pdf"
    path.write_bytes(blob)
    return path, title


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for law, lsi in TARGETS:
        links = annex_links(lsi)
        print(f"\n{law}: 별표·서식 링크 {len(links)}개", flush=True)
        for i, (seq, kind) in enumerate(links, 1):
            try:
                path, title = fetch_one(seq, law, kind)
            except Exception as e:
                print(f"  [{i}/{len(links)}] 실패 {seq}: {e}", flush=True)
                continue
            if path:
                saved.append({"law": law, "kind": kind, "title": title,
                              "path": str(path)})
                print(f"  [{i}/{len(links)}] {title[:50]} "
                      f"({path.stat().st_size // 1024}KB)", flush=True)
            time.sleep(0.3)      # 공공 사이트라 너무 몰아치지 않는다

    (OUT_DIR / "목록.json").write_text(
        json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {len(saved)}개 저장 → {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
