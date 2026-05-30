# 아키텍처 가이드 (Architecture Guide)

> **프로젝트:** SkinLens v1.0
> **버전:** v3.6
> **최종 수정:** 2026-05-27

---

## 개요

이 문서는 SkinLens v1.0의 아키텍처 패턴과 데이터베이스 구조를 설명합니다.

---

## 1. 전략 패턴 (Strategy Pattern)

### 1.1 분석기 전략 패턴

피부 분석 알고리즘을 쉽게 교체할 수 있는 전략 패턴 기반 아키텍처입니다.

**아키텍처:**
```
BaseAnalyzer (추상 인터페이스)
    ├── PigmentationAnalyzerV1 (현재 알고리즘)
    ├── PigmentationAnalyzerV2 (새로운 알고리즘 예시)
    ├── RednessAnalyzerV1
    ├── PoreAnalyzerV1
    ├── WrinkleAnalyzerV1
    ├── ToneElasticityAnalyzerV1 (톤·탄력·다크서클·피지)
    └── AcneAnalyzerV1 (트러블 - 독립)

AnalyzerRegistry (팩토리)
    └── 분석기 등록/조회

_SkinAnalyzerV3Core (오케스트레이터)
    └── 분석기 주입 (의존성 주입)

SkinAnalyzerV3 (공개 API)
    └── _SkinAnalyzerV3Core 위임 + 직교 신호 분해
```

**사용 방법:**

**기본 사용 (하위 호환):**
```python
from src.scoring.skin_scoring import _SkinAnalyzerV3Core

analyzer = _SkinAnalyzerV3Core()  # 기본 분석기 자동 로드
result = analyzer.analyze_all("image.jpg")
```

**분석기 직접 주입:**
```python
from src.skin.analyzers import AnalyzerRegistry, register_all_analyzers
from src.scoring.skin_scoring import _SkinAnalyzerV3Core

register_all_analyzers()

custom_analyzers = {
    "pigmentation": AnalyzerRegistry.get("pigmentation_v2"),  # v2 사용
    "redness": AnalyzerRegistry.get("redness_v1"),
    # ...
}

analyzer = _SkinAnalyzerV3Core(analyzers=custom_analyzers)
result = analyzer.analyze_all("image.jpg")
```

### 1.2 복원 백엔드 전략 패턴

피부 복원 백엔드를 쉽게 교체할 수 있는 전략 패턴 기반 아키텍처입니다.

**아키텍처:**
```
BaseRestorer (추상 인터페이스)
    ├── CodeFormerRestorer
    ├── RestoreFormerRestorer
    └── [추후 확장]

RestorerRegistry (팩토리)
    └── 복원 백엔드 등록/조회/인스턴스 생성
```

**BaseRestorer 메서드:**
- 필수: `restore()`, `get_name()`, `get_version()`
- 선택: `load_model()`, `unload_model()`, `preprocess()`, `postprocess()`, `cleanup()`, `get_supported_devices()`

**사용 방법:**
```python
from src.restoration import RestorerRegistry

# 복원 백엔드 등록 (자동)
# @RestorerRegistry.register("codeformer_v1", aliases=["codeformer", "cf"])

# 클래스 조회
restorer_class = RestorerRegistry.get("codeformer_v1")

# 인스턴스 생성 (팩토리 메서드)
restorer = RestorerRegistry.create("codeformer_v1", config={"repo": "path/to/CodeFormer"})

# 설정 기반 생성
restorer = RestorerRegistry.create_from_config({"restorer": "codeformer", "restorer_config": {...}})

# 복원 실행
result = restorer.restore("input.jpg", "output.jpg")
```

**새로운 엔진 추가:**
자세한 가이드는 `RESTORATION_ENGINE_GUIDE.md`를 참조하세요.

### 1.3 LLM 전략 패턴

LLM을 쉽게 교체할 수 있는 전략 패턴 기반 아키텍처입니다.

**아키텍처:**
```
BaseLLM (추상 인터페이스)
    ├── GeminiLLM
    └── [추후 확장: OpenAI, Claude 등]

LLMRegistry (팩토리)
    └── LLM 등록/조회
```

**사용 방법:**
```python
from src.llm import LLMRegistry, register_all_llms

# LLM 등록
register_all_llms()

# Gemini 사용
llm_class = LLMRegistry.get("gemini_v1")
llm = llm_class(api_key="your-api-key")
response = llm.generate(prompt)
```

### 1.4 LLM 응답 짤림 처리 (부분 완료 로직)

LLM 응답이 토큰 제한으로 인해 짤리는 경우, 전체 프롬프트를 다시 보내는 대신 누락된 필드만 요청하여 효율적으로 재시도합니다.

**작동 원리**:
1. **응답 짤림 감지**: `_is_response_truncated()` 함수로 응답이 완전한지 확인
2. **부분 JSON 파싱**: 마크다운 코드 블록 제거 후 부분 JSON 파싱 시도
3. **누락 필드 식별**: `_identify_missing_fields()`로 기대 필드와 실제 필드 비교
4. **부분 완료 요청**: 누락된 필드가 10개 미만일 경우 `_build_field_completion_prompt()`로 부분 요청 생성
5. **응답 병합**: `_merge_json_responses()`로 원본 응답과 완료 응답 병합

**적용 모드**:
- **Reference Guided 모드**: `reference_baseline`, `score_reasons`, `orig_metric_scores`, `orig_metric_opinions`, `orig_overall_score`, `orig_perceived_age`, `orig_overall_opinion`, `recommendation`, `ref_metric_scores`, `ref_metric_reasons`
- **Dual 모드**: `original_metric_opinions`, `restored_metric_opinions`, `original_overall_opinion`, `restored_overall_opinion`, `original_overall_score`, `restored_overall_score`, `original_perceived_age`, `restored_perceived_age`, `recommendation`

**재시도 전략**:
- 누락 필드 < 10개: 부분 완료 시도 (이미지 없이 텍스트만 요청)
- 누락 필드 ≥ 10개: 토큰 1.5배 증가 후 전체 재시도
- 최대 재시도: 기본 재시도 + 토큰 증가 재시도 2회

**타임아웃 설정**:
- 기본 타임아웃: 600초 (config.json `llm.timeout_sec`, `timeouts.llm_timeout_sec`, `llms.gemini_v1.timeout_sec`)

### 1.5 메타데이터 캐시 초기화

config.json 변경 사항이 즉시 반영되도록 진입점별로 캐시를 초기화합니다.

**캐시 초기화 대상**:
- `_clear_breakpoints_cache()`: 점수 기준점 캐시
- `clear_metadata_cache()`: LLM 메타데이터 캐시 (점수 스케일 등)

**적용 진입점**:
- **GUI 모드**: `src/gui/image_enhancer.py` main() 함수
- **서버 모드**: `src/server/server.py` lifespan startup
- **CLI 모드**: 필요 없음 (일회성 실행)

**초기화 시점**:
- GUI: 애플리케이션 시작 시
- 서버: FastAPI lifespan startup (서버 시작 시)

---

## 2. 데이터베이스 아키텍처

### 2.1 개요

AI Skin v3는 **로컬 SQLite DB**와 **클라우드 DB**의 2계층 데이터베이스 아키텍처를 사용하여 각기 다른 목적과 역할을 수행합니다. 이 하이브리드 아키텍처는 성능, 보안, 확장성, 그리고 규정 준수를 최적화하기 위해 설계되었습니다.

### 2.2 로컬 SQLite DB

**목적:**
- **실행 이력 추적**: 각 분석 작업의 실행 로그와 리소스 사용량 기록
- **시스템 모니터링**: 서버 헬스 체크, API 성능, 에러 추적
- **운영 통계**: 일별 분석 수, 성공/실패율, 모델 성능 메트릭
- **감사 로그**: 데이터 접근 기록, 보안 이벤트 추적
- **캐싱**: 빠른 조회를 위한 로컬 데이터 저장

**역할:**
- **운영 및 모니터링**: 서버 운영자가 시스템 상태를 실시간으로 모니터링
- **문제 해결**: 에러 추적, 성능 병목 식별, 디버깅 지원
- **보안 감사**: 누가 언제 무엇을 접근했는지 기록
- **통계 분석**: 서비스 사용 패턴, 트래픽 추이 분석
- **GDPR 준수**: 고객 데이터 삭제/내보내기 지원

**저장 데이터:**
| 테이블 | 설명 | 보관 기간 |
|--------|------|-----------|
| executions | 분석 작업 실행 이력 | 90일 (기본) |
| logs | 애플리케이션 로그 | 30일 (롤링) |
| analysis_stats | 일별 분석 통계 | 365일 |
| model_performance | 모델 성능 메트릭 | 90일 |
| score_trends | 고객별 점수 추이 | 무제한 |
| gemini_api_stats | Gemini API 사용 통계 | 365일 |
| image_metadata | 이미지 메타데이터 | 90일 |
| error_analysis | 에러 분석 및 추적 | 180일 |
| system_health | 시스템 헬스 체크 | 30일 |
| audit_log | 감사 로그 | 365일 |

**특징:**
- **빠른 조회**: 로컬 파일 기반으로 초고속 읽기
- **무서버**: 별도 DB 서버 없이 파일로 저장
- **간단한 백업**: 파일 복사만으로 백업 가능
- **저비용**: 추가 인프라 비용 없음
- **오프라인 작동**: 네트워크 연결 없이도 작동

**사용자:**
- **서버 관리자**: 시스템 모니터링, 문제 해결
- **DevOps 엔지니어**: 운영 통계, 성능 최적화
- **보안 담당자**: 감사 로그, 보안 이벤트 분석
- **고객 (제한적)**: 자신의 통계 데이터 조회

### 2.3 클라우드 DB

**목적:**
- **고객 데이터 저장**: 고객 분석 결과, 처방전, 이미지
- **장기 보관**: 법적 요구사항 준수를 위한 장기 보관
- **데이터 분석**: 머신러닝, 비즈니스 인텔리전스
- **동기화**: 여러 클라이언트 간 데이터 동기화

**역할:**
- **고객 서비스**: 고객 데이터 조회, 내보내기
- **데이터 분석**: 트렌드 분석, 모델 개선
- **규정 준수**: GDPR, 개인정보보호법 준수
- **백업/복구**: 재해 복구, 데이터 보호

**저장 데이터:**
| 테이블 | 설명 | 보관 기간 |
|--------|------|-----------|
| customers | 고객 정보 | 계정 존재 기간 |
| analyses | 분석 결과 | 3년 (기본) |
| prescriptions | 처방전 | 3년 (기본) |
| images | 이미지 | 3년 (기본) |
| pcr_results | PCR 결과 | 3년 (기본) |

**특징:**
- **확장성**: 수평 확장 가능
- **고가용성**: 복제, 장애 조치
- **보안**: 암호화, 접근 제어
- **글로벌 액세스**: 어디서든 접근 가능

**사용자:**
- **고객**: 자신의 데이터 조회, 내보내기
- **데이터 분석가**: 트렌드 분석, 모델 개선
- **비즈니스 팀**: 비즈니스 인텔리전스
- **규정 담당자**: 규정 준수 확인

### 2.4 데이터 흐름

```
고객 요청
    ↓
로컬 SQLite DB (캐싱, 로깅)
    ↓
클라우드 DB (장기 보관, 동기화)
    ↓
고객 응답
```

---

## 3. 레이어 아키텍처

### 3.1 전체 아키텍처

```
┌─────────────────────────────────────────┐
│         Presentation Layer             │
│  (GUI: PySide6, CLI, API)             │
└─────────────────┬───────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         Business Logic Layer           │
│  (Pipeline, Scoring, Prescription)    │
└─────────────────┬───────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│            Data Layer                  │
│  (Local SQLite, Cloud DB, File System) │
└─────────────────────────────────────────┘
```

### 3.2 모듈 의존성 규칙

**하위 → 상위 의존 허용:**
- `skin/core/` → 표준 라이브러리만
- `skin/compose/` → `skin/core/`, `scoring/`
- `scoring/` → `skin/core/`
- `pipeline/` → 독립 (표준 라이브러리만)
- `utils/` → `skin/`, `scoring/` (lazy import)

**상위 → 하위 의존 금지:**
- `server/` → `gui/` (금지)
- `cli/` → `gui/` (금지)

---

## 4. 직교 신호 분해 수정 이력 (2026-05-24)

### 4.1 수정 개요

**직교 항목 수**: 10개 (변경 없음)

**구조적 개선**:
- PIE(post_inflammatory_erythema_score) 신호 제거로 a* 채널 이중 계상 해결
- 가중치 조정으로 roughness ↔ fine_deep 중복 영향 완화

### 4.2 상세 수정 내용

**방향 A: PIE 완전 제거**
- `diffuse_redness`: `redness × 0.70 + PIE × 0.30` → `redness` 단독 사용
- `focal_lesion`: `acne × 0.60 + post_acne_pigment × 0.40` → `acne × 0.65 + post_acne_pigment × 0.35`
- 효과: diffuse_redness ↔ focal_lesion 간의 직교성 개선

**방향 C: 가중치 보정**
- `roughness_score`: 0.080 → 0.050 (fine_deep와의 중복 보정)
- `wrinkle_score`: 0.130 → 0.160 (roughness 감소분 보상)

### 4.3 수정 파일
- `src/skin/compose/score_composition.py`
- `src/scoring/skin_scoring.py`
- `config/config.json`

### 4.4 참고 문서
- 직교성 검토 내용은 config.json의 `_structure_guide` 및 `orthogonal_categories` 섹션 참조

---

## 5. 이미지 처리 방식 (Image Processing by Mode)

### 5.1 개요

SkinLens는 세 가지 실행 모드(GUI, CLI, 서버)에서 각각 다른 이미지 처리 방식을 사용합니다. 모든 모드에서 JSON 출력에 이미지 경로와 URL 정보를 포함합니다.

### 5.2 모드별 이미지 처리

#### 5.2.1 GUI 모드 (image_enhancer.py)

**이미지 처리 방식:**
- 로컬 파일 시스템 경로로 직접 처리
- 입력 이미지: 사용자가 선택한 로컬 파일
- 출력 이미지: `results/{이미지명}/` 폴더에 저장

**JSON 출력 구조:**
```json
{
  "original_image": "C:\\Project\\SkinLens v1\\results\\...",
  "restored_image": "C:\\Project\\SkinLens v1\\results\\...",
  "original_image_url": "file:///C:/Project/SkinLens v1/results/...",
  "restored_image_url": "file:///C:/Project/SkinLens v1/results/...",
  "customer_info": {
    "customer_id": null,
    "gender": null,
    "age": null,
    "race": null,
    "region": null
  }
}
```

**특징:**
- 로컬 개발 환경에서 사용
- `file://` 프로토콜 URL 제공
- 고객 정보는 CLI 인자로 선택적 입력

#### 5.2.2 CLI 모드 (skin_analysis_cli.py)

**이미지 처리 방식:**
- 로컬 파일 시스템 경로로 직접 처리
- 입력 이미지: 명령행 인자로 지정된 로컬 파일
- 출력 이미지: 지정된 출력 디렉토리에 저장

**JSON 출력 구조:**
```json
{
  "input_image": "/path/to/input.jpg",
  "restored_image": "/path/to/output.jpg",
  "input_image_url": "http://server.com/input.jpg",
  "restored_image_url": "http://server.com/output.jpg",
  "customer_info": {
    "customer_id": "CUST001",
    "gender": "female",
    "age": 30,
    "race": "asian",
    "region": "KR"
  }
}
```

**특징:**
- 서버 환경에서 `base_url` 제공 시 URL 기반 처리
- `base_url`이 없으면 로컬 경로만 제공
- 고객 정보 필수 (서버 환경)

#### 5.2.3 서버 모드 (jobs.py)

**이미지 처리 방식:**
- 로컬 폴더에 저장 후 URL로 접근
- 입력 이미지: `results/api_jobs/{job_id}/` 폴더에 저장
- 출력 이미지: 동일 폴더에 저장

**JSON 출력 구조:**
```json
{
  "input_image_url": "/analysis/jobs/{job_id}/artifacts/input.jpg",
  "restored_image_url": "/analysis/jobs/{job_id}/artifacts/restored.png",
  "customer_info": {
    "customer_id": "CUST001",
    "gender": "female",
    "age": 30,
    "race": "asian",
    "region": "KR"
  }
}
```

**특징:**
- 완전히 URL 기반으로 처리
- 스마트폰 앱에서 전송된 고객 정보 포함
- JWT 인증으로 고객 ID 검증

### 5.3 DB 저장

**로컬 SQLite (skin_analysis.db):**
- `original_image_path`: 절대 경로
- `restored_image_path`: 절대 경로
- `json_result`: 전체 JSON (URL 포함)
- `customer_id`: 고객 식별자

**클라우드 Supabase:**
- 로컬 SQLite와 동일한 구조로 동기화
- `skin_analysis_db.py`의 `save_analysis()`가 자동 동기화

### 5.4 이미지 저장 위치

| 모드 | 원본 이미지 | 복원 이미지 |
|------|-------------|-------------|
| GUI | `results/{이미지명}/00_input_{이미지명}.png` | `results/{이미지명}/01_restored_{이미지명}.png` |
| CLI | 지정된 출력 디렉토리 | 지정된 출력 디렉토리 |
| 서버 | `results/api_jobs/{job_id}/input.jpg` | `results/api_jobs/{job_id}/output.png` |

---

## 6. 보안 가이드 (Security Guide)

### 6.1 개요

SkinLens는 API 키, 데이터베이스 자격증명, 고객 정보 등 민감한 정보를 처리합니다. 안전한 운용을 위한 보안 가이드입니다.

### 6.2 API 키 관리

#### 6.2.1 현재 구조

**LLM API 키 (GEMINI_API_KEY):**
- 서버: 환경변수 `GEMINI_API_KEY`에서만 로드
- 로컬: `config/config.secrets.json`에서 로드
- 보안: 클라이언트 입력 무시, 환경변수만 사용

**Supabase 키:**
- 환경변수 `SUPABASE_URL`, `SUPABASE_KEY`에서 로드
- `config.json`에도 저장 가능 (비권장)

#### 6.2.2 보안 강화 방안

**1. 환경변수 사용 (권장)**
```bash
# 서버 환경
export GEMINI_API_KEY="your_api_key"
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_KEY="your_service_role_key"
```

**2. secrets.json 파일 관리**
- `config/config.secrets.json`은 `.gitignore`에 포함
- 예제 파일: `src/config/config/config.secrets.example.json`
- 실제 파일은 배포 시 수동 생성

**3. Kubernetes Secret (프로덕션)**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: skinlens-secrets
type: Opaque
stringData:
  GEMINI_API_KEY: "your_api_key"
  SUPABASE_URL: "https://xxx.supabase.co"
  SUPABASE_KEY: "your_service_role_key"
```

### 6.3 고객 정보 보호

#### 6.3.1 현재 구조

**고객 정보 필드:**
- `customer_id`: 고객 식별자
- `gender`: 성별
- `age`: 연령
- `race`: 인종
- `region`: 지역

**보안 조치:**
- JWT 인증으로 고객 ID 검증
- `validate_customer_id_match()` 함수로 ID 일치 확인

#### 6.3.2 보안 강화 방안

**1. 데이터 암호화**
- DB 저장 시 민감 필드 암호화
- `customer_id`, `gender`, `age` 등 암호화 저장

**2. 접근 제어**
- 관리자만 전체 고객 정보 접근 가능
- 일반 사용자는 자신의 정보만 접근

**3. 로그 마스킹**
- 로그에 고객 정보 출력 시 마스킹
- `customer_id`: `CUST***` 형식

### 6.4 이미지 보안

#### 6.4.1 현재 구조

**이미지 저장:**
- 로컬: `results/` 폴더
- 서버: `results/api_jobs/{job_id}/` 폴더

**URL 접근:**
- 서버: `/analysis/jobs/{job_id}/artifacts/{filename}`
- JWT 인증 필요

#### 6.4.2 보안 강화 방안

**1. 이미지 액세스 제어**
- JWT 토큰으로 이미지 접근 제한
- 고객은 자신의 이미지만 접근 가능

**2. 이미지 만료 정책**
- 일정 기간 후 자동 삭제
- `results/api_jobs/` 폴더 정기 정리

**3. URL 서명**
- 일회용 URL 서명 사용
- 만료 시간 설정

### 6.5 데이터베이스 보안

#### 6.5.1 현재 구조

**로컬 SQLite:**
- `results/skin_analysis.db`
- 파일 시스템 접근 제어 필요

**클라우드 Supabase:**
- Row Level Security (RLS) 활용
- Service Role Key 사용

#### 6.5.2 보안 강화 방안

**1. SQLite 보안**
- 파일 권한: `600` (소유자만 읽기/쓰기)
- 암호화 SQLite 사용 (SQLCipher)

**2. Supabase RLS**
```sql
-- 고객은 자신의 데이터만 접근
CREATE POLICY customer_access ON skin_analyses
  FOR SELECT USING (auth.uid()::text = customer_id);
```

**3. 백업 암호화**
- 백업 파일 암호화
- 암호화 키 별도 관리

### 6.6 네트워크 보안

#### 6.6.1 현재 구조

**서버:**
- FastAPI 기반
- CORS 설정
- Rate Limiting

#### 6.6.2 보안 강화 방안

**1. HTTPS 강제**
- 모든 요청 HTTPS로 리다이렉트
- SSL/TLS 인증서 사용

**2. Rate Limiting 강화**
- IP별 요청 제한
- 고객별 요청 제한

**3. Security Headers**
```python
# FastAPI Security Headers
app.add_middleware(
    SecureHeadersMiddleware,
    hsts_max_age=31536000,
    hsts_include_subdomains=True,
    hsts_preload=True,
)
```

### 6.7 로그 및 감사

#### 6.7.1 현재 구조

**감사 로그:**
- `ExecutionHistoryDB.record_audit_log()`
- 접근, 수정 기록

#### 6.7.2 보안 강화 방안

**1. 로그 보안**
- 민감 정보 마스킹
- 로그 파일 암호화

**2. 감사 추적**
- 모든 DB 변경 사항 기록
- 불규칙 활동 알림

**3. 로그 보관**
- 일정 기간 후 자동 삭제
- 장기 보관용 암호화 아카이브

### 6.8 보안 체크리스트

**배포 전 확인:**
- [ ] 모든 API 키 환경변수로 설정
- [ ] secrets.json .gitignore 확인
- [ ] HTTPS 설정 완료
- [ ] JWT 인증 활성화
- [ ] Rate Limiting 설정
- [ ] DB 암호화 확인
- [ ] 백업 정책 수립
- [ ] 감사 로그 활성화

---

## 7. 참고 문서

- `DEVELOPMENT_GUIDE.md` - 개발 가이드
- `SKIN_SCORING_GUIDE.md` - 스코어링 가이드
- `PRESCRIPTION_GUIDE.md` - 처방 가이드
- `RESTORATION_ENGINE_GUIDE.md` - 복원 엔진 추가 가이드

---

*생성일: 2026-05-24*  
*버전: v3.4*  
*수정일: 2026-05-24 (직교 신호 분해 개선, 복원 엔진 추상화 강화)*
