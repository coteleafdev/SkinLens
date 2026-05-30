@echo off
REM ============================================
REM SkinLens v1 - 전체 테스트 실행 배치 파일
REM ============================================

echo.
echo ============================================
echo   SkinLens v1 전체 테스트 실행
echo ============================================
echo.

REM 프로젝트 루트로 이동
cd /d "%~dp0.."

REM Python 확인
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python이 설치되지 않았거나 PATH에 없습니다.
    echo Python을 설치하고 PATH에 추가한 후 다시 실행하세요.
    pause
    exit /b 1
)

REM pytest 확인
python -m pytest --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] pytest가 설치되지 않았습니다. 설치합니다...
    pip install pytest pytest-asyncio pytest-cov
    if %errorlevel% neq 0 (
        echo [ERROR] pytest 설치에 실패했습니다.
        pause
        exit /b 1
    )
)

echo [INFO] 테스트 환경 확인 완료
echo.

REM 테스트 실행 옵션
set TEST_OPTIONS=-v --tb=short

REM 커버리지 옵션 (선택적)
set COVERAGE_OPTIONS=--cov=src --cov-report=html --cov-report=term

REM 사용자에게 커버리지 포함 여부 묻기
echo 커버리지 리포트를 생성하시겠습니까? (Y/N)
set /p INCLUDE_COVERAGE=

if /i "%INCLUDE_COVERAGE%"=="Y" (
    echo [INFO] 커버리지 리포트 포함하여 테스트 실행...
    python -m pytest tests/ %TEST_OPTIONS% %COVERAGE_OPTIONS%
) else (
    echo [INFO] 기본 테스트 실행...
    python -m pytest tests/ %TEST_OPTIONS%
)

REM 테스트 결과 확인
if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo   [SUCCESS] 모든 테스트가 통과했습니다!
    echo ============================================
) else (
    echo.
    echo ============================================
    echo   [FAILURE] 일부 테스트가 실패했습니다.
    echo ============================================
)

echo.
echo 테스트 완료. 아무 키나 누르면 종료합니다...
pause >nul
