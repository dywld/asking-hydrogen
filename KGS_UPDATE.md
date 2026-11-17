# KGS Code 자동 갱신

기존 `fetch_kgs_code.py`의 공식 목록·PDF 다운로드 경로를 사용한다.
같은 코드·같은 연도·같은 파일명이어도 **원문 SHA-256**이 달라지면 새 버전으로 보관한다.
기존 수집기는 같은 이름의 파일이 있으면 건너뛰므로, 예약 실행에 기존 수집기 대신
`kgs_watch.py`를 사용한다. Python 3.10 이상, 기존 프로젝트와 같은 `pymupdf`가 필요하다.

## Cloudflare 웹·윈도우 앱에 적용

이 저장소의 윈도우 앱은 `desktop/main.js`에서 `hydrogen-guide` Cloudflare 웹 주소를 연다.
그 웹 챗봇은 `cf/src/index.js`를 실행하고, `cf/wrangler.toml`에 연결된 D1에서 검색한다.
개정 감시를 실행하는 서버와 웹 검색을 제공하는 Worker는 다른 프로그램이다.

```
KGS 공식 PDF → kgs_cloud.py (수집·보관·적용일 확인) → Cloudflare Worker → D1 검색
```

### 첫 배포 — Cloudflare 담당자

기존 `hydrogen-guide`와 D1을 관리하는 계정으로, 새 코드가 합쳐진 프로젝트 루트에서 실행한다.
운영 DB의 기존 법령 데이터가 들어 있어야 한다. 마이그레이션은 KGS용 테이블과 색인 연결만 추가한다.

```bash
python cf/build_public.py
cd cf
npx wrangler d1 migrations apply hydrogen-guide --remote
npx wrangler secret put KGS_PUSH_KEY
npx wrangler deploy
```

`KGS_PUSH_KEY`에는 새로 생성한 충분히 긴 비밀값을 넣는다. 기존 Gemini 키와 별도로 관리한다.
서버 쪽 환경 변수에 같은 값을 넣는다. 공개 상태는 웹 주소에 `/api/kgs-updates`를 붙여 확인한다.
아직 게시된 KGS 개정판이 없다면 `{"active":[]}`가 정상이다.

### 예약 작업 — 공식 KGS 사이트에 접속되는 서버

기존 자료를 초기값으로 넣고 운영 자료는 저장소 밖에 둔다. 아래 예시는 리눅스 계정이 저장소 루트에서 실행하는 경우다.

```bash
python -m venv .venv
.venv/bin/python -m pip install pymupdf
mkdir -p "$HOME/kgs-sync/data" "$HOME/.config/hydrogen-guide"
cp -n data/kgs_code.jsonl "$HOME/kgs-sync/data/kgs_code.jsonl"
chmod 700 "$HOME/.config/hydrogen-guide"
```

`$HOME/.config/hydrogen-guide/kgs.env`를 권한 600으로 만들고 `export KGS_PUSH_KEY='Cloudflare와 같은 비밀값'`을 저장한다.
기본 게시 주소는 이 프로젝트의 `hydrogen-guide`다. 별도 Worker를 쓰는 경우 `KGS_PUSH_URL`을 HTTPS 주소로 지정한다.

```bash
. "$HOME/.config/hydrogen-guide/kgs.env"
.venv/bin/python kgs_cloud.py --root "$HOME/kgs-sync" sync
```

`sync`를 예약하면 수록된 KGS Code가 대상이다. 운영에서 일부만 감시하려면 `sync --codes FP216 ...`으로 고른다.
매일 오전 7시 예시(`crontab -e`, 서버 시간 기준). 아래 `REPO` 두 곳을 해당 저장소의 절대 경로로 바꾼다.

```cron
0 7 * * * . "$HOME/.config/hydrogen-guide/kgs.env" && REPO/.venv/bin/python REPO/kgs_cloud.py --root "$HOME/kgs-sync" sync >> "$HOME/kgs-sync/updates.log" 2>&1
```

### 시행일 확인과 운영 복구

- 수집·추출이 실패하면 기존 웹 자료를 사용한다. 시행일이나 경과조치가 불분명하면 후보 PDF만 보관한다.
- 승인 담당자가 적용일을 확인하면 `python kgs_watch.py --root "$HOME/kgs-sync" effective 코드 SHA-256 YYYY-MM-DD`로 등록한다. 즉시 웹에 게시할 때는 `python kgs_cloud.py --root "$HOME/kgs-sync" publish`를 실행한다. 미래 시행일은 예약 실행 때 게시된다.
- Worker는 한 버전의 조각이 모두 들어오고 시행일이 도래한 경우에만 웹 검색에 적용한다. 전송 중에 실패하면 다음 실행에서 다시 보낸다.
- 웹에서 쓰는 버전은 `python kgs_cloud.py --root "$HOME/kgs-sync" status`로 확인한다. 문제 발생 시 `python kgs_cloud.py --root "$HOME/kgs-sync" rollback 코드 현재_SHA-256 이전_SHA-256`으로 되돌린다. `baseline`을 지정하면 기존 D1 자료로 돌아간다. 되돌린 버전은 다음 실행에서 자동으로 재적용하지 않는다.
- 검색은 새 자료를 활성화하면 해당 코드의 이전 조각을 제외하고, 이전 답변 캐시도 피한다. KGS 원문에서 따로 옮긴 확정자료와 안전거리 표는 새 원문과 대조하고 버전을 기록할 때까지 자동으로 인용·판정하지 않는다. 개정 시행일보다 앞선 날짜의 질의에서는 해당 개정판을 제시하지 않는다.
- 전체 법령 자료를 다시 넣어 `docs_fts`를 재생성하는 경우, 기존 SQL을 모두 적용한 뒤 `cd cf && npx wrangler d1 execute hydrogen-guide --remote --file kgs_restore_index.sql`을 실행한다. 일상 KGS 갱신에는 전체 자료 재수입이나 Worker 재배포가 필요 없다.
- 위처럼 운영 자료를 별도 폴더에 두면 웹과 윈도우 앱에 게시된다. Oracle의 기존 Python 예비 챗봇도 같은 자료를 쓰게 하려면 Python 배포본을 이번 코드로 갱신하고, 그 프로젝트 폴더를 예약 작업의 `--root`로 선택한다. 웹의 복구 명령은 웹 D1에 적용되므로 Python 자료도 이전 버전으로 돌려야 한다면 아래 백업 절차를 별도로 실행한다.

## Python 챗봇에서 실행

프로젝트 폴더에서 실행한다. 기본 감시 대상은 현재 `data/kgs_code.jsonl`에 수록된 코드다.
새 코드도 수집하려면 `--codes`로 지정한다.

```bash
python -m pip install pymupdf
python kgs_watch.py sync --codes GC205 --dry-run
python kgs_watch.py sync --codes GC205 --apply
python kgs_watch.py status
```

`--dry-run`은 목록·원문을 조회하고 해시를 비교하지만 원문/상태/검색 데이터는 저장하지 않는다.
잠금 파일은 동시 실행 방지를 위해 생길 수 있다.
`sync`는 한 번 실행, `watch`는 계속 실행이다. 어떤 명령도 외부 알림을 전송하거나
클라우드 서비스를 배포하지 않는다. 계정·API 키도 필요하지 않다.

## 매일 자동 확인

Windows에서는 `start_kgs_watch.bat`을 실행한다. 창과 컴퓨터가 켜져 있어야 한다.
특정 코드만 확인하려면 다음처럼 실행한다.

```bash
python kgs_watch.py watch --hours 24 --codes GC205 FP216 --apply
```

서버의 cron 또는 Windows 작업 스케줄러에서 하루 한 번 아래 명령을 실행해도 된다.
작업의 시작 폴더와 Python 경로는 실제 프로젝트/가상환경의 **절대 경로**로 지정한다.

```bash
python /absolute/path/asking-hydrogen/kgs_watch.py sync --apply
```

KGS 사이트에 정상 접속되는 실행 환경이 필요하다. HTTP 400/403, 빈 목록, 로그인 화면,
다운로드 오류는 우회하지 않고 오류로 기록한다. 실패한 코드는 기존 검색 자료를 유지한다.
목록에서 사라진 코드도 자동 삭제하지 않는다. 게시 지연·실행 간격이 있으므로 초 단위 실시간은 아니다.

## 적용일이 없는 새 버전

**개정일·승인일을 시행일로 간주하지 않는다.** 본문에 명확한
`이 기준은 YYYY년 M월 D일부터 시행` 문장이 하나만 있고 경과조치 등 복잡한 조건이 없을 때만
자동으로 적용일을 읽는다. 대부분의 일반 KGS PDF는 이 조건에 해당하지 않을 수 있다.
이때 PDF와 변경 비교는 자동으로 저장하지만 검색 자료는 대기 상태로 둔다.

`status`에서 `latest_sha256`을 확인하고, 원문의 적용일·경과조치를 검토한 뒤
다음 명령으로 **그 버전의 적용일**을 등록한다.

```bash
python kgs_watch.py effective GC205 실제_64자리_SHA256 2026-11-10
```

이 날짜는 명령 형식 예시다. 실제 원문에서 확인한 날짜로 바꾼다.
한국 시간으로 적용일이 오늘 이전/오늘이면 즉시 반영하고, 미래이면 `watch --apply` 또는 다음
`sync --apply` 실행 때 날짜를 확인하여 반영한다. 날짜를 확인한 해시와 다른 새 개정판에는
이 날짜를 재사용하지 않는다. 항목별로 시행일이 다르거나 경과조치가 있으면 이 명령으로
전체 코드를 일괄 적용하기 전에 적용 범위를 별도로 검토해야 한다.
따라서 현재 구현의 완전 자동 적용 범위는 **적용일이 명확한 버전**이다.

## 저장 결과와 상태

| 경로/상태 | 의미 |
|---|---|
| `data/kgs_updates/versions/코드/SHA/document.pdf` | 수집한 공식 원문 |
| 같은 폴더의 `diff.txt` | 이전 검색 본문과의 변경 전후 비교 |
| `chunks.jsonl`, `metadata.json` | 새 검색 조각·원문 출처·적용일 |
| `data/kgs_updates/backups/해시.jsonl` | 적용 직전 전체 KGS 검색 데이터 |
| `data/kgs_updates/last_report.json` | 마지막 실행 결과·오류 |
| `staged` | 수집 완료, 아직 적용 작업을 실행하지 않음 |
| `needs_effective_date` | 적용일 확인 필요 |
| `scheduled` | 적용일 대기 |
| `active` / `unchanged` | 적용 완료 / 현재 검색 본문과 같음 |
| `older_version` | 자동으로 과거 버전으로 돌아가지 않도록 보류 |

원문과 검색 조각의 무결성을 확인하고 새 JSONL을 임시 파일에 쓴 뒤 원자적으로 교체한다.
수집/변환/교체 실패 시 기존 검색 파일을 유지한다. 같은 프로그램의 중복 실행은 잠금으로 막는다.
검증된 예약 버전은 다음 수집이 실패하더라도 적용일이 되면 반영할 수 있다.
활성 상태의 기준은 `state.json`의 표기가 아니라 실제 `kgs_code.jsonl`이다.

백업으로 되돌릴 때는 먼저 감시 프로그램을 멈춘 뒤, 원하는 백업 JSONL을
`data/kgs_code.jsonl`로 복사한다. 그 코드를 재적용하지 않으려면 감시 대상에서도 제외한다.

## 기존 챗봇과 연결되는 부분

- Python `app.py`/`search.py`: 다음 요청 때 새 검색 색인을 만들므로 서버 재시작이 필요 없다.
- 답변 캐시·문장 검증용 본문 묶음·PDF 쪽 이미지도 자료 버전을 구분한다.
- 기존 임베딩이 새 본문과 다르면 BM25 검색을 사용한다. 벡터가 필요하면
  `python embed_local.py`를 실행한다. 모델 다운로드/추론까지 감시 작업이 자동 실행하지는 않는다.
- 개수가 같은 문서끼리 교체되어도 본문 지문으로 오래된 임베딩을 걸러낸다.
- 갱신된 KGS에서 옮겨 적은 확정자료·안전거리 계산표는 새 버전 확인 전까지 사용하지 않는다.
  내용을 재검토한 표에 해당 `version_sha256`을 기록하면 다시 사용한다.
- `GET /api/kgs-updates`에서 활성 버전과 감시 상태를 볼 수 있다.
- 보관한 과거 PDF는 현재 검색에 섞지 않는다. 과거 기준일별 KGS 검색은 이번 범위에 없다.
- **Cloudflare Worker(`cf/`, `worker/`)는 별도 배포본**이다. 단독 `kgs_watch.py`는 로컬 자료를 갱신하며,
  원격 Worker 데이터는 위의 `kgs_cloud.py`가 게시한다.

KGS PDF의 표·그림은 기존 텍스트 추출 방식을 그대로 사용한다. OCR이나 표 구조 인식은
자동 갱신 기능에 포함되지 않는다. 이미지 PDF, 코드 번호가 다른 PDF, 손상된 PDF는 적용하지 않는다.
공식 사이트 HTML 구조가 바뀌면 목록 해석 오류가 표시되며 `fetch_kgs_code.py`의 파서를 수정해야 한다.

## 검사

```bash
node cf/test_kgs_updates.mjs     # Node.js 24, Worker와 SQLite 색인 통합 검사
python -m unittest discover -s tests -v
python distance.py --check
python facts.py --check
python eval_run.py eval_set_all.json --retrieval --min 0.95 --quiet
```

자동 검사는 로컬 HTTP 서버와 합성 PDF로 세션·다운로드·동일 연도 개정·예약 적용·실패 시 보존·
검색 갱신을 확인한다. 이 검사가 통과한 사실과 실제 KGS 서버의 접속/다운로드 성공은 구분한다.
첫 라이브 확인은 정상 접속되는 환경에서 `--codes` 하나와 `--dry-run`으로 한다.
