@echo off
REM CV 점수 파라미터 튜닝 배치 파일
REM 사용법: tune_cv_parameters.bat [옵션]

echo ========================================
echo CV 점수 파라미터 튜닝
echo ========================================
echo.

REM 기본 옵션 설정
set METRIC=
set ALL=false
set ITERATIONS=100
set STRATEGY=random
set TEST_TYPE=all

REM 인자 파싱
:parse_args
if "%1"=="" goto run_tuning
if "%1"=="--metric" (
    set METRIC=%2
    shift
    shift
    goto parse_args
)
if "%1"=="--all" (
    set ALL=true
    shift
    goto parse_args
)
if "%1"=="--iterations" (
    set ITERATIONS=%2
    shift
    shift
    goto parse_args
)
if "%1"=="--strategy" (
    set STRATEGY=%2
    shift
    shift
    goto parse_args
)
if "%1"=="--test-type" (
    set TEST_TYPE=%2
    shift
    shift
    goto parse_args
)
if "%1"=="--help" goto show_help
shift
goto parse_args

:run_tuning
if "%METRIC%"=="" if "%ALL%"=="false" (
    echo 오류: --metric 또는 --all 중 하나를 지정해야 합니다
    echo.
    goto show_help
)

echo 옵션:
if not "%METRIC%"=="" echo   메트릭: %METRIC%
if "%ALL%"=="true" echo   모든 메트릭 튜닝
echo   반복 횟수: %ITERATIONS%
echo   전략: %STRATEGY%
echo   테스트 타입: %TEST_TYPE%
echo.

REM Python 스크립트 실행
python scripts/tune_cv_parameters.py --config config/config.json --output results/tuning_results.json %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 오류: 튜닝 실패
    exit /b 1
)

echo.
echo ========================================
echo 튜닝 완료
echo ========================================
echo 결과: results/tuning_results.json
echo.
exit /b 0

:show_help
echo 사용법: tune_cv_parameters.bat [옵션]
echo.
echo 옵션:
echo   --metric METRIC        특정 메트릭 튜닝
echo   --all                  모든 메트릭 튜닝
echo   --iterations N         반복 횟수 (기본값: 100)
echo   --strategy STRATEGY    튜닝 전략 (random, grid, adaptive)
echo   --test-type TYPE       테스트 타입 (monotonicity, independence, composite, regression, all)
echo   --help                 도움말 표시
echo.
echo 예시:
echo   tune_cv_parameters.bat --metric melasma_score
echo   tune_cv_parameters.bat --all --iterations 50
echo   tune_cv_parameters.bat --metric pore_size_score --strategy grid
echo   tune_cv_parameters.bat --metric melasma_score --test-type monotonicity
echo   tune_cv_parameters.bat --all --test-type all
echo.
exit /b 0
