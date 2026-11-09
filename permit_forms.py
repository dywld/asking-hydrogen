#!/usr/bin/env python3
"""수소 시설 허가·신고·검사 신청서 채우기.

법령정보센터 원본 서식을 받아 칸 이름 옆에 글을 얹는다(sandbox_doc 과 같은 방식).
서식마다 다른 것은 아래 FORMS 표에만 적는다. 처리기간·첨부서류·수수료·제출처는
각 서식 PDF 본문에 적힌 그대로 옮겼다(2026-10 기준, 개정되면 서식이 바뀌니 다시 대조).
"""
import time

import forms
from sandbox_doc import FONT, BLUE, ORANGE, NEED

GAS = "고압가스 안전관리법 시행규칙"
H2 = "수소경제 육성 및 수소 안전관리에 관한 법률 시행규칙"

# 칸: (key, 서식의 칸 이름, 질문, 예시). 칸 이름은 PDF 에서 찾을 글자 그대로.
CO = ("company", "상호", "회사명 ('상호' 칸)", "예: ○○수소㈜")
CEO = ("ceo", "대표자 성명", "대표자 이름 ('대표자 성명' 칸)", "예: 홍길동")
CEO2 = ("ceo", "대표자", "대표자 이름 ('대표자' 칸)", "예: 홍길동")
OFFICE = ("office", "사무소소재지", "본사 주소 ('사무소 소재지' 칸)", "예: 강원 춘천시 ○○로 12")
OFFICE2 = ("office", "사무소 소재지", "본사 주소 ('사무소 소재지' 칸)", "예: 강원 춘천시 ○○로 12")
SITE = ("site", "사업소 소재지", "시설이 들어설 주소 ('사업소 소재지' 칸)", "예: 강원 삼척시 ○○산업단지 3블록")
TEL = ("tel", "전화번호", "전화번호 ('전화번호' 칸)", "예: 033-123-4567")
TELP = ("tel", "(전화번호:", "전화번호 ('전화번호' 칸)", "예: 033-123-4567")
MAIL = ("email", "전자우편주소", "전자우편 ('전자우편주소' 칸)", "예: info@example.co.kr")
MAIL_G = ("email", "(e-mail)", "전자우편 ('전자우편주소' 칸)", "예: info@example.co.kr")   # 고압가스 서식은 칸 이름 뒤에 (e-mail)
BIZ = ("bizno", "사업자등록번호", "사업자등록번호 ('사업자등록번호' 칸)", "예: 123-45-67890")
BIZ_B = ("bizno", "사업자등록번호(", "사업자등록번호 ('사업자등록번호' 칸)", "예: 123-45-67890", "below")
WISH = ("wish", "검사희망 연월일", "검사 받고 싶은 날 ('검사희망 연월일' 칸)", "예: 2027년 3월 중")

FORMS = {
    "gas_permit": {
        "title": "수소 충전소·제조·저장소 허가",
        "desc": "고압가스 제조(충전 포함)·저장소 설치·판매 허가",
        "law": GAS, "no": 1, "who": "시장·군수·구청장", "days": "5일",
        "fee": "제조허가 2만5천원, 저장소설치·판매허가 1만5천원",
        "docs": ["사업계획서 1부", "정관 1부 (법인만)", "한국가스안전공사 기술검토서 1부"],
        "before": "한국가스안전공사 기술검토를 먼저 받아야 신청할 수 있습니다.",
        "after": "시설 완공 후 완성검사 (별지 제21호) 를 받아야 운영할 수 있습니다.",
        "choose": ("type", "무슨 허가인가요?", ["제조 (충전소 포함)", "저장소설치", "판매"],
                   {"제조": "]제조", "저장소설치": "]저장소설치", "판매": "]판매"}),
        "check": ["]허가"],
        "fields": [CO, CEO, OFFICE, TELP, BIZ_B, MAIL_G, SITE,
                   ("gas", "고압가스 종류", "가스 종류 ('고압가스 종류' 칸)", "예: 압축수소", None, "압축수소")],
    },
    "gas_report": {
        "title": "소규모 고압가스 제조 신고",
        "desc": "허가 대상보다 작은 제조시설 (신고로 끝남)",
        "law": GAS, "no": 3, "who": "시장·군수·구청장", "days": "2일", "fee": "없음",
        "docs": ["사업계획의 개요를 적은 서류 1부"],
        "after": "신고 대상인지 (처리능력 기준) 먼저 확인하세요.",
        "check": ["]신고서"],
        "fields": [CO, CEO, OFFICE2, TELP, SITE,
                   ("gas", "고압가스의 종류", "가스 종류 ('고압가스의 종류' 칸)", "예: 압축수소", None, "압축수소")],
    },
    "gas_use": {
        "title": "특정고압가스(수소) 사용신고",
        "desc": "수소를 사다가 쓰는 시설 (공장·연구소 등)",
        "law": GAS, "no": 33, "who": "시장·군수·구청장", "days": "즉시", "fee": "없음",
        "docs": [],
        "after": "사용 시작 전에 신고하고, 시설은 완성검사를 받습니다.",
        "fields": [CO, CEO, TELP,
                   ("site", "사용처 주소", "수소를 쓰는 곳 주소 ('사용처 주소' 칸)", "예: 강원 원주시 ○○로 45"),
                   ("gas", "가스의 종류", "가스 종류 ('가스의 종류' 칸)", "예: 수소", None, "수소"),
                   ("cap", "저장능력", "저장할 수 있는 양 ('저장능력' 칸)", "예: 300 ㎥"),
                   ("purpose", "사용 목적ㆍ방법", "어디에 어떻게 쓰나요 ('사용 목적·방법' 칸)", "예: 연구용 연료전지 시험, 실린더 공급"),
                   ("month", "월간 사용량", "한 달 사용량 ('월간 사용량' 칸)", "예: 200 ㎥")],
    },
    "gas_inspect": {
        "title": "충전소·제조시설 완성검사",
        "desc": "허가받은 시설을 다 지은 뒤 받는 검사",
        "law": GAS, "no": 21, "who": "한국가스안전공사", "days": "7일",
        "fee": "산업통상부장관이 정하는 금액", "docs": [],
        "after": "완성검사에 합격해야 시설을 쓸 수 있습니다.",
        "choose": ("type", "어떤 시설인가요?", ["수소연료 충전시설", "고압가스 제조시설", "고압가스 저장시설"],
                   {"수소연료 충전시설": "수소연료 충전시설", "고압가스 제조시설": "고압가스 제조시설",
                    "고압가스 저장시설": "고압가스 저장시설"}),
        "check": ["]완성검사신청서"],
        "fields": [CO, CEO, OFFICE2, TELP, MAIL_G, BIZ,
                   ("biz", "사업의 종류", "사업의 종류 ('사업의 종류' 칸)", "예: 고압가스 특정제조(수소충전소)", "below"),
                   ("permit_no", "등록)번호", "허가번호 ('허가번호' 칸)", "예: 제2027-03호", "below"),
                   SITE, WISH],
    },
    "h2_maker": {
        "title": "수소용품 제조사업 허가",
        "desc": "수전해설비·연료전지·수소추출설비를 만들어 파는 사업",
        "law": H2, "no": 10, "who": "시장·군수·구청장", "days": "5일", "fee": "2만5천원",
        "docs": ["사업계획서 1부", "한국가스안전공사 기술검토서 1부"],
        "before": "한국가스안전공사 기술검토를 먼저 받아야 신청할 수 있습니다.",
        "after": "만든 제품은 출고 전 수소용품 검사 (별지 제25호) 를 받습니다.",
        "check": ["] 허가"],
        "fields": [CO, CEO2, OFFICE2, TEL, SITE,
                   ("spec", "종류 및 규격", "만드는 제품과 규격 ('수소용품의 종류 및 규격' 칸)", "예: 수전해설비, 1 MW (200 N㎥/h)")],
    },
    "h2_product": {
        "title": "수소용품 검사",
        "desc": "만든 수전해설비·연료전지를 출고 전에 받는 검사",
        "law": H2, "no": 25, "who": "한국가스안전공사", "days": "7일",
        "fee": "기후에너지환경부장관이 정한 수수료", "docs": [],
        "after": "합격하면 제품에 각인·표시를 합니다.",
        "fields": [CO, CEO2, OFFICE2, TEL, MAIL, BIZ, SITE,
                   ("permit_no", "품목허가번호", "품목허가번호 ('품목허가번호' 칸)", "예: 제2027-01호", "below"),
                   ("spec", "규격", "규격 ('규격' 칸)", "예: 1 MW 수전해설비", "below"),
                   ("qty", "수량", "수량 ('수량' 칸)", "예: 2대", "below"),
                   ("wish", "검사 희망 연월일", "검사 받고 싶은 날 ('검사 희망 연월일' 칸)", "예: 2027년 3월 중")],
    },
    "h2_use_inspect": {
        "title": "수소연료사용시설 완성검사",
        "desc": "연료전지 등 수소를 연료로 쓰는 시설을 다 지은 뒤 받는 검사",
        "law": H2, "no": 23, "who": "한국가스안전공사", "days": "7일",
        "fee": "기후에너지환경부장관이 정한 수수료",
        "docs": ["완공도면과 시공 현황 1부", "한국가스안전공사 기술검토서 1부"],
        "after": "검사에 합격해야 시설을 쓸 수 있습니다.",
        "check": ["] 수소연료사용시설", "] 완성검사"],
        "fields": [CO, CEO2, OFFICE2, TEL, MAIL, BIZ],
    },
    # ── 2026-11 추가: 허가 전·공사 중·운영 준비 서식. 처리기간·수수료·첨부서류는 각 서식 PDF 본문 그대로 ──
    "gas_review": {
        "title": "고압가스 기술검토 신청",
        "desc": "허가 신청 전에 한국가스안전공사에서 받는 기술검토 (허가 신청서에 기술검토서 첨부)",
        "law": GAS, "no": 8, "who": "한국가스안전공사",
        "days": "고압가스특정제조 20일, 일반제조·충전 15일, 저장소설치 10일, 판매 7일",
        "fee": "「고압가스 안전관리법 시행령」 제22조에 따른 금액",
        "docs": ["시설의 설치계획서 1부(변경하려는 경우에는 그 변경부분만 해당됩니다)",
                 "시설기준과 기술기준에 대한 도면 및 그 설명서 각 1부(변경하려는 경우에는 그 변경부분만 해당됩니다)"],
        "after": "받은 기술검토서를 허가 신청서(별지 제1호)에 붙여 시장·군수·구청장에게 냅니다.",
        "choose": ("type", "사업의 종류는?", ["제조", "저장", "판매"],
                   {"제조": "] 제조", "저장": "] 저장", "판매": "] 판매"}),
        "fields": [CO, ("ceo", "성명(대표자)", "대표자 이름 ('성명(대표자)' 칸)", "예: 홍길동"),
                   OFFICE2, TEL, MAIL_G, BIZ, SITE],
    },
    "gas_mid": {
        "title": "중간검사 신청 (충전소·제조·저장시설)",
        "desc": "공사 도중 기초·매설 직전 같은 공정에서 받는 검사",
        "law": GAS, "no": 20, "who": "한국가스안전공사", "days": "7일",
        "fee": "「고압가스 안전관리법」 제34조제2항에 따라 산업통상부장관이 정하는 금액", "docs": [],
        "after": "공사를 마치면 완성검사(별지 제21호)를 신청합니다.",
        "choose": ("type", "검사대상 시설은?", ["수소연료 충전시설", "고압가스 제조시설", "고압가스 저장시설"],
                   {"수소연료 충전시설": "] 수소연료 충전시설", "고압가스 제조시설": "] 고압가스 제조시설",
                    "고압가스 저장시설": "] 고압가스 저장시설"}),
        "fields": [CO, CEO, OFFICE2, TELP, MAIL_G, BIZ, SITE,
                   ("permit_no", "허가(신고ㆍ등록)번호", "허가번호 ('허가(신고·등록)번호' 칸)", "예: 제2027-03호"),
                   ("permit_date", "허가(신고ㆍ등록) 연월일", "허가 받은 날 ('허가 연월일' 칸)", "예: 2027. 2. 1."),
                   ("scope", "중간검사 범위", "중간검사 받을 공정 ('중간검사 범위' 칸)", "예: 방호벽 기초설치 공정"),
                   ("place", "검사를 받으려는 장소", "검사 장소 ('검사를 받으려는 장소' 칸)", "예: 사업소 내 압축설비 구역")],
    },
    "gas_use_inspect": {
        "title": "특정고압가스(수소) 사용시설 완성·정기검사",
        "desc": "사용신고한 수소 사용시설을 다 지은 뒤·운영 중 받는 검사",
        "law": GAS, "no": 35, "who": "한국가스안전공사", "days": "서식에 처리기간 기재 없음",
        "fee": "「고압가스 안전관리법」 제34조제2항에 따라 산업통상부장관이 정하는 금액",
        "docs": ["시설의 위치가 표시된 도면 1부(완성검사의 경우만 해당합니다.)"],
        "before": "사용 전에 특정고압가스 사용신고(별지 제33호)를 먼저 합니다.",
        "choose": ("type", "어떤 검사인가요?", ["완성검사", "정기검사"],
                   {"완성검사": "] 완성검사", "정기검사": "] 정기검사"}),
        "fields": [CO, OFFICE2, TEL, MAIL_G, BIZ,
                   ("gas", "가스명", "가스 이름 ('가스명' 칸)", "예: 수소", None, "수소")],
    },
    "gas_rules": {
        "title": "안전관리규정 심사 신청 (고압가스)",
        "desc": "작성한 안전관리규정을 한국가스안전공사에 심사받기",
        "law": GAS, "no": 14, "who": "한국가스안전공사",
        "days": "10일(「고압가스 안전관리법」 제11조제2항에 해당하는 자는 20일)",
        "fee": "「고압가스 안전관리법」 제34조제2항에 따라 산업통상부장관이 정하는 금액",
        "docs": ["안전관리규정안 3부"],
        "choose": ("type", "사업의 종류는?", ["제조", "저장", "판매"],
                   {"제조": "］제조", "저장": "］저장", "판매": "］판매"}),
        "fields": [CO, ("ceo", "성명(대표자)", "대표자 이름 ('성명(대표자)' 칸)", "예: 홍길동"),
                   OFFICE2, TELP, MAIL_G, BIZ, SITE],
    },
    "gas_manager": {
        "title": "안전관리자 선임 신고 (고압가스)",
        "desc": "안전관리자를 선임·해임했거나 퇴직했을 때",
        "law": GAS, "no": 19, "who": "특별자치시장·특별자치도지사, 시장·군수 또는 구청장", "days": "즉시", "fee": "없음",
        "docs": ["실무경력을 증명할 수 있는 서류(안전관리자를 선임한 경우로서 「고압가스 안전관리법 시행령」 별표 3에 따른 "
                 "안전관리자의 자격을 갖추었음을 증명하기 위해 필요한 경우에만 첨부합니다) 1부"],
        "choose": ("type", "무슨 신고인가요?", ["선임", "해임", "퇴직"],
                   {"선임": "] 선임", "해임": "] 해임", "퇴직": "] 퇴직"}),
        "fields": [CO, ("ceo", "성명(대표자)", "대표자 이름 ('성명(대표자)' 칸)", "예: 홍길동"),
                   OFFICE2, TEL, SITE, ("email", "전자우편주소", "전자우편 ('전자우편주소' 칸)", "예: info@example.co.kr",
                                        None, None, {"nth": 0}),
                   ("mgr_name", "성명", "안전관리자 이름 (표의 '성명' 칸)", "예: 김안전", "below", None, {"nth": 1, "row": "선임"}),
                   ("mgr_qual", "자격", "안전관리자 자격 (표의 '자격' 칸)", "예: 가스기능사", "below", None, {"row": "선임"}),
                   ("mgr_no", "자격증번호", "자격증 번호 (표의 '자격증번호' 칸)", "예: 12345678", "below", None, {"row": "선임"})],
        "sign_label": "(서명또는인)",          # 이 서식만 띄어쓰기 없이 적혀 있다(표의 '취업동의 (서명 또는 인)'과 구분)
    },
    "gas_start": {
        "title": "사업 개시·중단·폐지·재개 신고 (고압가스)",
        "desc": "허가받은 사업(저장소 사용)을 시작·중단·폐지·재개할 때",
        "law": GAS, "no": 9, "who": "시장·군수 또는 구청장", "days": "즉시", "fee": "없음",
        "docs": ["사업 또는 저장소의 폐지 시에는 가스설비 안의 고압가스 폐기를 증명할 수 있는 서류"],
        "choose": ("type", "무슨 신고인가요?", ["개시", "중단", "폐지", "재개"],
                   {"개시": "]개시", "중단": "]중단", "폐지": "]폐지", "재개": "]재개"}),
        "fields": [CO, CEO, OFFICE2, TELP,
                   ("permit_kind", "허가(신고ㆍ등록)종류", "허가 종류 ('허가(신고·등록)종류' 칸)", "예: 고압가스 특정제조"),
                   ("permit_no", "허가(신고ㆍ등록)번호", "허가번호 ('허가(신고·등록)번호' 칸)", "예: 제2027-03호"),
                   ("permit_date", "허가(신고ㆍ등록)연월일", "허가 받은 날 ('허가 연월일' 칸)", "예: 2027. 2. 1."),
                   ("start_date", "재개 연월일", "개시(중단·폐지·재개) 날 ('연월일' 칸)", "예: 2027. 9. 1."),
                   ("reason", "재개 사유", "사유 ('사유' 칸)", "예: 완성검사 합격에 따른 영업 개시")],
    },
    "h2_review": {
        "title": "수소용품·수소연료사용시설 기술검토 신청",
        "desc": "수소용품 제조허가 전, 수소연료사용시설 설치 전 한국가스안전공사 기술검토",
        "law": H2, "no": 28, "who": "한국가스안전공사", "days": "7일(외국수소용품 제조등록의 경우 15일)",
        "fee": "「고압가스 안전관리법 시행령」 제22조에 따른 수수료",
        "docs": ["시설의 설치계획서(허가 또는 등록 사항을 변경하려는 경우에는 그 변경된 부분만을 말합니다) 1부",
                 "시설기준과 기술기준에 관한 도면 및 그 설명서(허가 또는 등록 사항을 변경하려는 경우에는 그 변경된 부분만을 말합니다) 1부",
                 "수소용품 제조사업자나 외국수소용품의 제조등록자의 경우 수소용품제조공정도 1부"],
        "after": "받은 기술검토서를 수소용품 제조사업 허가 신청서(별지 제10호) 등에 붙입니다.",
        "fields": [CO, CEO2, OFFICE2, TEL, BIZ, MAIL, SITE,
                   ("scope", "사업의 종류 및 대상 범위", "사업 종류·대상 범위 ('사업의 종류 및 대상 범위' 칸)",
                    "예: 수소용품 제조사업 — 수전해설비 1 MW")],
        "no_name": True,                      # '신청인(Applicant)' 글자와 겹쳐 이름은 직접 적는다
    },
    "h2_rules": {
        "title": "안전관리규정 심사 신청 (수소법)",
        "desc": "수소법에 따른 안전관리규정을 한국가스안전공사에 심사받기",
        "law": H2, "no": 21, "who": "한국가스안전공사", "days": "7일",
        "fee": "「수소경제 육성 및 수소 안전관리에 관한 법률」 제55조제2항제1호에 따라 산업통상자원부장관이 정한 수수료",
        "docs": ["안전관리규정 3부"],
        "fields": [CO, CEO2, OFFICE2, TEL, MAIL, BIZ, SITE],
    },
    "h2_manager": {
        "title": "안전관리책임자 선임 신고 (수소법)",
        "desc": "수소법에 따른 안전관리책임자를 선임·해임했거나 퇴직했을 때",
        "law": H2, "no": 22, "who": "특별자치시장·특별자치도지사·시장·군수·구청장", "days": "즉시", "fee": "없음",
        "docs": [],
        "choose": ("type", "무슨 신고인가요?", ["선임", "해임", "퇴직"],
                   {"선임": "] 선임", "해임": "] 해임", "퇴직": "] 퇴직"}),
        "fields": [CO, ("ceo", "성명", "대표자 이름 ('성명' 칸)", "예: 홍길동", None, None, {"nth": 0}),
                   OFFICE2, TEL, MAIL, SITE,
                   ("mgr_name", "성명", "안전관리책임자 이름 (표의 '성명' 칸)", "예: 김안전", "below", None, {"nth": 1, "row": "선임"}),
                   ("mgr_qual", "자격", "자격 (표의 '자격' 칸)", "예: 가스기능사", "below", None, {"row": "선임"}),
                   ("mgr_no", "자격증 번호", "자격증 번호 (표의 '자격증 번호' 칸)", "예: 12345678", "below", None, {"row": "선임"})],
        "sign": "first",
    },
}


def _pick(hits, t):
    """칸 이름이 서식에 여러 번 나올 때 어느 것에 쓸지.
    전자우편·사업자번호는 맨 위 안내문에도 같은 글자가 있어 마지막 것, 나머지는 첫 것.
    t[6] = {"nth": n} 이면 n번째(선임신고서의 '성명'은 신고인 성명 다음, 표 머리의 성명)."""
    opts = t[6] if len(t) > 6 and isinstance(t[6], dict) else {}
    if "nth" in opts:
        return hits[min(opts["nth"], len(hits) - 1)] if opts["nth"] >= 0 else hits[opts["nth"]]
    return hits[-1] if t[0] in ("email", "bizno") else hits[0]


def catalog():
    """화면에 보낼 목록. 칸 위치 같은 내부 정보는 뺀다."""
    out = []
    for fid, f in FORMS.items():
        out.append({
            "id": fid, "title": f["title"], "desc": f["desc"],
            "form": f"{f['law'].replace(' 시행규칙', '')} 시행규칙 별지 제{f['no']}호서식",
            "who": f["who"], "days": f["days"], "fee": f["fee"], "docs": f["docs"],
            "before": f.get("before", ""), "after": f.get("after", ""),
            "choose": list(f["choose"][:3]) if f.get("choose") else None,
            "fields": [{"key": t[0], "q": t[2], "text": t[3], "value": (t[5] if len(t) > 5 else "") or ""}
                       for t in f["fields"]],
        })
    return out


def guess(q):
    """질문에서 서식을 짐작한다. 모르면 None."""
    # 새 서식(2026-11)을 먼저 본다 — '충전소 기술검토'가 충전소 허가로 가지 않게
    h2 = any(w in q for w in ("수소법", "수소용품", "연료전지", "수전해설비", "수소연료사용", "안전관리책임자"))
    rules = [("h2_review" if h2 else "gas_review", ("기술검토",)),
             ("gas_mid", ("중간검사",)),
             ("h2_rules" if h2 else "gas_rules", ("안전관리규정 심사", "안전관리규정심사", "규정 심사")),
             ("h2_manager" if h2 else "gas_manager", ("선임 신고", "선임신고", "안전관리자 선임", "안전관리책임자 선임", "해임 신고")),
             ("gas_start", ("개시 신고", "개시신고", "폐지 신고", "중단 신고", "재개 신고", "영업 개시", "사업 개시")),
             ("gas_use_inspect", ("사용시설 완성검사", "사용시설 정기검사", "특정고압가스 사용시설 검사")),
             ("h2_product", ("수소용품 검사", "제품 검사", "출고")),
             ("h2_use_inspect", ("연료전지", "사용시설")),
             ("h2_maker", ("수소용품", "수전해설비 제조", "연료전지 제조", "제조사업")),
             ("gas_inspect", ("완성검사", "정기검사")),
             ("gas_use", ("사용신고", "사용 신고")),
             ("gas_report", ("제조 신고", "제조신고")),
             ("gas_permit", ("충전소", "충전", "저장소", "제조허가", "제조 허가", "수전해"))]
    for fid, words in rules:
        if any(w in q for w in words):
            return fid
    return None



def sign_layout(p, first=False, label=None):
    """서식 아래 '년 월 일 / 신청인 ○○○ (서명 또는 인)' 줄의 자리를 pt 로 돌려준다.

    date : [(key, x, base, w)]   년·월·일 숫자를 쓸 자리(각 글자 바로 왼쪽)
    name : (x, base, w) 또는 None 신청인 이름을 쓸 자리(이름표와 서명 표시 사이)
    sign : (x0, y0, x1, y1) 또는 None 서명 그림 자리('(서명 또는 인)' 위에 겹친다 — 한국 서식 관례)
    """
    out = {"date": [], "name": None, "sign": None}
    # '생년월일' 칸 이름도 년·월이 붙어 있어 걸린다. 날짜 줄은 년과 월 사이가 넓다(15pt 넘게).
    ys = [r for r in p.search_for("년") if any(abs(r.y0 - m.y0) < 2 and m.x0 - r.x1 > 15 for m in p.search_for("월"))]
    if ys:
        y = ys[-1]
        row = lambda ch: next((r for r in p.search_for(ch) if abs(r.y0 - y.y0) < 2 and r.x0 > y.x0), None)
        for key, anchor, w in (("date_y", y, 26), ("date_m", row("월"), 13), ("date_d", row("일"), 13)):
            if anchor:
                out["date"].append((key, anchor.x0 - w, anchor.y1 - 1.5, w))
    sg = None
    for lab in ((label,) if label else ()) + ("(서명 또는 인)", "(서명 또는 날인)", "서명 또는"):
        hits = p.search_for(lab)
        if hits:
            sg = hits[0] if first else hits[-1]     # 동의서가 아래 붙은 서식은 첫 서명란이 신청인 칸
            break
    if sg:
        # 서명 칸 높이: 표시 위아래의 가로줄 사이를 넘지 않게 잰다.
        up, down = sg.y0 - 14, sg.y1 + 10
        for d in p.get_drawings():
            for it in d["items"]:
                if it[0] == "l" and abs(it[1].y - it[2].y) < 1:
                    ly, lx0, lx1 = it[1].y, min(it[1].x, it[2].x), max(it[1].x, it[2].x)
                    if lx0 < sg.x1 and lx1 > sg.x0:
                        if ly <= sg.y0 and ly > up:
                            up = ly + 1
                        if ly >= sg.y1 and ly < down:
                            down = ly - 1
        # 날짜 줄이 바로 위에 붙어 있으면(가로줄 없이) 그 줄을 덮지 않게 아래로 내린다.
        for _, _, base, _ in out["date"]:
            if base < sg.y0 and base + 3 > up:
                up = base + 3
        out["sign"] = (sg.x0 - 6, up, sg.x1 + 6, down)
        lab = next((r for nm in ("신청인", "신고인") for r in p.search_for(nm)
                    if abs(r.y0 - sg.y0) < 3 and r.x1 < sg.x0), None)
        x = (lab.x1 + 8) if lab else sg.x0 - 120
        out["name"] = (x, sg.y1 - 1.5, max(40, sg.x0 - 8 - x))
    return out


def below_base(p, h, t=None):
    """머리글 아래 칸에 넣을 글자 기준선. 머리글 바로 밑 가로줄을 재서 다음 칸 가운데에 맞춘다
    (실측: 수소제품 '규격·수량' 은 머리글 칸 아래 줄이 h.y1+11 이라 +12 로 넣으면 줄을 밟았다)."""
    opts = t[6] if t is not None and len(t) > 6 and isinstance(t[6], dict) else {}
    if opts.get("row"):
        # 머리 칸이 여러 줄이라 '바로 아래'가 아직 머리 칸 안인 서식(수소법 선임신고서): 왼쪽 '구분' 칸의
        # 줄 이름(예: 선임) 중 이 칸보다 왼쪽·아래에 있는 첫 것의 높이에 쓴다
        rows = [r for r in p.search_for(opts["row"]) if r.x1 < h.x0 and r.y0 > h.y0 + 2]
        if rows:
            r = min(rows, key=lambda r: r.y0)
            return r.y1 - 1.5
    ys = set()
    for d in p.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 1:
                a, b = sorted((it[1].x, it[2].x)); y = it[1].y
            elif it[0] == "re":
                r = it[1]; a, b = r.x0, r.x1
                for y in (r.y0, r.y1):
                    if a <= h.x0 + 2 <= b:
                        ys.add(round(y, 1))
                continue
            else:
                continue
            if a <= h.x0 + 2 <= b:
                ys.add(round(y, 1))
    ys = sorted(y for y in ys if y > h.y1 - 1)
    if ys and ys[0] < h.y1 + 13:                 # 머리글 칸이 바로 끝난다 → 그 아래 칸
        nxt = [y for y in ys if y > ys[0] + 6]
        if nxt:
            return (ys[0] + nxt[0]) / 2 + 3
    return h.y1 + 12


def fill(fid, vals, ink="black", dynamic=True):
    """ink: black=제출용(검정), blue=검토용(AI가 채운 칸이 보이게).
    dynamic=False 면 날짜·신청인·서명을 비운다(미리보기에서 바로 고칠 때 바탕용)."""
    import pymupdf
    f = FORMS[fid]
    INK = BLUE if ink == "blue" else (0, 0, 0)
    r = forms.resolve(f["law"], "서식", f["no"])
    if not r or not r.get("_pdf"):
        raise RuntimeError("공식 서식 파일을 찾지 못했습니다")
    data, _ = forms.fetch_file(r["_pdf"], "pdf")
    doc = pymupdf.open(stream=data, filetype="pdf")
    p = doc[0]
    p.insert_font(fontname="mg", fontfile=FONT)

    def mark(label):
        hits = p.search_for(label) or p.search_for(label.replace(" ", ""))
        if hits:                                         # '[ ]' 칸 안에 √
            h = hits[0]
            dx = 7 if label.startswith(("]", "］")) else 14   # '[  ] 이름' 은 괄호가 한 칸 더 왼쪽(］는 전각 괄호)
            p.insert_text((h.x0 - dx, h.y1 - 1.5), "√", fontname="mg", fontsize=9, color=INK)

    for label in f.get("check", []):
        mark(label)
    if f.get("choose"):
        key, _, opts, labels = f["choose"]
        v = vals.get(key) or ""
        for name, label in labels.items():
            if v.startswith(name):
                mark(label)

    for t in f["fields"]:
        key, label = t[0], t[1]
        hits = p.search_for(label)
        if not hits:
            continue
        # 전자우편·사업자번호는 서식 맨 위 안내문("…사업자등록번호와 전자우편주소는…")에도 같은 글자가 있다.
        # 칸 이름은 그 아래에 있으니 마지막 것을 쓴다.
        h = _pick(hits, t)
        v = (vals.get(key) or "").strip()
        if not v and ink != "blue":                       # 제출용은 빈칸을 그대로 비워 둔다
            continue
        text, color = (v, INK) if v else (NEED, ORANGE)
        if len(t) > 4 and t[4] == "below":               # 칸 이름이 머리글이고 값은 아래 줄
            p.insert_text((h.x0, below_base(p, h, t)), text[:20], fontname="mg", fontsize=8, color=color)
        else:
            p.insert_text((h.x1 + 8, h.y1 - 1.5), text[:48], fontname="mg", fontsize=8.5, color=color)

    # 날짜·신청인·서명. 날짜는 고친 값이 있으면 그것, 없으면 오늘.
    if dynamic:
        lay = sign_layout(p, f.get("sign") == "first", f.get("sign_label"))
        today = dict(zip(("date_y", "date_m", "date_d"),
                         (time.strftime("%Y"), time.strftime("%m").lstrip("0"), time.strftime("%d").lstrip("0"))))
        for key, x, base, w in lay["date"]:
            text = (vals.get(key) or today[key]).strip()
            p.insert_text((x, base), text[:4], fontname="mg", fontsize=8.5, color=INK)
        if lay["name"] and (vals.get("applicant") or "").strip() and not f.get("no_name"):
            x, base, w = lay["name"]
            p.insert_text((x, base), vals["applicant"].strip()[:20], fontname="mg", fontsize=9, color=INK)
        sig = vals.get("sign") or ""
        if lay["sign"] and sig.startswith("data:image/png;base64,"):
            import base64
            # 화면에서 잉크 부분만 잘라 보낸다. 원래 가로세로 비율 그대로 칸 안에 넣는다.
            p.insert_image(pymupdf.Rect(*lay["sign"]), stream=base64.b64decode(sig.split(",", 1)[1]),
                           keep_proportion=True, overlay=True)
    if ink == "blue":                                    # 제출용에는 안내 문구를 넣지 않는다
        note = "※ 검토용: 파란 글씨는 AI가 채운 초안, 주황 [직접 입력]은 직접 채우세요. 서명·생년월일은 직접 적습니다."
        p.insert_text((36, p.rect.height - 14), note, fontname="mg", fontsize=7, color=ORANGE)
    doc.subset_fonts()
    return doc.tobytes(garbage=3, deflate=True), f"{f['title']}_신청서.pdf"


def fill_hwpx(fid, vals):
    """같은 내용을 한글(HWPX) 문서로 만든다. 원본 서식의 칸 위치는 쓰지 않고, 항목·값 표로 옮긴다.

    빈 값은 [직접 입력]으로 적는다. 돌려주는 것: (bytes, 파일명).
    """
    import hwpx_doc
    f = FORMS[fid]
    rows = []
    for t in f["fields"]:
        v = (vals.get(t[0]) or "").strip()
        rows.append((t[1], v or "[직접 입력]"))
    blocks = [
        ("title", f"{f['title']} 신청서"),
        ("para", f"{f['law'].replace(' 시행규칙', '')} 시행규칙 별지 제{f['no']}호서식 기준으로 정리한 문서입니다. "
                 "공식 서식 PDF 와 내용을 대조한 뒤 제출하세요."),
        ("heading", "신청 내용"),
        ("table", rows),
        ("heading", "신청 정보"),
        ("table", [("접수 기관", f["who"]), ("처리 기간", f["days"]), ("수수료", f["fee"])]),
        ("heading", "같이 낼 서류"),
        ("para", " · ".join(f["docs"]) if f["docs"] else "없음"),
    ]
    if f.get("after"):
        blocks += [("heading", "다음 할 일"), ("para", f["after"])]
    blocks.append(("para", "주민등록번호·생년월일·서명은 직접 적으세요. 작성일: " + time.strftime("%Y-%m-%d")))
    return hwpx_doc.make_hwpx(blocks, title=f["title"]), f"{f['title']}_신청서.hwpx"


def edit_layout(fid, vals):
    """미리보기에서 바로 고치기용. 칸 글자는 비운 바탕 PDF 와, 칸마다 글을 얹을 자리를 돌려준다.

    화면에서는 바탕 그림 위에 같은 자리에 입력 상자를 얹고, 사용자가 치는 글자를 그대로
    보여 준다(바탕에 글자가 있으면 두 번 겹쳐 보이므로 바탕은 비운다). 자리 계산은 fill()
    과 같은 규칙을 쓴다 — 칸 이름 바로 오른쪽(아래 줄 칸은 이름 아래).
    """
    import pymupdf
    f = FORMS[fid]
    keep = {}
    if f.get("choose"):                         # 체크(√) 칸은 바탕에 그대로 찍는다
        k = f["choose"][0]
        if vals.get(k):
            keep[k] = vals[k]
    data, _ = fill(fid, keep, "black", dynamic=False)
    doc = pymupdf.open(stream=data, filetype="pdf")
    p = doc[0]
    pw, ph = p.rect.width, p.rect.height
    lay = sign_layout(p, f.get("sign") == "first", f.get("sign_label"))
    words = p.get_text("words")                 # (x0, y0, x1, y1, 글자, ...)
    # 표의 세로줄. 글자만 보고 끝을 정하면 상자가 줄을 밟는다(실측: 대표자 성명 칸).
    vlines = []
    table_right = pw - 30                       # 표의 오른쪽 끝(가로줄이 끝나는 곳)
    hl = []
    for d in p.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 1 and abs(it[1].x - it[2].x) > 100:
                hl.append(max(it[1].x, it[2].x))
            elif it[0] == "re" and it[1].height < 2 and it[1].width > 100:
                hl.append(it[1].x1)
    if hl:
        table_right = min(table_right, max(hl))
    for d in p.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.x - b.x) < 1 and abs(a.y - b.y) > 5:
                    vlines.append((a.x, min(a.y, b.y), max(a.y, b.y)))
            elif it[0] == "re":
                r = it[1]
                if r.width < 2 and r.height > 5:          # 가는 사각형으로 그린 세로줄
                    vlines.append((r.x0, r.y0, r.y1))
                elif r.height > 5:                         # 칸 테두리 사각형의 좌우 변
                    vlines.append((r.x0, r.y0, r.y1))
                    vlines.append((r.x1, r.y0, r.y1))
    boxes = []
    for t in f["fields"]:
        key, label = t[0], t[1]
        hits = p.search_for(label)
        if not hits:
            continue
        h = _pick(hits, t)
        below = len(t) > 4 and t[4] == "below"
        fs = 8 if below else 8.5
        if below:
            x, base = h.x0, below_base(p, h, t)
        else:
            x, base = h.x1 + 8, h.y1 - 1.5
        top = base - fs - 1
        # 오른쪽 끝: 같은 줄에서 다음 글자가 나오기 직전, 없으면 쪽 여백 직전까지.
        right = table_right - 4
        for w in words:
            if w[0] > x + 6 and w[1] < base and w[3] > top:
                right = min(right, w[0] - 4)
        for vx, y0, y1 in vlines:
            if vx > x + 6 and y0 < base and y1 > top:
                right = min(right, vx - 4)
        width = max(30, min(right - x, 300))
        boxes.append({"key": key, "q": t[2], "x": round(x, 1), "y": round(top, 1),
                      "w": round(width, 1), "h": round(fs + 4, 1), "fs": fs,
                      "value": (vals.get(key) or "").strip()})
    today = {"date_y": time.strftime("%Y"), "date_m": time.strftime("%m").lstrip("0"),
             "date_d": time.strftime("%d").lstrip("0")}
    for key, x, base, w in lay["date"]:
        boxes.append({"key": key, "q": {"date_y": "신청 연도", "date_m": "월", "date_d": "일"}[key],
                      "x": round(x - 1, 1), "y": round(base - 9.5, 1), "w": round(w, 1), "h": 12.5, "fs": 8.5,
                      "value": (vals.get(key) or today[key]).strip()})
    if lay["name"]:
        x, base, w = lay["name"]
        boxes.append({"key": "applicant", "q": "신청인 이름", "x": round(x, 1), "y": round(base - 10, 1),
                      "w": round(w, 1), "h": 13, "fs": 9, "value": (vals.get("applicant") or "").strip()})
    if lay["sign"]:
        x0, y0, x1, y1 = lay["sign"]
        boxes.append({"key": "sign", "kind": "sign", "q": "서명", "x": round(x0, 1), "y": round(y0, 1),
                      "w": round(x1 - x0, 1), "h": round(y1 - y0, 1), "fs": 9, "value": ""})
    return data, boxes, pw, ph


# ── 검사 ─────────────────────────────────────────────────────────
GUESS_CASES = [("충전소 기술검토 신청서 써줘", "gas_review"), ("연료전지 기술검토 신청서", "h2_review"),
               ("중간검사 신청서 작성", "gas_mid"), ("안전관리규정 심사 신청서 써줘", "gas_rules"),
               ("수소용품 안전관리규정 심사", "h2_rules"), ("안전관리자 선임 신고서 작성", "gas_manager"),
               ("안전관리책임자 선임 신고서", "h2_manager"), ("사업 개시 신고서 써줘", "gas_start"),
               ("충전소 허가 신청서 작성해줘", "gas_permit"), ("수소 사용시설 완성검사 신청서", "gas_use_inspect"),
               ("연료전지 완성검사 신청서", "h2_use_inspect"), ("수소 사용신고서 작성", "gas_use")]


def check():
    """① 질문 → 서식 짐작 ② 서식 PDF 에 칸 이름·체크 글자가 그대로 있는지(서식이 개정되면 여기서 걸린다).
    ②는 법령정보센터·pymupdf 가 있어야 하므로 없으면 건너뛴다."""
    bad = 0
    for q, want in GUESS_CASES:
        if guess(q) != want:
            print(f"✗ 서식 짐작: '{q}' → {guess(q)} (기대 {want})")
            bad += 1
    print(f"서식 짐작 {len(GUESS_CASES)}문항 확인")
    try:
        import pymupdf
    except ImportError:
        print("서식 칸 대조 건너뜀 (pymupdf 없음)")
        return bad
    for fid, f in FORMS.items():
        try:
            r = forms.resolve(f["law"], "서식", f["no"])
            data, _ = forms.fetch_file(r["_pdf"], "pdf")
        except Exception as e:
            print(f"서식 칸 대조 건너뜀 ({fid}: {type(e).__name__}) — 법령정보센터에 연결되지 않음")
            return bad
        p = pymupdf.open(stream=data, filetype="pdf")[0]
        labels = [t[1] for t in f["fields"]] + f.get("check", []) \
            + (list(f["choose"][3].values()) if f.get("choose") else [])
        for lab in labels:
            if not (p.search_for(lab) or p.search_for(lab.replace(" ", ""))):
                print(f"✗ {fid} ({f['law']} 별지 제{f['no']}호): '{lab}' 칸을 서식에서 못 찾음 — 서식 개정 확인")
                bad += 1
    print(f"서식 {len(FORMS)}종 칸 이름 대조" + (" — 전부 있음" if not bad else ""))
    return bad


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--check" in sys.argv:
        sys.exit(1 if check() else 0)
