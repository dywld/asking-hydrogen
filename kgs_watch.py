#!/usr/bin/env python3
"""KGS 원문 수집 → 버전 보관 → 변경 비교 → 적용일에 검색 데이터 갱신.

외부 패키지는 기존 프로젝트와 같은 pymupdf 하나다. 실행 방법은 KGS_UPDATE.md.
네트워크 오류/빈 목록/깨진 PDF는 기존 검색 데이터를 지우지 않는다.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from fetch_kgs_code import KgsClient, LIST
from ingest_kgs_code import extract_pdf

ROOT = Path(__file__).resolve().parent
CODE = re.compile(r"^[A-Z]{2}\d{3}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
KST = timezone(timedelta(hours=9), "Asia/Seoul")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_korea():
    return datetime.now(KST).date()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode_rows(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def read_rows(path):
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(r, dict) or not CODE.fullmatch(r.get("code", ""))
           or not isinstance(r.get("content"), str) or not r["content"].strip() for r in rows):
        raise ValueError(f"KGS 검색 데이터 형식 오류: {path.name}")
    return rows


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".kgs-", delete=False) as f:
            name = f.name
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


@contextmanager
def exclusive_lock(path):
    """프로세스 종료 시 OS가 잠금을 해제하므로 오래된 잠금이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        f.seek(0, 2)
        if not f.tell():
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise RuntimeError("다른 KGS 갱신 작업이 실행 중입니다") from e
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


def explicit_effective_date(text):
    """명시적 '이 기준은 YYYY년 M월 D일부터 시행'만 인식한다.

    개정일/승인일을 시행일로 추정하지 않는다. 경과조치·항목별 적용은 검토 대상으로 남긴다.
    """
    if re.search(r"경과조치|적용례|(?:항목|일부\s|다만).{0,40}(?:시행|적용)", text):
        return None
    matches = re.findall(r"이\s*기준은\s*(20\d{2})\s*년\s*(\d{1,2})\s*월\s*"
                         r"(\d{1,2})\s*일\s*부터\s*시행", text)
    dates = set()
    for y, m, d in matches:
        try:
            dates.add(date(int(y), int(m), int(d)).isoformat())
        except ValueError:
            return None
    return dates.pop() if len(dates) == 1 else None


def semantic_hash(rows):
    return digest(json.dumps([(r.get("item"), r.get("title"), r["content"]) for r in rows],
                             ensure_ascii=False).encode("utf-8"))


class Watcher:
    def __init__(self, root=ROOT, client=None):
        self.root = Path(root).resolve()
        self.data = self.root / "data" / "kgs_code.jsonl"
        self.work = self.root / "data" / "kgs_updates"
        self.state_file = self.work / "state.json"
        self.client = client or KgsClient()

    def state(self):
        if self.state_file.exists():
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            if state.get("schema") != 1 or not isinstance(state.get("codes"), dict):
                raise ValueError("KGS 상태 파일 형식 오류")
            return state
        return {"schema": 1, "codes": {}}

    def version_dir(self, code, sha):
        if not CODE.fullmatch(code) or not SHA.fullmatch(sha):
            raise ValueError("코드 또는 SHA-256 형식 오류")
        return self.work / "versions" / code / sha

    def stage(self, item, blob, previous):
        code, sha = item["code"], digest(blob)
        folder = self.version_dir(code, sha)
        pdf = folder / "document.pdf"
        metadata = folder / "metadata.json"
        if metadata.exists():
            meta = json.loads(metadata.read_text(encoding="utf-8"))
            rows = read_rows(folder / "chunks.jsonl")
            if digest(pdf.read_bytes()) != sha:
                raise ValueError(f"{code} 보관 원문 무결성 오류")
            return meta, rows
        atomic_write(pdf, blob)
        try:
            rows, text = extract_pdf(pdf, code, item["year"], item["title"],
                                     source=f"{code}_{item['year']}_{sha[:12]}.pdf")
        except Exception:
            # 잘못된 PDF는 현재 자료와 연결되지 않는다. 다음 실행에서 재시도한다.
            pdf.unlink(missing_ok=True)
            raise
        rel = pdf.relative_to(self.root).as_posix()
        effective_on = item.get("effective_on") or explicit_effective_date(text)
        if effective_on:
            effective_on = date.fromisoformat(effective_on).isoformat()
            # 과거 제정 이력에 적힌 시행일을 이번 판의 시행일로 쓰지 않는다.
            lower_bound = item.get("revised_on") or f"{item['year']}-01-01"
            if effective_on < lower_bound:
                effective_on = None
        for row in rows:
            row.update(version_sha256=sha, pdf_path=rel,
                       revised_on=item.get("revised_on"), effective_on=effective_on)
        meta = {"code": code, "sha256": sha, "year": str(item["year"]),
                "title": item["title"], "source_path": item["path"],
                "source_url": f"{LIST}?pblcCd={code}",
                "revised_on": item.get("revised_on"), "effective_on": effective_on,
                "effective_source": "explicit_text" if effective_on else None,
                "fetched_at": now(), "chunks": len(rows),
                "semantic_sha256": semantic_hash(rows)}
        old_text = "\n".join(r["content"] for r in previous)
        new_text = "\n".join(r["content"] for r in rows)
        changes = "\n".join(difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(), fromfile="previous", tofile=sha[:12],
            lineterm=""))
        atomic_write(folder / "diff.txt", changes.encode("utf-8"))
        atomic_write(folder / "chunks.jsonl", encode_rows(rows))
        write_json(metadata, meta)  # 마지막에 써서 완료된 버전만 재사용한다.
        return meta, rows

    def _activate_ready(self, state, report, today):
        rows = read_rows(self.data)
        for code, rec in sorted(state["codes"].items()):
            sha = rec.get("latest_sha256")
            if not sha:
                continue
            folder = self.version_dir(code, sha)
            meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            old = [r for r in rows if r["code"] == code]
            candidate = read_rows(folder / "chunks.jsonl")
            if not candidate or any(r["code"] != code or r.get("version_sha256") != sha for r in candidate):
                raise ValueError(f"{code} 보관 검색 데이터 무결성 오류")
            if digest((folder / "document.pdf").read_bytes()) != sha:
                raise ValueError(f"{code} 보관 PDF 무결성 오류")
            if semantic_hash(candidate) != meta["semantic_sha256"]:
                raise ValueError(f"{code} 보관 검색 데이터 내용이 변경되었습니다")
            if old and semantic_hash(old) == meta["semantic_sha256"]:
                rec["status"] = "unchanged"
                continue
            when = meta.get("effective_on")
            if not when:
                rec["status"] = "needs_effective_date"
                report["pending"].append({"code": code, "sha256": sha, "reason": rec["status"]})
                continue
            if date.fromisoformat(when) > today:
                rec["status"] = "scheduled"
                report["pending"].append({"code": code, "sha256": sha, "effective_on": when})
                continue
            # 오래된 목록/버전으로 자동 역행하지 않는다.
            old_dates = [r["effective_on"] for r in old if r.get("effective_on")]
            if (old and int(meta["year"]) < max(int(r["year"]) for r in old)
                    or old_dates and when < max(old_dates)):
                rec["status"] = "older_version"
                report["pending"].append({"code": code, "reason": rec["status"]})
                continue
            for row in candidate:
                row["effective_on"] = when
            rows = [r for r in rows if r["code"] != code] + candidate
            rec["status"] = "active"
            report["applied"].append({"code": code, "sha256": sha, "effective_on": when})
        if report["applied"]:
            rows.sort(key=lambda r: r["code"])  # 같은 코드의 항목 순서는 보존
            if self.data.exists():
                before = self.data.read_bytes()
                atomic_write(self.work / "backups" / f"{digest(before)}.jsonl", before)
            atomic_write(self.data, encode_rows(rows))
            # 이 파일 하나의 교체가 commit. 검색기는 다음 요청에 새 색인을 만든다.

    def sync(self, codes=None, apply=False, dry_run=False, today=None):
        today = today or today_korea()
        with exclusive_lock(self.work / "watch.lock"):
            state = self.state()
            rows = read_rows(self.data)
            wanted = set(codes or (r["code"] for r in rows))
            if not wanted or any(not CODE.fullmatch(c) for c in wanted):
                raise ValueError("감시할 코드가 없습니다. --codes GC205 FP216처럼 지정하세요")
            report = {"started_at": now(), "dry_run": dry_run, "checked": [],
                      "changed": [], "applied": [], "pending": [], "errors": []}
            try:
                items = self.client.list_codes(wanted)
                if not items:
                    raise ValueError("KGS 공식 목록이 비어 있습니다(기존 자료 유지)")
                by_code = {}
                for item in items:
                    if item["code"] in by_code:
                        raise ValueError(f"목록에 같은 코드가 두 번 나옵니다: {item['code']}")
                    by_code[item["code"]] = item
            except Exception as e:
                report["errors"].append({"code": None, "error": str(e)})
                by_code = {}
            for code in sorted(wanted):
                if code not in by_code:
                    if by_code:
                        report["errors"].append({"code": code, "error": "공식 목록에서 찾지 못함(기존 자료 유지)"})
                    continue
                try:
                    item = by_code[code]
                    # 연도/경로가 같아도 본문이 바뀔 수 있어 파일 내용까지 비교한다.
                    blob = self.client.download(item)
                    sha = digest(blob)
                    rec = state["codes"].get(code, {})
                    report["checked"].append(code)
                    if sha != rec.get("latest_sha256"):
                        report["changed"].append({"code": code, "sha256": sha})
                    if dry_run:
                        continue
                    meta, _ = self.stage(item, blob, [r for r in rows if r["code"] == code])
                    state["codes"][code] = dict(rec, latest_sha256=sha, last_checked=now(),
                                                status="staged", title=meta["title"])
                except Exception as e:
                    report["errors"].append({"code": code, "error": str(e)})
            if not dry_run:
                if apply:
                    # 한 코드의 실패는 다른 코드나 이미 예약된 버전의 적용을 막지 않는다.
                    self._activate_ready(state, report, today)
                state["last_run"] = dict(report, finished_at=now())
                write_json(self.state_file, state)
                write_json(self.work / "last_report.json", state["last_run"])
            return report

    def set_effective(self, code, sha, effective_on, apply=True, today=None):
        """날짜는 특정 해시에만 연결한다. 다음 개정에 재사용하지 않는다."""
        effective_on = date.fromisoformat(effective_on).isoformat()
        with exclusive_lock(self.work / "watch.lock"):
            state = self.state()
            rec = state["codes"].get(code)
            if not rec or rec.get("latest_sha256") != sha:
                raise ValueError("현재 수집된 최신 SHA-256과 일치하지 않습니다. status로 확인하세요")
            folder = self.version_dir(code, sha)
            meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            meta.update(effective_on=effective_on, effective_source="operator", confirmed_at=now())
            write_json(folder / "metadata.json", meta)
            report = {"applied": [], "pending": []}
            if apply:
                self._activate_ready(state, report, today or today_korea())
            write_json(self.state_file, state)
            return report

    def status(self):
        state = self.state()
        active = {}
        for row in read_rows(self.data):
            active[row["code"]] = {"sha256": row.get("version_sha256"),
                                    "year": row.get("year"), "effective_on": row.get("effective_on")}
        return {"active": active, "watch": state}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="프로젝트 폴더")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("sync", "watch"):
        p = sub.add_parser(command)
        p.add_argument("--codes", nargs="+", help="기본값: 현재 검색 데이터의 코드")
        p.add_argument("--apply", action="store_true", help="적용일이 확인되고 도래한 버전 자동 적용")
        p.add_argument("--dry-run", action="store_true", help="원문 해시 비교만, 데이터/상태 저장 안 함")
        if command == "watch":
            p.add_argument("--hours", type=float, default=24, help="확인 간격(최소 1시간)")
    p = sub.add_parser("effective", help="특정 버전의 적용일 확인 또는 예약")
    p.add_argument("code")
    p.add_argument("sha256")
    p.add_argument("date", help="YYYY-MM-DD; 조항별 시행/경과조치 검토 후 지정")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    watcher = Watcher(args.root)
    try:
        if args.command == "status":
            print(json.dumps(watcher.status(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "effective":
            print(json.dumps(watcher.set_effective(args.code.upper(), args.sha256, args.date),
                             ensure_ascii=False, indent=2))
            return 0
        if args.command == "watch" and (args.hours < 1 or not args.hours < float("inf")):
            parser.error("--hours는 1 이상의 유한한 값이어야 합니다")
        while True:
            try:
                report = watcher.sync(args.codes, args.apply, args.dry_run)
                print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
                if args.command == "sync":
                    return 1 if report["errors"] else 0
            except Exception as e:
                if args.command == "sync":
                    raise
                print(json.dumps({"error": str(e), "at": now()}, ensure_ascii=False),
                      file=sys.stderr, flush=True)
            time.sleep(args.hours * 3600)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"KGS 갱신 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
