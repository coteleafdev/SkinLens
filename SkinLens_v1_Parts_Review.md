# SkinLens v1.0 — 파트별 상세 코드 리뷰

> **기준:** SkinLense_v1.zip / config_version 3.6  
> **작성:** 2026-05-24  
> **방법:** 전체 소스 직접 정독 + Python 런타임 실행 검증  
> **규모:** 27,414 라인 / 120+ 파일 / 9개 파트

---

## 목차

| 파트 | 도메인 | 핵심 파일 | 라인 |
|------|--------|-----------|------|
| A | CV 분석기 | `src/skin/analyzers/` | ~2,445 |
| B | 점수 합성·변환 | `src/scoring/`, `src/skin/compose/` | ~2,568 |
| C | 복원 파이프라인 | `src/pipeline/`, `src/restoration/` | ~1,384 |
| D | 서버·보안 | `src/server/` | ~2,287 |
| E | LLM 리포터 | `src/llm/` | ~2,620 |
| F | 처방 계층 | `src/prescription/` | ~721 |
| G | DB·영속성 | `src/db/` | ~1,644 |
| H | CLI·텔레그램·유틸 | `src/cli/`, `src/telegram/` | ~7,120 |
| I | 테스트·스크립트·설정 | `tests/`, `scripts/`, `config/` | ~5,009 |

---

## 파트 A — CV 분석기 (Analyzer Layer)

**파일:** `src/skin/analyzers/`, `src/skin/core/`

### A-1. 분석기 구조 — Strategy + Registry 평가

`AnalyzerRegistry` → `_SkinAnalyzerCore` → 6개 도메인 분석기 구조는 교체 가능성이 좋다. `config.json`의 `measurement_analyzers` 섹션으로 18개 측정항목별 분석기 버전을 동적으로 매핑하는 방식은 올바른 설계다.

**문제:** `_SkinAnalyzerCore.analyze_all()`에서 각 도메인마다 동일한 3단계 폴백 패턴이 6회 반복된다. `AnalyzerRegistry` → `get_for_measurement()` → 순수함수 폴백의 구조를 단일 헬퍼로 추출해야 한다.

### A-2. pigmentation.py — 기미 분석

**긍정:** strip-norm L\* + 상대 b\* 임계 조합으로 피부 기저 톤 영향을 줄이는 설계가 적절하다. lentigo NMS 분리(blob 반지름 > 8 제외)로 잡티·주근깨를 물리적으로 분리한다.

**문제 — 형태학적 팽창 15×15 과도:**
```python
melasma_mask = cv2.morphologyEx(melasma_mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
```
300px 폭 얼굴에서 15px = 5% 너비 상당의 브리징이 발생해 인접한 별개 병변이 합쳐진다. `(9, 9)` 이하를 권장한다.

**문제 — pih_score 데드 코드:**
```python
return {
    "melasma_score": ...,
    "freckle_score": ...,
    "pih_score":     ...,  # OUTPUT_KEYS에 없어서 버려짐
}
```
`pih_score`는 계산되지만 `OUTPUT_KEYS`에 없어 결과에 포함되지 않는다. 계산 비용만 발생한다. 포함하거나 제거해야 한다.

**문제 — blob NMS O(n²):**
```python
if any(abs(by - ly) < lr and abs(bx - lx) < lr for ly, lx, lr in lentigo_centers):
```
lentigo blob이 많을수록 freckle 루프가 기하급수적으로 느려진다. `scipy.spatial.cKDTree`로 교체하면 O(n log n)이 된다.

### A-3. redness.py — 홍조 분석

**문제 — NORMAL_A_REF 조명 의존:**
```python
NORMAL_A_REF: float = 134.0   # 정상 동아시아 피부 a*
```
실내 따뜻한 조명(2700K)에서 a\* 채널이 체계적으로 높아지므로 정상 피부도 홍조로 판정될 수 있다. 절대값보다 `stat["base_a"]` 기반 상대 기준을 우선하고 절대값은 하한으로만 사용해야 한다.

**문제 — PIE와 redness 임계 중복:**
- `redness_score`의 local 파트: `a* > max(red_base_a + 1.5σ, LOCAL_A_FLOOR=140)`
- `PIE`: `a* > max(base_a + 1.8σ, PIE_A_FLOOR=142)`

PIE 조건 픽셀 ⊂ redness_local 조건 픽셀이다. `_compose_redness_lesion_scores()`에서 `redness * 0.70 + PIE * 0.30`으로 합산하면 동일 픽셀이 이중 계상된다.

**문제 — telangiectasia 수직 혈관선만 탐지:**
```python
kernel_thin = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 7))
```
수평 혈관선과 대각선 혈관선을 놓친다. 다방향 커널 앙상블이 필요하다.

### A-4. wrinkle_texture.py — 주름·텍스처 분석

**문제 — fine_deep_wrinkle_score와 roughness_score 직교 위반:**

`fine_deep_wrinkle_score`는 전체 얼굴 BoxFilter local_std(`cv2.boxFilter`)를, `roughness_score`는 전체 얼굴 LBP 분산을 측정한다. 두 신호 모두 동일한 물리 현상(표면 불규칙성)을 전체 얼굴 ROI에서 측정하므로 Cov > 0이 명확하다. 합성 레이어에서 `wrinkle_score`(weight 0.130) 안의 `fine_deep × 0.25`와 독립 직교 항목 `roughness_score`(weight 0.080)가 사실상 같은 신호에 총 weight 0.113을 부여한다.

**개선:** `fine_deep_wrinkle_score`의 ROI를 이마 전용으로 제한한다.

**문제 — dead_skin_score, smoothness_score 데드 코드:**
```python
def analyze_texture(...) -> Dict[str, float]:
    return {
        "roughness_score":  ...,
        "dead_skin_score":  ...,   # 직교 파이프라인에 미연결
        "smoothness_score": ...,   # 직교 파이프라인에 미연결
    }
```
두 항목이 계산되지만 `_compose_*()` 레이어에서 사용되지 않는다.

**문제 — analyze_restoration_quality() 혼합 책임:**
복원 품질(noise, detail, color_balance)을 wrinkle_texture.py가 담당한다. 별도 파일로 분리하거나 `restoration_quality.py`로 이동해야 한다.

### A-5. pore.py — 모공 분석

**긍정:** NMS(`_merge_pore_blobs_nms`)로 중복 blob을 제거하고, blob 없을 때 Laplacian 폴백을 제공하는 구조가 안정적이다.

**문제 — Laplacian fallback이 pore_sagging에 64% 기여:**
```python
pore_sagging_score = _clamp(score_otsu * 0.36 + score_lap * 0.64)
```
Laplacian 평균은 피부결 거칠기를 측정하므로 `roughness_score`와 상관이 높다. 저해상도 이미지에서 윤곽 검출이 실패하면 `pore_sagging_score`가 사실상 `roughness_score`를 이중 측정한다.

**문제 — blob 탐지에 동일 threshold를 2회 반복:**
```python
for thr in [0.055, 0.042, 0.030, 0.022]:   # 원본 gray
    blobs = blob_log(inv_plain, ...)
for thr in [0.055, 0.042, 0.030, 0.022]:   # CLAHE 강화 gray
    blobs = blob_log(inv_ce, ...)
```
동일 이미지에 4개 threshold × 2 = 8회 blob_log를 실행한다. 최고 성능 임계를 먼저 시도하고 blob이 없을 때만 낮추는 조기 종료 전략이 필요하다.

### A-6. tone_elasticity.py — 톤·탄력·트러블

**문제 — analyze_elasticity()에서 eye_wrinkle_score 입력 수신:**
```python
def analyze_elasticity(face, regions, eye_wrinkle_score: float, *, ...):
    ...
    eye_elasticity_score = _clamp(eye_wrinkle_score * 0.65 + dark_circle_score * 0.35)
```
`eye_elasticity_score`는 계산되지만 v3 합성(`_compose_elasticity_score`)에서 사용하지 않는다(`jawline_blur * 0.60 + cheek_sagging * 0.40`만 사용). 데드 코드 + 함수 시그니처에 불필요한 의존성을 추가한다.

**문제 — cheek_sagging의 _effective_width가 배경 오염에 취약:**
```python
def _effective_width(row: np.ndarray) -> int:
    nonzero = np.where(row > threshold)[0]
    return int(nonzero[-1] - nonzero[0])
```
배경이나 헤어가 얼굴 경계 안쪽에 있으면 너비가 부정확해진다. 피부 마스크를 적용한 후 유효 픽셀 너비를 계산해야 한다.

**문제 — acne_score 계산에 count_penalty 선형 차감:**
```python
count_penalty = max(0.0, (acne_count - 15) * 0.5)
acne_score = _clamp(0.70 * density_score + 0.30 * intensity_score - count_penalty)
```
면적 밀도와 개수를 동시에 패널티로 적용하면 같은 얼굴에 대해 이미지 해상도에 따라 개수가 달라져 점수가 불안정해진다.

---

## 파트 B — 점수 합성·변환 계층

**파일:** `src/scoring/`, `src/skin/compose/`

### B-1. 가중치 체계 삼원화 — 런타임 검증 확인

```python
# 레이어 A (직교 10개, 종합 점수 표시용)
w_a = _get_weights()   # 합계 1.000

# 레이어 B (보고서 21개, Safety Net·LLM용) — 런타임 실행 확인
from src.scoring._config import get_measurement_weights
w_b = get_measurement_weights()   # 합계 1.199
# noise_score=0.130, acne_score=0.279, detail_score=0.070 포함
```

사용자가 보는 종합 점수(레이어 A, 합계 1.000)와 Safety Net 판단 기준(레이어 B, 합계 1.199)이 다른 가중치 체계를 사용한다. 레이어 B에는 복원품질 항목(noise, detail, color_balance)이 포함되어 있어, 복원 후 노이즈 감소가 Safety Net 합격에 영향을 준다. 이것이 의도인지 설계 문서에 명시되어 있지 않다.

| 체계 | 항목 수 | 합계 | 사용처 |
|------|---------|------|--------|
| 레이어 A 직교 가중치 | 10개 | 1.000 | 표시 종합 점수 |
| 레이어 B 보고서 가중치 | **21개** | **1.199** | Safety Net, LLM 입력 |

### B-2. roughness_score compose 함수 누락

```python
# skin_scoring.py:333 — 9개와 달리 _compose_* 레이어 우회
m3["roughness_score"] = round(m2_raw.get("roughness_score", 50.0), 1)
```

다른 9개 직교 항목은 전용 `_compose_*()` 함수를 거치지만 `roughness_score`만 raw 직접 대입이다. 일관성이 없고, 향후 브레이크포인트 재조정 시 이 항목만 변환 계층 없이 동작한다.

### B-3. skin_type_score 역산 — 런타임 검증 확인

```python
# skin_scoring.py _legacy_to_current()
_dry_r  = m2_raw.get("dry_score", 50.0)   # OUTPUT_KEYS에 없는 키
_oily_r = m2_raw.get("oily_score", 50.0)  # OUTPUT_KEYS에 없는 키
_balance = max(0.0, 100.0 - abs(_dry_r - _oily_r) * 0.5)
# → 항상 abs(50-50)*0.5 = 0 → balance = 100.0 고정
```

`dry_score`, `oily_score`는 `analyze_sebum()` 반환값이지만 `OUTPUT_KEYS`에 없어 `m2_raw`에 존재하지 않는다. 결과적으로 `skin_type_score`가 항상 100.0으로 고정된다.

**수정:** `m2_raw.get("skin_type_score", 50.0)` 직접 사용.

### B-4. _WeightsProxy 스레드 비안전

```python
def _ensure_loaded(self):
    if not self._loaded:               # 두 스레드 동시 진입 가능
        self.update(_get_weights_cached())
        self._loaded = True
```

멀티 워커 환경에서 double-check locking이 없다. 결과는 동일하지만 불필요한 I/O가 중복 실행된다.

```python
# 수정
_WEIGHTS_LOCK = threading.Lock()

def _ensure_loaded(self):
    if not self._loaded:
        with _WEIGHTS_LOCK:
            if not self._loaded:
                self.update(_get_weights_cached())
                self._loaded = True
```

### B-5. _compose_redness_lesion_scores — PIE 이중 계상

```python
return {
    "diffuse_redness": round(_clamp(redness * 0.70 + inflam * 0.30), 1),
    "focal_lesion":    round(_clamp(acne_s  * 0.60 + red_m  * 0.40), 1),
}
```

`inflam`(PIE)은 `a* > max(base+1.8σ, 142)` 이상 픽셀이고 `redness`의 local 파트도 `a* > max(red_base+1.5σ, 140)` 이상을 포함한다. PIE 조건은 redness_local 조건의 진부분집합이므로 `diffuse_redness`에 이미 반영된 PIE를 추가로 `× 0.30` 합산한다. 동일 픽셀 이중 계상이다.

**개선:** `diffuse_redness = redness_score` (PIE 제거), `focal_lesion`에만 PIE 포함.

### B-6. 2-pass 변환 오차 누적

```
analyze_all() → 18개 서브점수 (내부 0~100)
 → _apply_measurements_display_10_90() → 표시 10~90
 → _score_from_display_10_90_adjusted() 역변환 → 내부 값 복원
 → _compose_*() → 10개 직교 항목
 → _apply_measurements_display_10_90() → 표시 10~90
```

`actual_ranges`가 정확하지 않은 항목에서 역변환 시 오차가 발생한다. `dullness_score`처럼 raw 보존이 필요한 항목만 별도 처리하는 현재 방식은 ad-hoc이며 확장성이 없다.

---

## 파트 C — 복원 파이프라인

**파일:** `src/pipeline/pipeline_core.py`, `src/restoration/`

### C-1. BaseRestorer 추상 메서드 미구현 — 런타임 검증 확인

```python
# 직접 실행 결과:
>>> CodeFormerRestorer({'repo': '/tmp'})
TypeError: Can't instantiate abstract class CodeFormerRestorer
without an implementation for abstract methods 'get_name', 'get_version'
```

`BaseRestorer`는 `get_name()`, `get_version()`을 `@abstractmethod`로 선언했으나 두 구현체는 `@property name`, `@property version`으로 구현했다. Python은 이를 서로 다른 메서드로 인식한다.

추가로 `BaseRestorer`에 `get_config()` 메서드가 없는데 두 구현체에서 `self.get_config("repo", "")` 등으로 호출한다.

`BaseLLM`도 동일한 패턴: `get_name()`, `get_version()`이 `@abstractmethod`인데 `GeminiLLM`은 `@property name`, `@property version`으로 구현했다.

**수정:**
```python
# base.py
def get_config(self, key: str, default=None):
    return self.config.get(key, default)

# 구현체 — @property 제거
def get_name(self) -> str:
    return "codeformer_v1"

def get_version(self) -> str:
    return "1.0.0"
```

### C-2. Strategy Pattern이 실제 파이프라인에서 미사용

`src/restoration/strategies/`에 `CodeFormerRestorer`, `RestoreFormerRestorer` 클래스가 있고 `RestorerRegistry`에 등록되어 있다. 그러나 실제 서버 파이프라인(`pipeline_core.py`, `skin_analysis_cli.py`)은 이 클래스들을 전혀 사용하지 않고 `run_codeformer()`, `run_restoreformer()` 순수 함수를 직접 호출한다. 아키텍처 데모 상태로 실사용이 없다.

### C-3. 매 요청마다 subprocess cold-start

```python
subprocess.run([sys.executable, "-u", str(script), ...], ...)
```

매 요청마다 새 Python 프로세스가 시작되고 PyTorch 모델이 cold-load된다. 초회 20~60초, 이후 5~15초 소요. `get_shared_executor(max_workers=1)`로 동시 처리를 1개로 제한하므로 처리량의 구조적 한계가 있다.

### C-4. PipelineSettings.codeformer_fidelity 기본값 = 1.0

```python
codeformer_fidelity: float = 1.0  # 0=보정 최대 / 1=원본 충실
```

`1.0`은 CodeFormer 보정을 완전히 비활성화한다는 의미다. 피부 분석 디테일 복원 목적에 반하는 기본값이며 선택 이유가 코드·config 어디에도 설명되어 있지 않다.

### C-5. _PipelineMode 분기에 elif 누락

```python
if mode is _PipelineMode.ANALYZE_ONLY:
    ...   # return 없음
if mode is _PipelineMode.RESTORE_ONLY:   # elif가 아닌 if
    ...
```

현재는 후속 조건이 False여서 안전하지만, `elif`로 명시해야 의도가 분명해진다.

### C-6. 전처리 캐시 디렉토리 크기 무제한

```python
cache_dir = image_path.parent / ".cache" / "preprocess"
```

총 크기 상한·LRU 정책이 없어 장기 운영 시 디스크가 소진된다.

---

## 파트 D — 서버·보안

**파일:** `src/server/`

### D-1. WebSocket 진행률 — asyncio 이벤트 루프 충돌

```python
def _run_job_sync(job_id: str) -> None:
    ...
    asyncio.run(_run_job(job_id))   # 새 이벤트 루프 생성
```

`asyncio.run()`은 새 이벤트 루프를 생성한다. `_run_job()` 안의 `await websocket.send_json()`은 FastAPI 메인 루프의 WebSocket 객체에 bind되어 있어 다른 루프에서 await하면 IO가 실패한다. **WebSocket 진행률 전달이 동작하지 않는다.**

**수정:**
```python
_main_loop: Optional[asyncio.AbstractEventLoop] = None

@asynccontextmanager
async def lifespan(app):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    yield

def _run_job_sync(job_id: str) -> None:
    ...
    future = asyncio.run_coroutine_threadsafe(_run_job(job_id), _main_loop)
    future.result(timeout=TIMEOUT)
```

### D-2. SSRF — 도메인명 차단 미흡 — 런타임 검증 확인

```python
def is_ssrf_blocked_host(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback ...
    except ValueError:
        return False   # IP가 아니면 무조건 통과
```

직접 실행 결과:
```
127.0.0.1           → blocked=True  ✓
localhost           → blocked=False ✗  (내부망 접근 가능)
metadata.google.internal → blocked=False ✗  (GCP 메타데이터)
169.254.169.254     → blocked=True  ✓
```

**수정:**
```python
_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal",
                                  "metadata.aws.internal"})

def is_ssrf_blocked_host(host: str) -> bool:
    if host.lower() in _BLOCKED_HOSTNAMES:
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        try:
            resolved = socket.gethostbyname(host)
            return is_ssrf_blocked_host(resolved)
        except socket.gaierror:
            return False
```

### D-3. path traversal 방어에 str.startswith() — 4곳

```python
if not str(resolved_save_path).startswith(str(resolved_jdir)):
```

`/tmp/jobs/abc` vs `/tmp/jobs/abcdef` 같은 우연한 prefix 일치로 경로 탈출이 가능하다.

**수정 (Python 3.9+):**
```python
if not resolved_save_path.is_relative_to(resolved_jdir):
    raise HTTPException(status_code=400, detail="invalid filename")
```

### D-4. 모든 고객이 단일 패스워드 공유

```python
CUSTOMER_PASSWORD = os.environ.get("CUSTOMER_PASSWORD", "")
if not _verify_pw(password, CUSTOMER_PASSWORD):
    raise HTTPException(401)
```

어떤 `customer_id`든 동일한 `CUSTOMER_PASSWORD`로 로그인 가능하다. 고객 데이터 격리가 없는 상태다. JWT `sub` 클레임에 customer_id를 포함해 자기 데이터만 접근 가능하도록 검증이 필요하다.

### D-5. ThreadPoolExecutor 중복 선언

```python
# deps.py 모듈 레벨 — 4개 idle 스레드, 실제 미사용
executor = ThreadPoolExecutor(max_workers=4)

# get_shared_executor() — 실제 job 처리에 사용
_shared_executor = ThreadPoolExecutor(max_workers=1)
```

미사용 `executor`가 idle 스레드 4개를 점유한다.

### D-6. get_current_customer Optional 반환 — 미인증 허용

```python
async def get_current_customer(...) -> Optional[Dict[str, Any]]:
    if not authorization:
        return None  # 미인증 시 None
```

`create_job()`이 `Optional[Dict]`로 받으므로 Authorization 헤더 없이 job 생성이 가능하다. Rate Limit(3/분)만 적용된 상태다.

### D-7. BackgroundTasks 기본값 직접 인스턴스화

```python
async def export_my_data(
    ...
    background_tasks: BackgroundTasks = BackgroundTasks(),  # 잘못된 패턴
):
```

FastAPI에서 `BackgroundTasks`는 직접 인스턴스화하면 응답 후 cleanup 체인에 포함되지 않는다. `Depends()`로 주입받아야 한다.

---

## 파트 E — LLM 리포터

**파일:** `src/llm/`

### E-1. GeminiLLM의 BaseLLM 인터페이스 불일치

`BaseLLM`이 `get_name()`, `get_version()`을 `@abstractmethod`로 선언했으나 `GeminiLLM`은 `@property name`, `@property version`으로 구현했다. `CodeFormerRestorer`와 동일한 패턴으로, Python이 이를 별개로 인식해 인스턴스화 시 `TypeError`가 발생한다.

### E-2. provider 추론 로직 취약

```python
base_name = model_name.split('/')[-1]    # "models/gemini-2.5-pro" → "gemini-2.5-pro"
provider = base_name.split('-')[0]       # "gemini-2.5-pro" → "gemini"
# "gpt-4o" → "gpt" (create_provider("gpt") → NotImplementedError)
# "claude-3-5-sonnet" → "claude" (미구현)
```

모델명 규칙이 변경되거나 다른 provider를 추가하면 즉시 실패한다.

**수정:** config에 `"default_provider": "gemini"` 명시 또는 모델→provider 매핑 테이블 사용.

### E-3. 재시도 대상이 역전되어 있음

```python
for attempt in range(self.max_retries + 1):
    try:
        response_text = self._call_llm(...)
        ...
    except (json.JSONDecodeError, ValueError) as e:   # JSON 파싱 실패만 재시도
        time.sleep(self.retry_delay)
```

JSON 파싱 실패만 재시도 대상이며, HTTP 429(할당량 초과)·503(서버 오류)처럼 실제로 재시도가 필요한 에러는 재시도 없이 실패한다.

### E-4. generate_report()에서 CV 분석 재실행

```python
def generate_report(self, image_path, ...):
    analyzer = SkinAnalyzer()
    analysis_result = analyzer.analyze_all(str(image_path))  # CV 파이프라인 재실행
```

서버에서는 `generate_report_from_measurements()`를 직접 호출하므로 중복이 없으나, `generate_report()`를 독립 호출하면 이중 분석이 발생한다.

### E-5. LlmSkinReporter 초기화 시 모델 목록 API 호출

```python
available_models = self._provider.list_models()   # 초기화마다 API 네트워크 요청
```

`compare_dialog.py`의 LLM 버튼을 누를 때마다 새 `LlmSkinReporter` 인스턴스를 생성하므로, 버튼 클릭마다 API에 모델 목록을 요청한다. 모듈 수준 캐싱이 필요하다.

---

## 파트 F — 처방(Prescription) 계층

**파일:** `src/prescription/prescription_calculator.py`

### F-1. PCR 처방 기능 완전 불동작 — 런타임 검증 확인

```python
# 직접 실행 결과:
calculate_pcr_prescription_for_category("total", -5)
→ None   # rv가 어떤 값이어도 항상 None

# 이유: config 규칙 (rv_min=-10, rv_max=0) 과 코드 조건 역전
if rv_max < rv <= rv_min:   # 0 < -5 <= -10 → 절대 True가 될 수 없음
```

config.json의 규칙 포맷은 `rv_min ≤ rv < rv_max` 의미인데, 코드 조건은 `rv_max < rv <= rv_min`으로 음수 범위를 역방향으로 비교한다.

**수정:**
```python
def calculate_pcr_prescription_for_category(category, rv):
    rules = _get_pcr_prescription_rules().get(category, [])
    for rv_min, rv_max, mix_code, percentage in rules:
        if rv_min <= rv < rv_max:   # ← config 포맷에 맞는 조건
            return (mix_code, percentage) if mix_code else None
    return None
```

### F-2. create_prescription에서 믹스 코드 중복 합산 문제

```python
total_mix_percentage = (
    sum(assessment_recipe.values()) +
    sum(pcr_recipe.values()) +    # 동일 믹스 코드가 있으면 이중 계상
    sum(skin_recipe.values()) +
    sum(care_recipe.values())
)
base_percentage = max(0, 100 - total_mix_percentage)
```

`assessment_recipe`와 `pcr_recipe`가 동일한 믹스 코드를 반환하면 `base_percentage`가 잘못 계산된다. 믹스 코드별로 합산해야 한다.

### F-3. PCR av_total 하드코딩 100

```python
av_total = 100   # 전체 평균을 기준(100)으로 설정 (하드코딩)
```

이미 `average_total`을 로드했는데 활용하지 않는다. 집단 평균이 기준값(100)과 다른 경우 rV 계산이 틀린다.

### F-4. _calculate_skin_type_mix, _calculate_concern_mix 미구현

```python
def _calculate_skin_type_mix(skin_type: str) -> Dict[str, float]:
    return {}   # 향후 구현 예정

def _calculate_concern_mix(concerns: List[str]) -> Dict[str, float]:
    return {}   # 향후 구현 예정
```

처방의 1단계 설문 연동이 완전히 미구현 상태다. API 문서에 이 사실이 명시되어 있지 않다.

### F-5. AGE_GROUP_MAPPING 모듈 수준 하드코딩

```python
AGE_GROUP_MAPPING: List[Tuple[int, int, int]] = [
    (0, 9, 0), (10, 19, 10), ...
]
```

다른 설정들이 config.json으로 이전된 것과 달리 이 부분만 남아 있다.

---

## 파트 G — DB·영속성

**파일:** `src/db/`

### G-1. SkinAnalysisDB 스레드 안전성 — 올바르게 구현됨

```python
with self._lock:
    cursor = self._conn.cursor()
    cursor.execute(...)
```

주요 메서드들이 `threading.Lock()`으로 보호되고 WAL 모드가 적용되어 있다. 올바른 구현이다.

### G-2. 스키마 마이그레이션이 예외 무시 방식

```python
try:
    cursor.execute("ALTER TABLE analyses ADD COLUMN input_json TEXT")
except sqlite3.OperationalError:
    pass   # 이미 존재 또는 다른 오류도 무시
```

`sqlite3.OperationalError`는 "column already exists" 외에도 DB 잠금, 읽기 전용, 디스크 부족 등 다양한 원인으로 발생한다. 실제 오류가 조용히 무시될 수 있다.

**수정:**
```python
cols = [row[1] for row in cursor.execute("PRAGMA table_info(analyses)")]
if "input_json" not in cols:
    cursor.execute("ALTER TABLE analyses ADD COLUMN input_json TEXT")
```

### G-3. Supabase 동기화 실패 재시도 없음

```python
try:
    self._syncer.sync(...)
except Exception as e:
    log.warning("Supabase 동기화 실패: %s", e)   # 조용히 실패
```

실패한 레코드를 retry 큐나 `failed_sync` 테이블에 기록해 이후 재시도하는 메커니즘이 없다.

### G-4. _init_db에서 샘플 데이터 자동 로드

```python
cursor.execute("SELECT COUNT(*) FROM products")
product_count = cursor.fetchone()[0]
if product_count == 0:
    self._load_sample_products(cursor)
```

운영 DB에서 테이블이 비어있으면 자동으로 샘플 데이터가 삽입된다. 테스트·개발용과 운영용 DB를 구분하는 환경변수나 플래그가 없다.

---

## 파트 H — CLI·텔레그램·유틸

**파일:** `src/cli/`, `src/telegram/`, `src/utils/`

### H-1. execution_history.py — 1,770라인 God Object 잔존

`repositories/` 하위 9개 파일로 분리가 진행됐지만 `execution_history.py` 자체는 여전히 1,770라인이다. `get_db_path_from_env()`가 이 파일에 있어 `src/server/`, `src/db/`, `src/cli/` 등 8곳 이상이 이 단일 파일을 import한다. 이 함수는 `src/utils/` 또는 `src/db/`로 이전해야 한다.

### H-2. run_analysis_pipeline_async — 올바른 async 패턴

```python
async def run_analysis_pipeline_async(..., executor=None):
    loop = asyncio.get_running_loop()
    ...
    result = await loop.run_in_executor(executor, _run_wrapper)
    return result
```

`loop.run_in_executor()`를 사용해 blocking 작업을 스레드 풀로 위임하는 올바른 패턴이다. `_run_job_sync`에서 `asyncio.run()`으로 감싸면서 이 함수 자체의 async 구현이 무력화된다는 점이 D-1의 근본 원인이다.

### H-3. TelegramNotifier — MarkdownV2 truncation 위험

```python
if len(text) > _TG_MAX_LEN:
    text = text[:_TG_MAX_LEN - len(_TG_TRUNCATE_SUFFIX)] + _TG_TRUNCATE_SUFFIX
```

MarkdownV2 포맷 블록(`*bold*`, `_italic_`, `` `code` ``) 중간에서 잘리면 파싱 오류가 발생한다. 잘라내기 전에 열린 마크업 태그를 닫는 처리가 필요하다.

### H-4. utils/config.py — 역방향 의존

```python
# src/utils/config.py
def load_config():
    from src.scoring._config import _load_scoring_config   # utils → scoring 역방향
    return _load_scoring_config()
```

`utils`는 leaf 레이어여야 하는데 `scoring` 레이어에 의존한다. `_load_scoring_config()`를 `src/config/` 공통 레이어로 이전하는 것이 적절하다.

---

## 파트 I — 테스트·스크립트·설정

**파일:** `tests/`, `scripts/`, `config/`

### I-1. 가짜 테스트 패턴 — 3개 파일 전수 확인

**test_security.py** — src.* import 0개, 실제 함수 미호출:
```python
def test_internal_ip_detection(self):
    internal_ips = ["127.0.0.1", "localhost", "192.168.1.1"]
    for ip in internal_ips:
        assert ip in ["127.0.0.1", "localhost", "192.168.1.1"]
        # is_ssrf_blocked_host() 한 번도 호출 안 함
        # localhost가 실제로 차단되는지 검증하지 않음
```

**test_integration.py** — 일부 가짜:
```python
def test_workflow_sequence(self):
    workflow_steps = ["upload", "analyze", "result"]
    for step in workflow_steps:
        assert step in workflow_steps   # 항상 True
```

**test_error_handling.py** — src.* import 0개:
```python
def test_timeout_error_raised(self):
    with pytest.raises(TimeoutError):
        raise TimeoutError("Connection timeout")   # 직접 raise, 실제 코드 미호출
```

### I-2. PCR 처방 테스트 없음 → F-1 버그 미감지

`calculate_pcr_prescription_for_category()`, `calculate_pcr_recipe()`에 대한 테스트가 전혀 없어 PCR 처방 기능이 항상 `None`을 반환하는 버그가 감지되지 않았다.

### I-3. BaseRestorer/BaseLLM 인스턴스화 테스트 없음 → C-1·E-1 버그 미감지

`test_restoration_llm_registry.py`가 클래스를 레지스트리에서 가져오지만 인스턴스화를 시도하지 않는다.
```python
cf_class = RestorerRegistry.get("codeformer_v1")
print(f"CodeFormer: {cf_class.name}")   # property 객체 출력, TypeError 미발생
```

### I-4. test_analyzers.py — 제로 픽셀 이미지만 테스트

```python
def make_dummy_face(): return np.zeros((100, 100, 3), dtype=np.uint8)
```

검은 픽셀 이미지만 사용해 측정 정확도를 전혀 검증하지 않는다. 반환 키 존재와 0~100 범위만 확인한다.

### I-5. llm_prompt_template.md가 설정 소스 역할

```
docs/llm_prompt_template.md
  ├─ LLM 프롬프트 텍스트
  ├─ <!-- MEASUREMENT_WEIGHTS_START --> 가중치 설정
  ├─ <!-- ACTUAL_RANGES_START --> 범위 설정
  └─ <!-- SCORE_MAPPING_START --> 점수 매핑 설정
```

`config_parser.py`가 Markdown HTML 주석 태그를 파싱해 설정을 추출한다. 프롬프트 텍스트 수정 시 주석 구조를 실수로 손상시킬 수 있다. 설정은 `config.json`으로 이전이 바람직하다.

### I-6. pyproject.toml Python 3.8 지원 선언 — 코드와 불일치

```toml
requires-python = ">=3.8"
```

그러나 코드에 `list[str]` (Python 3.9+) 타입힌트가 12곳 이상 사용되어 있어 Python 3.8에서 런타임 오류가 발생한다.

### I-7. pytorch-lightning==1.0.8 — torch 2.x 충돌 위험

```
torch>=2.0.0
pytorch-lightning==1.0.8   # 2020년 릴리스, torch 1.x 시대
```

`pytorch-lightning` 2.x 이상으로 업그레이드가 필요하다.

---

## 종합 우선순위 요약

### 🔴 P0 — 즉시 수정 (버그·보안·기능 불동작)

| # | 파트 | 이슈 | 영향 |
|---|------|------|------|
| 1 | F | **PCR 처방 조건 역전** → 항상 None 반환 | PCR 처방 기능 불동작 |
| 2 | C/E | **BaseRestorer·BaseLLM 추상 메서드 미구현** → TypeError | Strategy 클래스 인스턴스화 불가 |
| 3 | B | **skin_type_score 항상 100 고정** | 처방·분석 정확도 오류 |
| 4 | D | **asyncio.run() in ThreadPool** → WebSocket broken | 진행률 기능 불동작 |
| 5 | D | **SSRF — localhost·도메인명 차단 안 됨** | 내부망 접근 가능 |
| 6 | D | **str.startswith() path traversal** (4곳) | 경로 탈출 가능 |
| 7 | D | **모든 고객 공유 패스워드** | 데이터 격리 없음 |

### 🟠 P1 — 단기 수정 (정확도·기능)

| # | 파트 | 이슈 |
|---|------|------|
| 8 | A | pih_score, dead_skin_score 등 데드 코드 6개 |
| 9 | A | redness NORMAL_A_REF 조명 의존 |
| 10 | A | fine_deep ↔ roughness 직교 위반 |
| 11 | B | roughness_score compose 함수 누락 |
| 12 | B | PIE 이중 계상 (diffuse_redness + focal_lesion) |
| 13 | E | provider 모델명 파싱 추론 취약 |
| 14 | F | create_prescription 믹스 코드 중복 합산 |
| 15 | D | get_current_customer Optional 반환 → 미인증 허용 |

### 🟡 P2 — 중기 개선 (구조·성능·테스트)

| # | 파트 | 이슈 |
|---|------|------|
| 16 | I | test_security.py 가짜 테스트 → 실제 함수 테스트로 교체 |
| 17 | I | test_integration.py, test_error_handling.py 가짜 테스트 교체 |
| 18 | I | PCR·BaseRestorer 인스턴스화 테스트 추가 |
| 19 | C | Strategy Pattern을 실제 파이프라인에 연결 |
| 20 | G | 스키마 마이그레이션 PRAGMA table_info 사전 확인 |
| 21 | D | ThreadPoolExecutor 중복 선언 제거 |
| 22 | B | _WeightsProxy double-check locking 추가 |
| 23 | A | blob NMS O(n²) → cKDTree O(n log n) |
| 24 | H | execution_history.py get_db_path_from_env 이전 |

### 🔵 P3 — 장기 개선 (아키텍처)

| # | 파트 | 이슈 |
|---|------|------|
| 25 | B | 가중치 체계 삼원화 통합·문서화 |
| 26 | I | llm_prompt_template.md 설정을 config.json으로 이전 |
| 27 | C | subprocess cold-start → in-process 모델 상주 |
| 28 | I | pyproject.toml Python 3.8 지원 정정 또는 코드 호환화 |
| 29 | I | pytorch-lightning==1.0.8 → 2.x 업그레이드 |
| 30 | H | utils → scoring 역방향 의존 해소 |
| 31 | 전체 | deprecated alias 77개 DeprecationWarning + 제거 계획 |

---

*직접 런타임 실행 검증: P0 1~6번 전체, 가중치 로드 경로, SSRF 도메인명, pih_score OUTPUT_KEYS*  
*SkinLense_v1.zip 기준 / 2026-05-24 / Claude Sonnet 4.6*
