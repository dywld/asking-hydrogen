#!/usr/bin/env python3
"""제출 꾸러미 — 신청서 + 자체점검표 + 안전관리규정 초안 + 저장능력 계산서를 zip 하나로.

맨 앞에 '표지(제출 체크리스트)'를 둔다: 서식 본문에 적힌 첨부서류·접수기관·처리기간·수수료
(permit_forms.FORMS, 서식 PDF 에서 옮긴 값), 신청서 빈칸, 점검표에서 부적합·확인 필요로 나온 행,
꾸러미에 든 파일 목록. 첨부서류가 꾸러미에 없으면 '직접 준비'로 적는다(만든 척하지 않는다).

AI 를 부르지 않는다. 각 문서는 annex_checklist · safety_rules · storage_calc · permit_forms 가 만든다.
"""
import io
import re
import time
import zipfile

# 신청서마다 같이 보면 좋은 점검표·안전관리규정 (권하기만, 사용자가 끄고 켠다)
SUGGEST = {
    "gas_permit": {"checklist": "gas_annex5_station", "rules": ("gas_annex15", None)},
    "gas_report": {"checklist": "gas_annex8_storage", "rules": ("gas_annex15", "제조")},
    "gas_use": {"checklist": "gas_annex8_storage", "facility": "사용", "rules": None},
    "gas_inspect": {"checklist": "gas_annex5_station", "rules": ("gas_annex15", "제조")},
    "h2_maker": {"checklist": None, "rules": ("h2_annex2", "수소")},
    "h2_product": {"checklist": None, "rules": None},
    "h2_use_inspect": {"checklist": "h2_annex5_use", "rules": ("h2_annex2", "수소")},
}


def catalog():
    import permit_forms
    out = []
    for f in permit_forms.catalog():
        s = SUGGEST.get(f["id"], {})
        out.append({**f, "suggest": {"checklist": s.get("checklist"), "facility": s.get("facility"),
                                     "rules": list(s["rules"]) if s.get("rules") else None}})
    return out


def build(req, vals_clean):
    """req: {permit:{id, fields, fmt}, checklist?, rules?, storage?, company?}
    vals_clean: 신청서 칸을 정리하는 함수(app.permit_vals). → (zip bytes, 파일 이름, 요약)"""
    import permit_forms
    import hwpx_doc
    p = req.get("permit") or {}
    fid = p.get("id")
    if fid not in permit_forms.FORMS:
        raise ValueError("신청서 종류(id)가 없습니다")
    f = permit_forms.FORMS[fid]
    vals = vals_clean(p.get("fields"))
    for t in f["fields"]:                            # 서식이 정해 둔 기본값(예: 가스 종류 '압축수소')
        if len(t) > 5 and t[5] and not (vals.get(t[0]) or "").strip():
            vals[t[0]] = t[5]
    company = (vals.get("company") or str(req.get("company") or "")).strip()[:40]
    files, notes, summary = [], [], {}

    # 1) 신청서
    fmt = p.get("fmt") or "both"
    if fmt in ("pdf", "both"):
        try:
            data, _ = permit_forms.fill(fid, vals, "black")
            files.append(("01_신청서.pdf", data, f"{f['title']} 신청서 (공식 서식 PDF에 채움)"))
        except Exception as e:                       # 법령정보센터에 못 가면 PDF 는 빠진다
            notes.append(f"공식 서식 PDF 를 받지 못해 신청서 PDF 를 넣지 못했습니다({e}). HWPX 정리본을 참고하세요.")
    if fmt in ("hwpx", "both") or not any(n.endswith(".pdf") for n, *_ in files):
        data, _ = permit_forms.fill_hwpx(fid, vals)
        files.append(("01_신청서_정리본.hwpx", data, f"{f['title']} 신청서 항목 정리본 (한글)"))
    empty = [t[2].split(" (")[0] for t in f["fields"] if not (vals.get(t[0]) or "").strip()]

    # 2) 자체점검표
    ck = req.get("checklist")
    if isinstance(ck, dict) and ck.get("id"):
        import annex_checklist
        sheet = annex_checklist.build(str(ck.get("facility") or ""), ck.get("inputs") or {}, str(ck["id"]), ck.get("marks"))
        files.append((f"02_자체점검표_{sheet['facility']}.hwpx", annex_checklist.to_hwpx(sheet, company),
                      f"{sheet['title']} ({sheet['facility']}) — {sheet['law']} {sheet['annex'].strip('[]')}"))
        summary["checklist"] = {"title": sheet["title"], "count": sheet["count"],
                                "bad": [f"{r['title']} — {r['note']}" for r in sheet["rows"] if r["verdict"] == "부적합"],
                                "todo": sum(1 for r in sheet["rows"] if r["verdict"] == "확인 필요")}

    # 3) 안전관리규정 초안
    ru = req.get("rules")
    if isinstance(ru, dict) and ru.get("id"):
        import safety_rules
        info = dict(ru.get("info") or {})
        info.setdefault("company", company)
        doc = safety_rules.build(str(ru["id"]), str(ru.get("kind") or ""), ru.get("flags") or {}, info, ru.get("exclude") or [])
        files.append(("03_안전관리규정_초안.hwpx", safety_rules.to_hwpx(doc),
                      f"{doc['title']} 초안 — {doc['law']} {doc['annex'].strip('[]')}"))
        summary["rules"] = {"title": doc["title"], "count": doc["count"]}

    # 4) 저장능력 계산서
    st = req.get("storage")
    if isinstance(st, dict) and st.get("items"):
        import storage_calc
        res = storage_calc.calc(st["items"])
        if any(r["ok"] for r in res["rows"]):
            files.append(("04_저장능력_계산서.hwpx", storage_calc.to_hwpx(res, company),
                          f"저장능력 계산서 — {storage_calc.REF}"))
            summary["storage"] = res["combined_m3"]

    # 0) 표지
    made = {d for _, _, d in files}
    docs_rows = [(d, "직접 준비") for d in f["docs"]] or [("없음", "-")]
    blocks = [
        ("title", f"{f['title']} 제출 꾸러미"),
        ("table", [("사업장", company or "[직접 입력]"), ("신청서", f"{f['law']} 별지 제{f['no']}호서식 — {f['title']}"),
                   ("접수 기관", f["who"]), ("처리 기간", f["days"]), ("수수료", f["fee"]), ("만든 날", time.strftime("%Y-%m-%d"))]),
    ]
    if f.get("before"):
        blocks.append(("para", "먼저 할 일: " + f["before"]))
    blocks += [("heading", "서식에 적힌 첨부서류"), ("table", docs_rows),
               ("para", "※ 첨부서류는 서식 본문 그대로입니다. 이 꾸러미에는 만들어 넣지 않았으니 직접 준비하세요.")]
    if empty:
        blocks += [("heading", f"신청서 빈칸 {len(empty)}곳"), ("para", " · ".join(empty))]
    if "checklist" in summary:
        c = summary["checklist"]
        blocks += [("heading", "자체점검 결과"),
                   ("para", " · ".join(f"{k} {v}" for k, v in c["count"].items()) + f" — 확인 필요 {c['todo']}행은 현장·도면으로 확인하세요.")]
        if c["bad"]:
            blocks.append(("table", [(f"보완 {i}", b[:120]) for i, b in enumerate(c["bad"], 1)]))
    blocks += [("heading", "이 꾸러미에 든 파일"),
               ("grid", {"rows": [["파일", "내용"]] + [[n, d] for n, _, d in files], "widths": [14000, 28520]})]
    for n in notes:
        blocks.append(("para", "※ " + n))
    if f.get("after"):
        blocks.append(("para", "다음 할 일: " + f["after"]))
    blocks.append(("para", "※ 이 꾸러미는 작성 보조용입니다. 자동 판정·초안은 법적 효력이 없으니 제출 전 접수 기관 기준과 대조하세요."))
    cover = hwpx_doc.make_hwpx(blocks, title="제출 꾸러미 표지")
    files.insert(0, ("00_표지_제출체크리스트.hwpx", cover, "표지"))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data, _ in files:
            z.writestr(name, data)
    name = f"{f['title']}_제출꾸러미" + (f"_{company}" if company else "") + ".zip"
    summary.update({"files": [n for n, *_ in files], "empty": empty, "notes": notes})
    return buf.getvalue(), name, summary


# ── 챗봇에서 권하기 ───────────────────────────────────────────────
_PKG = re.compile(r"꾸러미|서류.{0,8}(한꺼번에|한번에|한 번에|묶|모아)|제출\s*서류.{0,8}(준비|정리|챙기|목록)|첨부\s*서류.{0,8}(준비|챙기|목록|뭐)")
_CAP = re.compile(r"저장\s*능력.{0,10}(계산|산정|구하|어떻게)|저장능력\s*산정")
SUGGEST_CASES = [("허가 신청 서류 한꺼번에 준비하고 싶어", "package"), ("첨부서류 뭐 챙겨야 해?", "package"),
                 ("튜브트레일러 저장능력 계산 어떻게 해?", "storage"), ("저장능력 산정기준 알려줘", "storage"),
                 ("수소충전소 안전거리는?", None)]


def suggest(q, past=""):
    out = []
    if _CAP.search(q):
        out.append({"id": "storage", "title": "저장능력 계산기 (고압가스법 시행규칙 별표 1)", "facility": "",
                    "url": "/checklist#calc", "law": "고압가스 안전관리법 시행규칙 별표 1",
                    "desc": "압축가스 Q=(10P+1)V₁ — 압력·내용적을 넣으면 설비별·합계 계산, 점검표에 바로 넣기, 계산서(HWPX)"})
    if _PKG.search(q):
        out.append({"id": "package", "title": "제출 꾸러미 만들기", "facility": "", "url": "/package",
                    "law": "", "desc": "신청서 + 자체점검표 + 안전관리규정 초안 + 저장능력 계산서를 zip 하나로, 첨부서류 체크리스트 표지 포함"})
    return out


def check():
    bad = 0
    for q, want in SUGGEST_CASES:
        got = [x["id"] for x in suggest(q)]
        if got[:1] != ([want] if want else []):
            print(f"✗ 꾸러미·계산기 권하기: '{q}' → {got} (기대 {want})")
            bad += 1
    import permit_forms
    for fid, s in SUGGEST.items():                 # 권하는 점검표·규정이 실제로 있는지
        if fid not in permit_forms.FORMS:
            print(f"✗ 꾸러미: 없는 신청서 {fid}"); bad += 1
        if s.get("checklist"):
            import annex_checklist
            try:
                t = annex_checklist.template(s["checklist"])
                if s.get("facility") and s["facility"] not in t["facilities"]:
                    print(f"✗ 꾸러미: {fid} 시설 종류 {s['facility']} 없음"); bad += 1
            except KeyError:
                print(f"✗ 꾸러미: 없는 점검표 {s['checklist']}"); bad += 1
        if s.get("rules"):
            import safety_rules
            try:
                t = safety_rules.template(s["rules"][0])
                if s["rules"][1] and s["rules"][1] not in t["kinds"]:
                    print(f"✗ 꾸러미: {fid} 사업 종류 {s['rules'][1]} 없음"); bad += 1
            except KeyError:
                print(f"✗ 꾸러미: 없는 규정 {s['rules'][0]}"); bad += 1
    print(f"꾸러미 연결 {len(SUGGEST)}종 · 권하기 {len(SUGGEST_CASES)}문항 확인")
    return bad


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--check" in sys.argv:
        sys.exit(1 if check() else 0)
