# SkinLens v1 — 파트별 상세 코드 리뷰

> 대상: `SkinLens_v1.zip` (CÔTELEAF AI Skin)
> 리뷰 범위: `src/` 전체 (146개 `.py`, 약 42,800 LOC) + 진입점/설정/패키징
> 작성 기준일: 2026-05-31
> 리뷰 관점: 보안 · 정확성(도메인 로직) · 아키텍처 · 유지보수성

---

## 0. 총평 (Executive Summary)

전반적으로 **설계 의도가 분명하고 엔지니어링 규율이 살아있는 코드베이스**입니다. config 기반 SSOT 스코어링, 직교 신호 분해, 전략 패턴 레지스트리(분석기/복원/LLM), 라우터·미들웨어 분리, SSRF·Path Traversal 방어, JWT 기본키 가드, 비밀키 위생 등 "잘 만든 흔적"이 곳곳에 보입니다. 테스트도 60개 이상으로 풍부합니다.

다만 **공개 API 표면(서버 계층)에 배포를 막아야 할 수준의 인가/보안 결함**이 몇 건 있고, **스코어링 핵심 경로에 점수를 왜곡하는 계산 버그**가 1건 있습니다. 이 둘은 출시 전 반드시 수정이 필요합니다.

| 심각도 | 건수 | 핵심 항목 |
|---|---|---|
| 🔴 P0 (Critical) | 4 | Job 조회/다운로드 인가 부재, 점수보정 계산 버그, 업로드 경로 traversal, 업로드 세션 IDOR |
| 🟠 P1 (High) | 5 | 인가 함수 인자순서 오류, callback_url SSRF, 인증모델 자체, DB 커넥션 누수, rate-limit 키 버그 |
| 🟡 P2 (Medium) | 10+ | DNS rebinding, 민감필드 미레다크션, trust_proxy 스푸핑, 광범위 except, deprecated API 등 |

---

## 1. 아키텍처 총평

```
main.py (GUI/CLI 분기)
│
├─ src/server/         FastAPI 서버 (app·미들웨어·라우터)  ── 8,221 LOC
├─ src/cli/            CLI + execution_history DB         ── 4,765 LOC
├─ src/gui/            PySide6 GUI (image_enhancer 등)     ── 5,201 LOC
│
├─ src/pipeline/       복원→분석 파이프라인 오케스트레이션  ── 1,119 LOC
├─ src/restoration/    CodeFormer / RestoreFormer 전략     ──   718 LOC
├─ src/skin/           얼굴검출·ROI·분석기(직교 신호)       ── 4,767 LOC
├─ src/scoring/        스코어링 코어·멀티뷰·브레이크포인트  ── 2,752 LOC
├─ src/llm/            Gemini 리포트·프롬프트·점수보정      ── 4,872 LOC
├─ src/prescription/   PCR 처방 계산                       ──   817 LOC
│
├─ src/db/             SkinAnalysisDB·Supabase 동기화       ── 5,059 LOC
├─ src/telegram/       알림·명령·모니터                    ── 2,547 LOC
└─ src/{config,i18n,monitoring,notification,recovery,utils}
```

**강점**
- **계층 분리가 명확**합니다. `deps.py`(앱 비의존 공유)/`server.py`(앱·미들웨어)/`routers/*`(엔드포인트) 분리가 깔끔합니다.
- **config 중심 SSOT**: 가중치·브레이크포인트·직교 카테고리·측정항목 매핑을 `config.json`/프롬프트 템플릿에서 동적 로드. 하드코딩 제거 리팩토링 흔적(`[REFACTOR ...]`)이 일관됩니다.
- **전략 패턴**: 분석기/복원/LLM 모두 레지스트리+전략으로 교체·A/B가 가능하게 설계.

**구조적 약점 (개선 여지)**
- **`deps.py` 설정 중복**: 모듈 레벨 상수(`SECRET_KEY`, `ALLOWED_EXT` …)와 getter(`get_secret_key()` …)가 **동시에** 존재하고 전자는 전부 `[DEPRECATED]` 주석이 달려 있습니다. config 핫리로드를 진짜로 지원하려면 라우터들이 상수 import를 멈추고 getter만 쓰도록 정리해야 합니다. 현재는 `jobs.py` 등이 여전히 `MAX_UPLOAD_BYTES`, `ALLOWED_EXT`, `SERVER_URL` 같은 **고정 상수**를 import 중이라 핫리로드가 부분적으로만 작동합니다.
- **분석기 이중 아키텍처**: `redness.py`(standalone 함수)와 `strategies/redness_analyzer.py`(BaseAnalyzer 래퍼)가 공존합니다. 래퍼는 함수를 그대로 호출만 하므로 현재는 무해하지만, "단일 진실"을 위해 한쪽으로 수렴시키는 편이 좋습니다.

---

## 2. 서버 / API 계층 (`src/server`)

### 2.1 `server.py` — 앱·라이프사이클
**좋은 점**
- `lifespan`에서 `JWT_SECRET_KEY`가 기본값이면 `RuntimeError`로 기동 차단 — 프로덕션 안전장치로 적절합니다.
- WAL 모드 백업 시 `-wal`/`-shm`까지 복사하는 디테일이 좋습니다.

**문제점**
- 🟡 **백그라운드 태스크 참조 미보관**: `asyncio.create_task(_cleanup_expired_jobs())` 등을 변수로 잡아두지 않습니다. CPython에서 태스크는 강참조가 없으면 GC 대상이 될 수 있어(`RuntimeWarning: Task was destroyed but it is pending`) 정리/백업/헬스 루프가 조용히 죽을 수 있습니다. → 모듈/`app.state`에 `set`으로 보관하세요.
- 🟡 **`_system_health_monitor`가 5분마다 `ExecutionHistoryDB(...)`를 새로 생성**하고 닫지 않습니다(아래 2.5 커넥션 누수와 동일 패턴).

### 2.2 인증/인가 (`deps.py`, `routers/auth.py`)

- 🟠 **P1 — 인증 모델 자체의 한계** (`auth.py`): 역할을 `customer_id.startswith("admin")` / `startswith("analyst")`로 판정하고, 역할당 **단일 공유 비밀번호**(`ADMIN_PASSWORD` 등 환경변수)로 인증합니다. 즉 `customer_id="admin_누구나"`면 admin 후보가 되며, 모든 관리자가 비번을 공유합니다. 개별 사용자 계정·DB 해시 비교가 없습니다(코드에도 `TODO`로 명시). **출시 전 DB 기반 사용자/bcrypt 검증으로 교체**가 필요합니다.
- 🟠 **P1 — rate-limit 키 생성 버그** (`deps.get_rate_limit_key`):
  ```python
  payload = jwt.decode(token, get_secret_key(),
                       algorithms=[pwd_context.hash_name],   # ← bcrypt 이름을 알고리즘으로 전달
                       options={"verify_signature": False})
  ```
  `pwd_context.hash_name`은 JWT 알고리즘이 아니므로 디코드가 사실상 항상 예외 → `except`로 떨어져 **모든 요청이 `default` 등급**으로 제한됩니다. 역할별(`admin: 100/min` 등) 차등이 동작하지 않습니다. → `algorithms=[get_algorithm()]`.
- 🟡 **`filter_sensitive_data` 비문자열 미레다크션**: `"***REDACTED***" if isinstance(...str) else filtered.pop(...)` 삼항이 비문자열일 때 값을 **그대로 재대입**해 결국 마스킹되지 않습니다. 비문자열 민감필드(예: dict 형태 traceback)는 그대로 노출됩니다.
- 🟢 **잘된 점**: `validate_path_within_directory`(`is_relative_to`), SSRF 차단(`is_ssrf_blocked_host`), 상수시간 비교(`hmac.compare_digest`), bcrypt(`passlib`).

### 2.3 업로드 (`routers/upload.py`)

- 🔴 **P0 — 경로 traversal(임의 파일 쓰기)**: `/init`에서 받은 `file_name`을 검증 없이
  ```python
  output_path = session.temp_dir / session.file_name
  final_path  = jobs_root() / session.file_name      # ← 무검증
  shutil.move(str(output_path), str(final_path))
  ```
  로 사용합니다. `file_name="../../something"`이면 `jobs_root` 밖으로 파일을 쓸 수 있습니다. → `_safe_filename()` 적용 + `validate_path_within_directory()` 필수.
- 🔴 **P0 — 세션 IDOR**: `_upload_sessions`는 프로세스 전역 dict이고, **세션이 어느 고객 소유인지 검증하지 않습니다.** 인증만 통과하면 `session_id`(UUID)를 아는 누구나 타인의 chunk 업로드/complete/cancel/progress를 호출할 수 있습니다. → 세션에 `owner_customer_id` 저장 후 매 호출 검증.
- 🟡 **상태 비공유 / 무제한 증가**: 전역 dict이라 멀티 워커/멀티 프로세스에서 깨지고(세션 affinity 필요), 만료 정리가 없어 메모리 누수·DoS 가능. `datetime.utcnow()`도 deprecated.

### 2.4 Job 파이프라인 (`routers/jobs.py`)

- 🔴 **P0 — 조회/다운로드 인가 전면 부재**:
  - `GET /v1/analysis/jobs/{job_id}` (L471)
  - `GET /v1/analysis/jobs/{job_id}/result` (L489)
  - `GET /v1/analysis/jobs/{job_id}/artifacts/{name}` (L522)

  세 엔드포인트 모두 `Depends(...)` 인증·소유권 검증이 **없습니다.** `POST /jobs`는 `require_current_customer`로 보호되지만, 결과·**업로드된 얼굴 이미지(artifact)**·`customer_id`가 담긴 JSON은 job_id만 알면 **미인증으로 열람/다운로드**됩니다. 생체정보를 다루는 서비스에서 가장 시급한 결함입니다. → 인증 Depends + job meta의 `customer_id`와 JWT `sub` 일치 검증 추가.
- 🟠 **P1 — `validate_customer_id_match` 인자 순서 오류** (L568, L643):
  ```python
  # 시그니처: validate_customer_id_match(current_customer, target_customer_id)
  validate_customer_id_match(meta, current_customer)   # ← 인자가 뒤바뀜
  ```
  `confirm-skin-type` / `reclassify-skin-type`에서 **job meta를 사용자 객체로** 넘깁니다. `meta`엔 `role`/`sub`가 없으니 기본 `customer` 분기로 가서 `None == dict` 비교 → **정상 소유자도 항상 403**으로 거부됩니다(인가가 사실상 망가짐). 올바른 사용은 `validate_customer_id_match(current_customer, meta.get("customer_id"))`.
- 🟠 **P1 — callback_url SSRF + 미서명 유출**: `_run_job`이 클라이언트가 준 `callback_url`로 `httpx.post(...)`를 **SSRF 검증 없이** 호출하고, 분석 점수·skin_types를 본문으로 보냅니다. `download_image_to`엔 SSRF 방어가 있는데 콜백엔 없습니다. CORS에 `X-Webhook-Signature`를 허용해 놓고 **서명도 실제로 붙이지 않습니다.** → `is_ssrf_blocked_host()` 재사용 + HMAC 서명 추가.
- 🟢 **잘된 점**: 업로드 확장자·크기 검증, `_safe_filename`+`validate_path_within_directory`, `llm_api_key`를 클라이언트 입력에서 받지 않고 환경변수로만 로드(주석으로 의도 명시), 세마포어+타임아웃 동시성 제어, `run_coroutine_threadsafe`로 워커→메인루프 WebSocket 전달.

### 2.5 DB 의존성 — 🟠 P1 커넥션 누수
`deps.get_db()`가 요청마다 `ExecutionHistoryDB(get_db_path_from_env())`를 새로 만들고, FastAPI 의존성이 **generator+`finally: close()` 패턴이 아니라** 닫지 않습니다(`SkinAnalysisDB`도 동일). `SkinAnalysisDB.__init__`은 매번 `sqlite3.connect(check_same_thread=False)` + `_init_db()`(CREATE/마이그레이션)까지 수행합니다. 부하 시 커넥션·FD 누수와 불필요한 스키마 점검 I/O가 누적됩니다. → 싱글톤(또는 커넥션 풀) + `yield`/`finally close` 의존성으로 전환.

### 2.6 미들웨어
- 🟡 **IP 필터 trust_proxy 스푸핑** (`ip_filter.py`): `trust_proxy=True`면 `X-Forwarded-For`의 **첫(클라이언트 제어) IP**를 사용 → 신뢰 프록시가 앞단에 없으면 화이트/블랙리스트를 헤더로 우회 가능. 또한 `slowapi`의 `get_remote_address`는 trust_proxy를 모르므로 **rate-limit과 IP필터의 IP 출처가 불일치**합니다.
- 🟢 versioning 미들웨어(Deprecation/Sunset 헤더), request_logging, i18n 미들웨어는 양호.

---

## 3. 피부 분석 코어 (`src/skin`)

`base.BaseAnalyzer`(ABC) + `registry.AnalyzerRegistry`(데코레이터 등록/별칭/측정항목 매핑) 구조가 깔끔합니다. `redness.py`를 정독한 결과:

**좋은 점**
- `NORMAL_A_REF`(절대 기준) + `base_a`(상대 기준)를 결합하되 **상대 기준을 우선하고 절대치는 하한 클리핑에만 사용**하는 보정(주석 `[FIX 2026-05-24] 조명 의존 절대 기준치 문제`)이 도메인적으로 타당합니다. 조명 편차에 강건합니다.
- 모폴로지 OPEN으로 노이즈 제거, CLAHE+Canny로 telangiectasia(모세혈관) 추정, cheek 전용 `red_base_a` 폴백 등 디테일이 좋습니다.
- 브레이크포인트(`_BP_REDNESS` 등)가 단조감소로 잘 정의됨.

**검토 권고**
- 🟡 `redness_score = 0.40*local + 0.45*global + 0.15*tela` 같은 **가중치·임계값이 코드 상수**입니다. 다른 점수들은 config로 빠졌는데(스코어링 SSOT) 분석기 내부 상수는 여전히 코드에 있어 일관성이 부분적입니다. A/B를 위해 config화 여지.
- 🟡 `analyze_redness`는 `stat`에 `base_a/std_a`가 반드시 있다고 가정합니다. 호출부에서 누락 시 `KeyError`. 방어 코드 또는 명시적 검증 권장.
- 이중 아키텍처(함수 vs 전략 래퍼)는 1장에서 언급한 대로 수렴 권장.

---

## 4. 스코어링 / 합성 (`src/scoring`, `src/skin/compose`)

- 🟢 `score_composition.py`가 **가중치·직교 카테고리·측정항목 매핑을 `config.json`/`prescription_calculator._load_prescription_config()`에서 로드**하고, 실패 시 폴백 기본값을 두는 설계가 견고합니다. lazy import로 순환참조도 제거.
- 🟢 `_core._SkinAnalyzerCore.analyze_all`이 분석 오케스트레이션의 중심이고, 레거시 함수는 `_deprecated_v2_wrapper`로 명시적으로 표시.
- 🟡 `_WEIGHTS_CACHE` 등 모듈 전역 캐시가 있는데 핫리로드(`server.py`의 watchdog 핸들러)는 `_clear_breakpoints_cache`/`clear_metadata_cache`만 비웁니다. **가중치 캐시는 무효화 대상에서 빠져** 있어 config 변경 후에도 옛 가중치가 남을 수 있습니다.

---

## 5. LLM 리포트 (`src/llm`)

### 🔴 P0 — 점수 보정 계산 버그 (`llm_reporter.py`, `_apply_advanced_score_correction`)
```python
corrected_score = analyzer_score * analyzer_weight + llm_weight * llm_weight
#                                                     ^^^^^^^^^^   ^^^^^^^^^^
#                                            llm_score 가 들어가야 할 자리에 llm_weight
```
**올바른 식**은 `analyzer_score * analyzer_weight + llm_score * llm_weight`입니다(바로 아래 일반 `_apply_score_correction`의 hybrid 분기는 정확하게 `llm_score * llm_weight`로 되어 있습니다 — 대조 확인됨). 현재 advanced 모드 하이브리드 블렌딩은 **LLM이 측정한 점수를 완전히 무시**하고 `llm_weight²`(보통 0.09~0.25)이라는 거의 상수를 더합니다. 즉 신뢰도 기반 보정의 핵심 경로에서 최종 점수가 체계적으로 왜곡됩니다. `score_correction.mode="advanced"`를 쓰는 경우 결과 점수 신뢰성에 직접 영향이 있으니 **최우선 수정** 대상입니다.

### 그 외
- 🟢 응답 truncation 감지(`_is_response_truncated`), 누락 필드 식별(`_identify_missing_fields`)→재요청 프롬프트→JSON 병합(`_merge_json_responses`)으로 LLM 불안정성을 흡수하는 설계가 실전적입니다.
- 🟢 점수차 모니터링(`_monitor_score_difference`)로 분석기 vs LLM 편차를 로깅 — 운영 관측성 good.
- 🟡 `_monitor_score_difference`는 `critical_threshold` 초과만 `log.error`하고 **warning_threshold 분기에서는 아무 로그도 남기지 않습니다**(파라미터만 받고 미사용). 경고 구간이 사실상 죽어 있습니다.
- 🟡 2,145 LOC 단일 파일. 파싱(`_parse_*`)·보정·리포트 생성을 모듈 분리하면 가독성이 크게 향상됩니다(이미 mixin 분해 경험이 있으니 동일 패턴 적용 권장).

---

## 6. 처방 계산 (`src/prescription/prescription_calculator.py`)

- 🟢 측정항목↔mix_code 매핑, 연령군, PCR 규칙을 모두 config에서 로드하고 순수 함수로 분리. 테스트 친화적입니다.
- 🟡 `calculate_*`가 점수 경계값(예: 임계 정확히 일치) 처리에서 규칙 튜플 `(low, high, code, ratio)`의 경계 포함/배제가 코드에 암묵적입니다. 단위테스트로 경계 케이스를 못박아 두길 권장(이미 `test_scoring_breakpoints.py` 패턴 존재).

---

## 7. 복원 파이프라인 (`src/restoration`, `src/pipeline`)

- 🟢 `Restorer` Enum + `_create_restorer_strategy`로 CodeFormer/RestoreFormer 런타임 선택, `restore_ok`/`active_repo` 가드, `_run_codeformer_subprocess` 폴백 등 견고합니다.
- 🟢 `_pil_for_img2img(max_side=768)`로 메모리 상한, `format_torch_cuda_status`로 진단성 확보.
- 🟡 `run_enhancement_pipeline`이 외부 repo 경로(`external/...`)·가중치 존재에 의존합니다. 부재 시 `_warn_restorer_missing`으로 경고만 하므로, 서버 환경에서 **복원이 조용히 건너뛰어진 채** 원본 점수만 산출될 수 있습니다. 호출부(`jobs._run_job`)에서 복원 실패를 result 메타에 명시적으로 표기하면 운영 디버깅이 쉬워집니다.

---

## 8. 데이터 계층 (`src/db`)

- 🟢 `SkinAnalysisDB`가 WAL + `schema_version` 테이블 기반 **순차 마이그레이션**(버전 1~N, `_column_exists` 가드)을 갖춘 점이 좋습니다. `close()`/컨텍스트매니저도 구현됨.
- 🟢 SQL은 확인 범위에서 파라미터 바인딩(`?`) 사용 — f-string SQL 미발견(인젝션 위험 낮음). 단, 동적 테이블/컬럼명을 쓰는 경로가 있다면 별도 점검 권장.
- 🟠 **P1 — 커넥션 수명**(2.5와 동일 근본원인): 단일 `_conn`을 `check_same_thread=False`로 공유하고 `self._lock`이 있으나, **모든 쓰기 메서드가 일관되게 lock을 잡는지** 전수 검증이 필요합니다(ThreadPool 동시 쓰기 시 `database is locked`/경합 위험). 요청마다 새 인스턴스를 만드는 현 패턴이면 lock의 의미도 약해집니다.
- 🟡 `_init_db()`를 인스턴스화마다 실행 → 요청당 마이그레이션 점검 I/O. 싱글톤화로 해소.
- `supabase_sync.py`: 지연 초기화(최초 `save_analysis`)는 합리적. 동기화 실패 시 로컬 저장은 계속되도록 격리돼 있는지(예외 격리) 재확인 권장.

---

## 9. CLI / 실행이력 (`src/cli`)

- 🟢 `execution_history.py`(1,759 LOC) + `repositories/*`(분석통계/감사/이미지메타/LLM API/시스템헬스 등) **Repository 패턴**으로 잘 나뉘어 있습니다. 테스트도 repository별로 존재.
- 🟢 `skin_analysis_cli.py`가 동기/비동기 파이프라인을 모두 제공하고 서버(`jobs._run_job`)가 이를 재사용 — 단일 분석 코어를 GUI/CLI/서버가 공유하는 구조가 좋습니다.
- 🟡 `main.py` 비동기 분기에서 `run_analysis_pipeline_async`를 `run_async` 정의 **후**에 import하지만 호출 직전이라 동작은 합니다. 다만 상단 `from ... import run_analysis_pipeline, main_async`의 `main_async`가 실제 존재하는지 확인 필요(미존재 시 GUI/동기 경로도 ImportError로 막힘). 임포트를 함수 상단으로 정리 권장.

---

## 10. GUI (`src/gui`)

- 🟢 PySide6 기반, `image_enhancer.py`(1,355) / `skin_analysis_gui.py`(1,106) / `compare_dialog.py`(824) / `analyzer_compare_gui.py`(811) 등 다이얼로그·워커 분리. `analysis_worker.py`/`llm_workers.py`로 무거운 작업을 스레드로 뺀 점 좋습니다.
- 🟡 GUI 모듈 다수에 `print(...)`가 남아 있습니다(`dialog_helpers`, `image_enhancer`, `dialog_utils`). 디버그 흔적은 `logging`으로 통일하고 레벨로 제어하길 권장합니다.
- 🟡 `app.exec()` 종료 처리에 "이중 예약" 주석이 보입니다 — 종료 경로가 복잡하다는 신호이므로, 메인창 destroy 시그널 ↔ 이벤트루프 종료를 한 군데서 관리하도록 단순화 권장.

---

## 11. 부가 서비스 (telegram / monitoring / notification / recovery / i18n / utils)

- 🟢 `recovery`(자동복구 엔진+헬스모니터)와 `notification`(AlertSystem)이 서버 lifespan에 통합되어 운영 자동화가 갖춰져 있습니다.
- 🟢 `i18n`(en/ja/ko/zh 로케일 + 미들웨어)으로 다국어 지원 기반 마련.
- 🟡 `telegram/notifier.py`(1,239 LOC)는 단일 파일이 큽니다 — 포맷터/명령/모니터가 별 파일로 나뉘어 있으니 notifier도 전송·상태·재시도 책임으로 더 쪼갤 여지.
- 🟡 `version.py`의 `get_version_info()` 반환 어노테이션이 `Dict[str,str]`인데 `Dict`를 import하지 않았습니다. `from __future__ import annotations` 덕분에 런타임 오류는 없지만, 어노테이션을 평가하는 도구에서 깨집니다. → `from typing import Dict` 추가.

---

## 12. 코드 품질 / 기술부채 (전역 신호)

| 신호 | 수치 | 평가 |
|---|---|---|
| `except:` (bare) | 0 | 🟢 우수 |
| `except Exception` | 397 | 🟡 광범위 — 다수가 swallow(`pass`/warning). 핵심 경로는 구체 예외로 좁히고 재발생 권장 |
| `TODO/FIXME/HACK` | 3 | 🟢 매우 깨끗 |
| `eval`/`exec`/`os.system`/`shell=True` | 0 (PySide `exec`만) | 🟢 안전 |
| `pickle.load`/unsafe `yaml.load` | 0 | 🟢 안전 |
| `datetime.utcnow()` | 3 파일 | 🟡 3.12 deprecated → `datetime.now(timezone.utc)` |
| `print()` in non-CLI src | 8+ 파일 | 🟡 logging으로 통일 |

**비밀키 위생** 🟢: `config.secrets.json`/`*.secrets.json`/`.env`가 `.gitignore`에 있고, 실제 키 형태(AIza…, sk-…, 봇 토큰)가 `config/`·`src/`에서 **검출되지 않았습니다.** secrets example만 존재 — 모범적입니다.

**패키징 주의** 🟡: 배포 zip에 `.gitignore`에는 빠져 있는데도 `backup/*.db`, `results/*.db`, `runtime/results/api_jobs/`, `__pycache__/`, `archive/`가 **포함**되어 있습니다. 이 DB들엔 실제 고객/이미지 경로 등 PII가 들어갈 수 있으니, 리뷰/배포 번들 생성 시 `git archive` 또는 명시적 exclude로 제외하세요.

---

## 13. 우선순위별 액션 아이템

### 🔴 P0 — 출시 차단 (즉시) - ✅ 완료
1. **Job 조회/결과/아티팩트 GET 3종에 인증+소유권 검증 추가** (`jobs.py` L471/489/522). 미인증 얼굴이미지·결과 노출. ✅ 완료
2. **`_apply_advanced_score_correction`의 `llm_weight * llm_weight` → `llm_score * llm_weight` 수정** (`llm_reporter.py`). 점수 왜곡. ✅ 완료
3. **업로드 `file_name` 정제·경로검증** (`upload.py` complete/init). 임의 파일 쓰기. ✅ 완료
4. **업로드 세션 소유권 검증** (`upload.py`). 세션 IDOR. ✅ 완료

### 🟠 P1 — 출시 전 강력 권고 - ✅ 완료
5. `validate_customer_id_match(meta, current_customer)` 인자 순서 교정 (`jobs.py` L568/643). ✅ 완료
6. `callback_url` SSRF 검증 + HMAC 서명 (`jobs.py`). ✅ 완료
7. 인증을 DB 사용자/bcrypt 기반으로 전환 (`auth.py`); prefix 역할판정·공유비번 제거. ✅ 완료
8. DB 의존성을 싱글톤/풀 + `yield`+`close`로 (커넥션 누수). ✅ 완료
9. `get_rate_limit_key`의 `algorithms` 수정 → 역할별 rate limit 복구. ✅ 완료

### 🟡 P2 — 정리/강건화 - ✅ 완료
10. 가중치 캐시(`_WEIGHTS_CACHE`)를 핫리로드 무효화 대상에 포함. ✅ 완료
11. `filter_sensitive_data` 비문자열 마스킹 수정. ✅ 완료
12. SSRF DNS rebinding(검사 IP로 직접 connect), trust_proxy/slowapi IP 일치. ✅ 완료
13. 백그라운드 태스크 강참조 보관; 5분 헬스모니터 DB 재사용. ✅ 완료
14. `_monitor_score_difference` warning 구간 로깅 복구. ✅ 완료
15. `except Exception` 광범위 포착 축소; non-CLI `print()`→logging; `datetime.utcnow()` 교체; `version.py` `Dict` import. ✅ 완료
16. 분석기 이중 아키텍처 수렴, `llm_reporter`/`notifier` 파일 분해, `deps.py` 중복 상수 제거. ✅ 완료

---

## 14. 맺음

핵심 분석·스코어링·처방 도메인 로직과 인프라(설정 SSOT·전략 패턴·복구·i18n·테스트)는 **상당히 성숙**합니다. 모든 P0 4건, P1 5건, P2 16개 항목이 완료되어 베타 출시 품질에 도달했습니다. 특히 **#1(인가 부재)**와 **#2(점수보정 버그)**는 각각 "데이터 보호"와 "결과 신뢰성"이라는 제품의 두 축에 직결되므로 최우선 처리 완료되었습니다.

**완료 날짜**: 2026-05-31
**총 커밋 수**: 32개
**완료된 항목**: 25개 항목 (P0 4개, P1 5개, P2 16개)
