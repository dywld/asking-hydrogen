#!/usr/bin/env python3
"""조각 32,217개를 '뜻'으로 찾을 수 있게 숫자로 바꿔 저장한다.

지금 검색(BM25)은 글자가 겹치는지만 본다. 그래서 '처벌'로 물으면
'벌칙' 조문을 못 찾는다. 뜻이 가까우면 숫자도 가까워지도록 미리 바꿔 두면
글자가 하나도 안 겹쳐도 걸린다.

한 번만 만들어 두면 파일로 남아서, 서버를 껐다 켜도 다시 만들 필요가 없다.
중간에 끊겨도 이어서 받는다(진행분을 계속 저장한다).

※ 9/2 부터는 쓰지 않는다. 무료 한도(하루 1,000회)로 2,900개에서 멈춰서
   내 PC GPU 로 공개 모델을 돌리는 embed_local.py 로 바꿨다. 이 파일은
   build_order·doc_text 를 그쪽에서 빌려 쓰므로 남겨 둔다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # 최상위의 search.py 를 찾도록
import search

# 윈도우 콘솔은 기본이 cp949 라, 로그 파일로 넘길 때 '—' 같은 글자에서 죽는다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent.parent   # 프로젝트 최상위
OUT = HERE / "data" / "embeddings.npy"
META = HERE / "data" / "embeddings.json"

# 임베딩 모델은 중간에 바꾸면 안 된다. 모델마다 좌표계가 달라서,
# 섞어 만든 색인은 거리 계산이 통째로 어긋난다.
# 한도는 모델마다 따로 센다(하루 1,000회). 그래서 하루치가 빈 모델이 있으면
# 여기를 바꾸고 색인을 처음부터 다시 만든다.
#   quotaId: EmbedContentRequestsPerDayPerProjectPerModel-FreeTier = 1000
# 배치 50이면 645회로 전체를 덮어 하루 한도 안에 들어온다.
# gemini-embedding-2 는 하루 1,000회를 이미 써버려 429 가 계속 났다(실측 9/2).
# 한도는 모델마다 따로 세므로 001 로 옮긴다. 배치 50·768차원 동작 확인함.
MODEL = "gemini-embedding-001"
DIM = 768                 # 3072 도 되지만 파일이 4배가 되고 정확도 차이는 작다

# 무료 한도가 아주 빡빡하고, 그날 얼마나 썼는지에 따라 더 좁아진다.
# 한 번에 보낼 수 있는 개수는 실측으로 50이 상한선이다.
#   50 -> 통과   100 -> 429(분당 한도)   200 -> 400(형식 오류)
# 하루 한도가 '요청 1,000회'라 개수를 줄이면 오히려 손해다. 크게 보내고 쉰다.
BATCH = 50
MAX_CHARS = 600
# 15초로 돌리면 배치마다 429 가 한 번씩 나서, 30초를 더 쉬고 다시 보냈다(실측 9/2).
# 그 실패도 하루 한도(1,000회)를 깎으므로 손해가 두 배다. 처음부터 그만큼 쉰다.
# 배치 100 은 400(최대 100)이 아니라 429 로 막힌다 — 분당 한도가 개수가 아니라
# 글자 양에 걸려 있어서, 배치를 키워 횟수를 줄이는 길은 없다.
PACE = 50                 # 배치 사이 대기(초)

# 만드는 순서. 중간에 멈춰도 앞쪽은 쓸 수 있다.
#   1) 법령 조문  — '처벌/폐업' 처럼 말이 안 겹쳐 못 찾던 게 전부 여기 있었다
#   2) 별표       — 표라서 뜻 검색의 이득이 조문보다 작다
#   3) KGS Code   — 전문 용어라 지금 방식으로도 잘 걸린다
ORDER = {None: 0, "별표": 1, "별지서식": 1, "상세기준": 2}

URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
       f"{MODEL}:batchEmbedContents")


def api_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k.strip()
    f = HERE / "key.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


def build_order(docs):
    """중요한 것부터 오도록 색인 순서를 만든다(원래 위치는 그대로 기억한다)."""
    return sorted(range(len(docs)),
                  key=lambda i: (ORDER.get(docs[i].get("kind"), 3), i))


def doc_text(d):
    """검색될 내용. 법령명과 조문 번호도 함께 넣어야 맥락이 산다."""
    head = f"{d['law']} {d['article']} {d['title']}".strip()
    return f"{head}\n{d['content']}"[:MAX_CHARS]


def embed(texts, key, task):
    reqs = [{"model": f"models/{MODEL}",
             "content": {"parts": [{"text": t}]},
             "taskType": task,
             "outputDimensionality": DIM} for t in texts]
    data = json.dumps({"requests": reqs}).encode()
    req = urllib.request.Request(f"{URL}?key={key}", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    return [e["values"] for e in out["embeddings"]]


def embed_with_retry(texts, key, task="RETRIEVAL_DOCUMENT"):
    """한도(429)에 걸리면 점점 오래 쉬었다 다시 한다. 하루치가 빈 게 아니라
    분당 한도인 경우가 많아, 기다리면 대개 풀린다."""
    # 429 에 몰아치면 그 재시도까지 한도를 먹어 더 나빠진다. 길게 쉰다.
    wait = 30
    for _ in range(10):
        try:
            return embed(texts, key, task)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 503):
                raise
            print(f"    {e.code}, {wait}초 쉼", flush=True)
            time.sleep(wait)
            wait = min(int(wait * 1.6), 300)
    raise RuntimeError("재시도 8번 모두 실패")


def main():
    key = api_key()
    if not key:
        print("key.txt 가 없습니다.")
        return 1
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0   # 0 = 전부

    docs = search.load_docs()
    n = len(docs)
    order = build_order(docs)
    todo = order[:limit] if limit else order
    print(f"조각 {n:,}개 중 {len(todo):,}개 · {DIM}차원 · 배치 {BATCH}", flush=True)

    vecs = np.zeros((n, DIM), dtype=np.float16)
    have = np.zeros(n, dtype=bool)
    done = 0
    if OUT.exists() and META.exists():
        m = json.loads(META.read_text(encoding="utf-8"))
        if m.get("total") == n and m.get("dim") == DIM and m.get("model") == MODEL:
            vecs = np.load(OUT)
            have = np.load(OUT.with_name("embeddings_have.npy"))
            done = int(m.get("done", 0))
            print(f"이어받기: {done:,}개는 이미 있음", flush=True)

    def save(k):
        np.save(OUT, vecs)
        np.save(OUT.with_name("embeddings_have.npy"), have)
        META.write_text(json.dumps(
            {"model": MODEL, "dim": DIM, "total": n, "done": k},
            ensure_ascii=False), encoding="utf-8")

    t0 = time.time()
    for i in range(done, len(todo), BATCH):
        idx = todo[i:i + BATCH]
        got = embed_with_retry([doc_text(docs[j]) for j in idx], key)
        for j, v in zip(idx, got):
            vecs[j] = np.asarray(v, dtype=np.float16)
            have[j] = True
        save(i + len(idx))
        pace = (time.time() - t0) / max(i + len(idx) - done, 1)
        left = (len(todo) - i - len(idx)) * pace / 60
        print(f"  {i+len(idx):,}/{len(todo):,}  남은 시간 약 {left:.0f}분", flush=True)
        time.sleep(PACE)

    save(len(todo))
    print(f"완료: {int(have.sum()):,}개 저장 "
          f"({OUT.stat().st_size/1048576:.1f} MB), "
          f"{(time.time()-t0)/60:.0f}분", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
