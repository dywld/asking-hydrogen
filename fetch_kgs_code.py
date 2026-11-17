#!/usr/bin/env python3
"""KGS Code(상세기준) PDF 를 가스기술기준정보시스템에서 받아온다.

왜 필요한가: 법 → 별표 → KGS Code 로 세 번 넘어간다.
  법 본문   "시설기준은 별표 8과 같다"
  별표 8    "상세기준은 KGS Code 에 따른다"
  KGS Code  실제 최종 수치            ← 여기가 비어 있었다
별표까지만 넣으면 마지막 한 칸에서 또 "코드에 따른다"로 끝난다.

목록(19쪽)을 훑어 PDF 경로를 모으고, 로그인 없이 그대로 내려받는다.
"""
import re
import html as html_lib
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = "https://cyber.kgs.or.kr"
LIST = f"{BASE}/kgscode.codeSearch.listV2.ex.do"
DOWN = f"{BASE}/cmm/fms/kgsFileDown.ex.do"
OUT_DIR = Path.home() / "Desktop" / "KGS_Code"

# 목록 한 줄 = 분야 + 코드번호/제목 + PDF 경로.
# 줄마다 모양이 조금씩 달라서 통째로 정규식 하나로 잡지 않고, <tr> 로 나눈 뒤
# 조각마다 필요한 것만 뽑는다(그렇게 안 하면 일부 줄을 놓친다 — 실측 6/10건).
# 최신 코드에는 연도 뒤에 new 아이콘(<img>)이 끼어든다.
CODE = re.compile(r"KGS\s+([A-Z]{2}\d{3})\s+(\d{4})\s*(?:<[^>]+>\s*)*<p>([^<]*)</p>", re.S)
PATH = re.compile(r"file_nm=(kgscode_pdf/[^&]+\.pdf)")
FIELD = re.compile(r"<td>\s*([^<>]{2,30}?)\s*(?:&nbsp;)?>", re.S)


def parse(html):
    out = []
    for tr in html.split("<tr")[1:]:
        c, f = CODE.search(tr), PATH.search(tr)
        if not (c and f):
            continue
        fld = FIELD.search(tr)
        date = re.search(r"(?<!\d)(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})(?!\d)",
                         re.sub(r"<[^>]+>", " ", tr))
        out.append({"field": fld.group(1).strip() if fld else "",
                    "code": c.group(1), "year": c.group(2),
                    "title": html_lib.unescape(c.group(3)).strip(),
                    "path": html_lib.unescape(f.group(1)),
                    "revised_on": (f"{date[1]}-{int(date[2]):02d}-{int(date[3]):02d}"
                                   if date else None)})
    return out


opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(CookieJar()))
opener.addheaders = [
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
    ("Referer", LIST)]


def page(i):
    with opener.open(f"{LIST}?pageIndex={i}", timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def download(path):
    data = urllib.parse.urlencode(
        {"file_nm": path, "file_folder": "codeLink"}).encode()
    with opener.open(urllib.request.Request(DOWN, data=data), timeout=180) as r:
        blob = r.read()
    return blob if blob.startswith(b"%PDF") else None


class KgsClient:
    """수집할 때마다 독립 세션을 사용한다. 차단·로그인 오류는 그대로 보고한다."""

    def __init__(self, timeout=60, pace=0.5, max_pages=100):
        self.timeout, self.pace, self.max_pages = timeout, pace, max_pages
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()))
        self.opener.addheaders = [("User-Agent", "asking-hydrogen-kgs-watch/1.0"),
                                  ("Referer", LIST)]

    def list_codes(self, wanted=None):
        with self.opener.open(f"{BASE}/kgscode.Index.do", timeout=self.timeout) as r:
            r.read()
        items, seen = [], set()
        for i in range(1, self.max_pages + 1):
            with self.opener.open(f"{LIST}?pageIndex={i}", timeout=self.timeout) as r:
                html = r.read().decode("utf-8", "replace")
            rows = parse(html)
            if not rows:
                plain = re.sub(r"<[^>]+>", " ", html)
                if items and re.search(r"(?:검색|조회|등록).{0,25}(?:결과|자료|코드).{0,15}없", plain):
                    return items
                # 빈 HTML/로그인 화면을 '변경 없음'으로 기록하지 않는다.
                raise RuntimeError(f"KGS 목록 {i}쪽 해석 실패: 기존 데이터는 유지합니다")
            fresh = [r for r in rows if r["code"] not in seen]
            if not fresh:                 # 기존 수집기와 같은 마지막 쪽 판별
                return items
            items.extend(fresh)
            seen.update(r["code"] for r in fresh)
            if wanted and set(wanted).issubset(seen):
                return items
            time.sleep(self.pace)
        raise RuntimeError("KGS 목록 페이지 상한 초과: 불완전한 목록은 적용하지 않습니다")

    def download(self, item):
        path = item["path"]
        decoded = urllib.parse.unquote(path)
        if (not re.fullmatch(r"kgscode_pdf/[A-Za-z0-9_./%가-힣 ()-]+\.pdf", path)
                or ".." in decoded or not decoded.startswith("kgscode_pdf/")):
            raise ValueError("공식 PDF 경로 형식이 아닙니다")
        data = urllib.parse.urlencode({"file_nm": path, "file_folder": "codeLink"}).encode()
        with self.opener.open(urllib.request.Request(DOWN, data=data), timeout=self.timeout) as r:
            blob = r.read(50 * 1024 * 1024 + 1)
        if len(blob) > 50 * 1024 * 1024 or not blob.startswith(b"%PDF"):
            raise ValueError("다운로드 결과가 PDF가 아니거나 50MB를 초과합니다")
        time.sleep(self.pace)
        return blob


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    opener.open(f"{BASE}/kgscode.Index.do", timeout=60).read()   # 세션 발급

    items, seen = [], set()
    for i in range(1, 40):
        html = page(i)
        rows = parse(html)
        fresh = [r for r in rows if r["code"] not in seen]
        if not fresh:
            break
        for r in fresh:
            seen.add(r["code"])
        items += fresh
        print(f"목록 {i}쪽 … 누적 {len(items)}건", flush=True)
        time.sleep(0.2)

    print(f"\n총 {len(items)}건 내려받기 시작\n", flush=True)
    ok = 0
    for n, it in enumerate(items, 1):
        # 제목에 줄바꿈이 든 코드가 있다(실측: AA917). 파일명에 그대로 쓰면
        # 윈도우에서 열리지 않아 저장이 통째로 실패한다.
        title = " ".join(it["title"].split())
        name = re.sub(r'[\/:*?"<>|]', "_",
                      f"{it['code']}_{it['year']}_{title}").strip()[:120]
        out = OUT_DIR / f"{name}.pdf"
        if out.exists():
            ok += 1
            continue
        try:
            blob = download(it["path"])
        except Exception as e:
            print(f"  [{n}/{len(items)}] 실패 {it['code']}: {e}", flush=True)
            continue
        if not blob:
            print(f"  [{n}/{len(items)}] PDF 아님 {it['code']}", flush=True)
            continue
        out.write_bytes(blob)
        ok += 1
        print(f"  [{n}/{len(items)}] {it['code']} {it['title'][:40]} "
              f"({len(blob) // 1024}KB)", flush=True)
        time.sleep(0.3)              # 공공 사이트라 몰아치지 않는다

    print(f"\n{ok}/{len(items)}건 저장 → {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
