#!/usr/bin/env python3
"""
CLI Entry Point - 명령줄 인터페이스 진입점

이 모듈은 CLI 모드의 진입점으로, pipeline_runner를 사용하여
피부 분석 파이프라인을 실행합니다.

사용법:
    python -m src.cli.entry -i input.jpg -o output_dir
    python -m src.cli.entry -i input.jpg -o output_dir --llm-report
    python -m src.cli.entry -i input.jpg -o output_dir --customer-id CUST001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from src.utils.utils import setup_logging
from src.pipeline.pipeline_runner import run_pipeline, run_pipeline_async


def main() -> int:
    """CLI 메인 함수."""
    parser = argparse.ArgumentParser(
        description="SkinLens CLI - 피부 분석 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 필수 인자
    parser.add_argument("-i", "--input", type=str, required=True, help="입력 이미지 경로")
    parser.add_argument("-o", "--output", type=str, required=True, help="출력 디렉토리 경로")

    # 선택적 인자
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

    # 입력/출력 경로
    input_path = Path(args.input)
    output_dir = Path(args.output)

    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}")
        return 1

    # 로깅 설정: 이미지 파일명을 customer_id로 사용하여 로그파일명에 포함
    # customer_id가 제공되지 않으면 이미지 파일명(확장자 제외)을 사용
    log_customer_id = args.customer_id or input_path.stem
    setup_logging(mode="cli", customer_id=log_customer_id)
    import logging
    log = logging.getLogger(__name__)

    # 파이프라인 실행: 기존 skin_analysis_cli.py의 전체 파이프라인 사용 (분석 포함)
    try:
        from src.cli.skin_analysis_cli import run_analysis_pipeline, run_analysis_pipeline_async

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
                    with open(args.output_json, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    print(f"결과가 {args.output_json}에 저장되었습니다.")
                else:
                    print(json.dumps(result, indent=2, ensure_ascii=False))

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
                with open(args.output_json, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"결과가 {args.output_json}에 저장되었습니다.")
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))

        return 0

    except Exception as e:
        print(f"오류: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
