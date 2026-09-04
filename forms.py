"""국가법령정보센터에서 별지 서식·별표의 원문 주소와 파일(HWP·PDF)을 가져온다.

왜 필요한가: 답변이 "별지 제8호서식을 첨부해 제출"이라고 알려 줘도, 사용자는 그
서식을 다시 찾아 헤매야 했다. 법령정보센터 주소 규칙(/법령/법령명/제8조)은 조문만
받고 별표·서식은 받지 않는다(별표8·별지8 어느 형태도 오류 페이지가 떴다).

법령정보센터 화면이 실제로 부르는 순서를 그대로 따른다(byl.js 에서 확인):
  1) /법령/법령명            → lsiSeq(법령 고유번호)
  2) lsBylInfoPLinkR.do      → 기본 bylSeq(목록을 부를 때 하나가 있어야 한다)
  3) lsBylInfoR.do (XHR)     → <select id=bylList> 에 별표·서식 전부.
                                값은 "bylSeq,호,의,종류코드,시행일". 110201=별표, 110202=서식
  4) lsBylContentsInfoR.do   → hanFlSeq(HWP)·pdfFlSeq(PDF)·govLnkUrl(정부24 민원 주소)
  5) flDownload.do?flSeq=    → 파일

XMLHttpRequest 헤더가 없으면 3)이 별표만 주고 서식을 빼먹는다. 파일은 한 번 받으면
data/forms/ 에 두고 다시 받지 않는다. 목록은 7일마다 다시 본다(개정으로 파일이 바뀐다).
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = "https://www.law.go.kr/LSW"
DIR = Path(__file__).parent / "data" / "forms"
INDEX = DIR / "index.json"
LIST_TTL = 7 * 86400
KIND_CODE = {"별표": "110201", "서식": "110202"}

_lock = threading.Lock()
_index = None
_opener = None


def _op():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()))
        _opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
            ("Referer", "https://www.law.go.kr/"),
            ("X-Requested-With", "XMLHttpRequest"),
        ]
    return _opener


def _get(url, binary=False):
    with _op().open(url, timeout=40) as r:
        data = r.read()
        return (data, r.headers) if binary else data.decode("utf-8", "replace")


def _post(url, params):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode())
    with _op().open(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def _load():
    global _index
    if _index is None:
        try:
            _index = json.loads(INDEX.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _index = {}
    return _index


def _save():
    DIR.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(_index, ensure_ascii=False, indent=1), encoding="utf-8")


def law_key(law):
    """'고압가스 안전관리법 시행규칙' → '고압가스안전관리법시행규칙'. 법령정보센터 주소 형식."""
    return re.sub(r"\s+", "", law).replace("·", "ㆍ")


def parse_ref(text):
    """'별지 제8호서식' → ('서식', 8, 0) · '별표 6의3' → ('별표', 6, 3) · '별지 제1호의2서식' → ('서식', 1, 2)"""
    m = re.search(r"별지\s*제?\s*(\d+)\s*호(?:의\s*(\d+))?\s*서식", text)
    if m:
        return "서식", int(m.group(1)), int(m.group(2) or 0)
    m = re.search(r"별표\s*(\d+)(?:\s*의\s*(\d+))?", text)
    if m:
        return "별표", int(m.group(1)), int(m.group(2) or 0)
    return None


def law_seq(key):
    page = _get("https://www.law.go.kr/" + urllib.parse.quote(f"법령/{key}"))
    m = re.search(r"lsiSeq=(\d+)", page)
    return m.group(1) if m else None


def _listing(lsi):
    """법령 하나의 별표·서식 목록. [{seq, kind, no, br, title}]"""
    page = _get(f"{BASE}/lsBylInfoPLinkR.do?lsiSeq={lsi}&bylCls=BF")
    m = re.search(r'id="bylSeq"[^>]*value="(\d+)"', page)
    if not m:                                       # 서식이 없는 법령이면 별표 쪽으로
        page = _get(f"{BASE}/lsBylInfoPLinkR.do?lsiSeq={lsi}")
        m = re.search(r'id="bylSeq"[^>]*value="(\d+)"', page)
    if not m:
        return []
    html = _post(f"{BASE}/lsBylInfoR.do",
                 {"bylSeq": m.group(1), "lsiSeq": lsi, "vSct": "*", "efYd": ""})
    items = []
    for val, label in re.findall(r'<option value="([^"]*)"[^>]*>\s*([^<]*)</option>', html):
        parts = val.split(",")
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        kind = {v: k for k, v in KIND_CODE.items()}.get(parts[3])
        if not kind:
            continue
        title = re.sub(r"^\[[^\]]*\]\s*", "", label).replace("&lt;", "<").replace("&gt;", ">").strip()
        items.append({"seq": parts[0], "kind": kind, "no": int(parts[1]),
                      "br": int(parts[2] or 0), "title": title})
    return items


def _law_entry(law):
    key = law_key(law)
    idx = _load()
    e = idx.get(key)
    if e and time.time() - e.get("t", 0) < LIST_TTL:
        return e
    with _lock:
        e = idx.get(key)
        if e and time.time() - e.get("t", 0) < LIST_TTL:
            return e
        lsi = law_seq(key)
        if not lsi:
            return None
        e = idx[key] = {"lsiSeq": lsi, "t": time.time(), "items": _listing(lsi), "files": {}}
        _save()
    return e


def resolve(law, kind, no, br=0):
    """서식·별표 하나의 원문 주소와 파일 번호. 없으면 None.

    돌려주는 것: title, link(법령정보센터 팝업), han·pdf(파일 번호), gov(정부24 민원 주소)
    """
    e = _law_entry(law)
    if not e:
        return None
    hit = next((i for i in e["items"] if i["kind"] == kind and i["no"] == no and i["br"] == br), None)
    if not hit:
        return None
    f = e["files"].get(hit["seq"])
    if f is None:
        html = _post(f"{BASE}/lsBylContentsInfoR.do", {"bylSeq": hit["seq"]})
        ids = dict(re.findall(r'id="(hanFlSeq|pdfFlSeq|govLnkUrl)"[^>]*value="([^"]*)"', html))
        f = {"han": ids.get("hanFlSeq", ""), "pdf": ids.get("pdfFlSeq", ""),
             "gov": ids.get("govLnkUrl", "").strip()}
        with _lock:
            e["files"][hit["seq"]] = f
            _save()
    return {
        "law": law, "kind": kind, "no": no, "br": br, "title": hit["title"],
        "link": f"{BASE}/lsBylInfoPLinkR.do?bylSeq={hit['seq']}&lsiSeq={e['lsiSeq']}",
        "han": bool(f["han"]), "pdf": bool(f["pdf"]), "gov": f["gov"],
        "_han": f["han"], "_pdf": f["pdf"],
    }


def fetch_file(fl_seq, ext):
    """파일 하나. (bytes, 파일명). 한 번 받으면 디스크에 둔다."""
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"{fl_seq}.{ext}"
    meta = DIR / f"{fl_seq}.name"
    if path.exists() and meta.exists():
        return path.read_bytes(), meta.read_text(encoding="utf-8")
    data, headers = _get(f"{BASE}/flDownload.do?flSeq={fl_seq}", binary=True)
    if ext == "pdf" and not data.startswith(b"%PDF"):
        return None, None
    if ext == "hwp" and data[:4] not in (b"\xd0\xcf\x11\xe0", b"HWP ", b"PK\x03\x04"):
        return None, None
    name = f"{fl_seq}.{ext}"
    m = re.search(r'filename="([^"]+)"', headers.get("Content-Disposition") or "")
    if m:
        name = urllib.parse.unquote(m.group(1))
    path.write_bytes(data)
    meta.write_text(name, encoding="utf-8")
    return data, name
