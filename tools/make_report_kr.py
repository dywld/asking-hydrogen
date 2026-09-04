#!/usr/bin/env python3
"""한국 인허가 보고서(.docx)를 만든다.

미국 보고서와 나란히 놓고 볼 것이라, 그 파일을 골격으로 삼아
글꼴·여백·표 선까지 그대로 물려받는다(내용만 갈아 끼운다).
"""
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt, RGBColor

HERE = Path(__file__).parent.parent / "docs"
SRC = HERE / "미국_캘리포니아_인허가_보고서.docx"
OUT = HERE / "수소충전소_허가종류와절차_보고서.docx"

GRAY = RGBColor(0x66, 0x66, 0x66)


def style_of(doc, name):
    """미국 보고서의 스타일 이름 표기가 표준과 조금 달라 이름으로는 못 찾는다.
    그래서 훑어서 같은 이름을 직접 집는다."""
    for st in doc.styles:
        if st.name == name:
            return st
    return None


def borders(table):
    """표 선을 직접 그린다(미국 보고서와 같은 실선 0.5pt)."""
    pr = table._tbl.tblPr
    el = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "808080")
        el.append(e)
    pr.append(el)


def clear(doc):
    """골격만 남기고 본문을 비운다."""
    body = doc.element.body
    for child in list(body):
        if child.tag.endswith(("}p", "}tbl")):
            body.remove(child)


def head(doc, text):
    p = doc.add_paragraph()
    st = style_of(doc, "Heading 1")
    if st is not None:
        p.style = st
        p.add_run(text)
    else:                                  # 스타일이 없으면 직접 굵게
        r = p.add_run(text)
        r.font.bold = True
        r.font.size = Pt(13)
        p.paragraph_format.space_before = Pt(14)
    return p


def para(doc, text="", style=None, size=None, bold=None,
         align=None, color=None, after=None):
    p = doc.add_paragraph()
    if style:
        st = style_of(doc, style)
        if st is not None:
            p.style = st
    if text:
        r = p.add_run(text)
        if size:
            r.font.size = Pt(size)
        if bold is not None:
            r.font.bold = bold
        if color is not None:
            r.font.color.rgb = color
    if align is not None:
        p.alignment = align
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    return p


def table(doc, head, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(head))
    borders(t)
    for i, h in enumerate(head):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.font.bold = True
        r.font.size = Pt(9.5)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(v)
            r.font.size = Pt(9.5)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = w
    doc.add_paragraph()
    return t


def main():
    if not SRC.exists():
        print("미국 보고서가 없어 골격을 못 씁니다.")
        return 1
    doc = Document(str(SRC))
    clear(doc)

    C = WD_ALIGN_PARAGRAPH.CENTER

    # ── 표지 ────────────────────────────────────────────────
    para(doc, "수소충전소는 어떤 허가를 어떤 순서로 받는가",
         size=20, bold=True, align=C, after=6)
    para(doc, "고압가스 안전관리법을 중심으로 정리한 조사",
         size=11, align=C, color=GRAY, after=18)
    para(doc, "2026 WE-Meet 프로젝트 · 수소시설 인허가 AI 가이드 팀",
         size=10, align=C, color=GRAY, after=4)
    para(doc, "작성자:                    소속:                    작성일: 2026. 9. 4.",
         size=10, align=C, color=GRAY, after=20)

    # ── 먼저 결론 ───────────────────────────────────────────
    head(doc, "먼저 결론")
    para(doc, "수소충전소라는 이름의 허가는 따로 없습니다. 법이 충전을 제조로 "
              "보기 때문에, 뼈대는 고압가스 안전관리법의 제조허가입니다. "
              "아래 세 가지만 알면 나머지는 세부 사항입니다.")
    for t in ["수소충전소는 법적으로 고압가스를 제조하는 시설입니다. "
              "그래서 제조허가를 받습니다.",
              "허가는 시장·군수·구청장이 내주고, 검사는 한국가스안전공사가 합니다.",
              "안전거리 같은 수치는 법에 없습니다. 법에서 시행규칙 별표로, "
              "다시 KGS Code로 이어져야 나옵니다."]:
        para(doc, t, style="List Paragraph")
    para(doc, "한 줄로 줄이면, 허가는 지자체에서 받고 기준은 가스안전공사가 "
              "만든 상세기준에서 찾습니다.")

    # ── 1 ──────────────────────────────────────────────────
    head(doc, "1. 왜 제조허가인가")
    para(doc, "고압가스 안전관리법 제4조 제1항은 이렇게 시작합니다. "
              "“고압가스를 제조(용기 또는 차량에 고정된 탱크에 충전하는 것을 "
              "포함한다)하려는 자는 그 제조소마다 시장·군수 또는 구청장의 허가를 "
              "받아야 한다.”")
    para(doc, "괄호가 열쇠입니다. 충전이 제조에 포함됩니다. 그래서 수소를 직접 "
              "만들어 넣든, 받아 와서 저장했다가 넣든 모두 제조허가 대상입니다.")
    para(doc, "시행령 제3조는 제조허가의 종류를 특정제조·일반제조·충전·냉동제조 "
              "등으로 나눕니다. 특정제조는 저장능력이나 처리능력이 일정 규모 이상인 "
              "것이고, 일반제조는 특정제조에 해당하지 않는 제조입니다. 실제 "
              "수소충전소가 어느 종류에 해당하는지는 사업 규모와 형태에 따라 "
              "달라지므로, 사업별로 확인이 필요합니다.")

    # ── 2 ──────────────────────────────────────────────────
    head(doc, "2. 허가의 종류")
    para(doc, "허가·신고·등록이 각각 다른 자리에 있습니다.")
    table(doc,
          ["구분", "대상", "누구에게", "근거"],
          [["제조허가", "고압가스를 제조(충전)하려는 자, 제조소마다",
            "시장·군수·구청장", "법 제4조 ①"],
           ["제조신고", "대통령령이 정한 종류·규모 이하의 제조",
            "시장·군수·구청장", "법 제4조 ②"],
           ["저장소 설치허가", "저장소를 설치하려는 자, 저장소마다",
            "시장·군수·구청장", "법 제4조 ⑤"],
           ["판매허가", "고압가스를 판매하려는 자, 판매소마다",
            "시장·군수·구청장", "법 제4조 ⑤"],
           ["변경허가", "허가사항 중 중요 사항 변경(사업소 위치, 가스 종류, "
            "저장설비 교체·능력 변경 등)", "허가관청", "시행규칙 제4조"],
           ["변경신고", "그 밖의 경미한 사항 변경", "허가관청", "시행규칙 제4조"],
           ["제조등록", "용기·냉동기·특정설비를 제조하려는 자",
            "시장·군수·구청장", "법 제5조 ①"]])
    para(doc, "신고에는 처리기간이 정해져 있습니다. 관청은 신고를 받은 날부터 "
              "2일 이내에 수리 여부를 알려야 하고, 그 기간에 통지가 없으면 신고를 "
              "수리한 것으로 봅니다(법 제4조 제3항·제4항). 반면 허가의 법정 "
              "처리기간은 법령에 규정되어 있지 않습니다.")

    # ── 3 ──────────────────────────────────────────────────
    head(doc, "3. 절차는 다섯 단계입니다")
    para(doc, "놓치기 쉬운 곳이 두 군데입니다. 기술검토는 허가를 신청하기 전에 "
              "받아야 하고, 완성검사에 합격했다고 끝이 아니라 사업 개시 신고를 "
              "따로 해야 합니다.")
    table(doc,
          ["단계", "무엇을", "어디에", "근거"],
          [["1. 기술검토",
            "시설 설치계획서와 도면을 내고 기술검토서를 받습니다",
            "한국가스안전공사", "시행규칙 제5조 ② 3호 · 제7조"],
           ["2. 제조허가 신청",
            "허가신청서(별지 제1호서식)에 사업계획서와 기술검토서를 첨부합니다",
            "시·군·구청", "법 제4조 · 시행규칙 제5조"],
           ["3. 중간검사·완성검사",
            "덮기 전 공정마다 중간검사를 받고, 공사를 마치면 완성검사를 받습니다",
            "한국가스안전공사(위탁)", "법 제16조 · 시행규칙 제28조"],
           ["4. 안전관리 준비",
            "안전관리자를 선임해 신고하고, 안전관리규정을 제출합니다",
            "허가관청", "법 제11조 · 제15조"],
           ["5. 사업 개시 신고",
            "시설 사용을 시작하기 전에 미리 신고합니다",
            "허가관청", "법 제7조 · 시행규칙 제11조"]])
    para(doc, "중간검사는 여섯 공정에서 받습니다. 기밀시험이나 내압시험을 할 수 "
              "있는 상태, 저장탱크를 지하에 매설하기 직전, 배관을 매몰하기 직전, "
              "지정된 부분의 비파괴시험, 방호벽과 저장탱크의 기초 설치, 내진설계 "
              "대상 설비의 기초 설치입니다. 완성검사에 합격하면 별지 제22호서식의 "
              "완성검사증명서를 발급받습니다(시행규칙 제28조).")
    para(doc, "안전관리자는 선임·해임하거나 퇴직한 경우 지체 없이 신고해야 하고, "
              "해임 또는 퇴직한 날부터 30일 이내에 다른 안전관리자를 선임해야 "
              "합니다(법 제15조). 안전관리규정에는 한국가스안전공사의 의견서를 "
              "첨부합니다(법 제11조).")
    para(doc, "검사는 법에 허가관청의 검사로 규정되어 있지만, 시행령 제25조가 "
              "그 업무를 한국가스안전공사에 위탁합니다. 그래서 실무에서는 공사가 "
              "검사를 수행합니다.")

    # ── 4 ──────────────────────────────────────────────────
    head(doc, "4. 고압가스법만으로 끝나지 않습니다")
    para(doc, "부지와 건물, 환경, 소방, 전기가 함께 걸립니다. 실제 순서는 지자체 "
              "조례와 사업 성격에 따라 달라집니다.")
    table(doc,
          ["법", "무엇이 걸리나", "누구에게", "근거"],
          [["국토계획법", "용도지역에서 지을 수 있는 건축물인지, 개발행위허가가 "
            "필요한지", "시·군·구청", "제56조 · 제76조"],
           ["건축법", "건축허가를 받고, 공사를 마치면 사용승인을 받습니다",
            "시·군·구청", "제11조 · 제22조"],
           ["소방시설법", "건축허가 등을 할 때 관할 소방서장의 동의를 받습니다",
            "관할 소방서", "제6조"],
           ["대기환경보전법",
            "개질기처럼 배출시설을 두는 경우 설치 허가 또는 신고를 합니다",
            "시·도 등", "제23조"],
           ["전기사업법", "전기설비 공사계획 신고와 사용전검사를 받습니다",
            "산업통상부 · 전기안전공사", "제61조 · 제63조"]])
    para(doc, "위 표는 인허가 과정에서 함께 걸리는 법을 모은 것이며, 사업의 "
              "형태와 부지 조건에 따라 해당 여부가 달라집니다.")

    # ── 5 ──────────────────────────────────────────────────
    head(doc, "5. 수치는 세 단계를 거쳐야 나옵니다")
    para(doc, "이번 조사에서 가장 중요한 발견입니다. 법 본문에는 수치가 없습니다.")
    table(doc,
          ["단계", "무엇이 규정되어 있나", "근거"],
          [["법", "시설기준과 기술기준은 산업통상부령으로 정하도록 위임합니다",
            "법 제4조 ⑥"],
           ["시행규칙 별표",
            "수소연료 충전의 시설기준과 기술기준은 별표 5",
            "시행규칙 제8조 ① 2호"],
           ["KGS Code(상세기준)",
            "그 기준의 범위에서 상세한 규격과 특정한 수치를 정합니다",
            "법 제22조의2 ①"]])
    para(doc, "KGS Code는 가스기술기준위원회가 정하고 산업통상부장관의 승인을 "
              "받는 상세기준으로, 사무국은 한국가스안전공사에 둡니다. 상세기준에 "
              "적합하면 법령이 정한 기준에 적합한 것으로 봅니다(법 제22조의2 "
              "제4항). 그래서 실무에서 실제로 펴 보는 것은 이 상세기준입니다.")
    para(doc, "수소충전소는 제조식이 KGS FP216, 저장식이 KGS FP217입니다. "
              "제1종보호시설과의 안전거리는 처리능력과 저장능력에 따라 17미터에서 "
              "30미터이며, 저장설비를 지하에 설치하는 경우 그 절반까지 완화할 수 "
              "있습니다(KGS FP216 2.1.1.1).")

    # ── 마무리 ─────────────────────────────────────────────
    head(doc, "더 확인할 것")
    for t in ["제조허가의 실제 처리기간입니다. 법령에 규정이 없어 지자체의 민원 "
              "처리 기준을 확인해야 합니다.",
              "해당 수소충전소가 시행령 제3조의 어느 종류에 해당하는지입니다. "
              "규모와 형태에 따라 갈리므로 사업별 확인이 필요합니다.",
              "수소법과 고압가스법의 적용 경계입니다. 실무에서 어떻게 정리되는지 "
              "확인이 필요합니다."]:
        para(doc, t, style="List Paragraph")
    para(doc, "이 조사에 나오는 조문 번호와 서식 번호는 국가법령정보센터의 법령 "
              "원문과, 수치는 가스기술기준정보시스템의 KGS Code 원문과 대조해 "
              "확인했습니다.", size=9.5, color=GRAY)

    doc.save(str(OUT))
    print(f"만들었습니다: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
