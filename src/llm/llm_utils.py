"""
llm_utils.py — LLM 유틸리티 모듈

보고서 로깅, JSON 직렬화, 파일 저장, 편의 함수 기능을 제공합니다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.llm.llm_formatters import SkinLLMReport
from src.llm.llm_config import get_default_model

log = logging.getLogger(__name__)


def log_report(report: SkinLLMReport) -> None:
    """로그 출력용"""
    sep = "=" * 70
    log.info(sep)
    log.info(f"  CÔTELEAF AI 피부 분석 소견  |  종합 {report.overall_score:.1f}점  |  인지나이 {report.perceived_age:.1f}세")
    log.info(sep)

    current_cat = None
    for mo in report.metric_opinions:
        if mo.category != current_cat:
            log.info(f"\n■ [{mo.category}]")
            current_cat = mo.category
        log.info(f"  [{mo.score:.1f}점 / {mo.grade}] {mo.display_name}")
        log.info(f"    {mo.opinion}")

    log.info(f"\n{'─'*70}")
    log.info("■ 종합 소견")
    log.info(f"  {report.overall_opinion}")

    log.info(f"\n{'─'*70}")
    log.info("■ 관리 권고사항")
    log.info(f"  {report.recommendation}")
    log.info(sep)


def report_to_dict(report: SkinLLMReport) -> Dict[str, Any]:
    """JSON 직렬화용 딕셔너리 변환 (점수는 정수로 변환)"""
    # matched_products의 match_score를 정수로 변환
    matched_products_int = []
    for product in report.matched_products:
        product_copy = product.copy()
        if "match_score" in product_copy:
            try:
                product_copy["match_score"] = int(round(float(product_copy["match_score"])))
            except (TypeError, ValueError):
                pass
        matched_products_int.append(product_copy)

    return {
        "overall_score": int(round(report.overall_score)),
        "perceived_age": int(round(report.perceived_age)),
        "overall_opinion": report.overall_opinion,
        "recommendation": report.recommendation,
        "product_recommendations": report.product_recommendations,
        "matched_products": matched_products_int,
        "metric_opinions": [
            {
                "key": mo.key,
                "display_name": mo.display_name,
                "category": mo.category,
                "score": int(round(mo.score)),
                "grade": mo.grade,
                "opinion": mo.opinion,
            }
            for mo in report.metric_opinions
        ],
    }


def save_report_json(report: SkinLLMReport, output_path: str | Path) -> Path:
    """보고서를 JSON 파일로 저장"""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(report_to_dict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("보고서 저장: %s", p)
    return p


# ──────────────────────────────────────────────────────────────
# 편의 함수 (단일 호출 진입점)
# ──────────────────────────────────────────────────────────────

def analyze_and_report(
    image_path: str | Path,
    llm_api_key: Optional[str] = None,
    *,
    model_name: Optional[str] = None,
    print_console: bool = True,
    save_json_path: Optional[str | Path] = None,
    analyzer_kwargs: Optional[Dict[str, Any]] = None,
    provide_scores: bool = True,  # 점수 제공 여부
) -> SkinLLMReport:
    """
    이미지 경로 하나로 피부 분석 + LLM 소견 생성까지 원스탑 실행.

    Parameters
    ----------
    image_path : str | Path
        분석할 얼굴 이미지 경로
    llm_api_key : str, optional
        LLM API 키. 지정하지 않으면 config/secrets.json에서 자동 로드합니다.
    model_name : str, optional
        LLM 모델명. 지정하지 않으면 config.json에서 기본값 로드.
    print_console : bool
        True 이면 콘솔에 결과 출력
    save_json_path : str | Path | None
        지정 시 해당 경로에 JSON 저장
    analyzer_kwargs : dict | None
        SkinAnalyzer.analyze_all() 에 전달할 추가 인자
    provide_scores : bool
        True 이면 측정 점수를 LLM에 제공, False 이면 항목명과 기준만 제공

    Returns
    -------
    SkinLLMReport
    """
    # 기본값 로드 (config reload 지원)
    if model_name is None:
        model_name = get_default_model()

    # ── 1. 피부 분석 ──────────────────────────────────────────
    from src.scoring.skin_scoring import SkinAnalyzer   # 런타임 임포트 (동일 디렉터리 필요)

    kwargs = analyzer_kwargs or {}
    analyzer = SkinAnalyzer()
    log.info("피부 분석 시작: %s", image_path)
    analysis_result: Dict[str, Any] = analyzer.analyze_all(str(image_path), **kwargs)
    
    # 점수 안전장치 적용 (복원 이미지의 경우 원본보다 점수가 낮으면 조정)
    # utils.apply_score_safety_net은 원본/복원 경로가 필요하지만,
    # 여기서는 단일 이미지 분석이므로 조정 없이 원본 점수 사용
    # 필요한 경우 별도로 점수 조정 로직 추가 가능
    
    log.info(
        "피부 분석 완료 — 종합 %.1f점, 인지나이 %.1f세",
        analysis_result.get("overall_score", 0),
        analysis_result.get("perceived_age", 0),
    )

    # ── 2. LLM 소견 생성 ───────────────────────────────────
    from src.llm.llm_reporter import LLMSkinReporter  # 런타임 임포트 (순환 참조 방지)
    
    reporter = LLMSkinReporter(
        api_key=llm_api_key,  # None이면 secrets.json에서 자동 로드
        model_name=model_name,
    )
    report = reporter.generate_report_from_measurements(
        image_path,
        analysis_result.get("measurements_report") or analysis_result.get("measurements", {}),
        analysis_result.get("overall_score", 0),
        analysis_result.get("perceived_age", 0),
        provide_scores=provide_scores,
    )

    # ── 3. 출력 / 저장 ───────────────────────────────────────
    if print_console:
        log_report(report)
    if save_json_path:
        save_report_json(report, save_json_path)

    return report
