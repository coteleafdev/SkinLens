# 서버 테스트 실행 가이드

## 개요

`tests/test_server.py`는 CODE_QUALITY_CHECKLIST.md의 **1.8 서버 (FastAPI)** 및 **4.4 테스트** 섹션을 기반으로 작성된 통합 테스트 파일입니다.

## 테스트 커버리지

### 1. API 엔드포인트 테스트 (TestFastAPIServer)
- ✅ POST /analyze 정상 동작
- ✅ GET /jobs/{id} 상태 조회
- ✅ 파일 업로드 크기 제한
- ✅ 지원되지 않는 파일 형식 거부
- ✅ URL 기반 이미지 다운로드
- ✅ 다중 이미지 업로드 (images[] + angles[])
- ✅ CORS 헤더 확인

### 2. 동시성 제어 테스트 (TestConcurrencyControl)
- ✅ MAX_CONCURRENT_JOBS 준수 확인
- ✅ 세마포어 타임아웃 처리
- ✅ ThreadPoolExecutor 설정 확인

### 3. 인증 테스트 (TestAuthenticationAPI)
- ✅ JWT 토큰 생성/검증
- ✅ 관리자/분석가 로그인
- ✅ 인증 없는 접근 거부

### 4. 고객 API 테스트 (TestCustomerAPI)
- ✅ 트렌드 조회
- ✅ 분석 통계 조회
- ✅ 에러 조회
- ✅ 데이터 삭제/내보내기

### 5. WebSocket 테스트 (TestWebSocketAPI)
- ✅ WebSocket 연결
- ✅ 진행 상태 전송
- ✅ 존재하지 않는 Job 처리

### 6. 통합 테스트 (TestE2EIntegration)
- ✅ 엔드투엔드 분석 파이프라인
- ✅ 인증 + 고객 ID 포함 E2E

## 실행 방법

### 전체 테스트 실행

```bash
cd "C:\Project\AI Skin Engine v3"
python -m pytest tests/test_server.py -v
```

### 특정 테스트 클래스만 실행

```bash
# API 엔드포인트 테스트만
python -m pytest tests/test_server.py::TestFastAPIServer -v

# 동시성 제어 테스트만
python -m pytest tests/test_server.py::TestConcurrencyControl -v

# WebSocket 테스트만
python -m pytest tests/test_server.py::TestWebSocketAPI -v

# 통합 테스트만
python -m pytest tests/test_server.py::TestE2EIntegration -v
```

### 커버리지 확인

```bash
python -m pytest tests/test_server.py --cov=src/server --cov-report=html
```

### 마커 기반 실행

```bash
# 서버 관련 테스트만
python -m pytest tests/test_server.py -m server -v

# FastAPI 의존성이 있는 테스트만
python -m pytest tests/test_server.py -m requires_fastapi -v
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
