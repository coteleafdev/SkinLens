#!/usr/bin/env python3
"""
Pipeline Runner - 공통 파이프라인 실행기

CLI와 GUI 모두에서 사용하는 파이프라인 실행 로직을 중앙화합니다.
이 모듈은 파이프라인 실행의 핵심 로직을 포함하며, CLI/GUI 특화 로직은
각각의 래퍼 모듈에서 처리합니다.

주요 기능:
- 동기 파이프라인 실행 (run_pipeline)
- 비동기 파이프라인 실행 (run_pipeline_async)
- 점수 변환 (int로 변환)
- 결과 JSON 생성
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import asdict

from src.pipeline.pipeline_core import (
    run_enhancement_pipeline,
    PipelineSettings,
    PipelineResult,
)
from src.utils.utils import setup_logging

log = logging.getLogger(__name__)

# 기본 서버 URL
SERVER_URL = "http://localhost:8000"


def _convert_scores_to_int(result: Dict[str, Any]) -> Dict[str, Any]:
    """모든 점수를 정수로 변환합니다.

    참고: 이 함수는 skin_analysis_cli.py의 전체 분석 결과에 사용됩니다.
    pipeline_runner의 기본 PipelineResult에는 분석 점수가 포함되지 않습니다.

    Args:
        result: 파이프라인 결과 딕셔너리

    Returns:
        점수가 정수로 변환된 결과 딕셔너리
    """
    if "internal_analysis" in result:
        for analysis_type in ["original", "restored"]:
            if analysis_type in result["internal_analysis"]:
                analysis = result["internal_analysis"][analysis_type]
                if "overall_score" in analysis:
                    analysis["overall_score"] = int(round(float(analysis["overall_score"])))
                if "perceived_age" in analysis:
                    analysis["perceived_age"] = int(round(float(analysis["perceived_age"])))
                if "scores" in analysis:
                    for metric_key, value in analysis["scores"].items():
                        if isinstance(value, (int, float)):
                            analysis["scores"][metric_key] = int(round(float(value)))

    if "llm_analysis" in result:
        for analysis_type in ["original", "restored", "reference"]:
            if analysis_type in result["llm_analysis"]:
                analysis = result["llm_analysis"][analysis_type]
                if "overall_score" in analysis:
                    analysis["overall_score"] = int(round(float(analysis["overall_score"])))
                if "perceived_age" in analysis:
                    analysis["perceived_age"] = int(round(float(analysis["perceived_age"])))
                if "metric_opinions" in analysis:
                    for opinion in analysis["metric_opinions"]:
                        if "score" in opinion:
                            opinion["score"] = int(round(float(opinion["score"])))

    return result


def run_pipeline(
    input_image: Path,
    output_dir: Path,
    *,
    do_restore: bool = True,
    debug: bool = False,
    include_base64: bool = False,
    base_url: str = SERVER_URL,
    score_safety_net: bool = True,
    llm_report: bool = True,
    llm_api_key: Optional[str] = None,
    llm_scores: Optional[Dict[str, Any]] = None,
    customer_id: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    race: Optional[str] = None,
    region: Optional[str] = None,
    lateral_images: Optional[list] = None,
    use_multi_view_analysis: bool = True,
    input_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """피부 분석 파이프라인을 동기로 실행합니다.

    Args:
        input_image: 입력 이미지 경로
        output_dir: 출력 디렉토리 경로
        do_restore: 복원 수행 여부
        debug: 디버그 모드
        include_base64: base64 인코딩 포함 여부
        base_url: 기본 URL
        score_safety_net: 점수 안전장치 적용 여부
        llm_report: LLM 소견 생성 여부
        llm_api_key: LLM API 키
        llm_scores: LLM 점수
        customer_id: 고객 ID
        gender: 성별
        age: 연령
        race: 인종
        region: 지역
        lateral_images: 측면 이미지 목록
        use_multi_view_analysis: 다중 뷰 분석 사용 여부
        input_json: 입력 JSON 데이터

    Returns:
        파이프라인 결과 딕셔너리
    """
    log.info(f"파이프라인 시작: {input_image}")

    # 파이프라인 설정 (PipelineSettings는 실제 파이프라인 코어의 설정만 포함)
    # CLI/GUI 특화 파라미터는 별도로 처리
    settings = PipelineSettings(
        llm_report=llm_report,
    )

    # 파이프라인 실행 (시그니처: cfg, out_dir, *, input_image, do_restore)
    result: PipelineResult = run_enhancement_pipeline(
        cfg=settings,
        out_dir=output_dir,
        input_image=input_image,
        do_restore=do_restore,
    )

    # 결과를 딕셔너리로 변환 (PipelineResult는 dataclass)
    result_dict = asdict(result)

    # Path 객체를 문자열로 변환
    if result_dict.get("restored"):
        result_dict["restored"] = str(result_dict["restored"])

    log.info(f"파이프라인 완료: {input_image}")

    return result_dict


async def run_pipeline_async(
    input_image: Path,
    output_dir: Path,
    *,
    do_restore: bool = True,
    debug: bool = False,
    include_base64: bool = False,
    base_url: str = SERVER_URL,
    score_safety_net: bool = True,
    llm_report: bool = True,
    llm_api_key: Optional[str] = None,
    llm_scores: Optional[Dict[str, Any]] = None,
    customer_id: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    race: Optional[str] = None,
    region: Optional[str] = None,
    lateral_images: Optional[list] = None,
    use_multi_view_analysis: bool = True,
    input_json: Optional[Dict[str, Any]] = None,
    executor=None,
) -> Dict[str, Any]:
    """피부 분석 파이프라인을 비동기로 실행합니다.

    Args:
        input_image: 입력 이미지 경로
        output_dir: 출력 디렉토리 경로
        do_restore: 복원 수행 여부
        debug: 디버그 모드
        include_base64: base64 인코딩 포함 여부
        base_url: 기본 URL
        score_safety_net: 점수 안전장치 적용 여부
        llm_report: LLM 소견 생성 여부
        llm_api_key: LLM API 키
        llm_scores: LLM 점수
        customer_id: 고객 ID
        gender: 성별
        age: 연령
        race: 인종
        region: 지역
        lateral_images: 측면 이미지 목록
        use_multi_view_analysis: 다중 뷰 분석 사용 여부
        input_json: 입력 JSON 데이터
        executor: 비동기 실행기

    Returns:
        파이프라인 결과 딕셔너리
    """
    import asyncio
    import functools

    log.info(f"비동기 파이프라인 시작: {input_image}")

    # 동기 함수를 비동기로 실행
    loop = asyncio.get_event_loop()
    if executor is None:
        executor = None  # 기본 executor 사용

    result = await loop.run_in_executor(
        executor,
        functools.partial(
            run_pipeline,
            input_image,
            output_dir,
            do_restore=do_restore,
            debug=debug,
            include_base64=include_base64,
            base_url=base_url,
            score_safety_net=score_safety_net,
            llm_report=llm_report,
            llm_api_key=llm_api_key,
            llm_scores=llm_scores,
            customer_id=customer_id,
            gender=gender,
            age=age,
            race=race,
            region=region,
            lateral_images=lateral_images,
            use_multi_view_analysis=use_multi_view_analysis,
            input_json=input_json,
        ),
    )

    log.info(f"비동기 파이프라인 완료: {input_image}")

    return result
