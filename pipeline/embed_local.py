#!/usr/bin/env python3
"""조각 32,217개를 '뜻'으로 찾을 수 있게 숫자로 바꿔 저장한다 — 내 컴퓨터 GPU 판.

embed_index.py 는 구글 API 를 쓰는데 무료 한도가 하루 1,000회라 열흘 넘게 걸렸다
(실측 9/2: 2,900개에서 멈춤). 이 스크립트는 공개 모델을 내 컴퓨터에 받아서 직접
계산한다. 한도가 없고 GTX 1060 으로 30분 안팎이면 끝난다.

결과 파일 형식(embeddings.npy / embeddings_have.npy / embeddings.json)은
embed_index.py 와 같아서 search.py 가 그대로 읽는다. 모델 이름 앞에 "local:" 을
붙여 두면 search.py 가 질문도 같은 모델로 숫자로 바꾼다.

    python embed_local.py          # 전부
    python embed_local.py 500      # 앞 500개만(시험용)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # 최상위의 search.py 를 찾도록
import search
from embed_index import build_order, doc_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent.parent   # 프로젝트 최상위
OUT = HERE / "data" / "embeddings.npy"
META = HERE / "data" / "embeddings.json"

# 한국어 성능이 좋은 공개 모델(bge-m3 를 한국어로 더 학습한 것). 1024차원.
# 질문 쪽(search.py)도 반드시 같은 모델을 써야 한다 — 모델마다 좌표계가 다르다.
MODEL = "nlpai-lab/KURE-v1"
DIM = 1024
BATCH = 32
MAX_TOKENS = 512          # 조각이 600자라 이 안에 다 들어간다


def main():
    import torch
    from sentence_transformers import SentenceTransformer

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    docs = search.load_docs()
    n = len(docs)
    order = build_order(docs)
    todo = order[:limit] if limit else order

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"조각 {n:,}개 중 {len(todo):,}개 · {MODEL} · {device}", flush=True)
    model = SentenceTransformer(MODEL, device=device)
    model.max_seq_length = MAX_TOKENS
    if device == "cuda":
        model.half()

    vecs = np.zeros((n, DIM), dtype=np.float16)
    have = np.zeros(n, dtype=bool)

    def save(k):
        np.save(OUT, vecs)
        np.save(OUT.with_name("embeddings_have.npy"), have)
        META.write_text(json.dumps(
            {"model": f"local:{MODEL}", "dim": DIM, "total": n, "done": k},
            ensure_ascii=False), encoding="utf-8")

    t0 = time.time()
    step = BATCH * 20                       # 640개마다 저장·보고
    for i in range(0, len(todo), step):
        idx = todo[i:i + step]
        got = model.encode([doc_text(docs[j]) for j in idx],
                           batch_size=BATCH, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)
        vecs[idx] = got.astype(np.float16)
        have[idx] = True
        done = i + len(idx)
        save(done)
        pace = (time.time() - t0) / done
        print(f"  {done:,}/{len(todo):,}  남은 시간 약 {(len(todo)-done)*pace/60:.0f}분",
              flush=True)

    save(len(todo))
    print(f"완료: {int(have.sum()):,}개 · {OUT.stat().st_size/1048576:.1f} MB · "
          f"{(time.time()-t0)/60:.1f}분", flush=True)


if __name__ == "__main__":
    sys.exit(main())
