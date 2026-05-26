# 테스트 가이드

## 테스트 실행

### 모든 테스트 실행
```bash
cd c:\Project\AI Skin v3
pytest tests/ -v
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
```

### 특정 테스트 클래스 실행
```bash
pytest tests/test_cli.py::TestCLIPipeline -v
pytest tests/test_server.py::TestFastAPIServer -v
pytest tests/test_db_features.py::TestExecutionHistoryDB -v
pytest tests/test_db_api.py::TestDBHealthCheckAPI -v
pytest tests/test_db_cli.py::TestDBCLI -v
```

### 특정 테스트 메서드 실행
```bash
pytest tests/test_cli.py::TestCLIPipeline::test_run_analysis_pipeline_basic_params -v
pytest tests/test_server.py::TestFastAPIServer::test_health_check -v
pytest tests/test_db_features.py::TestExecutionHistoryDB::test_check_health_healthy -v
pytest tests/test_db_api.py::TestDBHealthCheckAPI::test_health_db_healthy -v
pytest tests/test_db_cli.py::TestDBCLI::test_backup_command -v
```

## 테스트 구조

- `test_cli.py`: CLI 모듈 단위 테스트
  - `TestCLIPipeline`: 파이프라인 실행 테스트
  - `TestCLIParameters`: 파라미터 처리 테스트

- `test_server.py`: FastAPI 서버 단위 테스트
  - `TestFastAPIServer`: API 엔드포인트 테스트
  - `TestServerHelpers`: 서버 헬퍼 함수 테스트

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

## 테스트 작성 원칙

1. **Mock 사용**: 실제 모델/외부 API 호출은 mock으로 대체
2. **독립성**: 각 테스트는 독립적으로 실행 가능해야 함
3. **명확성**: 테스트 이름과 설명이 명확해야 함
4. **속도**: 빠른 실행을 위해 불필요한 작업 제거

## 참고

- 테스트는 현재 mock 기반으로 작성되어 있어 실제 모델 없이 실행 가능
- 통합 테스트는 별도 파일로 추가 예정
