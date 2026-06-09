"""
test_pipeline_image_utils.py — 이미지 유틸리티 단위 테스트

이미지 전처리, 후처리, 해상도 조정 유틸리티 테스트
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
import tempfile
import shutil

from src.pipeline.image_utils import (
    _run_subprocess_with_heartbeat,
    _preprocess_image,
    _postprocess_image,
    _ensure_match_resolution
)
from src.scoring.config._config import _load_scoring_config
from src.config.config_manager import ConfigManager


class TestRunSubprocessWithHeartbeat:
    """서브프로세스 하트비트 테스트"""
    
    def test_run_subprocess_no_heartbeat(self, tmp_path):
        """하트비트 없는 서브프로세스 테스트"""
        # Windows에서는 python 명령어 사용
        cmd = [sys.executable, "-c", "print('test')"]
        
        # 하트비트 비활성화 (pulse_every_sec <= 0)
        _run_subprocess_with_heartbeat(
            cmd,
            cwd=str(tmp_path),
            pulse_every_sec=0
        )
    
    def test_run_subprocess_with_heartbeat(self, tmp_path):
        """하트비트 있는 서브프로세스 테스트"""
        # Windows에서는 python 명령어 사용
        cmd = [sys.executable, "-c", "print('test')"]
        
        # 하트비트 활성화
        _run_subprocess_with_heartbeat(
            cmd,
            cwd=str(tmp_path),
            pulse_every_sec=0.1  # 짧은 간격으로 테스트
        )
    
    def test_run_subprocess_failure(self, tmp_path):
        """서브프로세스 실패 테스트"""
        # 실패하는 명령어
        cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
        
        with pytest.raises(Exception):
            _run_subprocess_with_heartbeat(
                cmd,
                cwd=str(tmp_path),
                pulse_every_sec=0
            )


class TestPreprocessImage:
    """이미지 전처리 테스트"""
    
    @pytest.fixture
    def sample_image(self, tmp_path):
        """테스트용 이미지 fixture"""
        img = Image.new('RGB', (1000, 1000), color='white')
        img_path = tmp_path / "test_image.jpg"
        img.save(img_path, 'JPEG')
        return img_path
    
    def test_preprocess_image_no_resize(self, sample_image):
        """리사이즈 없는 전처리 테스트"""
        # config.json에서 리사이즈 설정이 없는 경우
        result_path = _preprocess_image(sample_image)
        
        # 원본 경로 반환
        assert result_path == sample_image
    
    def test_preprocess_image_with_resize(self, sample_image):
        """리사이즈 포함 전처리 테스트"""
        # config.json에서 리사이즈 설정 mocking
        config = _load_scoring_config()
        resize_config = config.get("image_processing", {}).get("resize", {})
        # 테스트 구현
    
    def test_preprocess_image_caching(self, sample_image):
        """캐싱 테스트"""
        config = _load_scoring_config()
        # 테스트 구현
    
    def test_preprocess_image_cache_invalidation(self, sample_image, tmp_path):
        """캐시 무효화 테스트 (파일 수정)"""
        config = _load_scoring_config()
        # 테스트 구현
    
    def test_preprocess_image_invalid_resize_config(self, sample_image):
        """잘못된 리사이즈 설정 테스트"""
        config = _load_scoring_config()
        # 테스트 구현


class TestPostprocessImage:
    """이미지 후처리 테스트"""
    
    @pytest.fixture
    def sample_image(self, tmp_path):
        """테스트용 이미지 fixture"""
        img = Image.new('RGB', (500, 500), color='white')
        img_path = tmp_path / "test_image.png"
        img.save(img_path, 'PNG')
        return img_path
    
    def test_postprocess_image_disabled(self, sample_image):
        """후처리 비활성화 테스트"""
        config_manager = ConfigManager()
        # 테스트 구현
    
    def test_postprocess_image_color_correction(self, sample_image):
        """색상 보정 테스트"""
        config_manager = ConfigManager()
        # 테스트 구현
    
    def test_postprocess_image_quality_enhancement(self, sample_image):
        """품질 개선 테스트"""
        config_manager = ConfigManager()
        # 테스트 구현
    
    def test_postprocess_image_artifact_removal_gaussian(self, sample_image):
        """가우시안 필터 아티팩트 제거 테스트"""
        config_manager = ConfigManager()
        # 테스트 구현
    
    def test_postprocess_image_artifact_removal_median(self, sample_image):
        """미디언 필터 아티팩트 제거 테스트"""
        config_manager = ConfigManager()
        # 테스트 구현
    
    def test_postprocess_image_no_modifications(self, sample_image):
        """수정 없는 후처리 테스트"""
        config_manager = ConfigManager()
        # 테스트 구현
    
    def test_postprocess_image_error_handling(self, sample_image):
        """에러 핸들링 테스트"""
        config_manager = ConfigManager()
        # 테스트 구현


class TestEnsureMatchResolution:
    """해상도 조정 테스트"""
    
    @pytest.fixture
    def sample_image(self, tmp_path):
        """테스트용 이미지 fixture"""
        img = Image.new('RGB', (1000, 1000), color='white')
        img_path = tmp_path / "test_image.png"
        img.save(img_path, 'PNG')
        return img_path
    
    def test_ensure_match_resolution_same_size(self, sample_image):
        """동일 해상도 테스트"""
        result_path = _ensure_match_resolution(sample_image, (1000, 1000))
        
        # 원본 경로 반환 (변경 없음)
        assert result_path == sample_image.resolve()
    
    def test_ensure_match_resolution_different_size(self, sample_image):
        """다른 해상도 테스트"""
        result_path = _ensure_match_resolution(sample_image, (500, 500))
        
        # 해상도 변경 확인
        img = Image.open(result_path)
        assert img.size == (500, 500)
    
    def test_ensure_match_resolution_upscale(self, sample_image):
        """업스케일 테스트"""
        result_path = _ensure_match_resolution(sample_image, (2000, 2000))
        
        # 해상도 변경 확인
        img = Image.open(result_path)
        assert img.size == (2000, 2000)
    
    def test_ensure_match_resolution_downscale(self, sample_image):
        """다운스케일 테스트"""
        result_path = _ensure_match_resolution(sample_image, (100, 100))
        
        # 해상도 변경 확인
        img = Image.open(result_path)
        assert img.size == (100, 100)
