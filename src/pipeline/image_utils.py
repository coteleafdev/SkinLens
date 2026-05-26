"""
image_utils.py — 이미지 전처리/후처리 유틸리티 함수.

이 모듈은 pipeline_core.py에서 분리되어 순환 import 문제를 해결합니다.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _run_subprocess_with_heartbeat(
    cmd: list[str],
    *,
    cwd: str,
    pulse_every_sec: float = 45.0,
    pulse_msg: str = "  … subprocess still running …",
) -> None:
    """서브프로세스 실행 및 하트비트 로깅."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if pulse_every_sec <= 0:
        try:
            subprocess.run(cmd, cwd=cwd, check=True, env=env)
        except subprocess.CalledProcessError as e:
            log.error("subprocess 실행 실패: %s", e)
            raise
        return
    stop = threading.Event()

    def _pulse() -> None:
        while not stop.wait(timeout=pulse_every_sec):
            log.debug(pulse_msg)

    t = threading.Thread(target=_pulse, daemon=True)
    t.start()
    try:
        subprocess.run(cmd, cwd=cwd, check=True, env=env)
    except subprocess.CalledProcessError as e:
        log.error("subprocess 실행 실패: %s", e)
        raise
    finally:
        stop.set()
        t.join(timeout=2.0)
        if t.is_alive():
            log.warning("heartbeat 스레드가 제때 종료되지 않았습니다.")


def _preprocess_image(image_path: Path) -> Path:
    """이미지 전처리 함수 (스마트폰 이미지 리사이징 포함).
    
    [EXTENSION 2026-05-16] 스마트폰 이미지 리사이징 기능을 전처리 단으로 이동.
    config.json에서 리사이즈 크기를 로드하여 적용.
    추후 노이즈 제거, 색상 보정 등 추가 전처리 로직 추가 예정.
    
    [OPTIMIZATION 2026-05-23] 불필요한 I/O 제거: 동일 이미지에 대해 캐싱 적용.
    이미 리사이징된 파일이 존재하면 재사용하여 중복 I/O 방지.
    """
    from PIL import Image
    
    # config.json에서 리사이즈 크기 로드
    resize_wh = None  # null이면 원본 해상도 유지
    try:
        from src.scoring.skin_scoring import _load_scoring_config
        config = _load_scoring_config()
        resize_wh_config = config.get("restoration", {}).get("input_resize", None)
        if resize_wh_config is not None and isinstance(resize_wh_config, list) and len(resize_wh_config) == 2:
            resize_wh = tuple(resize_wh_config)
    except Exception:
        pass  # 기본값(null=원본해상도) 사용
    
    if resize_wh is None:
        # 리사이즈 필요 없으면 원본 경로 반환
        return image_path
    
    # 캐시 파일명 생성 (원본 파일명 + 해시 + 리사이즈 크기 + mtime)
    # 동일한 이미지와 리사이즈 크기에 대해 재사용
    # [FIX P1-1] 파일 mtime을 해시에 포함하여 파일 수정 시 캐시 갱신
    cache_key = f"{image_path.stem}_{resize_wh[0]}x{resize_wh[1]}"
    # 파일 경로 + mtime 해시를 사용하여 파일 수정 감지
    file_mtime = image_path.stat().st_mtime
    file_hash = hashlib.md5(f"{str(image_path)}_{file_mtime}".encode()).hexdigest()[:8]
    cache_dir = image_path.parent / ".cache" / "preprocess"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_path = cache_dir / f"{cache_key}_{file_hash}.png"

    # [FIX P1-2] 동일 cache_key를 가진 오래된 캐시 파일 정리
    try:
        for old_file in cache_dir.glob(f"{cache_key}_*.png"):
            if old_file != output_path:
                old_file.unlink()
                log.debug("오래된 캐시 파일 삭제: %s", old_file.name)
    except Exception as e:
        log.warning("캐시 파일 정리 실패: %s", e)

    # 캐시 파일이 존재하면 재사용
    if output_path.exists():
        log.debug("전처리 캐시 재사용: %s", output_path.name)
        return output_path
    
    # 리사이즈 필요한 경우 캐시에 저장
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    im = im.resize(resize_wh, Image.Resampling.LANCZOS)
    
    im.save(output_path, "PNG")
    log.info("전처리 리사이징: %s %dx%d → %dx%d → %s (캐시)", image_path.name, w, h, resize_wh[0], resize_wh[1], output_path.name)
    
    return output_path


def _postprocess_image(image_path: Path) -> Path:
    """이미지 후처리 더미 함수 (향후 확장성을 위해 추가).
    
    [EXTENSION 2026-05-16] 현재는 입력을 그대로 반환.
    추후 색상 보정, 대비 조정, 아티팩트 제거 등 후처리 로직 추가 예정.
    
    TODO: 실제 후처리 로직이 추가될 때까지 더미로 유지
    """
    return image_path


def _ensure_match_resolution(path: Path, target_wh: tuple[int, int]) -> Path:
    """디스크상 이미지를 target_wh 로 맞춤(덮어쓰기). 입력 해상도와 불일치할 때만 리샘플."""
    from PIL import Image

    p = Path(path)
    tw, th = target_wh
    im = Image.open(p).convert("RGB")
    w0, h0 = im.size
    if (w0, h0) == (tw, th):
        return p.resolve()
    im = im.resize((tw, th), Image.Resampling.LANCZOS)
    log.info("출력을 입력 해상도에 맞춤: %s %dx%d → %dx%d", p.name, w0, h0, tw, th)
    im.save(p, "PNG")
    return p.resolve()
