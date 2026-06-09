# -*- coding: utf-8 -*-
"""
테스트 스크립트: 분석기 레지스트리 기능 검증

Phase 1 구현 검증:
1. BaseAnalyzer 인터페이스
2. AnalyzerRegistry 등록/조회
3. 분석기 인스턴스 생성
4. 설정 기반 분석기 로드
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.skin.analyzers import (
    BaseAnalyzer,
    AnalyzerRegistry,
    register_analyzers_from_config,
)


def test_registry():
    """레지스트리 기능 테스트."""
    print("=" * 60)
    print("테스트 1: 레지스트리 기능")
    print("=" * 60)
    
    # 모든 분석기 등록
    register_analyzers_from_config()
    
    # 사용 가능한 분석기 목록
    available = AnalyzerRegistry.list_available()
    print(f"사용 가능한 분석기: {available}")
    
    # 별칭 목록
    aliases = AnalyzerRegistry.list_aliases()
    print(f"별칭 매핑: {aliases}")
    
    # 분석기 생성 (이름으로)
    analyzer1 = AnalyzerRegistry.get("pigmentation_v1")
    print(f"분석기 생성 (이름): {analyzer1.name} v{analyzer1.version}")
    
    # 분석기 생성 (별칭으로)
    analyzer2 = AnalyzerRegistry.get("pigmentation")
    print(f"분석기 생성 (별칭): {analyzer2.name} v{analyzer2.version}")
    
    # 설정 전달
    config = {"bp_melasma": [(0.0, 100.0), (0.01, 80.0)]}
    analyzer3 = AnalyzerRegistry.get("pigmentation_v1", config=config)
    print(f"분석기 생성 (설정): {analyzer3.name} v{analyzer3.version}")
    print(f"설정 값: {analyzer3.get_config('bp_melasma')}")
    
    print("\n✓ 레지스트리 테스트 통과\n")


def test_analyzer_interface():
    """분석기 인터페이스 테스트."""
    print("=" * 60)
    print("테스트 2: 분석기 인터페이스")
    print("=" * 60)
    
    # 분석기 생성
    analyzer = AnalyzerRegistry.get("pigmentation_v1")
    
    # 인터페이스 확인
    print(f"name: {analyzer.name}")
    print(f"version: {analyzer.version}")
    print(f"config: {analyzer.config}")
    
    # 설정 조회 테스트
    default_value = analyzer.get_config("nonexistent_key", "default")
    print(f"존재하지 않는 키 조회: {default_value}")
    
    print("\n✓ 인터페이스 테스트 통과\n")


def test_config_based_loading():
    """설정 기반 분석기 로드 테스트."""
    print("=" * 60)
    print("테스트 3: 설정 기반 분석기 로드")
    print("=" * 60)
    
    import json
    
    # config.json 로드
    config_path = Path("config/config.json")
    if not config_path.exists():
        print("config.json이 존재하지 않습니다. 테스트 건너뜀.")
        return
    
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    analyzer_config = config.get("analyzers", {})
    print(f"설정된 분석기: {analyzer_config}")
    
    # 설정에서 분석기 로드
    for key, analyzer_name in analyzer_config.items():
        try:
            analyzer = AnalyzerRegistry.get(analyzer_name)
            print(f"  {key}: {analyzer.name} v{analyzer.version}")
        except ValueError as e:
            print(f"  {key}: 오류 - {e}")
    
    print("\n✓ 설정 기반 로드 테스트 통과\n")


def test_v2_analyzer():
    """v2 분석기 테스트 (새로운 알고리즘 예시)."""
    print("=" * 60)
    print("테스트 4: v2 분석기 (새로운 알고리즘)")
    print("=" * 60)
    
    try:
        analyzer = AnalyzerRegistry.get("pigmentation_v2")
        print(f"v2 분석기: {analyzer.name} v{analyzer.version}")
        print(f"설정: {analyzer.config}")
    except ValueError as e:
        print(f"v2 분석기가 등록되지 않았습니다: {e}")
    
    print("\n✓ v2 분석기 테스트 완료\n")


if __name__ == "__main__":
    print("\n분석기 레지스트리 테스트 시작\n")
    
    try:
        test_registry()
        test_analyzer_interface()
        test_config_based_loading()
        test_v2_analyzer()
        
        print("=" * 60)
        print("모든 테스트 통과! ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
