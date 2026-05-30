# 서버 테스트 실행 가이드

이 문서는 SkinLens v1의 서버 관련 테스트를 위한 상세한 실행 가이드입니다.

## 목차

1. [개요](#개요)
2. [테스트 파일 목록](#테스트-파일-목록)
3. [테스트 커버리지 상세](#테스트-커버리지-상세)
4. [실행 방법](#실행-방법)
5. [테스트 구조 상세](#테스트-구조-상세)
6. [의존성 및 환경 설정](#의존성-및-환경-설정)
7. [CI/CD 통합](#cicd-통합)
8. [트러블슈팅](#트러블슈팅)

---

## 개요

이 가이드는 SkinLens v1의 서버 관련 테스트를 다룹니다. 서버 테스트는 다음 영역을 커버합니다:

- **Core Server Tests**: FastAPI 서버 통합 테스트 (API 엔드포인트, 동시성 제어, 인증, WebSocket, E2E)
- **API Tests**: 인증, 관리자, 헬스 체크, 주문 API 단위 테스트

### 테스트 철학

1. **Mock 기반**: 실제 데이터베이스/외부 API는 mock으로 대체
2. **독립성**: 각 테스트는 독립적으로 실행 가능
3. **비동기 지원**: FastAPI의 비동기 특성을 완전히 테스트
4. **실제 시나리오**: 실제 사용 시나리오를 반영한 테스트 케이스

---

## 테스트 파일 목록

### 1. Core Server Tests

#### test_server.py - FastAPI 서버 통합 테스트

이 파일은 FastAPI 서버의 핵심 기능을 테스트합니다.

- **TestFastAPIServer**: API 엔드포인트 테스트
  - 이미지 분석 엔드포인트 (/analyze)
  - 작업 상태 조회 (/jobs/{id})
  - 파일 업로드 처리
  - URL 기반 이미지 다운로드
  - 다중 이미지 업로드
  - CORS 헤더 검증

- **TestConcurrencyControl**: 동시성 제어 테스트
  - 최대 동시 작업 수 제한
  - 세마포어 타임아웃 처리
  - ThreadPoolExecutor 설정

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

### 2. API Tests

#### test_auth_api.py - 인증 API 테스트

인증 시스템의 핵심 기능을 테스트합니다.

- **TestAuthAPI**: 인증 관련 테스트
  - 로그인 성공/실패 시나리오
  - 비밀번호 검증
  - 현재 사용자 정보 조회
  - 고객 접근 확인
  - 레이트 리미팅
  - 토큰 만료 처리

#### test_admin_api.py - 관리자 API 테스트

관리자 전용 기능을 테스트합니다.

- **TestAdminAPI**: 관리자 기능 테스트
  - 감사 로그 조회
  - DB 헬스 체크
  - DB 메트릭 조회
  - 감사 요약
  - 인증/권한 검증
  - 레이트 리미팅
  - 관리자 전용 엔드포인트

#### test_health_api.py - 헬스 체크 API 테스트

시스템 헬스 모니터링 기능을 테스트합니다.

- **TestHealthAPI**: 헬스 체크 테스트
  - 기본 헬스 체크
  - 서비스 상태 확인
  - 장애 이벤트 조회
  - 복구 작업 트리거
  - 롤백 트리거
  - 헬퍼 함수 테스트
  - CPU/메모리/디스크 헬스 체크

#### test_orders_api.py - 주문 API 테스트

주문 관리 기능을 테스트합니다.

- **TestOrdersAPI**: 주문 기능 테스트
  - 주문 생성 성공/실패
  - 주문 상태 조회
  - 주문 취소
  - 구매 이력 조회
  - 페이지네이션
  - 데이터 모델 검증
  - 유효성 검사
  - 비즈니스 로직 검증

---

## 테스트 커버리지 상세

### test_server.py

#### TestFastAPIServer
- ✅ POST /analyze 정상 동작
- ✅ GET /jobs/{id} 상태 조회
- ✅ 파일 업로드 크기 제한 (10MB)
- ✅ 지원되지 않는 파일 형식 거부
- ✅ URL 기반 이미지 다운로드
- ✅ 다중 이미지 업로드 (images[] + angles[])
- ✅ CORS 헤더 확인
- ✅ 비동기 작업 처리
- ✅ 에러 응답 포맷 검증

#### TestConcurrencyControl
- ✅ MAX_CONCURRENT_JOBS 준수 확인
- ✅ 세마포어 타임아웃 처리
- ✅ ThreadPoolExecutor 설정 확인
- ✅ 동시 요청 처리
- ✅ 리소스 해제 확인

#### TestAuthenticationAPI
- ✅ JWT 토큰 생성/검증
- ✅ 관리자 로그인 (admin/admin123)
- ✅ 분석가 로그인 (analyst/analyst123)
- ✅ 인증 없는 접근 거부
- ✅ 잘못된 비밀번호 처리
- ✅ 토큰 만료 처리

#### TestCustomerAPI
- ✅ 트렌드 조회 (GET /trends)
- ✅ 분석 통계 조회 (GET /stats)
- ✅ 에러 조회 (GET /errors)
- ✅ 데이터 삭제 (DELETE /data)
- ✅ 데이터 내보내기 (GET /export)
- ✅ 고객 ID 필터링
- ✅ 날짜 범위 필터링

#### TestWebSocketAPI
- ✅ WebSocket 연결 (/ws/jobs/{id})
- ✅ 진행 상태 전송
- ✅ 존재하지 않는 Job 처리
- ✅ 연결 종료 처리
- ✅ 메시지 포맷 검증

#### TestE2EIntegration
- ✅ 엔드투엔드 분석 파이프라인
- ✅ 인증 + 고객 ID 포함 E2E
- ✅ 이미지 업로드 → 분석 → 결과 조회
- ✅ WebSocket을 통한 실시간 상태 업데이트

### test_auth_api.py

#### TestAuthAPI
- ✅ 로그인 성공 (올바른 자격증명)
- ✅ 로그인 실패 (잘못된 비밀번호)
- ✅ 로그인 실패 (존재하지 않는 사용자)
- ✅ 비밀번호 검증 (해시 비교)
- ✅ 현재 사용자 정보 조회 (/me)
- ✅ 고객 접근 확인
- ✅ 레이트 리미팅 (5회/분)
- ✅ 토큰 만료 처리
- ✅ 인증 헬퍼 함수 테스트
- ✅ 토큰 디코딩 테스트

### test_admin_api.py

#### TestAdminAPI
- ✅ 감사 로그 조회 (/admin/audit-logs)
- ✅ 감사 로그 필터링 (날짜, 사용자, 작업)
- ✅ DB 헬스 체크 (/admin/db-health)
- ✅ DB 메트릭 조회 (/admin/db-metrics)
- ✅ 감사 요약 (/admin/audit-summary)
- ✅ 인증 검증 (관리자만 접근)
- ✅ 권한 검증 (비관리자 거부)
- ✅ 레이트 리미팅 (10회/분)
- ✅ 페이지네이션
- ✅ 정렬 기능

### test_health_api.py

#### TestHealthAPI
- ✅ 기본 헬스 체크 (/health)
- ✅ 서비스 상태 확인 (CPU, 메모리, 디스크)
- ✅ 장애 이벤트 조회 (/incidents)
- ✅ 장애 이벤트 필터링
- ✅ 복구 작업 트리거 (/recovery/trigger)
- ✅ 롤백 트리거 (/recovery/rollback)
- ✅ 헬퍼 함수 테스트 (check_cpu, check_memory, check_disk)
- ✅ 서비스 상태 계산
- ✅ 장애 심각도 분류

### test_orders_api.py

#### TestOrdersAPI
- ✅ 주문 생성 성공 (POST /orders)
- ✅ 주문 생성 실패 (잘못된 데이터)
- ✅ 주문 생성 실패 (이미 존재하는 주문)
- ✅ 주문 상태 조회 (GET /orders/{id})
- ✅ 주문 상태 필터링
- ✅ 주문 취소 (POST /orders/{id}/cancel)
- ✅ 주문 취소 실패 (이미 완료된 주문)
- ✅ 구매 이력 조회 (GET /orders)
- ✅ 구매 이력 필터링 (고객 ID, 상태)
- ✅ 페이지네이션 (limit, offset)
- ✅ 데이터 모델 검증 (Order 모델)
- ✅ 유효성 검사 (필수 필드)
- ✅ 비즈니스 로직 검증 (상태 전환)

---

## 실행 방법

### 환경 설정

**현재 개발 환경**: Python 3.12

테스트 실행 전 다음 의존성이 필요합니다:

```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

### 전체 서버 테스트 실행

```bash
cd "c:\Project\SkinLens v1"
python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py -v
```

또는 배치 파일 사용:
```bash
scripts\run_server_tests.bat
```

### 개별 테스트 파일 실행

```bash
# Core 서버 테스트
python -m pytest tests/test_server.py -v

# 인증 API 테스트
python -m pytest tests/test_auth_api.py -v

# 관리자 API 테스트
python -m pytest tests/test_admin_api.py -v

# 헬스 체크 API 테스트
python -m pytest tests/test_health_api.py -v

# 주문 API 테스트
python -m pytest tests/test_orders_api.py -v
```

### 특정 테스트 클래스만 실행

```bash
# test_server.py
python -m pytest tests/test_server.py::TestFastAPIServer -v
python -m pytest tests/test_server.py::TestConcurrencyControl -v
python -m pytest tests/test_server.py::TestAuthenticationAPI -v
python -m pytest tests/test_server.py::TestCustomerAPI -v
python -m pytest tests/test_server.py::TestWebSocketAPI -v
python -m pytest tests/test_server.py::TestE2EIntegration -v

# API 테스트
python -m pytest tests/test_auth_api.py::TestAuthAPI -v
python -m pytest tests/test_admin_api.py::TestAdminAPI -v
python -m pytest tests/test_health_api.py::TestHealthAPI -v
python -m pytest tests/test_orders_api.py::TestOrdersAPI -v
```

### 특정 테스트 메서드 실행

```bash
# test_server.py
python -m pytest tests/test_server.py::TestFastAPIServer::test_analyze_success -v
python -m pytest tests/test_server.py::TestFastAPIServer::test_get_job_status -v

# API 테스트
python -m pytest tests/test_auth_api.py::TestAuthAPI::test_login_success -v
python -m pytest tests/test_admin_api.py::TestAdminAPI::test_get_audit_logs -v
python -m pytest tests/test_health_api.py::TestHealthAPI::test_health_check -v
python -m pytest tests/test_orders_api.py::TestOrdersAPI::test_create_order_success -v
```

### 커버리지 확인

```bash
# 전체 서버 커버리지
python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py --cov=src/server --cov-report=html

# 특정 파일 커버리지
python -m pytest tests/test_server.py --cov=src/server --cov-report=html
python -m pytest tests/test_auth_api.py --cov=src/server/routers/auth --cov-report=html
```

### 상세 출력 모드

```bash
# 매우 상세한 출력
python -m pytest tests/test_server.py -vv -s

# 실패한 테스트만 상세 출력
python -m pytest tests/test_server.py -v --tb=long
```

---

## 테스트 구조 상세

### Mock 사용 패턴

서버 테스트는 다음 Mock 패턴을 사용합니다:

```python
# FastAPI TestClient
from fastapi.testclient import TestClient
client = TestClient(app)

# Mock 데이터베이스
from unittest.mock import Mock
mock_db = Mock()
mock_db.get_analysis.return_value = {...}

# Mock 의존성
@pytest.fixture
def mock_auth():
    return Mock(return_value={"customer_id": "test_123"})
```

### 비동기 테스트 패턴

```python
@pytest.mark.asyncio
async def test_async_endpoint():
    response = await client.post("/analyze", ...)
    assert response.status_code == 200
```

### 인증 테스트 패턴

```python
# 토큰 생성
token = create_jwt_token(user_id="admin", role="admin")
headers = {"Authorization": f"Bearer {token}"}

# 인증된 요청
response = client.get("/admin/audit-logs", headers=headers)
```

---

## 의존성 및 환경 설정

### 의존성 설치

```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

### 환경 변수 설정

테스트 실행 전 다음 환경 변수가 설정되어야 합니다:

```bash
set JWT_SECRET_KEY=test-secret-for-ci
set SKIN_API_MAX_UPLOAD_BYTES=10485760
set ADMIN_PASSWORD=admin123
set ANALYST_PASSWORD=analyst123
```

### 환경 변수 설명

| 변수 | 설명 | 기본값 |
|------|------|--------|
| JWT_SECRET_KEY | JWT 토큰 서명 키 | test-secret-for-ci |
| SKIN_API_MAX_UPLOAD_BYTES | 최대 업로드 크기 (바이트) | 10485760 (10MB) |
| ADMIN_PASSWORD | 관리자 비밀번호 | admin123 |
| ANALYST_PASSWORD | 분석가 비밀번호 | analyst123 |

---

## CI/CD 통합

### GitHub Actions 예시

```yaml
name: Server Tests

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
      - name: Set environment variables
        run: |
          export JWT_SECRET_KEY=test-secret-for-ci
          export SKIN_API_MAX_UPLOAD_BYTES=10485760
          export ADMIN_PASSWORD=admin123
          export ANALYST_PASSWORD=analyst123
      - name: Run server tests
        run: |
          python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py -v --cov=src/server --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

### 로컬 CI 시뮬레이션

```bash
# 전체 서버 테스트 실행
scripts\run_server_tests.bat

# 전체 테스트 실행 (서버 포함)
scripts\run_all_tests.bat
```

---

## 트러블슈팅

### 일반적인 문제

#### 1. 환경 변수 누락

**문제**: 환경 변수가 설정되지 않음
```bash
KeyError: 'JWT_SECRET_KEY'
```

**해결**:
```bash
set JWT_SECRET_KEY=test-secret-for-ci
set SKIN_API_MAX_UPLOAD_BYTES=10485760
set ADMIN_PASSWORD=admin123
set ANALYST_PASSWORD=analyst123
```

#### 2. 의존성 누락

**문제**: 모듈을 찾을 수 없음
```bash
ModuleNotFoundError: No module named 'httpx'
```

**해결**:
```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

#### 3. 비동기 테스트 실패

**문제**: 비동기 테스트가 실패
```bash
RuntimeError: Async test function not marked with @pytest.mark.asyncio
```

**해결**: `@pytest.mark.asyncio` 데코레이터 추가

#### 4. 인증 실패

**문제**: 인증 토큰이 유효하지 않음
```bash
401 Unauthorized
```

**해결**: 환경 변수가 올바르게 설정되었는지 확인

### 디버깅 팁

#### 1. 상세 출력
```bash
python -m pytest tests/test_server.py -vv -s
```

#### 2. 특정 테스트 중단점
```python
def test_with_breakpoint():
    import pdb; pdb.set_trace()
    # 테스트 코드
```

#### 3. 실패한 테스트만 재실행
```bash
python -m pytest tests/test_server.py --lf
```

#### 4. 마지막으로 실패한 테스트 재실행
```bash
python -m pytest tests/test_server.py --ff
```

---

## 테스트 결과 해석

- **PASS**: 테스트 성공
- **FAIL**: 테스트 실패 - 코드 수정 필요
- **SKIP**: 의존성 누락 등으로 건너뜀
- **XFAIL**: 예상된 실패 (xfail 마커 사용)
- **XPASS**: 예상된 실패가 성공 (xfail 마커 사용)

---

## 주의사항

1. **테스트용 이미지**: 일부 테스트는 실제 이미지 파일이 필요합니다. 테스트용 이미지는 `tests/fixtures/` 디렉토리에 배치하세요.
2. **동시성 테스트**: 동시성 테스트는 시스템 리소스에 영향을 받을 수 있습니다. 리소스가 부족한 환경에서는 주의하세요.
3. **WebSocket 테스트**: WebSocket 테스트는 비동기 실행을 지원해야 합니다.
4. **환경 변수**: 모든 테스트는 올바른 환경 변수 설정을 필요로 합니다.
5. **배치 파일**: `scripts/run_server_tests.bat`를 사용하면 환경 변수가 자동으로 설정됩니다.
6. **데이터베이스**: 테스트는 mock을 사용하므로 실제 데이터베이스가 필요하지 않습니다.

---

## 추가 참고

- 전체 테스트 가이드: `tests/README.md`
- 전체 테스트 실행: `scripts/run_all_tests.bat`
- 서버 소스 코드: `src/server/`
- API 문서: `docs/api/API_DOCUMENTATION.md`
