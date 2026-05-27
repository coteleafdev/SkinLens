# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.register_analyzers — 분석기 자동 등록

앱 시작 시 이 모듈을 import하여 모든 분석기를 레지스트리에 등록합니다.

[REFACTOR 2026-05-24] config.json에서 분석기 설정을 동적으로 로드.

사용 예:
    from src.skin.analyzers.strategies.register_analyzers import register_all_analyzers
    register_all_analyzers()
"""
from __future__ import annotations

import logging
import importlib

from src.skin.analyzers.registry import AnalyzerRegistry
from src.skin.analyzers.strategies.pigmentation_analyzer import (
    PigmentationAnalyzerV1,
    PigmentationAnalyzerV2,
)
from src.skin.analyzers.strategies.redness_analyzer import RednessAnalyzerV1
from src.skin.analyzers.strategies.pore_analyzer import PoreAnalyzerV1
from src.skin.analyzers.strategies.wrinkle_analyzer import WrinkleAnalyzerV1
from src.skin.analyzers.strategies.tone_elasticity_analyzer import ToneElasticityAnalyzerV1
from src.skin.analyzers.strategies.acne_analyzer import AcneAnalyzerV1

log = logging.getLogger(__name__)

# 분석기 등록 상태 추적 (중복 등록 방지)
_analyzers_registered = False


def register_analyzers_from_config() -> None:
    """config.json에서 분석기 설정을 로드하여 동적으로 등록.

    [REFACTOR 2026-05-24] config.json의 analyzers 섹션에서 로드.
    [OPTIMIZE 2026-05-24] 이미 등록된 경우 중복 등록 방지.
    [FIX 2026-05-27] 전체 config 로드로 수정 - _load_prescription_config는 prescription 섹션만 반환
    [FIX 2026-05-27] prescription.analyzers 섹션 사용 - 최상위 analyzers는 문자열 매핑
    """
    global _analyzers_registered
    
    # 이미 등록된 경우 건너뜀
    if _analyzers_registered:
        log.debug("분석기가 이미 등록되어 있어 등록을 건너뜁니다.")
        return
    
    try:
        from src.scoring.config._config import _load_scoring_config

        config = _load_scoring_config()
        # prescription 섹션의 analyzers 사용 (최상위 analyzers는 문자열 매핑)
        prescription_config = config.get("prescription", {}) if config else {}
        analyzers_config = prescription_config.get("analyzers", {})

        for analyzer_name, analyzer_config in analyzers_config.items():
            if analyzer_name.startswith("_"):
                continue  # _note 등 주석 필드 건너뜀

            if not analyzer_config.get("enabled", True):
                log.info(f"분석기 비활성화: {analyzer_name}")
                continue

            class_name = analyzer_config.get("class")
            module_path = analyzer_config.get("module")
            aliases = analyzer_config.get("aliases", [])

            if not class_name or not module_path:
                log.warning(f"분석기 설정 불완전: {analyzer_name}")
                continue

            try:
                # 동적 import
                module = importlib.import_module(module_path)
                analyzer_class = getattr(module, class_name)

                # 레지스트리에 등록
                AnalyzerRegistry.register(analyzer_name, aliases=aliases)(analyzer_class)
                log.info(f"분석기 등록 완료: {analyzer_name} ({class_name})")
            except Exception as e:
                log.warning(f"분석기 등록 실패: {analyzer_name} - {e}")
        
        # 등록 완료 표시
        _analyzers_registered = True
        log.info("분석기 등록 완료 (config.json): %s", AnalyzerRegistry.list_available())

    except Exception as e:
        log.warning(f"config.json에서 분석기 설정 로드 실패, 하드코딩된 등록 사용: {e}")
        register_all_analyzers_fallback()


def register_all_analyzers_fallback() -> None:
    """하드코딩된 분석기 등록 (폴백).
    
    [OPTIMIZE 2026-05-24] 이미 등록된 경우 중복 등록 방지.
    """
    global _analyzers_registered
    
    # 이미 등록된 경우 건너뜀
    if _analyzers_registered:
        log.debug("분석기가 이미 등록되어 있어 폴백 등록을 건너뜁니다.")
        return
    
    # 색소 분석기 등록
    AnalyzerRegistry.register("pigmentation_v1", aliases=["pigmentation", "pig_v1"])(PigmentationAnalyzerV1)
    AnalyzerRegistry.register("pigmentation_v2", aliases=["pig_v2"])(PigmentationAnalyzerV2)

    # 홍조 분석기 등록
    AnalyzerRegistry.register("redness_v1", aliases=["redness", "red_v1"])(RednessAnalyzerV1)

    # 모공 분석기 등록
    AnalyzerRegistry.register("pore_v1", aliases=["pore", "pore_v1"])(PoreAnalyzerV1)

    # 주름 분석기 등록
    AnalyzerRegistry.register("wrinkle_v1", aliases=["wrinkle", "wrinkle_v1"])(WrinkleAnalyzerV1)

    # 톤·탄력 분석기 등록
    AnalyzerRegistry.register("tone_elasticity_v1", aliases=["tone_elasticity", "tone_v1"])(ToneElasticityAnalyzerV1)

    # 트러블 분석기 등록 (독립)
    AnalyzerRegistry.register("acne_v1", aliases=["acne", "acne_v1"])(AcneAnalyzerV1)

    # 등록 완료 표시
    _analyzers_registered = True
    log.info("하드코딩된 분석기 등록 완료: %s", AnalyzerRegistry.list_available())


def register_all_analyzers() -> None:
    """모든 분석기를 레지스트리에 등록.

    [REFACTOR 2026-05-24] config.json에서 동적 로드 우선, 실패 시 폴백 사용.
    """
    register_analyzers_from_config()


# 모듈 import 시 자동 등록 (선택적)
# register_all_analyzers()
