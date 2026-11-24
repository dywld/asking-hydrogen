"""Windows 브라우저로 KGS 기준 한 건을 확인하고 기존 갱신기에 전달한다."""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import pymupdf
from playwright.sync_api import Error as BrowserError, sync_playwright

from fetch_kgs_code import BASE, LIST, parse
from kgs_cloud import Cloud, DEFAULT_URL, publish
from kgs_watch import CODE, Watcher, now, write_json

LIST_CODE = re.compile(r"\bKGS\s*([A-Z]{2}\d{3})\s*[-:(]?\s*(20\d{2})\b", re.I)
MAX_BYTES = 50 * 1024 * 1024


def official(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname == urlsplit(BASE).hostname and parsed.port in (None, 443)


def visit(page, url):
    response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    if response is None or not official(page.url):
        raise ValueError("KGS 공식 페이지를 열지 못했습니다.")
    if not response.ok:
        raise ValueError(f"KGS 접속 오류 HTTP {response.status}")
    message = page.title() + "\n" + page.locator("body").inner_text()[:1200]
    if re.search(r"접근이 차단|접속이 차단|자동화된 요청|verify you are human|access denied", message, re.I):
        raise ValueError("KGS 사이트가 접속 제한 또는 사람 확인을 표시했습니다.")


def find_row(page, code):
    pattern = re.compile(rf"\bKGS\s*{code}\s*[-:(]?\s*(20\d{{2}})\b", re.I)
    seen = set()
    for number in range(1, 101):
        query = f"pblcCd={code}" if number == 1 else f"pageIndex={number - 1}"
        visit(page, f"{LIST}?{query}")
        rows = page.locator("tr:visible").filter(has_text=LIST_CODE)
        rows.first.wait_for(timeout=8_000)
        matching = rows.filter(has_text=pattern)
        count = matching.count()
        if count == 1:
            row = matching.first
            year = pattern.search(row.inner_text()).group(1)
            return row, year
        if count > 1:
            raise ValueError(f"{code}가 여러 줄이어서 어느 판인지 확인해야 합니다.")
        signature = tuple(rows.all_inner_texts())
        if number > 2 and signature in seen:
            break
        seen.add(signature)
        time.sleep(0.6)
    raise ValueError(f"공식 목록에서 {code}를 찾지 못했습니다.")


def pdf_button(row):
    actions = row.locator("a:visible, button:visible, input[type=image]:visible, input[type=button]:visible")
    named = re.compile(r"PDF|다운로드|내려받기|원문\s*받기", re.I)
    candidates = [
        actions.and_(row.locator('[href*="kgscode_pdf" i], [onclick*="kgscode_pdf" i]')),
        row.get_by_role("link", name=named).or_(row.get_by_role("button", name=named)).and_(actions),
    ]
    for group in candidates:
        count = group.count()
        if count == 1:
            return group.first
        if count > 1:
            raise ValueError("다운로드 버튼이 여러 개입니다.")
    raise ValueError("기준의 PDF 다운로드 버튼을 찾지 못했습니다.")


def validated_pdf(path, item):
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("파일이 비었거나 50MB를 초과했습니다.")
    blob = path.read_bytes()
    if not blob.startswith(b"%PDF-"):
        raise ValueError("다운로드 결과가 PDF가 아닙니다.")
    with pymupdf.open(stream=blob, filetype="pdf") as doc:
        if doc.needs_pass or not doc.page_count:
            raise ValueError("암호화되었거나 빈 PDF입니다.")
        match = LIST_CODE.search(doc[0].get_text())
        if not match or (match[1].upper(), match[2]) != (item["code"], item["year"]):
            raise ValueError("공식 목록과 PDF 표지의 기준 번호 또는 연도가 다릅니다.")
    return blob


class BrowserSource:
    """Watcher가 목록과 원문을 같은 브라우저 탭에서 차례로 가져오도록 연결한다."""
    def __init__(self, page, folder):
        self.page = page
        self.folder = folder

    def list_codes(self, wanted):
        code, = wanted  # 실행 한 번에 지정한 기준 한 건
        visit(self.page, BASE + "/kgscode.Index.do")
        row, year = find_row(self.page, code)
        self.row = row
        items = parse(row.evaluate("(el) => el.outerHTML"))
        for item in items:
            if item["code"] == code and item["year"] == year:
                return [item]
        # 경로를 onclick 등에 숨기는 목록도 화면의 제목과 표지로 대조한다.
        titles = row.locator("p:visible")
        title = titles.first.inner_text().strip() if titles.count() else ""
        if not title:
            raise ValueError("공식 목록에서 기준 제목을 확인할 수 없습니다.")
        listed = row.inner_text()
        dates = re.findall(r"(?<!\d)(20\d{2})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})(?!\d)", listed)
        revised = None
        if len(set(dates)) == 1:
            y, m, d = dates[0]
            revised = f"{y}-{int(m):02d}-{int(d):02d}"
        return [{"code": code, "year": year, "title": title, "revised_on": revised,
                 "path": f"{LIST}?pblcCd={code}"}]

    def download(self, item):
        button = pdf_button(self.row)
        downloads = []

        def listen(page):
            page.on("download", downloads.append)

        listen(self.page)
        self.page.context.on("page", listen)
        button.click(timeout=12_000)
        deadline = time.monotonic() + 60
        while not downloads and time.monotonic() < deadline:
            self.page.wait_for_timeout(150)
        if not downloads:
            raise ValueError("1분 안에 PDF 다운로드가 시작되지 않았습니다.")
        download = downloads[0]
        if not official(download.url):
            raise ValueError("KGS 공식 다운로드 출처를 확인할 수 없습니다.")
        path = self.folder / "received.pdf"
        download.save_as(path)
        return validated_pdf(path, item)


def sync_browser(root, code, publish_to_web):
    with tempfile.TemporaryDirectory(prefix="kgs-daily-") as temp, sync_playwright() as pw:
        folder = Path(temp)
        profile = folder / "profile"
        prefs = profile / "Default" / "Preferences"
        prefs.parent.mkdir(parents=True)
        prefs.write_text('{"plugins":{"always_open_pdf_externally":true}}', encoding="utf-8")
        for channel in ("chrome", "msedge"):
            try:
                context = pw.chromium.launch_persistent_context(
                    str(profile), channel=channel, headless=False, accept_downloads=True)
                break
            except BrowserError as e:
                if "not found" not in str(e).lower() and "doesn't exist" not in str(e).lower():
                    raise
        else:
            raise ValueError("Chrome 또는 Edge가 필요합니다.")
        try:
            page = context.pages[0] if context.pages else context.new_page()
            watcher = Watcher(root, client=BrowserSource(page, folder))
            report = watcher.sync([code], apply=True)
        finally:
            context.close()
    result = {"finished_at": now(), "check": report}
    if publish_to_web:
        try:
            cloud = Cloud(os.environ.get("KGS_PUSH_URL", DEFAULT_URL), os.environ.get("KGS_PUSH_KEY", ""))
            result["web"] = publish(watcher, cloud)
        except (OSError, ValueError, RuntimeError) as error:
            result["web"] = {"errors": [{"error": str(error)}]}
    write_json(watcher.work / "daily_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if report["errors"] or result.get("web", {}).get("errors") else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="운영 자료를 저장할 폴더")
    parser.add_argument("--code", default="FP216")
    parser.add_argument("--publish", action="store_true", help="시행일이 확인된 자료를 웹에 반영")
    args = parser.parse_args()
    code = args.code.strip().upper()
    if not CODE.fullmatch(code):
        parser.error("기준 번호 형식이 잘못되었습니다.")
    if not (args.root / "data" / "kgs_code.jsonl").is_file():
        parser.error("먼저 매일_자동수집_설정.bat를 실행해 운영 자료를 준비하세요.")
    try:
        return sync_browser(args.root, code, args.publish)
    except (OSError, ValueError, RuntimeError, BrowserError) as error:
        print(f"KGS 수집 중단 — {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
