#!/usr/bin/env python3
"""법령 개정 감시 — 수록 법령의 공포일·시행일이 바뀌면 클라우드플레어판에 알린다(앱 알림).

국가법령정보센터 OpenAPI 는 신청할 때 등록한 서버 IP 에서만 응답한다(그 밖에서는
"사용자 정보 검증에 실패" 로 막힘). 클라우드플레어 워커는 IP 가 고정이 아니라서,
IP 가 고정인 오라클 서버에서 하루 한 번 돌린다.

    LAW_OC=신청한OC  APP_PUSH_KEY=워커와같은값  python law_watch.py
    python law_watch.py --dry       # 알리지 않고 바뀐 것만 출력

처음 돌리면 지금 값을 data/law_watch.json 에 적어 두기만 하고 알리지 않는다.
오라클 서버 crontab 예:  10 7 * * *  cd ~/hydrogen-bot && LAW_OC=... APP_PUSH_KEY=... python3 law_watch.py

주의: OpenAPI 응답의 칸 이름(법령명한글·공포일자·시행일자·법령일련번호)은 공개 안내에 따른 것이다.
OC 승인 뒤 첫 실행에서 --dry 로 값이 제대로 나오는지 확인할 것.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "law_watch.json"
PUSH = os.environ.get("APP_PUSH_URL", "https://hydrogen-guide.tmdfoqhdl030.workers.dev/api/app/laws")
SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"


def law_names():
    """수록한 한국 법령 이름(법률·시행령·시행규칙). KGS Code·요약자료는 빼고."""
    names = set()
    for f in ("korea_laws.jsonl", "korea_laws_extra.jsonl", "korea_annexes.jsonl"):
        p = ROOT / "data" / f
        if not p.exists():
            continue
        for line in p.open(encoding="utf-8"):
            law = json.loads(line).get("law", "").strip()
            if law.endswith(("법", "령", "규칙")) and not law.startswith("KGS"):
                names.add(law)
    return sorted(names)


def lookup(oc, name):
    q = urllib.parse.urlencode({"OC": oc, "target": "law", "type": "JSON", "query": name, "display": 20})
    with urllib.request.urlopen(f"{SEARCH}?{q}", timeout=20) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "LawSearch" not in d:
        raise RuntimeError(d.get("result") or str(d)[:200])
    items = d["LawSearch"].get("law") or []
    if isinstance(items, dict):
        items = [items]
    key = name.replace(" ", "")
    for it in items:
        if str(it.get("법령명한글", "")).replace(" ", "") == key:
            return {"promulgated": str(it.get("공포일자", "")), "effective": str(it.get("시행일자", "")),
                    "kind": str(it.get("제개정구분명", "")), "mst": str(it.get("법령일련번호", ""))}
    return None


def fmt(d):
    d = "".join(c for c in d if c.isdigit())
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        sys.exit("LAW_OC 가 없습니다 (open.law.go.kr 에서 OpenAPI 신청 후 받은 OC)")
    dry = "--dry" in sys.argv
    old = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    new, changes = dict(old), []
    for name in law_names():
        try:
            cur = lookup(oc, name)
        except Exception as e:
            print(f"! {name}: {e}")
            if "검증" in str(e):
                sys.exit("OpenAPI 사용자 검증 실패 - 이 서버 IP 가 OC 신청에 등록돼 있는지 확인")
            continue
        time.sleep(0.3)
        if not cur:
            print(f"? {name}: 검색 결과에 같은 이름이 없음")
            continue
        prev = old.get(name)
        new[name] = cur
        if prev and prev.get("promulgated") != cur["promulgated"]:
            link = f"https://www.law.go.kr/법령/{urllib.parse.quote(name)}"
            changes.append({"law": name, "promulgated": fmt(cur["promulgated"]), "effective": fmt(cur["effective"]),
                            "kind": cur["kind"], "link": link})
            print(f"* {name}: 공포 {fmt(prev.get('promulgated', ''))} -> {fmt(cur['promulgated'])}, 시행 {fmt(cur['effective'])}")
    if not old:
        print(f"처음 실행: {len(new)}개 법령의 현재 값을 적어 둠(알림 없음)")
    if dry:
        print(f"--dry: 바뀐 법령 {len(changes)}개, 저장·알림 안 함")
        return
    if changes:
        key = os.environ.get("APP_PUSH_KEY", "")
        req = urllib.request.Request(PUSH, data=json.dumps({"changes": changes}, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "x-push-key": key, "User-Agent": "law_watch"})
        with urllib.request.urlopen(req, timeout=30) as r:
            print("알림 보냄:", r.read().decode("utf-8"))
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
