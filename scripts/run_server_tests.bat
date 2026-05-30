@echo off
REM 서버 테스트 실행 스크립트

echo ========================================
echo SkinLens v1 서버 테스트 실행
echo ========================================
echo.

REM 프로젝트 루트로 이동
cd /d "%~dp0.."

REM 환경 변수 설정
set JWT_SECRET_KEY=test-secret-for-ci
set SKIN_API_MAX_UPLOAD_BYTES=10485760
set ADMIN_PASSWORD=admin123
set ANALYST_PASSWORD=analyst123

REM 의존성 확인
echo [1/3] 의존성 확인 중...
python -c "import pytest; import pytest_asyncio; import httpx" 2>nul
if errorlevel 1 (
    echo [오류] 필수 의존성이 설치되지 않았습니다.
    echo 설치 명령: pip install pytest pytest-asyncio pytest-cov httpx
    pause
    exit /b 1
)
echo [완료] 의존성 확인 완료
echo.

REM 테스트 실행
echo [2/3] 서버 테스트 실행 중...
python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py -v --tb=short
if errorlevel 1 (
    echo [실패] 일부 테스트가 실패했습니다.
    echo.
) else (
    echo [성공] 모든 테스트가 통과했습니다.
    echo.
)

REM 커버리지 보고서 생성 (선택사항)
echo [3/3] 커버리지 보고서 생성 중...
python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py --cov=src/server --cov-report=html --cov-report=term-missing
if errorlevel 1 (
    echo [경고] 커버리지 보고서 생성 실패
) else (
    echo [완료] 커버리지 보고서 생성 완료: htmlcov/index.html
)

echo.
echo ========================================
echo 테스트 실행 완료
echo ========================================
pause
