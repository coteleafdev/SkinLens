# -*- coding: utf-8 -*-
"""
src.restoration.strategies.restoreformer_restorer — RestoreFormer++ 복원 백엔드

현재 RestoreFormer++ 알고리즘을 BaseRestorer 인터페이스로 래핑합니다.
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


class RestoreFormerRestorer(BaseRestorer):
    """RestoreFormer++ 복원 백엔드 v1 (현재 알고리즘).
    
    기존 run_restoreformer() 함수를 래핑합니다.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """RestoreFormer++ 복원 백엔드 v1 초기화.
        
        Args:
            config: 복원 백엔드 설정
                - repo: RestoreFormer++ 레포 루트 경로
                - device: "cuda" | "cpu" (기본 None)
                - output_size: (w, h) - 저장 후 해상도
        """
        super().__init__(config)
    
    def restore(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """RestoreFormer++ 복원 수행.
        
        Args:
            input_path: 입력 이미지 경로
            output_path: 출력 이미지 경로
            **kwargs: 추가 파라미터
                - device: 디바이스
                - output_size: 출력 해상도
        
        Returns:
            복원 결과 딕셔너리
        """
        repo = Path(self.get_config("repo", ""))
        if not repo.is_dir():
            raise ValueError(f"RestoreFormer++ 레포 경로가 유효하지 않습니다: {repo}")
        
        script = repo / "inference.py"
        if not script.is_file():
            raise RuntimeError(f"RestoreFormer++ inference.py 없음: {script}")
        
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        in_path = Path(input_path)
        if not in_path.is_file():
            raise FileNotFoundError(f"RestoreFormer++ 입력 이미지 없음: {in_path}")
        
        # 파라미터 로드
        device = kwargs.get("device", self.get_config("device"))
        output_size = kwargs.get("output_size", self.get_config("output_size"))
        
        # 전처리
        preprocessed_input = _preprocess_image(in_path)
        
        try:
            with tempfile.TemporaryDirectory() as td:
                work_dir = Path(td)
                staged_input = work_dir / f"rf_input{in_path.suffix or '.png'}"
                shutil.copy2(preprocessed_input, staged_input)
                
                cmd = [
                    sys.executable, "-u", str(script),
                    "-i", str(staged_input),
                    "-o", str(work_dir),
                    "-v", "RestoreFormer++",
                    "-s", "2",
                ]
                
                # "auto"는 inference.py에서 지원하지 않으므로 None으로 변환 (auto-detect)
                if device is not None and device != "auto":
                    cmd.extend(["--device", device])
                
                log.info("RestoreFormer++ 입력: %s → %s", in_path.name, staged_input)
                log.info("RestoreFormer++ 실행 중…")
                
                _run_subprocess_with_heartbeat(
                    cmd,
                    cwd=str(repo),
                    pulse_msg="  … RestoreFormer++ 진행 중 (모델/추론) …",
                )
                
                restored_dir = work_dir / "restored_imgs"
                if restored_dir.is_dir():
                    found = sorted(restored_dir.glob(f"{staged_input.stem}.*"))
                    produced = found[0] if found else restored_dir / f"{staged_input.stem}.png"
                else:
                    produced = restored_dir / f"{staged_input.stem}.png"
                
                if not produced.is_file():
                    raise RuntimeError(
                        f"RestoreFormer++ 출력 없음 (기대: {produced}). "
                        f"폴더 내용: {list(work_dir.rglob('*'))[:20]}"
                    )
                
                shutil.copy2(produced, out)
        finally:
            if preprocessed_input != in_path and preprocessed_input.exists():
                preprocessed_input.unlink(missing_ok=True)
        
        if output_size is not None:
            _ensure_match_resolution(out, output_size)
        
        # 후처리
        _postprocess_image(out)
        
        return {
            "output_path": str(out),
            "device": device,
        }
    
    def get_name(self) -> str:
        """복원 백엔드 이름."""
        return "restoreformer_v1"
    
    def get_version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"
