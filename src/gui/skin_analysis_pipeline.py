# -*- coding: utf-8 -*-
"""
skin_analysis_pipeline.py — AI Skin Analysis Pipeline 진입점 (v1 → v3 리팩토링).

변경 요약
─────────
• PySide6 import 를 GUI 경로에서만 수행 (CLI 환경에서 ImportError 방지)
• 파이프라인 로직 → pipeline_core.py (모델 캐싱, Enum 모드 분기)
• GUI 코드 → skin_analysis_gui.py
• --skip-restore 이중 플래그 제거, --no-restore 단일화
• [REFACTOR 2026-05-16] 모공 완화 기능 제거
• [REFACTOR 2026-05-16] SD 기능 제거
• 복원 백엔드 선택: --restorer {restoreformer,codeformer} (기본 restoreformer)
• RestoreFormer++: --restoreformer-root, CodeFormer: --codeformer-root/--cf-fidelity/--cf-upscale
• GUI 「측정항목 비교」: skin_scoring 레이어B 로 원본 vs 보정 이미지 측정항목 바 차트 (`skin_measurement_chart_dialog.py`)
• 복원(입력→RF++/CF) 시 skin_scoring 레이어B 측정항목이 입력 대비 올라가기 쉽도록 기본 튜닝(`--analyzer-score-tune`, 기본 켬)
• 기미·주근깨·검버섯(색소 3항) 부담이 큰 입력은 홍조·모공늘어짐 점수 보호를 위해 튜닝 완화 분기
• 파이프라인 최종 산출 확정 시 `analyzer_compare_gui` 동일 로직으로 원본 vs 결과 팝업(`--restore-score-popup`, 기본 켬)

실행
────
  python skin_analysis_pipeline.py              # GUI (PySide6)
  python skin_analysis_pipeline.py --cli ...   # CLI
  python skin_analysis_pipeline.py --cli --help
"""
from __future__ import annotations

# 모듈 경로 추가: 프로젝트 루트를 Python 경로에 추가
import sys
import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Pillow 디버그 로그 숨기기
logging.getLogger("PIL").setLevel(logging.WARNING)

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Windows 콘솔 한글 깨짐 방지: UTF-8 인코딩 설정
if sys.platform == "win32":
    import io
    # 이미 TextIOWrapper로 감싸져 있는지 확인 후 재설정 방지
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except (ValueError, AttributeError):
            pass  # 이미 닫혀있거나 설정 불가능한 경우 무시
    if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding != 'utf-8':
        try:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except (ValueError, AttributeError):
            pass  # 이미 닫혀있거나 설정 불가능한 경우 무시

import argparse
import json
import traceback
from datetime import datetime
from typing import Optional

from src.pipeline.pipeline_core import (
    Restorer,
    PipelineSettings,
    final_pipeline_artifact_path,
    format_duration,
    resolve_init_image,
    format_torch_cuda_status,
    run_enhancement_pipeline,
)


from src.utils.config import load_config as _load_config
from src.skin.core.config_parser import get_measurement_count


# config.json에서 설정 로드 (lazy getter)
def _get_config() -> dict:
    return _load_config()

def get_paths_config() -> dict:
    """config.json에서 paths 설정을 가져옵니다."""
    return _get_config().get("paths", {})

def get_device_config() -> dict:
    """config.json에서 device 설정을 가져옵니다."""
    return _get_config().get("device", {})


def _get_restoration_defaults():
    """config.json에서 복원 파라미터 기본값을 가져옵니다."""
    try:
        config = _get_config()
        resto = config.get("restoration", {})
        return (
            resto.get("codeformer_fidelity", 1.0),
            resto.get("codeformer_upscale", 2),
            resto.get("codeformer_additional", True),
            resto.get("codeformer_bg_upsampler", "none"),
        )
    except Exception:
        # import 실패 시 기본값 반환
        return (1.0, 2, True, "none")


def _input_has_stressed_pigmentation(input_path: Path) -> Optional[bool]:
    """기미·주근깨·검버섯 등 색소 부담이 커 보일 때(색소 3항 평균·최저 기준).

    이 경우 강한 bilateral·tone_ab·낮은 CodeFormer fidelity 가
    `redness_score`(a채널 기반)·`pore_sagging_score`(하안 윤곽 이진화)를
    복원 후에 악화시키는 사례가 있어 완화 튜닝 분기로 넘긴다.

    Returns:
        True  — 색소 부담 큼 (완화 튜닝 분기)
        False — 색소 부담 없음 (강한 튜닝 적용)
        None  — 분석 실패 (import 오류·예외) → 호출부에서 튜닝 전체 건너뜀
    """
    try:
        from src.scoring.skin_scoring import SkinAnalyzer as SkinAnalyzer
    except ImportError:
        return None   # [FIX v1.0 ⑨] 분석 불가 → 강한 튜닝 적용 방지
    try:
        res = SkinAnalyzer().analyze_all(
            str(input_path.resolve()),
            debug=False,
            clahe_preprocessed=False,
        )
    except Exception:
        return None   # [FIX v1.0 ⑨] 분석 예외 → 강한 튜닝 적용 방지
    m = res.get("measurements_report") or res.get("measurements") or {}

    def _f(key: str, default: float = 70.0) -> float:
        try:
            return float(m.get(key, default))
        except (TypeError, ValueError):
            return default

    mel, freckle, pap = _f("melasma_score"), _f("freckle_score"), _f("post_acne_pigment_score")
    avg3 = (mel + freckle + pap) / 3.0
    if avg3 < 58.0:
        return True
    if min(mel, freckle, pap) < 48.0:
        return True
    return False


def _apply_restore_analyzer_score_tuning(
    cfg: PipelineSettings,
    *,
    enabled: bool,
    do_restore: bool,
    input_image: Path | None,
) -> None:
    """입력→복원(및 그 직후 산출)이 `skin_scoring` 레이어B 18개 점수에서 입력보다 오르기 쉽게 경향 조정.

    색소(기미·주근깨·검버섯) 부담이 큰 입력은 홍조·모공늘어짐 점수 보호를 위해
    낮은 fidelity 를 완화한 분기를 쓴다.
    """
    log.debug(
        f"튜닝 함수 진입: enabled={enabled}, do_restore={do_restore}"
    )
    if not enabled or not do_restore:
        log.debug(
            f"튜닝 건너뜀: enabled={enabled}, do_restore={do_restore}"
        )
        return

    pigment_heavy: Optional[bool] = False
    if input_image is not None and input_image.is_file():
        pigment_heavy = _input_has_stressed_pigmentation(Path(input_image))

    log.debug(f"색소 부담 감지 결과: pigment_heavy={pigment_heavy}")

    # [FIX v1.0 ⑨] 분석 자체가 실패한 경우(None) — 강한 튜닝 적용하지 않음
    if pigment_heavy is None:
        log.warning(
            "색소 부담 판정 분석 실패 — 자동 튜닝 건너뜀 "
            "(끄기: --no-analyzer-score-tune)"
        )
        return

    # 색소 부담 여부에 따라 튜닝 분기
    if pigment_heavy:
        log.debug("색소 부담 입력 - 복원만 적용")
        log.info("색소 부담 입력 감지 — 복원만 적용")
        return
    else:
        log.debug("일반 입력 - 기본 복원 적용")
    measurement_count = get_measurement_count()
    log.info(
        f"analyzer {measurement_count}항목 경향: 복원 산출에 복원만 적용 "
        + (
            "| CodeFormer "
            if cfg.restorer is Restorer.CODEFORMER
            else "| RestoreFormer++ "
        )
        + "(끄기: --no-analyzer-score-tune)"
    )


# ---------------------------------------------------------------------------
# 점수 안전장치 유틸
# ---------------------------------------------------------------------------

from src.utils.utils import apply_score_safety_net


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def _create_error_json(
    error: Exception,
    input_image: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    debug: bool = False,
    customer_id: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    race: Optional[str] = None,
    region: Optional[str] = None,
) -> dict:
    """오류 정보를 JSON 형식으로 생성."""
    error_json = {
        "error": True,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "timestamp": datetime.now().isoformat(),
        "input_image": str(input_image) if input_image else None,
        "output_dir": str(output_dir) if output_dir else None,
        "customer_info": {
            "customer_id": customer_id,
            "gender": gender,
            "age": age,
            "race": race,
            "region": region
        }
    }
    
    if debug:
        error_json["error_traceback"] = traceback.format_exc()
    
    return error_json


def _configure_stdio_encoding() -> None:
    """Windows cp949 콘솔에서 유니코드 출력 시 UnicodeEncodeError 방지."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception as e:
            log.warning(f"Stream reconfigure failed: {e}", exc_info=True)


def _print_self_help() -> None:
    print(
        "skin_analysis_pipeline.py\n"
        "  (인자 없음)     PySide6 GUI 실행\n"
        "  --cli [인자...] 파이프라인 CLI\n"
        "  --analyze IMG  skin_scoring 단일 이미지 분석 (레이어B 측정항목)\n"
        "  --compare ORIG REF   측정항목 비교 다이얼로그만 실행\n"
        "  --cli --help    파이프라인 옵션 전체 보기\n",
        end="",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_body(args) -> int:
    """CLI 파이프라인 실행 로직 (동기/비동기 공통)"""
    global llm_time
    _configure_stdio_encoding()
    
    # 전체 처리 시간 측정 시작
    import time
    total_start_time = time.time()
    llm_time = 0.0
    
    # ConfigManager 초기화 - 분석 전에 설정 로드 보장
    try:
        from src.config.config_manager import ConfigManager
        config_mgr = ConfigManager.get_instance()
        log.info("ConfigManager 초기화 완료")
    except Exception as e:
        log.warning("ConfigManager 초기화 실패: %s. 레거시 설정 로드 사용.", e)
    
    # config.json에서 복원 파라미터 기본값 로드
    cf_bg_upsampler_default = _get_restoration_defaults()[3]
    
    # 상호 배타 검증
    if args.restore_only and args.text2img:
        from argparse import ArgumentParser
        p = ArgumentParser()
        p.error("--restore-only 와 --text2img 은 함께 쓸 수 없습니다.")
    if args.restore_only and args.sd_after_rf:
        from argparse import ArgumentParser
        p = ArgumentParser()
        p.error("--restore-only 와 --sd-after-rf 는 함께 쓸 수 없습니다.")

    # cfg 구성
    cfg = PipelineSettings()
    cfg.restorer = Restorer(args.restorer)
    
    # config.json 기본값 적용 (None이면 자동 탐색)
    if args.restoreformer_root is not None:
        cfg.restoreformer_repo = args.restoreformer_root
    if args.restoreformer_device is not None:
        cfg.restoreformer_device = args.restoreformer_device
    if args.codeformer_root is not None:
        cfg.codeformer_repo = args.codeformer_root
    cfg.codeformer_fidelity = max(0.0, min(1.0, float(args.cf_fidelity)))
    cfg.codeformer_upscale  = max(1, int(args.cf_upscale))
    cfg.codeformer_additional = args.cf_additional
    cfg.codeformer_bg_upsampler = cf_bg_upsampler_default

    init_resolved = resolve_init_image(args.input, force_text2img=args.text2img)

    _apply_restore_analyzer_score_tuning(
        cfg,
        enabled=args.analyzer_score_tune,
        do_restore=args.restore,
        input_image=init_resolved,
    )

    log.info(format_torch_cuda_status())
    log.info(f"[진행] 복원 백엔드: {cfg.restorer.value}")
    if init_resolved is not None:
        log.info(f"[진행] CLI 입력 이미지 확정: {init_resolved.name} → {init_resolved.resolve()}")
    log.info(f"[진행] 복원 백엔드: {cfg.restorer.value}")
    if init_resolved is not None:
        log.info(f"[진행] 산출 폴더: {args.out_dir.resolve()}")

    if init_resolved is not None and Path(init_resolved).is_file():
        try:
            r = run_enhancement_pipeline(
                cfg,
                args.out_dir,
                input_image=init_resolved,
                do_restore=args.restore,
            )

            log.info(f"restored    : {r.restored}")
            parts = []
            if r.wall_restore_sec is not None:
                parts.append(f"CodeFormer {format_duration(r.wall_restore_sec)}")
            if r.wall_total_sec is not None:
                parts.append(f"합계 {format_duration(r.wall_total_sec)}")
            if parts:
                log.info(f"[시간] 요약: {' | '.join(parts)}")

            if init_resolved is not None and Path(init_resolved).is_file():
                out_dir = Path(args.out_dir)
                final_p = final_pipeline_artifact_path(r, out_dir)
                if final_p is None or not final_p.is_file():
                    log.warning(
                        f"[경고] 점수 분석 생략: 최종 산출 PNG 없음 "
                        f"(stem={r.output_stem!r}, out_dir={out_dir.resolve()})"
                    )
                else:
                    # 이미지별 폴더로 파일 이동
                    input_stem = r.output_stem
                    image_folder = out_dir / input_stem
                    image_folder.mkdir(parents=True, exist_ok=True)
                    
                    # 스테이징된 파일 이동
                    staged_file = out_dir / f"00_input_{input_stem}.png"
                    if staged_file.exists():
                        shutil.move(str(staged_file), str(image_folder / staged_file.name))
                    
                    # 복원 파일 이동
                    if final_p.exists():
                        shutil.move(str(final_p), str(image_folder / final_p.name))
                        final_p = image_folder / final_p.name  # 경로 업데이트

                    try:
                        from src.gui.analyzer_compare_gui import show_restore_score_popup, analyze_compare_triple
                        from src.scoring.skin_scoring import SkinAnalyzer

                        log.info(
                            f"[진행] 점수 분석: 원본={Path(init_resolved).resolve()} → 산출={final_p.resolve()}"
                        )

                        # 점수 분석 및 안전장치 적용
                        # [구조변경 #3] 중복 제거: GUI 인라인 compare_triple+safety_net 시퀀스를
                        # AnalysisService.run_compare 로 위임(동일 함수·순서·폴백 → 점수 불변).
                        from src.pipeline.analysis_service import AnalysisService
                        o, i1, i2 = AnalysisService().run_compare(
                            Path(init_resolved),
                            final_p,
                            score_safety_net=args.score_safety_net,
                        )

                        # [구조변경 #3 Phase 2] GUI 표시측 후처리 모듈 사용
                        from src.gui.score_postprocess import (
                            filter_measurements,
                            apply_score_offset_v2,
                            load_scoring_config
                        )
                        
                        # offset 설정 로드
                        offset_config, weights, max_score_limit = load_scoring_config()

                        # 원본/복원 점수 필터링
                        original_score_filtered = {
                            "overall": float(o.get("overall_score_report", o.get("overall_score", 0))),
                            "measurements": filter_measurements(o.get("measurements_report") or o.get("measurements", {}))
                        }
                        restored_score_filtered = {
                            "overall": float(i1.get("overall_score_report", i1.get("overall_score", 0))),
                            "measurements": filter_measurements(i1.get("measurements_report") or i1.get("measurements", {}))
                        }

                        # offset 적용 (GUI 표시측 후처리)
                        original_score_adjusted = apply_score_offset_v2(original_score_filtered, offset_config, weights, max_score_limit)
                        restored_score_adjusted = apply_score_offset_v2(restored_score_filtered, offset_config, weights, max_score_limit)
                        
                        # 인지 나이 추출
                        original_perceived_age = o.get("perceived_age", 0)
                        restored_perceived_age = i1.get("perceived_age", 0)

                        # LLM API 호출 (원본이미지와 기준이미지만 제공)
                        llm_orig_result = None
                        llm_ref_result = None
                        llm_time = 0
                        # 체크박스 상태와 관계없이 항상 LLM 호출 수행
                        # 체크박스 OFF: provide_scores=False로 LLM이 직접 점수 산출
                        # 체크박스 ON: provide_scores=True로 자체 측정 점수 제공
                        try:
                            from src.llm.llm_skin_report import LlmSkinReporter, list_available_models, _load_llm_api_key
                            import time

                            log.info("[진행] LLM API 호출 중... (원본+복원 분석)")
                            llm_start = time.time()

                            # 사용 가능한 모델 목록 출력
                            try:
                                api_key = _load_llm_api_key()
                                available_models = list_available_models(api_key)
                                if available_models:
                                    log.info(f"[LLM] 사용 가능한 모델 {len(available_models)}개")
                                    log.info(f"[LLM] 사용 가능한 모델 목록 (상위 5개): {', '.join(available_models[:5])}...")
                            except Exception as e:
                                log.warning(f"[LLM] 사용 가능한 모델 목록 조회 실패: {e}")

                            reporter = LlmSkinReporter()
                            log.info(f"[LLM] 모델: {reporter.model_name}")
                            
                            # 진행 콜백
                            def progress_callback(msg: str) -> None:
                                log.info(f"[LLM] {msg}")

                            # 내부 측정 점수 제공 여부 결정
                            # 처방전 계산을 위해 측정 점수는 항상 전달
                            # provide_scores는 LLM에게 점수를 제공할지 여부만 결정
                            # [FIX] offset 보정 전의 원본 점수를 LLM에 전달하여 점수 차이 경고 방지
                            # LLM 모듈은 평면적인 dict를 기대하므로 measurements만 전달
                            orig_measurements = filter_measurements(o.get("measurements_report") or o.get("measurements", {}))
                            ref_measurements = filter_measurements(i1.get("measurements_report") or i1.get("measurements", {}))
                            orig_overall_score = float(o.get("overall_score_report", o.get("overall_score", 0)))
                            ref_overall_score = float(i1.get("overall_score_report", i1.get("overall_score", 0)))
                            orig_perceived_age = o.get("perceived_age", 0)
                            ref_perceived_age = i1.get("perceived_age", 0)
                            provide_scores = args.llm_scores  # --llm-scores true면 점수 제공
                            
                            # ProductRepository 생성 (LLM Reporter에 전달)
                            product_repo = None
                            concerns = []
                            skin_type = None
                            try:
                                from src.db.product_repository import ProductRepository
                                product_repo = ProductRepository(db_path=str(args.out_dir / "skin_analysis.db"))
                                log.info("[정보] ProductRepository 초기화 완료")
                                
                                # 설문에서 고민사항 추출 (input_json이 있는 경우)
                                if hasattr(args, 'input_json') and args.input_json:
                                    survey = args.input_json.get("survey", {})
                                    concerns = survey.get("skin_concerns", [])
                                    skin_types = survey.get("skin_types", [])
                                    skin_type = skin_types[0] if skin_types else None
                                    log.info(f"[정보] 설문 응답: concerns={concerns}, skin_type={skin_type}")
                                else:
                                    # 설문이 없는 경우 분석 결과에서 피부타입 추출
                                    # skin_type_score 기반 피부타입 추정
                                    skin_type_score = original_score_filtered.get("skin_type_score", 0)
                                    if skin_type_score < 40:
                                        skin_type = "oily"  # 지성
                                    elif skin_type_score < 60:
                                        skin_type = "combination"  # 복합성
                                    elif skin_type_score < 80:
                                        skin_type = "dry"  # 건성
                                    else:
                                        skin_type = "sensitive"  # 민감성
                                    log.info(f"[정보] 분석 결과 기반 피부타입 추정: skin_type_score={skin_type_score}, skin_type={skin_type}")
                            except Exception as e:
                                log.warning(f"[경고] ProductRepository 초기화 실패: {e}")
                            
                            # 듀얼 이미지 분석 (product_repository 전달)
                            log.info(f"[LLM 호출] 메인 프로세스에서 LLM API 호출 시작 (provide_scores={provide_scores}, 체크박스={'ON' if args.llm_scores else 'OFF'})")
                            llm_orig_result, llm_ref_result = reporter.generate_report_from_dual_images(
                                str(init_resolved),  # orig_image_path
                                str(final_p),  # ref_image_path
                                orig_measurements,  # orig_measurements_report
                                orig_overall_score,  # orig_overall_score (offset 보정 전)
                                orig_perceived_age,  # orig_perceived_age
                                ref_measurements,  # ref_measurements_report
                                ref_overall_score,  # ref_overall_score (offset 보정 전)
                                ref_perceived_age,  # ref_perceived_age
                                provide_scores=provide_scores,  # --llm-scores true면 True
                                product_info=None,  # LLM Reporter가 내부적으로 생성
                                product_repository=product_repo,  # ProductRepository 전달
                                concerns=concerns,  # 설문 응답 전달
                                skin_type=skin_type,  # 설문 응답 전달
                            )

                            llm_time = time.time() - llm_start
                            log.info(f"[완료] LLM API 호출 완료 ({llm_time:.2f}초)")
                        except Exception as e:
                            log.warning(f"[경고] LLM API 호출 실패: {e}")
                            import traceback
                            traceback.print_exc()
                            llm_orig_result = None
                            llm_ref_result = None

                        # 메타데이터 수집
                        # 복원 백엔드 실제 이름 확인 (별칭 지원)
                        restorer_name = args.restorer
                        # 별칭 매핑
                        restorer_alias_map = {
                            "codeformer": "codeformer_v1",
                            "cf": "codeformer_v1",
                            "restoreformer": "restoreformer_v1",
                            "rf": "restoreformer_v1"
                        }
                        # config 로드
                        try:
                            config = _get_config()
                        except Exception:
                            config = {}
                        
                        if restorer_name in restorer_alias_map:
                            restorer_name = restorer_alias_map[restorer_name]
                        elif restorer_name not in config.get("restorers", {}):
                            # 등록된 이름도 아닌 경우, 기본값 사용
                            restorer_name = config.get("restorers", {}).get("default", "codeformer_v1")
                        
                        # LLM 이름 확인
                        llm_name = config.get("llms", {}).get("default", "gemini_v1")
                        llm_config = config.get("llms", {}).get(llm_name, {})
                        
                        metadata = {
                            "analyzers": config.get("analyzers", {}),
                            "restorer": {
                                "name": restorer_name,
                                "config": config.get("restorers", {}).get(restorer_name, {})
                            },
                            "llm": {
                                "name": llm_name,
                                "model": getattr(reporter, 'model_name', llm_config.get("model", "unknown")) if llm_orig_result else llm_config.get("model", "unknown"),
                                "config": llm_config
                            }
                        }
                        
                        # 전체 처리 시간 계산
                        total_elapsed = time.time() - total_start_time
                        
                        result_json = {
                            "input_image": str(Path(init_resolved).resolve()),
                            "restored_image": str(final_p.resolve()),
                            "output_dir": str(args.out_dir),
                            "original_image_url": f"file://{str(Path(init_resolved).resolve())}",
                            "restored_image_url": f"file://{str(final_p.resolve())}",
                            "metadata": metadata,
                            "customer_info": {
                                "customer_id": getattr(args, 'customer_id', None),
                                "gender": getattr(args, 'gender', None),
                                "age": getattr(args, 'age', None),
                                "race": getattr(args, 'race', None),
                                "region": getattr(args, 'region', None)
                            },
                            "execution_time": {
                                "total_sec": round(total_elapsed, 2),
                                "llm_sec": round(llm_time, 2) if llm_time > 0 else None
                            },
                            # CLI와 동일한 구조: analysis_result
                            "analysis_result": {
                                "overall_score": int(round(float(i1.get("overall_score_report", i1.get("overall_score", 0))))),
                                "overall_score_report": int(round(float(i1.get("overall_score_report", i1.get("overall_score", 0))))),
                                "perceived_age": int(round(i1.get("perceived_age", 0))),
                                "measurements": filter_measurements(i1.get("measurements_report") or i.get("measurements", {})),
                                "measurements_report": filter_measurements(i1.get("measurements_report") or i.get("measurements", {})),
                                "overall_score_adjusted": restored_score_adjusted["overall"],
                                "measurements_adjusted": restored_score_adjusted["measurements"]
                            }
                        }

                        # LLM 결과가 있으면 추가 (CLI와 동일한 구조: llm_report inside analysis_result)
                        if llm_orig_result and llm_ref_result:
                            # 원본 보고서
                            orig_dict = {
                                "overall_opinion": getattr(llm_orig_result, 'overall_opinion', ''),
                                "overall_score": int(round(getattr(llm_orig_result, 'overall_score', 0))),
                                "perceived_age": int(round(getattr(llm_orig_result, 'perceived_age', 0))),
                                "recommendation": getattr(llm_orig_result, 'recommendation', ''),
                                "product_recommendations": getattr(llm_orig_result, 'product_recommendations', {}),
                                "matched_products": getattr(llm_orig_result, 'matched_products', []),
                                "metric_opinions": [
                                    {
                                        "key": m.key,
                                        "display_name": m.display_name,
                                        "category": m.category,
                                        "score": int(round(m.score)),
                                        "opinion": m.opinion,
                                        "reason": m.reason,
                                        "grade": m.grade
                                    }
                                    for m in llm_orig_result.metric_opinions
                                ]
                            }

                            # 복원 보고서
                            ref_dict = {
                                "overall_opinion": getattr(llm_ref_result, 'overall_opinion', ''),
                                "overall_score": int(round(getattr(llm_ref_result, 'overall_score', 0))),
                                "perceived_age": int(round(getattr(llm_ref_result, 'perceived_age', 0))),
                                "recommendation": getattr(llm_ref_result, 'recommendation', ''),
                                "product_recommendations": getattr(llm_ref_result, 'product_recommendations', {}),
                                "matched_products": getattr(llm_ref_result, 'matched_products', []),
                                "metric_opinions": [
                                    {
                                        "key": m.key,
                                        "display_name": m.display_name,
                                        "category": m.category,
                                        "score": int(round(m.score)),
                                        "opinion": m.opinion,
                                        "reason": m.reason,
                                        "grade": m.grade
                                    }
                                    for m in llm_ref_result.metric_opinions
                                ]
                            }

                            # CLI와 동일한 구조: llm_report inside analysis_result
                            result_json["analysis_result"]["llm_report"] = {
                                "original": orig_dict,
                                "reference": ref_dict
                            }
                            result_json["analysis_result"]["llm_model"] = getattr(llm_orig_result, 'model', llm_config.get("model", "unknown"))
                            result_json["analysis_result"]["llm_stats"] = getattr(llm_orig_result, 'llm_stats', {})
                            log.info(f"[JSON 저장] matched_products: {len(orig_dict.get('matched_products', []))}")
                        else:
                            result_json["analysis_result"]["llm_report"] = {
                                "note": "LLM API 호출 실패 또는 미제공 모드"
                            }
                        
                        # 처방전 기록 (제조사에서 맞춤형 화장품 제조를 위해)
                        try:
                            from src.prescription.prescription_calculator import create_prescription
                            
                            full_prescription = create_prescription(
                                skin_assessment_scores=result_json["analysis_result"].get("measurements_report", {}),
                                pcr_result=None,  # PCR 데이터가 없으면 None
                                age_group_statistics=None,
                                age=getattr(args, 'age', 30) or 30,
                                gender=getattr(args, 'gender', 'female') or 'female',
                                skin_type=getattr(args, 'skin_type', None),
                                concerns=getattr(args, 'concerns', None),
                            )
                            
                            # [REFACTOR 2026-06-08] create_prescription가 믹스 이름을
                            # 직접 포함하므로 별도 enrich/config 조회가 불필요.
                            result_json["analysis_result"]["prescription"] = full_prescription
                            log.info("[JSON 저장] 처방전 기록 완료 (믹스 코드 이름 포함)")
                        except Exception as e:
                            log.warning(f"[경고] 처방전 기록 실패: {e}")
                            result_json["analysis_result"]["prescription"] = None
                        
                        json_output = json.dumps(result_json, indent=2, ensure_ascii=False)
                        print("[JSON 출력]", flush=True)
                        print(json_output, flush=True)
                        
                        # JSON 파일 저장 (CLI와 동일하게 results 폴더)
                        # 입력 이미지의 파일명을 사용하여 고객별 결과 누적
                        # 이미지별 폴더(image_folder)가 이미 생성되었으므로 이를 사용
                        if args.save_json:
                            # JSON 저장 (results/이미지명/00_input_이미지명.json)
                            json_path = image_folder / f"00_input_{input_stem}.json"
                            with open(json_path, "w", encoding="utf-8") as f:
                                f.write(json_output)
                            log.info(f"[완료] JSON 저장 완료: {json_path}")
                        
                        # DB에 분석 결과 저장 (JSON 저장 시에만)
                        if args.save_json:
                            try:
                                from src.db.skin_analysis_db import SkinAnalysisDB
                                db = SkinAnalysisDB(db_path=str(args.out_dir / "skin_analysis.db"))
                                db.save_analysis(
                                    original_path=str(image_folder / f"00_input_{input_stem}.png"),
                                    restored_path=str(final_p),
                                    json_result=result_json
                                )
                            except Exception as e:
                                log.warning(f"[경고] DB 저장 실패: {e}")
                                import traceback
                                traceback.print_exc()

                        # 점수 팝업 표시 생략, 측정항목 비교는 GUI 모드에서만 실행
                        # CLI에서는 --no-restore-score-popup 옵션으로 건너뜀
                        if args.restore_score_popup:  # --restore-score-popup일 때만 실행
                            log.info("[진행] 측정항목 비교 다이얼로그 표시")
                            try:
                                from PySide6.QtCore import QProcess
                            except ImportError:
                                log.warning("[경고] PySide6가 설치되어 있지 않아 측정항목 비교 다이얼로그를 표시할 수 없습니다.")
                            else:
                                proc = QProcess()
                                # 이미지별 폴더로 이동된 경로 사용
                                original_moved_path = image_folder / f"00_input_{input_stem}.png"
                                proc_args = [
                                    sys.executable,
                                    "-B",  # .pyc 파일 생성 비활성화 (캐시 문제 방지)
                                    __file__,
                                    "--compare",
                                    str(original_moved_path),
                                    str(final_p),
                                ]
                                # JSON 파일 경로 전달 (서브프로세스에서 LLM 재호출 방지)
                                proc_args.append("--llm-json")
                                proc_args.append(str(json_path))
                                # --llm-scores도 전달 (서브프로세스에서 LLM 점수 표시용)
                                if provide_scores:
                                    proc_args.append("--llm-scores")
                                log.debug(f"[DEBUG] 실행 인자: {proc_args}")
                                log.debug(f"[DEBUG] JSON 파일 경로: {json_path}")
                                proc.setArguments(proc_args)
                                proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
                                proc.start()
                                log.info(f"[진행] 측정항목 비교 서브프로세스 시작: {' '.join(proc_args)}")
                    except Exception as e:
                        log.warning(f"[경고] 점수 분석 실패: {e}")
        except Exception as e:
            log.error(f"[오류] 파이프라인 실행 중 오류: {e}")

            # 오류 JSON 생성 및 출력
            error_json = _create_error_json(
                e,
                input_image=init_resolved,
                output_dir=args.out_dir,
                debug=args.debug,
                customer_id=getattr(args, 'customer_id', None),
                gender=getattr(args, 'gender', None),
                age=getattr(args, 'age', None),
                race=getattr(args, 'race', None),
                region=getattr(args, 'region', None),
            )
            json_output = json.dumps(error_json, indent=2, ensure_ascii=False)

            if args.output_json:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                with open(args.output_json, "w", encoding="utf-8") as f:
                    f.write(json_output)
                log.error(f"[오류] 오류 JSON 저장: {args.output_json}")
            else:
                print(json_output, flush=True)
            
            # save_json 옵션이 있으면 out-dir에도 저장
            if args.save_json:
                staged_files = list(args.out_dir.glob("00_input_*.png"))
                if staged_files:
                    # 현재 처리 중인 파일과 일치하는 스테이징된 파일 찾기
                    input_stem = Path(init_resolved).stem if init_resolved else None
                    matching_file = None
                    if input_stem:
                        for f in staged_files:
                            if f.stem == f"00_input_{input_stem}":
                                matching_file = f
                                break
                    if matching_file:
                        input_filename = matching_file.stem
                    else:
                        # 일치하는 파일이 없으면 가장 최근 파일 사용
                        input_filename = max(staged_files, key=lambda f: f.stat().st_mtime).stem
                else:
                    input_filename = Path(init_resolved).stem if init_resolved else "error"
                
                # 이미지별 폴더 생성 (results/이미지명/)
                image_folder = args.out_dir / input_filename.replace("00_input_", "")
                image_folder.mkdir(parents=True, exist_ok=True)
                
                # JSON 저장 (results/이미지명/00_input_이미지명.json)
                json_path = image_folder / f"{input_filename}.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    f.write(json_output)
                log.error(f"[오류] 오류 JSON 저장: {json_path}")
            return 1

    # 전체 처리 시간 출력
    total_elapsed = time.time() - total_start_time
    log.info(f"[전체 처리 시간] {format_duration(total_elapsed)}")
    if llm_time > 0:
        log.info(f"[LLM 처리 시간] {format_duration(llm_time)}")

    return 0


def _cli() -> int:
    """CLI 진입점 (동기 모드)"""
    # ConfigManager 초기화 - 분석 전에 설정 로드 보장
    try:
        from src.config.config_manager import ConfigManager
        config_mgr = ConfigManager.get_instance()
        log.info("ConfigManager 초기화 완료")
    except Exception as e:
        log.warning("ConfigManager 초기화 실패: %s. 레거시 설정 로드 사용.", e)
    
    # config.json에서 복원 파라미터 기본값 로드
    cf_fidelity_default = 1.0
    cf_upscale_default = 1
    cf_additional_default = _get_restoration_defaults()[2]
    cf_bg_upsampler_default = _get_restoration_defaults()[3]
    
    p = argparse.ArgumentParser(
        description=(
            "원본 보정: RF++/CodeFormer 복원 (pipeline_core.py 사용)"
        ),
        epilog=(
            "RF++ 만(기본): -i. 원본 복사·RF만: --restore-only."
        ),
    )
    p.add_argument(
        "--input", "-i",
        type=Path, nargs="?", const=Path("images/origin.png"), default=None,
        metavar="PATH",
        help="img2img 초기 이미지. 플래그만 쓰면 images/origin.png.",
    )
    p.add_argument(
        "--restore-only", action="store_true",
        help="복원 전용 — 입력 원본을 복사한 뒤 복원 엔진만 실행",
    )
    p.add_argument(
        "--text2img", action="store_true",
        help="초기 이미지 없이 text2img 만",
    )
    p.add_argument(
        "--sd-after-rf", action="store_true",
        help="RF++ 이후에 추가 복원 실행(기본은 RF++ 결과만 사용)",
    )
    p.add_argument(
        "--sd-strength", type=float, default=0.12, metavar="S",
        help="추가 복원 강도 (0,1]. 기본 0.12",
    )
    p.add_argument(
        "--sd-max-side", type=int, default=768, metavar="PX",
        help="추가 복원 시 긴 변 상한(px). 입력 파일 해상도는 유지하고 산출만 맞춤",
    )
    p.add_argument(
        "--sd-guidance", type=float, default=None, metavar="G",
        help="guidance_scale (미지정 시 5.5)",
    )
    p.add_argument(
        "--sd-steps", type=int, default=None, metavar="N",
        help="추가 복원 추론 스텝 (미지정 시 40)",
    )
    p.add_argument(
        "--sd-negative-prompt", type=str, default=None, metavar="TEXT",
        help="negative prompt",
    )
    p.add_argument(
        "--out-dir", type=Path, default=Path("results"),
        help="산출물 폴더",
    )
    p.add_argument(
        "--prompt", type=str, default=None,
        help="프롬프트(영문 권장). 생략 시 기본 문구",
    )
    p.add_argument("--model-id", type=str, default=None, help="모델 ID")
    p.add_argument(
        "--restore", action=argparse.BooleanOptionalAction, default=True,
        help="CodeFormer 실행 여부 (기본 켜짐). 끄려면 --no-restore",
    )
    p.add_argument(
        "--restorer",
        type=str,
        choices=[r.value for r in Restorer],
        default=Restorer.CODEFORMER.value,
        metavar="{restoreformer,codeformer}",
        help=(
            "복원 백엔드 선택. "
            "restoreformer: RestoreFormerPlusPlus 사용, "
            "codeformer(기본): CodeFormer 사용"
        ),
    )
    paths_config = get_paths_config()
    rf_root_default = paths_config.get("restoreformer_root")
    if rf_root_default:
        rf_root_default = Path(rf_root_default)
    p.add_argument(
        "--restoreformer-root", type=Path, default=rf_root_default,
        metavar="PATH",
        help="RestoreFormer++ 저장소 경로",
    )
    p.add_argument(
        "--restoreformer-device",
        type=str,
        choices=["auto", "cuda", "cpu"],
        default="auto",
        metavar="{auto,cuda,cpu}",
        help="RestoreFormer++ 장치 선택",
    )
    cf_root_default = paths_config.get("codeformer_root")
    if cf_root_default:
        cf_root_default = Path(cf_root_default)
    p.add_argument(
        "--codeformer-root", type=Path, default=cf_root_default,
        metavar="PATH",
        help="CodeFormer 저장소 경로",
    )
    p.add_argument(
        "--cf-fidelity", type=float, default=cf_fidelity_default, metavar="F",
        help=f"CodeFormer fidelity_weight 0(최대보정)~1(원본충실). 기본 {cf_fidelity_default} (config.json)",
    )
    p.add_argument(
        "--cf-additional", action=argparse.BooleanOptionalAction, default=False,
        help="RF++ 복원 후 CodeFormer 추가 복원 수행 (기본 끔)",
    )
    p.add_argument(
        "--cf-upscale", type=int, default=cf_upscale_default, metavar="N",
        help=f"CodeFormer 업스케일 배수. 기본 {cf_upscale_default} (config.json)",
    )
    p.add_argument(
        "--analyzer-score-tune",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "켜면 복원(RF++/CF) 후 분석 점수 경향에 맞춰 CodeFormer "
            "fidelity를 자동 조정하여 점수가 원본 대비 올라가기 쉽게 함. "
            "기본 켜짐. 끄려면 --no-analyzer-score-tune"
        ),
    )
    p.add_argument(
        "--score-safety-net",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "켜면 기준이미지 점수가 원본보다 1점 미만일 때 가장 가중치가 높은 항목 점수를 조정하여 피부건강지수가 1점 오르도록 함. "
            "기본 켜짐. 끄려면 --no-score-safety-net"
        ),
    )
    p.add_argument(
        "--restore-score-popup",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "파이프라인 끝나면 analyzer_compare_gui 와 동일한 ref_stat·측정항목 표를 "
            "팝업으로 표시. 기본 끔. 켜려면 --restore-score-popup"
        ),
    )
    p.add_argument(
        "--llm-scores",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "LLM에 내부 측정 점수를 제공. "
            "기본: 내부 측정 점수 미제공 (켜기: --llm-scores)"
        ),
    )
    p.add_argument(
        "--output-json", type=Path, default=None,
        help="결과 JSON 출력 파일 경로 (지정하지 않으면 stdout)",
    )
    p.add_argument(
        "--save-json", action="store_true", default=True,
        help="결과 JSON을 out-dir에 저장 (기본 True)",
    )
    # 고객 정보 인자
    p.add_argument("--customer-id", type=str, help="고객 ID")
    p.add_argument("--gender", type=str, help="성별")
    p.add_argument("--age", type=int, help="연령")
    p.add_argument("--race", type=str, help="인종")
    p.add_argument("--region", type=str, help="지역")
    p.add_argument(
        "--debug", action="store_true",
        help="디버그 모드 (오류 시 스택 트레이스 포함)",
    )
    p.add_argument(
        "--async", dest="async_mode", action="store_true",
        help="비동기 모드 실행 (서버 환경용)",
    )

    args = p.parse_args()

    # 비동기 모드인 경우 asyncio.run으로 실행
    if args.async_mode:
        import asyncio
        asyncio.run(_cli_async(args))
        return 0

    return _cli_body(args)


async def _cli_async(args) -> int:
    """CLI 비동기 진입점"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    # ThreadPoolExecutor로 동기 함수를 비동기로 실행
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=3) as executor:
        result = await loop.run_in_executor(executor, _cli_body, args)
    return result


def _run_pipeline_cli(forwarded: list[str]) -> int:
    # CLI 모드에서 로깅 설정 (자식 프로세스인지 확인)
    from src.utils.utils import setup_logging
    import os
    if os.environ.get("SKINLENS_CHILD_PROCESS"):
        # GUI에서 호출된 자식 프로세스: 로그 파일에 기록하지 않음
        pass
    else:
        # 독립 실행인 경우: 로그 파일 생성
        setup_logging(mode="cli")
    
    old = sys.argv
    try:
        sys.argv = [old[0]] + forwarded
        try:
            return _cli()
        except SystemExit as exc:
            code = exc.code
            if code is None:
                return 0
            return code if isinstance(code, int) else 1
        except Exception as e:
            # argparse 등에서 발생한 오류도 JSON으로 출력
            error_json = _create_error_json(e, debug=False)
            json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
            print(json_output, flush=True)
            return 1
    finally:
        sys.argv = old


# ---------------------------------------------------------------------------
# GUI 진입점 — PySide6 import 는 여기서만
# ---------------------------------------------------------------------------
def _run_gui() -> int:
    # GUI 경로에서만 import → CLI 환경 PySide6 없어도 정상 동작
    try:
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        log.error("PySide6 가 설치되어 있지 않습니다: %s", e)
        log.error("  pip install PySide6")
        return 1
    try:
        from src.gui.skin_analysis_gui import SkinAnalysisWindow, _center_window_on_screen
    except ImportError as e:
        log.error("GUI 모듈을 불러오지 못했습니다 (PySide6 외 의존성): %s", e)
        log.error("  프로젝트 루트에서 실행하는지, skin_scoring 가 요구하는 모듈이 있는지 확인하세요.")
        return 1

    # Windows에서 종료 직전 일시 정지 시 뜨는 "응답 없음(ghost window)" 표시를 억제.
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.DisableProcessWindowsGhosting()
        except Exception as e:
            log.warning(f"DisableProcessWindowsGhosting failed: {e}", exc_info=True)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    w = SkinAnalysisWindow()
    # [FIX P2] 종료 처리 단순화: 단일 quit 호출로 충분
    w.destroyed.connect(app.quit)
    w.show()
    _center_window_on_screen(w)
    _ret = app.exec()
    exit_code = int(_ret) if isinstance(_ret, int) else 0
    return exit_code


def _run_compare_dialog(orig: Path, ref: Path, llm_scores: bool = False, llm_json_path: Path = None) -> int:
    _configure_stdio_encoding()
    log.debug(f"[DEBUG] _run_compare_dialog 시작: {orig}, {ref}, llm_scores={llm_scores}, llm_json_path={llm_json_path}")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as e:
        error_json = _create_error_json(e)
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        print(json_output, flush=True)
        return 1
    try:
        from src.gui.skin_measurement_chart_dialog import show_skin_measurement_compare_dialog
    except ImportError as e:
        error_json = _create_error_json(e)
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        print(json_output, flush=True)
        return 1
    
    # 이미 실행 중인 QApplication 인스턴스가 있는지 확인
    existing_app = QApplication.instance()
    log.debug(f"[DEBUG] existing_app: {existing_app}")
    if existing_app is None:
        # 측정항목 비교 독립 실행: QApplication 생성 전에 DPI 설정
        try:
            from PySide6.QtCore import Qt
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except Exception as e:
            log.warning(f"SetHighDpiScaleFactorRoundingPolicy failed: {e}", exc_info=True)
        app = QApplication(sys.argv)
        log.debug(f"[DEBUG] QApplication 생성 완료, 다이얼로그 표시 시도")
        # 서브프로세스 환경: 다이얼로그를 모달로 표시하여 이벤트 루프 유지
        dlg = show_skin_measurement_compare_dialog(None, orig, ref, llm_scores=llm_scores, modal=True, llm_json_path=llm_json_path)
        log.debug(f"[DEBUG] show_skin_measurement_compare_dialog 반환: modal=True, dlg={dlg}")
        if dlg:
            log.debug(f"[DEBUG] dlg.exec() 호출 시작")
            result = dlg.exec()
            log.debug(f"[DEBUG] dlg.exec() 종료, result={result}")
            return result
        else:
            log.debug(f"[DEBUG] 다이얼로그 생성 실패, 종료 코드 1 반환")
            return 1
    else:
        # GUI 모드 실행: 기존 QApplication 사용
        log.debug(f"[DEBUG] 기존 QApplication 사용, 다이얼로그 표시 시도")
        show_skin_measurement_compare_dialog(None, orig, ref, llm_scores=not llm_scores)
        log.debug(f"[DEBUG] 다이얼로그 표시 완료")
        return 0


def _run_analyze(image_path: Path) -> int:
    _configure_stdio_encoding()
    if not image_path.is_file():
        error_json = _create_error_json(
            FileNotFoundError(f"이미지 파일이 없습니다: {image_path}"),
            input_image=image_path,
        )
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        print(json_output, flush=True)
        return 2
    try:
        from src.scoring.skin_scoring import SkinAnalyzer as SkinAnalyzer, measurement_report_string as measurement_report_string
    except ImportError as e:
        error_json = _create_error_json(e, input_image=image_path)
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        print(json_output, flush=True)
        return 1
    try:
        analyzer = SkinAnalyzer()
        res = analyzer.analyze_all(str(image_path), debug=False, clahe_preprocessed=False)
        print(measurement_report_string(res), end="")
        return 0
    except Exception as e:
        error_json = _create_error_json(e, input_image=image_path)
        json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
        print(json_output, flush=True)
        return 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    # 캐시 초기화 - config.json 변경 반영
    from src.scoring._breakpoints import _clear_breakpoints_cache
    from src.llm.llm_metadata import clear_metadata_cache
    _clear_breakpoints_cache()
    clear_metadata_cache()

    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        _print_self_help()
        return 0
    if argv and argv[0] == "--analyze":
        if len(argv) < 2:
            error_json = _create_error_json(
                ValueError("--analyze 는 IMG 경로가 필요합니다.")
            )
            json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
            print(json_output, flush=True)
            return 2
        return _run_analyze(Path(argv[1]))
    if argv and argv[0] == "--compare":
        if len(argv) < 3:
            error_json = _create_error_json(
                ValueError("--compare 는 ORIG REF 경로 2개가 필요합니다.")
            )
            json_output = json.dumps(error_json, indent=2, ensure_ascii=False)
            print(json_output, flush=True)
            return 2
        # --llm-json 옵션 파싱 (JSON 파일 경로)
        llm_json_path = None
        if "--llm-json" in argv:
            idx = argv.index("--llm-json")
            if idx + 1 < len(argv):
                llm_json_path = Path(argv[idx + 1])
                log.debug(f"[DEBUG] --llm-json 경로: {llm_json_path}")
        # --llm-scores 옵션 파싱 (기본값: False - 점수 미제공)
        log.debug(f"[DEBUG] argv = {argv}")
        llm_scores = "--llm-scores" in argv  # --llm-scores가 있으면 점수 제공
        log.debug(f"[DEBUG] --llm-scores in argv = {'--llm-scores' in argv}")
        log.debug(f"[DEBUG] llm_scores = {llm_scores} (True=점수 제공, False=점수 미제공)")
        return _run_compare_dialog(Path(argv[1]), Path(argv[2]), llm_scores, llm_json_path)
    if argv and argv[0] == "--cli":
        return _run_pipeline_cli(argv[1:])
    return _run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
