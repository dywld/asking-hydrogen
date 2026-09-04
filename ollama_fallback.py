#!/usr/bin/env python3
"""로컬 LLM 폴백 — 제미나이 무료 한도가 전부 막혔을 때 내 컴퓨터의 모델로 답한다.

무료 한도는 모델마다 하루치가 따로라 9개를 줄세워 두었지만, 발표 직전에
전부 소진되는 일이 없다고 장담할 수 없다. Ollama 가 떠 있으면 마지막 순서로
그쪽에 같은 대화를 넘긴다. 검색·근거·검증은 그대로이고 답변 문장만 로컬에서 만든다.

설정(환경변수):
    BOT_OLLAMA=http://127.0.0.1:11434      비어 있으면 이 기능은 꺼진다
    BOT_OLLAMA_MODEL=exaone3.5:7.8b         한국어가 되는 모델이면 무엇이든

터널 구조상 오라클 서버에서 내 PC 의 Ollama 로 가려면 PC 쪽에 터널을 하나 더 열고
그 주소를 BOT_OLLAMA 에 넣는다.
"""
import json
import os
import urllib.request

BASE = os.environ.get("BOT_OLLAMA", "").rstrip("/")
MODEL = os.environ.get("BOT_OLLAMA_MODEL", "exaone3.5:7.8b")


def enabled():
    return bool(BASE)


def alive(timeout=2):
    """서버가 떠 있고 모델이 받아져 있는지 확인한다(빠르게)."""
    if not BASE:
        return False
    try:
        with urllib.request.urlopen(f"{BASE}/api/tags", timeout=timeout) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
        return any(n == MODEL or n.split(":")[0] == MODEL.split(":")[0] for n in names)
    except Exception:
        return False


def _to_messages(system, contents):
    """제미나이 contents 형식 → Ollama chat 형식."""
    msgs = [{"role": "system", "content": system}]
    for c in contents:
        role = "assistant" if c.get("role") == "model" else "user"
        text = "".join(p.get("text", "") for p in c.get("parts", []))
        msgs.append({"role": role, "content": text})
    return msgs


def stream(system, contents, timeout=300):
    """답변 조각을 하나씩 내보낸다. 실패는 예외로 던진다(호출자가 다음 수단으로)."""
    body = json.dumps({
        "model": MODEL, "stream": True,
        "messages": _to_messages(system, contents),
        "options": {"temperature": 0.2, "num_ctx": 16384, "num_predict": 4096},
    }).encode()
    req = urllib.request.Request(f"{BASE}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            try:
                d = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            t = (d.get("message") or {}).get("content")
            if t:
                yield t
            if d.get("done"):
                break


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("주소:", BASE or "(없음 — BOT_OLLAMA 를 설정하세요)")
    print("모델:", MODEL, "· 살아있음:", alive())
    if alive():
        for t in stream("짧게 답하라.", [{"role": "user", "parts": [{"text": "수소는 무엇인가?"}]}]):
            print(t, end="", flush=True)
        print()
