# 서버 테스트 실행 가이드

## 개요

이 문서는 SkinLens v1의 서버 관련 테스트를 위한 실행 가이드입니다.

## 테스트 파일 목록

### 1. Core Server Tests
- `test_server.py`: FastAPI 서버 통합 테스트
  - API 엔드포인트, 동시성 제어, 인증, WebSocket, E2E 테스트

### 2. API Tests
- `test_auth_api.py`: 인증 API 테스트
  - 로그인, 현재 사용자, 인증 헬퍼 함수 테스트

- `test_admin_api.py`: 관리자 API 테스트
  - 감사 로그, DB 헬스 체크, DB 메트릭, 감사 요약 테스트

- `test_health_api.py`: 헬스 체크 API 테스트
  - 시스템 헬스 체크, 장애 관리, 복구 작업 테스트

- `test_orders_api.py`: 주문 API 테스트
  - 주문 생성, 상태 조회, 취소, 구매 이력 테스트

## 테스트 커버리지

### test_server.py (TestFastAPIServer)
- ✅ POST /analyze 정상 동작
- ✅ GET /jobs/{id} 상태 조회
- ✅ 파일 업로드 크기 제한
- ✅ 지원되지 않는 파일 형식 거부
- ✅ URL 기반 이미지 다운로드
- ✅ 다중 이미지 업로드 (images[] + angles[])
- ✅ CORS 헤더 확인

### test_server.py (TestConcurrencyControl)
- ✅ MAX_CONCURRENT_JOBS 준수 확인
- ✅ 세마포어 타임아웃 처리
- ✅ ThreadPoolExecutor 설정 확인

### test_server.py (TestAuthenticationAPI)
- ✅ JWT 토큰 생성/검증
- ✅ 관리자/분석가 로그인
- ✅ 인증 없는 접근 거부

### test_server.py (TestCustomerAPI)
- ✅ 트렌드 조회
- ✅ 분석 통계 조회
- ✅ 에러 조회
- ✅ 데이터 삭제/내보내기

### test_server.py (TestWebSocketAPI)
- ✅ WebSocket 연결
- ✅ 진행 상태 전송
- ✅ 존재하지 않는 Job 처리

### test_server.py (TestE2EIntegration)
- ✅ 엔드투엔드 분석 파이프라인
- ✅ 인증 + 고객 ID 포함 E2E

### test_auth_api.py (TestAuthAPI)
- ✅ 로그인 성공/실패
- ✅ 비밀번호 검증
- ✅ 현재 사용자 정보 조회
- ✅ 고객 접근 확인
- ✅ 레이트 리미팅

### test_admin_api.py (TestAdminAPI)
- ✅ 감사 로그 조회
- ✅ DB 헬스 체크
- ✅ DB 메트릭 조회
- ✅ 감사 요약
- ✅ 인증/권한 검증
- ✅ 레이트 리미팅

### test_health_api.py (TestHealthAPI)
- ✅ 기본 헬스 체크
- ✅ 서비스 상태 확인
- ✅ 장애 이벤트 조회
- ✅ 복구 작업 트리거
- ✅ 롤백 트리거
- ✅ 헬퍼 함수 테스트

### test_orders_api.py (TestOrdersAPI)
- ✅ 주문 생성 성공/실패
- ✅ 주문 상태 조회
- ✅ 주문 취소
- ✅ 구매 이력 조회
- ✅ 페이지네이션
- ✅ 데이터 모델 검증

## 실행 방법

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

### 커버리지 확인

```bash
python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py --cov=src/server --cov-report=html
```

## 의존성 설치

```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

## 환경 변수 설정

테스트 실행 전 다음 환경 변수가 설정되어야 합니다:

```bash
set JWT_SECRET_KEY=test-secret-for-ci
set SKIN_API_MAX_UPLOAD_BYTES=10485760
set ADMIN_PASSWORD=admin123
set ANALYST_PASSWORD=analyst123
```

## CI/CD 통합

GitHub Actions에서 자동 실행하려면 `.github/workflows/test-server.yml`을 참조하세요.

## 테스트 결과 해석

- **PASS**: 테스트 성공
- **FAIL**: 테스트 실패 - 코드 수정 필요
- **SKIP**: 의존성 누락 등으로 건너뜀

## 주의사항

1. 일부 테스트는 실제 이미지 파일이 필요합니다. 테스트용 이미지는 `tests/fixtures/` 디렉토리에 배치하세요.
2. 동시성 테스트는 시스템 리소스에 영향을 받을 수 있습니다.
3. WebSocket 테스트는 비동기 실행을 지원해야 합니다.
4. 배치 파일 `run_all_tests.bat`를 사용하면 모든 테스트를 한 번에 실행할 수 있습니다.
