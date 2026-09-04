#!/usr/bin/env python3
"""채점 이력(eval_history/*.json)을 한 장의 HTML 로 그린다 → 정확도추이.html

지금까지는 정확도측정.md 두 장뿐이라 "지난주보다 나아졌나"를 보려면 파일을 열어
숫자를 비교해야 했다. 커밋마다 채점해 두면 여기서 선 하나로 보인다.
문항별 O/X 격자도 함께 그려, 어떤 문항이 오락가락하는지 보인다.

    python eval_run.py eval_set50.json --retrieval   # 이력 하나 추가(검색만, 무료)
    python eval_run.py eval_set50.json               # 이력 하나 추가(전체, 모델 호출)
    python eval_dashboard.py                         # 그림 갱신
"""
import json
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent   # 프로젝트 최상위(data/, search.py)
HISTORY = HERE / "eval_history"
OUT = HERE / "정확도추이.html"

# 색은 두 계열만 쓴다. 내용(파랑)·근거(초록). 색맹에서도 갈리는 짝이고 명도도 다르다.
C_CONTENT, C_REF = "#2f6fed", "#1c7c4a"


def load():
    runs = []
    for p in sorted(HISTORY.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            r["file"] = p.name
            runs.append(r)
        except Exception:
            pass
    return runs


def line_chart(runs, key, color, label):
    """한 지표의 추이. 가로는 실행 순서, 세로는 정답률(%)."""
    pts = [(i, r[key] * 100 / r["n"]) for i, r in enumerate(runs) if r.get(key) is not None]
    if not pts:
        return ""
    W, H, L, T = 640, 200, 44, 16
    x = lambda i: L + i * (W - L - 16) / max(len(runs) - 1, 1)
    y = lambda v: T + (100 - v) * (H - T - 28) / 100
    grid = "".join(
        f'<line x1="{L}" y1="{y(v)}" x2="{W - 16}" y2="{y(v)}" stroke="#e4e8ee"/>'
        f'<text x="{L - 6}" y="{y(v) + 4}" text-anchor="end" font-size="11" fill="#5b6675">{v}</text>'
        for v in (0, 50, 100))
    path = " ".join(f"{'M' if k == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for k, (i, v) in enumerate(pts))
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="{color}" stroke="#fff" stroke-width="2">'
        f'<title>{escape(runs[i]["t"])} · {escape(runs[i]["set"])} · {v:.0f}%</title></circle>'
        for i, v in pts)
    last = pts[-1]
    lab = (f'<text x="{x(last[0]) + 8:.1f}" y="{y(last[1]) + 4:.1f}" font-size="12" '
           f'fill="#1b2430" font-weight="600">{last[1]:.0f}%</text>')
    xs = "".join(
        f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle" font-size="10" fill="#5b6675">'
        f'{escape(r["t"][5:10])}</text>' for i, r in enumerate(runs) if len(runs) <= 12 or i % 3 == 0)
    return (f'<figure><figcaption>{escape(label)}</figcaption>'
            f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{escape(label)} 추이">'
            f'{grid}<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>{dots}{lab}{xs}</svg></figure>')


def grid_table(runs):
    """문항 × 실행 격자. 세로가 문항, 가로가 실행. 초록 = 맞음."""
    full = [r for r in runs if r.get("rows")]
    if not full:
        return ""
    qs = {}
    for r in full:
        for row in r["rows"]:
            qs.setdefault((r["set"], row["n"]), row["q"])
    head = "".join(f'<th title="{escape(r["t"])}">{escape(r["t"][5:10])}<br><small>{escape(r["kind"])}</small></th>'
                   for r in full)
    body = []
    for (s, n), q in sorted(qs.items()):
        cells = []
        for r in full:
            row = next((x for x in r["rows"] if x["n"] == n and r["set"] == s), None)
            if not row:
                cells.append("<td></td>")
                continue
            if row.get("content") is None:
                ok = row.get("ref")
                cells.append(f'<td class="{"ok" if ok else "bad"}">{"근거" if ok else "✗"}</td>')
            else:
                c, rf = row.get("content"), row.get("ref")
                cells.append(f'<td class="{"ok" if c and rf else "bad" if not c else "half"}">'
                             f'{"O" if c else "X"}{"" if rf else "·근거X"}</td>')
        body.append(f'<tr><td class="q">{escape(s)} {n}. {escape(q)}</td>{"".join(cells)}</tr>')
    return ('<h2>문항별</h2><div class="tblwrap"><table><thead><tr><th>문항</th>'
            f'{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def ops_section():
    """운영 지표 — 질문 기록(chat_log.jsonl)과 피드백에서 뽑는다. 시중 서비스가 매일 보는 네 숫자."""
    log = ROOT / "data" / "chat_log.jsonl"
    if not log.exists():
        return ""
    rows = []
    for line in log.open(encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    if not rows:
        return ""
    n = len(rows)
    weak = sum(1 for r in rows if r.get("weak"))
    removed = sum(1 for r in rows if r.get("removed"))
    warned = sum(1 for r in rows if r.get("warnings"))
    cached = sum(1 for r in rows if r.get("cached") or r.get("model") in ("cache", "demo-lock"))
    secs = [r["sec"] for r in rows if isinstance(r.get("sec"), (int, float))]
    avg = sum(secs) / len(secs) if secs else None
    fb = ROOT / "data" / "feedback.jsonl"
    up = down = 0
    if fb.exists():
        for line in fb.open(encoding="utf-8"):
            try:
                v = json.loads(line).get("vote")
                up += v == "up"
                down += v == "down"
            except ValueError:
                pass
    by_day = {}
    for r in rows:
        by_day[r.get("t", "")[:10]] = by_day.get(r.get("t", "")[:10], 0) + 1
    days = sorted(by_day.items())[-14:]
    W, H, L, T = 640, 160, 40, 14
    mx = max(v for _, v in days) or 1
    bw = (W - L - 16) / max(len(days), 1)
    bars = "".join(
        f'<rect x="{L + i * bw + 2:.1f}" y="{T + (H - T - 28) * (1 - v / mx):.1f}" width="{max(bw - 4, 2):.1f}" '
        f'height="{(H - T - 28) * v / mx:.1f}" rx="3" fill="{C_CONTENT}"><title>{escape(d)} · {v}건</title></rect>'
        f'<text x="{L + i * bw + bw / 2:.1f}" y="{H - 8}" text-anchor="middle" font-size="10" fill="#5b6675">{escape(d[5:])}</text>'
        for i, (d, v) in enumerate(days))
    tiles = [("질문 수", f"{n:,}"), ("자료 없음 판정", f"{weak * 100 // n}%"),
             ("검증 경고", f"{warned * 100 // n}%"), ("문장 삭제", f"{removed * 100 // n}%"),
             ("캐시 응답", f"{cached * 100 // n}%"),
             ("평균 응답", f"{avg:.1f}초" if avg else "-"), ("👍 / 👎", f"{up} / {down}")]
    tile_html = "".join(f'<div class="tile"><small>{escape(k)}</small><strong>{escape(v)}</strong></div>' for k, v in tiles)
    return (f'<h2>운영 지표 · 질문 기록 {n:,}건</h2><div class="tiles">{tile_html}</div>'
            f'<figure><figcaption>날짜별 질문 수(최근 14일)</figcaption>'
            f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="날짜별 질문 수">{bars}</svg></figure>')


def main():
    runs = load()
    if not runs:
        print("eval_history/ 가 비어 있습니다. eval_run.py 를 먼저 실행하세요.")
        return 1
    sets = sorted({r["set"] for r in runs})
    parts = []
    for s in sets:
        rs = [r for r in runs if r["set"] == s]
        parts.append(f"<h2>{escape(s)} · 실행 {len(rs)}회</h2>")
        parts.append('<div class="charts">')
        parts.append(line_chart([r for r in rs if r["kind"] == "full"], "content", C_CONTENT, "내용 정답률 (모델 답변)"))
        parts.append(line_chart(rs, "ref", C_REF, "근거 일치율 (검색)"))
        parts.append("</div>")
        rows = "".join(
            f'<tr><td>{escape(r["t"])}</td><td>{escape(r["git"] or "-")}</td><td>{escape(r["kind"])}</td>'
            f'<td>{"재순위" if r.get("rerank") else ""}</td>'
            f'<td>{"-" if r.get("content") is None else f"{r["content"]}/{r["n"]}"}</td>'
            f'<td>{r["ref"]}/{r["n"]}</td><td>{r.get("sec_per_q", "")}</td></tr>' for r in rs)
        parts.append('<div class="tblwrap"><table><thead><tr><th>시각</th><th>커밋</th><th>종류</th><th>옵션</th>'
                     f'<th>내용</th><th>근거</th><th>초/문항</th></tr></thead><tbody>{rows}</tbody></table></div>')
    parts.append(grid_table(runs))
    parts.insert(0, ops_section())
    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>정확도 추이</title>
<style>
body{{font:15px/1.6 Pretendard,-apple-system,"Malgun Gothic",system-ui,sans-serif;color:#1b2430;background:#fff;max-width:900px;margin:0 auto;padding:28px 20px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px}} p{{color:#5b6675;margin:0 0 20px}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} @media(max-width:700px){{.charts{{grid-template-columns:1fr}}}}
figure{{margin:0;border:1px solid #e4e8ee;border-radius:12px;padding:12px}} figcaption{{font-size:13px;color:#5b6675;margin-bottom:4px}}
.tblwrap{{overflow-x:auto;border:1px solid #e4e8ee;border-radius:10px;margin-top:10px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:6px 10px;border-bottom:1px solid #e4e8ee;text-align:left;white-space:nowrap}}
th{{background:#f4f6fa;color:#5b6675;font-weight:600}} td.q{{white-space:normal;min-width:260px}}
td.ok{{background:#e6f5ec;color:#1c7c4a;text-align:center}} td.bad{{background:#fff6e0;color:#8a5a00;text-align:center}} td.half{{background:#f4f6fa;text-align:center}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:14px}}
.tile{{border:1px solid #e4e8ee;border-radius:12px;padding:10px 12px}} .tile small{{display:block;color:#5b6675;font-size:12px}} .tile strong{{font-size:22px}}
</style></head><body>
<h1>정확도 추이</h1><p>eval_history/ 의 채점 기록 {len(runs)}건. 내용 = 모델 답변에 정답 표현이 있는가, 근거 = 검색 상위에 정답 법령이 있는가.</p>
{"".join(parts)}
</body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"{OUT.name} ← 실행 {len(runs)}건")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
