"""src/skin/analyzer — 도메인별 분석 함수 패키지.

각 모듈은 순수 함수 집합으로 구성되어 있으며
_SkinAnalyzerV2 가 오케스트레이터로서 이들을 호출한다.

[REFACTOR PHASE 1] 전략 패턴 도입:
  - base.py: 분석기 추상 기반 클래스
  - registry.py: 분석기 등록 및 팩토리
  - strategies/: 분석기 구체 구현 클래스

모듈:
  pigmentation    : 기미·주근깨·PIH
  redness         : 홍조·홍반 (PIE)
  pore            : 모공 크기·개수·늘어짐
  wrinkle_texture : 주름·텍스처·복원품질
  tone_elasticity : 톤·탄력·피부타입·트러블
"""
from __future__ import annotations

# 기존 순수 함수 (하위 호환 유지)
from src.skin.analyzers.pigmentation import analyze_pigmentation, make_pigment_mask
from src.skin.analyzers.redness import analyze_redness
from src.skin.analyzers.pore import analyze_pores
from src.skin.analyzers.wrinkle_texture import (
    analyze_wrinkles, analyze_texture, analyze_restoration_quality,
)
from src.skin.analyzers.tone_elasticity import (
    analyze_tone, analyze_elasticity, analyze_dark_circle,
    analyze_sebum, analyze_acne_marks, analyze_perceived_age,
)

# 전략 패턴 관련 (새로운 인터페이스)
from src.skin.analyzers.base import BaseAnalyzer
from src.skin.analyzers.registry import AnalyzerRegistry
from src.skin.analyzers.strategies.register_analyzers import (
    register_all_analyzers,
    register_analyzers_from_config,
)

__all__ = [
    # 기존 순수 함수
    "analyze_pigmentation", "make_pigment_mask",
    "analyze_redness",
    "analyze_pores",
    "analyze_wrinkles", "analyze_texture", "analyze_restoration_quality",
    "analyze_tone", "analyze_elasticity", "analyze_dark_circle",
    "analyze_sebum", "analyze_acne_marks", "analyze_perceived_age",
    # 전략 패턴
    "BaseAnalyzer",
    "AnalyzerRegistry",
    "register_all_analyzers",
    "register_analyzers_from_config",
]
