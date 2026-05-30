# 테스트 가이드

이 문서는 SkinLens v1 프로젝트의 테스트 구조, 실행 방법, 작성 가이드라인을 상세하게 설명합니다.

## 목차

1. [테스트 개요](#테스트-개요)
2. [테스트 실행](#테스트-실행)
3. [테스트 구조](#테스트-구조)
4. [테스트 작성 가이드라인](#테스트-작성-가이드라인)
5. [테스트 커버리지](#테스트-커버리지)
6. [트러블슈팅](#트러블슈팅)
7. [CI/CD 통합](#cicd-통합)

---

## 테스트 개요

SkinLens v1 테스트 스위트는 다음 계층을 커버합니다:

- **Core Tests**: CLI, 서버, 애널라이저 핵심 기능
- **DB Tests**: 데이터베이스 기능, API, CLI
- **API Tests**: 인증, 관리자, 헬스 체크, 주문 API
- **Repository Tests**: 8개 CLI Repository 계층
- **Scoring Tests**: 점수 계산, 브레이크포인트, 보고서 생성
- **Recovery Tests**: 자동 복구 엔진

### 테스트 철학

1. **단위 테스트 우선**: 각 모듈을 독립적으로 테스트
2. **Mock 기반**: 외부 의존성은 mock으로 대체하여 빠른 실행
3. **통합 테스트 분리**: 실제 환경 테스트는 별도 파일로 관리
4. **커버리지 중시**: 성공/실패, 엣지 케이스, 에러 처리 모두 포함

---

## 테스트 실행

### 환경 설정

테스트 실행 전 다음 의존성이 필요합니다:

```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

### 모든 테스트 실행

```bash
cd c:\Project\SkinLens v1
pytest tests/ -v
```

또는 배치 파일 사용:
```bash
scripts\run_all_tests.bat
```

### 특정 테스트 파일 실행

```bash
# CLI 테스트
pytest tests/test_cli.py -v

# 서버 테스트
pytest tests/test_server.py -v

# DB 기능 테스트
pytest tests/test_db_features.py -v

# DB API 테스트
pytest tests/test_db_api.py -v

# DB CLI 테스트
pytest tests/test_db_cli.py -v

# 애널라이저 테스트
pytest tests/test_analyzers.py -v

# API 테스트
pytest tests/test_auth_api.py -v
pytest tests/test_admin_api.py -v
pytest tests/test_health_api.py -v
pytest tests/test_orders_api.py -v

# Repository 테스트
pytest tests/test_repository_*.py -v

# Scoring 테스트
pytest tests/test_scoring_*.py -v

# Recovery 테스트
pytest tests/test_recovery_engine.py -v
```

### 특정 테스트 카테고리 실행

```bash
# 모든 API 테스트
pytest tests/test_*_api.py -v

# 모든 Repository 테스트
pytest tests/test_repository_*.py -v

# 모든 Scoring 테스트
pytest tests/test_scoring_*.py -v

# 모든 DB 테스트
pytest tests/test_db_*.py -v
```

### 특정 테스트 클래스 실행

```bash
pytest tests/test_cli.py::TestCLIPipeline -v
pytest tests/test_server.py::TestFastAPIServer -v
pytest tests/test_db_features.py::TestExecutionHistoryDB -v
pytest tests/test_db_api.py::TestDBHealthCheckAPI -v
pytest tests/test_db_cli.py::TestDBCLI -v
pytest tests/test_auth_api.py::TestAuthAPI -v
pytest tests/test_admin_api.py::TestAdminAPI -v
pytest tests/test_health_api.py::TestHealthAPI -v
pytest tests/test_orders_api.py::TestOrdersAPI -v
```

### 특정 테스트 메서드 실행

```bash
pytest tests/test_cli.py::TestCLIPipeline::test_run_analysis_pipeline_basic_params -v
pytest tests/test_server.py::TestFastAPIServer::test_health_check -v
pytest tests/test_db_features.py::TestExecutionHistoryDB::test_check_health_healthy -v
pytest tests/test_db_api.py::TestDBHealthCheckAPI::test_health_db_healthy -v
pytest tests/test_db_cli.py::TestDBCLI::test_backup_command -v
pytest tests/test_auth_api.py::TestAuthAPI::test_login_success -v
```

### 커버리지 리포트 생성

```bash
# 전체 커버리지
pytest tests/ --cov=src --cov-report=html --cov-report=term

# 특정 모듈 커버리지
pytest tests/test_server.py --cov=src/server --cov-report=html
pytest tests/test_repository_*.py --cov=src/cli/repositories --cov-report=html
```

### 상세 출력 모드

```bash
# 매우 상세한 출력
pytest tests/ -vv -s

# 실패한 테스트만 상세 출력
pytest tests/ -v --tb=long
```

### 병렬 실행

```bash
# pytest-xdist 설치 필요
pip install pytest-xdist

# 4개 프로세스로 병렬 실행
pytest tests/ -n 4
```

---

## 테스트 구조

### Core Tests

#### test_cli.py - CLI 모듈 단위 테스트
- **TestCLIPipeline**: 파이프라인 실행 테스트
  - 기본 파라미터 처리
  - 이미지 경로 검증
  - 출력 디렉토리 생성
- **TestCLIParameters**: 파라미터 처리 테스트
  - 파라미터 파싱
  - 기본값 설정
  - 유효성 검사

#### test_server.py - FastAPI 서버 단위 테스트
- **TestFastAPIServer**: API 엔드포인트 테스트
  - POST /analyze 정상 동작
  - GET /jobs/{id} 상태 조회
  - 파일 업로드 크기 제한
  - 지원되지 않는 파일 형식 거부
  - URL 기반 이미지 다운로드
  - 다중 이미지 업로드
  - CORS 헤더 확인
- **TestConcurrencyControl**: 동시성 제어 테스트
  - MAX_CONCURRENT_JOBS 준수 확인
  - 세마포어 타임아웃 처리
  - ThreadPoolExecutor 설정 확인
- **TestAuthenticationAPI**: 인증 테스트
  - JWT 토큰 생성/검증
  - 관리자/분석가 로그인
  - 인증 없는 접근 거부
- **TestCustomerAPI**: 고객 API 테스트
  - 트렌드 조회
  - 분석 통계 조회
  - 에러 조회
  - 데이터 삭제/내보내기
- **TestWebSocketAPI**: WebSocket 테스트
  - WebSocket 연결
  - 진행 상태 전송
  - 존재하지 않는 Job 처리
- **TestE2EIntegration**: 통합 테스트
  - 엔드투엔드 분석 파이프라인
  - 인증 + 고객 ID 포함 E2E

#### test_analyzers.py - 피부 분석 애널라이저 테스트
- **TestAnalyzers**: 주름, 색소, 톤/탄력 분석 테스트
  - analyze_wrinkle_texture 함수 테스트
  - analyze_pigmentation 함수 테스트
  - analyze_elasticity 함수 테스트
  - 필수 반환 키 검증
  - 파라미터 유효성 검사

### DB Tests

#### test_db_features.py - DB 기능 단위 테스트
- **TestExecutionHistoryDB**: ExecutionHistoryDB 테스트
  - 실행 이력 기록/조회
  - 통계 계산
  - 데이터 정리
- **TestConnectionPool**: 연결 풀 테스트
  - 연결 풀 생성/해제
  - 최대 연결 수 제한
  - 연결 재사용
- **TestDBMigrationManager**: 마이그레이션 관리자 테스트
  - 마이그레이션 적용/롤백
  - 버전 관리
  - 마이그레이션 파일 로드
- **TestArchiveOldData**: 데이터 아카이빙 테스트
  - 오래된 데이터 아카이빙
  - 압축 저장
  - 아카이브 복원
- **TestReadonlyReplica**: 읽기 전용 복제본 테스트
  - 복제본 연결
  - 읽기 전용 제한
  - 동기화 확인
- **TestDBBackupRestore**: 백업/복구 테스트
  - 전체 백업
  - 증분 백업
  - 복구 작업
- **TestDBRetry**: 재시도 메커니즘 테스트
  - 연결 실패 재시도
  - 쿼리 실패 재시도
  - 최대 재시도 횟수

#### test_db_api.py - DB 관리 API 테스트
- **TestDBHealthCheckAPI**: DB Health Check API 테스트
  - DB 연결 상태 확인
  - 테이블 무결성 검사
  - 성능 메트릭 반환
- **TestDBMetricsAPI**: DB Metrics API 테스트
  - 쿼리 성능 메트릭
  - 연결 풀 상태
  - 디스크 사용량
- **TestAuditSummaryAPI**: 감사 로그 요약 API 테스트
  - 감사 로그 집계
  - 일별/주별 통계
  - 이상 활동 감지

#### test_db_cli.py - DB 관리 CLI 테스트
- **TestDBCLI**: DB CLI 명령어 테스트
  - 백업 명령어
  - 복구 명령어
  - 마이그레이션 명령어
  - 정리 명령어
- **TestDBCLIIntegration**: DB CLI 통합 테스트
  - 명령어 조합 실행
  - 에러 처리
  - 롤백 시나리오

### API Tests

#### test_auth_api.py - 인증 API 테스트
- **TestAuthAPI**: 로그인, 현재 사용자, 인증 헬퍼 테스트
  - 로그인 성공/실패
  - 비밀번호 검증
  - 현재 사용자 정보 조회
  - 고객 접근 확인
  - 레이트 리미팅
  - 토큰 만료 처리

#### test_admin_api.py - 관리자 API 테스트
- **TestAdminAPI**: 감사 로그, DB 헬스, 메트릭 테스트
  - 감사 로그 조회
  - DB 헬스 체크
  - DB 메트릭 조회
  - 감사 요약
  - 인증/권한 검증
  - 레이트 리미팅
  - 관리자 전용 엔드포인트

#### test_health_api.py - 헬스 체크 API 테스트
- **TestHealthAPI**: 시스템 헬스, 장애 관리 테스트
  - 기본 헬스 체크
  - 서비스 상태 확인
  - 장애 이벤트 조회
  - 복구 작업 트리거
  - 롤백 트리거
  - 헬퍼 함수 테스트
  - CPU/메모리/디스크 헬스 체크

#### test_orders_api.py - 주문 API 테스트
- **TestOrdersAPI**: 주문 생성, 상태, 취소, 구매 이력 테스트
  - 주문 생성 성공/실패
  - 주문 상태 조회
  - 주문 취소
  - 구매 이력 조회
  - 페이지네이션
  - 데이터 모델 검증
  - 유효성 검사
  - 비즈니스 로직 검증

### Repository Tests

#### test_repository_analysis_stats.py - 분석 통계 레포지토리 테스트
- **TestAnalysisStatsRepository**: 분석 통계, 모델 성능, 점수 추이 테스트
  - 분석 통계 기록/조회
  - 모델 성능 기록/조회
  - 점수 추이 기록/조회
  - 기간 필터링
  - 이동 평균 계산
  - 롤백 처리

#### test_repository_customer_data.py - 고객 데이터 레포지토리 테스트
- **TestCustomerDataRepository**: GDPR 준수 데이터 삭제/내보내기 테스트
  - 고객 데이터 삭제
  - 데이터 내보내기 (JSON)
  - 다중 테이블 처리
  - 롤백 처리
  - GDPR 준수 검증

#### test_repository_error_audit.py - 에러 및 감사 로그 레포지토리 테스트
- **TestErrorAuditRepository**: 에러 추적, 감사 로그 테스트
  - 에러 기록/조회
  - 에러 해결 표시
  - 감사 로그 기록/조회
  - 필터링 기능
  - 롤백 처리

#### test_repository_execution_stats.py - 실행 이력 레포지토리 테스트
- **TestExecutionStatsRepository**: 실행 이력, 통계, 정리 테스트
  - 실행 이력 기록/조회
  - 통계 계산
  - 오래된 레코드 정리
  - 성공/실패 필터링
  - 리소스 사용량 기록

#### test_repository_image_metadata.py - 이미지 메타데이터 레포지토리 테스트
- **TestImageMetadataRepository**: 이미지 메타데이터 관리 테스트
  - 메타데이터 기록/조회
  - 분석 ID 필터링
  - 이미지 타입 필터링
  - EXIF 데이터 처리
  - 다양한 이미지 포맷

#### test_repository_llm_api.py - LLM API 레포지토리 테스트
- **TestLLMAPIRepository**: LLM API 통계 테스트
  - API 호출 기록/조회
  - 토큰 사용량 계산
  - 비용 추정
  - 고객별 통계
  - 시간 기반 필터링

#### test_repository_log.py - 로그 레포지토리 테스트
- **TestLogRepository**: 애플리케이션 로그 관리 테스트
  - 로그 기록/조회
  - 레벨 필터링
  - 시간 기반 필터링
  - CSV/JSON 내보내기
  - 보관 기간 관리
  - 롤링 삭제

#### test_repository_system_health.py - 시스템 헬스 레포지토리 테스트
- **TestSystemHealthRepository**: 시스템 리소스 모니터링 테스트
  - 시스템 헬스 기록/조회
  - CPU/메모리/디스크 모니터링
  - DB 상태 확인
  - 테이블 행 수 확인
  - 느린 쿼리 감지 (미구현)

### Scoring Tests

#### test_scoring_breakpoints.py - 점수 브레이크포인트 테스트
- **TestScoringBreakpoints**: 브레이크포인트 설정, 이미지 처리 파라미터 테스트
  - 기본 브레이크포인트 로드
  - 메트릭별 브레이크포인트 조회
  - 이미지 처리 파라미터 로드
  - CLAHE 파라미터
  - Blob detection 파라미터
  - Freckle detection 파라미터
  - 캐싱 검증
  - 캐시 초기화

#### test_scoring_multi_view.py - 멀티뷰 분석 테스트
- **TestLateralFaceAnalyzer**: 측면 얼굴 분석 테스트
  - 측면 영역 구조
  - ROI 추출
  - Sobel 컴포넌트 계산
  - 눈가 주름 측정
  - 비강 주름 측정
- **TestMultiViewIntegration**: 멀티뷰 통합 테스트
  - 모듈 임포트
  - 클래스 메서드 검증
  - 상수성 검증

#### test_scoring_report.py - 보고서 생성 테스트
- **TestReportLazyAccessors**: 보고서 데이터 접근 테스트
  - 가중치 로드
  - 키 로드
  - 카테고리 로드
  - 표시 이름 로드
  - 캐싱 검증
- **TestComputeOverallScoreReport**: 종합 점수 계산 테스트
  - 기본 점수 계산
  - None 값 처리
  - 잘못된 값 처리
  - 점수 클램핑
- **TestReportLayer**: 보고서 레이어 테스트
  - 기본 빌드
  - raw_measurements 사용
  - v3 데이터 폴백
  - 점수 변환
  - 클램핑
- **TestMeasurementReportString**: 보고서 문자열 테스트
  - 기본 문자열 생성
  - 누락된 필드 처리
  - 구조 검증

#### test_scoring_score_utils.py - 점수 유틸리티 테스트
- **TestScoreMapping**: 점수 매핑 테스트
  - 0-100 → 10-90 매핑
  - 클램핑 검증
  - 조정된 매핑
  - 역매핑
  - 라운드 트립
- **TestApplyMeasurementsDisplay**: 측정값 변환 테스트
  - 변환 적용
  - 불리언 값 건너뛰기
  - 클램핑
- **TestScoreQuantization**: 점수 양자화 테스트
  - 점수 스냅
  - 경계 조건
  - 20단위 양자화
- **TestAdaptiveThreshold**: 적응형 임계값 테스트
  - 기본 계산
  - 마스크 포함
  - 빈 마스크
  - z 파라미터
- **TestActualRangesCache**: 실제 범위 캐시 테스트
  - 범위 로드
  - 캐시 초기화
  - 캐싱 검증

### Recovery Tests

#### test_recovery_engine.py - 자동 복구 엔진 테스트
- **TestIncidentType**: 장애 유형 테스트
  - SERVER_DOWN, DATABASE_DOWN, NETWORK_FAILURE
  - CPU_OVERLOAD, MEMORY_OVERLOAD, DISK_FULL
- **TestSeverity**: 심각도 테스트
  - P0, P1, P2, P3
- **TestRecoveryActionType**: 복구 작업 유형 테스트
  - RESTART, FAILOVER, SCALE_OUT
  - ROLLBACK, DATA_RESTORE
- **TestRecoveryEngine**: 복구 엔진 테스트
  - 초기화
  - 플레이북 등록
  - 장애 감지 및 복구
  - 플레이북 없는 장애 처리
  - 플레이북 실행 성공/실패
  - 각 플레이북 테스트
  - 롤백
- **TestHealthMonitor**: 헬스 모니터 테스트
  - 초기화
  - 모니터링 중지
  - CPU 오버로드 감지
  - 메모리 오버로드 감지
  - 디스크 꽉 참 감지
  - 정상 상태
- **TestRecoveryIntegration**: 복구 통합 테스트
  - Enum 완전성
  - 기본 알림 시스템
  - 전체 복구 흐름

---

## 테스트 작성 가이드라인

### 1. 테스트 파일 명명 규칙

- 테스트 파일은 `test_` 접두사로 시작
- 테스트하는 모듈과 동일한 이름 사용
  - `src/server/routers/auth.py` → `tests/test_auth_api.py`
  - `src/cli/repositories/analysis_stats.py` → `tests/test_repository_analysis_stats.py`

### 2. 테스트 클래스 명명 규칙

- 클래스는 `Test` 접두사로 시작
- 테스트하는 기능을 명확하게 표현
  - `TestAuthAPI`, `TestAnalysisStatsRepository`

### 3. 테스트 메서드 명명 규칙

- 메서드는 `test_` 접두사로 시작
- 테스트하는 기능을 설명적으로 표현
  - `test_login_success`, `test_record_analysis_stat_new_record`

### 4. Fixture 사용

```python
@pytest.fixture
def mock_db():
    """Mock 데이터베이스"""
    db = Mock()
    db.create_incident = Mock(return_value="incident_123")
    return db

@pytest.fixture
def repository(mock_db):
    """Repository 인스턴스"""
    return AnalysisStatsRepository(db_path="test.db")
```

### 5. Mock 사용

```python
from unittest.mock import Mock, AsyncMock, patch

# Mock 객체 생성
mock_service = Mock()
mock_service.method.return_value = "result"

# AsyncMock (비동기 함수)
async_mock = AsyncMock()
async_mock.method.return_value = "result"

# patch 데코레이터
@patch('src.module.ClassName')
def test_method(mock_class):
    mock_class.return_value = Mock()
    # 테스트 코드
```

### 6. 예외 테스트

```python
def test_invalid_input():
    with pytest.raises(ValueError):
        function_with_invalid_input()
```

### 7. 비동기 테스트

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result is not None
```

### 8. 파라미터화 테스트

```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_multiply(input, expected):
    assert multiply_by_two(input) == expected
```

### 9. 테스트 정리

```python
def test_with_cleanup():
    # 테스트 설정
    test_file = create_test_file()
    
    try:
        # 테스트 실행
        result = process_file(test_file)
        assert result is not None
    finally:
        # 정리
        if os.path.exists(test_file):
            os.remove(test_file)
```

---

## 테스트 커버리지

### 현재 커버리지 상태

| 모듈 | 커버리지 | 상태 |
|------|----------|------|
| CLI 파이프라인 | ✅ | 완료 |
| FastAPI 서버 | ✅ | 완료 |
| 데이터베이스 기능 | ✅ | 완료 |
| 피부 분석 애널라이저 | ✅ | 완료 |
| 인증 API | ✅ | 완료 |
| 관리자 API | ✅ | 완료 |
| 헬스 체크 API | ✅ | 완료 |
| 주문 API | ✅ | 완료 |
| Repository 계층 (8개) | ✅ | 완료 |
| Scoring 모듈 (4개) | ✅ | 완료 |
| 자동 복구 엔진 | ✅ | 완료 |

### 향후 계획

- ⏳ Middleware 테스트
- ⏳ DB 모듈 추가 테스트
- ⏳ Utility/Helper 테스트
- ⏳ GUI 테스트 (우선순위 낮음)

---

## 트러블슈팅

### 일반적인 문제

#### 1. ImportError

**문제**: 모듈을 찾을 수 없음
```bash
ModuleNotFoundError: No module named 'src'
```

**해결**:
```bash
# 프로젝트 루트에서 실행
cd c:\Project\SkinLens v1
pytest tests/ -v

# 또는 PYTHONPATH 설정
set PYTHONPATH=c:\Project\SkinLens v1
pytest tests/ -v
```

#### 2. Fixture not found

**문제**: Fixture를 찾을 수 없음
```bash
Fixture 'auth_client' not found
```

**해결**: Fixture가 `conftest.py`에 정의되어 있는지 확인

#### 3. Async test not marked

**문제**: 비동기 테스트가 실패
```bash
RuntimeError: Async test function not marked with @pytest.mark.asyncio
```

**해결**: `@pytest.mark.asyncio` 데코레이터 추가

#### 4. Database locked

**문제**: SQLite 데이터베이스 잠금
```bash
sqlite3.OperationalError: database is locked
```

**해결**: 테스트 간 독립된 데이터베이스 파일 사용 (fixture 활용)

### 디버깅 팁

#### 1. 상세 출력
```bash
pytest tests/ -vv -s
```

#### 2. 특정 테스트 중단점
```python
def test_with_breakpoint():
    import pdb; pdb.set_trace()
    # 테스트 코드
```

#### 3. 실패한 테스트만 재실행
```bash
pytest tests/ --lf
```

#### 4. 마지막으로 실패한 테스트 재실행
```bash
pytest tests/ --ff
```

---

## CI/CD 통합

### GitHub Actions 예시

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install pytest pytest-asyncio pytest-cov httpx
      - name: Run tests
        run: |
          pytest tests/ -v --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

### 로컬 CI 시뮬레이션

```bash
# 전체 테스트 실행
scripts\run_all_tests.bat

# 서버 테스트만 실행
scripts\run_server_tests.bat
```

---

## 참고

- 테스트는 현재 mock 기반으로 작성되어 있어 실제 모델 없이 실행 가능
- 통합 테스트는 별도 파일로 추가 예정
- 배치 파일 `scripts/run_all_tests.bat`로 모든 테스트를 한 번에 실행 가능
- 서버 테스트는 `scripts/run_server_tests.bat`로 실행 가능
- 상세 서버 테스트 가이드는 `tests/README_SERVER_TESTS.md` 참조
