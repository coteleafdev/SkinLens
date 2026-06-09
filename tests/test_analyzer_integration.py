# -*- coding: utf-8 -*-
"""
테스트 스크립트: 분석기 통합 테스트

Phase 3 구현 검증:
1. _SkinAnalyzerV2 분석기 주입 테스트
2. 설정 기반 분석기 로드 테스트
3. 하위 호환성 테스트 (순수 함수 사용)
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def test_analyzer_injection():
    """분석기 주입 테스트."""
    print("=" * 60)
    print("테스트 1: 분석기 주입")
    print("=" * 60)
    
    from src.skin.analyzers import AnalyzerRegistry, register_analyzers_from_config
    from src.scoring.skin_scoring import _SkinAnalyzerCore
    
    # 분석기 등록
    register_analyzers_from_config()
    
    # 사용자 정의 분석기 주입
    custom_analyzers = {
        "pigmentation": AnalyzerRegistry.get("pigmentation_v1"),
        "redness": AnalyzerRegistry.get("redness_v1"),
        "pore": AnalyzerRegistry.get("pore_v1"),
        "wrinkle": AnalyzerRegistry.get("wrinkle_v1"),
        "tone_elasticity": AnalyzerRegistry.get("tone_elasticity_v1"),
        "acne": AnalyzerRegistry.get("acne_v1"),
    }
    
    analyzer = _SkinAnalyzerCore(analyzers=custom_analyzers)
    
    # 분석기 확인
    print(f"주입된 분석기 수: {len(analyzer.analyzers)}")
    for key, analyzer_inst in analyzer.analyzers.items():
        print(f"  {key}: {analyzer_inst.name} v{analyzer_inst.version}")
    
    print("\n✓ 분석기 주입 테스트 통과\n")


def test_config_based_loading():
    """설정 기반 분석기 로드 테스트."""
    print("=" * 60)
    print("테스트 2: 설정 기반 분석기 로드")
    print("=" * 60)
    
    import json
    from src.scoring.skin_scoring import _SkinAnalyzerCore
    
    # config.json 로드
    config_path = Path("config/config.json")
    if not config_path.exists():
        print("config.json이 존재하지 않습니다. 테스트 건너뜀.")
        return
    
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    # 설정에서 분석기 로드
    analyzers = _SkinAnalyzerCore.load_analyzers_from_config(config)
    
    # 분석기 생성
    analyzer = _SkinAnalyzerCore(analyzers=analyzers)
    
    print(f"로드된 분석기 수: {len(analyzer.analyzers)}")
    for key, analyzer_inst in analyzer.analyzers.items():
        print(f"  {key}: {analyzer_inst.name} v{analyzer_inst.version}")
    
    print("\n✓ 설정 기반 로드 테스트 통과\n")


def test_backward_compatibility():
    """하위 호환성 테스트 (분석기 없으면 순수 함수 사용)."""
    print("=" * 60)
    print("테스트 3: 하위 호환성")
    print("=" * 60)
    
    from src.scoring.skin_scoring import _SkinAnalyzerCore
    
    # 분석기 없이 생성 (기본 순수 함수 사용)
    analyzer = _SkinAnalyzerCore(analyzers={})
    
    print(f"분석기 수: {len(analyzer.analyzers)}")
    print("분석기가 없으므로 순수 함수를 사용합니다.")
    
    # 기본 분석기 로드 시도
    default_analyzers = analyzer._get_default_analyzers()
    print(f"기본 분석기 로드 결과: {len(default_analyzers)}개")
    
    print("\n✓ 하위 호환성 테스트 통과\n")


def test_algorithm_switching():
    """알고리즘 교체 테스트 (v1 → v2)."""
    print("=" * 60)
    print("테스트 4: 알고리즘 교체")
    print("=" * 60)
    
    from src.skin.analyzers import AnalyzerRegistry, register_analyzers_from_config
    from src.scoring.skin_scoring import _SkinAnalyzerCore
    
    # 분석기 등록
    register_analyzers_from_config()
    
    # v1 사용
    analyzers_v1 = {
        "pigmentation": AnalyzerRegistry.get("pigmentation_v1"),
        "redness": AnalyzerRegistry.get("redness_v1"),
        "pore": AnalyzerRegistry.get("pore_v1"),
        "wrinkle": AnalyzerRegistry.get("wrinkle_v1"),
        "tone_elasticity": AnalyzerRegistry.get("tone_elasticity_v1"),
        "acne": AnalyzerRegistry.get("acne_v1"),
    }
    analyzer_v1 = _SkinAnalyzerCore(analyzers=analyzers_v1)
    print(f"v1 분석기: pigmentation = {analyzer_v1.analyzers['pigmentation'].name}, acne = {analyzer_v1.analyzers['acne'].name}")
    
    # v2 사용 (pigmentation만 교체)
    analyzers_v2 = {
        "pigmentation": AnalyzerRegistry.get("pigmentation_v2"),  # v2로 교체
        "redness": AnalyzerRegistry.get("redness_v1"),
        "pore": AnalyzerRegistry.get("pore_v1"),
        "wrinkle": AnalyzerRegistry.get("wrinkle_v1"),
        "tone_elasticity": AnalyzerRegistry.get("tone_elasticity_v1"),
        "acne": AnalyzerRegistry.get("acne_v1"),
    }
    analyzer_v2 = _SkinAnalyzerCore(analyzers=analyzers_v2)
    print(f"v2 분석기: pigmentation = {analyzer_v2.analyzers['pigmentation'].name}, acne = {analyzer_v2.analyzers['acne'].name}")
    
    print("\n✓ 알고리즘 교체 테스트 통과\n")


if __name__ == "__main__":
    print("\n분석기 통합 테스트 시작\n")
    
    try:
        test_analyzer_injection()
        test_config_based_loading()
        test_backward_compatibility()
        test_algorithm_switching()
        
        print("=" * 60)
        print("모든 테스트 통과! ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
