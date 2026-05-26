#!/usr/bin/env python3
"""
COTELEAF Skin Analysis - 메인 진입점

GUI와 CLI 모드를 통합한 메인 진입점입니다.

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
from pathlib import Path


def main():
    """메인 진입점."""
    parser = argparse.ArgumentParser(
        description="COTELEAF Skin Analysis - 피부 분석 파이프라인",
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
    
    # CLI 전용 인자들 (skin_analysis_cli.py와 동일)
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
        # CLI 모드
        print("CLI 모드로 실행합니다...")
        
        # 필수 인자 확인
        if not args.input or not args.output:
            print("오류: CLI 모드에서는 -i/--input과 -o/--output이 필수입니다.")
            print("사용법: python main.py --cli -i input.jpg -o output_dir")
            sys.exit(1)
        
        # skin_analysis_cli.py 임포트 및 실행
        try:
            from src.cli.skin_analysis_cli import run_analysis_pipeline, main_async
            
            input_path = Path(args.input)
            output_dir = Path(args.output)
            
            if args.async_mode:
                # 비동기 모드
                import asyncio
                
                async def run_async():
                    result = await run_analysis_pipeline_async(
                        input_image=input_path,
                        output_dir=output_dir,
                        do_restore=not args.no_restore,
                        debug=args.debug,
                        include_base64=not args.no_base64,
                        llm_report=args.llm_report,
                        llm_api_key=args.llm_api_key,
                        customer_id=args.customer_id,
                        gender=args.gender,
                        age=args.age,
                        race=args.race,
                        region=args.region,
                    )
                    
                    if args.output_json:
                        import json
                        with open(args.output_json, "w", encoding="utf-8") as f:
                            json.dump(result, f, indent=2, ensure_ascii=False)
                        print(f"결과가 {args.output_json}에 저장되었습니다.")
                    else:
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                
                from src.cli.skin_analysis_cli import run_analysis_pipeline_async
                asyncio.run(run_async())
            else:
                # 동기 모드
                result = run_analysis_pipeline(
                    input_image=input_path,
                    output_dir=output_dir,
                    do_restore=not args.no_restore,
                    debug=args.debug,
                    include_base64=not args.no_base64,
                    llm_report=args.llm_report,
                    llm_api_key=args.llm_api_key,
                    customer_id=args.customer_id,
                    gender=args.gender,
                    age=args.age,
                    race=args.race,
                    region=args.region,
                )
                
                if args.output_json:
                    import json
                    with open(args.output_json, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    print(f"결과가 {args.output_json}에 저장되었습니다.")
                else:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
        
        except ImportError as e:
            print(f"오류: skin_analysis_cli 모듈을 임포트할 수 없습니다: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"오류: {e}")
            sys.exit(1)
    else:
        # GUI 모드 (기본)
        print("GUI 모드로 실행합니다...")
        
        # GUI 임포트 및 실행
        try:
            from src.gui.image_enhancer import main as gui_main
            
            gui_main()
        
        except ImportError as e:
            print(f"오류: GUI 모듈을 임포트할 수 없습니다: {e}")
            print("GUI 모드를 사용하려면 PySide6를 설치하세요: pip install PySide6")
            sys.exit(1)
        except Exception as e:
            print(f"오류: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
