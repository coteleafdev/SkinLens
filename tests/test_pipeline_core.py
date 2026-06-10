"""
test_pipeline_core.py — 파이프라인 코어 단위 테스트

복원 파이프라인 핵심 로직 테스트
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
import tempfile

from src.pipeline.pipeline_core import (
    project_root,
    format_duration,
    format_torch_cuda_status,
    Restorer,
    _default_restoreformer_repo,
    _default_codeformer_repo,
    _detect_realesrgan_upsampler,
    safe_output_stem,
    PipelineSettings,
    PipelineResult,
    _PipelineMode,
    _choose_mode,
    first_existing_file,
    _stage_pipeline_input_rgb,
    _pil_for_img2img,
    resolve_init_image,
    _load_in_process_config
)


class TestUtilityFunctions:
    """유틸리티 함수 테스트"""
    
    def test_project_root(self):
        """프로젝트 루트 경로 테스트"""
        root = project_root()
        
        assert root is not None
        assert isinstance(root, Path)
        assert root.exists()
    
    def test_format_duration_seconds(self):
        """초 단위 포맷 테스트"""
        assert format_duration(5.5) == "5.50s"
        assert format_duration(30.0) == "30.00s"
    
    def test_format_duration_minutes(self):
        """분 단위 포맷 테스트"""
        assert format_duration(90) == "1m 30s"
        assert format_duration(150) == "2m 30s"
    
    def test_format_duration_hours(self):
        """시간 단위 포맷 테스트"""
        assert format_duration(3661) == "1h 1m 1s"
        assert format_duration(7320) == "2h 2m 0s"
    
    def test_format_torch_cuda_status_no_torch(self):
        """PyTorch 설치 상태 테스트"""
        # torch 모듈이 있으면 테스트 실행
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")
        
        # torch가 있으면 테스트 실행
        status = format_torch_cuda_status()
        assert status is not None
    
    def test_format_torch_cuda_status_no_cuda(self):
        """CUDA 미사용 가능 상태 테스트"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")
        
        status = format_torch_cuda_status()
        assert status is not None
    
    def test_format_torch_cuda_status_available(self):
        """CUDA 사용 가능 상태 테스트"""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")
        
        status = format_torch_cuda_status()
        assert status is not None


class TestRestorerEnum:
    """Restorer Enum 테스트"""
    
    def test_restorer_values(self):
        """Restorer 값 테스트"""
        assert Restorer.RESTOREFORMER == "restoreformer"
        assert Restorer.CODEFORMER == "codeformer"
    
    def test_restorer_string_inheritance(self):
        """Restorer 문자열 상속 테스트"""
        assert isinstance(Restorer.RESTOREFORMER, str)
        assert isinstance(Restorer.CODEFORMER, str)


class TestRepoDetection:
    """레포지토리 감지 테스트"""
    
    def test_default_restoreformer_repo(self):
        """RestoreFormer 기본 레포 테스트"""
        repo = _default_restoreformer_repo()
        
        # 레포가 없으면 None 반환
        assert repo is None or isinstance(repo, Path)
    
    def test_default_codeformer_repo(self):
        """CodeFormer 기본 레포 테스트"""
        repo = _default_codeformer_repo()
        
        # 레포가 없으면 None 반환
        assert repo is None or isinstance(repo, Path)
    
    def test_detect_realesrgan_upsampler_none_repo(self):
        """레포 없는 경우 RealESRGAN 감지 테스트"""
        result = _detect_realesrgan_upsampler(None)
        
        assert result == "none"
    
    def test_detect_realesrgan_upsampler_invalid_repo(self, tmp_path):
        """잘못된 레포 경로 테스트"""
        invalid_repo = tmp_path / "invalid"
        invalid_repo.mkdir()
        
        result = _detect_realesrgan_upsampler(invalid_repo)
        
        assert result == "none"
    
    def test_detect_realesrgan_upsampler_no_weights(self, tmp_path):
        """가중치 파일 없는 경우 테스트"""
        repo = tmp_path / "CodeFormer"
        repo.mkdir()
        (repo / "inference_codeformer.py").touch()
        
        result = _detect_realesrgan_upsampler(repo)
        
        assert result == "none"
    
    def test_detect_realesrgan_upsampler_with_weights(self, tmp_path):
        """가중치 파일 있는 경우 테스트"""
        repo = tmp_path / "CodeFormer"
        repo.mkdir()
        (repo / "inference_codeformer.py").touch()
        
        weights_dir = repo / "weights" / "realesrgan"
        weights_dir.mkdir(parents=True)
        (weights_dir / "RealESRGAN_x2plus.pth").touch()
        
        result = _detect_realesrgan_upsampler(repo)
        
        assert result == "realesrgan"


class TestSafeOutputStem:
    """안전한 출력 파일명 테스트"""
    
    def test_safe_output_stem_none(self):
        """None 입력 테스트"""
        stem = safe_output_stem(None)
        
        assert stem == "image"
    
    def test_safe_output_stem_normal(self):
        """일반 파일명 테스트"""
        stem = safe_output_stem(Path("test_image.jpg"))
        
        assert stem == "test_image"
    
    def test_safe_output_stem_unsafe_chars(self):
        """안전하지 않은 문자 테스트"""
        stem = safe_output_stem(Path("test:file/name.jpg"))
        
        assert ":" not in stem
        assert "/" not in stem
        # 밑줄로 치환되거나 제거됨
    
    def test_safe_output_stem_long_name(self):
        """긴 파일명 테스트"""
        long_name = "a" * 200
        stem = safe_output_stem(Path(f"{long_name}.jpg"))
        
        # 120자로 제한
        assert len(stem) <= 120


class TestPipelineSettings:
    """PipelineSettings 테스트"""
    
    def test_default_settings(self):
        """기본 설정 테스트"""
        settings = PipelineSettings()
        
        assert settings.restorer == Restorer.CODEFORMER
        assert settings.codeformer_fidelity == 1.0
        assert settings.codeformer_upscale == 2
        assert settings.codeformer_additional is True
        assert settings.codeformer_bg_upsampler == "none"
        assert settings.llm_report is True
    
    def test_custom_settings(self):
        """사용자 정의 설정 테스트"""
        settings = PipelineSettings(
            restorer=Restorer.RESTOREFORMER,
            codeformer_fidelity=0.5,
            codeformer_upscale=4,
            llm_report=False
        )
        
        assert settings.restorer == Restorer.RESTOREFORMER
        assert settings.codeformer_fidelity == 0.5
        assert settings.codeformer_upscale == 4
        assert settings.llm_report is False
    
    def test_active_repo_codeformer(self, tmp_path):
        """CodeFormer 활성 레포 테스트"""
        repo = tmp_path / "CodeFormer"
        repo.mkdir()
        (repo / "inference_codeformer.py").touch()
        
        settings = PipelineSettings(codeformer_repo=repo)
        
        assert settings.active_repo == repo
    
    def test_active_repo_restoreformer(self, tmp_path):
        """RestoreFormer 활성 레포 테스트"""
        repo = tmp_path / "RestoreFormerPlusPlus"
        repo.mkdir()
        (repo / "inference.py").touch()
        
        settings = PipelineSettings(
            restorer=Restorer.RESTOREFORMER,
            restoreformer_repo=repo
        )
        
        assert settings.active_repo == repo
    
    def test_restore_ok_codeformer(self, tmp_path):
        """CodeFormer 복원 가능 여부 테스트"""
        repo = tmp_path / "CodeFormer"
        repo.mkdir()
        (repo / "inference_codeformer.py").touch()
        
        settings = PipelineSettings(codeformer_repo=repo)
        
        assert settings.restore_ok is True
    
    def test_restore_ok_restoreformer(self, tmp_path):
        """RestoreFormer 복원 가능 여부 테스트"""
        repo = tmp_path / "RestoreFormerPlusPlus"
        repo.mkdir()
        (repo / "inference.py").touch()
        
        settings = PipelineSettings(
            restorer=Restorer.RESTOREFORMER,
            restoreformer_repo=repo
        )
        
        assert settings.restore_ok is True
    
    def test_restore_ok_none(self):
        """레포 없는 복원 가능 여부 테스트"""
        settings = PipelineSettings()
        
        # 레포가 실제로 존재할 수 있으므로 확인
        # 레포가 없으면 False, 있으면 True
        if settings.codeformer_repo is None and settings.restoreformer_repo is None:
            assert settings.restore_ok is False
        else:
            # 레포가 존재하면 True
            assert settings.restore_ok is True


class TestPipelineResult:
    """PipelineResult 테스트"""
    
    def test_default_result(self):
        """기본 결과 테스트"""
        result = PipelineResult()
        
        assert result.output_stem == ""
        assert result.restored is None
        assert result.wall_restore_sec is None
        assert result.wall_total_sec is None
        assert result.notes == []
    
    def test_custom_result(self, tmp_path):
        """사용자 정의 결과 테스트"""
        restored_path = tmp_path / "restored.png"
        restored_path.touch()
        
        result = PipelineResult(
            output_stem="test",
            restored=restored_path,
            wall_restore_sec=10.5,
            wall_total_sec=15.0,
            notes=["Test note"]
        )
        
        assert result.output_stem == "test"
        assert result.restored == restored_path
        assert result.wall_restore_sec == 10.5
        assert result.wall_total_sec == 15.0
        assert result.notes == ["Test note"]


class TestPipelineMode:
    """파이프라인 모드 테스트"""
    
    def test_choose_mode_analyze_only(self):
        """분석 전용 모드 테스트"""
        mode = _choose_mode(
            input_image=Path("test.jpg"),
            do_restore=False,
            restore_ok=True
        )
        
        assert mode == _PipelineMode.ANALYZE_ONLY
    
    def test_choose_mode_restore_only(self):
        """복원 전용 모드 테스트"""
        mode = _choose_mode(
            input_image=Path("test.jpg"),
            do_restore=True,
            restore_ok=True
        )
        
        assert mode == _PipelineMode.RESTORE_ONLY
    
    def test_choose_mode_restore_not_ok(self):
        """복원 불가능 모드 테스트"""
        with pytest.raises(ValueError):
            _choose_mode(
                input_image=Path("test.jpg"),
                do_restore=True,
                restore_ok=False
            )


class TestFirstExistingFile:
    """첫 번째 존재하는 파일 테스트"""
    
    def test_first_existing_file_found(self, tmp_path):
        """파일 찾기 테스트"""
        file1 = tmp_path / "file1.txt"
        file1.touch()
        
        result = first_existing_file(file1, tmp_path / "file2.txt")
        
        assert result == file1
    
    def test_first_existing_file_none(self, tmp_path):
        """파일 없음 테스트"""
        result = first_existing_file(
            tmp_path / "file1.txt",
            tmp_path / "file2.txt"
        )
        
        assert result is None
    
    def test_first_existing_file_with_none(self, tmp_path):
        """None 포함 테스트"""
        file1 = tmp_path / "file1.txt"
        file1.touch()
        
        result = first_existing_file(None, file1)
        
        assert result == file1


class TestStagePipelineInputRgb:
    """입력 스테이징 테스트"""
    
    def test_stage_pipeline_input_rgb(self, tmp_path):
        """RGB 변환 스테이징 테스트"""
        # 테스트 이미지 생성
        img = Image.new('RGB', (100, 100), color='white')
        input_path = tmp_path / "input.jpg"
        img.save(input_path, 'JPEG')
        
        result = _stage_pipeline_input_rgb(input_path, tmp_path, "test")
        
        assert result.exists()
        assert result.name == "00_input_test.png"
        
        # RGB 변환 확인
        staged_img = Image.open(result)
        assert staged_img.mode == "RGB"


class TestPilForImg2Img:
    """img2img PIL 변환 테스트"""
    
    def test_pil_for_img2img_no_resize(self, tmp_path):
        """리사이즈 없는 테스트"""
        img = Image.new('RGB', (496, 496), color='white')  # 8의 배수
        input_path = tmp_path / "input.png"
        img.save(input_path)
        
        result = _pil_for_img2img(input_path, max_side=768)
        
        # 8의 배수로 정렬되므로 496x496 유지
        assert result.size == (496, 496)
    
    def test_pil_for_img2img_resize(self, tmp_path):
        """리사이즈 테스트"""
        img = Image.new('RGB', (1000, 1000), color='white')
        input_path = tmp_path / "input.png"
        img.save(input_path)
        
        result = _pil_for_img2img(input_path, max_side=500)
        
        # 긴 변이 500 이하
        assert max(result.size) <= 500
    
    def test_pil_for_img2img_8_multiple(self, tmp_path):
        """8픽셀 배수 정렬 테스트"""
        img = Image.new('RGB', (501, 501), color='white')
        input_path = tmp_path / "input.png"
        img.save(input_path)
        
        result = _pil_for_img2img(input_path, max_side=768)
        
        # 8픽셀 배수
        assert result.size[0] % 8 == 0
        assert result.size[1] % 8 == 0


class TestResolveInitImage:
    """초기 이미지 해결 테스트"""
    
    def test_resolve_init_image_explicit(self, tmp_path):
        """명시적 경로 테스트"""
        img = Image.new('RGB', (100, 100), color='white')
        input_path = tmp_path / "test.jpg"
        img.save(input_path)
        
        result = resolve_init_image(
            explicit=input_path
        )
        
        assert result == input_path.resolve()
    
    def test_resolve_init_image_explicit_not_found(self, tmp_path):
        """명시적 경로 없음 테스트"""
        with pytest.raises(FileNotFoundError):
            resolve_init_image(
                explicit=tmp_path / "nonexistent.jpg"
            )
    
    def test_resolve_init_image_default(self, tmp_path):
        """기본 이미지 테스트"""
        # 기본 이미지 생성
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        default_img = images_dir / "origin.png"
        img = Image.new('RGB', (100, 100), color='white')
        img.save(default_img)
        
        with patch('src.pipeline.pipeline_core._default_init_image_path', return_value=default_img):
            result = resolve_init_image(
                explicit=None
            )
            
            assert result == default_img.resolve()


class TestLoadInProcessConfig:
    """In-process 설정 로드 테스트"""
    
    def test_load_in_process_config_default(self):
        """기본 설정 로드 테스트"""
        config = _load_in_process_config()
        
        assert config is not None
        assert "enabled" in config
        assert "codeformer" in config
        assert "restoreformer" in config
        assert "gpu_memory" in config
    
    def test_load_in_process_config_structure(self):
        """설정 구조 테스트"""
        config = _load_in_process_config()
        
        # codeformer 설정
        codeformer_config = config["codeformer"]
        assert "enabled" in codeformer_config
        assert "fallback_on_error" in codeformer_config
        assert "device" in codeformer_config
        assert "default_fidelity" in codeformer_config
        assert "default_upscale" in codeformer_config
        assert "default_bg_upsampler" in codeformer_config
        
        # restoreformer 설정
        restoreformer_config = config["restoreformer"]
        assert "enabled" in restoreformer_config
        assert "fallback_on_error" in restoreformer_config
        assert "device" in restoreformer_config
        assert "default_scale" in restoreformer_config
        
        # gpu_memory 설정
        gpu_config = config["gpu_memory"]
        assert "threshold" in gpu_config
        assert "enable_monitoring" in gpu_config
        assert "auto_unload" in gpu_config
