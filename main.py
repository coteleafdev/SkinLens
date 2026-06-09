#!/usr/bin/env python3
"""
SkinLens - 메인 진입점

GUI와 CLI 모드를 통합한 메인 진입점입니다.

새로운 구조:
- CLI 모드: src/cli/entry.py → src/pipeline/pipeline_runner.py
- GUI 모드: src/gui/entry.py → src/gui/gui_wrapper.py

사용법:
    # GUI 모드 (기본)
    python main.py

    # CLI 모드
    python main.py --cli -i input.jpg -o output_dir

    # CLI 모드 (비동기)
    python main.py --cli -i input.jpg -o output_dir --async
"""
import argparse
import sys


def main():
    """메인 진입점."""
    parser = argparse.ArgumentParser(
        description="SkinLens - 피부 분석 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # GUI 모드 (기본)
  python main.py

  # CLI 모드
  python main.py --cli -i input.jpg -o output_dir

  # CLI 모드 (비동기)
  python main.py --cli -i input.jpg -o output_dir --async
        """
    )

    parser.add_argument(
        "--cli",
        action="store_true",
        help="CLI 모드로 실행 (GUI 없이 명령줄 기반 동작)"
    )

    # CLI 전용 인자들 (src/cli/entry.py로 전달)
    parser.add_argument("-i", "--input", type=str, help="입력 이미지 경로")
    parser.add_argument("-o", "--output", type=str, help="출력 디렉토리 경로")
    parser.add_argument("--no-restore", action="store_true", help="복원 생략")
    parser.add_argument("--no-base64", action="store_true", help="base64 인코딩 생략")
    parser.add_argument("--async", dest="async_mode", action="store_true", help="비동기 모드")
    parser.add_argument("--debug", action="store_true", help="디버그 모드")
    parser.add_argument("--output-json", type=str, help="결과 JSON 출력 파일 경로")
    parser.add_argument("--llm-report", action="store_true", default=True, help="LLM 소견 생성 (기본: True)")
    parser.add_argument("--no-llm-report", action="store_false", dest="llm_report", help="LLM 소견 비활성화")
    parser.add_argument("--llm-api-key", type=str, help="LLM API 키")
    parser.add_argument("--customer-id", type=str, help="고객 ID")
    parser.add_argument("--gender", type=str, help="성별")
    parser.add_argument("--age", type=int, help="연령")
    parser.add_argument("--race", type=str, help="인종")
    parser.add_argument("--region", type=str, help="지역")

    args = parser.parse_args()

    if args.cli:
        # CLI 모드: 필수 인자 검증
        if not args.input or not args.output:
            print("오류: CLI 모드에서는 -i/--input과 -o/--output이 필수입니다.")
            print("사용법: python main.py --cli -i input.jpg -o output_dir")
            sys.exit(1)

        # CLI 모드: src/cli/entry.py 사용
        try:
            from src.cli.entry import main as cli_main
            sys.argv = ["cli-entry"] + [arg for arg in sys.argv[1:] if arg != "--cli"]
            sys.exit(cli_main())
        except ImportError as e:
            print(f"오류: CLI 모듈을 임포트할 수 없습니다: {e}")
            sys.exit(1)
    else:
        # GUI 모드: src/gui/entry.py 사용
        try:
            from src.gui.entry import main as gui_main
            sys.exit(gui_main())
        except ImportError as e:
            print(f"오류: GUI 모듈을 임포트할 수 없습니다: {e}")
            print("GUI 모드를 사용하려면 PySide6를 설치하세요: pip install PySide6")
            sys.exit(1)


if __name__ == "__main__":
    main()
