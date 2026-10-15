#!/usr/bin/env python3
"""클라우드플레어판 검색 채점 — eval_run.py --retrieval 과 같은 잣대(근거 일치).

워커의 /api/chat 에 debug='search' 를 보내 모델 없이 첫 검색 결과만 받는다.
상위 8조각의 '법령 조문' 안에 정답 법령(ref)이 하나라도 있으면 맞음.

    npx --no-install wrangler dev --remote --port 8788   (cf/ 에서)
    python cf/eval_cf.py [eval_set_all.json] [--url http://localhost:8788] [--compare] [--quiet]

--compare: 노트북 검색(search.py)도 같이 돌려 둘의 1등 점수 비와 어긋난 문항을 보여 준다.
"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


URL = arg("--url", "http://localhost:8788").rstrip("/") + "/api/chat"


def cf_hits(q):
    d = json.dumps({"messages": [{"role": "user", "text": q}], "debug": "search"}).encode()
    req = urllib.request.Request(URL, data=d, headers={"Content-Type": "application/json", "User-Agent": "eval_cf"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                for line in r:
                    e = json.loads(line.decode("utf-8"))
                    if e.get("type") == "debug":
                        return e["hits"]
                    if e.get("type") == "text":
                        raise RuntimeError(e["t"])
        except Exception as e:
            err = e
            time.sleep(1)
    raise err


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and sys.argv[i - 1] != "--url"]
    name = args[0] if args else "eval_set_all.json"
    items = json.loads((ROOT / name).read_text(encoding="utf-8"))
    quiet = "--quiet" in sys.argv
    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda it: cf_hits(it["q"]), items))
    dt = (time.time() - t0) / max(len(items), 1)
    py = None
    if "--compare" in sys.argv:
        sys.path.insert(0, str(ROOT))
        import search
        idx = search.get_index()
        py = [idx.search(it["q"], top_k=12) for it in items]
    ok, ratios = 0, []
    for k, (it, hits) in enumerate(zip(items, res)):
        joined = " ".join(f"{h['law']} {h['article']}" for h in hits[:8])
        r = (not it.get("ref")) or any(w in joined for w in it["ref"])
        ok += r
        if py is not None and py[k] and hits:
            ratios.append(py[k][0]["score"] / max(hits[0]["score"], 1e-6))
        if not quiet or not r:
            line = f"{it['n']:3d}. {'O' if r else 'X'} {it['q'][:40]}"
            if not r:
                line += f"\n      정답 {it.get('ref')} | CF: " + " / ".join(f"{h['law']} {h['article']}" for h in hits[:3])
                if py is not None:
                    line += "\n      PY: " + " / ".join(f"{h['law']} {h['article']}" for h in py[k][:3])
            print(line, flush=True)
    n = len(items)
    print(f"\n근거 일치(CF) {ok}/{n} · 질문당 {dt:.2f}초 · 노트북 기준 111/111(eval_set_all)")
    if ratios:
        ratios.sort()
        print(f"1등 점수 비(노트북/CF) 중앙값 {ratios[len(ratios) // 2]:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
