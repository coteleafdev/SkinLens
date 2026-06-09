"""
test_llm_config.py — LLM 설정 관리 단위 테스트

src/llm/llm_config.py 테스트
"""
import pytest
from unittest.mock import patch

from src.llm.llm_config import (
    get_default_model,
    get_default_provider,
    get_default_timeout_sec,
    get_default_max_retries
)


class TestLLMConfig:
    """LLM 설정 테스트"""
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_model(self, mock_load_config):
        """기본 모델 가져오기 테스트"""
        mock_load_config.return_value = {
            "llm": {
                "default_model": "models/gemini-2.5-flash"
            }
        }
        
        model = get_default_model()
        assert model == "models/gemini-2.5-flash"
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_model_default(self, mock_load_config):
        """기본 모델 기본값 테스트"""
        mock_load_config.return_value = {}
        
        model = get_default_model()
        assert model == "models/gemini-2.5-pro"
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_provider(self, mock_load_config):
        """기본 provider 가져오기 테스트"""
        mock_load_config.return_value = {
            "llm": {
                "provider": "openai"
            }
        }
        
        provider = get_default_provider()
        assert provider == "openai"
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_provider_default(self, mock_load_config):
        """기본 provider 기본값 테스트"""
        mock_load_config.return_value = {}
        
        provider = get_default_provider()
        assert provider == "gemini"
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_timeout_sec(self, mock_load_config):
        """기본 타임아웃 가져오기 테스트"""
        mock_load_config.return_value = {
            "timeouts": {
                "llm_timeout_sec": 600
            }
        }
        
        timeout = get_default_timeout_sec()
        assert timeout == 600
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_timeout_sec_default(self, mock_load_config):
        """기본 타임아웃 기본값 테스트"""
        mock_load_config.return_value = {}
        
        timeout = get_default_timeout_sec()
        assert timeout == 300
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_max_retries(self, mock_load_config):
        """기본 최대 재시도 횟수 가져오기 테스트"""
        mock_load_config.return_value = {
            "llm": {
                "max_retries": 5
            }
        }
        
        retries = get_default_max_retries()
        assert retries == 5
    
    @patch('src.llm.llm_config._load_config')
    def test_get_default_max_retries_default(self, mock_load_config):
        """기본 최대 재시도 횟수 기본값 테스트"""
        mock_load_config.return_value = {}
        
        retries = get_default_max_retries()
        assert retries == 3
