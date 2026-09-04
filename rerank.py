#!/usr/bin/env python3
"""재순위(크로스인코더) — 검색 상위 후보를 질문과 함께 다시 읽어 줄을 세운다.

글자 검색(BM25)과 뜻 검색(임베딩)은 질문과 조각을 따로 숫자로 만든 뒤 견준다.
그래서 "허가"가 여러 번 나오는 정의 조문처럼, 단어는 겹치는데 답은 아닌 조각이
1등을 차지하는 일이 있다. 크로스인코더는 질문과 조각을 한 문장으로 붙여 읽고
"이 조각이 이 질문의 답인가"를 직접 매긴다. 대신 조각마다 모델을 돌려야 해서
느리다(CPU 기준 24개에 1~3초). 그래서 상위 후보에만 건다.

켜는 법:  BOT_RERANK=1 (server 환경변수). 모델이 없으면 조용히 건너뛴다.
모델:     BAAI/bge-reranker-v2-m3 (다국어, 한국어 포함, 약 2.2GB)
바꾸기:   BOT_RERANK_MODEL=다른이름

    python rerank.py "수소충전소 안전거리"      # 켜고 끈 상위 5개를 나란히 본다
"""
import os
import sys
import threading

MODEL = os.environ.get("BOT_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
MAX_CHARS = 700               # 조각이 600자 안팎이라 이 안에 다 들어간다

_model = None
_lock = threading.Lock()
_failed = False


def _load():
    global _model, _failed
    if _model is not None or _failed:
        return _model
    with _lock:
        if _model is None and not _failed:
            try:
                from sentence_transformers import CrossEncoder
                dev = "cuda" if _has_cuda() else "cpu"
                _model = CrossEncoder(MODEL, max_length=512, device=dev)
            except Exception:
                _failed = True            # 라이브러리·모델이 없으면 이 기능만 끈다
    return _model


def _has_cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def score(query, docs):
    """질문과 조각 목록을 받아 점수 목록을 돌려준다. 못 하면 None."""
    m = _load()
    if m is None or not docs:
        return None
    pairs = [(query, f"{d['law']} {d['article']} {d['title']}\n{d['content']}"[:MAX_CHARS])
             for d in docs]
    try:
        return [float(x) for x in m.predict(pairs, batch_size=16, show_progress_bar=False)]
    except Exception:
        return None


def warm():
    """서버가 뜰 때 미리 읽어 첫 질문이 안 늦게 한다."""
    _load()


if __name__ == "__main__":
    import time
    import search
    q = " ".join(sys.argv[1:]) or "수소충전소 안전거리"
    idx = search.get_index()
    for on in (False, True):
        t = time.time()
        hits = idx.search(q, top_k=5, rerank=on)
        print(f"\n── 재순위 {'켬' if on else '끔'} ({time.time() - t:.2f}초)")
        for h in hits:
            print(f"  [{h['score']}] {h['law']} {h['article']} ({h['title'][:30]})")
