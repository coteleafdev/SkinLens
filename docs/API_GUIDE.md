# Backend API Guide (SkinLens v1.0)

이 문서는 현재 프로젝트를 **백엔드 서버 환경**에서 구동하면서, 외부 시스템(웹/모바일/파트너 시스템)과 **HTTP API로 정보를 주고받는 방법**을 설계/구현할 때 참고할 가이드입니다.

현재 코드베이스는 `skin_analysis_cli.py` 기반의 **CLI 실행 흐름**이 중심이며, 로컬 파일 저장소 기반의 FastAPI 서버 구현(`server.py`)도 함께 포함되어 있습니다.

---

## 1) 시스템 개요

- **입력**
  - 얼굴 이미지 1장 또는 다중 이미지(파일 업로드 또는 URL)
  - 파이프라인 옵션: `do_restore`, `score_safety_net`, `analyzer_score_tune`
  - (선택) 고객/세션 식별자: `customer_id`, `gender`, `age`, `race`, `region`
  - (선택) 설문 응답: `survey` (피부 고민사항, 피부 타입 등)
  - (선택) 클라이언트 메타: `client_meta` (앱 버전, 플랫폼, 디바이스 정보 등)
  - (선택) LLM 보고서: `llm_report`, `llm_api_key`, `llm_scores`

- **처리**
  - 복원(RestorerRegistry, CodeFormer/RestoreFormer++, 전처리/후처리 훅)
  - 피부 분석(AnalyzerRegistry, 6개 분석기, 18개 측정항목, 직교 신호 분해, 가중치 체계)
  - 처방 계산(PrescriptionCalculator, AGE_GROUP_MAPPING, PCR 규칙, 믹스 코드)
  - (선택) 맞춤형 화장품 매칭(ProductRepository, 설문 및 점수 기반)
  - (선택) LLM AI 소견 생성 (성분 정보 포함)
  - 실행 이력 SQLite 저장

- **출력**
  - 분석 결과 JSON (URL 기반)
  - 메타데이터 (analyzers, restorer, llm 정보)
  - 입력 JSON (survey + client_meta)
  - 처방 정보 (mix_codes)
  - 입력 이미지 (URL 기반)
  - 복원 이미지 (URL 기반)
  - (선택) 맞춤형 화장품 추천 (product_recommendations)

---

## 2) 권장 API 형태

### 비동기(Async) Job API (권장)
- 장점: 모바일/웹/배치 등 다양한 클라이언트에 안정적
- 단점: Job 저장소(DB/Redis/파일) 및 상태 관리 필요

이 문서에서는 **Async Job API를 기준**으로 설명합니다.

---

## 3) 공통 규칙

### 3.1 Content-Type
- 파일 업로드: `multipart/form-data`
- JSON 요청: `application/json`

### 3.2 시간/ID
- 서버는 각 요청에 대해 `job_id`(UUID)를 발급합니다.
- 분석 시각은 `timestamp`(ISO 8601) 형식입니다.

### 3.3 파이프라인 옵션
- `do_restore`: 복원 수행 여부 (기본: true)
- `score_safety_net`: 점수 안전장치 (기본: true)
- `analyzer_score_tune`: 복원 후 점수 자동 튜닝 (기본: true)
- `llm_scores`: LLM에 내부 측정 점수 제공 (기본: false)

---

## 4) 엔드포인트 설계

### 4.1 Health Check
`GET /health`

**Response 200**
```json
{
  "status": "ok",
  "service": "skin-analysis",
  "version": "3.1"
}
```

---

### 4.2 분석 Job 생성 (Async)
`POST /v3/analysis/jobs`

**Rate Limit**
- 분석 엔드포인트는 **3회/분**으로 제한됩니다 (GPU 집약적 작업 보호)

**Request (multipart/form-data)**
- `image`: (file, optional) 분석할 이미지 파일 업로드
- `image_url`: (string, optional) 분석할 이미지 공개 URL (http/https)
- `images[]`: (file, optional) 다중 이미지 업로드 (권장 방식)
- `angles[]`: (string, optional) 각도 지정 (`front`/`left45`/`right45`)
- `do_restore`: (bool, optional) 복원 수행 (기본: true)
- `score_safety_net`: (bool, optional) 점수 안전장치 (기본: true)
- `analyzer_score_tune`: (bool, optional) 복원 후 점수 자동 튜닝 (기본: true)
- `include_base64`: (bool, optional) base64 인코딩 포함 (기본: false)
- `base_url`: (string, optional) 베이스 URL
- `llm_report`: (bool, optional) LLM 소견 생성 (기본: false)
- `llm_api_key`: (string, optional) LLM API 키
- `llm_scores`: (bool, optional) LLM에 내부 측정 점수 제공 (기본: false)
- `use_multi_view_analysis`: (bool, optional) 다중 뷰 분석 사용 (기본: true)
- `survey`: (string, optional) 고객 설문 JSON (피부 고민사항, 피부 타입 등)
  ```json
  {
    "skin_concerns": ["여드름", "홍조", "색소침착"],
    "skin_types": ["oily", "combination", "sensitive"]
  }
  ```
- `client_meta`: (string, optional) 클라이언트 메타데이터 JSON
- `customer_id`: (string, optional) 외부 고객 식별자
- `gender`: (string, optional) 성별
- `age`: (int, optional) 연령
- `race`: (string, optional) 인종
- `region`: (string, optional) 지역
- `debug`: (bool, optional) 디버그 모드

**규칙**
- `image`와 `image_url` 중 **정확히 하나만** 제공해야 합니다.
- 다중 이미지 업로드 시 `images[]`와 `angles[]`를 사용합니다.
- `use_multi_view_analysis=true`인 경우 좌/우 45° 이미지도 분석하여 통합 결과를 반환합니다.

**예시**

파일 업로드 (단일 이미지):
```bash
curl -X POST "http://localhost:8000/v3/analysis/jobs" \
  -F "image=@./images/01-F-1.jpg" \
  -F "do_restore=true" \
  -F "customer_id=test01"
```

다중 이미지 업로드 (권장):
```bash
curl -X POST "http://localhost:8000/v3/analysis/jobs" \
  -F "images[]=@./images/front.jpg" \
  -F "angles[]=front" \
  -F "images[]=@./images/left45.jpg" \
  -F "angles[]=left45" \
  -F "images[]=@./images/right45.jpg" \
  -F "angles[]=right45" \
  -F "do_restore=true" \
  -F "use_multi_view_analysis=true" \
  -F "customer_id=test01"
```

URL 입력:
```bash
curl -X POST "http://localhost:8000/v3/analysis/jobs" \
  -F "image_url=https://example.com/sample.jpg" \
  -F "do_restore=true" \
  -F "customer_id=test01"
```

설문 포함 (맞춤형 화장품 추천):
```bash
curl -X POST "http://localhost:8000/v3/analysis/jobs" \
  -F "image=@./images/01-F-1.jpg" \
  -F "do_restore=true" \
  -F "llm_report=true" \
  -F "survey='{\"skin_concerns\": [\"여드름\", \"홍조\"], \"skin_types\": [\"combination\"]}'" \
  -F "customer_id=test01"
```

**Response 202**
```json
{
  "job_id": "7c45d7d5-2f9e-4e64-bc2a-8d2b1d3b2f91",
  "status": "queued",
  "created_at": "2026-01-28T12:00:00Z"
}
```

**서버 동작**
- 업로드 파일을 서버 로컬에 저장
- 백그라운드 워커로 `run_analysis_pipeline_async()` 실행
- RestorerRegistry에서 복원 백엔드 선택 및 전처리/후처리 훅 호출
- 다중 이미지 업로드 시 복원 병렬 처리 (ThreadPoolExecutor)
- AnalyzerRegistry에서 분석기 선택 및 18개 측정항목 분석
- `use_multi_view_analysis=true`인 경우 좌/우 45° 이미지도 분석하여 통합 결과 반환
  - 각도별 특화 항목 가중치 적용 (측면 특화: 모공 처짐, 눈가 주름, 턱선 흐림, 볼 처짐)
  - 정면 특화 항목 가중치 적용 (기미, 홍조, 피부 톤, 칙칙함, 톤 불균일, 인중 주름)
  - 최대값 기반 통합 (여드름, 여드름 후 색소)
  - 각도별 개별 결과 포함 (`angle_results`)
- PrescriptionCalculator로 처방전 생성 (AGE_GROUP_MAPPING, PCR 규칙, 믹스 코드)
- 설문(survey)가 제공되면 ProductRepository에서 맞춤형 화장품 매칭 수행
- LLM 소견 생성 시 성분 정보 포함 (제품 매칭 성공 시)
- 완료 후 결과 파일을 artifacts 디렉토리에 저장
- 실행 이력을 SQLite 데이터베이스에 자동 저장

---

### 4.3 Job 상태 조회
`GET /v3/analysis/jobs/{job_id}`

**Response 200**
```json
{
  "job_id": "...",
  "status": "running",
  "created_at": "...",
  "started_at": "...",
  "finished_at": null,
  "error": null,
  "artifacts": {}
}
```

**status 값**
- `queued` | `running` | `succeeded` | `failed`

---

### 4.4 Job 결과(JSON) 조회
`GET /v3/analysis/jobs/{job_id}/result`

**Response 200**
```json
{
  "job_id": "...",
  "status": "succeeded",
  "timestamp": "2026-01-28T12:01:02.345Z",
  "analysis": {
    "input_image": "/v3/analysis/jobs/.../artifacts/input.jpg",
    "input_image_url": "/v3/analysis/jobs/.../artifacts/input.jpg",
    "restored_image": "/v3/analysis/jobs/.../artifacts/00_restored.png",
    "restored_image_url": "/v3/analysis/jobs/.../artifacts/00_restored.png",
    "execution_time": {
      "total_sec": 45.3,
      "restore_sec": 15.2,
      "analysis_sec": 28.5,
      "llm_sec": 1.6
    },
    "timestamp": "2026-01-28T12:01:02.345Z",
    "timestamp_local": "2026-01-28T21:01:02+09:00",
    "settings": {
      "restorer": "codeformer_v1",
      "score_safety_net": true,
      "analyzer_score_tune": true,
      "device": "cuda"
    },
    "image_metadata": {
      "input": {
        "width": 1024,
        "height": 1365,
        "format": "JPEG",
        "size_bytes": 2048576
      },
      "restored": {
        "width": 1024,
        "height": 1365,
        "format": "PNG",
        "size_bytes": 3145728
      }
    },
    "pipeline_status": {
      "restore": "succeeded",
      "analysis": "succeeded",
      "llm": "succeeded"
    },
    "version": {
      "config_version": "3.6",
      "analyzer_version": "v3.0",
      "restorer_version": "codeformer_v1"
    },
    "environment": {
      "device": "cuda",
      "python_version": "3.12.4"
    },
    "score_adjustment": {
      "safety_net_applied": true,
      "original_score": 65.0,
      "adjusted_score": 72.0,
      "boost_delta": 7.0
    },
    "error": null,
    "metadata": {
      "analyzers": {
        "pigmentation": "pigmentation_v1",
        "redness": "redness_v1",
        "pore": "pore_v1",
        "wrinkle": "wrinkle_v1",
        "tone_elasticity": "tone_elasticity_v1",
        "acne": "acne_v1"
      },
      "restorer": {
        "name": "codeformer_v1",
        "config": {
          "repo": null,
          "fidelity": 1.0,
          "upscale": 1,
          "bg_upsampler": "none"
        }
      },
      "llm": {
        "name": "gemini_v1",
        "model": "models/gemini-2.5-pro",
        "config": {
          "timeout_sec": 300,
          "max_retries": 3
        }
      }
    },
    "input_json": {
      "survey": {
        "consent_agreed": true,
        "gender": "female",
        "age_group": "30s",
        "skin_types": ["combination", "sensitive"],
        "skin_concerns": ["acne", "red_marks"]
      },
      "client_meta": {
        "app_version": "1.0.3",
        "platform": "ios",
        "os_version": "17.4"
      }
    },
    "analysis_result": {
      "overall_score": 78.2,
      "perceived_age": 28,
      "llm_model": "models/gemini-2.5-flash-image",
      "llm_stats": {
        "input_tokens": 1000,
        "output_tokens": 500,
        "total_tokens": 1500,
        "estimated_cost_usd": 0.0015
      },
      "measurements_v18": {
        "pigmentation_score": 65,
        "redness_score": 72,
        ...
      }
    },
    "prescription": {
      "mix_codes": {
        "M01": {"base": 10.0, "items": ["나이아신아마이드", "비타민 C"]},
        "M02": {"base": 15.0, "items": ["레티놀", "펩타이드"]}
      },
      "recommendation": "측정된 피부 상태를 기반으로 맞춤형 처방전을 생성했습니다."
    },
    "llm_analysis": {
      "recommendation": "현재 피부 상태를 개선하고 유지하기 위해 다음과 같은 관리를 권장합니다...",
      "product_recommendations": {
        "matched_products": [
          {
            "product_id": "P001",
            "product_name": "CÔTELEAF 트러블 케어 세럼",
            "category": "트러블 케어",
            "key_ingredients": ["나이아신아마이드", "살리실산", "티트리 오일"],
            "efficacy": "여드름 억제, 모공 관리, 피부 진정",
            "match_score": 0.95,
            "match_reason": "설문의 피부 고민사항(여드름)과 측정 점수(acne_score: 50) 기반 매칭"
          }
        ],
        "recommendation_summary": "측정된 피부 상태와 설문 응답을 기반으로 당사 맞춤형 화장품을 추천합니다."
      }
    }
  },
  "artifacts": {
    "results.json": "/v3/analysis/jobs/.../artifacts/results.json",
    "input_image": "/v3/analysis/jobs/.../artifacts/input.jpg",
    "restored_image": "/v3/analysis/jobs/.../artifacts/00_restored.png"
  },
  "error": null
}
```

---

### 4.5 결과 파일(artifact) 다운로드
`GET /v3/analysis/jobs/{job_id}/artifacts/{name}`

- `{name}` 예시
  - `results.json`
  - `input.jpg`
  - `00_restored.png`

**Response 200**
- `Content-Type`: 파일에 맞게 설정
- `Content-Disposition: attachment; filename="{name}"`

---

### 4.6 피부 타입 확인
`POST /v3/analysis/jobs/{job_id}/confirm-skin-type`

**Request (multipart/form-data)**
- `skin_types[]`: (string, required) 확인할 피부 타입 목록 (oily/dry/combination/sensitive)

**Response 200**
```json
{
  "job_id": "7c45d7d5-2f9e-4e64-bc2a-8d2b1d3b2f91",
  "confirmed_skin_types": ["oily", "sensitive"],
  "previous_detected_types": ["oily"],
  "skin_type_source": "manual"
}
```

### 4.7 피부 타입 재감지
`POST /v3/analysis/jobs/{job_id}/reclassify-skin-type`

**Request (multipart/form-data)**
- `force_reclassification`: (bool, optional) 강제 재감지 (기본: true)

**Response 200**
```json
{
  "job_id": "7c45d7d5-2f9e-4e64-bc2a-8d2b1d3b2f91",
  "new_skin_types": ["oily", "sensitive"],
  "previous_skin_types": ["oily"],
  "confidence": 0.82
}
```

---

## 5) 에러 설계

### 5.1 HTTP Status 가이드
- `400`: 입력 오류 (image/image_url 파라미터 오류)
- `404`: Job/리소스 없음
- `409`: Job이 아직 완료되지 않음
- `500`: 서버 내부 오류

---

## 6) 결과 스키마 가이드

프로젝트 결과 구조는 `skin_analysis_cli.py`의 `run_analysis_pipeline_async()` 반환값을 기반으로 합니다.

**주요 필드:**

### 기본 필드
- `input_image`: 입력 이미지 로컬 경로
- `input_image_url`: 입력 이미지 다운로드 URL
- `restored_image`: 복원 이미지 로컬 경로
- `restored_image_url`: 복원 이미지 다운로드 URL
- `output_dir`: 출력 디렉토리

### 1. 실행 시간 정보
- `execution_time.total_sec`: 전체 실행 시간 (초)
- `execution_time.restore_sec`: 복원 시간 (초)
- `execution_time.analysis_sec`: 분석 시간 (초)
- `execution_time.llm_sec`: LLM 소견 생성 시간 (초)

### 2. 타임스탬프
- `timestamp`: 분석 시각 (UTC, ISO 8601)
- `timestamp_local`: 분석 시각 (로컬, ISO 8601)

### 3. 사용된 설정 정보
- `settings.restorer`: 사용된 복원 엔진 (restoreformer/codeformer)
- `settings.score_safety_net`: 점수 안전장치 적용 여부
- `settings.analyzer_score_tune`: 분석 점수 튜닝 적용 여부
- `settings.device`: 사용된 디바이스 (cuda/cpu/auto)

### 4. LLM API 통계
- `analysis_result.llm_model`: 사용된 LLM 모델명
- `analysis_result.llm_stats.input_tokens`: 입력 토큰 수
- `analysis_result.llm_stats.output_tokens`: 출력 토큰 수
- `analysis_result.llm_stats.total_tokens`: 전체 토큰 수
- `analysis_result.llm_stats.estimated_cost_usd`: 추정 비용 (USD)

### 5. 이미지 메타데이터
- `image_metadata.input.width`: 입력 이미지 너비
- `image_metadata.input.height`: 입력 이미지 높이
- `image_metadata.input.format`: 입력 이미지 형식
- `image_metadata.input.size_bytes`: 입력 이미지 크기 (바이트)
- `image_metadata.restored.*`: 복원 이미지 메타데이터

### 6. 파이프라인 상태
- `pipeline_status.restore`: 복원 단계 상태 (succeeded/failed)
- `pipeline_status.analysis`: 분석 단계 상태 (succeeded/failed)
- `pipeline_status.llm`: LLM 단계 상태 (succeeded/skipped/failed)

### 7. 버전 정보
- `version.config_version`: config.json 버전
- `version.analyzer_version`: 분석기 버전
- `version.restorer_version`: 복원기 버전

### 8. 환경 정보
- `environment.device`: 사용된 디바이스
- `environment.python_version`: Python 버전
- `environment.cpu_cores`: CPU 코어 수 (리소스 모니터링 시)
- `environment.memory_peak_mb`: 최대 메모리 사용량 (MB, 리소스 모니터링 시)

### 9. 점수 조정 정보
- `score_adjustment.safety_net_applied`: 안전장치 적용 여부
- `score_adjustment.original_score`: 원본 점수
- `score_adjustment.adjusted_score`: 조정된 점수
- `score_adjustment.boost_delta`: 점수 증가분

### 10. 에러 정보
- `error`: 에러 정보 (실패 시 상세, 정상 시 null)

### 11. 맞춤형 화장품 추천 (product_recommendations)
- `llm_analysis.product_recommendations`: 맞춤형 화장품 추천 정보 (제품 매칭 성공 시)
  - `matched_products`: 매칭된 제품 목록 (상위 3개)
    - `product_id`: 제품 ID
    - `product_name`: 제품명
    - `category`: 카테고리
    - `key_ingredients`: 주요 성분 목록
    - `efficacy`: 효능 설명
    - `match_score`: 매칭 점수 (0-1)
    - `match_reason`: 매칭 사유
  - `recommendation_summary`: 추천 요약

**매칭 로직:**
- 고민사항 매칭: +0.5 점 (설문 skin_concerns 기반)
- 피부 타입 매칭: +0.3 점 (설문 skin_types 기반)
- 측정 점수 기반 매칭: +0.2 점 (점수 < 60인 항목)
- match_score = (고민사항 점수 + 피부 타입 점수 + 점수 기반 점수) / 최대 가능 점수

**조건부 동작:**
- ProductTable에 제품 데이터가 없으면 빈 객체 `{}`
- 설문(survey)가 없으면 빈 객체 `{}`
- 제품 매칭 실패 시 빈 객체 `{}`

### 기존 필드
- `pipeline_mode`: 파이프라인 모드 정보
- `restoration_stats`: 복원 통계 (시간, 노트)
- `customer_info`: 고객 정보
- `lateral_images`: 측면 이미지 목록
- `analysis_result`: 분석 결과 (overall_score, perceived_age, measurements_v17, llm_report)

### 12. 다중 뷰 분석 결과 (multi_view_detail)
- `multi_view_detail`: 다중 뷰 분석 통합 상세 정보 (다중 이미지 업로드 시)
  - 각 측정항목별 통합 방법 및 가중치 정보
  - `method`: 통합 방법 (`weighted_average`, `max`, `front_only`)
  - `front`: 정면 이미지 점수
  - `left`: 좌측 45° 이미지 점수
  - `right`: 우측 45° 이미지 점수
  - `merged`: 통합된 점수

### 13. 각도별 개별 결과 (angle_results)
- `angle_results`: 각도별 개별 분석 결과 (다중 이미지 업로드 시)
  - `front`: 정면 이미지 전체 분석 결과
  - `left`: 좌측 45° 이미지 전체 분석 결과
  - `right`: 우측 45° 이미지 전체 분석 결과

**각도별 가중치:**
- 측면 특화 (front: 20%, left: 40%, right: 40%): 모공 처짐, 눈가 주름, 턱선 흐림, 볼 처짐
- 정면 특화 (front: 70%, left: 15%, right: 15%): 기미, 홍조, 피부 톤, 칙칙함, 톤 불균일, 인중 주름
- 최대값 기반: 여드름, 여드름 후 색소
- 기본값 (33% each): 기타 항목

### 14. 피부 타입 자동 감지 (skin_type_detection)
- `skin_type_detection`: 피부 타입 자동 감지 결과
  - `skin_types`: 감지된 피부 타입 목록 (예: ["oily"], ["oily", "sensitive"])
  - `primary_type`: 주요 피부 타입 (oily/dry/combination/sensitive/unknown)
  - `secondary_type`: 2차 피부 타입 (다중 타입인 경우)
  - `confidence`: 감지 신뢰도 (0 ~ 1)
  - `all_scores`: 각 타입별 점수
  - `features`: 감지에 사용된 특성 값
  - `zone_analysis`: T존/U존 분석 결과

**피부 타입:**
- `oily`: 지성 (유분 과다, 모공 큼, 광택 있음)
- `dry`: 건성 (건조, 각질, 모공 작음)
- `combination`: 복합성 (T존 지성, U존 건성/중성)
- `sensitive`: 민감성 (홍조, 염증, 자극 민감)
- `unknown`: 알 수 없음 (신뢰도 낮음)

---

## 7) 서버 구현 시 고려사항

### 7.1 config.json 설정

서버 운용에 필요한 모든 설정은 `config/config.json` 파일에서 관리됩니다. 환경 변수로 오버라이드 가능합니다.

#### server 섹션
```json
{
  "server": {
    "url": "http://localhost:8000",
    "host": "0.0.0.0",
    "port": 8000,
    "max_upload_bytes": 20971520,
    "max_concurrent_jobs": 2,
    "allowed_origins": "*",
    "allowed_extensions": [".jpg", ".jpeg", ".png", ".webp"]
  }
}
```

- `url`: 서버 기본 URL
- `host`: 바인딩 호스트 (기본: 0.0.0.0)
- `port`: 서버 포트 (기본: 8000)
- `max_upload_bytes`: 최대 업로드 파일 크기 (바이트, 기본: 20MB)
- `max_concurrent_jobs`: 최대 동시 Job 수 (기본: 2)
- `allowed_origins`: CORS 허용 오리진 (콤마로 구분, 기본: *)
- `allowed_extensions`: 허용 파일 확장자 목록

**환경 변수 오버라이드:**
- `SERVER_URL`: 서버 URL
- `SKIN_API_MAX_UPLOAD_BYTES`: 최대 업로드 크기
- `ALLOWED_ORIGINS`: CORS 허용 오리진
- `SKIN_API_MAX_CONCURRENT`: 최대 동시 Job 수

#### database 섹션
```json
{
  "database": {
    "sqlite": {
      "path": "execution_history.db"
    },
    "supabase": {
      "enabled": true,
      "url": null,
      "key": null,
      "bucket": "skin-images"
    }
  }
}
```

##### SQLite 설정 (로컬 DB)
- `sqlite.path`: 로컬 SQLite DB 경로 (기본: execution_history.db)
  - 실행 이력, 로그, 통계, 감사 로그 등 저장
  - 환경 변수 `EXECUTION_HISTORY_DB`로 오버라이드 가능

**추가 SQLite DB:**
- `skin_analysis.db`: 피부 분석 결과 저장 (results 디렉토리)
  - `analyses` 테이블: 분석 기록 저장
  - `products` 테이블: 맞춤형 화장품 성분 정보 저장
    - 제품 ID, 제품명, 카테고리, 주요 성분, 효능
    - 타겟 피부 타입, 타겟 고민사항

**환경 변수 오버라이드:**
- `EXECUTION_HISTORY_DB`: SQLite DB 파일 경로

##### Supabase 설정 (클라우드 DB/Storage)
- `supabase.enabled`: Supabase 동기화 활성화 여부 (기본: true)
- `supabase.url`: Supabase 프로젝트 URL
- `supabase.key`: Supabase API 키
- `supabase.bucket`: 스토리지 버킷명 (기본: skin-images)

**동작 방식:**
- `enabled=true`이면 로컬 SQLite 저장 후 Supabase에도 자동 동기화
- 이미지 파일은 Supabase Storage에 업로드
- 분석 결과는 Supabase DB에 저장

**환경 변수 오버라이드:**
- `SUPABASE_URL`: Supabase 프로젝트 URL
- `SUPABASE_KEY`: Supabase API 키

#### jwt 섹션
```json
{
  "jwt": {
    "secret_key_env": "JWT_SECRET_KEY",
    "algorithm": "HS256",
    "access_token_expire_minutes": 30
  }
}
```

- `secret_key_env`: JWT 시크릿 키 환경 변수명 (기본: JWT_SECRET_KEY)
- `algorithm`: JWT 알고리즘 (기본: HS256)
- `access_token_expire_minutes`: 액세스 토큰 만료 시간 (분, 기본: 30)

**환경 변수 오버라이드:**
- `JWT_SECRET_KEY`: JWT 시크릿 키

#### environment 섹션
```json
{
  "environment": "development"
}
```

- `environment`: 실행 환경 (development, staging, production)

#### llm 섹션
```json
{
  "llm": {
    "default_model": "models/gemini-2.5-flash-image",
    "api_key_env": "GEMINI_API_KEY",
    "timeout_sec": 300,
    "max_retries": 3
  }
}
```

- `default_model`: 기본 LLM 모델
- `api_key_env`: LLM API 키 환경 변수명
- `timeout_sec`: LLM API 타임아웃 (초)
- `max_retries`: 최대 재시도 횟수

**환경 변수 오버라이드:**
- `GEMINI_API_KEY`: Gemini API 키

#### timeouts 섹션
```json
{
  "timeouts": {
    "job_semaphore_timeout_sec": 300,
    "llm_timeout_sec": 300,
    "analysis_timeout_sec": 600,
    "restore_timeout_sec": 300
  }
}
```

- `job_semaphore_timeout_sec`: Job 세마포어 타임아웃 (초)
- `llm_timeout_sec`: LLM API 타임아웃 (초)
- `analysis_timeout_sec`: 분석 타임아웃 (초)
- `restore_timeout_sec`: 복원 타임아웃 (초)

#### logging 섹션
```json
{
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s [%(levelname)s] %(name)s:%(pathname)s:%(lineno)d: %(message)s",
    "datefmt": "%H:%M:%S",
    "db_logging": {
      "enabled": true,
      "retention_days": 7
    }
  }
}
```

- `level`: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
- `format`: 로그 형식 (전체 파일 경로와 라인번호 포함)
- `db_logging.enabled`: DB 로깅 활성화 여부
- `db_logging.retention_days`: 로그 보관 기간 (일)

### 7.2 환경변수
- `EXECUTION_HISTORY_DB`: 실행 이력 데이터베이스 경로 (기본: execution_history.db)
- `SKIN_API_JOBS_DIR`: Job 저장 루트 디렉토리 (기본: ./results/api_jobs)
- `SKIN_API_MAX_WORKERS`: 백그라운드 워커 스레드 수 (기본: 2)
- `SKIN_API_URL_TIMEOUT`: URL 다운로드 타임아웃 (초, 기본: 10)
- `SKIN_API_URL_MAX_BYTES`: URL 다운로드 최대 크기 (바이트, 기본: 10MB)

### 7.3 동시성/리소스
- 복원 및 SD 처리는 GPU 사용량이 높을 수 있어 워커 수 제한 필요
- 피부 분석은 CPU 사용량이 높을 수 있음

### 7.4 파일 저장소
- 개발/단일 서버: 로컬 디스크 저장 가능
- 운영/수평 확장: S3/GCS 같은 오브젝트 스토리지 권장

### 7.5 CORS
- 브라우저 클라이언트가 직접 호출한다면 CORS 허용 필요
- 현재는 모든 origin 허용 (`allow_origins=["*"]`)

### 7.6 보안
- 업로드 파일 확장자/콘텐츠 타입 검증
- 파일 크기 제한
- 개인정보/생체정보(얼굴 이미지) 취급 정책 수립

---

## 8) 최소 연동 예시 (클라이언트)

### 8.1 Job 생성
```bash
curl -X POST "http://localhost:8000/v3/analysis/jobs" \
  -F "image=@./images/01-F-1.jpg" \
  -F "do_restore=true" \
  -F "customer_id=test01"
```

### 8.2 상태 조회
```bash
curl "http://localhost:8000/v3/analysis/jobs/<job_id>"
```

### 8.3 결과 다운로드
```bash
curl -L -o results.json "http://localhost:8000/v3/analysis/jobs/<job_id>/artifacts/results.json"
curl -L -o restored.png "http://localhost:8000/v3/analysis/jobs/<job_id>/artifacts/00_restored.png"
```

---

## 9) FastAPI 서버 실행 가이드

현재 저장소에는 **비동기 Job API**를 제공하는 FastAPI 서버 파일이 포함되어 있습니다.

- 서버 파일: `server.py`
- OpenAPI(Swagger): 서버 실행 후
  - `http://localhost:8000/docs`
  - `http://localhost:8000/redoc`

### 9.1 필수 패키지

```bash
pip install fastapi uvicorn python-multipart
```

### 9.2 실행

```bash
python server.py
# 또는
uvicorn server:app --host 0.0.0.0 --port 8000
```

### 9.3 Job 결과 저장 위치

기본 저장 경로:
- `./results/api_jobs/<job_id>/artifacts/`

실행 이력 데이터베이스:
- `execution_history.db` (프로젝트 루트)

---

## 10) 외부 배포 시 준비/고려사항

### 10.1 런타임/프로세스 구성
- WAS 권장: `gunicorn` + `uvicorn.workers.UvicornWorker` 조합
- reverse proxy 권장: Nginx/ALB 등으로 TLS 종료, 업로드 크기 제한

### 10.2 Secrets/API Key 관리
- Gemini API Key는 환경변수 또는 클라우드 Secret Manager 사용
- 키 로테이션/만료/권한 최소화 원칙 적용

### 10.3 스토리지/결과물 보관
- 기본은 로컬 디스크에 저장
- 운영/수평 확장 환경에서는 오브젝트 스토리지(S3/GCS)로 이전 고려
- 실행 이력 데이터베이스 주기적 정리 필요

### 10.4 보안
- `image_url` 사용 시 SSRF 방지 (내부망 접근 차단)
- 외부 배포 시 토큰 기반 인증(JWT/API Key) 권장
- 얼굴 이미지는 민감정보로 취급: 저장/전송 암호화, 접근 통제

---

## 11) Node 백엔드 연동 가이드

### 11.1 권장 아키텍처(비동기 Job)
- Node 백엔드 → Skin Analysis API
  - `POST /v3/analysis/jobs`로 이미지 업로드
  - `GET /v3/analysis/jobs/{job_id}`로 상태 확인(폴링)
  - 완료 시 `GET /v3/analysis/jobs/{job_id}/result`로 결과 수집

### 11.2 Node에서 Job 생성 예시

```js
import fs from "fs";
import axios from "axios";
import FormData from "form-data";

export async function createSkinAnalysisJob({
  apiBaseUrl,
  imagePath,
  doRestore = true,
  customerId,
}) {
  const form = new FormData();
  form.append("image", fs.createReadStream(imagePath));
  form.append("do_restore", String(doRestore));
  if (customerId) form.append("customer_id", customerId);

  const res = await axios.post(`${apiBaseUrl}/v3/analysis/jobs`, form, {
    headers: form.getHeaders(),
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
    timeout: 30_000,
  });
  return res.data; // { job_id, status, created_at }
}
```

### 11.3 결과 수집 및 DB 저장

완료된 Job에 대해서는 아래 API로 결과 JSON을 가져와 DB에 저장합니다.

- `GET /v3/analysis/jobs/{job_id}/result`

DB 저장 권장:
- `job_id`
- `status` (`succeeded|failed`)
- `timestamp`
- `error` (실패 시)
- `analysis` (JSON 컬럼으로 저장)
- `artifacts` (다운로드 URL 맵)

---

## 12) 로그 다운로드 API

### 12.1 로그 조회 (JSON)
`GET /v3/logs`

**Query Parameters**
- `level`: (string, optional) 필터링할 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
- `limit`: (int, optional) 조회할 레코드 수 (기본 100, 최대 1000)
- `hours`: (int, optional) 최근 N시간 내의 로그만 조회

**Response 200**
```json
{
  "logs": [
    {
      "id": 1,
      "timestamp": "2026-05-15T12:34:56.789",
      "level": "INFO",
      "logger_name": "src.scoring.skin_scoring",
      "message": "점수 설정 로드 완료",
      "module": "skin_scoring",
      "function": "get_measurement_weights",
      "line_number": 256
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 전체 로그 (100개)
curl http://localhost:8000/v3/logs

# ERROR 레벨만 (50개)
curl http://localhost:8000/v3/logs?level=ERROR&limit=50

# 최근 6시간 로그 (200개)
curl http://localhost:8000/v3/logs?hours=6&limit=200
```

### 12.2 로그 파일 다운로드
`GET /v3/logs/download`

**Query Parameters**
- `level`: (string, optional) 필터링할 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
- `hours`: (int, optional) 최근 N시간 내의 로그만 다운로드
- `format`: (string, optional) 출력 형식 (csv, json, 기본 csv)

**Response 200**
- CSV 파일 (`text/csv`) 또는 JSON 파일 (`application/json`)
- 파일명: `logs_YYYYMMDD_HHMMSS.{format}`

**Response 404**
- 조건에 맞는 로그가 없는 경우

**예시**
```bash
# 전체 로그 CSV 다운로드
curl http://localhost:8000/v3/logs/download?format=csv -o logs.csv

# ERROR 레벨만 CSV 다운로드
curl http://localhost:8000/v3/logs/download?level=ERROR&format=csv -o errors.csv

# 최근 24시간 로그 JSON 다운로드
curl http://localhost:8000/v3/logs/download?hours=24&format=json -o recent.json
```

### 12.3 로그 DB 설정

로그 DB 저장은 `config/config.json`에서 설정합니다:

```json
{
  "logging": {
    "db_logging": {
      "enabled": true,
      "retention_days": 7
    }
  }
}
```

- `enabled`: DB 로깅 활성화/비활성화
- `retention_days`: 보관 기간 (일). 로그 저장 시 자동으로 오래된 로그 삭제 (롤링 방식)

### 12.4 환경 변수

- `EXECUTION_HISTORY_DB`: 로그 DB 파일 경로 (기본: `execution_history.db`)

---

## 13) 통계 조회 API

### 13.1 분석 통계 조회
`GET /v3/stats/analysis`

**Query Parameters**
- `days`: 조회할 기간 (일, 기본 7)
- `customer_id`: 고객 ID (선택)

**Response 200**
```json
{
  "stats": [
    {
      "id": 1,
      "date": "2026-05-15",
      "customer_id": "user123",
      "total_analyses": 10,
      "successful_analyses": 9,
      "failed_analyses": 1,
      "avg_score_original": 65.5,
      "avg_score_restored": 72.3,
      "avg_execution_time_sec": 45.2
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 최근 7일 통계
curl http://localhost:8000/v3/stats/analysis?days=7

# 특정 고객 통계
curl http://localhost:8000/v3/stats/analysis?customer_id=user123&days=30
```

### 13.2 모델 성능 조회
`GET /v3/stats/model-performance`

**Query Parameters**
- `model_type`: 모델 유형 필터 (예: skin_analyzer, restoreformer)
- `hours`: 최근 N시간 (선택)
- `limit`: 조회할 레코드 수 (기본 100)

**Response 200**
```json
{
  "performance": [
    {
      "id": 1,
      "timestamp": "2026-05-15T12:34:56.789",
      "model_type": "skin_analyzer",
      "execution_time_ms": 1500,
      "memory_peak_mb": 512,
      "cpu_percent_avg": 45.2,
      "success": true,
      "error_type": null,
      "input_resolution": "1024x1365",
      "output_quality_score": null
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 최근 24시간 성능
curl http://localhost:8000/v3/stats/model-performance?hours=24

# 특정 모델 성능
curl http://localhost:8000/v3/stats/model-performance?model_type=skin_analyzer
```

### 13.3 점수 추이 조회
`GET /v3/stats/score-trends`

**Query Parameters**
- `customer_id`: 고객 ID (선택)
- `days`: 조회할 기간 (일, 기본 30)
- `limit`: 조회할 레코드 수 (기본 100)

**Response 200**
```json
{
  "trends": [
    {
      "id": 1,
      "customer_id": "user123",
      "timestamp": "2026-05-15T12:34:56.789",
      "overall_score": 72.0,
      "melasma_score": 60,
      "redness_score": 70,
      "wrinkle_score": 65,
      "pore_score": 75,
      "improvement_delta": 7.0,
      "analysis_count": 5
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 특정 고객 점수 추이
curl http://localhost:8000/v3/stats/score-trends?customer_id=user123

# 최근 90일 추이
curl http://localhost:8000/v3/stats/score-trends?days=90
```

### 13.4 Gemini API 통계 조회
`GET /v3/stats/gemini-api`

**Query Parameters**
- `customer_id`: 고객 ID (선택)
- `days`: 조회할 기간 (일, 기본 30)

**Response 200**
```json
{
  "stats": [
    {
      "id": 1,
      "timestamp": "2026-05-15T12:34:56.789",
      "customer_id": "user123",
      "request_type": "single",
      "input_tokens": 1000,
      "output_tokens": 500,
      "total_tokens": 1500,
      "execution_time_sec": 3.2,
      "success": true,
      "error_message": null,
      "estimated_cost_usd": 0.0005
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 최근 7일 Gemini API 통계
curl http://localhost:8000/v3/stats/gemini-api?days=7

# 특정 고객 API 사용량
curl http://localhost:8000/v3/stats/gemini-api?customer_id=user123
```

### 13.5 이미지 메타데이터 조회
`GET /v3/stats/image-metadata`

**Query Parameters**
- `analysis_id`: 분석 ID (선택)
- `image_type`: 이미지 유형 (original, restored)

**Response 200**
```json
{
  "metadata": [
    {
      "id": 1,
      "analysis_id": 100,
      "image_type": "original",
      "file_size_bytes": 2048576,
      "width": 1024,
      "height": 1365,
      "format": "JPEG",
      "exif_date_taken": "2026-05-15T10:00:00",
      "exif_device": "iPhone 14",
      "exif_location": null
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 원본 이미지 메타데이터
curl http://localhost:8000/v3/stats/image-metadata?image_type=original

# 특정 분석 메타데이터
curl http://localhost:8000/v3/stats/image-metadata?analysis_id=100
```

### 13.6 에러 조회
`GET /v3/stats/errors`

**Query Parameters**
- `resolved`: 해결 여부 (true/false)
- `severity`: 심각도 (critical, high, medium, low)
- `days`: 조회할 기간 (일, 기본 30)
- `limit`: 조회할 레코드 수 (기본 100)

**Response 200**
```json
{
  "errors": [
    {
      "id": 1,
      "timestamp": "2026-05-15T12:34:56.789",
      "error_type": "ValueError",
      "error_message": "Invalid image format",
      "module": "pipeline_core",
      "function": "load_image",
      "line_number": 256,
      "stack_trace": null,
      "customer_id": "user123",
      "image_path": "/path/to/image.jpg",
      "pipeline_mode": "cli",
      "severity": "medium",
      "resolved": 0,
      "resolved_at": null,
      "resolution_note": null
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 미해결 에러 조회
curl http://localhost:8000/v3/stats/errors?resolved=false

# 심각한 에러 조회
curl http://localhost:8000/v3/stats/errors?severity=critical

# 최근 7일 에러
curl http://localhost:8000/v3/stats/errors?days=7
```

### 13.7 에러 해결 표시
`POST /v3/stats/errors/{error_id}/resolve`

**Request Body**
```json
{
  "resolution_note": "Fixed by updating image format validation"
}
```

**Response 200**
```json
{
  "message": "Error resolved successfully",
  "error_id": 1
}
```

**예시**
```bash
curl -X POST http://localhost:8000/v3/stats/errors/1/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution_note": "Fixed by updating validation"}'
```

### 13.8 시스템 헬스 조회
`GET /v3/stats/system-health`

**Query Parameters**
- `hours`: 조회할 기간 (시간, 기본 24)
- `limit`: 조회할 레코드 수 (기본 100)

**Response 200**
```json
{
  "health": [
    {
      "id": 1,
      "timestamp": "2026-05-15T12:34:56.789",
      "cpu_usage_percent": 45.2,
      "memory_usage_percent": 62.1,
      "disk_usage_percent": 78.5,
      "disk_free_gb": 45.2,
      "gpu_usage_percent": null,
      "gpu_memory_usage_percent": null,
      "network_status": "ok",
      "api_latency_ms": 150,
      "active_jobs": 2,
      "queue_size": 0
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 최근 24시간 시스템 헬스
curl http://localhost:8000/v3/stats/system-health

# 최근 1시간 헬스
curl http://localhost:8000/v3/stats/system-health?hours=1
```

### 13.9 전체 통계 요약
`GET /v3/stats/summary`

**Response 200**
```json
{
  "today_analyses": 15,
  "recent_errors": 3,
  "recent_errors_critical": 0,
  "system_health": {
    "cpu_usage_percent": 45.2,
    "memory_usage_percent": 62.1,
    "active_jobs": 2
  },
  "gemini_api_calls_today": 20,
  "gemini_cost_today": 0.01
}
```

**예시**
```bash
curl http://localhost:8000/v3/stats/summary
```

---

## 14) 인증 및 보안

### 14.1 개요
모든 통계 조회 API는 JWT 토큰 기반 인증을 지원합니다. 인증된 사용자만 자신의 데이터에 접근할 수 있으며, 관리자는 모든 데이터에 접근할 수 있습니다.

### 14.2 역할 (Roles)

| 역할 | 권한 | 설명 |
|------|------|------|
| customer | read_own | 자신의 데이터만 읽기 가능 |
| admin | read_all, write, delete | 모든 데이터 접근 및 수정/삭제 가능 |
| analyst | read_all | 모든 데이터 읽기 가능 |

### 14.3 로그인
`POST /v3/auth/login`

**Request Body (Form)**
- `customer_id`: 고객 ID
- `password`: 비밀번호 (개발용: customer_id 접두사로 역할 결정)

**Response 200**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "customer_id": "user123",
  "role": "customer",
  "expires_in": 1800
}
```

**역할 결정 규칙 (개발용)**
- `admin*`로 시작하면 `admin` 역할
- `analyst*`로 시작하면 `analyst` 역할
- 그 외: `customer` 역할

**예시**
```bash
# 일반 고객 로그인
curl -X POST http://localhost:8000/v3/auth/login \
  -F "customer_id=user123" \
  -F "password=password123"

# 관리자 로그인
curl -X POST http://localhost:8000/v3/auth/login \
  -F "customer_id=admin001" \
  -F "password=admin123"
```

### 14.4 현재 사용자 정보
`GET /v3/auth/me`

**Headers**
- `Authorization: Bearer <token>`

**Response 200**
```json
{
  "customer_id": "user123",
  "role": "customer"
}
```

**예시**
```bash
curl http://localhost:8000/v3/auth/me \
  -H "Authorization: Bearer <token>"
```

### 14.5 인증된 요청
모든 API 요청에 `Authorization` 헤더를 포함하여 인증된 요청을 보낼 수 있습니다.

**예시**
```bash
# 인증된 통계 조회
curl http://localhost:8000/v3/stats/summary \
  -H "Authorization: Bearer <token>"

# 인증된 점수 추이 조회
curl http://localhost:8000/v3/stats/score-trends?customer_id=user123 \
  -H "Authorization: Bearer <token>"
```

### 14.6 속도 제한 (Rate Limiting)
- 로그인: 분당 5회
- 통계 조회: 분당 30회
- 데이터 내보내기/삭제: 분당 10회

### 14.7 민감 정보 필터링
비관리자 사용자에게는 다음 필드가 제거되거나 마스킹됩니다:
- `image_path`
- `input_path`
- `output_dir`
- `stack_trace`
- `error_traceback`

### 14.8 감사 로그
모든 데이터 접근은 감사 로그에 기록됩니다:
- 접근자 ID
- 대상 고객 ID
- 엔드포인트
- HTTP 메서드
- 사용자 역할
- IP 주소
- 성공/실패 여부

---

## 15) 고객 전용 API

### 15.1 내 점수 추이 조회
`GET /v3/customer/my/trends`

**Headers**
- `Authorization: Bearer <token>` (필수)

**Query Parameters**
- `days`: 조회할 기간 (일, 기본 30)
- `limit`: 조회할 레코드 수 (기본 100)

**Response 200**
```json
{
  "trends": [
    {
      "id": 1,
      "customer_id": "user123",
      "timestamp": "2026-05-15T12:34:56.789",
      "overall_score": 72.0,
      "melasma_score": 60,
      "redness_score": 70,
      "wrinkle_score": 65,
      "pore_score": 75,
      "improvement_delta": 7.0,
      "analysis_count": 5
    }
  ],
  "count": 1
}
```

**예시**
```bash
curl http://localhost:8000/v3/customer/my/trends?days=30 \
  -H "Authorization: Bearer <token>"
```

### 15.2 내 분석 통계 조회
`GET /v3/customer/my/analysis`

**Headers**
- `Authorization: Bearer <token>` (필수)

**Query Parameters**
- `days`: 조회할 기간 (일, 기본 7)

**Response 200**
```json
{
  "stats": [
    {
      "id": 1,
      "date": "2026-05-15",
      "customer_id": "user123",
      "total_analyses": 10,
      "successful_analyses": 9,
      "failed_analyses": 1,
      "avg_score_original": 65.5,
      "avg_score_restored": 72.3,
      "avg_execution_time_sec": 45.2
    }
  ],
  "count": 1
}
```

**예시**
```bash
curl http://localhost:8000/v3/customer/my/analysis?days=7 \
  -H "Authorization: Bearer <token>"
```

### 15.3 내 에러 조회
`GET /v3/customer/my/errors`

**Headers**
- `Authorization: Bearer <token>` (필수)

**Query Parameters**
- `days`: 조회할 기간 (일, 기본 30)
- `limit`: 조회할 레코드 수 (기본 100)

**Response 200**
```json
{
  "errors": [
    {
      "id": 1,
      "timestamp": "2026-05-15T12:34:56.789",
      "error_type": "ValueError",
      "error_message": "Invalid image format",
      "module": "pipeline_core",
      "function": "load_image",
      "line_number": 256,
      "stack_trace": null,
      "customer_id": "user123",
      "image_path": "***REDACTED***",
      "pipeline_mode": "cli",
      "severity": "medium",
      "resolved": 0,
      "resolved_at": null,
      "resolution_note": null
    }
  ],
  "count": 1
}
```

**예시**
```bash
curl http://localhost:8000/v3/customer/my/errors?days=30 \
  -H "Authorization: Bearer <token>"
```

### 15.4 내 데이터 삭제 (GDPR)
`DELETE /v3/customer/my/data`

**Headers**
- `Authorization: Bearer <token>` (필수)

**Response 200**
```json
{
  "message": "Data deleted successfully",
  "deleted_records": 25
}
```

**예시**
```bash
curl -X DELETE http://localhost:8000/v3/customer/my/data \
  -H "Authorization: Bearer <token>"
```

### 15.5 내 데이터 내보내기
`GET /v3/customer/my/data/export`

**Headers**
- `Authorization: Bearer <token>` (필수)

**Response**
- ZIP 파일 다운로드 (JSON 포함)

**예시**
```bash
curl http://localhost:8000/v3/customer/my/data/export \
  -H "Authorization: Bearer <token>" \
  --output my_data.zip
```

---

## 16) 관리자 전용 API

### 16.1 감사 로그 조회
`GET /v3/admin/audit-logs`

**Headers**
- `Authorization: Bearer <token>` (필수, admin 역할)

**Query Parameters**
- `actor_customer_id`: 수행자 고객 ID (선택)
- `target_customer_id`: 대상 고객 ID (선택)
- `days`: 조회할 기간 (일, 기본 30)
- `limit`: 조회할 레코드 수 (기본 100)

**Response 200**
```json
{
  "audit_logs": [
    {
      "id": 1,
      "timestamp": "2026-05-15T12:34:56.789",
      "actor_customer_id": "user123",
      "target_customer_id": "user123",
      "endpoint": "/v3/customer/my/trends",
      "method": "GET",
      "user_role": "customer",
      "ip_address": "192.168.1.100",
      "user_agent": "Mozilla/5.0...",
      "success": 1,
      "error_message": null
    }
  ],
  "count": 1
}
```

**예시**
```bash
# 모든 감사 로그
curl http://localhost:8000/v3/admin/audit-logs \
  -H "Authorization: Bearer <admin_token>"

# 특정 고객 접근 기록
curl http://localhost:8000/v3/admin/audit-logs?actor_customer_id=user123 \
  -H "Authorization: Bearer <admin_token>"
```

---

## 17) 환경 변수

### 보안 관련
- `JWT_SECRET_KEY`: JWT 토큰 시크릿 키 (config.json의 `jwt.secret_key_env` 참조, 프로덕션에서 반드시 변경)
- `ALLOWED_ORIGINS`: CORS 허용 오리진 (config.json의 `server.allowed_origins` 참조, 콤마로 구분)

### DB 관련
#### SQLite
- `EXECUTION_HISTORY_DB`: 로컬 SQLite DB 파일 경로 (config.json의 `database.sqlite.path` 참조, 기본: `execution_history.db`)

#### Supabase
- `SUPABASE_URL`: Supabase 프로젝트 URL (config.json의 `database.supabase.url` 참조)
- `SUPABASE_KEY`: Supabase API 키 (config.json의 `database.supabase.key` 참조)

### 서버 관련
- `SERVER_URL`: 서버 URL (config.json의 `server.url` 참조)
- `SKIN_API_MAX_UPLOAD_BYTES`: 최대 업로드 크기 (config.json의 `server.max_upload_bytes` 참조)
- `SKIN_API_MAX_CONCURRENT`: 최대 동시 Job 수 (config.json의 `server.max_concurrent_jobs` 참조)

### LLM 관련
- `GEMINI_API_KEY`: Gemini API 키 (config.json의 `llm.api_key_env` 참조)

### 백업 관련
- `SKIN_API_BACKUP_INTERVAL_H`: 자동 백업 간격 (시간, 기본: 24)
- `SKIN_API_BACKUP_DIR`: 백업 디렉토리 (기본: `backup`)

---

## 18) DB 관리 API

### 18.1 DB Health Check
`GET /v3/health/db`

**Response 200 (Healthy)**
```json
{
  "healthy": true,
  "file_size_mb": 12.34,
  "file_size_bytes": 12945678,
  "row_counts": {
    "executions": 1000,
    "logs": 5000,
    "analysis_stats": 30,
    "model_performance": 100,
    "score_trends": 200,
    "gemini_api_stats": 50,
    "image_metadata": 1000,
    "error_analysis": 50,
    "system_health": 100,
    "audit_log": 500
  },
  "db_path": "execution_history.db",
  "last_check": "2026-05-15T12:34:56.789"
}
```

**Response 503 (Unhealthy)**
```json
{
  "healthy": false,
  "error": "Database file not found",
  "db_path": "execution_history.db",
  "last_check": "2026-05-15T12:34:56.789"
}
```

**예시**
```bash
curl http://localhost:8000/v3/health/db
```

### 18.2 DB Metrics (관리자 전용)
`GET /v3/admin/db/metrics`

**Headers**
- `Authorization: Bearer <token>` (필수, admin 역할)

**Response 200**
```json
{
  "execution_history": {
    "healthy": true,
    "file_size_mb": 12.34,
    "file_size_bytes": 12945678,
    "row_counts": {
      "executions": 1000,
      "logs": 5000
    },
    "db_path": "execution_history.db"
  },
  "analysis_results": {
    "healthy": true,
    "note": "Analysis results DB health check not implemented yet"
  },
  "supabase": {
    "healthy": true,
    "note": "Supabase health check not implemented yet"
  },
  "timestamp": "2026-05-15T12:34:56.789"
}
```

**예시**
```bash
curl http://localhost:8000/v3/admin/db/metrics \
  -H "Authorization: Bearer <admin_token>"
```

### 18.3 감사 로그 요약 (관리자 전용)
`GET /v3/admin/audit/summary`

**Headers**
- `Authorization: Bearer <token>` (필수, admin 역할)

**Query Parameters**
- `days`: 조회할 기간 (일, 기본 30)

**Response 200**
```json
{
  "total_access": 5000,
  "unique_users": 50,
  "failed_access": 100,
  "success_rate": 98.0,
  "top_endpoints": [
    {"endpoint": "/v3/customer/my/trends", "count": 1000},
    {"endpoint": "/v3/stats/summary", "count": 500}
  ],
  "suspicious_activity": [
    {
      "type": "multiple_failures",
      "ip_address": "192.168.1.100",
      "failure_count": 15
    }
  ],
  "period_days": 30
}
```

**예시**
```bash
curl http://localhost:8000/v3/admin/audit/summary?days=30 \
  -H "Authorization: Bearer <admin_token>"
```

---

## 19) DB 관리 CLI

### 19.1 명령어 목록

```bash
python src/db/db_cli.py [COMMAND]
```

### 19.2 명령어 설명

#### cleanup
오래된 데이터 정리 (아카이빙)

```bash
python src/db/db_cli.py cleanup --days=90
```

#### backup
DB 백업 생성

```bash
python src/db/db_cli.py backup
```

#### status
DB 상태 확인

```bash
python src/db/db_cli.py status
```

**출력 예시**
```
DB Status: Healthy
File Size: 12.34 MB
Row Counts:
  executions: 1000
  logs: 5000
  analysis_stats: 30
  ...
```

#### migrate
DB 마이그레이션 실행

```bash
python src/db/db_cli.py migrate
```

#### archive
오래된 데이터 아카이빙

```bash
python src/db/db_cli.py archive --days=90
```

#### replica
읽기 전용 복제본 생성

```bash
python src/db/db_cli.py replica --output=execution_history_readonly.db
```

---

## 20) DB 기능 보완 내역

### 구현된 기능

1. **DB Health Check API**
   - DB 상태 실시간 확인
   - 파일 크기, 테이블 행 수 모니터링

2. **트랜잭션 관리**
   - `transaction()` 컨텍스트 매니저
   - 자동 커밋/롤백

3. **슬로우 쿼리 로그**
   - 느린 쿼리 감지 (기본 구조)

4. **재시도 메커니즘**
   - `tenacity` 패키지 사용
   - 최대 3회 재시도

5. **자동 백업**
   - 24시간마다 자동 백업
   - 7일 이상 된 백업 자동 삭제

6. **감사 로그 분석**
   - 비정상 활동 탐지
   - 상위 엔드포인트 통계

7. **연결 풀링**
   - `ConnectionPool` 클래스
   - 최대 10개 연결 풀링

8. **DB 마이그레이션 자동화**
   - `DBMigrationManager` 클래스
   - 버전 관리 기반 마이그레이션

9. **DB 암호화**
   - `EncryptedExecutionHistoryDB` 클래스
   - SQLCipher 사용 (선택적)

10. **읽기 전용 복제본**
    - `create_readonly_replica()` 함수
    - 읽기 전용 모드 복제본 생성

11. **데이터 아카이빙**
    - `archive_old_data()` 함수
    - 오래된 데이터 아카이브 테이블로 이동

12. **DB 관리 CLI**
    - 백업, 정리, 상태 확인, 마이그레이션, 아카이빙, 복제본 생성

### 추가된 의존성

```txt
tenacity>=8.2.0  # 재시도 메커니즘
click>=8.1.0     # CLI 도구
```

---

## 21) 코드 리뷰 반영 내역

### 21.1 보안 강화 (CRIT)

#### JWT 시크릿 키 검증
- **파일:** `src/server/server.py`
- **내용:** 서버 시작 시 JWT 시크릿 키 검증 추가
- **변경:** 기본값 사용 시 서버 시작 거부
- **환경 변수:** `JWT_SECRET_KEY` (필수)

#### 분석 엔드포인트 Rate Limit
- **파일:** `src/server/server.py`
- **내용:** `POST /v3/analysis/jobs`에 Rate Limit 적용
- **변경:** 3회/분 제한 (GPU 집약적 작업 보호)
- **API:** [4.2 분석 Job 생성](#42-분석-job-创建-async)

#### DB 테이블 중복 생성 제거
- **파일:** `src/cli/execution_history.py`
- **내용:** `EncryptedExecutionHistoryDB` 테이블 초기화 제거
- **변경:** 암호화 연결 제공 전용 클래스로 변경

### 21.2 코드 구조 개선 (HIGH)

#### DB 초기화 함수 분리
- **파일:** `src/cli/execution_history.py`
- **내용:** `_init_db()` 함수를 4개 서브 함수로 분리
- **변경:**
  - `_init_core_tables()`: executions, logs
  - `_init_stats_tables()`: 7개 통계 테이블
  - `_init_audit_tables()`: audit_log
  - `_init_indexes()`: 18개 인덱스
  - 트랜잭션 `BEGIN/COMMIT/ROLLBACK` 추가

### 21.3 의존성 관리 (MED)

#### requirements.txt opencv 중복 제거
- **파일:** `requirements.txt`
- **내용:** opencv 중복 지정 제거
- **변경:** 포워드 참조 방식으로 변경 (`-r requirements-core.txt`, `-r requirements-gui.txt`)

### 21.4 추후 작업

#### MultiViewMergerV3 파이프라인 연결
- **파일:** `src/scoring/skin_scoring.py`
- **내용:** 다중 이미지 업로드(left45, right45) 기능과 연결 필요
- **상태:** TODO 주석 추가 (추후 작업)

---

## 22) 리팩토링 반영 내역 (AI_Skin_v3_refactor_review.md)

### 22.1 Phase 1 - 즉시 수정 (완료)

#### P0-1: 런타임 크래시 방지
- **파일:** `src/gui/skin_measurement_chart_dialog.py`
- **문제:** 존재하지 않는 `src.gemini` 패키지 import → 런타임 ImportError
- **수정:** `src.gemini.gemini_skin_report` → `src.llm.llm_skin_report`

#### P1-1: 계층 위반 import (이미 구현됨)
- **파일:** `src/utils/utils.py`
- **문제:** 서버/CLI 공통 유틸인데 PySide6 직접 import
- **상태:** 이미 lazy import로 구현됨

#### P2-2: Python 3.12 deprecated
- **파일:** `src/server/server.py`
- **문제:** `datetime.utcnow()` deprecated
- **수정:** `datetime.now(timezone.utc)`로 교체

### 22.2 Phase 2 - 안정성 (완료)

#### P1-2: 전역 가변 상태 race condition
- **파일:** `src/scoring/skin_scoring.py`
- **문제:** `_load_scoring_config()` 전역 상태 수정 시 lock 없음
- **수정:** `threading.Lock` 추가, `_CONFIG_LOCK`으로 race condition 방지

#### P1-3: import 시 파일 I/O
- **파일:** `src/scoring/skin_scoring.py`
- **문제:** `_MEASUREMENT_ACTUAL_RANGES` 모듈 import 시 파일 I/O 실행
- **수정:** lazy 초기화로 변경, `_get_measurement_actual_ranges()` 함수 추가

#### P2-1: print() 대량 사용
- **파일:** `src/pipeline/pipeline_core.py`
- **문제:** 31개 print() 사용, 서버 환경 stdout 오염
- **수정:** 모든 print()를 log.debug/info/warning/error로 교체

### 22.3 추후 작업 (Phase 3/4)

#### P2-3: execution_history.py 분리
- **파일:** `src/cli/execution_history.py` (2,209줄)
- **제안:** Mixin 또는 서브모듈로 분리

#### P2-4: server.py 분리
- **파일:** `src/server/server.py` (2,020줄)
- **제안:** FastAPI routers 분리

#### P2-5: skin_scoring.py 분리
- **파일:** `src/scoring/skin_scoring.py` (3,856줄)
- **제안:** `_SkinAnalyzerV2` Mixin 분리

자세한 내용은 [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md#15-리팩토링-반영-내역)를 참조하세요.

---

## 23) SD 기능 제거 (2026-05-16)

### 제거 이유
- Stable Diffusion 기능이 실제로 사용되지 않음
- 코드 복잡도 감소 및 유지보수성 향상
- LLM 제공업체 독립성 확보 (Gemini → 일반 LLM)

### API 변경

#### POST /v3/analysis/jobs
**제거된 매개변수:**
- `skip_sd` (Form): SD 생략 여부
- `sd_strength` (Form): SD img2img 강도

**이름 변경된 매개변수:**
- `gemini_report` → `llm_report`: LLM 소견 생성
- `gemini_api_key` → `llm_api_key`: LLM API 키

**변경 전:**
```python
skip_sd: bool = Form(True),
do_restore: bool = Form(True),
sd_strength: float = Form(0.12),
gemini_report: bool = Form(False),
gemini_api_key: Optional[str] = Form(None),
```

**변경 후:**
```python
do_restore: bool = Form(True),
llm_report: bool = Form(False),
llm_api_key: Optional[str] = Form(None),
```

### 영향 범위
- API 클라이언트에서 skip_sd, sd_strength 매개변수 제거 필요
- API 클라이언트에서 gemini_report → llm_report, gemini_api_key → llm_api_key로 변경 필요
- 기본적으로 복원만 수행 (do_restore=True)

자세한 내용은 [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md#16-sd-기능-제거-2026-05-16)를 참조하세요.
