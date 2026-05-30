# 테스트 가이드

## 테스트 실행

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

## 테스트 구조

### Core Tests
- `test_cli.py`: CLI 모듈 단위 테스트
  - `TestCLIPipeline`: 파이프라인 실행 테스트
  - `TestCLIParameters`: 파라미터 처리 테스트

- `test_server.py`: FastAPI 서버 단위 테스트
  - `TestFastAPIServer`: API 엔드포인트 테스트
  - `TestServerHelpers`: 서버 헬퍼 함수 테스트

- `test_analyzers.py`: 피부 분석 애널라이저 테스트
  - `TestAnalyzers`: 주름, 색소, 톤/탄력 분석 테스트

### DB Tests
- `test_db_features.py`: DB 기능 단위 테스트
  - `TestExecutionHistoryDB`: ExecutionHistoryDB 테스트
  - `TestConnectionPool`: 연결 풀 테스트
  - `TestDBMigrationManager`: 마이그레이션 관리자 테스트
  - `TestArchiveOldData`: 데이터 아카이빙 테스트
  - `TestReadonlyReplica`: 읽기 전용 복제본 테스트
  - `TestDBBackupRestore`: 백업/복구 테스트
  - `TestDBRetry`: 재시도 메커니즘 테스트

- `test_db_api.py`: DB 관리 API 테스트
  - `TestDBHealthCheckAPI`: DB Health Check API 테스트
  - `TestDBMetricsAPI`: DB Metrics API 테스트
  - `TestAuditSummaryAPI`: 감사 로그 요약 API 테스트

- `test_db_cli.py`: DB 관리 CLI 테스트
  - `TestDBCLI`: DB CLI 명령어 테스트
  - `TestDBCLIIntegration`: DB CLI 통합 테스트

### API Tests
- `test_auth_api.py`: 인증 API 테스트
  - `TestAuthAPI`: 로그인, 현재 사용자, 인증 헬퍼 테스트

- `test_admin_api.py`: 관리자 API 테스트
  - `TestAdminAPI`: 감사 로그, DB 헬스, 메트릭 테스트

- `test_health_api.py`: 헬스 체크 API 테스트
  - `TestHealthAPI`: 시스템 헬스, 장애 관리 테스트

- `test_orders_api.py`: 주문 API 테스트
  - `TestOrdersAPI`: 주문 생성, 상태, 취소, 구매 이력 테스트

### Repository Tests
- `test_repository_analysis_stats.py`: 분석 통계 레포지토리 테스트
  - `TestAnalysisStatsRepository`: 분석 통계, 모델 성능, 점수 추이 테스트

- `test_repository_customer_data.py`: 고객 데이터 레포지토리 테스트
  - `TestCustomerDataRepository`: GDPR 준수 데이터 삭제/내보내기 테스트

- `test_repository_error_audit.py`: 에러 및 감사 로그 레포지토리 테스트
  - `TestErrorAuditRepository`: 에러 추적, 감사 로그 테스트

- `test_repository_execution_stats.py`: 실행 이력 레포지토리 테스트
  - `TestExecutionStatsRepository`: 실행 이력, 통계, 정리 테스트

- `test_repository_image_metadata.py`: 이미지 메타데이터 레포지토리 테스트
  - `TestImageMetadataRepository`: 이미지 메타데이터 관리 테스트

- `test_repository_llm_api.py`: LLM API 레포지토리 테스트
  - `TestLLMAPIRepository`: LLM API 통계 테스트

- `test_repository_log.py`: 로그 레포지토리 테스트
  - `TestLogRepository`: 애플리케이션 로그 관리 테스트

- `test_repository_system_health.py`: 시스템 헬스 레포지토리 테스트
  - `TestSystemHealthRepository`: 시스템 리소스 모니터링 테스트

### Scoring Tests
- `test_scoring_breakpoints.py`: 점수 브레이크포인트 테스트
  - `TestScoringBreakpoints`: 브레이크포인트 설정, 이미지 처리 파라미터 테스트

- `test_scoring_multi_view.py`: 멀티뷰 분석 테스트
  - `TestLateralFaceAnalyzer`: 측면 얼굴 분석 테스트
  - `TestMultiViewIntegration`: 멀티뷰 통합 테스트

- `test_scoring_report.py`: 보고서 생성 테스트
  - `TestReportLazyAccessors`: 보고서 데이터 접근 테스트
  - `TestComputeOverallScoreReport`: 종합 점수 계산 테스트
  - `TestReportLayer`: 보고서 레이어 테스트
  - `TestMeasurementReportString`: 보고서 문자열 테스트

- `test_scoring_score_utils.py`: 점수 유틸리티 테스트
  - `TestScoreMapping`: 점수 매핑 테스트
  - `TestApplyMeasurementsDisplay`: 측정값 변환 테스트
  - `TestScoreQuantization`: 점수 양자화 테스트
  - `TestAdaptiveThreshold`: 적응형 임계값 테스트

### Recovery Tests
- `test_recovery_engine.py`: 자동 복구 엔진 테스트
  - `TestIncidentType`: 장애 유형 테스트
  - `TestSeverity`: 심각도 테스트
  - `TestRecoveryActionType`: 복구 작업 유형 테스트
  - `TestRecoveryEngine`: 복구 엔진 테스트
  - `TestHealthMonitor`: 헬스 모니터 테스트
  - `TestRecoveryIntegration`: 복구 통합 테스트

## 테스트 작성 원칙

1. **Mock 사용**: 실제 모델/외부 API 호출은 mock으로 대체
2. **독립성**: 각 테스트는 독립적으로 실행 가능해야 함
3. **명확성**: 테스트 이름과 설명이 명확해야 함
4. **속도**: 빠른 실행을 위해 불필요한 작업 제거
5. **커버리지**: 성공/실패, 엣지 케이스, 에러 처리 모두 포함

## 테스트 커버리지

현재 테스트는 다음 영역을 커버합니다:
- ✅ CLI 파이프라인 및 파라미터 처리
- ✅ FastAPI 서버 API 엔드포인트
- ✅ 데이터베이스 기능 및 API
- ✅ 피부 분석 애널라이저
- ✅ 인증 및 관리자 API
- ✅ 헬스 체크 및 주문 API
- ✅ CLI Repository 계층 (8개 레포지토리)
- ✅ Scoring 모듈 (4개 하위 모듈)
- ✅ 자동 복구 엔진

## 참고

- 테스트는 현재 mock 기반으로 작성되어 있어 실제 모델 없이 실행 가능
- 통합 테스트는 별도 파일로 추가 예정
- 배치 파일 `run_all_tests.bat`로 모든 테스트를 한 번에 실행 가능
