"""
test_utils.py — 공통 유틸리티 함수 단위 테스트

src/utils/utils.py 테스트
"""
import pytest
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

from src.utils.utils import (
    setup_logging,
    apply_formatter_to_all_loggers,
    get_logging_level,
    set_logging_level,
    _load_logging_level
)


class TestSetupLogging:
    """setup_logging 테스트"""
    
    def setup_method(self):
        """각 테스트 전 로거 초기화"""
        # 기존 핸들러 제거
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        # 로거 레벨 초기화
        root_logger.setLevel(logging.NOTSET)
    
    def teardown_method(self):
        """각 테스트 후 로거 정리"""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.NOTSET)
    
    def test_setup_logging_default(self):
        """기본 로깅 설정 테스트"""
        setup_logging(force=True)
        
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        # config.json에서 로드된 레벨 또는 기본값
        assert root_logger.level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
    
    def test_setup_logging_with_level(self):
        """로그 레벨 지정 테스트"""
        setup_logging(level="DEBUG", force=True)
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
    
    def test_setup_logging_force(self):
        """강제 재설정 테스트"""
        setup_logging(level="INFO", force=True)
        setup_logging(level="DEBUG", force=True)
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
    
    def test_setup_logging_no_force(self):
        """비강제 재설정 테스트"""
        setup_logging(level="INFO", force=True)
        setup_logging(level="DEBUG", force=False)
        
        # force=False이면 이미 설정되어 있으면 스킵
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
    
    def test_setup_logging_disable_db_logging(self):
        """DB 로깅 비활성화 테스트"""
        setup_logging(enable_db_logging=False, force=True)
        
        # DB 로깅 핸들러가 추가되지 않음
        root_logger = logging.getLogger()
        # 최소한 기본 핸들러는 있어야 함
        assert len(root_logger.handlers) >= 1
    
    @patch('src.utils.utils._load_logging_level')
    def test_setup_logging_from_config(self, mock_load_level):
        """설정 파일에서 로드 테스트"""
        mock_load_level.return_value = "DEBUG"
        
        setup_logging(force=True)
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
    
    def test_setup_logging_invalid_level(self):
        """잘못된 로그 레벨 테스트"""
        setup_logging(level="INVALID", force=True)
        
        # 잘못된 레벨은 기본값 INFO로 대체
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO


class TestApplyFormatterToAllLoggers:
    """apply_formatter_to_all_loggers 테스트"""
    
    def setup_method(self):
        """각 테스트 전 로거 초기화"""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
    
    def teardown_method(self):
        """각 테스트 후 로거 정리"""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
    
    def test_apply_formatter_to_root_logger(self):
        """루트 로거 포맷터 적용 테스트"""
        setup_logging(level="INFO")
        
        apply_formatter_to_all_loggers()
        
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        assert root_logger.handlers[0].formatter is not None
    
    def test_apply_formatter_to_custom_logger(self):
        """사용자 정의 로거 포맷터 적용 테스트"""
        setup_logging(level="INFO")
        
        # 사용자 정의 로거 생성
        custom_logger = logging.getLogger("custom")
        custom_logger.addHandler(logging.StreamHandler())
        
        apply_formatter_to_all_loggers()
        
        assert custom_logger.handlers[0].formatter is not None


class TestLoadLoggingLevel:
    """_load_logging_level 테스트"""
    
    def test_load_logging_level_default(self):
        """기본 로그 레벨 로드 테스트"""
        level = _load_logging_level()
        
        # config.json이 있으면 그 값, 없으면 INFO
        assert level in ["DEBUG", "INFO", "WARNING", "ERROR"]
    
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_load_logging_level_file_not_found(self, mock_open):
        """파일 없음 테스트"""
        level = _load_logging_level()
        
        assert level == "INFO"
    
    @patch('builtins.open', side_effect=Exception("JSON error"))
    def test_load_logging_level_json_error(self, mock_open):
        """JSON 파싱 에러 테스트"""
        level = _load_logging_level()
        
        assert level == "INFO"
    
    @patch('builtins.open', create=True)
    @patch('json.load')
    def test_load_logging_level_from_config(self, mock_json_load, mock_open):
        """설정 파일에서 로드 테스트"""
        mock_json_load.return_value = {
            "logging": {
                "level": "DEBUG"
            }
        }
        
        level = _load_logging_level()
        
        assert level == "DEBUG"
    
    @patch('builtins.open', create=True)
    @patch('json.load')
    def test_load_logging_level_no_logging_key(self, mock_json_load, mock_open):
        """logging 키 없음 테스트"""
        mock_json_load.return_value = {}
        
        level = _load_logging_level()
        
        assert level == "INFO"


class TestGetLoggingLevel:
    """get_logging_level 테스트"""
    
    def setup_method(self):
        """각 테스트 전 로거 초기화"""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
    
    def teardown_method(self):
        """각 테스트 후 로거 정리"""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
    
    def test_get_logging_level_default(self):
        """기본 로그 레벨 반환 테스트"""
        level = get_logging_level()
        
        assert level in ["DEBUG", "INFO", "WARNING", "ERROR"]
    
    def test_get_logging_level_after_setup(self):
        """설정 후 로그 레벨 반환 테스트"""
        setup_logging(level="DEBUG")
        
        level = get_logging_level()
        assert level == "DEBUG"


class TestSetLoggingLevel:
    """set_logging_level 테스트"""
    
    def setup_method(self):
        """각 테스트 전 로거 초기화"""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.NOTSET)
    
    def teardown_method(self):
        """각 테스트 후 로거 정리"""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.NOTSET)
    
    def test_set_logging_level(self):
        """로그 레벨 설정 테스트"""
        set_logging_level("DEBUG", force=True)
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
    
    def test_set_logging_level_no_force(self):
        """비강제 로그 레벨 설정 테스트"""
        setup_logging(level="INFO", force=True)
        set_logging_level("DEBUG", force=False)
        
        # force=False이면 재설정 안 됨
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
    
    @patch('src.utils.utils._persist_logging_level')
    def test_set_logging_level_persist(self, mock_persist):
        """로그 레벨 저장 테스트"""
        set_logging_level("DEBUG", force=True, persist=True)
        
        mock_persist.assert_called_once_with("DEBUG")
    
    @patch('src.utils.utils._persist_logging_level')
    def test_set_logging_level_no_persist(self, mock_persist):
        """로그 레벨 저장 안 함 테스트"""
        set_logging_level("DEBUG", force=True, persist=False)
        
        mock_persist.assert_not_called()


class TestApplyScoreSafetyNet:
    """apply_score_safety_net 테스트"""
    
    def test_apply_score_safety_net_skip(self, tmp_path):
        """모듈 의존으로 인한 테스트 건너뜀"""
        # 이 함수는 analyze_utils 모듈이 필요하므로 통합 테스트에서 다룸
        pytest.skip("apply_score_safety_net은 analyze_utils 모듈이 필요하며 통합 테스트에서 다룹니다")
