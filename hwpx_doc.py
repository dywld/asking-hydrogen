#!/usr/bin/env python3
"""한글(HWPX) 문서 만들기. 표준 라이브러리만 쓴다(zipfile, xml).

HWPX 는 OWPML 규격의 zip 묶음이다. 원본 HWP(OLE 이진) 칸을 고치는 대신,
채운 내용을 표 하나짜리 문서로 새로 짠다. 구성:
  mimetype (맨 앞, 무압축) · META-INF/container.xml · version.xml · settings.xml
  Contents/content.hpf · Contents/header.xml · Contents/section0.xml

블록 형식:
  ("title", 글)                       큰 제목 한 줄
  ("para", 글)                        본문 한 문단
  ("heading", 글)                     굵은 소제목
  ("table", [(항목, 값), ...])         두 칸짜리 표(왼쪽 항목 회색 칸)
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape

FONT = "맑은 고딕"
TEXT_W = 42520          # A4 본문 폭(hwpunit, 1/7200 inch 기준 약 150mm)
ROW_H = 2400            # 표 한 줄 높이(hwpunit)

NS = ('xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
      'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
      'xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph" '
      'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
      'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" '
      'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
      'xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" '
      'xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page" '
      'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf" '
      'xmlns:dc="http://purl.org/dc/elements/1.1/" '
      'xmlns:opf="http://www.idpf.org/2007/opf/" '
      'xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart" '
      'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar" '
      'xmlns:epub="http://www.idpf.org/2007/ops" '
      'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"')

XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# charPr 0 본문 10pt, 1 제목 16pt 굵게, 2 소제목 11pt 굵게, 3 표 머리 10pt
# paraPr 0 왼쪽, 1 가운데(제목), 2 표 안 왼쪽
# borderFill 1 테두리 없음, 2 실선 테두리, 3 실선 테두리 + 회색 배경(항목 칸)
_FONTS = "".join(
    f'<hh:fontface lang="{lang}" fontCnt="1"><hh:font id="0" face="{FONT}" type="TTF" isEmbedded="0"/></hh:fontface>'
    for lang in ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"))

_SIDE = ('<hh:{s} type="{t}" width="0.12 mm" color="#000000"/>')


def _border(bid, solid, fill=None):
    t = "SOLID" if solid else "NONE"
    sides = "".join(_SIDE.format(s=s, t=t) for s in
                    ("leftBorder", "rightBorder", "topBorder", "bottomBorder"))
    face = (f'<hc:fillBrush><hc:winBrush faceColor="{fill}" hatchColor="#999999" alpha="0"/></hc:fillBrush>'
            if fill else "")
    return (f'<hh:borderFill id="{bid}" threeD="0" shadow="0" centerLine="NONE" '
            f'breakCellSeparateLine="0"><hh:slash type="NONE" crooked="0" isCounter="0"/>'
            f'<hh:backSlash type="NONE" crooked="0" isCounter="0"/>{sides}'
            f'<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>{face}</hh:borderFill>')


HEADER = (
    XML_DECL
    + f'<hh:head {NS} version="1.4" secCnt="1">'
    + '<hh:refList>'
    + f'<hh:fontfaces itemCnt="7">{_FONTS}</hh:fontfaces>'
    + '<hh:borderFills itemCnt="3">'
    + _border(1, False) + _border(2, True) + _border(3, True, "#EEEEEE")
    + '</hh:borderFills>'
    + '<hh:charProperties itemCnt="4">'
    + '<hh:charPr id="0" height="1000" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
    + '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '</hh:charPr>'
    + '<hh:charPr id="1" height="1600" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
    + '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:bold/></hh:charPr>'
    + '<hh:charPr id="2" height="1100" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
    + '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:bold/></hh:charPr>'
    + '<hh:charPr id="3" height="1000" textColor="#333333" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
    + '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    + '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    + '</hh:charPr>'
    + '</hh:charProperties>'
    + '<hh:tabProperties itemCnt="1"><hh:tabPr id="0" autoTabLeft="0" autoTabRight="0"/></hh:tabProperties>'
    + '<hh:numberings itemCnt="0"/>'
    + '<hh:bullets itemCnt="0"/>'
    + '<hh:paraProperties itemCnt="3">'
    + '<hh:paraPr id="0" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="0" suppressLineNumbers="0" checked="0">'
    + '<hh:align horizontal="JUSTIFY" vertical="BASELINE"/>'
    + '<hh:margin><hc:intent value="0" unit="HWPUNIT"/><hc:left value="0" unit="HWPUNIT"/><hc:right value="0" unit="HWPUNIT"/><hc:prev value="0" unit="HWPUNIT"/><hc:next value="400" unit="HWPUNIT"/></hh:margin>'
    + '<hh:lineSpacing type="PERCENT" value="160" unit="HWPUNIT"/>'
    + '</hh:paraPr>'
    + '<hh:paraPr id="1" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="0" suppressLineNumbers="0" checked="0">'
    + '<hh:align horizontal="CENTER" vertical="BASELINE"/>'
    + '<hh:margin><hc:intent value="0" unit="HWPUNIT"/><hc:left value="0" unit="HWPUNIT"/><hc:right value="0" unit="HWPUNIT"/><hc:prev value="0" unit="HWPUNIT"/><hc:next value="600" unit="HWPUNIT"/></hh:margin>'
    + '<hh:lineSpacing type="PERCENT" value="160" unit="HWPUNIT"/>'
    + '</hh:paraPr>'
    + '<hh:paraPr id="2" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="0" suppressLineNumbers="0" checked="0">'
    + '<hh:align horizontal="LEFT" vertical="CENTER"/>'
    + '<hh:margin><hc:intent value="0" unit="HWPUNIT"/><hc:left value="0" unit="HWPUNIT"/><hc:right value="0" unit="HWPUNIT"/><hc:prev value="0" unit="HWPUNIT"/><hc:next value="0" unit="HWPUNIT"/></hh:margin>'
    + '<hh:lineSpacing type="PERCENT" value="140" unit="HWPUNIT"/>'
    + '</hh:paraPr>'
    + '</hh:paraProperties>'
    + '<hh:styles itemCnt="1"><hh:style id="0" type="PARA" name="바탕글" engName="Normal" '
      'paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/></hh:styles>'
    + '</hh:refList>'
    + '<hh:compatibleDocument targetProgram="HWP201X"><hh:layoutCompatibility/></hh:compatibleDocument>'
    + '<hh:docOption><hh:linkinfo path="" pageInherit="0" footnoteInherit="0"/></hh:docOption>'
    + '<hh:trackchageConfig flags="0"/>'
    + '</hh:head>'
)


def _run(text, char=0):
    return f'<hp:run charPrIDRef="{char}"><hp:t>{escape(text)}</hp:t></hp:run>'


def _para(runs, para=0, pid=0):
    return (f'<hp:p id="{pid}" paraPrIDRef="{para}" styleIDRef="0" pageBreak="0" '
            f'columnBreak="0" merged="0">{runs}'
            '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" '
            'textheight="1000" baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/>'
            '</hp:linesegarray></hp:p>')


def _cell(text, col, row, width, fill, char=0):
    body = _para(_run(text, char), para=2)
    return (f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="{fill}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" '
            f'linkListIDRef="0" linkListNextIDRef="0" textWidth="{width}" textHeight="{ROW_H}" hasTextRef="0" hasNumRef="0">'
            f'{body}</hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="{width}" height="{ROW_H}"/>'
            '<hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>')


def _table(rows):
    lw = 12000
    vw = TEXT_W - lw
    trs = []
    for i, (label, value) in enumerate(rows):
        trs.append('<hp:tr>' + _cell(label, 0, i, lw, 3, 3) + _cell(value, 1, i, vw, 2) + '</hp:tr>')
    return (f'<hp:tbl id="0" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" '
            f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="0" '
            f'rowCnt="{len(rows)}" colCnt="2" cellSpacing="0" borderFillIDRef="2" noAdjust="0">'
            f'<hp:sz width="{TEXT_W}" widthRelTo="ABSOLUTE" height="{ROW_H * len(rows)}" heightRelTo="ABSOLUTE" protect="0"/>'
            '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
            'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            '<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
            + ''.join(trs) + '</hp:tbl>')


def _section(blocks):
    out = []
    for kind, val in blocks:
        if kind == "title":
            out.append(_para(_run(val, 1), para=1))
        elif kind == "heading":
            out.append(_para(_run(val, 2), para=2))
        elif kind == "para":
            out.append(_para(_run(val, 0), para=0))
        elif kind == "table":
            # 표는 문단 안의 run 으로 넣는다(글자처럼 취급)
            out.append(_para(f'<hp:run charPrIDRef="0">{_table(val)}</hp:run>', para=0))
            out.append(_para(_run(""), para=0))
        else:
            raise ValueError(f"알 수 없는 블록: {kind}")
    # 구역 속성(secPr)은 맨 앞 빈 문단의 run 에 둔다. 페이지는 A4 세로, 여백 약 20mm.
    secpr = ('<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" '
             'tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="0" memoShapeIDRef="0" '
             'textVerticalWidthHead="0" masterPageCnt="0">'
             '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/>'
             '<hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>'
             '<hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY">'
             '<hp:margin header="4252" footer="4252" gutter="0" left="5669" right="5669" top="5669" bottom="4252"/>'
             '</hp:pagePr></hp:secPr>')
    head = _para(f'<hp:run charPrIDRef="0">{secpr}<hp:t></hp:t></hp:run>', para=0)
    body = head + "".join(out)
    counter = iter(range(10**6))                       # 문단 id 를 0부터 차례로 붙인다
    body = re.sub(r'<hp:p id="0"', lambda m: f'<hp:p id="{next(counter)}"', body)
    return XML_DECL + f'<hs:sec {NS}>' + body + '</hs:sec>'


def _manifest():
    return (XML_DECL + f'<opf:package {NS} version="" unique-identifier="" id="">'
            '<opf:metadata><opf:title>{title}</opf:title><opf:language>ko</opf:language>'
            '<opf:meta name="creator" content="text">Claude</opf:meta></opf:metadata>'
            '<opf:manifest>'
            '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
            '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
            '<opf:item id="settings" href="settings.xml" media-type="application/xml"/>'
            '</opf:manifest>'
            '<opf:spine><opf:itemref idref="header" linear="yes"/>'
            '<opf:itemref idref="section0" linear="yes"/></opf:spine></opf:package>')


CONTAINER = (XML_DECL
             + '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" '
               'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
               '<ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" '
               'media-type="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>')

VERSION = (XML_DECL
           + '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
           'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="0" buildNumber="0" '
           'os="1" xmlVersion="1.4" application="Hancom Office Hangul" appVersion="5.1.0.0"/>')

SETTINGS = (XML_DECL
            + '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app">'
            '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/></ha:HWPApplicationSetting>')


def make_hwpx(blocks, title="문서"):
    """blocks 를 HWPX 바이트로 만든다. mimetype 은 맨 앞 무압축 항목."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("version.xml", VERSION, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("settings.xml", SETTINGS, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("Contents/content.hpf", _manifest().replace("{title}", escape(title)),
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("Contents/header.xml", HEADER, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("Contents/section0.xml", _section(blocks), compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()
