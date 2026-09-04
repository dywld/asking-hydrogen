#!/usr/bin/env python3
"""발표 질문을 미리 돌려 사람이 확인할 답을 만든다 → data/demo_answers.json

발표 자리에서 모델이 새 문장을 만들게 두면 그날 컨디션에 답이 달린다.
미리 돌려 보고 사람이 읽어 approved 를 true 로 바꾼 답만, 서버가
BOT_DEMO_LOCK=1 일 때 그대로 내보낸다. 나머지 질문은 평소대로 답한다.

    python demo_prepare.py 발표질문.txt     # 한 줄에 질문 하나
    python demo_prepare.py --list           # 승인 상태 보기
파일을 열어 body 를 읽고, 맞으면 "approved": true 로 고친다.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent.parent   # 프로젝트 최상위
OUT = HERE / "data" / "demo_answers.json"
URL = "http://localhost:8000/api/chat"


def norm(q):
    return re.sub(r"[\s?？!.~,]+", "", q).lower()


def ask(q, mode="demo"):
    d = json.dumps({"messages": [{"role": "user", "text": q}], "mode": mode,
                    "nocache": True}).encode()
    req = urllib.request.Request(URL, data=d, headers={"Content-Type": "application/json"})
    out = {"q": q, "body": "", "sources": [], "cited": [], "followups": [],
           "warnings": [], "judge": None, "model": None, "approved": False}
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            try:
                e = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            t = e.get("type")
            if t == "text":
                out["body"] += e["t"]
            elif t == "replace":
                out["body"] = e["t"]
            elif t == "sources":
                out["sources"] = e["sources"]
            elif t == "cited":
                out["cited"] = e["refs"]
            elif t == "followups":
                out["followups"] = e["items"]
            elif t == "verify":
                out["warnings"] = e["warnings"]
            elif t == "judge":
                out["judge"] = e["bad"]
            elif t == "done":
                out["model"] = e.get("model")
    return out


def main():
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if "--list" in sys.argv:
        for k, v in data.items():
            print(f"{'✔' if v.get('approved') else '·'} {v['q'][:40]}  경고 {len(v.get('warnings') or [])}"
                  f"  검수 불일치 {len(v.get('judge') or [])}")
        return
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not src or not src.exists():
        print("사용법: python demo_prepare.py 질문파일.txt")
        return
    for q in [l.strip() for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]:
        k = norm(q)
        if data.get(k, {}).get("approved"):
            print(f"✔ 이미 승인됨: {q[:40]}")
            continue
        print(f"… {q[:40]}", flush=True)
        try:
            rec = ask(q)
        except Exception as e:
            print(f"  실패: {e}")
            continue
        data[k] = rec
        flag = "경고 없음" if not rec["warnings"] and not rec["judge"] else \
            f"경고 {len(rec['warnings'])} · 검수 불일치 {len(rec['judge'] or [])}"
        print(f"  {rec['model']} · {flag}")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{OUT.name} 에 {len(data)}건. 파일을 열어 읽고 맞는 것만 \"approved\": true 로 바꾼 뒤"
          " 서버를 BOT_DEMO_LOCK=1 로 띄운다.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
