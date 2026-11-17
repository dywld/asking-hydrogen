#!/usr/bin/env python3
"""KGS 개정 감시 결과를 Cloudflare 웹 챗봇에 게시한다."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

from kgs_watch import CODE, ROOT, SHA, Watcher, digest, exclusive_lock, read_rows, semantic_hash

DEFAULT_URL = "https://hydrogen-guide.tmdfoqhdl030.workers.dev/api/kgs-updates"
BATCH_BYTES = 160_000


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Cloud:
    def __init__(self, url, key):
        u = urllib.parse.urlsplit(url)
        if (u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"))
                or not u.hostname or u.username or u.password or u.fragment or u.query
                or u.path != "/api/kgs-updates"):
            raise ValueError("KGS_PUSH_URL은 HTTPS /api/kgs-updates 주소여야 합니다")
        if not key:
            raise ValueError("KGS_PUSH_KEY 환경 변수를 설정하세요")
        self.url = url
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirects())

    def request(self, action, code, **fields):
        data = encode({"action": action, "code": code, **fields})
        req = urllib.request.Request(self.url, data=data, headers={
            "Content-Type": "application/json", "x-kgs-push-key": self.key,
            "User-Agent": "asking-hydrogen-kgs-update",
        })
        try:
            with self.opener.open(req, timeout=45) as response:
                return json.loads(response.read(1_000_000))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Cloudflare {action} {code}: HTTP {e.code} {e.read(1000).decode(errors='replace')}") from None


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def search_rows(code, rows):
    law = f"KGS {code}"
    out = []
    for row in rows:
        item = f" {row['item']}" if row.get("item") else ""
        ref = f"[{law}{item}]"
        out.append({"article": ref, "title": row["title"],
                    "content": row["content"], "ref": ref})
    return out


def batches(rows):
    part, start, size = [], 0, 0
    for row in rows:
        n = len(encode(row)) + 1
        if n > BATCH_BYTES:
            raise ValueError("KGS 검색 조각 하나가 전송 한도를 초과했습니다")
        if part and (size + n > BATCH_BYTES or len(part) == 48):
            yield start, part
            start += len(part)
            part, size = [], 0
        part.append(row)
        size += n
    if part:
        yield start, part


def cloud_state(cloud, code):
    return {r["law"][4:]: r for r in cloud.request("state", code)["state"]}


def publish(watcher, cloud):
    report = {"published": [], "blocked": [], "errors": []}
    with exclusive_lock(watcher.work / "watch.lock"):
        release = {}
        for row in read_rows(watcher.data):
            if row.get("version_sha256"):
                release.setdefault(row["code"], []).append(row)
        if not release:
            return report
        state = cloud_state(cloud, next(iter(release)))
        for code, active in sorted(release.items()):
            try:
                sha, effective = active[0]["version_sha256"], active[0]["effective_on"]
                previous = state.get(code, {})
                if sha == previous.get("version"):
                    continue
                if sha == previous.get("blocked_version"):
                    report["blocked"].append(code)
                    continue
                folder = watcher.version_dir(code, sha)
                meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
                if (any(r.get("version_sha256") != sha or r.get("effective_on") != effective for r in active)
                        or digest((folder / "document.pdf").read_bytes()) != sha
                        or semantic_hash(active) != meta["semantic_sha256"] or len(active) != meta["chunks"]):
                    raise ValueError("보관 원문 또는 검색 자료 무결성 불일치")
                rows = search_rows(code, active)
                fields = {"version": sha, "total": len(rows), "effective_date": effective,
                          "release_hash": digest(encode(rows))}
                for start, part in batches(rows):
                    cloud.request("stage", code, **fields, start=start, rows=part)
                cloud.request("activate", code, version=sha, expected_version=previous.get("version"))
                report["published"].append({"code": code, "version": sha, "effective_date": effective})
            except (OSError, ValueError, KeyError, RuntimeError) as error:
                report["errors"].append({"code": code, "error": str(error)})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="KGS 확인·적용 후 웹 검색 자료 게시")
    sync.add_argument("--codes", nargs="+")
    sub.add_parser("publish", help="이미 적용된 로컬 버전을 웹에 게시 또는 실패 재시도")
    sub.add_parser("status", help="웹의 활성 버전과 보류 상태 확인")
    rollback = sub.add_parser("rollback", help="웹 검색 자료를 기존 또는 이전 버전으로 복구")
    rollback.add_argument("code")
    rollback.add_argument("current", help="현재 웹 버전 SHA-256")
    rollback.add_argument("target", help="이전 SHA-256 또는 baseline")
    args = parser.parse_args(argv)
    try:
        watcher = Watcher(args.root)
        cloud = Cloud(os.environ.get("KGS_PUSH_URL", DEFAULT_URL), os.environ.get("KGS_PUSH_KEY", ""))
        if args.command == "status":
            print(json.dumps(cloud_state(cloud, "GC205"), ensure_ascii=False, indent=2))
            return 0
        if args.command == "rollback":
            code = args.code.upper()
            target = None if args.target == "baseline" else args.target
            if not CODE.fullmatch(code) or not SHA.fullmatch(args.current) or (target and not SHA.fullmatch(target)):
                parser.error("코드와 SHA-256을 확인하세요")
            print(json.dumps(cloud.request("rollback", code, version=target,
                                           expected_version=args.current), ensure_ascii=False))
            return 0
        check = watcher.sync(args.codes, apply=True) if args.command == "sync" else None
        result = publish(watcher, cloud)
        if check is not None:
            result["check"] = check
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["errors"] or (check and check["errors"]) else 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"KGS 웹 갱신 실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
