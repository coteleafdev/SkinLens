# 문서 목록 (Documentation Index)

이 문서는 SkinLens v1 프로젝트의 모든 문서를 체계적으로 정리한 목록입니다.

## 목차

1. [문서 구조](#문서-구조)
2. [문서 카테고리](#문서-카테고리)
3. [문서 검색 가이드](#문서-검색-가이드)
4. [문서 작성 가이드라인](#문서-작성-가이드라인)

---

## 문서 구조

```
docs/
├── README.md                           # 이 파일 (문서 목록)
├── PROJECT_OVERVIEW.md                 # 프로젝트 전체 개요
├── EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md # 외부 시스템 연동 가이드
├── INTEGRATION_TEST_GUIDE.md          # 연동 테스트 가이드
├── APP_FEATURE_RECOMMENDATIONS.md     # 앱 기능 추천
├── api/                                # API 문서 (1개)
├── db/                                 # 데이터베이스 문서 (2개)
├── design/                             # 디자인 문서 (23개)
├── guides/                             # 개발 가이드 (11개)
├── ops/                                # 운영 가이드 (8개)
├── project/                            # 프로젝트 관리 (3개)
└── user/                               # 사용자 가이드 (5개)
```

---

## 문서 카테고리

### 📄 루트 문서

| 파일 | 설명 | 대상 |
|------|------|------|
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | 프로젝트 전체 개요, 아키텍처, 기능 설명 | 모든 사용자 |
| [EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md](EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md) | 외부 시스템 연동 가이드 (웹훅, 콜백, OAuth, WebSocket) | 개발자, DevOps |
| [INTEGRATION_TEST_GUIDE.md](INTEGRATION_TEST_GUIDE.md) | 연동 테스트 가이드 | 개발자, QA |
| [APP_FEATURE_RECOMMENDATIONS.md](APP_FEATURE_RECOMMENDATIONS.md) | 앱 기능 추천 | 제품 디자이너, 개발자 |

### 🔌 API 문서 (api/)

| 파일 | 설명 | 대상 |
|------|------|------|
| [API_REFERENCE.md](api/API_REFERENCE.md) | API 엔드포인트, 요청/응답 형식, 인증, 에러 코드 | 개발자 |

### 🗄️ 데이터베이스 문서 (db/)

| 파일 | 설명 | 대상 |
|------|------|------|
| [DATA_MODEL.md](db/DATA_MODEL.md) | 데이터 모델, 스키마, JSON 구조 | 개발자, DBA |
| [supabase_setup.sql](db/supabase_setup.sql) | Supabase 데이터베이스 설정 SQL | DBA, 개발자 |

### 🎨 디자인 문서 (design/)

| 파일 | 설명 | 상태 |
|------|------|------|
| [AB_TESTING_FRAMEWORK_DESIGN.md](design/AB_TESTING_FRAMEWORK_DESIGN.md) | A/B 테스트 프레임워크 설계 | 설계 |
| [ANALYSIS_RESULT_SHARING_DESIGN.md](design/ANALYSIS_RESULT_SHARING_DESIGN.md) | 분석 결과 공유 설계 | 설계 |
| [AUTO_RECOVERY_DESIGN.md](design/AUTO_RECOVERY_DESIGN.md) | 자동 복구 시스템 설계 | 설계 |
| [AUTO_SCALING_DESIGN.md](design/AUTO_SCALING_DESIGN.md) | 자동 스케일링 설계 | 설계 |
| [DESIGN_REFERENCE_GUIDED_SCORING.md](design/DESIGN_REFERENCE_GUIDED_SCORING.md) | 참조 기반 점수 매기기 설계 | 설계 |
| [DIAGNOSIS_FEEDBACK_LOOP_DESIGN.md](design/DIAGNOSIS_FEEDBACK_LOOP_DESIGN.md) | 진단 피드백 루프 설계 | 설계 |
| [FACE_AUTHENTICATION_DESIGN.md](design/FACE_AUTHENTICATION_DESIGN.md) | 얼굴 인증 설계 | 설계 |
| [GDPR_COMPLIANCE_DESIGN.md](design/GDPR_COMPLIANCE_DESIGN.md) | GDPR 준수 설계 | 설계 |
| [IMAGE_ENCRYPTION_DESIGN.md](design/IMAGE_ENCRYPTION_DESIGN.md) | 이미지 암호화 설계 | 설계 |
| [MULTI_IMAGE_ANALYSIS_DESIGN.md](design/MULTI_IMAGE_ANALYSIS_DESIGN.md) | 멀티 이미지 분석 설계 | 설계 |
| [MULTI_LANGUAGE_SUPPORT_DESIGN.md](design/MULTI_LANGUAGE_SUPPORT_DESIGN.md) | 다국어 지원 설계 | 설계 |
| [PRESCRIPTION_HISTORY_TRACKING_DESIGN.md](design/PRESCRIPTION_HISTORY_TRACKING_DESIGN.md) | 처방 이력 추적 및 효과 예측 설계 | 설계 |
| [PRICE_FILTER_DESIGN.md](design/PRICE_FILTER_DESIGN.md) | 가격 필터 설계 | 설계 |
| [PRODUCT_REVIEW_AND_OFFLINE_DESIGN.md](design/PRODUCT_REVIEW_AND_OFFLINE_DESIGN.md) | 제품 리뷰 통합 및 오프라인 모드 설계 | 설계 |
| [PUSH_NOTIFICATION_DESIGN.md](design/PUSH_NOTIFICATION_DESIGN.md) | 푸시 알림 설계 | 설계 |
| [REALTIME_RESTORATION_PREVIEW_DESIGN.md](design/REALTIME_RESTORATION_PREVIEW_DESIGN.md) | 실시간 복원 미리보기 설계 | 설계 |
| [REGIONAL_RESTORATION_DESIGN.md](design/REGIONAL_RESTORATION_DESIGN.md) | 지역별 복원 설계 | 설계 |
| [SCORE_CORRECTION_DESIGN.md](design/SCORE_CORRECTION_DESIGN.md) | 점수 보정 설계 | 설계 |
| [SKIN_TYPE_AUTO_DETECTION_DESIGN.md](design/SKIN_TYPE_AUTO_DETECTION_DESIGN.md) | 피부 타입 자동 감지 설계 | 설계 |
| [TIME_SERIES_ANALYSIS_DESIGN.md](design/TIME_SERIES_ANALYSIS_DESIGN.md) | 시계열 분석 설계 | 설계 |
| [WEBSOCKET_PROGRESS.md](design/WEBSOCKET_PROGRESS.md) | WebSocket 진행률 설계 | 설계 |
| [IN_PROCESS_MODEL_ARCHITECTURE.md](design/IN_PROCESS_MODEL_ARCHITECTURE.md) | 인프로세스 모델 상주 아키텍처 설계 | 설계 |
| [PERFECTCORP_VS_COTELEAF_COMPARISON.md](design/PERFECTCORP_VS_COTELEAF_COMPARISON.md) | PerfectCorp vs CÔTELEAF 측정항목 비교 | 설계 |

### 📚 개발 가이드 (guides/)

| 파일 | 설명 | 대상 |
|------|------|------|
| [ARCHITECTURE_GUIDE.md](guides/ARCHITECTURE_GUIDE.md) | 아키텍처 가이드, 전략 패턴 | 개발자 |
| [DEVELOPMENT_GUIDE.md](guides/DEVELOPMENT_GUIDE.md) | 개발 환경 설정, 코딩 규칙 | 개발자 |
| [JSON_IO_FLOW.md](guides/JSON_IO_FLOW.md) | 데이터 처리 흐름, 폴더 구조 | 개발자 |
| [PERFORMANCE_GUIDE.md](guides/PERFORMANCE_GUIDE.md) | 성능 최적화 가이드 | 개발자 |
| [PRESCRIPTION_GUIDE.md](guides/PRESCRIPTION_GUIDE.md) | 처방 가이드, PCR 규칙 | 개발자 |
| [RESTORATION_ENGINE_GUIDE.md](guides/RESTORATION_ENGINE_GUIDE.md) | 복원 엔진 추가 가이드 | 개발자 |
| [SKIN_SCORING_GUIDE.md](guides/SKIN_SCORING_GUIDE.md) | 피부 점수 가이드, 18개 측정항목 | 개발자 |
| [TESTING_GUIDE.md](guides/TESTING_GUIDE.md) | 테스트 가이드, 단위/통합/E2E | 개발자 |
| [CODEFORMER_PIPELINE_ALGORITHM.md](guides/CODEFORMER_PIPELINE_ALGORITHM.md) | CodeFormer 파이프라인 알고리즘 | 개발자 |
| [LLM_PROMPT_TEMPLATE.md](guides/LLM_PROMPT_TEMPLATE.md) | LLM 프롬프트 템플릿 | 개발자 |
| [WEIGHT_SYSTEM_DOCUMENTATION.md](guides/WEIGHT_SYSTEM_DOCUMENTATION.md) | 가중치 체계 문서 | 개발자 |

### ⚙️ 운영 가이드 (ops/)

| 파일 | 설명 | 대상 |
|------|------|------|
| [CI_CD_GUIDE.md](ops/CI_CD_GUIDE.md) | CI/CD 통합 가이드 | DevOps, 개발자 |
| [DEPLOYMENT_GUIDE.md](ops/DEPLOYMENT_GUIDE.md) | 배포 가이드 (Docker/직접) | DevOps |
| [INCIDENT_RESPONSE_GUIDE.md](ops/INCIDENT_RESPONSE_GUIDE.md) | 인시던트 대응 가이드 | DevOps |
| [LINUX_DOCKER_DEPLOYMENT.md](ops/LINUX_DOCKER_DEPLOYMENT.md) | 리눅스 Docker 상세 배포 가이드 | DevOps |
| [MONITORING_GUIDE.md](ops/MONITORING_GUIDE.md) | 모니터링 가이드 | DevOps |
| [SECURITY_GUIDE.md](ops/SECURITY_GUIDE.md) | 보안 가이드 (API 키, 데이터 보호) | DevOps, 개발자 |
| [SERVER_TEST_GUIDE.md](ops/SERVER_TEST_GUIDE.md) | 서버 테스트 가이드 | DevOps, 개발자 |
| [TROUBLESHOOTING_GUIDE.md](ops/TROUBLESHOOTING_GUIDE.md) | 트러블슈팅 가이드 | DevOps, 개발자 |

### 📁 프로젝트 관리 (project/)

| 파일 | 설명 | 대상 |
|------|------|------|
| [CODE_REVIEW_HISTORY.md](project/CODE_REVIEW_HISTORY.md) | 코드 리뷰 이력 | 개발자 |
| [DEPRECATION.md](project/DEPRECATION.md) | 폐지 예정 기능 | 개발자 |
| [IMPROVEMENT_PLAN.md](project/IMPROVEMENT_PLAN.md) | 개선 계획 | 개발자 |

### 👤 사용자 가이드 (user/)

| 파일 | 설명 | 대상 |
|------|------|------|
| [MOBILE_APP_GUIDE.md](user/MOBILE_APP_GUIDE.md) | 모바일 앱 가이드 | 최종 사용자 |
| [PRODUCT_PURCHASE_GUIDE.md](user/PRODUCT_PURCHASE_GUIDE.md) | 제품 구매 가이드 | 최종 사용자 |
| [SERUM_PRESCRIPTION_CUSTOMER_GUIDE.md](user/SERUM_PRESCRIPTION_CUSTOMER_GUIDE.md) | 세럼 처방 고객 가이드 | 최종 사용자 |
| [USER_GUIDE.md](user/USER_GUIDE.md) | 사용자 가이드 (웹) | 최종 사용자 |
| [IMAGE_ENHANCER_GUIDE.md](user/IMAGE_ENHANCER_GUIDE.md) | 이미지 인핸서 사용자 가이드 (GUI) | 최종 사용자 |

---

## 문서 검색 가이드

### 사용자별 추천 문서

#### 🆕 새로운 개발자
1. [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) - 프로젝트 전체 이해
2. [DEVELOPMENT_GUIDE.md](guides/DEVELOPMENT_GUIDE.md) - 개발 환경 설정
3. [ARCHITECTURE_GUIDE.md](guides/ARCHITECTURE_GUIDE.md) - 아키텍처 이해
4. [API_REFERENCE.md](api/API_REFERENCE.md) - API 사용 방법
5. [EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md](EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md) - 외부 시스템 연동
6. [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md#314-버전-관리) - 버전 관리 정책

#### 🔧 DevOps 엔지니어
1. [DEPLOYMENT_GUIDE.md](ops/DEPLOYMENT_GUIDE.md) - 배포 방법
2. [LINUX_DOCKER_DEPLOYMENT.md](ops/LINUX_DOCKER_DEPLOYMENT.md) - Docker 상세 배포
3. [SECURITY_GUIDE.md](ops/SECURITY_GUIDE.md) - 보안 설정
4. [TROUBLESHOOTING_GUIDE.md](ops/TROUBLESHOOTING_GUIDE.md) - 문제 해결
5. [EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md](EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md) - 외부 시스템 연동

#### 🎨 기능 설계자
1. [DESIGN_REFERENCE_GUIDED_SCORING.md](design/DESIGN_REFERENCE_GUIDED_SCORING.md) - 점수 시스템
2. [SKIN_SCORING_GUIDE.md](guides/SKIN_SCORING_GUIDE.md) - 피부 점수 가이드
3. [SKIN_TYPE_AUTO_DETECTION_DESIGN.md](design/SKIN_TYPE_AUTO_DETECTION_DESIGN.md) - 피부 타입 감지
4. [GDPR_COMPLIANCE_DESIGN.md](design/GDPR_COMPLIANCE_DESIGN.md) - GDPR 준수

#### 👤 최종 사용자
1. [USER_GUIDE.md](user/USER_GUIDE.md) - 기본 사용법
2. [MOBILE_APP_GUIDE.md](user/MOBILE_APP_GUIDE.md) - 모바일 앱 사용법
3. [PRODUCT_PURCHASE_GUIDE.md](user/PRODUCT_PURCHASE_GUIDE.md) - 제품 구매 방법
4. [SERUM_PRESCRIPTION_CUSTOMER_GUIDE.md](user/SERUM_PRESCRIPTION_CUSTOMER_GUIDE.md) - 세럼 처방 안내
5. [APP_FEATURE_RECOMMENDATIONS.md](APP_FEATURE_RECOMMENDATIONS.md) - 앱 기능 추천

### 주제별 검색

#### 앱 기능
- [APP_FEATURE_RECOMMENDATIONS.md](APP_FEATURE_RECOMMENDATIONS.md) - 앱 기능 추천

#### API 관련
- [API_REFERENCE.md](api/API_REFERENCE.md) - API 엔드포인트 상세

#### 주문/결제 관련
- [API_REFERENCE.md](api/API_REFERENCE.md#9-주문-orders) - 주문 API 상세

#### 앱 기능 관련
- [API_REFERENCE.md](api/API_REFERENCE.md#10-앱-기능-app-features) - 앱 기능 API 상세

#### 데이터베이스 관련
- [DATA_MODEL.md](db/DATA_MODEL.md) - 데이터 모델, 스키마
- [supabase_setup.sql](db/supabase_setup.sql) - Supabase 설정
- [GDPR_COMPLIANCE_DESIGN.md](design/GDPR_COMPLIANCE_DESIGN.md) - 데이터 보호

#### 모델/알고리즘 관련
- [CODEFORMER_PIPELINE_ALGORITHM.md](guides/CODEFORMER_PIPELINE_ALGORITHM.md) - CodeFormer 알고리즘
- [LLM_PROMPT_TEMPLATE.md](guides/LLM_PROMPT_TEMPLATE.md) - LLM 프롬프트
- [IN_PROCESS_MODEL_ARCHITECTURE.md](design/IN_PROCESS_MODEL_ARCHITECTURE.md) - 모델 아키텍처

#### 보안 관련
- [SECURITY_GUIDE.md](ops/SECURITY_GUIDE.md) - 보안 가이드
- [GDPR_COMPLIANCE_DESIGN.md](design/GDPR_COMPLIANCE_DESIGN.md) - GDPR 준수
- [IMAGE_ENCRYPTION_DESIGN.md](design/IMAGE_ENCRYPTION_DESIGN.md) - 이미지 암호화
- [FACE_AUTHENTICATION_DESIGN.md](design/FACE_AUTHENTICATION_DESIGN.md) - 얼굴 인증

#### 신규 기능 설계
- [design/](design/) 폴더의 모든 문서
- [IMPROVEMENT_PLAN.md](project/IMPROVEMENT_PLAN.md) - 개선 계획

#### 성능/테스트
- [PERFORMANCE_GUIDE.md](guides/PERFORMANCE_GUIDE.md) - 성능 최적화
- [TESTING_GUIDE.md](guides/TESTING_GUIDE.md) - 테스트 가이드
- [SERVER_TEST_GUIDE.md](ops/SERVER_TEST_GUIDE.md) - 서버 테스트

---

## 문서 작성 가이드라인

### 파일 명명 규칙

- **모든 md 파일은 대문자**: 모든 문서 파일명은 대문자로 작성 (예: `PROJECT_OVERVIEW.md`, `CODEFORMER_PIPELINE_ALGORITHM.md`)
- **언더스코어**: 단어 구분 (예: `CI_CD_GUIDE.md`)

### 문서 구조

```markdown
# 문서 제목

> **프로젝트:** SkinLens v1.0
> **버전:** v1.0
> **작성일:** YYYY-MM-DD
> **상태:** 초안/검토/완료

---

## 목차

1. [섹션 1](#섹션-1)
2. [섹션 2](#섹션-2)

---

## 섹션 1

내용...

---

## 섹션 2

내용...
```

### 문서 상태

- **초안**: 작성 중인 문서
- **검토**: 리뷰가 필요한 문서
- **완료**: 검토 완료된 문서
- **폐지**: 더 이상 사용하지 않는 문서

### 문서 업데이트

문서를 업데이트할 때:
1. 버전 번호 업데이트
2. 작성일 업데이트
3. 변경 사항을 문서 상단에 기록
4. 관련 문서의 참조 업데이트

---

## 추가 리소스

- **프로젝트 README**: [../README.md](../README.md)
- **테스트 가이드**: [../tests/README.md](../tests/README.md)
- **서버 테스트 가이드**: [../tests/README_SERVER_TESTS.md](../tests/README_SERVER_TESTS.md)
- **CI/CD 가이드**: [ops/CI_CD_GUIDE.md](ops/CI_CD_GUIDE.md)

---

## 문서 관리

이 문서는 다음 경우에 업데이트됩니다:
- 새로운 문서가 추가될 때
- 기존 문서가 삭제될 때
- 문서 구조가 변경될 때
- 문서 카테고리가 재정리될 때

---

**마지막 업데이트**: 2026-05-31
**현재 개발 환경**: Python 3.12
