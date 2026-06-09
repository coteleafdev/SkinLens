# -*- coding: utf-8 -*-
"""
테스트 스크립트: 복원 백엔드 및 LLM 레지스트리 테스트

Strategy Pattern 구현 검증:
1. 복원 백엔드 레지스트리 테스트
2. LLM 레지스트리 테스트
3. 설정 기반 로드 테스트
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def test_restorer_registry():
    """복원 백엔드 레지스트리 테스트."""
    print("=" * 60)
    print("테스트 1: 복원 백엔드 레지스트리")
    print("=" * 60)
    
    from src.restoration import RestorerRegistry, register_all_restorers
    
    # 복원 백엔드 등록
    register_all_restorers()
    
    # 사용 가능한 복원 백엔드 확인
    available = RestorerRegistry.list_available()
    print(f"사용 가능한 복원 백엔드: {available}")
    
    # 복원 백엔드 조회
    cf_class = RestorerRegistry.get("codeformer_v1")
    rf_class = RestorerRegistry.get("restoreformer_v1")
    
    print(f"CodeFormer: {cf_class.__name__}")
    print(f"RestoreFormer: {rf_class.__name__}")
    
    # 별칭 테스트
    cf_class_alias = RestorerRegistry.get("codeformer")
    assert cf_class == cf_class_alias, "별칭 조회 실패"
    print("별칭 조회 테스트 통과")
    
    print("\n✓ 복원 백엔드 레지스트리 테스트 통과\n")


def test_llm_registry():
    """LLM 레지스트리 테스트."""
    print("=" * 60)
    print("테스트 2: LLM 레지스트리")
    print("=" * 60)
    
    from src.llm import LLMRegistry, register_all_llms
    
    # LLM 등록
    register_all_llms()
    
    # 사용 가능한 LLM 확인
    available = LLMRegistry.list_available()
    print(f"사용 가능한 LLM: {available}")
    
    # LLM 조회
    gemini_class = LLMRegistry.get("gemini_v1")
    print(f"Gemini: {gemini_class.__name__}")
    
    # 별칭 테스트
    gemini_class_alias = LLMRegistry.get("gemini")
    assert gemini_class == gemini_class_alias, "별칭 조회 실패"
    print("별칭 조회 테스트 통과")
    
    print("\n✓ LLM 레지스트리 테스트 통과\n")


def test_config_based_loading():
    """설정 기반 로드 테스트."""
    print("=" * 60)
    print("테스트 3: 설정 기반 로드")
    print("=" * 60)
    
    import json
    from src.restoration import RestorerRegistry, register_all_restorers
    from src.llm import LLMRegistry, register_all_llms
    
    # 등록
    register_all_restorers()
    register_all_llms()
    
    # config.json 로드
    config_path = Path("config/config.json")
    if not config_path.exists():
        print("config.json이 존재하지 않습니다. 테스트 건너뜀.")
        return
    
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    # 복원 백엔드 로드
    restorer_name = config["restorers"]["default"]
    restorer_config = config["restorers"][restorer_name]
    restorer_class = RestorerRegistry.get(restorer_name)
    print(f"복원 백엔드: {restorer_name}")
    print(f"설정: {restorer_config}")
    
    # LLM 로드
    llm_name = config["llms"]["default"]
    llm_config = config["llms"][llm_name]
    llm_class = LLMRegistry.get(llm_name)
    print(f"LLM: {llm_name}")
    print(f"설정: {llm_config}")
    
    print("\n✓ 설정 기반 로드 테스트 통과\n")


if __name__ == "__main__":
    print("\n복원 백엔드 및 LLM 레지스트리 테스트 시작\n")
    
    try:
        test_restorer_registry()
        test_llm_registry()
        test_config_based_loading()
        
        print("=" * 60)
        print("모든 테스트 통과! ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
