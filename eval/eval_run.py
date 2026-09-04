#!/usr/bin/env python3
"""정답셋으로 챗봇을 채점한다.

발표에 넣을 숫자("20문항 중 몇 개 맞음")를 사람 손으로 세지 않으려고 만들었다.
셋 다 본다.
  내용  — 답에 있어야 할 말이 들어 있나
  근거  — 근거 목록에 맞는 법령이 있나
  거절  — 자료에 없는 질문에 "없다"고 답했나(지어내면 실패)
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent   # 프로젝트 최상위(data/, search.py)
URL = "http://localhost:8000/api/chat"


def ask(q):
    d = json.dumps({"messages": [{"role": "user", "text": q}]}).encode()
    req = urllib.request.Request(URL, data=d,
                                 headers={"Content-Type": "application/json"})
    text, srcs, cited = "", [], []
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "text":
                text += e["t"]
            elif e.get("type") == "replace":       # 자기교정·삭제 뒤의 최종 본문
                text = e["t"]
            elif e.get("type") == "sources":
                srcs = e.get("sources") or []
            elif e.get("type") == "cited":
                cited = e.get("refs") or []
    # 답변은 [3] 처럼 번호로 인용한다. 화면은 그 번호 옆에 법령명·조문을 붙여 보여주므로
    # 채점도 같은 것을 본다: 인용된 근거의 이름을 본문 뒤에 붙여서 '제4조' 같은 표현을 찾는다.
    names = " ".join(f"{g.get('law', '')} {g.get('ref', '')}" for g in srcs
                     if g.get("ref") in cited)
    return text + "\n" + names, srcs


def grade(item, text, srcs):
    """내용·근거를 각각 본다. must 는 하나만 맞아도 인정한다
    (같은 뜻을 여러 표기로 쓰기 때문 — '2,000' / '2000')."""
    # 띄어쓰기·쉼표만 다른 값("1만 5천 원" ↔ "1만5천원", "25,000" ↔ "25000")은 같은 답이다.
    def norm(s):
        return re.sub(r"[\s,]", "", s)
    flat = norm(text)
    hit_must = any(norm(w) in flat for w in item["must"])
    hit_any = (not item.get("any")) or any(norm(w) in flat for w in item["any"])
    joined = " ".join(f"{g.get('law','')} {g.get('ref','')}" for g in srcs)
    hit_ref = (not item.get("ref")) or any(w in joined for w in item["ref"])
    return hit_must and hit_any, hit_ref


def git_hash():
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def retrieval_only(items, label):
    """모델을 부르지 않고 검색만 채점한다(근거 일치만).

    재순위·가중치 같은 검색 쪽 변경은 이걸로 먼저 본다. 무료 한도를 안 쓰고 10초면 끝난다.
    """
    sys.path.insert(0, str(ROOT))
    import search
    idx = search.get_index()
    ok, rows = 0, []
    quiet = "--quiet" in sys.argv
    t0 = time.time()
    for it in items:
        hits = idx.search(it["q"], top_k=12)
        joined = " ".join(f"{h['law']} {h['article']}" for h in hits[:8])
        r = (not it.get("ref")) or any(w in joined for w in it["ref"])
        ok += r
        rows.append((it, r, [f"{h['law']} {h['article']}" for h in hits[:3]]))
        if not quiet or not r:
            print(f"{it['n']:2d}. {'O' if r else 'X'} {it['q'][:34]}", flush=True)
    n = len(items)
    dt = (time.time() - t0) / max(n, 1)
    print(f"\n근거 일치 {ok}/{n} · 질문당 {dt:.2f}초 · {label}")
    # --min 0.95 : 이 비율보다 낮으면 실패로 끝낸다(커밋 훅용).
    for a in sys.argv:
        if a.startswith("--min"):
            need = float(sys.argv[sys.argv.index(a) + 1]) if a == "--min" else float(a.split("=")[1])
            if ok / max(n, 1) < need:
                print(f"✗ 기준 {need:.0%} 미달 — 커밋을 막습니다")
                sys.exit(1)
    save_history({"t": time.strftime("%Y-%m-%d %H:%M"), "set": label, "git": git_hash(),
                  "kind": "retrieval", "n": n, "content": None, "ref": ok,
                  "sec_per_q": round(dt, 2),
                  "rerank": search.RERANK_ON,
                  "rows": [{"n": it["n"], "q": it["q"], "ref": r, "top": top}
                           for it, r, top in rows]})
    return ok


HISTORY = HERE / "eval_history"


def save_history(rec):
    """채점 결과를 날짜별 JSON 으로 남긴다. eval_dashboard.py 가 추이를 그린다."""
    HISTORY.mkdir(exist_ok=True)
    name = time.strftime("%Y%m%d_%H%M%S") + f"_{rec['set']}_{rec['kind']}.json"
    (HISTORY / name).write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                                encoding="utf-8")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "eval_set.json"
    items = json.loads((HERE / name).read_text(encoding="utf-8"))
    label = name.replace(".json", "")
    if "--retrieval" in sys.argv:
        retrieval_only(items, label)          # 기준 미달이면 안에서 sys.exit(1)
        return 0                              # 맞은 개수를 돌려주면 종료 코드가 되어 훅이 실패한다(실측)
    out_name = "정확도측정" + name.replace("eval_set", "").replace(".json", "") + ".md"
    rows, ok_c, ok_r = [], 0, 0
    for it in items:
        try:
            text, srcs = ask(it["q"])
        except Exception as e:                      # 서버가 죽어도 표는 남긴다
            text, srcs = f"[실패] {e}", []
        c, r = grade(it, text, srcs)
        ok_c += c
        ok_r += r
        rows.append((it, c, r, text, srcs))
        print(f"{it['n']:2d}. {'O' if c else 'X'}{'O' if r else 'X'} "
              f"{it['q'][:34]}", flush=True)
        time.sleep(1)

    n = len(items)
    lines = [f"# 정확도 측정 — {time.strftime('%Y-%m-%d')}", "",
             f"- 문항 {n}개", f"- 내용 정답 **{ok_c}/{n}** ({ok_c*100//n}%)",
             f"- 근거 일치 **{ok_r}/{n}** ({ok_r*100//n}%)", "",
             "| # | 유형 | 질문 | 내용 | 근거 |", "|---:|---|---|:--:|:--:|"]
    for it, c, r, _, _ in rows:
        lines.append(f"| {it['n']} | {it['type']} | {it['q']} | "
                     f"{'O' if c else 'X'} | {'O' if r else 'X'} |")
    lines += ["", "---", "", "## 답변 전문"]
    for it, c, r, text, srcs in rows:
        lines += ["", f"### {it['n']}. {it['q']}",
                  f"판정 — 내용 {'O' if c else 'X'} / 근거 {'O' if r else 'X'}",
                  "", text.strip()[:900], "",
                  "> 근거: " + " | ".join(
                      f"{g.get('law','')} {g.get('ref','')}" for g in srcs[:4])]
    (HERE / out_name).write_text("\n".join(lines), encoding="utf-8")
    save_history({"t": time.strftime("%Y-%m-%d %H:%M"), "set": label, "git": git_hash(),
                  "kind": "full", "n": n, "content": ok_c, "ref": ok_r,
                  "rows": [{"n": it["n"], "q": it["q"], "type": it.get("type"),
                            "content": c, "ref": r} for it, c, r, _, _ in rows]})
    print(f"\n내용 {ok_c}/{n} · 근거 {ok_r}/{n} → {out_name}")


if __name__ == "__main__":
    sys.exit(main())
