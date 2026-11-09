#!/usr/bin/env python3
"""저장능력 계산서 — 고압가스 안전관리법 시행규칙 별표 1(저장능력 산정기준).

왜 필요한가: 안전거리·방호벽·허가 구분이 전부 '저장능력'으로 갈리는데, 사업자는 탱크·용기의
압력과 내용적만 안다. 별표 1 의 계산식으로 설비마다 저장능력을 내고, 합산 규칙(배관 연결,
중심거리 30m 이하, 같은 구축물)에 따라 더한다. 계산 과정을 그대로 보여 주는 계산서를 만든다.

    압축가스 저장탱크·용기  Q = (10P + 1)·V₁      Q ㎥, P 35℃ 최고충전압력 ㎫, V₁ 내용적 ㎥
    액화가스 저장탱크        W = 0.9·d·V₂          W ㎏, d 상용온도 비중 ㎏/L, V₂ 내용적 L
    액화가스와 압축가스가 섞이면 액화가스 10㎏ = 압축가스 1㎥

AI 를 부르지 않는다. 식과 정의는 별표 원문 그대로이고 --check 가 대조한다.

    python storage_calc.py --check
    python storage_calc.py 45:0.2:10 20:1.5:1     # 압력:내용적(㎥):개수
"""
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
LAW = "고압가스 안전관리법 시행규칙"
ANNEX = "[별표 1]"
REF = "고압가스 안전관리법 시행규칙 별표 1"

# 원문 그대로(대조 대상). 화면·계산서에 근거로 붙인다.
QUOTES = {
    "comp": "압축가스의 저장탱크 및 용기는 다음 가목의 계산식에 따라",
    "comp_f": "가. Q=(10P+1)V₁",
    "liq": "액화가스의 저장탱크는 다음 나목의 계산식에 따라",
    "liq_f": "나. W=0.9dV2",
    "Q": "Q: 저장능력(단위: ㎥)",
    "P": "P: 35℃(아세틸렌가스의 경우에는 15℃)에서의 최고충전 압력(단위: ㎫)",
    "V1": "V₁: 내용적(단위: ㎥)",
    "W": "W: 저장능력(단위: ㎏)",
    "d": "d: 상용온도에서의 액화가스의 비중(단위: ㎏/L)",
    "V2": "V₂: 내용적(단위: L)",
    "sum": "저장탱크 및 용기가 다음 각 목에 해당하는 경우에는 제1호에 따라 산정한 각각의 저장능력을 합산한다.",
    "mix": "액화가스와 압축가스가 섞여 있는 경우에는 액화가스 10㎏을 압축가스 1㎥로 본다.",
    "sum_a": "저장탱크 및 용기가 배관으로 연결된 경우",
    "sum_b": "저장탱크 및 용기 사이의 중심거리가 30m 이하인 경우 또는 같은 구축물에 설치되어 있는 경우. 다만, 소화설비용 저장탱크 및 용기는 제외한다.",
}


def _num(v):
    try:
        x = float(str(v).replace(",", "").strip())
        return x if x >= 0 else None
    except (TypeError, ValueError):
        return None


def calc(items):
    """items: [{kind: comp|liq, name, p(㎫), v(내용적 — comp ㎥, liq L), d(liq 비중), n(개수)}]
    → {rows, total_m3, total_kg, combined_m3, mixed, steps}. 빠진 값이 있는 줄은 계산하지 않고 표시만."""
    rows, tq, tw = [], 0.0, 0.0
    for i, it in enumerate(items or []):
        if not isinstance(it, dict):
            continue
        kind = "liq" if it.get("kind") == "liq" else "comp"
        n = _num(it.get("n")) or 1
        name = str(it.get("name") or f"설비 {i + 1}")[:30]
        if kind == "comp":
            p, v = _num(it.get("p")), _num(it.get("v"))
            if p is None or v is None:
                rows.append({"name": name, "kind": kind, "ok": False, "why": "압력·내용적을 넣어 주세요"})
                continue
            q1 = (10 * p + 1) * v
            q = q1 * n
            tq += q
            rows.append({"name": name, "kind": kind, "ok": True, "p": p, "v": v, "n": n, "each": round(q1, 3),
                         "value": round(q, 3), "unit": "㎥",
                         "step": f"Q = (10×{p:g} + 1) × {v:g} = {q1:,.3f}㎥" + (f" × {n:g}개 = {q:,.3f}㎥" if n != 1 else "")})
        else:
            d, v = _num(it.get("d")), _num(it.get("v"))
            if d is None or v is None:
                rows.append({"name": name, "kind": kind, "ok": False, "why": "비중·내용적(L)을 넣어 주세요"})
                continue
            w1 = 0.9 * d * v
            w = w1 * n
            tw += w
            rows.append({"name": name, "kind": kind, "ok": True, "d": d, "v": v, "n": n, "each": round(w1, 3),
                         "value": round(w, 3), "unit": "㎏",
                         "step": f"W = 0.9 × {d:g} × {v:g} = {w1:,.3f}㎏" + (f" × {n:g}개 = {w:,.3f}㎏" if n != 1 else "")})
    mixed = tq > 0 and tw > 0
    combined = tq + tw / 10 if mixed else (tq if tq else None)
    return {"rows": rows, "total_m3": round(tq, 3), "total_kg": round(tw, 3),
            "combined_m3": round(combined, 3) if combined is not None else None, "mixed": mixed,
            "quotes": QUOTES, "ref": REF}


def to_hwpx(res, company="", note=""):
    import hwpx_doc
    grid = [["설비", "종류", "입력값", "계산", "저장능력"]]
    for r in res["rows"]:
        if not r["ok"]:
            grid.append([r["name"], "압축가스" if r["kind"] == "comp" else "액화가스", "-", r["why"], "-"])
            continue
        inp = (f"P {r['p']:g}㎫ · V₁ {r['v']:g}㎥" if r["kind"] == "comp" else f"d {r['d']:g}㎏/L · V₂ {r['v']:g}L") \
            + (f" · {r['n']:g}개" if r["n"] != 1 else "")
        grid.append([r["name"], "압축가스" if r["kind"] == "comp" else "액화가스", inp, r["step"],
                     f"{r['value']:,.3f}{r['unit']}"])
    total = []
    if res["total_m3"]:
        total.append(("압축가스 합계", f"{res['total_m3']:,.3f}㎥"))
    if res["total_kg"]:
        total.append(("액화가스 합계", f"{res['total_kg']:,.3f}㎏"))
    if res["mixed"]:
        total.append(("합산 저장능력", f"{res['combined_m3']:,.3f}㎥ (액화가스 10㎏ = 압축가스 1㎥로 환산)"))
    q = QUOTES
    blocks = [
        ("title", "저장능력 계산서"),
        ("table", [("사업장", company or "[직접 입력]"), ("작성일", time.strftime("%Y-%m-%d")), ("근거", REF + " (저장능력 산정기준)")]),
        ("heading", "계산식 (별표 원문)"),
        ("para", f"{q['comp']} — {q['comp_f']}"),
        ("para", f"{q['liq']} — {q['liq_f']}"),
        ("para", " / ".join(q[k] for k in ("Q", "P", "V1", "W", "d", "V2"))),
        ("heading", "설비별 계산"),
        ("grid", {"rows": grid, "widths": [7000, 5000, 10000, 13000, 7520]}),
        ("heading", "합계"),
        ("table", total or [("합계", "계산된 설비 없음")]),
        ("para", f"※ 합산 기준: {q['sum']} 가. {q['sum_a']} 나. 가목의 경우를 제외한 경우로서 {q['sum_b']} {q['mix']}"),
    ]
    if note:
        blocks.append(("para", "※ " + note))
    blocks.append(("para", "※ 입력값(최고충전압력·내용적)은 설비 명판·설계서 값으로 확인하세요. 이 계산서는 작성 보조용이며 법적 효력이 없습니다."))
    return hwpx_doc.make_hwpx(blocks, title="저장능력 계산서")


def check():
    import annex_checklist
    rows = [json.loads(l) for l in open(HERE / "data" / "korea_annexes.jsonl", encoding="utf-8")]
    parts = sorted((r for r in rows if r["law"] == LAW and r["annex"] == ANNEX), key=lambda r: int(r["part"].split("/")[0]))
    body = annex_checklist._flat("".join(r["content"].split("\n", 1)[1] for r in parts))
    bad = 0
    for k, q in QUOTES.items():
        if annex_checklist._flat(q) not in body:
            print(f"✗ 저장능력 {k}: 원문에 없음 — {q[:40]}")
            bad += 1
    # 계산식 손 검산: 45㎫·0.2㎥ → (450+1)×0.2 = 90.2㎥ · 비중 0.07·1000L → 63㎏
    r = calc([{"kind": "comp", "p": 45, "v": 0.2}, {"kind": "liq", "d": 0.07, "v": 1000}])
    if r["rows"][0]["value"] != 90.2 or r["rows"][1]["value"] != 63.0 or r["combined_m3"] != 96.5:
        print("✗ 저장능력 검산 불일치", r["rows"][0]["value"], r["rows"][1]["value"], r["combined_m3"])
        bad += 1
    print(f"저장능력(별표 1): {len(QUOTES)}개 글 대조 · 검산" + (" — 전부 일치" if not bad else ""))
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--check" in sys.argv:
        sys.exit(1 if check() else 0)
    items = []
    for a in sys.argv[1:]:
        p, v, *n = a.split(":")
        items.append({"kind": "comp", "p": p, "v": v, "n": n[0] if n else 1})
    res = calc(items or [{"kind": "comp", "p": 45, "v": 0.2, "n": 10}])
    for r in res["rows"]:
        print(r.get("step") or r.get("why"))
    print("합계", res["combined_m3"], "㎥")
