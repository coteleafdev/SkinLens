"""
전체 테스트 실행 스크립트

이 스크립트는 프로젝트의 모든 테스트를 실행하고 결과를 요약합니다.

사용법:
    python run_all_tests.py                    # 모든 테스트 실행
    python run_all_tests.py --skip-server      # 서버 의존성 테스트 스킵
    python run_all_tests.py --db-only         # DB 테스트만 실행
    python run_all_tests.py --config-only      # config 테스트만 실행
"""
import subprocess
import sys
from pathlib import Path

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent


def run_command(cmd, description):
    """명령어 실행 및 결과 출력"""
    print(f"\n{'='*60}")
    print(f"실행: {description}")
    print(f"{'='*60}")
    print(f"명령어: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr, file=sys.stderr)
    
    return result.returncode == 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="전체 테스트 실행 스크립트")
    parser.add_argument("--skip-server", action="store_true", help="서버 의존성 테스트 스킵")
    parser.add_argument("--db-only", action="store_true", help="DB 테스트만 실행")
    parser.add_argument("--config-only", action="store_true", help="config 테스트만 실행")
    parser.add_argument("--repositories-only", action="store_true", help="Repository 테스트만 실행")
    parser.add_argument("-v", "--verbose", action="store_true", help="상세 출력")
    
    args = parser.parse_args()
    
    python_exe = sys.executable
    pytest_args = ["-v"] if args.verbose else []
    
    # 테스트 파일 목록
    test_files = []
    
    if args.config_only:
        test_files = ["tests/test_config.py"]
    elif args.db_only:
        test_files = ["tests/test_db_features.py", "tests/test_repositories.py"]
    elif args.repositories_only:
        test_files = ["tests/test_repositories.py"]
    else:
        # 모든 테스트 (서버 의존성 제외)
        test_files = [
            "tests/test_config.py",
            "tests/test_db_features.py",
            "tests/test_repositories.py",
            "tests/test_unit.py",
            "tests/test_cli.py",
            "tests/test_integration.py",
        ]
        
        if not args.skip_server:
            test_files.extend([
                "tests/test_server.py",
                "tests/test_db_api.py",
                "tests/test_stats_api.py",
                "tests/test_logs_api.py",
                "tests/test_security.py",
                "tests/test_db_cli.py",
            ])
    
    # pytest 실행
    cmd = [python_exe, "-m", "pytest"] + pytest_args + test_files
    
    print(f"\n{'#'*60}")
    print("# 전체 테스트 실행")
    print(f"{'#'*60}")
    print(f"테스트 파일: {len(test_files)}개")
    print(f"파일 목록: {', '.join(test_files)}")
    print(f"{'#'*60}\n")
    
    success = run_command(cmd, "전체 테스트 실행")
    
    # 결과 요약
    print(f"\n{'#'*60}")
    print("# 테스트 결과 요약")
    print(f"{'#'*60}")
    if success:
        print("✅ 모든 테스트 통과")
        sys.exit(0)
    else:
        print("❌ 일부 테스트 실패")
        print("\n참고:")
        print("- 서버 의존성 테스트를 실행하려면: pip install python-jose[cryptography] fastapi uvicorn")
        print("- 서버 테스트 스킵: python run_all_tests.py --skip-server")
        sys.exit(1)


if __name__ == "__main__":
    main()
