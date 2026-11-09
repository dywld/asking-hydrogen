#!/usr/bin/env python3
"""별표(안전관리규정 작성요령) → 안전관리규정 초안.

왜 필요한가: 허가 신청서에는 "안전관리규정 1부"를 붙여야 하는데, 무엇을 담아야 하는지는
작성요령 별표(고압가스법 시행규칙 별표 15, 수소법 시행규칙 별표 2)에만 있다. 여기서는 별표의
항목을 장(章)으로, 세부 항목을 조(條)로 세운 뼈대를 만들고, 사업장 정보를 채운다.
조문 본문은 지어내지 않고 '[직접 입력]'으로 남긴다(목적 조만 정형 문장).

AI 를 부르지 않는다. 장 제목·작성할 내용은 별표 원문 그대로이고 --check 가 대조한다.

    python safety_rules.py --check
    python safety_rules.py gas_annex15 제조 --hwpx 규정.hwpx company=○○수소 facility=삼척충전소
"""
import json
import re
import sys
import time
from pathlib import Path

import annex_checklist

HERE = Path(__file__).parent
DIR = HERE / "data" / "rule_templates"
NEED = "[직접 입력]"
INFO_KEYS = {"company": "사업장(회사) 이름", "ceo": "대표자", "address": "소재지",
             "facility": "시설 이름·종류", "date": "제정일"}

_cache = {}


def template(tid):
    if tid not in _cache:
        path = DIR / f"{tid}.json"
        if not re.fullmatch(r"[a-z0-9_]+", tid or "") or not path.exists():
            raise KeyError(tid)
        _cache[tid] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[tid]


def catalog():
    out = []
    for p in sorted(DIR.glob("*.json")):
        t = template(p.stem)
        out.append({"id": t["id"], "title": t["title"], "short": t["short"], "law": t["law"],
                    "annex": t["annex"], "annex_no": int(re.search(r"\d+", t["annex"]).group()),
                    "act": t["act"], "article": t["article"], "detail": t["detail"],
                    "kinds": t["kinds"], "flags": t["flags"], "info": INFO_KEYS})
    return out


def _d(s):
    """화면·문서용: 자료 속 옛 가운뎃점(ᆞ·ㆍ)을 보통 가운뎃점으로. 대조는 원래 글로 한다."""
    return re.sub(r"[ᆞㆍ]", "·", s)


def _short(s):
    """'자율검사 주기 및 대상에 관한 사항' → '자율검사 주기 및 대상' (조 제목용)."""
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"(에 관한 사항|에 관한 |에 대한 |의 관리)$", "", s.strip())
    s = re.sub(r"\s*에\s*관한\s*사항$", "", s).strip()
    if len(s) > 26:                       # 긴 항목은 단어 경계에서 자르고 '…'
        cut = s[:26].rsplit(" ", 1)[0]
        s = cut.rstrip(" ,·및") + "…"
    return s


def build(tid, kind, flags=None, info=None, exclude=None):
    """초안 한 벌. chapters 의 status: 필수 · 확인(우리 사업이 해당하는지 사람이 확인) · 제외.
    별표 15 의 '사업 종류별 기재사항 표'(제1호러목)는 자료에서 칸 위치가 사라져, ○가 어느 사업 종류인지
    모르는 줄이 있다. 그런 장은 지어내지 않고 '확인'으로 둔다."""
    t = template(tid)
    if kind not in t["kinds"]:
        raise ValueError(f"사업 종류는 {', '.join(t['kinds'])} 중 하나입니다")
    flags = {k for k, v in (flags or {}).items() if v and k in t["flags"]}
    info = {k: str(v).strip()[:60] for k, v in (info or {}).items() if k in INFO_KEYS and str(v).strip()}
    exclude = set(exclude or [])
    annex = t["annex"].strip("[]")
    chapters, art = [], 0

    def articles(ch):
        nonlocal art
        out = []
        if ch.get("draft"):
            art += 1
            text = ch["draft"].format(act=t["act"], article=t["article"],
                                      company=info.get("company", NEED), facility=info.get("facility", NEED))
            out.append({"no": art, "title": _short(_d(ch["title"])), "text": text})
            return out
        for s in (ch["subs"] or [ch["title"]]):
            art += 1
            out.append({"no": art, "title": _short(_d(s)), "text": NEED})
        return out

    for ch in t["chapters"]:
        if ch.get("only") == "special":
            status = "필수" if "special" in flags else "제외"
            why = "고압가스특정제조자만 해당" + ("" if status == "필수" else " — 특정제조자가 아니라 뺌")
        elif ch.get("marks", 4) >= 4:
            status, why = "필수", "모든 업종에 포함"
        else:
            status = "확인"
            why = (f"사업 종류에 따라 넣을지가 달라지는 항목입니다(4개 사업 종류 중 {ch['marks']}개만 해당). "
                   f"별표 원문의 '사업 종류별 기재사항 표'에서 '{kind}'에 ○가 있으면 남기고, 없으면 빼세요.")
        if ch["id"] in exclude and status == "확인":
            status, why = "제외", "사용자가 뺌 (우리 사업 종류에는 해당 없음)"
        row = {"id": ch["id"], "title": _d(ch["title"]), "ref": f"{annex} {ch['ref']}"
               + (f" · 기재사항 표 {ch['no']}번" if ch.get("no") else ""),
               "status": status, "why": why, "note": ch.get("note", ""), "subs": [_d(x) for x in ch["subs"]],
               "table": ch.get("table"), "articles": []}
        if status != "제외":
            row["articles"] = articles(ch)
        chapters.append(row)
    if "comprehensive" in flags:
        for ch in t["comprehensive"]:
            row = {"id": ch["id"], "title": _d(ch["title"]), "ref": f"{annex} {ch['ref']}", "status": "필수",
                   "why": "종합적 안전관리대상자 항목", "note": "", "subs": [_d(x) for x in ch["subs"]], "table": None}
            row["articles"] = articles(ch)
            chapters.append(row)
    n = 0
    for ch in chapters:
        if ch["status"] != "제외":
            n += 1
            ch["chapter"] = n
    return {"id": t["id"], "title": t["title"], "act": t["act"], "article": t["article"],
            "law": t["law"], "annex": t["annex"], "annex_title": t["annex_title"], "detail": t["detail"],
            "kind": kind, "kind_desc": t["kinds"][kind], "flags": sorted(flags), "info": info,
            "chapters": chapters, "articles": art,
            "count": {s: sum(1 for c in chapters if c["status"] == s) for s in ("필수", "확인", "제외")},
            "made": time.strftime("%Y-%m-%d")}


def to_hwpx(doc):
    import hwpx_doc
    info = doc["info"]
    live = [c for c in doc["chapters"] if c["status"] != "제외"]
    blocks = [
        ("title", f"{info.get('company', '')} 안전관리규정 (초안)".strip()),
        ("para", f"「{doc['act']}」 {doc['article']}에 따른 안전관리규정의 뼈대입니다. 장 제목과 '작성할 내용'은 "
                 f"{doc['law']} {doc['annex']} {doc['annex_title']} 원문 그대로이고, 조문 본문의 [직접 입력]은 "
                 "사업장 실정에 맞게 채워야 합니다."),
        ("table", [(INFO_KEYS[k], info.get(k) or (doc["made"] if k == "date" else NEED)) for k in INFO_KEYS]
         + [("사업 종류", doc["kind_desc"])]),
        ("heading", "목차"),
        ("para", "  ".join(f"제{c['chapter']}장 {c['title']}" for c in live)),
    ]
    for c in live:
        blocks.append(("heading", f"제{c['chapter']}장 {c['title']}"))
        blocks.append(("para", f"근거: {c['ref']}"))
        if c["status"] == "확인":
            blocks.append(("para", f"※ {c['why']}"))
        if c["note"]:
            blocks.append(("para", f"※ {c['note']}"))
        if c["subs"]:
            blocks.append(("para", "작성할 내용 (별표 원문): " + " / ".join(c["subs"])))
        for a in c["articles"]:
            blocks.append(("para", f"제{a['no']}조({a['title']}) {a['text']}"))
        if c.get("table") == "managers":
            blocks.append(("grid", {"rows": [["구분", "성명", "자격", "선임일", "직무"]]
                                    + [[NEED, "", "", "", ""] for _ in range(4)],
                                    "widths": [9000, 7000, 9000, 7000, 10520]}))
    grid = [["별표 항목", "이 초안", "비고"]]
    for c in doc["chapters"]:
        grid.append([f"{c['ref']}\n{c['title']}",
                     f"제{c['chapter']}장" if c["status"] != "제외" else "제외",
                     c["why"] if c["status"] != "필수" else ""])
    blocks += [("heading", "포함 항목 대조표"), ("grid", {"rows": grid, "widths": [18000, 6000, 18520]}),
               ("para", "※ " + doc["detail"]),
               ("para", "※ 이 문서는 작성 보조용 초안이며 법적 효력이 없습니다. 제출 전 관할 관청·한국가스안전공사 기준과 대조하세요.")]
    return hwpx_doc.make_hwpx(blocks, title=doc["title"])


# ── 챗봇에서 권하기 ───────────────────────────────────────────────
_ASK = re.compile(r"안전\s*관리\s*규정")
_H2 = re.compile(r"수소법|수소경제|수소용품|연료\s*전지|수전해\s*설비\s*제조|제41조")


def suggest(q, past=""):
    """'안전관리규정' 이야기가 나오면 초안 버튼. 수소법 쪽 말이 있으면 수소법 별표 2, 아니면 고압가스법 별표 15."""
    if not _ASK.search(q):
        return []
    tid = "h2_annex2" if _H2.search(q) or (_H2.search(past or "") and not re.search(r"고압가스", q)) else "gas_annex15"
    t = template(tid)
    return [{"id": tid, "title": f"{t['title']} 초안 만들기", "facility": "", "url": f"/rules?t={tid}",
             "law": f"{t['law']} {t['annex'].strip('[]')}",
             "desc": f"{t['law']} {t['annex'].strip('[]')} 항목을 장·조로 세운 뼈대 · 사업장 정보 채움 · 한글(HWPX)로 받기"}]


# ── 원문 대조 ─────────────────────────────────────────────────────
def check():
    bad = 0
    rows = [json.loads(l) for l in open(HERE / "data" / "korea_annexes.jsonl", encoding="utf-8")]
    for p in sorted(DIR.glob("*.json")):
        t = template(p.stem)
        law = t.get("data_law", t["law"])
        parts = sorted((r for r in rows if r["law"] == law and r["annex"] == t["annex"]),
                       key=lambda r: int(r["part"].split("/")[0]))
        body = annex_checklist._flat("".join(
            r["content"].split("\n", 1)[1] if r["content"].startswith(r["law"]) else r["content"] for r in parts))
        if not body:
            print(f"✗ {t['id']}: 원문 조각 없음")
            bad += 1
            continue
        texts = []
        for ch in t["chapters"] + t["comprehensive"]:
            texts += [(ch["id"], q) for q in ch.get("quote", [])]
            texts += [(ch["id"], s) for s in ch["subs"]]
            texts.append((ch["id"], ch["title"]))
        n0 = bad
        for cid, q in texts:
            if annex_checklist._flat(q) not in body:
                print(f"✗ {t['id']} {cid}: 원문에 없음 — {q[:40]}…")
                bad += 1
        print(f"{t['id']}: {len(texts)}개 글 대조" + (" — 전부 원문과 일치" if bad == n0 else ""))
    cases = [("충전소 안전관리규정 어떻게 써?", "gas_annex15"), ("수소용품 제조사업 안전관리규정 작성", "h2_annex2"),
             ("연료전지 안전관리규정 항목", "h2_annex2"), ("충전소 허가 누구한테 받아?", None)]
    for q, want in cases:
        got = [x["id"] for x in suggest(q)]
        if got != ([want] if want else []):
            print(f"✗ 초안 권하기: '{q}' → {got} (기대 {want})")
            bad += 1
    print(f"초안 권하기 {len(cases)}문항 확인")
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if "--check" in args:
        sys.exit(1 if check() else 0)
    out = None
    if "--hwpx" in args:
        i = args.index("--hwpx")
        out = args[i + 1]
        del args[i:i + 2]
    tid = args[0] if args else "gas_annex15"
    kind = args[1] if len(args) > 1 else next(iter(template(tid)["kinds"]))
    kv = dict(a.partition("=")[::2] for a in args[2:])
    flags = {k: True for k in ("special", "comprehensive") if kv.pop(k, None)}
    d = build(tid, kind, flags, kv)
    for c in d["chapters"]:
        print(f"[{c['status']}] {('제%d장' % c['chapter']) if c.get('chapter') else '  -  '} {c['title']:<40} {c['ref']}")
    print(f"조문 {d['articles']}개 ·", " · ".join(f"{k} {v}" for k, v in d["count"].items()))
    if out:
        Path(out).write_bytes(to_hwpx(d))
        print(f"→ {out}")
