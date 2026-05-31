# 프로젝트 개요 (Project Overview)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

## 문서 목적

이 문서는 SkinLens v1.0 프로젝트의 전체적인 개요를 제공합니다. 프로젝트의 비전, 아키텍처, 기술 스택, 사용법, 배포 방법 등을 포괄적으로 설명합니다.

## 1. 프로젝트 비전 및 목표

### 1.1 프로젝트 목적

SkinLens v1.0은 AI 기반 피부 분석 및 복원 파이프라인 프로젝트입니다. 고급 이미지 복원 기술과 정밀한 피부 상태 분석을 결합하여 사용자에게 전문적인 피부 관리 솔루션을 제공합니다.

### 1.2 핵심 가치

- **정밀성**: 18개 측정항목 기반 상세한 피부 분석
- **AI 기반 소견**: Google Gemini를 활용한 전문 피부 소견 생성
- **고품질 복원**: RestoreFormer++, CodeFormer를 활용한 고품질 이미지 복원
- **다양한 인터페이스**: GUI, CLI, API 서버 등 다양한 사용 환경 지원
- **보안성**: JWT 인증, 역할 기반 접근 제어, 감사 로그 등 보안 기능 탑재

### 1.3 차별점

- **통합 파이프라인**: 이미지 복원부터 피부 분석, AI 소견 생성까지 원스톱 처리
- **실시간 분석**: 빠른 처리 속도로 실시간 피부 분석 제공
- **확장성**: 모듈화된 아키텍처로 쉬운 기능 확장 가능
- **운영 효율성**: 실행 이력 추적, 로그 DB, 자동 백업 등 운영 자동화
- **외부 시스템 연동**: 웹훅, 콜백 URL, OAuth, WebSocket을 통한 유연한 연동

---

## 2. 기술 스택

### 2.1 핵심 기술

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| Deep Learning | PyTorch, Transformers | 딥러닝 모델 실행 |
| 이미지 처리 | OpenCV, PIL, scikit-image | 이미지 전처리/후처리 |
| GUI | PySide6 | 그래픽 사용자 인터페이스 |
| Web API | FastAPI, Uvicorn | REST API 서버 |
| AI | Google Generative AI (Gemini) | 피부 소견 생성 |
| 데이터베이스 | SQLite, Supabase (PostgreSQL) | 데이터 저장 |
| 보안 | python-jose (JWT), passlib, slowapi | 인증/인가 |
| DB 관리 | tenacity (재시도), click (CLI) | DB 운영 |

### 2.2 복원 모델

- **RestoreFormer++**: 고급 이미지 복원 모델
- **CodeFormer**: 얼굴 복원 모델

### 2.3 피부 분석

- **SkinAnalyzerV3**: 18개 측정항목 기반 피부 상태 분석 엔진
- **MediaPipe**: 얼굴 감지 (blaze_face_short_range.tflite)
- **Strategy 패턴**: AnalyzerRegistry를 통한 동적 분석기 등록
- **config.json 기반**: 분석기 활성화/비활성화 설정 지원

---

## 3. 주요 기능

### 3.1 이미지 복원

**개요**: 고품질 얼굴 이미지 복원을 제공합니다.

**지원 엔진**:
- **RestoreFormer++**: 고급 이미지 복원 모델
- **CodeFormer**: 얼굴 특화 복원 모델

**특징**:
- Strategy Pattern 기반 엔진 교체 가능
- RestorerRegistry를 통한 동적 엔진 선택
- 전처리/후처리 훅 지원
- in-process 실행 지원 (cold-start 방지)
- 순차 실행 지원 (RF++ → CodeFormer)

**사용 예시**:
```python
from src.restoration import RestorerRegistry

# 엔진 선택 및 인스턴스 생성
restorer = RestorerRegistry.create("codeformer_v1", config={"repo": "/path/to/CodeFormer"})

# 복원 실행
result = restorer.restore("input.jpg", "output.jpg")
```

**자세한 가이드**: [RESTORATION_ENGINE_GUIDE.md](guides/RESTORATION_ENGINE_GUIDE.md)

---

### 3.2 피부 분석

**개요**: 18개 측정항목 기반 정밀한 피부 상태 분석을 제공합니다.

**측정항목 (18개)**:
- **색소 (2개)**: melasma_score, freckle_score
- **홍조 (2개)**: redness_score, post_inflammatory_erythema_score
- **트러블 (2개)**: acne_score, post_acne_pigment_score
- **모공 (2개)**: pore_size_score, pore_sagging_score
- **주름 (3개)**: eye_wrinkle_score, nasolabial_wrinkle_score, fine_deep_wrinkle_score
- **텍스처 (1개)**: roughness_score
- **톤 (3개)**: skin_tone_score, dullness_score, uneven_tone_score
- **탄력 (2개)**: jawline_blur_score, cheek_sagging_score
- **피부 타입 (1개)**: skin_type_score

**분석기 (6개)**:
- PigmentationAnalyzerV1: 색소 분석
- RednessAnalyzerV1: 홍조 분석
- PoreAnalyzerV1: 모공 분석
- WrinkleAnalyzerV1: 주름/결 분석
- ToneElasticityAnalyzerV1: 톤/탄력 분석
- AcneAnalyzerV1: 여드름 분석

**특징**:
- Strategy Pattern 기반 분석기 교체 가능
- AnalyzerRegistry를 통한 동적 분석기 선택
- config.json 기반 활성화/비활성화 설정
- 직교 신호 분해 (10개 내부 신호)
- 가중치 체계 삼원화 (레이어A/레이어B/레거시)

**출력 예시**:
```json
{
  "measurements": {
    "melasma_score": 75,
    "freckle_score": 80,
    "redness_score": 67,
    ...
  },
  "overall_score": 72.5
}
```

---

### 3.3 AI 소견 생성

**개요**: Google Gemini를 활용한 전문 피부 소견 생성을 제공합니다.

**특징**:
- Strategy Pattern 기반 LLM 교체 가능
- LLMRegistry를 통한 동적 LLM 선택
- 듀얼 이미지 소견 (원본/복원 비교)
- 맞춤형 화장품 성분 정보 통합
- 설문 응답 기반 맞춤 소견

**LLM 엔진**:
- GeminiLLM: Google Gemini 2.5 Pro

---

### 3.4 맞춤형 화장품 추천

**개요**: 설문 응답과 측정 점수를 기반으로 맞춤형 화장품을 추천합니다.

**특징**:
- ProductTable DB 기반 제품 정보 관리
- 다중 매칭 기준 (고민사항, 피부 타입, 측정 점수)
- match_score 계산 및 정렬
- 최대 3개 제품 추천
- 성분 정보 기반 추천

**매칭 기준**:
- 고민사항 기반 매칭 (+0.5 점)
- 피부 타입 기반 매칭 (+0.3 점)
- 측정 점수 기반 매칭 (+0.2 점)

---

### 3.5 처방 시스템

**개요**: 피부 측정 점수 기반 처방전 생성 및 제품 매칭을 제공합니다.

**특징**:
- PrescriptionCalculator로 처방전 생성
- PCR (Prescription Calculator Rules) 기반 처방
- 믹스 코드 기반 처방 항목 구성
- ProductRepository로 제품 매칭
- base 비율 계산 (중복 제거)

**처방 계산 프로세스**:
1. 피부 측정 점수 수집 (18개 항목)
2. 나이대 그룹 매핑 (AGE_GROUP_MAPPING)
3. PCR 규칙 적용 (total, beneficial, trouble, harmful)
4. 믹스 코드 계산 (M01~M10)
5. 처방 항목 생성 (base 비율 포함)
6. 제품 매칭 (ProductRepository)

---

### 3.6 실행 이력 추적

**개요**: SQLite 기반 실행 이력 추적 및 리소스 모니터링을 제공합니다.

**특징**:
- ExecutionHistoryDB: 실행 이력 저장
- 로그 DB: 애플리케이션 로그 저장
- 롤링 방식 자동 정리
- 리소스 사용량 모니터링
- 성능 메트릭 추적

**저장 데이터**:
- executions: 분석 작업 실행 이력 (90일)
- logs: 애플리케이션 로그 (30일)
- analysis_stats: 일별 분석 통계 (365일)
- model_performance: 모델 성능 메트릭 (90일)
- score_trends: 고객별 점수 추이 (무제한)
- gemini_api_stats: Gemini API 사용 통계 (365일)

---

### 3.7 보안 기능

**개요**: JWT 인증, 역할 기반 접근 제어, 감사 로그 등 보안 기능을 제공합니다.

**특징**:
- JWT 인증 (시크릿 키 검증)
- 역할 기반 접근 제어 (RBAC)
- 감사 로그 (접근 기록)
- 속도 제한 (분석 엔드포인트 3/분)
- SSRF 방어 (도메인명 차단)
- Path traversal 방어 (파일명 검증)
- 고객 공유 패스워드 제거

**역할**:
- admin: 모든 권한
- customer: 자신의 데이터만 접근

---

### 3.8 외부 시스템 연동

**개요**: 웹훅, 콜백 URL, OAuth, WebSocket을 통한 외부 시스템 연동을 제공합니다.

**특징**:
- 웹훅 관리 (등록, 조회, 수정, 삭제)
- 콜백 URL 지원 (분석 완료 시 알림)
- OAuth/SSO 연동 (Google, 등)
- 데이터 동기화 (고객, 제품)
- WebSocket 실시간 진행률 전송
- CORS 설정 (외부 도메인 접근 허용)

**지원 연동 방식**:
- 웹훅: 이벤트 기반 알림
- 콜백 URL: 비동기 작업 완료 알림
- 데이터 동기화: 고객/제품 데이터 동기화
- OAuth/SSO: 통합 인증
- WebSocket: 실시간 진행률 전송
- REST API: 표준 HTTP 기반 통신

**자세한 가이드**: [EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md](EXTERNAL_SYSTEM_INTEGRATION_GUIDE.md)

---

### 3.9 버전 관리

SkinLens v1.0은 여러 층위에서 버전을 관리합니다. 각 버전은 독립적인 목적을 가지며 서로 다른 주기로 업데이트됩니다.

| 버전 | 위치 | 현재 값 | 목적 | 업데이트 주기 |
|------|------|---------|------|--------------|
| **프로젝트 버전** | `src/version.py`<br/>`pyproject.toml`<br/>`docs/PROJECT_OVERVIEW.md` | `1.0.0` | 전체 프로젝트 릴리스 버전 | 메이저 릴리스 시 |
| **API 버전** | `src/server/server.py`<br/>`config.json` | `v3` | API 호환성 관리 | API 변경 시 |
| **설정 버전** | `src/config/config_manager.py`<br/>`config.json` | `3.6` | config.json 구조 버전 | 설정 구조 변경 시 |
| **DB 스키마 버전** | `src/db/skin_analysis_db.py`<br/>`schema_version` 테이블 | `32` | 데이터베이스 마이그레이션 버전 | 스키마 변경 시 |
| **프롬프트 버전** | `src/llm/prompt_manager.py`<br/>프롬프트 파일명 | `v1` | LLM 프롬프트 템플릿 버전 | 프롬프트 변경 시 |
| **텔레그램 모듈 버전** | `src/telegram/__init__.py` | `3.0.0` | 텔레그램 봇 모듈 버전 | 텔레그램 기능 변경 시 |

---

## 4. 아키텍처

자세한 아키텍처 정보는 [ARCHITECTURE_GUIDE.md](guides/ARCHITECTURE_GUIDE.md)를 참조하세요.

### 4.1 시스템 구성도

전체 시스템 아키텍처는 다음과 같습니다:

- **사용자 인터페이스**: GUI (PySide6), CLI (argparse), API 서버 (FastAPI), 텔레그램 Bot
- **파이프라인 코어**: pipeline_core.py
- **복원 모델**: RestoreFormer++, CodeFormer
- **피부 분석**: SkinAnalyzerV3 (18개 측정항목)
- **Gemini AI**: 소견 생성
- **실행 이력**: SQLite (execution_history.py)

### 4.2 데이터 처리 흐름

데이터 처리 흐름은 다음과 같습니다:

1. **입력 단계**: 이미지, 설문 JSON, 클라이언트 메타, config.json
2. **복원 엔진**: RestorerRegistry → CodeFormer/RestoreFormer
3. **분석기 엔진**: AnalyzerRegistry → 6개 분석기
4. **데이터베이스**: ExecutionHistoryDB, SkinAnalysisDB, ProductTable
5. **LLM 엔진**: LLMRegistry → GeminiLLM
6. **처방 시스템**: PrescriptionCalculator, ProductRepository

### 4.3 프로젝트 구조

자세한 프로젝트 구조는 [JSON_IO_FLOW.md](guides/JSON_IO_FLOW.md)를 참조하세요.

---

## 5. 디렉토리 구조

```
SkinLens v1.0/
├── src/                        # 소스 코드
│   ├── cli/                    # CLI 모듈
│   │   └── skin_analysis_cli.py    # CLI 진입점
│   ├── gui/                    # GUI 모듈
│   │   ├── image_enhancer.py        # 메인 GUI
│   │   ├── analyzer_compare_gui.py  # 비교 GUI
│   │   └── compare_dialog.py        # 비교 다이얼로그
│   ├── server/                 # FastAPI 서버
│   │   ├── server.py               # API 서버
│   │   └── deps.py                 # 서버 의존성
│   ├── telegram/               # 텔레그램 모듈
│   │   ├── bridge.py               # 통합 브리지
│   │   ├── commands.py             # 명령 핸들러
│   │   ├── monitors.py             # 모니터링 믹스인
│   │   ├── notifier.py             # 알림 발송
│   │   └── formatters.py           # 메시지 포맷터
│   ├── skin/                   # 피부 분석 코어
│   │   ├── core/                    # 핵심 분석 로직
│   │   │   ├── face_detector.py      # 얼굴 감지
│   │   │   └── image_utils.py        # 이미지 유틸리티
│   │   ├── analyzers/              # 분석기 전략
│   │   │   ├── pigmentation.py      # 색소 분석
│   │   │   ├── redness.py           # 홍조 분석
│   │   │   ├── pore.py              # 모공 분석
│   │   │   ├── wrinkle_texture.py   # 주름/결 분석
│   │   │   ├── tone_elasticity.py   # 톤/탄력 분석
│   │   │   └── acne.py              # 여드름 분석
│   │   ├── compose/                # 점수 조합
│   │   │   └── score_composition.py # 점수 조합 로직
│   │   └── strategies/             # 분석기 전략 패턴
│   ├── pipeline/               # 파이프라인
│   │   └── pipeline_core.py        # 복원 파이프라인
│   ├── scoring/                # 점수 계산
│   │   ├── skin_scoring.py         # 피부 점수 계산
│   │   ├── _core.py                # 핵심 분석 로직
│   │   └── _multi_view.py          # 다중 뷰 분석
│   ├── llm/                    # LLM 모듈
│   │   ├── llm_reporter.py         # LLM 소견 생성
│   │   ├── llm_prompt_builder.py   # 프롬프트 빌더
│   │   └── llm_providers.py        # LLM 제공자
│   ├── db/                     # 데이터베이스
│   │   ├── db_cli.py               # DB CLI
│   │   └── repositories.py         # DB 리포지토리
│   ├── restoration/             # 복원 모듈
│   │   └── restoration_manager.py  # 복원 관리자
│   ├── prescription/           # 처방전 모듈
│   │   └── prescription_manager.py # 처방전 관리자
│   └── utils/                  # 공통 유틸리티
│       └── ...
├── models/                     # 외부 모델 (git 제외)
│   ├── CodeFormer/              # CodeFormer 모델
│   └── RestoreFormerPlusPlus/  # RestoreFormer++ 모델
├── config/                     # 설정 파일
│   ├── config.json             # 메인 설정
│   └── config.secrets.json     # 비밀 설정 (git 제외)
├── docs/                       # 문서
│   ├── *.md                    # 마크다운 문서
│   ├── api/                    # API 문서
│   ├── db/                     # DB 문서
│   ├── design/                 # 디자인 문서
│   ├── guides/                 # 개발 가이드
│   ├── ops/                    # 운영 가이드
│   ├── project/                # 프로젝트 관리
│   └── user/                   # 사용자 가이드
├── results/                    # 결과 파일 (git 제외)
│   ├── 이미지명/               # 분석 결과별 폴더
│   ├── skin_analysis.db        # 통합 DB (서버 + 로컬)
│   ├── execution_history.db    # 실행 기록 DB
│   ├── api_jobs/               # 서버 API 작업
│   ├── exports/                # 엑셀/CSV 내보내기
│   ├── images/                 # 입력 이미지 저장소
│   ├── logs/                   # 로그 파일
│   └── weights/                # 모델 가중치
├── scripts/                    # 유틸리티 스크립트
│   ├── batch_report.py         # 배치 리포트
│   ├── bp_optimizer.py         # 백포인트 최적화
│   ├── score_bias_monitor.py   # 점수 편향 모니터링
│   ├── check_llm_models.py    # LLM 모델 확인
│   ├── monitors.py             # 시스템 모니터링
│   └── deploy/                # 배포 스크립트
│       ├── deploy.ps1
│       └── deploy.sh
├── tests/                      # 테스트
│   ├── test_*.py               # 단위/통합 테스트
│   └── README.md               # 테스트 가이드
├── main.py                     # 메인 진입점
├── pyproject.toml              # 프로젝트 설정
├── requirements.txt            # 전체 의존성
├── requirements-core.txt       # 코어 의존성 (서버/CLI)
├── requirements-dev.txt        # 개발 의존성
├── requirements-gui.txt        # GUI 의존성
├── pytest.ini                  # pytest 설정
├── README.md                   # 프로젝트 README
└── PROJECT_OVERVIEW.md         # 이 파일
```

---

## 6. 사용법

### 6.1 사전 요구사항

- Python 3.8+
- CUDA 11.8+ (GPU 사용 시)
- 16GB+ RAM (GPU 사용 권장)

### 6.2 설치

```bash
# 코어 의존성 설치 (서버/CLI)
pip install -r requirements-core.txt

# GUI 의존성 설치 (GUI 모드 사용 시)
pip install -r requirements-gui.txt
```

### 6.3 GUI 모드

```bash
python main.py
```

### 6.4 CLI 모드

```bash
# 기본 사용
python main.py --cli -i input.jpg -o output_dir

# LLM 소견 비활성화
python main.py --cli -i input.jpg -o output_dir --no-llm-report

# 비동기 모드
python main.py --cli -i input.jpg -o output_dir --async
```

### 6.5 API 서버

```bash
python main.py
# 또는
uvicorn src.server.server:app --host 0.0.0.0 --port 8000
```

### 6.6 API 엔드포인트

- `GET /health`: 헬스 체크
- `POST /v1/analysis/jobs`: 분석 Job 생성
- `GET /v1/analysis/jobs/{job_id}`: Job 상태 조회
- `GET /v1/analysis/jobs/{job_id}/result`: Job 결과 조회
- `GET /v1/analysis/jobs/{job_id}/artifacts/{name}`: 아티팩트 다운로드

---

## 7. 환경변수

### 7.1 실행 이력

- `EXECUTION_HISTORY_DB`: 실행 이력 데이터베이스 경로 (기본: execution_history.db)

### 7.2 API 서버

- `SKIN_API_JOBS_DIR`: Job 저장 루트 디렉토리 (기본: ./results/api_jobs)
- `SKIN_API_MAX_WORKERS`: 백그라운드 워커 스레드 수 (기본: 2)
- `SKIN_API_URL_TIMEOUT`: URL 다운로드 타임아웃 (초, 기본: 10)
- `SKIN_API_URL_MAX_BYTES`: URL 다운로드 최대 크기 (바이트, 기본: 10MB)

### 7.3 텔레그램

- `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
- `TELEGRAM_CHAT_ID`: 텔레그램 채트 ID

### 7.4 Gemini AI

- `GEMINI_API_KEY`: Google Gemini API 키

### 7.5 보안

- `JWT_SECRET_KEY`: JWT 토큰 시크릿 키 (프로덕션에서 반드시 변경)
- `ALLOWED_ORIGINS`: CORS 허용 오리진 (콤마로 구분)

---

## 8. 테스트

### 8.1 테스트 실행

```bash
# 모든 테스트
pytest tests/ -v

# CLI 테스트
pytest tests/test_cli.py -v

# 서버 테스트
pytest tests/test_server.py -v
```

### 8.2 테스트 커버리지

- `test_cli.py`: CLI 파이프라인 및 파라미터 테스트
- `test_server.py`: FastAPI API 엔드포인트 테스트
- `test_config.py`: 설정 파일 로드 및 유효성 테스트

---

## 9. DB 관리

### 9.1 CLI 명령어

```bash
# DB 백업
python src/db/db_cli.py backup

# DB 상태 확인
python src/db/db_cli.py status

# DB 마이그레이션
python src/db/db_cli.py migrate

# 데이터 아카이빙
python src/db/db_cli.py archive --days=90
```

### 9.2 DB Health Check API

```bash
# DB 상태 확인
curl http://localhost:8000/v1/health/db

# DB 메트릭 (관리자 전용)
curl http://localhost:8000/v1/admin/db/metrics \
  -H "Authorization: Bearer <admin_token>"
```

---

## 10. 배포

### 10.1 배포 패키지 생성

민감 정보를 제외한 배포용 ZIP 패키지를 생성합니다.

#### Linux/macOS

```bash
chmod +x deploy.sh
./deploy.sh
```

#### Windows (PowerShell)

```powershell
.\deploy.ps1
```

### 10.2 제외되는 파일/디렉토리

- **민감 정보**: `config/config.secrets.json`, `*.secrets.json`, `.env`
- **모델 가중치**: `RestoreFormerPlusPlus/weights/`, `CodeFormer/weights/`
- **런타임 생성**: `results/`, `backup/`, `*.db`, `__pycache__/`
- **Python 패키지**: `*.egg-info/`, `dist/`, `build/`, `.venv/`

### 10.3 배포 후 설정

1. **비밀 설정 파일 생성**: `config/config.secrets.json` 복사 및 실제 값 입력
2. **환경 변수 설정**: `.env` 파일 생성 또는 시스템 환경 변수 설정
3. **모델 가중치 다운로드**: `models/` 디렉토리에 필요한 가중치 파일 배치

---

## 11. 코드 리뷰 반영

### 11.1 보안 강화

- **JWT 시크릿 키 검증**: 서버 시작 시 기본값 사용 시 거부
- **분석 엔드포인트 Rate Limit**: 3회/분 제한 적용
- **DB 테이블 중복 생성 제거**: 암호화 클래스에서 테이블 초기화 제거

### 11.2 코드 구조 개선

- **DB 초기화 함수 분리**: 260줄 단일 함수를 4개 서브 함수로 분리
- **트랜잭션 추가**: DB 초기화 시 트랜잭션으로 원자성 보장
- **Repository 패턴**: ExecutionHistoryDB를 여러 Repository로 분리 계획

### 11.3 리팩토링

- **SD 기능 제거**: Stable Diffusion 기능 완전 제거 (2026-05-16)
- **모공 완화 기능 제거**: 파이프라인 단순화 (2026-05-16)
- **매직넘버 외부 주입**: config.json으로 설정 외부화 (2026-05-16)

---

## 12. 기능 현황

### 12.1 현재 지원되는 기능

다음 기능들은 이미 구현이 완료되어 사용할 수 있습니다.

#### 핵심 기능
- **이미지 복원**: RestoreFormer++, CodeFormer를 활용한 고품질 얼굴 이미지 복원
- **피부 분석**: 18개 측정항목 기반 정밀한 피부 상태 분석
- **AI 소견 생성**: Google Gemini를 활용한 전문 피부 소견 생성
- **맞춤형 화장품 추천**: 설문 응답과 측정 점수 기반 제품 추천
- **처방 시스템**: 피부 측정 점수 기반 처방전 생성 및 제품 매칭

#### 운영 기능
- **실행 이력 추적**: SQLite 기반 실행 이력 및 리소스 모니터링
- **보안 기능**: JWT 인증, 역할 기반 접근 제어, 감사 로그
- **장애 자동 복구**: 장애 감지 시 자동 복구, 헬스 체크 API, 알림 시스템 (Slack, PagerDuty)

#### 사용자 경험
- **다국어 지원**: 한국어, 영어, 중국어, 일본어 지원 (API 응답 자동 번역)
- **피부 타입 자동 감지**: 이미지 분석을 통한 피부 타입 자동 분류 (지성, 건성, 복합성, 민감성)

#### 인터페이스
- **GUI 모드**: PySide6 기반 그래픽 사용자 인터페이스
- **CLI 모드**: 명령줄 인터페이스
- **API 서버**: FastAPI 기반 REST API
- **텔레그램 봇**: 텔레그램을 통한 분석 요청 및 결과 전송

### 12.2 향후 지원 예정 기능

다음 기능들은 설계 문서가 작성되었으며, 향후 구현 예정입니다.

#### 분석 기능 강화
- **지역별 복원**: 눈, 입 등 특정 얼굴 영역 선택적 복원 (설계 문서: `REGIONAL_RESTORATION_DESIGN.md`)
- **실시간 복원 미리보기**: 슬라이더로 복원 강도 조절 및 실시간 미리보기 (설계 문서: `REALTIME_RESTORATION_PREVIEW_DESIGN.md`)
- **다중 이미지 분석**: 여러 이미지 비교 분석 (설계 문서: `MULTI_IMAGE_ANALYSIS_DESIGN.md`)
- **시계열 분석 (이력 비교)**: 과거 분석 결과와 비교하여 변화 추이 시각화 (설계 문서: `TIME_SERIES_ANALYSIS_DESIGN.md`)

#### 처방 기능 강화
- **처방 효과 예측**: 처방 사용 후 예상 점수 개선 시뮬레이션 (설계 문서: `PRESCRIPTION_EFFECT_PREDICTION_DESIGN.md`)
- **처방 이력 추적**: 처방 사용 이력 및 효과 분석 (설계 문서: `PRESCRIPTION_HISTORY_TRACKING_DESIGN.md`)
- **제품 리뷰 통합**: 실제 사용자 리뷰 점수를 제품 매칭에 반영 (설계 문서: `PRODUCT_REVIEW_INTEGRATION_DESIGN.md`)
- **가격 필터**: 가격 범위별 제품 추천 필터링 (설계 문서: `PRICE_FILTER_DESIGN.md`)

#### 보안 및 개인정보 보호
- **얼굴 인증**: 생체 인증을 통한 보안 강화 (설계 문서: `FACE_AUTHENTICATION_DESIGN.md`)
- **이미지 암호화**: 클라이언트 단계 이미지 암호화 (AES-256-GCM) (설계 문서: `IMAGE_ENCRYPTION_DESIGN.md`)
- **GDPR 준수**: 데이터 삭제 권한, 데이터 이동 권한 (설계 문서: `GDPR_COMPLIANCE_DESIGN.md`)

#### 운영 효율성
- **자동 스케일링**: 트래픽에 따른 자동 리소스 스케일링 (설계 문서: `AUTO_SCALING_DESIGN.md`)
- **A/B 테스트 프레임워크**: 분석 알고리즘 A/B 테스트 (설계 문서: `AB_TESTING_FRAMEWORK_DESIGN.md`)

#### 사용자 경험
- **진단 피드백 루프**: 사용자 피드백을 통한 LLM 재학습 (설계 문서: `DIAGNOSIS_FEEDBACK_LOOP_DESIGN.md`)
- **오프라인 모드**: 인터넷 연결 없이 기본 분석 기능 제공 (설계 문서: `OFFLINE_MODE_DESIGN.md`)
- **푸시 알림**: 분석 완료 등 이벤트 푸시 알림 (설계 문서: `PUSH_NOTIFICATION_DESIGN.md`)
- **분석 결과 공유**: SNS 공유, PDF 리포트 다운로드 (설계 문서: `ANALYSIS_RESULT_SHARING_DESIGN.md`)

---

## 13. 로드맵

### 13.1 단기 계획

- **Repository 패턴 분리**: ExecutionHistoryDB를 여러 Repository로 분리
- **LLM 프롬프트 최적화**: 점수/소견 일치성 개선
- **이미지 리사이징 최적화**: API 전송 전 자동 리사이징

### 13.2 중기 계획

- **성능 최적화**: GPU 활용 최적화, 배치 처리
- **모델 업데이트**: 최신 복원 모델 통합
- **분석 기능 강화**: 지역별 복원, 실시간 미리보기 등 설계된 기능 구현

### 13.3 장기 계획

- **클라우드 배포**: AWS/GCP 클라우드 배포
- **모바일 앱**: iOS/Android 모바일 앱 개발
- **AI 모델 커스터마이징**: 사용자별 맞춤형 모델 학습

---

## 14. 문서

### API 문서 (docs/api/)
- [API_GUIDE.md](api/API_GUIDE.md): API 서버 상세 가이드
- [API_DOCUMENTATION.md](api/API_DOCUMENTATION.md): API 엔드포인트 참조

### 사용자 가이드 (docs/user/)
- [USER_GUIDE.md](user/USER_GUIDE.md): 사용자 매뉴얼
- [PRODUCT_PURCHASE_GUIDE.md](user/PRODUCT_PURCHASE_GUIDE.md): 제품 구매 가이드
- [SERUM_PRESCRIPTION_CUSTOMER_GUIDE.md](user/SERUM_PRESCRIPTION_CUSTOMER_GUIDE.md): 처방전 고객 가이드
- [MOBILE_APP_GUIDE.md](user/MOBILE_APP_GUIDE.md): 모바일 앱 가이드

### 운영 가이드 (docs/ops/)
- [DEPLOYMENT_GUIDE.md](ops/DEPLOYMENT_GUIDE.md): 배포 가이드
- [MONITORING_GUIDE.md](ops/MONITORING_GUIDE.md): 모니터링 가이드
- [INCIDENT_RESPONSE_GUIDE.md](ops/INCIDENT_RESPONSE_GUIDE.md): 장애 대응 가이드
- [SERVER_TEST_GUIDE.md](ops/SERVER_TEST_GUIDE.md): 서버 테스트 가이드
- [LINUX_DOCKER_DEPLOYMENT.md](ops/LINUX_DOCKER_DEPLOYMENT.md): 리눅스 Docker 배포 가이드

### 기술 가이드 (docs/guides/)
- [LLM_PROMPT_TEMPLATE.md](guides/LLM_PROMPT_TEMPLATE.md): LLM 프롬프트 템플릿
- [SKIN_SCORING_GUIDE.md](guides/SKIN_SCORING_GUIDE.md): 18개 측정항목 상세 (가중치·측정원리·ROI), 점수 척도, 카테고리 배분
- [PRESCRIPTION_GUIDE.md](guides/PRESCRIPTION_GUIDE.md): 처방전 구성 (M01~M10 + PCR 3종), 처방 생성 플로우차트, 베이스 비율 계산
- [ARCHITECTURE_GUIDE.md](guides/ARCHITECTURE_GUIDE.md): Strategy 패턴 (분석기·복원기·LLM), DB 구조, 의존성 방향도
- [CODE_REVIEW_HISTORY.md](project/CODE_REVIEW_HISTORY.md): 코드 리뷰 결과, 리팩토링 이력, 변경 명세서
- [JSON_IO_FLOW.md](guides/JSON_IO_FLOW.md): 데이터 처리 흐름
- [DEVELOPMENT_GUIDE.md](guides/DEVELOPMENT_GUIDE.md): 개발 가이드
- [IMPROVEMENT_PLAN.md](project/IMPROVEMENT_PLAN.md): 개선 계획

### 기능 설계 문서 (docs/design/)
- [REGIONAL_RESTORATION_DESIGN.md](design/REGIONAL_RESTORATION_DESIGN.md): 지역별 복원 기능 설계
- [REALTIME_RESTORATION_PREVIEW_DESIGN.md](design/REALTIME_RESTORATION_PREVIEW_DESIGN.md): 실시간 복원 미리보기 기능 설계
- [PRESCRIPTION_EFFECT_PREDICTION_DESIGN.md](design/PRESCRIPTION_EFFECT_PREDICTION_DESIGN.md): 처방 효과 예측 기능 설계
- [PRESCRIPTION_HISTORY_TRACKING_DESIGN.md](design/PRESCRIPTION_HISTORY_TRACKING_DESIGN.md): 처방 이력 추적 기능 설계
- [PRODUCT_REVIEW_INTEGRATION_DESIGN.md](design/PRODUCT_REVIEW_INTEGRATION_DESIGN.md): 제품 리뷰 통합 기능 설계
- [PRICE_FILTER_DESIGN.md](design/PRICE_FILTER_DESIGN.md): 가격 필터 기능 설계
- [MULTI_LANGUAGE_SUPPORT_DESIGN.md](design/MULTI_LANGUAGE_SUPPORT_DESIGN.md): 다국어 지원 기능 설계
- [DIAGNOSIS_FEEDBACK_LOOP_DESIGN.md](design/DIAGNOSIS_FEEDBACK_LOOP_DESIGN.md): 진단 피드백 루프 기능 설계
- [OFFLINE_MODE_DESIGN.md](design/OFFLINE_MODE_DESIGN.md): 오프라인 모드 기능 설계
- [PUSH_NOTIFICATION_DESIGN.md](design/PUSH_NOTIFICATION_DESIGN.md): 푸시 알림 기능 설계
- [ANALYSIS_RESULT_SHARING_DESIGN.md](design/ANALYSIS_RESULT_SHARING_DESIGN.md): 분석 결과 공유 기능 설계
- [FACE_AUTHENTICATION_DESIGN.md](design/FACE_AUTHENTICATION_DESIGN.md): 얼굴 인증 기능 설계
- [IMAGE_ENCRYPTION_DESIGN.md](design/IMAGE_ENCRYPTION_DESIGN.md): 이미지 암호화 기능 설계
- [GDPR_COMPLIANCE_DESIGN.md](design/GDPR_COMPLIANCE_DESIGN.md): GDPR 준수 기능 설계
- [AB_TESTING_FRAMEWORK_DESIGN.md](design/AB_TESTING_FRAMEWORK_DESIGN.md): A/B 테스트 프레임워크 설계
- [AUTO_SCALING_DESIGN.md](design/AUTO_SCALING_DESIGN.md): 자동 스케일링 기능 설계
- [AUTO_RECOVERY_DESIGN.md](design/AUTO_RECOVERY_DESIGN.md): 장애 자동 복구 기능 설계

### 기타
- [README.md](../README.md): 프로젝트 기본 정보
- [tests/README.md](../tests/README.md): 테스트 가이드

---

## 15. 라이선스

이 프로젝트는 상업적 목적으로 사용됩니다.

---

## 16. 연락처

프로젝트 관련 문의사항은 프로젝트 관리자에게 문의하세요.

---

## 17. 문서 갱신 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (v1.0에서 마이그레이션) | Cascade |
| 0.1.0 | 2026-05-31 | 문서 구조 재정리, 섹션 번호 정리, 중복 내용 제거 | Cascade |
| 0.0.8 | 2026-05-24 | 기능 현황 섹션 추가, 장애 자동 복구 기능 구현 완료, 다국어 지원 기능 구현 완료 | Cascade |
| 0.0.7 | 2026-05-24 | 직교 신호 분해 개선, 유연한 구조 설계 | Cascade |
| 0.0.6 | 2026-05-24 | 측정항목 17개 → 18개로 변경 (볼 처짐 추가), LLM JSON 파싱 재시도 로직 추가, 처방 시스템 보완, config.json 설정 중앙화, Strategy 패턴 도입, 문서 체계 재편 | Cascade |
| 0.0.5 | 2026-05-16 | SD 기능 제거, 모공 완화 기능 제거, 매직넘버 외부 주입 | Cascade |
| 0.0.4 | 2026-05-15 | Repository 패턴 분리 계획, 보안 강화, 코드 구조 개선 | Cascade |
