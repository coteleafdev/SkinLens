"""
test_restoration_base.py — 복원 베이스 클래스 단위 테스트

BaseRestorer 추상 클래스 테스트
"""
import pytest
from pathlib import Path
from src.restoration.base import BaseRestorer


class MockRestorer(BaseRestorer):
    """테스트용 Mock 복원 클래스"""
    
    def restore(self, input_path, output_path, **kwargs):
        """복원 수행 (Mock)"""
        return {"output_path": str(output_path)}
    
    def get_name(self):
        """이름 반환"""
        return "MockRestorer"
    
    def get_version(self):
        """버전 반환"""
        return "1.0.0"


class TestBaseRestorer:
    """BaseRestorer 테스트"""
    
    def test_init_default(self):
        """기본 초기화 테스트"""
        restorer = MockRestorer()
        
        assert restorer.config == {}
        assert restorer._model_loaded is False
    
    def test_init_with_config(self):
        """설정 포함 초기화 테스트"""
        config = {"repo": "/path/to/repo", "device": "cuda"}
        restorer = MockRestorer(config=config)
        
        assert restorer.config == config
        assert restorer._model_loaded is False
    
    def test_restore(self, tmp_path):
        """복원 메서드 테스트"""
        input_path = tmp_path / "input.jpg"
        output_path = tmp_path / "output.jpg"
        
        restorer = MockRestorer()
        result = restorer.restore(input_path, output_path)
        
        assert result["output_path"] == str(output_path)
    
    def test_get_name(self):
        """이름 반환 테스트"""
        restorer = MockRestorer()
        
        assert restorer.get_name() == "MockRestorer"
    
    def test_get_version(self):
        """버전 반환 테스트"""
        restorer = MockRestorer()
        
        assert restorer.get_version() == "1.0.0"
    
    def test_load_model(self):
        """모델 로드 테스트"""
        restorer = MockRestorer()
        
        assert restorer._model_loaded is False
        restorer.load_model()
        assert restorer._model_loaded is True
    
    def test_unload_model(self):
        """모델 언로드 테스트"""
        restorer = MockRestorer()
        restorer.load_model()
        
        assert restorer._model_loaded is True
        restorer.unload_model()
        assert restorer._model_loaded is False
    
    def test_preprocess(self, tmp_path):
        """전처리 테스트"""
        input_path = tmp_path / "input.jpg"
        input_path.touch()
        
        restorer = MockRestorer()
        result = restorer.preprocess(input_path)
        
        # 기본 구현은 입력 경로를 그대로 반환
        assert result == input_path
    
    def test_postprocess(self, tmp_path):
        """후처리 테스트"""
        output_path = tmp_path / "output.jpg"
        output_path.touch()
        
        restorer = MockRestorer()
        result = restorer.postprocess(output_path)
        
        # 기본 구현은 출력 경로를 그대로 반환
        assert result == output_path
    
    def test_cleanup(self):
        """리소스 정리 테스트"""
        restorer = MockRestorer()
        
        # 기본 구현은 아무것도 하지 않음
        restorer.cleanup()
        assert True  # 예외가 발생하지 않으면 통과
    
    def test_get_config(self):
        """설정 값 가져오기 테스트"""
        config = {"repo": "/path/to/repo", "device": "cuda"}
        restorer = MockRestorer(config=config)
        
        assert restorer.get_config("repo") == "/path/to/repo"
        assert restorer.get_config("device") == "cuda"
        assert restorer.get_config("nonexistent", "default") == "default"
    
    def test_validate_config_valid(self):
        """설정 유효성 검사 테스트 (유효)"""
        config = {"repo": "/path/to/repo", "device": "cuda"}
        restorer = MockRestorer(config=config)
        
        # 필수 키가 모두 있으면 예외 발생 안 함
        restorer.validate_config(["repo", "device"])
    
    def test_validate_config_missing(self):
        """설정 유효성 검사 테스트 (누락)"""
        config = {"repo": "/path/to/repo"}
        restorer = MockRestorer(config=config)
        
        # 필수 키가 없으면 ValueError 발생
        with pytest.raises(ValueError, match="필수 설정 키가 없습니다"):
            restorer.validate_config(["repo", "device"])
    
    def test_is_model_loaded(self):
        """모델 로드 상태 확인 테스트"""
        restorer = MockRestorer()
        
        assert restorer.is_model_loaded() is False
        restorer.load_model()
        assert restorer.is_model_loaded() is True
    
    def test_get_supported_devices(self):
        """지원 디바이스 목록 테스트"""
        restorer = MockRestorer()
        
        devices = restorer.get_supported_devices()
        assert devices == ["cpu"]  # 기본값


class TestCustomRestorer(BaseRestorer):
    """사용자 정의 복원 클래스 테스트"""
    
    def restore(self, input_path, output_path, **kwargs):
        """사용자 정의 복원"""
        return {
            "output_path": str(output_path),
            "custom_field": "custom_value"
        }
    
    def get_name(self):
        return "CustomRestorer"
    
    def get_version(self):
        return "2.0.0"
    
    def get_supported_devices(self):
        return ["cuda", "cpu"]


class TestCustomRestorerTests:
    """사용자 정의 복원 클래스 테스트"""
    
    def test_custom_restore(self, tmp_path):
        """사용자 정의 복원 테스트"""
        input_path = tmp_path / "input.jpg"
        output_path = tmp_path / "output.jpg"
        
        restorer = TestCustomRestorer()
        result = restorer.restore(input_path, output_path)
        
        assert result["output_path"] == str(output_path)
        assert result["custom_field"] == "custom_value"
    
    def test_custom_get_supported_devices(self):
        """사용자 정의 지원 디바이스 테스트"""
        restorer = TestCustomRestorer()
        
        devices = restorer.get_supported_devices()
        assert devices == ["cuda", "cpu"]
