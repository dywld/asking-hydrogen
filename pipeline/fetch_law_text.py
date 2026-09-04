#!/usr/bin/env python3
"""법령 본문(조문)을 국가법령정보센터에서 받아 기존 형식으로 저장한다.

법제처는 조문을 자바스크립트로 그려서 curl 로는 빈 껍데기만 온다.
그래서 크롬을 잠깐 띄워(headless) 화면에 그려진 결과를 받아 쓴다.
크롬은 --dump-dom 이 끝나면 스스로 종료되고, 임시 프로필도 지운다.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT = Path(__file__).parent.parent / "data" / "korea_laws_extra.jsonl"

# 규제특례(실증특례·임시허가·규제자유특구) 근거 법령.
# 계획서의 "규제특례 사례 분석" 항목인데 기존 데이터에 0건이었다.
LAWS = [
    # 규제특례(실증특례·임시허가·규제자유특구) 근거법
    "산업융합촉진법",
    "산업융합촉진법시행령",
    "규제자유특구및지역특화발전특구에관한규제특례법",
    "규제자유특구및지역특화발전특구에관한규제특례법시행령",
    # 팀 원본 데이터에 빠져 있던 두 법 — 부지 용도와 배출시설 신고에 걸린다
    "국토의계획및이용에관한법률",
    "국토의계획및이용에관한법률시행령",
    "대기환경보전법",
    "대기환경보전법시행령",
]

# '제12조(실증을 위한 특례) ① 누구든지 …' 형태로 잘린다.
ARTICLE = re.compile(r"(?m)^\s*(제\d+조(?:의\d+)?)\s*\(([^)]{1,60})\)")


def law_seq(name):
    # 주소에 한글이 들어가므로 경로 전체를 인코딩한다('법령'도 한글이다).
    url = "https://www.law.go.kr/" + urllib.parse.quote(f"법령/{name}")
    with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
            timeout=40) as r:
        page = r.read().decode("utf-8", "replace")
    m = re.search(r"lsiSeq=(\d+)", page)
    return m.group(1) if m else None


def render(url):
    """크롬으로 한 번 그려서 화면 텍스트를 받아온다."""
    prof = tempfile.mkdtemp(prefix="lawdump_")
    try:
        html = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
             "--virtual-time-budget=15000", f"--user-data-dir={prof}",
             "--dump-dom", url],
            capture_output=True, timeout=180).stdout.decode("utf-8", "replace")
    finally:
        shutil.rmtree(prof, ignore_errors=True)   # 임시 프로필은 반드시 치운다

    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    import html as H
    text = H.unescape(text).replace("\xa0", " ")
    text = "\n".join(" ".join(l.split()) for l in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text)


def split_articles(text, law_name):
    """조문 단위로 자른다. 기존 korea_laws.jsonl 과 같은 모양으로 맞춘다."""
    marks = list(ARTICLE.finditer(text))
    rows = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end].strip()
        if len(body) < 30:
            continue
        rows.append({
            "file_name": f"{law_name}.pdf",     # 기존 스키마와 맞추기 위한 표기
            "article": m.group(1),
            "title": m.group(2).strip(),
            "content": body[:6000],
            "effective_date": None,
            "version": "current",
        })
    # 같은 조문이 목차·본문에 두 번 잡히면 긴 쪽만 남긴다.
    best = {}
    for r in rows:
        k = r["article"]
        if k not in best or len(r["content"]) > len(best[k]["content"]):
            best[k] = r
    return list(best.values())


def main():
    all_rows = []
    for name in LAWS:
        seq = law_seq(name)
        if not seq:
            print(f"{name}: 법령번호를 못 찾음", flush=True)
            continue
        url = (f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={seq}"
               f"&chrClsCd=010202&urlMode=lsInfoP&ancYnChk=0")
        text = render(url)
        rows = split_articles(text, name)
        all_rows += rows
        print(f"{name}: 조문 {len(rows)}개", flush=True)

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n총 {len(all_rows)}개 조문 저장 → {OUT.name}")


if __name__ == "__main__":
    sys.exit(main())
