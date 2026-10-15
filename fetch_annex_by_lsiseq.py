#!/usr/bin/env python3
"""법령번호(lsiSeq) 하나로 그 법령의 별표 PDF 를 전부 받아온다.

fetch_annex_web.py 는 별표마다 링크번호를 미리 긁어 둔 목록(seqs/)이 필요했다.
여기서는 별표 팝업 첫 페이지의 <select id="bylList"> 에 모든 별표의 bylSeq 가
들어 있는 것을 이용해, 목록 파일 없이 곧바로 훑는다.
"""
import html as H
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from fetch_law_text import law_seq

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "https://www.law.go.kr/LSW"
OUT_DIR = Path.home() / "Desktop" / "추가_별표"

LAWS = [
    "액화석유가스의안전관리및사업법시행령",
    "산업융합촉진법시행령",
    "규제자유특구및지역특화발전특구에관한규제특례법시행령",
]

OPTION = re.compile(r'<option value="(\d+),[^"]*"[^>]*>\s*(\[별표[^<]*)</option>')
PDF_SEQ = re.compile(r'id="pdfFlSeq"[^>]*value="(\d+)"')

opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(CookieJar()))
opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                     ("Referer", "https://www.law.go.kr/")]


def dump(url):
    """별표 목록은 자바스크립트가 그리므로 크롬을 잠깐 띄워 받는다."""
    prof = tempfile.mkdtemp(prefix="bylдump_")
    try:
        return subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
             "--virtual-time-budget=15000", f"--user-data-dir={prof}",
             "--dump-dom", url],
            capture_output=True, timeout=180).stdout.decode("utf-8", "replace")
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def pdf_of(byl_seq, lsi_seq):
    """별표 하나의 PDF. pdfFlSeq 도 자바스크립트가 채우므로 크롬으로 받는다."""
    page = dump(f"{BASE}/lsBylInfoPLinkR.do?lsiSeq={lsi_seq}&bylSeq={byl_seq}")
    m = PDF_SEQ.search(page)
    if not m:
        return None                                  # 한글파일만 있는 별표
    with opener.open(f"{BASE}/flDownload.do?flSeq={m.group(1)}", timeout=60) as r:
        blob = r.read()
    return blob if blob.startswith(b"%PDF") else None


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for name in LAWS:
        lsi = law_seq(name)
        if not lsi:
            print(f"{name}: 법령번호 못 찾음", flush=True)
            continue
        page = dump(f"{BASE}/lsBylInfoPLinkR.do?lsiSeq={lsi}")
        items = list(dict.fromkeys(OPTION.findall(page)))
        print(f"\n{name} (lsiSeq={lsi}): 별표 {len(items)}개", flush=True)
        for byl, title in items:
            title = H.unescape(title).strip()
            try:
                blob = pdf_of(byl, lsi)
            except Exception as e:
                print(f"  실패 {title[:40]}: {e}", flush=True)
                continue
            if not blob:
                print(f"  PDF 없음 {title[:40]}", flush=True)
                continue
            safe = re.sub(r'[\/:*?"<>|]', "_", f"{name}{title}")[:120]
            path = OUT_DIR / f"{safe}.pdf"
            path.write_bytes(blob)
            saved.append({"law": name, "title": title, "path": str(path)})
            print(f"  {title[:50]} ({len(blob) // 1024}KB)", flush=True)
            time.sleep(0.3)                       # 공공 사이트라 몰아치지 않는다

    (OUT_DIR / "목록.json").write_text(
        json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {len(saved)}개 저장 → {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
