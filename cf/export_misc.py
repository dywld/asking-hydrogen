#!/usr/bin/env python3
"""review.js·misc.js 가 쓰는 자료를 src/misc_data.json 으로 뽑는다.

  python cf/export_misc.py

- forms: permit_forms.FORMS 의 검토용 정보(title·law·no·docs·fields[key, 칸 질문, 기본값])
- distance: data/distance_tables.json 의 표
- sandbox: data/sandbox_cases.json
- byl: data/forms/index.json (법령정보센터 별지·별표 목록 캐시. 없는 법령은 워커가 직접 찾는다)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import permit_forms  # noqa: E402

forms = {fid: {"title": f["title"], "law": f["law"], "no": f["no"], "docs": f["docs"],
               "fields": [[t[0], t[2], t[5] if len(t) > 5 else ""] for t in f["fields"]]}
         for fid, f in permit_forms.FORMS.items()}


def rd(p, default):
    p = ROOT / "data" / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


byl = {k: {"lsiSeq": v["lsiSeq"], "items": v["items"], "files": v.get("files", {})}
       for k, v in rd("forms/index.json", {}).items()}
out = {"forms": forms, "distance": rd("distance_tables.json", {"tables": []})["tables"],
       "sandbox": rd("sandbox_cases.json", []), "byl": byl}
dst = Path(__file__).parent / "src" / "misc_data.json"
dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(dst, dst.stat().st_size, "bytes")
