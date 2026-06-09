#!/usr/bin/env python
"""
CÔTELEAF LLM 소견 생성 — CLI 실행 스크립트
==============================================

사용법:
  python run_llm_report.py face.jpg --api-key YOUR_LLM_KEY
  python run_llm_report.py face.jpg --api-key YOUR_KEY --save-json report.json
  python run_llm_report.py face.jpg --api-key YOUR_KEY --model gemini-2.5-flash

환경변수로 API 키 지정:
  export GEMINI_API_KEY=AIza...
  python run_llm_report.py face.jpg
"""

import argparse
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.utils import setup_logging


from src.utils.config import load_config as _load_config


# config.json에서 설정 로드 (lazy getter)
def _get_config() -> dict:
    return _load_config()

def get_default_model() -> str:
    """config.json에서 기본 LLM 모델을 가져옵니다."""
    return _get_config().get("llm", {}).get("default_model", "models/gemini-2.5-pro")

# 하위 호환성을 위해 모듈 레벨 상수 유지
DEFAULT_MODEL = get_default_model()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CÔTELEAF 피부 분석 + LLM 소견 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("image", nargs="?", help="분석할 얼굴 이미지 경로 (JPG/PNG). --list-models 또는 --check-model 사용 시 생략 가능")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="LLM API 키 (미지정 시 GEMINI_API_KEY 환경변수 사용)",
    )
    from src.llm.llm_skin_report import LlmSkinReporter
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"LLM 모델명 (기본: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--save-json",
        metavar="PATH",
        default=None,
        help="보고서 JSON 저장 경로",
    )
    parser.add_argument(
        "--no-print",
        action="store_true",
        help="콘솔 출력 생략",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="사용 가능한 Gemini 모델 목록 표시 후 종료",
    )
    parser.add_argument(
        "--check-model",
        type=str,
        metavar="MODEL",
        help="특정 모델이 사용 가능한지 확인",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="디버그 로그 활성화",
    )

    args = parser.parse_args()

    # 로깅 설정 (debug 플래그 지원)
    log_level = "DEBUG" if args.debug else None
    setup_logging(level=log_level, mode="cli")
    import logging
    log = logging.getLogger(__name__)

    # --list-models 옵션 처리
    if args.list_models:
        from src.llm.llm_skin_report import list_available_models
        models = list_available_models(args.api_key)
        if models:
            logger.info("사용 가능한 Gemini 모델 목록:")
            for model in sorted(models):
                logger.info(f"  - {model}")
        else:
            logger.warning("사용 가능한 모델을 찾을 수 없습니다.")
        return 0

    # --check-model 옵션 처리
    if args.check_model:
        from src.llm.llm_skin_report import check_model_availability
        is_available = check_model_availability(args.check_model, args.api_key)
        if is_available:
            logger.info(f"모델 '{args.check_model}' 사용 가능")
            return 0
        else:
            logger.warning(f"모델 '{args.check_model}' 사용 불가능")
            return 1

    # API 키 검증
    if not args.api_key:
        logger.error("LLM API 키가 없습니다. --api-key 인자 또는 GEMINI_API_KEY 환경변수를 설정하세요.")
        return 1

    # 이미지 경로 검증 (--list-models 또는 --check-model 사용 시 생략 가능)
    if args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            logger.error(f"이미지 파일을 찾을 수 없습니다: {image_path}")
            return 1
    else:
        image_path = None

    # 실행
    if image_path is None:
        logger.error("이미지 경로가 필요합니다. --list-models 또는 --check-model을 사용하세요.")
        return 1
    
    try:
        from src.llm.llm_skin_report import analyze_and_report

        analyze_and_report(
            image_path=image_path,
            llm_api_key=args.api_key,
            model_name=args.model,
            print_console=not args.no_print,
            save_json_path=args.save_json,
        )
    except Exception as exc:
        logger.error(f"실행 오류: {exc}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1

    return 0


# ──────────────────────────────────────────────────────────────
# 코드 내 직접 호출 예제 (스크립트가 아닌 모듈로 임포트할 때)
# ──────────────────────────────────────────────────────────────

def example_direct_usage():
    """
    Python 코드 내에서 직접 사용하는 예제.
    analyze_and_report() : 분석 + 소견 생성 원스탑 함수
    """
    from src.llm.llm_skin_report import (
        LlmSkinReporter,
        analyze_and_report,
        print_report,
        report_to_dict,
        save_report_json,
    )

    # ── 방법 A: 원스탑 편의 함수 ─────────────────────────────
    report = analyze_and_report(
        image_path="face_front.jpg",
        llm_api_key="AIzaSy...",
        model_name="gemini-2.5-flash",   # 또는 "models/gemini-2.5-pro"
        print_console=True,
        save_json_path="output/report.json",
    )

    # ── 방법 B: 단계별 수동 제어 ─────────────────────────────
    from src.scoring.skin_scoring import SkinAnalyzer, analyze_all_multi_v3

    # 1. 피부 분석 (단일 or 멀티뷰)
    analyzer = SkinAnalyzer()
    result = analyzer.analyze_all("face_front.jpg")

    # 멀티뷰 분석 (3장)
    # result = analyze_all_multi_v3("front.jpg", "left45.jpg", "right45.jpg")

    # 2. LLM 소견 생성
    reporter = LlmSkinReporter(
        api_key="AIzaSy...",
        model_name="gemini-2.5-flash",
        max_retries=3,
        retry_delay=5.0,
    )
    report = reporter.generate_report(
        image_path="face_front.jpg",
        measurements=result,
    )

    # 3. 결과 활용
    print_report(report)                          # 콘솔 출력
    save_report_json(report, "report.json")       # JSON 저장
    d = report_to_dict(report)                   # dict 변환 (API 응답 등)

    # 항목별 접근
    for mo in report.metric_opinions:
        logger.info(f"{mo.display_name}: {mo.score:.1f}점 → {mo.opinion}")

    # 종합 소견만
    logger.info(report.overall_opinion)
    logger.info(report.recommendation)


if __name__ == "__main__":
    sys.exit(main())
