# -*- coding: utf-8 -*-
"""
src.restoration.strategies.codeformer_restorer — CodeFormer 복원 백엔드

현재 CodeFormer 알고리즘을 BaseRestorer 인터페이스로 래핑합니다.
"""
from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from src.pipeline.image_utils import _preprocess_image, _postprocess_image, _run_subprocess_with_heartbeat, _ensure_match_resolution
from src.restoration.base import BaseRestorer

log = logging.getLogger(__name__)


class CodeFormerRestorer(BaseRestorer):
    """CodeFormer 복원 백엔드 v1 (현재 알고리즘).
    
    기존 run_codeformer() 함수를 래핑합니다.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """CodeFormer 복원 백엔드 v1 초기화.
        
        Args:
            config: 복원 백엔드 설정
                - repo: CodeFormer 레포 루트 경로
                - fidelity: --fidelity_weight (기본 1.0, PipelineSettings와 일치)
                - upscale: --upscale 배수 (기본 2)
                - bg_upsampler: "realesrgan" | "none" (기본 "none")
                - output_size: (w, h) - 저장 후 해상도
        """
        super().__init__(config)
    
    def restore(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """CodeFormer 복원 수행.
        
        Args:
            input_path: 입력 이미지 경로
            output_path: 출력 이미지 경로
            **kwargs: 추가 파라미터
                - fidelity: fidelity_weight
                - upscale: upscale 배수
                - bg_upsampler: bg_upsampler
                - output_size: 출력 해상도
        
        Returns:
            복원 결과 딕셔너리
        """
        repo = Path(self.get_config("repo", ""))
        if not repo.is_dir():
            raise ValueError(f"CodeFormer 레포 경로가 유효하지 않습니다: {repo}")
        
        script = repo / "inference_codeformer.py"
        if not script.is_file():
            raise RuntimeError(f"CodeFormer inference_codeformer.py 없음: {script}")
        
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        in_path = Path(input_path)
        if not in_path.is_file():
            raise FileNotFoundError(f"CodeFormer 입력 이미지 없음: {in_path}")
        
        # 파라미터 로드
        fidelity = kwargs.get("fidelity", self.get_config("fidelity", 1.0))  # PipelineSettings와 일치
        upscale = kwargs.get("upscale", self.get_config("upscale", 2))
        bg_upsampler = kwargs.get("bg_upsampler", self.get_config("bg_upsampler", "none"))
        output_size = kwargs.get("output_size", self.get_config("output_size"))
        
        # 전처리
        preprocessed_input = _preprocess_image(in_path)
        
        # bg_upsampler 값 정규화
        _bg = bg_upsampler.strip().lower() if bg_upsampler else "none"
        if _bg not in ("realesrgan", "none"):
            log.warning("CodeFormer bg_upsampler 알 수 없는 값 %r → 'none' 으로 폴백", _bg)
            _bg = "none"
        
        try:
            with tempfile.TemporaryDirectory() as td:
                work_dir = Path(td)
                tmp_in_dir = work_dir / "input_imgs"
                tmp_in_dir.mkdir()
                staged_name = f"cf_input{in_path.suffix or '.png'}"
                staged_input_path = tmp_in_dir / staged_name
                shutil.copy2(preprocessed_input, staged_input_path)
                
                cmd = [
                    sys.executable, "-u", str(script),
                    "--input_path", str(tmp_in_dir),
                    "--output_path", str(work_dir),
                    "--fidelity_weight", str(float(fidelity)),
                    "--upscale", str(int(upscale)),
                    "--bg_upsampler", _bg,
                ]
                
                log.info("CodeFormer 입력: %s → %s (fidelity=%.2f, upscale=%d×, bg_upsampler=%s)", 
                         in_path.name, staged_input_path, float(fidelity), int(upscale), _bg)
                log.info("CodeFormer 실행 중…")
                
                _run_subprocess_with_heartbeat(
                    cmd,
                    cwd=str(repo),
                    pulse_msg="  … CodeFormer 진행 중 (모델/추론) …",
                )
                
                stem = staged_input_path.stem
                restored_dir = work_dir / "final_results"
                if restored_dir.is_dir():
                    found = sorted(restored_dir.glob(f"{stem}.*"))
                    produced = found[0] if found else restored_dir / f"{stem}.png"
                else:
                    produced = restored_dir / f"{stem}.png"
                
                if not produced.is_file():
                    raise RuntimeError(
                        f"CodeFormer 출력 없음 (기대: {produced}). "
                        f"폴더 내용: {list(work_dir.rglob('*'))[:20]}"
                    )
                
                shutil.copy2(produced, out)
                log.info("CodeFormer 산출 → %s", out)
        finally:
            if preprocessed_input != in_path and preprocessed_input.exists():
                preprocessed_input.unlink(missing_ok=True)
        
        if output_size is not None:
            _ensure_match_resolution(out, output_size)
        
        # 후처리
        _postprocess_image(out)
        
        return {
            "output_path": str(out),
            "fidelity": fidelity,
            "upscale": upscale,
            "bg_upsampler": bg_upsampler,
        }
    
    def get_name(self) -> str:
        """복원 백엔드 이름."""
        return "codeformer_v1"
    
    def get_version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
