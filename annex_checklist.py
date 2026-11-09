#!/usr/bin/env python3
"""별표 → 자체점검표. 별표의 시설기준을 한 줄씩 점검표 행으로 바꾼다.

왜 필요한가: 별표는 "무엇을 지켜야 하나"를 적은 글이라, 사업자가 자기 시설에 대어 보려면
항목마다 다시 정리해야 했다. 여기서는 별표를 점검표 행으로 미리 쪼개 두고(data/annex_templates/),
사업자가 시설 수치를 넣으면 거리·대수 같은 행은 코드가 판정하고 나머지는 확인할 칸으로 남긴다.

AI 를 부르지 않는다. 행의 기준 글(quote)은 별표 원문 그대로이고, --check 가 원문 조각에
실제로 있는지 대조한다. 보호시설 거리는 distance.py 표(원문 대조 끝난 값)에서 꺼낸다.

    python annex_checklist.py --check                    # 기준 글이 원문에 있는지 · KGS 항목이 있는지
    python annex_checklist.py 제조식 15000 d_prot1=20 d_boundary=8 wall=1    # 한 번 돌려 보기
    python annex_checklist.py 저장식 9000 d_store_charger=9 store_count=2 --hwpx out.hwpx
    python annex_checklist.py --id gas_annex8_storage 저장 8000 d_boundary=15    # 다른 별표 점검표
"""
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import distance

HERE = Path(__file__).parent
DIR = HERE / "data" / "annex_templates"

OK, BAD, CHECK, NA, INFO = "적합", "부적합", "확인 필요", "해당 없음", "참고"

_cache = {}


def template(tid="gas_annex5_station"):
    if tid not in _cache:
        path = DIR / f"{tid}.json"
        if not re.fullmatch(r"[a-z0-9_]+", tid) or not path.exists():
            raise KeyError(tid)
        _cache[tid] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[tid]


def catalog():
    """화면용 목록: 점검표 종류와 입력 칸."""
    out = []
    for p in sorted(DIR.glob("*.json")):
        t = template(p.stem)
        out.append({"id": t["id"], "title": t["title"], "law": t["law"], "annex": t["annex"],
                    "annex_no": int(re.search(r"\d+", t["annex"]).group()), "short": t.get("short", t["title"]),
                    "annex_title": t["annex_title"], "scope": t.get("scope", ""),
                    "facilities": {k: v["desc"] for k, v in t["facilities"].items()},
                    "inputs": t["inputs"]})
    return out


# ── 챗봇에서 점검표 권하기 ─────────────────────────────────────────
# 질문에 '어떤 시설'과 '기준·점검 쪽 말'이 함께 있으면 답 아래에 점검표 버튼을 붙인다.
# 시설 말만으로는 띄우지 않는다("충전소 허가 누구한테 받아?" 에 점검표는 엉뚱하다).
_WANT = re.compile(r"점검|체크|완성검사|중간검사|정기검사|시설\s*기준|설치\s*기준|기준|준비|"
                   r"안전\s*거리|이격|떨어|거리|방호벽|설치|지어|짓|세우")
_SUGGEST = [
    # (점검표, 시설 말, 시설 종류 짐작 [(말, 종류)])
    ("h2_annex5_use", re.compile(r"연료\s*전지|수소\s*연료\s*사용\s*시설|수소연료사용|입상관|가스\s*계량기"), []),
    ("gas_annex5_station", re.compile(r"충전소|충전\s*시설|충전\s*설비|디스펜서"),
     [(re.compile(r"제조식|수전해|추출|개질|온\s*사이트"), "제조식"),
      (re.compile(r"저장식|튜브\s*트레일러|오프\s*사이트"), "저장식")]),
    ("gas_annex8_storage", re.compile(r"저장소|저장\s*설비|저장\s*탱크|용기\s*보관|사용\s*신고|사용\s*시설|특정\s*고압가스"),
     [(re.compile(r"사용\s*신고|사용\s*시설|특정\s*고압가스|용기\s*보관|쓰는|사용하는"), "사용"),
      (re.compile(r"저장소|저장\s*탱크"), "저장")]),
]


SUGGEST_CASES = [
    ("수소충전소 완성검사 준비하려면 뭘 봐야 해?", ("gas_annex5_station", "")),
    ("제조식 충전소 안전거리는?", ("gas_annex5_station", "제조식")),
    ("튜브트레일러 쓰는 충전소 방호벽 기준", ("gas_annex5_station", "저장식")),
    ("연료전지 설치 기준이 뭐야?", ("h2_annex5_use", "")),
    ("가스계량기 전기계량기랑 얼마나 떨어져야 해?", ("h2_annex5_use", "")),
    ("수소 사용신고 하는 시설 기준", ("gas_annex8_storage", "사용")),
    ("수소 저장탱크 사업소 경계 거리", ("gas_annex8_storage", "저장")),
    ("수소충전소 허가 누구한테 받아?", None),
    ("고압가스 제조허가 수수료 얼마야?", None),
    ("규제특례에는 어떤 종류가 있어?", None),
]


def suggest(q, past=""):
    """질문(과 앞선 대화)에 맞는 점검표. [{id, title, facility, url, why}] — 없으면 빈 목록.
    시설 말은 앞선 대화에서 찾아도 되지만, 기준·점검 쪽 말은 이번 질문에 있어야 한다."""
    if not _WANT.search(q):
        return []
    out = []
    for tid, fac_re, kinds in _SUGGEST:
        here = fac_re.search(q)
        if not here and not fac_re.search(past or ""):
            continue
        t = template(tid)
        text = q if here else f"{past} {q}"
        fac = next((k for rx, k in kinds if rx.search(text)), None)
        url = f"/checklist?t={tid}" + (f"&f={urllib.parse.quote(fac)}" if fac else "")
        out.append({"id": tid, "title": t["title"], "facility": fac or "", "url": url,
                    "law": f"{t['law']} {t['annex'].strip('[]')}",
                    "rows": sum(1 for it in t["items"] if not it.get("only") or not fac or it["only"] == fac)})
        if here:                 # 이번 질문에 시설이 또렷하면 그것 하나만
            break
    return out[:2]


# ── 입력 정리 ────────────────────────────────────────────────────
def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.]", "", str(v).replace(",", ""))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "y", "yes", "예", "네", "있음", "o"):
        return True
    if s in ("0", "false", "n", "no", "아니오", "아니요", "없음", "x"):
        return False
    return None


def clean(t, vals):
    """입력 칸 정의대로 숫자·참거짓만 남긴다. 모르는 키는 버린다."""
    out = {}
    for inp in t["inputs"]:
        v = (vals or {}).get(inp["key"])
        v = _num(v) if inp["type"] == "number" else _bool(v)
        if v is not None:
            out[inp["key"]] = v
    return out


def _m(x, unit="m"):
    return f"{x:g}{unit}"


# ── 판정 ─────────────────────────────────────────────────────────
def _protection(t, fac, v, a):
    """보호시설 거리. a 의 선택:
    underground  half(지하면 ½, 별표 5 충전소) · exempt(지하면 표 적용 안 함, 별표 8)
    exempt_if    이 입력이 '예'면 표 적용 안 함(수소법 별표 5: 방호벽을 설치한 수소저장설비)
    hint         부적합일 때 덧붙일 말"""
    if a.get("underground") == "exempt" and v.get("underground"):
        return NA, "지하에 설치한 저장설비는 이 거리 표를 적용하지 않습니다.", None
    if a.get("exempt_if") and v.get(a["exempt_if"]):
        return NA, a.get("exempt_why", "적용 제외 대상입니다."), None
    cap = v.get(a.get("cap", "capacity"))
    if cap is None:
        return CHECK, "처리·저장능력을 넣으면 표에서 거리를 찾습니다.", None
    r = distance.lookup(t["facilities"][fac]["distance"], cap)
    if not r:
        return CHECK, "표 범위 밖입니다. 원문 표를 직접 확인하세요.", None
    need = []
    for i, (col, key) in enumerate((("제1종", "d_prot1"), ("제2종", "d_prot2"))):
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*m\s*", r["values"][i])
        need.append((col, key, float(m.group(1)) if m else None, r["values"][i]))
    half = a.get("underground", "half") == "half" and bool(v.get("underground"))
    parts, verdict = [], OK
    have_any = False
    for col, key, base, raw in need:
        if base is None:                     # 5만 초과 줄처럼 식이 들어간 칸
            parts.append(f"{col} 기준 '{raw}' — 원문 표 확인")
            verdict = CHECK if verdict == OK else verdict
            continue
        req = base / 2 if half else base
        d = v.get(key)
        label = f"{col} {_m(req)} 이상" + (" (지하 설치 ½)" if half else "")
        if d is None:
            parts.append(f"{label} — 거리 미입력(해당 보호시설이 없으면 무관)")
            continue
        have_any = True
        if d >= req:
            parts.append(f"{label} — 실제 {_m(d)} ✓")
        else:
            parts.append(f"{label} — 실제 {_m(d)} ✗ ({_m(req - d)} 부족)")
            verdict = BAD
    if not have_any and verdict == OK:
        verdict = CHECK
    basis = f"{r['ref']} '{r['label']}' 줄"
    note = " · ".join(parts) + f". 근거 표: {basis}. 시장·군수·구청장이 거리를 더할 수 있습니다."
    if verdict == BAD and a.get("hint"):
        note += " " + a["hint"]
    return verdict, note, f"능력 {cap:g}㎥ → {r['label']}"


def _boundary_prot1(t, fac, v, a):
    """별표 8 제1호가목1)다): 사업소 경계까지 = 경계 밖 제1종보호시설 거리(표 값), 20m 넘으면 20m."""
    if v.get("underground"):
        return NA, "지하에 설치한 저장설비는 해당 없음."
    cap, d = v.get("capacity"), v.get(a["input"])
    if cap is None:
        return CHECK, "저장능력을 넣으면 기준 거리를 계산합니다."
    r = distance.lookup(t["facilities"][fac]["distance"], cap)
    m = r and re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*m\s*", r["values"][0])
    if not m:
        return CHECK, "표에서 제1종 거리를 찾지 못했습니다. 원문 표를 확인하세요."
    base = float(m.group(1))
    need = min(base, 20)
    why = f"제1종 거리 {_m(base)}" + (" → 20m 상한" if base > 20 else "")
    if d is None:
        return CHECK, f"기준 {_m(need)} 이상({why}). 사업소 경계 거리를 넣어 주세요."
    if d >= need:
        return OK, f"기준 {_m(need)} 이상({why}) — 실제 {_m(d)} ✓"
    return BAD, f"기준 {_m(need)} 이상({why}) — 실제 {_m(d)} ✗ ({_m(need - d)} 부족)"


def _wall_or_distance(v, a):
    """별표 8 제2호가목6)가): 저장량 300㎏(압축가스 1㎥ = 5㎏) 이상 용기보관실 벽은 방호벽.
    다만 보호시설까지 표의 거리를 지키면 방호벽을 안 해도 된다."""
    q = v.get(a["input"])
    if q is None:
        return CHECK, "저장량(㎥)을 넣어 주세요."
    kg = q * a.get("kg_per_m3", 1)
    if kg < a["kg"]:
        return NA, f"저장량 {q:g}㎥ = {kg:g}㎏ → {a['kg']}㎏ 미만이라 대상 아님."
    head = f"저장량 {q:g}㎥ = {kg:g}㎏ → 방호벽 대상."
    if v.get(a["wall"]):
        return OK, head + " 용기보관실 벽을 방호벽으로 함."
    n1, n2 = a["need"]
    d1, d2 = v.get("d_prot1"), v.get("d_prot2")
    if (d1 is None or d1 >= n1) and (d2 is None or d2 >= n2) and (d1 is not None or d2 is not None):
        return OK, head + f" 방호벽 대신 보호시설 거리(제1종 {n1}m·제2종 {n2}m 이상)를 지킴."
    if v.get(a["wall"]) is None and d1 is None and d2 is None:
        return CHECK, head + f" 방호벽을 하거나 보호시설까지 제1종 {n1}m·제2종 {n2}m 이상을 지켜야 합니다."
    return BAD, head + f" 방호벽이 없고 보호시설 거리(제1종 {n1}m·제2종 {n2}m)도 못 지킴."


def _wall_indoor(v, a):
    """수소법 별표 5 제1호아목1): 저장능력 60㎥ 이상 수소저장설비를 실내에 두면 그 공간의 벽은 방호벽."""
    indoor = v.get(a["indoor"])
    if indoor is False:
        return NA, "실외 설치라 해당 없음."
    cap = v.get(a["input"])
    if cap is None or indoor is None:
        return CHECK, "저장능력과 실내 설치 여부를 넣어 주세요."
    if cap < a["min_cap"]:
        return NA, f"저장능력 {cap:g}㎥ → {a['min_cap']}㎥ 미만이라 해당 없음."
    w = v.get(a["wall"])
    if w:
        return OK, f"저장능력 {cap:g}㎥ 실내 설치 → 벽을 방호벽으로 함."
    if w is None:
        return CHECK, f"저장능력 {cap:g}㎥ 실내 설치 → 벽이 방호벽인지 넣어 주세요."
    return BAD, f"저장능력 {cap:g}㎥ 실내 설치인데 벽이 방호벽이 아닙니다."


def _range(v, a):
    x = v.get(a["input"])
    u = a.get("unit", "m")
    if x is None:
        return CHECK, "값을 넣어 주세요."
    ok = a["min"] <= x <= a["max"]
    return (OK if ok else BAD), f"기준 {_m(a['min'], u)} 이상 {_m(a['max'], u)} 이내 — 실제 {_m(x, u)} {'✓' if ok else '✗'}"


def _wall30(v):
    near, wall = v.get("bld_30m"), v.get("wall")
    if near is None:
        return CHECK, "30m 안 건축물 여부를 넣어 주세요."
    if not near:
        return NA, "30m 안에 사람을 수용하는 건축물이 없음."
    if wall:
        return OK, "30m 안 건축물 있음 → 방호벽 설치 계획 있음."
    if wall is None:
        return CHECK, "30m 안 건축물 있음 → 방호벽 설치 여부를 넣어 주세요."
    return BAD, "30m 안 건축물이 있는데 방호벽이 없습니다."


def _other(v):
    f, o = v.get("d_flam"), v.get("d_o2")
    if f is None and o is None:
        return NA, "주변에 다른 가연성가스·산소 제조시설이 없으면 해당 없음."
    parts, verdict = [], OK
    for d, need, name in ((f, 5, "가연성가스 제조시설"), (o, 10, "산소 제조시설")):
        if d is None:
            continue
        ok = d >= need
        parts.append(f"{name} {need}m 이상 — 실제 {_m(d)} {'✓' if ok else '✗'}")
        if not ok:
            verdict = BAD
    return verdict, " · ".join(parts)


def _min(a, v):
    u = a.get("unit", "m")
    d = v.get(a["input"])
    if d is None:
        return (NA, "해당 시설이 근처에 없으면 해당 없음.") if a.get("blank_na") else (CHECK, "거리를 넣어 주세요.")
    alt = v.get(a["alt_if"]) if a.get("alt_if") else None
    if alt and not a["alt_min"]:                 # 방호벽·평가가 있으면 거리 기준 자체가 풀리는 경우
        return OK, f"{a['alt_why']} → {_m(a['min'], u)} 기준 예외 — 실제 {_m(d, u)}"
    need = a["alt_min"] if alt else a["min"]
    why = f" ({a['alt_why']} 시 {'완화' if need < a['min'] else '기준'})" if alt else ""
    if d >= need:
        return OK, f"기준 {_m(need, u)} 이상{why} — 실제 {_m(d, u)} ✓"
    msg = f"기준 {_m(need, u)} 이상{why} — 실제 {_m(d, u)} ✗ ({_m(round(need - d, 2), u)} 부족)"
    if not alt and a.get("alt_if") and a["alt_min"] < a["min"]:
        msg += f". {a['alt_why']} 시 {_m(a['alt_min'], u)} 이상이면 됩니다." if a["alt_min"] else f". {a['alt_why']} 시 예외."
    return BAD, msg


def judge(t, item, fac, v):
    """→ (판정, 설명, 덧붙일 계산 줄 또는 None)"""
    a = item.get("auto")
    if item.get("info"):
        return INFO, item.get("info_note", "거리 기준을 못 맞출 때 쓸 수 있는 예외. 한국가스안전공사와 협의가 필요합니다."), None
    if not a:
        return CHECK, "", None
    if a.get("na_if") and v.get(a["na_if"]):          # 예: 보호상자 안 입상관
        return NA, a.get("na_why", "해당 없음."), None
    kind = a["type"]
    if kind == "protection":
        return _protection(t, fac, v, a)
    if kind == "boundary_prot1":
        return (*_boundary_prot1(t, fac, v, a), None)
    if kind == "wall_or_distance":
        return (*_wall_or_distance(v, a), None)
    if kind == "wall_indoor":
        return (*_wall_indoor(v, a), None)
    if kind == "range":
        return (*_range(v, a), None)
    if kind == "wall30":
        return (*_wall30(v), None)
    if kind == "other":
        return (*_other(v), None)
    if kind == "min":
        return (*_min(a, v), None)
    if kind == "max":
        n = v.get(a["input"])
        if n is None:
            return CHECK, "대수를 넣어 주세요.", None
        return (OK if n <= a["max"] else BAD), f"기준 {a['max']}대 이하 — 계획 {n:g}대", None
    if kind == "flag":
        f = v.get(a["input"])
        if f is None:
            return CHECK, "처음 설치하거나 위치·수량·용량을 늘리면 대상입니다.", None
        return (CHECK, "대상입니다 — 평가를 받고 결과대로 보완해야 합니다.", None) if f else (NA, "신규·증설이 아님.", None)
    return CHECK, "", None


def build(fac, vals, tid="gas_annex5_station", marks=None):
    """점검표 한 장. rows 는 화면·문서가 그대로 쓰는 모양.
    marks: 사람이 확인한 행의 판정 {행 id: 적합|부적합|해당 없음}. 코드가 판정한 행에는 쓰지 않는다."""
    marks = marks if isinstance(marks, dict) else {}
    t = template(tid)
    if fac not in t["facilities"]:
        raise ValueError(f"시설 종류는 {', '.join(t['facilities'])} 중 하나입니다")
    v = clean(t, vals)
    F = t["facilities"][fac]
    rows, count = [], {}
    for it in t["items"]:
        if it.get("only") and it["only"] != fac:
            continue
        verdict, note, calc = judge(t, it, fac, v)
        manual = marks.get(it["id"])
        if verdict == CHECK and not it.get("auto") and manual in (OK, BAD, NA):
            verdict, note = manual, "사용자 확인"
        count[verdict] = count.get(verdict, 0) + 1
        # 시설 종류마다 원문이 다르면 quotes 에 따로 둔다(quote_s 는 충전소 저장식용 옛 이름)
        quote = (it.get("quotes") or {}).get(fac) or (it.get("quote_s") if fac == "저장식" else None) or it["quote"]
        rows.append({
            "id": it["id"], "group": it["group"], "title": it["title"],
            "quote": quote,
            "ref": f"{t['annex'].strip('[]')} {it['ref'][fac]}",
            "kgs": f"{F['kgs']} {it['kgs']}" if it.get("kgs") and F.get("kgs") else "",
            "mid": fac in it.get("mid", []),
            "auto": bool(it.get("auto")),
            "verdict": verdict, "note": note, "calc": calc,
        })
    return {"id": t["id"], "title": t["title"], "facility": fac, "facility_desc": F["desc"],
            "law": t["law"], "annex": t["annex"], "annex_title": t["annex_title"],
            "kgs_code": F.get("kgs", ""), "scope": t.get("scope", ""),
            "inputs": v, "rows": rows, "count": count,
            "made": time.strftime("%Y-%m-%d")}


# ── 문서 ─────────────────────────────────────────────────────────
def to_hwpx(sheet, company=""):
    import hwpx_doc
    c = sheet["count"]
    names = {i["key"]: i["q"] for i in template(sheet["id"])["inputs"]}
    inputs = [(names.get(k, k).split(" (")[0][:28], ("예" if v is True else "아니오" if v is False else f"{v:g}"))
              for k, v in sheet["inputs"].items()]
    grid = [["번호", "점검 항목", "기준 (별표 원문)", "근거", "판정·메모"]]
    for i, r in enumerate(sheet["rows"], 1):
        basis = r["ref"] + (f"\n{r['kgs']}" if r["kgs"] else "") + ("\n[중간검사]" if r["mid"] else "")
        memo = r["verdict"] + (f" — {r['note']}" if r["note"] else "")
        if r["verdict"] == CHECK and not r["auto"]:          # 아직 안 본 행은 종이에 체크할 칸으로
            memo = "□ 적합  □ 부적합  □ 해당 없음"
        grid.append([str(i), f"[{r['group']}] {r['title']}", r["quote"], basis, memo])
    blocks = [
        ("title", f"{sheet['title']} ({sheet['facility']})"),
        ("para", f"{sheet['law']} {sheet['annex']} {sheet['annex_title']} 중 시설기준 항목을 "
                 "점검표로 옮긴 것입니다. 기준 글은 별표 원문 그대로이며, 세부 수치는 "
                 + (f"{sheet['kgs_code']} 를" if sheet["kgs_code"] else "KGS Code 를") + " 함께 확인하세요."
                 + (f" {sheet['scope']}" if sheet["scope"] else "")),
        ("table", [("사업장", company or "[직접 입력]"), ("시설 종류", f"{sheet['facility']} — {sheet['facility_desc']}"),
                   ("작성일", sheet["made"]),
                   ("판정 요약", " · ".join(f"{k} {c[k]}" for k in (OK, BAD, CHECK, NA, INFO) if c.get(k)))]),
    ]
    if inputs:
        blocks += [("heading", "입력한 시설 정보"), ("table", inputs)]
    blocks += [
        ("heading", "점검 항목"),
        ("grid", {"rows": grid, "widths": [2600, 8200, 15000, 7400, 9320]}),
        ("para", "※ 완성검사는 시설기준 전 항목이 대상입니다. "
                 + (f"[중간검사] 표시는 {sheet['annex'].strip('[]')} 검사기준 표의 중간검사 항목입니다. "
                    if any(r["mid"] for r in sheet["rows"]) else "")
                 + "자동 판정은 입력값 기준의 참고용이며 법적 효력이 없습니다. 최종 판단은 한국가스안전공사·관할 관청에 확인하세요."),
    ]
    return hwpx_doc.make_hwpx(blocks, title=sheet["title"])


# ── 원문 대조 ─────────────────────────────────────────────────────
def _flat(s):
    s = re.sub(r"\s+", "", s)
    return re.sub(r"[ᆞㆍ·․‧]", "·", s)


def check(tid=None):
    """기준 글(quote)이 별표 원문 조각에 있는지, KGS 항목이 자료에 있는지 대조한다."""
    bad = 0
    annex_rows = [json.loads(l) for l in open(HERE / "data" / "korea_annexes.jsonl", encoding="utf-8")]
    kgs_items, kgs_text = {}, {}
    for l in open(HERE / "data" / "kgs_code.jsonl", encoding="utf-8"):
        r = json.loads(l)
        kgs_items.setdefault(r["law"], set()).add(r["item"])
        kgs_text[r["law"]] = kgs_text.get(r["law"], "") + " " + re.sub(r"\s+", " ", r["content"])
    ids = [tid] if tid else [p.stem for p in sorted(DIR.glob("*.json"))]
    for t_id in ids:
        t = template(t_id)
        data_law = t.get("data_law", t["law"])          # 자료 속 법령명(띄어쓰기 없이 들어 있는 것도 있다)
        parts = [r for r in annex_rows if r["law"] == data_law and r["annex"] == t["annex"]]
        parts.sort(key=lambda r: int(r["part"].split("/")[0]))
        # 조각 사이에서 문장이 끊기므로 머리줄을 떼고 이어 붙여 대조한다
        body = _flat("".join(r["content"].split("\n", 1)[1] if r["content"].startswith(r["law"]) else r["content"]
                             for r in parts))
        if not body:
            print(f"✗ {t_id}: 원문 조각을 찾지 못함 ({t['law']} {t['annex']})")
            bad += 1
            continue
        seen = set()
        for it in t["items"]:
            if it["id"] in seen:
                print(f"✗ {t_id} {it['id']}: id 중복")
                bad += 1
            seen.add(it["id"])
            texts = [("quote", it.get("quote")), ("quote_s", it.get("quote_s"))]
            texts += [(f"quotes.{f}", q) for f, q in (it.get("quotes") or {}).items()]
            for k, q in texts:
                if q and _flat(q) not in body:
                    print(f"✗ {t_id} {it['id']} {k}: 원문에 없음 — {q[:40]}…")
                    bad += 1
            if it.get("kgs"):
                for fac, F in t["facilities"].items():
                    if (it.get("only") and it["only"] != fac) or not F.get("kgs"):
                        continue
                    have = kgs_items.get(F["kgs"], set())
                    # 항목이 조각 머리가 아니라 앞 조각 본문 속에 들어 있는 경우도 있다(FP217 2.6.7)
                    if not any(x == it["kgs"] or x.startswith(it["kgs"] + ".") for x in have) \
                            and f" {it['kgs']} " not in kgs_text.get(F["kgs"], ""):
                        print(f"✗ {t_id} {it['id']}: {F['kgs']} {it['kgs']} 항목이 자료에 없음")
                        bad += 1
            for fac in t["facilities"]:
                if (not it.get("only") or it["only"] == fac) and fac not in it["ref"]:
                    print(f"✗ {t_id} {it['id']}: {fac} 근거 조항 없음")
                    bad += 1
        n = len(t["items"])
        print(f"{t_id}: {n}행 대조" + (" — 전부 원문과 일치" if not bad else ""))
    # 챗봇 버튼 규칙: 띄워야 할 질문엔 맞는 점검표가, 엉뚱한 질문엔 아무것도 안 떠야 한다
    for q, want in SUGGEST_CASES:
        got = [(x["id"], x["facility"]) for x in suggest(q)]
        if (got[:1] if want else got) != ([want] if want else []):
            print(f"✗ 점검표 권하기: '{q}' → {got} (기대 {want})")
            bad += 1
    print(f"점검표 권하기 {len(SUGGEST_CASES)}문항 확인")
    if bad:
        print(f"{bad}개 어긋남")
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if "--check" in args:
        sys.exit(1 if check() else 0)
    out, tid = None, "gas_annex5_station"
    if "--id" in args:
        i = args.index("--id")
        tid = args[i + 1]
        del args[i:i + 2]
    if "--hwpx" in args:
        i = args.index("--hwpx")
        out = args[i + 1]
        del args[i:i + 2]
    fac = args[0] if args else next(iter(template(tid)["facilities"]))
    vals = {"capacity": args[1]} if len(args) > 1 else {}
    for a in args[2:]:
        k, _, val = a.partition("=")
        vals[k] = val
    sheet = build(fac, vals, tid)
    for r in sheet["rows"]:
        mark = {OK: "✓", BAD: "✗", NA: "-", INFO: "i"}.get(r["verdict"], "□")
        print(f"{mark} [{r['group']}] {r['title']:<28} {r['ref']:<28} {r['note'][:90]}")
    print(" · ".join(f"{k} {v}" for k, v in sheet["count"].items()))
    if out:
        Path(out).write_bytes(to_hwpx(sheet))
        print(f"→ {out}")
