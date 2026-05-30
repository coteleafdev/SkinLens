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

## 5. 참고 문서

- `DEVELOPMENT_GUIDE.md` - 개발 가이드
- `SKIN_SCORING_GUIDE.md` - 스코어링 가이드
- `PRESCRIPTION_GUIDE.md` - 처방 가이드
- `RESTORATION_ENGINE_GUIDE.md` - 복원 엔진 추가 가이드

---

*생성일: 2026-05-24*  
*버전: v3.4*  
*수정일: 2026-05-24 (직교 신호 분해 개선, 복원 엔진 추상화 강화)*
