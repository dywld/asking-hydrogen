#!/usr/bin/env python3
"""클라우드플레어용 도구 자료: 자체점검표·안전관리규정 초안·저장능력 계산·제출 꾸러미.

파이썬 서버(app.py)에서는 annex_checklist · safety_rules · storage_calc · package 가 만들던 것을
클라우드플레어판에서는 브라우저(cf/public_extra/cf-tools.js)가 같은 규칙으로 만든다.
그 규칙이 쓰는 자료(별표 템플릿·거리표·서식 정보)와 화면 목록(catalog)을 여기서 미리 뽑는다.

만드는 것:
  cf/public_extra/docs/tools.json   브라우저용: 템플릿 원본 · 목록 · 서식 칸 · 저장능력 원문
  cf/src/tools_data.json            워커용: 챗봇 답 아래 버튼(suggest)에 필요한 것만

쓰는 법: python cf/export_tools.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import annex_checklist  # noqa: E402
import distance  # noqa: E402
import package  # noqa: E402
import permit_forms  # noqa: E402
import safety_rules  # noqa: E402
import storage_calc  # noqa: E402


def main():
    annex = {p.stem: annex_checklist.template(p.stem) for p in sorted(annex_checklist.DIR.glob("*.json"))}
    rules = {p.stem: safety_rules.template(p.stem) for p in sorted(safety_rules.DIR.glob("*.json"))}
    forms = {fid: {k: f.get(k) for k in ("title", "law", "no", "who", "days", "fee", "docs", "before", "after")}
             | {"fields": [list(t) for t in f["fields"]]} for fid, f in permit_forms.FORMS.items()}
    tools = {
        "annex": annex, "rules": rules, "distance": distance.tables(),
        "checklist_catalog": annex_checklist.catalog(), "rules_catalog": safety_rules.catalog(),
        "package_catalog": package.catalog(), "forms": forms,
        "rule_info_keys": safety_rules.INFO_KEYS,
        "storage": {"quotes": storage_calc.QUOTES, "ref": storage_calc.REF},
    }
    out = HERE / "public_extra" / "docs" / "tools.json"
    out.write_text(json.dumps(tools, ensure_ascii=False), encoding="utf-8")

    # 워커: 점검표마다 제목·법령·시설 종류(첫 종류 기준 행 수), 규정 제목
    worker = {
        "annex": {tid: {"title": t["title"], "law": t["law"], "annex": t["annex"],
                        "facilities": list(t["facilities"]),
                        "rows": {f: sum(1 for it in t["items"] if not it.get("only") or it["only"] == f)
                                 for f in t["facilities"]}} for tid, t in annex.items()},
        "rules": {tid: {"title": t["title"], "law": t["law"], "annex": t["annex"]} for tid, t in rules.items()},
    }
    (HERE / "src" / "tools_data.json").write_text(json.dumps(worker, ensure_ascii=False), encoding="utf-8")
    print("tools.json", round(out.stat().st_size / 1024), "KB · 점검표", len(annex), "· 규정", len(rules), "· 서식", len(forms))


if __name__ == "__main__":
    main()
