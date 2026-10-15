#!/usr/bin/env python3
"""클라우드플레어용 서류 만들기 자료를 미리 뽑는다(브라우저가 PDF·HWPX·DOCX 를 직접 만든다).

무료 워커는 요청마다 CPU 10ms 라 PDF 채우기를 못 돌린다. 그래서 칸 위치는 서버에서 쓰던
permit_forms.fill / sandbox_doc.fill_pdf 를 그대로 돌려, pymupdf 가 글자·그림을 얹는 호출을
가로채 기록한다(값 대신 표지 글자를 넣어 어느 칸인지 알아낸다). 브라우저(cf-shim.js)는 이
기록대로 같은 자리에 같은 크기·색으로 글을 얹는다.

만드는 것 (cf/public_extra/docs/):
  layout.json          서식별 칸 자리·체크 자리·날짜·서명 자리·편집기 상자, 서식 정보, 글자 폭 표
  forms/<id>.pdf       원본 서식 PDF(법령정보센터, data/forms 캐시)
  editor/<id>_<v>_<n>.png  편집기 바탕 그림(칸 글자를 비운 서식, 110dpi)
  font.ttf             본문 글꼴(Noto Sans KR, OFL) 굵기 400 고정·한글/기호만 남긴 것

쓰는 법: python cf/export_docs.py   (repo 루트 기준 경로를 스스로 잡는다)
"""
import base64
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

import forms  # noqa: E402
import permit_forms as pf  # noqa: E402
import sandbox_doc as sd  # noqa: E402

OUT = HERE / "public_extra" / "docs"
NOTO_VF = "C:/Windows/Fonts/NotoSansKR-VF.ttf"
# 1x1 투명 PNG(서명 자리 기록용)
DOT = "data:image/png;base64," + base64.b64encode(pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 2), 1).tobytes("png")).decode()

# ---------------------------------------------------------------- 호출 가로채기
LOG = []
_orig = {n: getattr(pymupdf.Page, n) for n in ("insert_text", "insert_textbox", "insert_image")}


def _mat(page):
    m = page.transformation_matrix
    return [m.a, m.b, m.c, m.d, m.e, m.f]


def _rec_text(self, point, text, **kw):
    LOG.append({"op": "text", "page": self.number, "x": float(pymupdf.Point(point).x), "y": float(pymupdf.Point(point).y),
                "text": text, "fs": kw.get("fontsize", 11), "color": list(kw.get("color") or (0, 0, 0))})
    return _orig["insert_text"](self, point, text, **kw)


def _rec_box(self, rect, buffer, **kw):
    r = pymupdf.Rect(rect)
    LOG.append({"op": "box", "page": self.number, "rect": [r.x0, r.y0, r.x1, r.y1], "text": buffer,
                "fs": kw.get("fontsize", 11), "lh": kw.get("lineheight"), "color": list(kw.get("color") or (0, 0, 0))})
    return _orig["insert_textbox"](self, rect, buffer, **kw)


def _rec_img(self, rect, **kw):
    r = pymupdf.Rect(rect)
    LOG.append({"op": "img", "page": self.number, "rect": [r.x0, r.y0, r.x1, r.y1],
                "keep": bool(kw.get("keep_proportion", True))})
    return _orig["insert_image"](self, rect, **kw)


pymupdf.Page.insert_text = _rec_text
pymupdf.Page.insert_textbox = _rec_box
pymupdf.Page.insert_image = _rec_img


def run(fn, *a, **kw):
    LOG.clear()
    out = fn(*a, **kw)
    return list(LOG), out


def pages_png(data):
    """app.pdf_pages_png 과 같다(110dpi, 10쪽까지)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    return [pg.get_pixmap(dpi=110).tobytes("png") for pg in list(doc)[:10]]


def page_info(pdf_bytes):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return {"n": len(doc), "mat": [_mat(p) for p in doc], "rot": [p.rotation for p in doc],
            "w": doc[0].rect.width, "h": doc[0].rect.height}


def pos(e):
    return {"page": e["page"], "x": round(e["x"], 3), "y": round(e["y"], 3), "fs": e["fs"]}


def strip_boxes(boxes):
    out = []
    for b in boxes:
        b = dict(b)
        b.pop("value", None)
        out.append(b)
    return out


def save_editor(eid, variant, data):
    names = []
    for i, png in enumerate(pages_png(data)):
        name = f"editor/{eid}_{variant}_{i}.png"
        (OUT / name).write_bytes(png)
        names.append(name)
    return names


# ---------------------------------------------------------------- 허가 신청서
def permit_layout(fid):
    f = pf.FORMS[fid]
    r = forms.resolve(f["law"], "서식", f["no"])
    data, _ = forms.fetch_file(r["_pdf"], "pdf")
    (OUT / "forms" / f"{fid}.pdf").write_bytes(data)
    lay = {"pdf": f"forms/{fid}.pdf", "page": page_info(data)}

    # 칸: 값마다 표지 글자를 넣어 어느 호출이 어느 칸인지 가린다.
    sent = {t[0]: f"Q{i}Z" for i, t in enumerate(f["fields"])}
    vals = dict(sent, date_y="D0", date_m="D1", date_d="D2", applicant="APX", sign=DOT)
    calls, _ = run(pf.fill, fid, vals, "black")
    fields = {}
    checks = []
    dates = {}
    name = None
    sign = None
    for e in calls:
        if e["op"] == "img":
            sign = {"page": e["page"], "rect": [round(v, 3) for v in e["rect"]]}
            continue
        t = e["text"]
        key = next((k for k, s in sent.items() if t == s), None)
        if key:
            below = next((len(x) > 4 and x[4] == "below") for x in f["fields"] if x[0] == key)
            fields[key] = dict(pos(e), max=20 if below else 48)
        elif t in ("D0", "D1", "D2"):
            dates[{"D0": "date_y", "D1": "date_m", "D2": "date_d"}[t]] = dict(pos(e), max=4)
        elif t == "APX":
            name = dict(pos(e), max=20)
        elif t == "√":
            checks.append(pos(e))
        else:
            raise RuntimeError(f"모르는 호출 {fid}: {t}")
    # 체크: 항상 찍는 것(check) 과 선택(choose) 에 따라 찍는 것을 나눈다.
    base, _ = run(pf.fill, fid, {}, "black")
    lay["checks"] = [pos(e) for e in base if e["op"] == "text" and e["text"] == "√"]
    lay["choose"] = None
    variants = [("0", {})]
    if f.get("choose"):
        key, _, opts, labels = f["choose"]
        lay["choose"] = {"key": key, "names": list(labels.keys()), "marks": {}}
        for i, nm in enumerate(labels.keys(), 1):
            c, _ = run(pf.fill, fid, {key: nm}, "black")
            marks = [pos(e) for e in c if e["op"] == "text" and e["text"] == "√"]
            extra = marks[len(lay["checks"]):]
            lay["choose"]["marks"][nm] = extra
            variants.append((str(i), {key: nm}))
    lay["fields"] = fields
    lay["field_order"] = [t[0] for t in f["fields"]]
    lay["dates"] = dates
    lay["name"] = name
    lay["sign"] = sign
    # 검토용(파랑): 빈칸 표시와 아래 안내문
    blue, _ = run(pf.fill, fid, {}, "blue")
    note = [e for e in blue if e["op"] == "text" and e["text"].startswith("※")]
    lay["note"] = dict(pos(note[0]), text=note[0]["text"]) if note else None
    need = [e for e in blue if e["op"] == "text" and e["text"] == sd.NEED]
    assert len(need) == len(fields), (fid, len(need), len(fields))
    # 편집기: 선택값마다 바탕 그림·상자. 선택 칸에 √ 가 찍히면 글자로 잡혀 상자 끝이 달라질 수 있어 따로 둔다.
    lay["editor"] = {}
    for v, keep in variants:
        LOG.clear()
        data2, boxes, pw, ph = pf.edit_layout(fid, keep)
        lay["editor"][v] = {"pages": save_editor(fid, v, data2), "w": pw, "h": ph, "boxes": strip_boxes(boxes)}
    lay["info"] = {k: f.get(k) for k in ("title", "law", "no", "who", "days", "fee", "docs", "after")}
    lay["info"]["field_labels"] = [[t[0], t[1]] for t in f["fields"]]
    return lay


# ---------------------------------------------------------------- 샌드박스 신청서
def sandbox_layout(kind, idx):
    data = sd._form_pdf(kind)
    sid = f"sandbox{idx}"
    (OUT / "forms" / f"{sid}.pdf").write_bytes(data)
    lay = {"pdf": f"forms/{sid}.pdf", "page": page_info(data)}
    sent = {s[0]: f"Q{i}Z" for i, s in enumerate(sd.SLOTS)}
    vals = dict(sent, kind=kind, date_y="D0", date_m="D1", date_d="D2", sign=DOT)
    calls, _ = run(sd.fill_pdf, vals, "black")
    fields, dates, sign = {}, {}, None
    for e in calls:
        if e["op"] == "img":
            sign = {"page": e["page"], "rect": [round(v, 3) for v in e["rect"]]}
            continue
        t = e["text"]
        key = next((k for k, s in sent.items() if t == s), None)
        if key and e["op"] == "box":
            fields[key] = {"page": e["page"], "box": [round(v, 3) for v in e["rect"]], "fs": e["fs"], "lh": e["lh"]}
        elif key:
            fields[key] = dict(pos(e), max=60)
        elif t in ("D0", "D1", "D2"):
            dates[{"D0": "date_y", "D1": "date_m", "D2": "date_d"}[t]] = dict(pos(e), max=4)
        else:
            raise RuntimeError(f"모르는 호출 {kind}: {t}")
    lay.update(fields=fields, field_order=[s[0] for s in sd.SLOTS], dates=dates, sign=sign,
               checks=[], choose=None, name=None)
    # 유형·신청사유 √ 자리(sandbox_doc.fill_pdf 와 같은 계산): 고른 순번마다 찍는다
    pp = pymupdf.open(stream=data, filetype="pdf")[0]
    lay["chk"] = {k: [{"page": 0, "x": round(h.x0 + 4.5, 3), "y": round(h.y1 - 1.5, 3), "fs": 9} for h in rs]
                  for k, rs in sd._checks(pp).items()}
    blue, _ = run(sd.fill_pdf, {"kind": kind}, "blue")
    note = [e for e in blue if e["op"] == "text" and e["text"].startswith("※")]
    lay["note"] = dict(pos(note[0]), text=note[0]["text"]) if note else None
    LOG.clear()
    data2, boxes, pw, ph = sd.edit_layout({"kind": kind})
    lay["editor"] = {"0": {"pages": save_editor(sid, "0", data2), "w": pw, "h": ph, "boxes": strip_boxes(boxes)}}
    return lay


# ---------------------------------------------------------------- 글자 폭(맑은 고딕, 줄바꿈 계산용)
def malgun_metrics():
    doc = pymupdf.open()
    p = doc.new_page()
    x = p.insert_font(fontname="mg", fontfile=sd.FONT)
    info = pymupdf.CheckFontInfo(doc, x)[1]
    w = doc.get_char_widths(x, 0x10000)
    hangul = sorted({w[c][1] for c in range(0xAC00, 0xD7A4)})
    assert len(hangul) == 1
    low = [round(w[c][1], 5) for c in range(0x3400)]
    return {"ascender": info["ascender"], "descender": info["descender"], "ordering": info["ordering"],
            "low": low, "hangul": hangul[0], "other": {str(c): round(w[c][1], 5) for c in range(0x3400, 0x10000)
                                                         if not 0xAC00 <= c < 0xD7A4 and w[c][1] != 1.0}}


# ---------------------------------------------------------------- 글꼴
def make_font():
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    from fontTools import subset
    f = TTFont(NOTO_VF)
    f = instancer.instantiateVariableFont(f, {"wght": 400}, updateFontNames=True)
    keep = set(range(0x20, 0x7F)) | set(range(0xA0, 0x180)) | set(range(0x2000, 0x2BFF)) \
        | set(range(0x3000, 0x3100)) | set(range(0x3130, 0x3190)) | set(range(0x3200, 0x3400)) \
        | set(range(0xAC00, 0xD7A4)) | set(range(0xFF00, 0xFFF0)) | {0x00B7, 0x318D}
    opt = subset.Options()
    opt.layout_features = []          # 모양 바꿈(GSUB) 없이 글자 하나에 그림 하나
    opt.hinting = False
    opt.name_IDs = ["*"]
    opt.notdef_outline = True
    s = subset.Subsetter(opt)
    s.populate(unicodes=keep)
    s.subset(f)
    # pdf-lib(fontkit) 의 subset 은 복합 글리프(부품을 참조하는 글자)를 깨뜨린다(실측: 한글 대부분이 빠짐). 모두 풀어 둔다.
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    gs = f.getGlyphSet()
    glyf = f["glyf"]
    for name in f.getGlyphOrder():
        if glyf[name].isComposite():
            rec = DecomposingRecordingPen(gs)
            gs[name].draw(rec)
            pen = TTGlyphPen(None)
            rec.replay(pen)
            glyf[name] = pen.glyph()
    f.save(OUT / "font.ttf")


def make_docx_template():
    """sandbox_doc.make_docx 와 같은 바탕(python-docx 기본 서식 + 본문 글꼴 설정). 본문은 브라우저가 채운다."""
    from docx import Document
    from docx.shared import Pt
    from docx.oxml.ns import qn
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Malgun Gothic"
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    st.font.size = Pt(10.5)
    doc.save(OUT / "plan_template.docx")


def main():
    (OUT / "forms").mkdir(parents=True, exist_ok=True)
    (OUT / "editor").mkdir(parents=True, exist_ok=True)
    out = {"made": time.strftime("%Y-%m-%d %H:%M"), "permit": {}, "sandbox": {},
           "colors": {"blue": list(sd.BLUE), "orange": list(sd.ORANGE)}, "need": sd.NEED,
           "metrics": malgun_metrics()}
    for fid in pf.FORMS:
        out["permit"][fid] = permit_layout(fid)
        print("permit", fid, "ok")
    for i, kind in enumerate(sd.FORM_NO):
        out["sandbox"][kind] = sandbox_layout(kind, i)
        print("sandbox", i, "ok")
    out["sandbox_form_no"] = sd.FORM_NO
    import hwpx_doc
    out["hwpx"] = {k: getattr(hwpx_doc, k) for k in ("HEADER", "CONTAINER", "VERSION", "SETTINGS", "NS", "XML_DECL",
                                                      "TEXT_W", "ROW_H")}
    out["hwpx"]["MANIFEST"] = hwpx_doc._manifest()
    make_docx_template()
    (OUT / "layout.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if not (OUT / "font.ttf").exists() or "--font" in sys.argv:
        make_font()
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print("done", round(total / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
