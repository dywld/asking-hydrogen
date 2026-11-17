#!/usr/bin/env python3
"""cf/test_tools.mjs 가 부른다: 파이썬 도구(annex_checklist·safety_rules·storage_calc·package)를
여러 입력으로 돌려 기대 결과를 JSON 으로 낸다. 브라우저판(cf-tools.js)이 같은 답을 내는지 대조하는 데 쓴다.
한글 문서는 바이트 대신 make_hwpx 에 넘긴 블록을 기록한다(문서 모양은 블록이 정한다)."""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import annex_checklist  # noqa: E402
import app  # noqa: E402
import hwpx_doc  # noqa: E402
import package  # noqa: E402
import permit_forms  # noqa: E402
import safety_rules  # noqa: E402
import storage_calc  # noqa: E402

BLOCKS = []
hwpx_doc.make_hwpx = lambda blocks, title="문서": (BLOCKS.append({"title": title, "blocks": blocks}), b"HWPX")[1]


def blocks_of(fn, *a):
    BLOCKS.clear()
    fn(*a)
    return BLOCKS[-1]


def jl(x):
    """튜플 → 리스트(JSON 과 같게)"""
    return json.loads(json.dumps(x, ensure_ascii=False))


def main():
    rnd = random.Random(7)
    NUMS = [None, 0, 3, 5, 8.5, 9.99, 12, 17, 18, 20, 21, 25, 30, 45, 100, 299, 300, 9000, 10000, 15000,
            25000, 45000, 60000, 120000, "1,200", "abc", "7m", "", "1.2.3", True]
    BOOLS = [None, True, False, "예", "0", "있음", "모름"]
    out = {"checklist": [], "rules": [], "storage": [], "package": [], "suggest": []}

    for tid in [p.stem for p in sorted(annex_checklist.DIR.glob("*.json"))]:
        t = annex_checklist.template(tid)
        for fac in t["facilities"]:
            for _ in range(60):
                vals = {}
                for inp in t["inputs"]:
                    if rnd.random() < 0.7:
                        vals[inp["key"]] = rnd.choice(NUMS if inp["type"] == "number" else BOOLS)
                marks = {it["id"]: rnd.choice(["적합", "부적합", "해당 없음", "x"]) for it in t["items"] if rnd.random() < 0.3}
                company = rnd.choice(["", "평창수소(주)"])
                s = annex_checklist.build(fac, vals, tid, marks)
                b = blocks_of(annex_checklist.to_hwpx, s, company)
                out["checklist"].append({"args": [fac, vals, tid, marks], "company": company, "sheet": jl(s), "hwpx": jl(b)})

    for tid in [p.stem for p in sorted(safety_rules.DIR.glob("*.json"))]:
        t = safety_rules.template(tid)
        for kind in t["kinds"]:
            for fl in ({}, {"special": True}, {"comprehensive": 1}, {"special": True, "comprehensive": True, "x": True}):
                info = rnd.choice([{}, {"company": "평창수소(주)", "facility": "  평창충전소 ", "ceo": "홍길동", "zz": "무시"}, {"date": "2026-11-01", "address": ""}])
                d = safety_rules.build(tid, kind, fl, info)
                b = blocks_of(safety_rules.to_hwpx, d)
                out["rules"].append({"args": [tid, kind, fl, info], "doc": jl(d), "hwpx": jl(b)})

    P = [None, "", "abc", 0, 1, 20, 35, 45, 70, 87.5, "1,000", -3, "0.15"]
    for _ in range(150):
        items = []
        for i in range(rnd.randint(0, 5)):
            kind = rnd.choice(["comp", "liq", "x"])
            items.append({"kind": kind, "name": rnd.choice([None, "", "튜브트레일러", "저장탱크" * 10]),
                          "p": rnd.choice(P), "v": rnd.choice(P + [0.2, 1.5, 1000]), "d": rnd.choice(P + [0.07, 0.55]),
                          "n": rnd.choice([None, 0, 1, 2, 10, "3"])})
        if rnd.random() < 0.1:
            items.append("not a dict")
        r = storage_calc.calc(items)
        company = rnd.choice(["", "평창수소"])
        b = blocks_of(storage_calc.to_hwpx, r, company)
        out["storage"].append({"items": items, "res": jl(r), "company": company, "hwpx": jl(b)})
    # 손 검산 값
    out["storage"].append({"items": [{"kind": "comp", "p": 45, "v": 0.2, "n": 10}], "res": jl(storage_calc.calc([{"kind": "comp", "p": 45, "v": 0.2, "n": 10}])),
                           "company": "", "hwpx": jl(blocks_of(storage_calc.to_hwpx, storage_calc.calc([{"kind": "comp", "p": 45, "v": 0.2, "n": 10}]), ""))})

    # 제출 꾸러미: 신청서 PDF 는 가짜로(가끔 실패시켜 안내 문구도 본다)
    state = {"fail": False}

    def fake_fill(fid, vals, ink):
        if state["fail"]:
            raise RuntimeError("법령정보센터 응답 없음")
        return b"PDF", "x.pdf"
    permit_forms.fill = fake_fill
    permit_forms.fill_hwpx = lambda fid, vals: (b"HWPX", "x.hwpx")
    for fid, f in permit_forms.FORMS.items():
        for _ in range(6):
            state["fail"] = rnd.random() < 0.3
            fields = {t[0]: rnd.choice(["", "  ", "평창수소(주)", "홍길동", 12]) for t in f["fields"] if rnd.random() < 0.6}
            req = {"permit": {"id": fid, "fields": fields, "fmt": rnd.choice([None, "pdf", "hwpx", "both"])},
                   "company": rnd.choice([None, "", "회사이름"])}
            s = package.SUGGEST.get(fid, {})
            if s.get("checklist") and rnd.random() < 0.7:
                t = annex_checklist.template(s["checklist"])
                fac = s.get("facility") or next(iter(t["facilities"]))
                req["checklist"] = {"id": s["checklist"], "facility": fac,
                                    "inputs": {i["key"]: rnd.choice(NUMS if i["type"] == "number" else BOOLS) for i in t["inputs"]}}
            if s.get("rules") and rnd.random() < 0.7:
                rt = safety_rules.template(s["rules"][0])
                req["rules"] = {"id": s["rules"][0], "kind": s["rules"][1] or next(iter(rt["kinds"])),
                                "flags": {"special": rnd.random() < 0.5}, "info": rnd.choice([{}, {"facility": "평창충전소"}])}
            if rnd.random() < 0.5:
                req["storage"] = {"items": [{"kind": "comp", "p": 45, "v": 0.2, "n": rnd.choice([1, 10])}]}
            BLOCKS.clear()
            data, name, summary = package.build(req, app.permit_vals)
            out["package"].append({"req": req, "name": name, "summary": jl(summary), "cover": jl(BLOCKS[-1])})

    qs = [q for q, _ in annex_checklist.SUGGEST_CASES] + [q for q, _ in package.SUGGEST_CASES] + [
        "충전소 안전관리규정 어떻게 써?", "수소용품 제조사업 안전관리규정 작성", "연료전지 안전관리규정 항목",
        "고압가스 충전소 안전관리규정", "저장능력 계산 어떻게 해? 충전소 안전거리 기준도", "제출 서류 준비 목록 알려줘",
        "수소 저장탱크 설치 기준", "제조식 충전소 방호벽 설치", "오늘 날씨", "튜브트레일러 저장식 충전소 이격거리"]
    pasts = ["", "수소충전소 짓고 싶어요", "연료전지 설치하려고 해요", "수소법 적용 시설입니다"]
    for q in qs:
        for past in pasts:
            got = package.suggest(q, past) + safety_rules.suggest(q, past) + annex_checklist.suggest(q, past)
            out["suggest"].append({"q": q, "past": past, "items": got})

    out["sections"] = []
    for case in out["checklist"][:5] + out["rules"][:3] + out["storage"][:3] + out["package"][:3]:
        b = case.get("hwpx") or case.get("cover")
        out["sections"].append({"blocks": b["blocks"], "xml": hwpx_doc._section(b["blocks"])})
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
