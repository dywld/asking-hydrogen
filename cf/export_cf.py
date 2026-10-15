#!/usr/bin/env python3
"""클라우드플레어 배포용 자료 만들기(hydrogen-guide).

노트북의 검색 색인(search.py)을 D1 데이터베이스용 SQL 로 내보낸다.
- docs: 조각 원문과 화면에 쓸 값(법령·조문·링크).
- docs_fts: FTS5 색인. 본문을 search.tokenize 와 같은 방식(글자 2개씩)으로 잘라 넣는다.
  검색어도 같은 방식으로 잘라 OR 로 찾고 bm25 로 줄 세운다.
그리고 워커가 쓸 낱말 확장표·잡음어·답변 지침·캐시 답을 src/data.json 으로 낸다.

    python worker/export_cf.py      # → worker/build/*.sql, worker/src/data.json
"""
import os
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import search  # noqa: E402
import app  # noqa: E402
import permit_forms  # noqa: E402

OUT = HERE / "build"
OUT.mkdir(exist_ok=True)


def q(s):
    return "'" + str(s if s is not None else "").replace("'", "''") + "'"


def search_meta(idx):
    """search.py 의 가산·감산 규칙을 워커가 SQL 로 다시 짜도록 넘긴다(chat_extras.js)."""
    docs = idx.docs
    # 기준일 감산용: 시행 예정판이 있는 현행 조문 (법령, 조문, 예정판 시행일)
    cur_fut = []
    for k, fut in idx.future_of.items():
        effs = [docs[j].get("effective_date") or "9999" for j in fut]
        for c in idx.current_of.get(k, ()):
            cur_fut.append([docs[c]["law"], docs[c]["article"], min(effs)])
    # 조문 → 별표 조각(D1 id = 순번 + 1)
    linked = {f"{lk}|{art}": [i + 1 for i in ids] for (lk, art), ids in idx.linked.items()}
    # 흔한 2글자(문서 800개 넘게 나옴): MATCH 에서 빼서 D1 읽기 행 수를 줄인다(무료 하루 500만 행)
    df = {}
    for d in docs:
        for t in set(search.tokenize(f"{d['law']} {d['title']} {d['content']}")):
            df[t] = df.get(t, 0) + 1
    common = {t: n for t, n in df.items() if n > int(os.environ.get("CF_COMMON", 4000))}
    return {"search": {
        "common": common,
        "jp_words": search.JP_WORDS,
        "procedure": search.PROCEDURE.pattern,
        "xref": search.XREF.pattern,
        "bundles": search.BUNDLES,
        "change": search.CHANGE.pattern,
        "facility": search.FACILITY,
        "core": list(search.CORE_LAWS),
        "make_code": list(search.MAKE_CODE),
        "install": search.INSTALL.pattern,
        "gas": {k: list(v) for k, v in search.GAS.items()},
        "noise_title": search.NOISE_TITLE.pattern,
        "cur_fut": cur_fut,
        "linked": linked,
    }}


def chat_meta():
    """app.py do_chat 의 곁가지(체크리스트·재작성·규제 사례·확정 자료·검증)에 쓰는 값."""
    import re
    facts_raw = json.loads((ROOT / "data" / "fact_tables.json").read_text(encoding="utf-8"))["topics"]
    reg = json.loads((ROOT / "data" / "reg_cases.json").read_text(encoding="utf-8"))
    demo_f = ROOT / "data" / "demo_answers.json"
    demo = json.loads(demo_f.read_text(encoding="utf-8")) if demo_f.exists() else {}
    demo = {k: v for k, v in demo.items() if v.get("approved")}
    return {"chat": {
        "checklist_re": app.CHECKLIST_RE.pattern,
        "checklist_system": app.CHECKLIST_SYSTEM,
        "rewrite_chain": app.REWRITE_CHAIN,
        "rewrite_prompt": app.REWRITE_PROMPT,
        "long_q": app.LONG_Q,
        "smalltalk": app.SMALLTALK.pattern,
        "meta": app.META.pattern,
        "intro": app.INTRO,
        "sandbox_ask": app.SANDBOX_ASK.pattern,
        "reg_stop": sorted(app.REG_STOP),
        "reg_cases": reg,
        "facts": [{k: t[k] for k in ("id", "match", "law", "ref", "title", "facts")} for t in facts_raw],
        "demo": demo,
        "correct_prompt": app.CORRECT_PROMPT,
        "law_short": app.LAW_SHORT,
        "judge_prompt": app.JUDGE_PROMPT,
        "model_sets": app.MODEL_SETS,
    }}


def main():
    idx = search.get_index()
    rows = []
    meta_only = "--meta" in sys.argv          # 자료(SQL)는 두고 data.json 만 다시 만든다
    for i, d in enumerate([] if meta_only else idx.docs):
        h = dict(d, score=0)
        g = app.group_sources([h])[0]
        rows.append((i + 1, d["country"], d["law"], d["article"], d["title"], d["content"],
                     1 if d.get("future") else 0, d.get("effective_date") or "", d.get("kind") or "",
                     g["ref"], g.get("link", ""),
                     " ".join(search.tokenize(f"{d['law']} {d['title']} {d['content']}"))))
    # D1 은 한 번에 보내는 SQL 크기에 한도가 있어 파일을 나눈다.
    schema = """DROP TABLE IF EXISTS docs; DROP TABLE IF EXISTS docs_fts;
CREATE TABLE docs (id INTEGER PRIMARY KEY, country TEXT, law TEXT, article TEXT, title TEXT, content TEXT,
  future INTEGER, effective_date TEXT, kind TEXT, ref TEXT, link TEXT);
CREATE VIRTUAL TABLE docs_fts USING fts5(bg, content='', tokenize='unicode61');
"""
    if not meta_only:
        (OUT / "00_schema.sql").write_text(schema, encoding="utf-8")
    part, size, n = [], 0, 1
    for r in rows:
        line = (f"INSERT INTO docs VALUES ({r[0]},{q(r[1])},{q(r[2])},{q(r[3])},{q(r[4])},{q(r[5])},"
                f"{r[6]},{q(r[7])},{q(r[8])},{q(r[9])},{q(r[10])});\n"
                f"INSERT INTO docs_fts(rowid, bg) VALUES ({r[0]},{q(r[11])});\n")
        part.append(line)
        size += len(line.encode())
        if size > 25_000_000:
            (OUT / f"{n:02d}_docs.sql").write_text("".join(part), encoding="utf-8")
            part, size, n = [], 0, n + 1
    if part and not meta_only:
        (OUT / f"{n:02d}_docs.sql").write_text("".join(part), encoding="utf-8")

    cache = {}
    cf = ROOT / "data" / "answer_cache.json"
    if cf.exists():
        try:
            cache = json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    data = {
        "expand": search.EXPAND,
        "filler": search.FILLER.pattern,
        "system": app.SYSTEM,
        "articles": len(idx.docs),
        "korea": sum(1 for d in idx.docs if d["country"] == "한국"),
        "permit": permit_forms.catalog(),
        "guess": [["h2_product", ["수소용품 검사", "제품 검사", "출고"]],
                  ["h2_use_inspect", ["연료전지", "사용시설"]],
                  ["h2_maker", ["수소용품", "수전해설비 제조", "연료전지 제조", "제조사업"]],
                  ["gas_inspect", ["완성검사", "정기검사"]],
                  ["gas_use", ["사용신고", "사용 신고"]],
                  ["gas_report", ["제조 신고", "제조신고"]],
                  ["gas_permit", ["충전소", "충전", "저장소", "제조허가", "제조 허가", "수전해"]]],
        "permit_re": app.PERMIT_DRAFT.pattern,
        "sandbox_re": app.SANDBOX_DRAFT.pattern,
        "models": app.MODEL_SETS["daily"],
        # 답하기 전에 조건부터 묻는 질문(샌드박스 신청서·안전거리·수수료…). 정규식은 글자로 넘긴다.
        "ask": [[need.pattern, [[k, t, o, h.pattern] for k, t, o, h in steps]] for need, steps in app.ASK],
        "dist_other": app.DIST_OTHER.pattern,
        "other": app.OTHER,
        "clarify": [[n.pattern, h.pattern, t, o] for n, h, t, o in app.CLARIFY],
        "kind_words": app.KIND_WORDS,
        "sandbox_docs": app.SANDBOX_DOCS,
    }
    data.update(search_meta(idx))
    data.update(chat_meta())
    # 답변 캐시(data/answer_cache.json)는 D1 answer_cache 표로 옮긴다. 표는 지우지 않고 덮어쓴다.
    cache_sql = ["CREATE TABLE IF NOT EXISTS answer_cache (key TEXT PRIMARY KEY, rec TEXT NOT NULL, ts INTEGER);\n"]
    for k, rec in cache.items():
        cache_sql.append(f"INSERT OR REPLACE INTO answer_cache VALUES ({q(k)},{q(json.dumps(rec, ensure_ascii=False))},"
                         f"{int(rec.get('ts', 0))});\n")
    (OUT / "answer_cache.sql").write_text("".join(cache_sql), encoding="utf-8")
    (HERE / "src" / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(len(rows), "rows,", n, "files, cache", len(cache))


if __name__ == "__main__":
    main()
