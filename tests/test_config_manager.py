"""
ConfigManager 단위 테스트 - 설정 로드, 캐싱, 리로드
"""
import json
import threading
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestConfigManager:
    """ConfigManager 테스트"""

    def test_singleton_pattern(self):
        """싱글톤 패턴 확인"""
        from src.config.config_manager import ConfigManager
        
        instance1 = ConfigManager.get_instance()
        instance2 = ConfigManager.get_instance()
        assert instance1 is instance2

    def test_load_config_success(self):
        """config.json 로드 성공 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        cfg = config.get_config()
        
        # config.json이 존재하면 딕셔너리 반환
        assert isinstance(cfg, dict)

    def test_load_config_file_not_found(self):
        """config.json 파일 없음 테스트"""
        from src.config.config_manager import ConfigManager
        
        # 임시 ConfigManager 인스턴스 생성 (캐시 우회)
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            
            # 직접 인스턴스 생성 및 속성 설정
            config = ConfigManager.__new__(ConfigManager)
            config._initialized = True
            config._config_path = config_path
            config._config_cache = {}
            config._config_mtime = None
            config._cache_lock = threading.Lock()
            
            cfg = config._load_config()
            assert cfg == {}

    def test_load_config_invalid_json(self):
        """잘못된 JSON 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text("{invalid json}")
            
            # 직접 인스턴스 생성 및 속성 설정
            config = ConfigManager.__new__(ConfigManager)
            config._initialized = True
            config._config_path = config_path
            config._config_cache = {}
            config._config_mtime = None
            config._cache_lock = threading.Lock()
            
            cfg = config._load_config()
            assert cfg == {}

    def test_load_config_version_check(self):
        """config.json 버전 검증 테스트"""
        from src.config.config_manager import ConfigManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"config_version": "1.0"}))
            
            # 직접 인스턴스 생성 및 속성 설정
            config = ConfigManager.__new__(ConfigManager)
            config._initialized = True
            config._config_path = config_path
            config._config_cache = {}
            config._config_mtime = None
            config._cache_lock = threading.Lock()
            
            cfg = config._load_config()
            # 버전 미달 시 빈 딕셔너리 반환
            assert cfg == {}

    def test_get_measurement_weights(self):
        """측정항목 가중치 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        weights = config.get_measurement_weights()
        
        assert isinstance(weights, dict)

    def test_get_display_names(self):
        """디스플레이 이름 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        names = config.get_display_names()
        
        assert isinstance(names, dict)

    def test_get_categories(self):
        """카테고리 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        categories = config.get_categories()
        
        assert isinstance(categories, list)

    def test_get_actual_ranges(self):
        """실측 범위 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        ranges = config.get_actual_ranges()
        
        assert isinstance(ranges, dict)

    def test_get_display_range(self):
        """디스플레이 범위 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        display_range = config.get_display_range()
        
        assert isinstance(display_range, tuple)
        assert len(display_range) == 2

    def test_get_score_safety_net_config(self):
        """안전장치 설정 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        safety_net = config.get_score_safety_net_config()
        
        assert isinstance(safety_net, dict)
        assert "enabled" in safety_net

    def test_get_restoration_config(self):
        """복원 설정 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        restoration = config.get_restoration_config()
        
        assert isinstance(restoration, dict)

    def test_get_product_recommendation_config(self):
        """화장품 추천 설정 로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        product = config.get_product_recommendation_config()
        
        assert isinstance(product, dict)
        assert "enabled" in product

    def test_reload(self):
        """설정 리로드 테스트"""
        from src.config.config_manager import ConfigManager
        
        config = ConfigManager.get_instance()
        
        # 리로드 전 캐시 확인
        assert config._config_cache is not None
        
        # 리로드 실행
        config.reload()
        
        # 캐시 초기화 확인
        assert config._config_cache == {}

    def test_caching_mechanism(self):
        """캐싱 메커니즘 테스트"""
        from src.config.config_manager import ConfigManager
        
        # 신규 인스턴스 생성 (캐시 우회)
        config = ConfigManager.__new__(ConfigManager)
        config._initialized = True
        config._config_path = Path(__file__).parent.parent / "config" / "config.json"
        config._config_cache = {}
        config._config_mtime = None
        config._cache_lock = threading.Lock()
        config._required_config_version = "3.6"
        
        # 첫 번째 로드
        cfg1 = config._load_config()
        mtime1 = config._config_mtime
        
        # 두 번째 로드 (캐시 사용)
        cfg2 = config._load_config()
        mtime2 = config._config_mtime
        
        # 캐시된 결과는 동일해야 함 (값 비교)
        assert cfg1 == cfg2
        assert mtime1 == mtime2
