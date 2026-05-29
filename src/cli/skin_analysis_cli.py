#!/usr/bin/env python3
"""
COTELEAF Skin Analysis CLI (Server-Ready)

서버 환경에서 GUI 없이 동작하는 CLI 기반 피부 분석 파이프라인.

워크플로우:
1. 원본 이미지 입력
2. 복원 파이프라인 실행 (pipeline_core.run_enhancement_pipeline)
3. 복원 이미지를 기준으로 원본 이미지 분석 (skin_scoring)
4. 점수 안전장치 적용 (utils.apply_score_safety_net)
5. Gemini AI 소견 작성 (llm_prompt_template.md 사용)
6. 결과 JSON 출력

사용법:
    python skin_analysis_cli.py -i input.jpg -o output_dir
    python skin_analysis_cli.py -i input.jpg -o output_dir --llm-report
    python skin_analysis_cli.py -i input.jpg -o output_dir --llm-report --llm-api-key YOUR_API_KEY
    python skin_analysis_cli.py -i input.jpg -o output_dir --customer-id CUST001 --gender female --age 30 --race asian --region KR

비동기 사용법 (서버 환경용):
    import asyncio
    from skin_analysis_cli import run_analysis_pipeline_async
    
    result = await run_analysis_pipeline_async(...)
"""

import argparse
import asyncio
import base64
import copy
import json
from src.utils.utils import setup_logging
import os
import sys
import traceback
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

# 프로젝트 모듈 import
from src.pipeline.pipeline_core import (
    run_enhancement_pipeline,
    PipelineSettings,
    PipelineResult,
)
from src.scoring.skin_scoring import SkinAnalyzer
from src.llm.llm_skin_report import LlmSkinReporter
from src.cli.execution_history import ExecutionHistoryDB, get_db_path_from_env, ResourceMonitor, PSUTIL_AVAILABLE


# 중앙 집중식 로깅 설정
setup_logging()
log = logging.getLogger(__name__)


from src.utils.config import load_config as _load_config


# config.json에서 설정 로드 (lazy getter)
def _get_config() -> Dict[str, Any]:
    return _load_config()

def get_server_url() -> str:
    """config.json에서 서버 URL을 가져옵니다 (환경 변수 우선)."""
    config = _get_config()
    server_config = config.get("server", {})
    return os.getenv("SERVER_URL", server_config.get("url", "http://localhost:8000"))

def get_cli_defaults() -> Dict[str, Any]:
    """config.json에서 CLI 기본값을 가져옵니다."""
    return _get_config().get("cli_defaults", {})

# 서버 기본 URL (lazy getter 사용 권장)
SERVER_URL = get_server_url()


def _create_error_json(
    error: Exception,
    input_image: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    debug: bool = False,
    customer_id: Optional[str] = None,
    pipeline_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """오류 정보를 JSON 형식으로 생성."""
    error_json = {
        "error": True,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "timestamp": datetime.now().isoformat(),
        "input_image": str(input_image) if input_image else None,
        "output_dir": str(output_dir) if output_dir else None,
    }
    
    if debug:
        error_json["error_traceback"] = traceback.format_exc()
    
    # 6. 에러 분석 기록
    try:
        db_path = get_db_path_from_env()
        db = ExecutionHistoryDB(db_path)
        
        # 스택 트레이스 추출
        stack_trace = traceback.format_exc() if debug else None
        
        # 심각도 판정
        error_type_name = type(error).__name__
        if error_type_name in ("MemoryError", "RuntimeError", "SystemError"):
            severity = "critical"
        elif error_type_name in ("ValueError", "KeyError", "TypeError"):
            severity = "medium"
        else:
            severity = "high"
        
        db.record_error(
            error_type=error_type_name,
            error_message=str(error),
            module=error.__traceback__.tb_frame.f_globals.get('__name__') if error.__traceback__ else None,
            function=error.__traceback__.tb_frame.f_code.co_name if error.__traceback__ else None,
            line_number=error.__traceback__.tb_lineno if error.__traceback__ else None,
            stack_trace=stack_trace,
            customer_id=customer_id,
            image_path=str(input_image) if input_image else None,
            pipeline_mode=pipeline_mode,
            severity=severity,
        )
    except Exception as e:
        log.warning("에러 분석 기록 실패: %s", e)
    
    return error_json


def _image_to_base64(image_path: Path) -> str:
    """이미지를 base64 문자열로 변환."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def run_analysis_pipeline(
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
    customer_id: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    race: Optional[str] = None,
    region: Optional[str] = None,
    lateral_images: Optional[List[Dict[str, str]]] = None,
    use_multi_view_analysis: bool = True,
    input_json: Optional[Dict[str, Any]] = None,
    # lateral_images: [{"angle": "front"|"left45"|"right45", "path": "/path/to/img.jpg"}, ...]
    # use_multi_view_analysis: 다중 뷰 분석 사용 여부 (기본 True)
) -> Dict[str, Any]:
    """복원 → 분석 통합 파이프라인 실행.

    Parameters
    ----------
    lateral_images:
        다중 각도 이미지 목록. 서버(create_job)가 수신한 전 각도 이미지 경로와
        각도 라벨을 담아 전달. 파이프라인 분석은 input_image(front)를 기준으로
        수행하고, lateral_images 메타데이터는 결과 JSON에 포함됩니다.
    use_multi_view_analysis:
        다중 뷰 분석 사용 여부. True인 경우 좌/우 45° 이미지도 분석하여 통합 결과를 반환합니다.
    """
    
    # 실행 시간 측정 시작
    start_time = time.time()
    restore_start_time = None
    analysis_start_time = None
    llm_start_time = None
    
    # 리소스 모니터링 시작
    resource_monitor = None
    if PSUTIL_AVAILABLE:
        try:
            resource_monitor = ResourceMonitor()
            resource_monitor.start()
            log.info("리소스 모니터링 시작")
        except Exception as e:
            log.warning("리소스 모니터링 시작 실패: %s", e)
    
    log.info("=== COTELEAF Skin Analysis Pipeline ===")
    log.info("입력 이미지: %s", input_image)
    log.info("출력 디렉토리: %s", output_dir)
    
    # 출력 디렉토리 생성
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # ── 다중 이미지 경로 추출 ───────────────────────────────────────
    left45_path = None
    right45_path = None
    if lateral_images:
        for img in lateral_images:
            angle = img.get("angle")
            path = img.get("path")
            if angle == "left45" and path:
                left45_path = Path(path)
            elif angle == "right45" and path:
                right45_path = Path(path)
    
    if left45_path:
        log.info("좌측 45° 이미지: %s", left45_path)
    if right45_path:
        log.info("우측 45° 이미지: %s", right45_path)
    
    # ── 단계 1: 복원 파이프라인 ────────────────────────────────────────
    log.info("[단계 1/2] 복원 파이프라인 실행 중...")
    restore_start_time = time.time()

    # [REFACTOR P1-16] config.json의 restoration 설정을 반영
    from src.scoring.skin_scoring import get_restoration_config
    resto = get_restoration_config()
    cfg = PipelineSettings(
        codeformer_fidelity=resto.get("codeformer_fidelity", 1.0),
        codeformer_upscale=resto.get("codeformer_upscale", 2),
        codeformer_bg_upsampler=resto.get("codeformer_bg_upsampler", "none"),
        codeformer_additional=resto.get("codeformer_additional", True),
    )
    
    # 다중 이미지 복원 (병렬)
    restored_image = None
    restored_left45 = None
    restored_right45 = None
    
    if use_multi_view_analysis and left45_path and right45_path:
        log.info("다중 이미지 복원 (병렬)...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            futures.append(executor.submit(
                run_enhancement_pipeline,
                cfg=cfg,
                out_dir=output_dir,
                input_image=input_image,
                do_restore=do_restore,
            ))
            futures.append(executor.submit(
                run_enhancement_pipeline,
                cfg=cfg,
                out_dir=output_dir,
                input_image=left45_path,
                do_restore=do_restore,
            ))
            futures.append(executor.submit(
                run_enhancement_pipeline,
                cfg=cfg,
                out_dir=output_dir,
                input_image=right45_path,
                do_restore=do_restore,
            ))
            
            results = [f.result() for f in futures]
            
            # 복원 이미지 경로 결정
            if results[0].restored and results[0].restored.exists():
                restored_image = results[0].restored
            if results[1].restored and results[1].restored.exists():
                restored_left45 = results[1].restored
            if results[2].restored and results[2].restored.exists():
                restored_right45 = results[2].restored
    else:
        # 단일 이미지 복원
        restore_result: PipelineResult = run_enhancement_pipeline(
            cfg=cfg,
            out_dir=output_dir,
            input_image=input_image,
            do_restore=do_restore,
        )
        
        # 복원 이미지 경로 결정
        if restore_result.restored and restore_result.restored.exists():
            restored_image = restore_result.restored
    
    if not restored_image:
        raise RuntimeError("복원 이미지가 생성되지 않았습니다.")
    
    log.info("복원 완료: %s", restored_image)
    if restored_left45:
        log.info("좌측 45° 복원 완료: %s", restored_left45)
    if restored_right45:
        log.info("우측 45° 복원 완료: %s", restored_right45)
    
    # ── 단계 2: 원본 이미지 분석 ─────────────────────────────────────
    # [FIX BUG-3] pre_analyzed 결과를 apply_score_safety_net에 주입하여 재분석 방지
    log.info("원본 이미지 분석 중...")
    analysis_start_time = time.time()

    # 다중 뷰 분석
    if use_multi_view_analysis and left45_path and right45_path:
        log.info("다중 뷰 분석 (정면 + 좌45° + 우45°)...")
        from src.scoring.skin_scoring import analyze_all_multi_v3
        
        # 복원된 이미지 사용
        analysis_input = restored_image if do_restore else input_image
        left_input = restored_left45 if (do_restore and restored_left45) else left45_path
        right_input = restored_right45 if (do_restore and restored_right45) else right45_path
        
        analysis_result = analyze_all_multi_v3(
            str(analysis_input),
            left45_path=str(left_input) if left_input else None,
            right45_path=str(right_input) if right_input else None,
            debug=debug,
            use_full_analysis=True,
        )
        
        # original_analysis는 정면만 분석한 결과 (점수 안전장치용)
        analyzer = SkinAnalyzer()
        original_analysis = analyzer.analyze_all(
            str(input_image),
            debug=debug,
        )
    else:
        # 단일 뷰 분석
        analyzer = SkinAnalyzer()
        original_analysis = analyzer.analyze_all(
            str(input_image),
            debug=debug,
        )
        analysis_result = copy.deepcopy(original_analysis)

    log.info("분석 완료")

    # ── 피부 타입 자동 감지 ─────────────────────────────────────────────
    try:
        from src.scoring.skin_scoring import detect_skin_type
        skin_type_detection = detect_skin_type(analysis_result)
        analysis_result["skin_type_detection"] = {
            "skin_types": skin_type_detection.skin_types,
            "primary_type": skin_type_detection.primary_type,
            "secondary_type": skin_type_detection.secondary_type,
            "confidence": skin_type_detection.confidence,
            "all_scores": skin_type_detection.all_scores,
            "features": skin_type_detection.features,
            "zone_analysis": skin_type_detection.zone_analysis
        }
        log.info(f"피부 타입 감지 완료: {skin_type_detection.skin_types} (신뢰도: {skin_type_detection.confidence:.2f})")
    except Exception as e:
        log.warning(f"피부 타입 감지 실패: {e}")
        analysis_result["skin_type_detection"] = None

    # 점수 안전장치 적용
    i1 = None  # [P1-3] 초기화 추가 - 예외 발생 시 NameError 방지
    if score_safety_net and do_restore:
        log.info("점수 안전장치 적용 중...")
        try:
            from src.utils.utils import apply_score_safety_net
            from src.scoring.skin_scoring import SkinAnalyzer
            # [FIX BUG-3] pre_analyzed_original, pre_analyzed_restored 전달로 재분석 방지
            restored_analysis = SkinAnalyzer().analyze_all(str(restored_image))
            o, i1, i2 = apply_score_safety_net(
                input_image,
                restored_image,
                pre_analyzed_original=original_analysis,
                pre_analyzed_restored=restored_analysis,
            )
            # 안전장치가 적용된 복원 이미지 점수로 analysis_result 업데이트
            if i1:
                # [FIX BUG-1] utils.py 가 저장하는 키와 일치시킴
                # overall_score_report_before_safety_net: utils [FIX BUG-1]에서 추가된 키
                for _src_key in (
                    "overall_score_before_safety_net",
                    "overall_score_report_before_safety_net",
                    "safety_net_adjusted",
                    "safety_net_adjusted_keys",
                    "safety_net_clamp_keys",
                    "safety_net_boost_keys",
                ):
                    if _src_key in i1:
                        analysis_result[_src_key] = i1[_src_key]
                # 조정된 종합점수 반영
                for _score_key in ("overall_score_report", "overall_score",
                                   "overall_score_report_raw", "overall_score_raw"):
                    if _score_key in i1:
                        analysis_result[_score_key] = i1[_score_key]
                # measurements_report 반영 (복원 점수 조정 결과)
                # [FIX BUG-2] measurements_v26 참조 제거 — v3.2 이후 삭제된 필드
                for _meas_key in ("measurements_report", "measurements"):
                    if _meas_key in i1:
                        analysis_result[_meas_key] = i1[_meas_key]
                # [FIX] perceived_age 반영 (복원 인지 나이 사용)
                if "perceived_age" in i1:
                    analysis_result["perceived_age"] = i1["perceived_age"]
            log.info("점수 안전장치 적용 완료")
        except Exception as e:
            log.warning("점수 안전장치 적용 실패, 원래 점수 사용: %s", e)
    
    # ── 설문 JSON 로드 ───────────────────────────────────────────────
    survey_info = None
    if input_json:
        try:
            survey = input_json.get("survey", {})
            survey_info = json.dumps(survey, ensure_ascii=False)
            log.info("설문 정보 로드 완료")
        except Exception as e:
            log.warning(f"설문 정보 로드 실패: {e}")
    
    # ── LLM AI 소견 작성 ─────────────────────────────────────────────
    if llm_report:
        log.info("LLM (Gemini) AI 소견 작성 중...")
        llm_start_time = time.time()
        try:
            # API 키 직접 주입 (환경변수 오염 방지)
            reporter = LlmSkinReporter(api_key=llm_api_key)

            if do_restore:
                # 듀얼 이미지 모드: 원본과 복원 이미지 소견 작성
                orig_analysis = original_analysis  # [FIX] 원본 분석 결과 직접 사용 (복원 점수로 덮어쓴 analysis_result 사용 방지)
                rest_analysis = i1 if (score_safety_net and do_restore and i1) else analysis_result

                llm_result = reporter.generate_report_from_dual_images(
                    orig_image_path=str(input_image),
                    orig_measurements_report=orig_analysis.get("measurements_report", {}),
                    orig_overall_score=float(orig_analysis.get("overall_score", 0)),
                    orig_perceived_age=float(orig_analysis.get("perceived_age", 0)),
                    ideal_image_path=str(restored_image),
                    ideal_measurements_report=rest_analysis.get("measurements_report", {}),
                    ideal_overall_score=float(rest_analysis.get("overall_score", 0)),
                    ideal_perceived_age=float(rest_analysis.get("perceived_age", 0)),
                    provide_scores=args.llm_scores,  # [FIX] GUI와 동일하게 args.llm_scores 사용 (기본 False)
                    survey_info=survey_info,
                )
            else:
                # 단일 이미지 모드: 원본 이미지 소견 작성
                llm_result = reporter.generate_report_from_measurements(
                    image_path=str(input_image),
                    measurements_report=analysis_result.get("measurements_report", {}),
                    overall_score=float(analysis_result.get("overall_score", 0)),
                    perceived_age=float(analysis_result.get("perceived_age", 0)),
                    provide_scores=args.llm_scores,  # [FIX] GUI와 동일하게 args.llm_scores 사용 (기본 False)
                    survey_info=survey_info,
                )

            analysis_result["llm_report"] = llm_result
            if isinstance(llm_result, tuple):
                # 듀얼 이미지 모드: (orig_report, ideal_report)
                orig_report, ideal_report = llm_result
                if hasattr(orig_report, 'model'):
                    analysis_result["llm_model"] = orig_report.model
                if hasattr(orig_report, 'llm_stats'):
                    analysis_result["llm_stats"] = orig_report.llm_stats
            elif hasattr(llm_result, 'model'):
                # 단일 이미지 모드
                analysis_result["llm_model"] = llm_result.model
            if hasattr(llm_result, 'llm_stats'):
                analysis_result["llm_stats"] = llm_result.llm_stats
            log.info("LLM (Gemini) AI 소견 작성 완료")
        except Exception as e:
            log.warning("LLM (Gemini) AI 소견 작성 실패: %s", e)
            analysis_result["llm_report"] = None
    
    # ── 결과 통합 ───────────────────────────────────────────────────────
    # 실행 시간 계산
    total_time = time.time() - start_time
    restore_time = restore_result.wall_restore_sec if restore_start_time else 0
    analysis_time = (analysis_start_time - start_time) if analysis_start_time else 0
    if llm_start_time:
        llm_time = time.time() - llm_start_time
    else:
        llm_time = 0
    
    # 1. 실행 시간 정보
    execution_time_info = {
        "total_sec": round(total_time, 2),
        "restore_sec": round(restore_time, 2),
        "analysis_sec": round(analysis_time, 2),
        "llm_sec": round(llm_time, 2)
    }
    
    # 2. 타임스탬프
    from datetime import datetime, timezone
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    timestamp_local = datetime.now().isoformat()
    
    # 3. 사용된 설정 정보
    settings_info = {
        "restorer": cfg.restorer.value if hasattr(cfg, 'restorer') else "unknown",
        "score_safety_net": score_safety_net,
        "analyzer_score_tune": cli_defaults.get("analyzer_score_tune", True),
        "device": config.get("device", {}).get("restoreformer_device", "auto")
    }
    
    # 5. 이미지 메타데이터
    def get_image_metadata(image_path):
        try:
            from PIL import Image
            img = Image.open(image_path)
            return {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "size_bytes": image_path.stat().st_size if image_path.exists() else 0
            }
        except Exception as e:
            log.warning("이미지 메타데이터 추출 실패: %s", e)
            return {}
    
    image_metadata_info = {
        "input": get_image_metadata(input_image),
        "restored": get_image_metadata(restored_image)
    }
    
    # 6. 파이프라인 상태
    pipeline_status_info = {
        "restore": "succeeded" if restore_result.restored else "failed",
        "analysis": "succeeded" if analysis_result else "failed",
        "llm": "succeeded" if analysis_result.get("llm_report") else "skipped"
    }
    
    # 7. 버전 정보
    version_info = {
        "config_version": config.get("version", "unknown"),
        "analyzer_version": "v3.0",
        "restorer_version": cfg.restorer.value if hasattr(cfg, 'restorer') else "unknown"
    }
    
    # 8. 환경 정보
    environment_info = {
        "device": config.get("device", {}).get("restoreformer_device", "auto"),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    }
    if resource_stats:
        environment_info["cpu_cores"] = resource_stats.get('cpu_cores', 0)
        environment_info["memory_peak_mb"] = resource_stats.get('memory_peak_mb', 0)
    
    # 9. 점수 조정 정보
    score_adjustment_info = {}
    if score_safety_net and i1:
        original_score = original_analysis.get("overall_score", 0)
        adjusted_score = i1.get("overall_score", 0)
        score_adjustment_info = {
            "safety_net_applied": True,
            "original_score": original_score,
            "adjusted_score": adjusted_score,
            "boost_delta": round(adjusted_score - original_score, 2)
        }
    
    # 10. 에러 정보 (정상적인 경우)
    error_info = None
    
    result = {
        "input_image": str(input_image),
        "restored_image": str(restored_image),
        "output_dir": str(output_dir),
        # 1. 실행 시간 정보
        "execution_time": execution_time_info,
        # 2. 타임스탬프
        "timestamp": timestamp_utc,
        "timestamp_local": timestamp_local,
        # 3. 사용된 설정 정보
        "settings": settings_info,
        "pipeline_mode": {
            "do_restore": do_restore,
        },
        "restoration_stats": {
            "wall_restore_sec": restore_result.wall_restore_sec,
            "notes": restore_result.notes,
        },
        # 5. 이미지 메타데이터
        "image_metadata": image_metadata_info,
        # 6. 파이프라인 상태
        "pipeline_status": pipeline_status_info,
        # 7. 버전 정보
        "version": version_info,
        # 8. 환경 정보
        "environment": environment_info,
        # 9. 점수 조정 정보
        "score_adjustment": score_adjustment_info,
        # 10. 에러 정보
        "error": error_info,
        "customer_info": {
            "customer_id": customer_id or "",
            "gender": gender or "",
            "age": age or 0,
            "race": race or "",
            "region": region or "",
        },
        "lateral_images": lateral_images or [{"angle": "front", "path": str(input_image)}],
        "analysis_result": analysis_result,
    }
    
    # URL 기반 이미지 경로 (서버 환경용)
    effective_base_url = base_url or SERVER_URL
    if effective_base_url:
        # 입력 이미지 URL (파일명만 사용)
        input_filename = input_image.name
        result["input_image_url"] = f"{effective_base_url.rstrip('/')}/{input_filename}"
        
        # 복원 이미지 URL (파일명만 사용)
        restored_filename = restored_image.name
        result["restored_image_url"] = f"{effective_base_url.rstrip('/')}/{restored_filename}"
    
    # base64 인코딩 옵션 (기본 False)
    if include_base64:
        result["input_image_base64"] = _image_to_base64(input_image)
        result["restored_image_base64"] = _image_to_base64(restored_image)
    
    # 실행 시간 측정 종료 및 이력 기록
    execution_time = time.time() - start_time
    log.info("실행 시간: %.2f초", execution_time)
    
    # 리소스 모니터링 종료
    resource_stats = None
    if resource_monitor:
        try:
            resource_stats = resource_monitor.stop()
            log.info("리소스 사용량: 메모리=%dMB, CPU=%.1f%%",
                     resource_stats['memory_peak_mb'],
                     resource_stats['cpu_percent_avg'])
        except Exception as e:
            log.warning("리소스 모니터링 종료 실패: %s", e)
    
    # 실행 이력 데이터베이스에 기록
    try:
        db_path = get_db_path_from_env()
        db = ExecutionHistoryDB(db_path)
        
        # 기존 실행 이력 기록
        db.log_execution(
            input_path=str(input_image),
            output_dir=str(output_dir),
            result=result,
            execution_time=execution_time,
            success=("error" not in result),
            resource_stats=resource_stats,
        )
        
        # 1. 분석 통계 기록
        overall_score_original = analysis_result.get("overall_score")
        overall_score_restored = i1.get("overall_score") if i1 else overall_score_original
        db.record_analysis_stat(
            customer_id=customer_id,
            success=("error" not in result),
            score_original=overall_score_original,
            score_restored=overall_score_restored,
            execution_time_sec=execution_time,
        )
        
        # 2. 모델 성능 기록 (피부 분석 모델)
        if resource_stats:
            db.record_model_performance(
                model_type="skin_analyzer",
                execution_time_ms=execution_time * 1000,
                memory_peak_mb=resource_stats.get('memory_peak_mb'),
                cpu_percent_avg=resource_stats.get('cpu_percent_avg'),
                success=("error" not in result),
            )
        
        # 3. 점수 추이 기록
        if customer_id and overall_score_restored is not None:
            measurements = analysis_result.get("measurements", {})
            # 이전 점수 조회
            previous_trends = db.get_score_trends(customer_id=customer_id, limit=1)
            previous_score = previous_trends[0]['overall_score'] if previous_trends else None
            improvement_delta = overall_score_restored - previous_score if previous_score else None
            
            db.record_score_trend(
                customer_id=customer_id,
                overall_score=overall_score_restored,
                measurements=measurements,
                improvement_delta=improvement_delta,
            )
        
        # 5. 이미지 메타데이터 기록
        try:
            from PIL import Image
            img = Image.open(input_image)
            width, height = img.size
            file_size = input_image.stat().st_size
            format_str = img.format or "UNKNOWN"
            
            db.record_image_metadata(
                analysis_id=None,  # execution ID를 가져와서 연결 가능
                image_type="original",
                file_size_bytes=file_size,
                width=width,
                height=height,
                format=format_str,
            )
            
            if do_restore and restored_image.exists():
                img_restored = Image.open(restored_image)
                width_r, height_r = img_restored.size
                file_size_r = restored_image.stat().st_size
                format_r = img_restored.format or "UNKNOWN"
                
                db.record_image_metadata(
                    analysis_id=None,
                    image_type="restored",
                    file_size_bytes=file_size_r,
                    width=width_r,
                    height=height_r,
                    format=format_r,
                )
        except Exception as e:
            log.warning("이미지 메타데이터 기록 실패: %s", e)
        
        log.info("실행 이력 및 통계 기록 완료")
    except Exception as e:
        log.warning("실행 이력 기록 실패: %s", e)
    
    return result


async def run_analysis_pipeline_async(
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
    customer_id: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    race: Optional[str] = None,
    region: Optional[str] = None,
    lateral_images: Optional[List[Dict[str, str]]] = None,
    use_multi_view_analysis: bool = True,
    executor: Optional[ThreadPoolExecutor] = None,
    input_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """복원 → 분석 통합 파이프라인 실행 (비동기 버전).
    
    Parameters
    ----------
    use_multi_view_analysis:
        다중 뷰 분석 사용 여부. True인 경우 좌/우 45° 이미지도 분석하여 통합 결과를 반환합니다.
    executor:
        외부에서 제공된 ThreadPoolExecutor (선택)
    """
    loop = asyncio.get_event_loop()
    
    # 외부 executor가 제공되지 않으면 생성
    _executor = executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=3)
        should_shutdown = True
    else:
        should_shutdown = False
    
    try:
        # 동기 함수를 비동기로 실행
        result = await loop.run_in_executor(
            _executor,
            run_analysis_pipeline,
            input_image,
            output_dir,
            do_restore,
            debug,
            include_base64,
            base_url,
            score_safety_net,
            llm_report,
            llm_api_key,
            customer_id,
            gender,
            age,
            race,
            region,
            lateral_images,
            use_multi_view_analysis,
            input_json,
        )
        return result
    finally:
        if should_shutdown:
            _executor.shutdown(wait=True)


async def main_async(args) -> None:
    """비동기 모드 메인 함수."""
    # 입력 파일 확인
    if not args.input.exists():
        log.error("입력 파일을 찾을 수 없습니다: %s", args.input)
        error_json = _create_error_json(
            FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {args.input}"),
            input_image=args.input,
            output_dir=args.output,
            debug=args.debug,
            customer_id=getattr(args, 'customer_id', None),
            pipeline_mode="cli",
        )
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_json, "w", encoding="utf-8") as f:
                f.write(json_output)
        else:
            print(json_output)
        
        sys.exit(1)
    
    try:
        result = await run_analysis_pipeline_async(
            input_image=args.input,
            output_dir=args.output,
            do_restore=not args.no_restore,
            debug=args.debug,
            include_base64=args.include_base64,
            base_url=args.base_url,
            score_safety_net=args.score_safety_net,
            llm_report=args.llm_report,
            llm_api_key=args.llm_api_key,
            customer_id=args.customer_id,
            gender=args.gender,
            age=args.age,
            race=args.race,
            region=args.region,
            use_multi_view_analysis=args.use_multi_view,
        )
        
        # 결과 출력
        json_output = json.dumps(result, indent=2, ensure_ascii=False)
        
        # 기본 JSON 저장 경로 (results 폴더)
        # 입력 이미지의 파일명을 사용하여 고객별 결과 누적
        if args.output_json:
            json_path = args.output_json
        else:
            input_filename = Path(args.input).stem  # 확장자 제거
            json_path = args.output / f"{input_filename}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        log.info("결과 JSON 저장: %s", json_path)
        
        # DB에 분석 결과 저장 (로컬 SQLite + Supabase 자동 동기화)
        try:
            from src.db.skin_analysis_db import SkinAnalysisDB
            db = SkinAnalysisDB(db_path=str(args.output / "skin_analysis.db"))
            db.save_analysis(
                original_path=args.input,
                restored_path=result.get("restored_image", ""),
                json_result=result,
                customer_id=args.customer_id,
            )
        except Exception as e:
            log.warning("DB 저장 실패: %s", e)
        
        # --output-json 옵션이 없으면 터미널에도 출력
        if not args.output_json:
            print(json_output)
        
        log.info("파이프라인 완료 (비동기 모드)")
        
    except Exception as e:
        log.error("파이프라인 실행 중 오류: %s", e, exc_info=args.debug)
        
        # 오류 JSON 생성 및 출력
        error_json = _create_error_json(
            e,
            input_image=args.input,
            output_dir=args.output,
            debug=args.debug,
            customer_id=getattr(args, 'customer_id', None),
            pipeline_mode="cli",
        )
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_json, "w", encoding="utf-8") as f:
                f.write(json_output)
            log.info("오류 JSON 저장: %s", args.output_json)
        else:
            print(json_output)
        
        sys.exit(1)


def main():
    # 프로젝트 이름과 버전 로드
    try:
        config = _get_config()
        project_name = config.get("project", {}).get("name", "SkinLens")
        project_version = config.get("project", {}).get("version", "1.0.0")
        description = f"{project_name} v{project_version} - AI Skin Analysis CLI - Server-Ready Pipeline"
    except Exception:
        description = "SkinLens v1.0.0 - AI Skin Analysis CLI - Server-Ready Pipeline"

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 기본: 원본 → 복원 → 분석
  python skin_analysis_cli.py -i input.jpg -o output_dir

  # 복원 생략 (원본만 분석)
  python skin_analysis_cli.py -i input.jpg -o output_dir --no-restore

  # LLM AI 소견 작성 (환경 변수 GOOGLE_API_KEY 사용)
  python skin_analysis_cli.py -i input.jpg -o output_dir --llm-report

  # LLM AI 소견 작성 (API 키 직접 지정)
  python skin_analysis_cli.py -i input.jpg -o output_dir --llm-report --llm-api-key YOUR_API_KEY

  # 서버 환경: 고객 정보 포함
  python skin_analysis_cli.py -i input.jpg -o output_dir --customer-id CUST001 --gender female --age 30 --race asian --region KR

  # 비동기 모드 (서버 환경용)
  python skin_analysis_cli.py -i input.jpg -o output_dir --async
        """
    )
    
    parser.add_argument(
        "-i", "--input",
        type=Path,
        required=True,
        help="입력 이미지 경로"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path(config.get("paths", {}).get("output_dir", "results")),
        help="출력 디렉토리 경로 (기본: results)"
    )
    
    parser.add_argument(
        "--no-restore",
        action="store_true",
        help="복원 생략 (원본 이미지만 분석)"
    )
    
    parser.add_argument(
        "--include-base64",
        action="store_true",
        default=cli_defaults.get("include_base64", False),
        help="base64 인코딩 포함 (JSON 크기 증가, 기본 생략)"
    )
    
    parser.add_argument(
        "--base-url",
        type=str,
        default=SERVER_URL,
        help="이미지 URL 기본 경로 (예: https://server.com/images/)"
    )
    
    parser.add_argument(
        "--score-safety-net",
        action=argparse.BooleanOptionalAction,
        default=cli_defaults.get("score_safety_net", True),
        help="점수 안전장치 (기본 켬, 끄려면 --no-score-safety-net)"
    )
    
    parser.add_argument(
        "--analyzer-score-tune",
        action=argparse.BooleanOptionalAction,
        default=cli_defaults.get("analyzer_score_tune", True),
        help=(
            "켜면 복원(RF++/CF) 후 분석 점수 경향에 맞춰 CodeFormer "
            "fidelity·후처리(모공/톤/주름/트러블)를 가산. 기본 켬, 끄려면 --no-analyzer-score-tune"
        ),
    )
    
    parser.add_argument(
        "--llm-report",
        action="store_true",
        default=cli_defaults.get("llm_report", True),
        help="LLM (Gemini) AI 소견 작성 (기본 끔)"
    )

    parser.add_argument(
        "--llm-scores",
        action=argparse.BooleanOptionalAction,
        default=cli_defaults.get("llm_scores", False),
        help="LLM에 내부 측정 점수 제공 (기본 끔, 켜려면 --llm-scores)"
    )

    parser.add_argument(
        "--llm-api-key",
        type=str,
        default=None,
        help="LLM (Gemini) API 키 (지정하지 않으면 환경 변수 GOOGLE_API_KEY 사용)"
    )
    
    parser.add_argument(
        "--input-json",
        type=str,
        default=None,
        help="설문 JSON 파일 경로 (고객정보, 설문내용 포함)"
    )
    
    parser.add_argument(
        "--customer-id",
        type=str,
        default=None,
        help="고객 ID"
    )
    
    parser.add_argument(
        "--gender",
        type=str,
        default=None,
        help="성별 (예: male, female, other)"
    )
    
    parser.add_argument(
        "--age",
        type=int,
        default=None,
        help="연령"
    )
    
    parser.add_argument(
        "--race",
        type=str,
        default=None,
        help="인종 (예: asian, caucasian, african, hispanic)"
    )
    
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="지역 (예: KR, US, JP)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="디버그 모드"
    )
    
    parser.add_argument(
        "--output-json",
        type=Path,
        help="결과 JSON 출력 파일 경로 (지정하지 않으면 stdout)"
    )
    
    parser.add_argument(
        "--async",
        action="store_true",
        dest="async_mode",
        help="비동기 모드 실행 (서버 환경용)"
    )
    
    parser.add_argument(
        "--use-multi-view",
        action=argparse.BooleanOptionalAction,
        default=cli_defaults.get("use_multi_view_analysis", True),
        help="다중 뷰 분석 사용 (기본 켬, 끄려면 --no-use-multi-view)"
    )
    
    args = parser.parse_args()
    
    # 비동기 모드인 경우 asyncio.run으로 실행
    if args.async_mode:
        asyncio.run(main_async(args))
        return
    
    # 입력 파일 확인
    if not args.input.exists():
        log.error("입력 파일을 찾을 수 없습니다: %s", args.input)
        error_json = _create_error_json(
            FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {args.input}"),
            input_image=args.input,
            output_dir=args.output,
            debug=args.debug,
            customer_id=getattr(args, 'customer_id', None),
            pipeline_mode="cli",
        )
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_json, "w", encoding="utf-8") as f:
                f.write(json_output)
        else:
            print(json_output)
        
        sys.exit(1)
    
    try:
        result = run_analysis_pipeline(
            input_image=args.input,
            output_dir=args.output,
            do_restore=not args.no_restore,
            debug=args.debug,
            include_base64=args.include_base64,
            base_url=args.base_url,
            score_safety_net=args.score_safety_net,
            llm_report=args.llm_report,
            llm_api_key=args.llm_api_key,
            customer_id=args.customer_id,
            gender=args.gender,
            age=args.age,
            race=args.race,
            region=args.region,
            use_multi_view_analysis=args.use_multi_view,
        )
        
        # 결과 출력
        json_output = json.dumps(result, indent=2, ensure_ascii=False)
        
        # 기본 JSON 저장 경로 (results 폴더)
        # 입력 이미지의 파일명을 사용하여 고객별 결과 누적
        if args.output_json:
            json_path = args.output_json
        else:
            input_filename = Path(args.input).stem  # 확장자 제거
            json_path = args.output / f"{input_filename}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        log.info("결과 JSON 저장: %s", json_path)
        
        # DB에 분석 결과 저장 (로컬 SQLite + Supabase 자동 동기화)
        try:
            from src.db.skin_analysis_db import SkinAnalysisDB
            db = SkinAnalysisDB(db_path=str(args.output / "skin_analysis.db"))
            db.save_analysis(
                original_path=args.input,
                restored_path=result.get("restored_image", ""),
                json_result=result,
                customer_id=args.customer_id,
            )
        except Exception as e:
            log.warning("DB 저장 실패: %s", e)
        
        # --output-json 옵션이 없으면 터미널에도 출력
        if not args.output_json:
            print(json_output)
        
        log.info("파이프라인 완료")
        
    except Exception as e:
        log.error("파이프라인 실행 중 오류: %s", e, exc_info=args.debug)
        
        # 오류 JSON 생성 및 출력
        error_json = _create_error_json(
            e,
            input_image=args.input,
            output_dir=args.output,
            debug=args.debug,
            customer_id=getattr(args, 'customer_id', None),
            pipeline_mode="cli",
        )
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_json, "w", encoding="utf-8") as f:
                f.write(json_output)
            log.info("오류 JSON 저장: %s", args.output_json)
        else:
            print(json_output)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
