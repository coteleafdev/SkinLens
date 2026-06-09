"""
pipeline_core.py - RestoreFormer++ / CodeFormer / 모공 파이프라인 핵심 로직.

skin_analysis_pipeline.py 에서 import 해서 사용합니다.
PySide6 의존 없음 → CLI/서버 환경에서도 단독 사용 가능.

복원 백엔드 선택 (Restorer Enum / --restorer CLI 인자)
  restoreformer  : RestoreFormerPlusPlus/inference.py  (-v RestoreFormer++ -s 2)
  codeformer     : CodeFormer/inference_codeformer.py  (--fidelity_weight, --upscale)

기본값: restoreformer
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# [FIX P2-21] Strategy Pattern: BaseRestorer import for type hint
from src.restoration.base import BaseRestorer

# [REFACTOR P2-19] Strategy Pattern: 레지스트리 등록
from src.restoration.strategies.register_restorers import register_all_restorers
register_all_restorers()  # 모듈 로드 시 자동 등록

# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def project_root() -> Path:
    """프로젝트 루트 디렉터리 반환."""
    return Path(__file__).resolve().parent.parent.parent


def _load_in_process_config() -> dict:
    """Load in-process execution configuration from config file.
    
    Returns:
        Dict with configuration settings.
    """
    import json
    
    config_path = project_root() / "config" / "in_process_config.json"
    
    # Default configuration
    default_config = {
        "in_process_execution": {
            "enabled": True,
            "codeformer": {
                "enabled": True,
                "fallback_on_error": True,
                "device": "auto",
                "default_fidelity": 1.0,
                "default_upscale": 2,
                "default_bg_upsampler": "none"
            },
            "restoreformer": {
                "enabled": False,
                "fallback_on_error": True,
                "device": "auto",
                "default_scale": 2
            },
            "gpu_memory": {
                "threshold": 0.9,
                "enable_monitoring": True,
                "auto_unload": True
            }
        }
    }
    
    # Load from file if exists
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                # Merge with default config
                default_config.update(user_config)
                log.debug(f"Loaded in-process config from {config_path}")
        except Exception as e:
            log.warning(f"Failed to load in-process config from {config_path}: {e}")
            log.warning("Using default configuration")
    else:
        log.debug(f"In-process config not found at {config_path}, using defaults")
    
    return default_config.get("in_process_execution", default_config["in_process_execution"])


# 하위 호환 별칭 - 내부 코드가 _project_root() 를 직접 참조하는 곳을 위해 유지
_project_root = project_root


def format_duration(seconds: float) -> str:
    """초를 사람이 읽기 쉬운 문자열로 변환."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


# 하위 호환 별칭
_format_duration = format_duration


def _log_stage_timing(label: str, seconds: float) -> None:
    """[REFACTOR P2] print() → log.debug() 교체"""
    log.debug("[시간] %s: %s", label, _format_duration(seconds))


def format_torch_cuda_status() -> str:
    """CUDA 상태 문자열 반환. GUI·CLI 모두 사용."""
    try:
        import torch
    except ImportError:
        return "PyTorch: 설치되지 않음"
    
    if not torch.cuda.is_available():
        return (
            "PyTorch CUDA: 사용 불가 (torch.cuda.is_available()==False). "
            "GPU가 있어도 CPU 전용 torch 이거나 드라이버/CUDA 버전이 맞지 않을 수 있습니다."
        )
    n = torch.cuda.device_count()
    name = torch.cuda.get_device_name(0)
    return f"PyTorch CUDA: 사용 가능 - GPU {n}개, cuda:0 = {name}"


# ---------------------------------------------------------------------------
# 복원 백엔드 선택 Enum
# ---------------------------------------------------------------------------
class Restorer(str, Enum):
    """복원 백엔드. str 상속으로 argparse choices / JSON 직렬화 호환."""
    RESTOREFORMER = "restoreformer"
    CODEFORMER    = "codeformer"


def _default_restoreformer_repo() -> Optional[Path]:
    p = _project_root() / "external" / "RestoreFormerPlusPlus"
    if p.is_dir() and (p / "inference.py").is_file():
        return p
    return None


def _default_codeformer_repo() -> Optional[Path]:
    p = _project_root() / "external" / "CodeFormer"
    if p.is_dir() and (p / "inference_codeformer.py").is_file():
        return p
    return None


def _detect_realesrgan_upsampler(codeformer_repo: Optional[Path]) -> str:
    """[FIX ①⑦] CodeFormer RealESRGAN 가중치 파일 존재 여부로 bg_upsampler 자동 결정.

    CodeFormer 는 --bg_upsampler realesrgan 지정 시 runtime/weights/ 아래
    RealESRGAN_x2plus.pth 또는 RealESRGAN_x4plus.pth 를 요구한다.
    해당 파일이 없으면 실행 중 오류가 나므로, 미리 탐색해 "none" 으로 폴백한다.

    Returns:
        "realesrgan" - 가중치 파일 존재 확인됨
        "none"       - 파일 없음 또는 레포 경로 미확인
    """
    if codeformer_repo is None or not codeformer_repo.is_dir():
        return "none"
    weights_dir = codeformer_repo / "weights" / "realesrgan"
    candidates = [
        weights_dir / "RealESRGAN_x2plus.pth",
        weights_dir / "RealESRGAN_x4plus.pth",
    ]
    if any(p.is_file() for p in candidates):
        return "realesrgan"
    # weights 바로 아래에 있는 경우도 허용
    alt_dir = codeformer_repo / "weights"
    alt_candidates = [
        alt_dir / "RealESRGAN_x2plus.pth",
        alt_dir / "RealESRGAN_x4plus.pth",
    ]
    if any(p.is_file() for p in alt_candidates):
        return "realesrgan"
    return "none"


def _default_init_image_path() -> Path:
    return _project_root() / "images" / "origin.png"


def _pil_for_img2img(path: Path, *, max_side: int = 768) -> Any:
    """img2img 입력용 PIL: 긴 변을 max_side 이하로 맞춘 뒤 8픽셀 배수로 정렬."""
    from PIL import Image

    im = Image.open(path).convert("RGB")
    w, h = im.size
    w0, h0 = w, h
    m = max(w, h)
    if m > max_side:
        scale = max_side / float(m)
        w = max(8, int(round(w * scale)))
        h = max(8, int(round(h * scale)))
        im = im.resize((w, h), Image.Resampling.LANCZOS)
    w, h = im.size
    nw = max(8, (w // 8) * 8)
    nh = max(8, (h // 8) * 8)
    if (nw, nh) != (w, h):
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    fw, fh = im.size
    if (fw, fh) != (w0, h0):
        log.info("입력 리사이즈: %s %dx%d → %dx%d (긴 변 상한 %dpx)", path.name, w0, h0, fw, fh, max_side)
    return im


def resolve_init_image(
    explicit: Optional[Path],
) -> Optional[Path]:
    """-i 경로 또는 기본 images/origin.png 로 img2img."""
    if explicit is not None:
        p = Path(explicit).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"-i 경로에 파일이 없습니다: {p}")
        return p
    default = _default_init_image_path()
    if default.is_file():
        log.info("입력 미지정 - img2img 기본 이미지 사용: %s", default)
        return default.resolve()
    return None


# 하위 호환 별칭
_resolve_init_image = resolve_init_image


_STEM_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_STEM_MULTI_US = re.compile(r"_+")


def safe_output_stem(input_image: Optional[Path]) -> str:
    """산출 PNG 파일명에 붙일 안전한 식별자.

    OS 불가 문자(백슬래시·콜론·와일드카드 등)만 ``_`` 로 치환한다.
    한글·알파벳·숫자·공백 이외의 일반 유니코드는 유지된다.
    """
    if input_image is None:
        return "image"
    raw = Path(input_image).resolve().stem
    s = _STEM_UNSAFE.sub("_", raw)
    s = _STEM_MULTI_US.sub("_", s).strip("._-")
    return s[:120] if s else "image"


def _stage_pipeline_input_rgb(source: Path, out_dir: Path, stem: str) -> Path:
    """입력을 RGB PNG로 00_input_<stem>.png 에 저장.
    
    [REFACTOR 2026-05-16] 리사이징 로직을 전처리 단(_preprocess_image)으로 이동.
    이 함수는 단순히 RGB 변환만 담당.
    """
    from PIL import Image

    out_path = out_dir / f"00_input_{stem}.png"
    im = Image.open(source).convert("RGB")
    w, h = im.size
    log.info("입력 스테이징: %s %dx%d → %s", source.name, w, h, out_path.name)
    im.save(out_path, "PNG")
    return out_path.resolve()


def first_existing_file(*candidates: Optional[Path]) -> Optional[Path]:
    """후보 경로를 순서대로 탐색해 처음으로 존재하는 파일을 반환한다."""
    for p in candidates:
        if p is None:
            continue
        if p.is_file():
            return p
    return None


# 하위 호환 별칭
_first_existing_file = first_existing_file


# ---------------------------------------------------------------------------
# 설정 Dataclass
# ---------------------------------------------------------------------------
@dataclass
class PipelineSettings:
    """복원 파이프라인 설정."""
    # ── 복원 백엔드 선택 ──────────────────────────────────────────────────
    restorer: Restorer = Restorer.CODEFORMER  # 기본: CodeFormer
    # ── RestoreFormer++ ──────────────────────────────────────────────────
    restoreformer_repo: Optional[Path] = None
    restoreformer_device: Optional[str] = None  # "cuda" | "cpu" | "auto" | None (auto-detect)
    # ── CodeFormer ───────────────────────────────────────────────────────
    codeformer_repo: Optional[Path] = None
    codeformer_fidelity: float = 1.0  # 0=보정 최대 / 1=원본 충실 (분석 측정항목 경향 반영)
    codeformer_upscale: int = 2        # 업스케일 배수
    codeformer_additional: bool = True  # RF++ 복원 후 CodeFormer 추가 복원 여부
    # [FIX ①⑦] bg_upsampler: "realesrgan" | "none"
    # RealESRGAN 가중치 미설치 환경에서는 "none" 으로 설정해야 크래시를 방지한다.
    # 기본값을 "none"으로 설정하여 CPU 환경에서도 안정 실행
    codeformer_bg_upsampler: str = "none"
    # ── LLM 소견 ───────────────────────────────────────────────────────
    llm_report: bool = True  # 기본적으로 LLM 소견 생성

    def __post_init__(self) -> None:
        # None 이면 프로젝트 내 기본 경로 탐색 (양쪽 모두 시도)
        if self.restoreformer_repo is None:
            self.restoreformer_repo = _default_restoreformer_repo()
        if self.codeformer_repo is None:
            self.codeformer_repo = _default_codeformer_repo()

    # ── 편의 프로퍼티 ─────────────────────────────────────────────────────
    @property
    def active_repo(self) -> Optional[Path]:
        """현재 선택된 백엔드의 레포 경로."""
        if self.restorer is Restorer.CODEFORMER:
            return self.codeformer_repo
        return self.restoreformer_repo

    @property
    def restore_ok(self) -> bool:
        """현재 백엔드가 실행 가능한지 확인."""
        if self.restorer is Restorer.CODEFORMER:
            r = self.codeformer_repo
            return r is not None and r.is_dir() and (r / "inference_codeformer.py").is_file()
        r = self.restoreformer_repo
        return r is not None and r.is_dir() and (r / "inference.py").is_file()




@dataclass
class PipelineResult:
    """파이프라인 실행 결과."""
    output_stem: str = ""
    restored: Optional[Path] = None
    wall_restore_sec: Optional[float] = None
    wall_total_sec: Optional[float] = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 파이프라인 모드 Enum
# ---------------------------------------------------------------------------
class _PipelineMode(Enum):
    """내부 파이프라인 실행 경로를 명확히 분류.

    [REFACTOR 2026-05-17] ANALYZE_ONLY 추가 (복원 없이 원본 직접 분석)
    """
    RESTORE_ONLY = auto()       # --restore-only: 원본 복사 → 복원 엔진
    ANALYZE_ONLY = auto()       # --no-restore: 복원 없이 원본 직접 분석


def _choose_mode(
    *,
    input_image: Optional[Path],
    do_restore: bool,
    restore_ok: bool,
) -> _PipelineMode:
    """파이프라인 모드 선택.

    [REFACTOR 2026-05-17] do_restore=False 시 ANALYZE_ONLY 반환
    """
    if not do_restore:
        return _PipelineMode.ANALYZE_ONLY   # 복원 없이 원본 직접 분석
    if not restore_ok:
        raise ValueError(
            "복원 엔진이 필요합니다. "
            "CodeFormer 또는 RestoreFormer 경로를 확인하세요."
        )
    return _PipelineMode.RESTORE_ONLY


# ---------------------------------------------------------------------------
# 스테이지 함수
# ---------------------------------------------------------------------------
# 이미지 전처리/후처리 함수는 image_utils 모듈로 분리 (순환 import 방지)
from src.pipeline.image_utils import _preprocess_image, _postprocess_image, _run_subprocess_with_heartbeat, _ensure_match_resolution


def run_restoreformer(
    repo: Path,
    input_path: Path,
    output_path: Path,
    *,
    output_size: Optional[tuple[int, int]] = None,
    device: Optional[str] = None,
) -> Path:
    """
    RestoreFormer++ 복원 스테이지.

    레포 구조:
        RestoreFormerPlusPlus/
            inference.py
    
    [EXTENSION 2026-05-16] 전처리/후처리 함수 추가 (현재는 더미)
    """
    script = repo / "inference.py"
    if not script.is_file():
        raise RuntimeError(f"RestoreFormer++ inference.py 없음: {script}")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    in_path = Path(input_path)
    if not in_path.is_file():
        raise FileNotFoundError(f"RestoreFormer++ 입력 이미지 없음: {in_path}")

    # 전처리 (현재는 더미)
    preprocessed_input = _preprocess_image(in_path)

    try:
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            # OpenCV(cv2.imread)가 Windows에서 유니코드 경로를 못 읽는 경우를 피하기 위해
            # ASCII 파일명으로 임시 스테이징 후 서브프로세스에 전달한다.
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
            log.info("RestoreFormer++ 실행 중… (모델 로드·가중치 다운로드로 수 분 조용할 수 있음)")
            _run_subprocess_with_heartbeat(
                cmd,
                cwd=str(repo),
                pulse_msg="  … RestoreFormer++ 진행 중 (모델/추론) …",
            )
            restored_dir = work_dir / "restored_imgs"
            # glob 우선 탐색: 확장자 추측 오류 방지
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
        # 임시 파일 정리 (리사이즈된 경우만)
        if preprocessed_input != in_path and preprocessed_input.exists():
            preprocessed_input.unlink(missing_ok=True)
    if output_size is not None:
        _ensure_match_resolution(out, output_size)
    
    # 후처리 (현재는 더미)
    _postprocess_image(out)
    
    return out


def run_codeformer(
    repo: Path,
    input_path: Path,
    output_path: Path,
    *,
    fidelity: float = 1.0,  # PipelineSettings 기본값과 일치 (1.0=원본 충실)
    upscale: int = 2,
    bg_upsampler: str = "none",
    output_size: Optional[tuple[int, int]] = None,
    use_in_process: Optional[bool] = None,  # [NEW] In-process execution flag (None = read from config)
) -> Path:
    """
    CodeFormer 복원 스테이지.

    [REFACTOR 2026-05-24] In-process execution support.
    use_in_process=True: Use in-process CodeFormer (faster, no subprocess overhead)
    use_in_process=False: Use subprocess (fallback for compatibility)

    레포 구조 예:
        CodeFormer/
            inference_codeformer.py
            weights/CodeFormer/codeformer.pth   ← 자동 다운로드 또는 사전 배치
    출력 구조 (--output_path 는 RestoreFormer++ 의 -o 와 같이 임시 work_dir 루트):
        <work_dir>/cropped_faces/, restored_faces/ … (중간 산출)
        <work_dir>/final_results/<입력파일 stem>.png  ← 합성 결과 (기본 PNG)

    [EXTENSION 2026-05-16] 전처리/후처리 함수 추가 (현재는 더미)

    Parameters
    ----------
    repo          : CodeFormer 레포 루트 경로
    input_path    : 원본 이미지 경로
    output_path   : 산출 이미지 저장 경로
    fidelity      : --fidelity_weight (0=최대 보정, 1=원본 충실), 기본 1.0 (PipelineSettings와 일치)
    upscale       : --upscale 배수 (기본 2)
    bg_upsampler  : [FIX ①⑦] "realesrgan" | "none" - RealESRGAN 가중치 없으면 "none"
    output_size   : (w, h) - 저장 후 이 해상도로 리샘플
    use_in_process: True for in-process, False for subprocess, None to read from config (default: None)
    """
    # Load in-process configuration
    if use_in_process is None:
        use_in_process = _load_in_process_config().get("codeformer", {}).get("enabled", True)
    
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    in_path = Path(input_path)
    if not in_path.is_file():
        raise FileNotFoundError(f"CodeFormer 입력 이미지 없음: {in_path}")

    # 전처리 (현재는 더미)
    preprocessed_input = _preprocess_image(in_path)

    # [FIX ②] bg_upsampler 값 정규화
    _bg = bg_upsampler.strip().lower() if bg_upsampler else "none"
    if _bg not in ("realesrgan", "none"):
        log.warning("CodeFormer bg_upsampler 알 수 없는 값 %r → 'none' 으로 폴백", _bg)
        _bg = "none"

    # In-process execution (new path)
    if use_in_process:
        try:
            log.info("CodeFormer in-process 실행 (fidelity=%.2f, upscale=%d×, bg_upsampler=%s)", float(fidelity), int(upscale), _bg)
            
            # Import in-process CodeFormer wrapper
            # Add project path to import from model-serving-refactor
            import sys
            project_root = Path(__file__).resolve().parents[2]  # src/pipeline → project root
            in_process_path = project_root / "model-serving-refactor" / "src"
            if str(in_process_path) not in sys.path:
                sys.path.insert(0, str(in_process_path))
            
            from codeformer import CodeFormer
            
            # Initialize and load model
            model = CodeFormer(repo_path=repo, device=None)  # Auto-detect device
            model.load(fidelity=fidelity, upscale=upscale, bg_upsampler=_bg)
            
            # codeformer 로거에 포맷 적용 (codeformer가 자체 로거를 설정한 후)
            from src.utils.utils import apply_formatter_to_all_loggers
            apply_formatter_to_all_loggers()
            
            # Run inference
            result = model(
                preprocessed_input,
                out,
                fidelity=fidelity,
                upscale=upscale,
                bg_upsampler=_bg
            )
            
            log.info("CodeFormer in-process 완료 → %s", result)
            
        except Exception as e:
            log.warning(f"CodeFormer in-process 실패, subprocess로 폴백: {e}")
            log.info("CodeFormer subprocess 실행으로 전환...")
            # Fallback to subprocess
            return _run_codeformer_subprocess(
                repo, preprocessed_input, out,
                fidelity=fidelity, upscale=upscale, bg_upsampler=_bg,
                original_input=in_path
            )
    else:
        # Subprocess execution (original path)
        return _run_codeformer_subprocess(
            repo, preprocessed_input, out,
            fidelity=fidelity, upscale=upscale, bg_upsampler=_bg,
            original_input=in_path
        )
    
    # Cleanup
    if preprocessed_input != in_path and preprocessed_input.exists():
        preprocessed_input.unlink(missing_ok=True)

    if output_size is not None:
        _ensure_match_resolution(out, output_size)
    
    # 후처리 (현재는 더미)
    _postprocess_image(out)
    
    return out


def _run_codeformer_subprocess(
    repo: Path,
    input_path: Path,
    output_path: Path,
    *,
    fidelity: float,
    upscale: int,
    bg_upsampler: str,
    original_input: Path,
) -> Path:
    """Subprocess execution for CodeFormer (fallback path)."""
    script = repo / "inference_codeformer.py"
    if not script.is_file():
        raise RuntimeError(f"CodeFormer inference_codeformer.py 없음: {script}")
    
    try:
        with tempfile.TemporaryDirectory() as td:
            work_dir = Path(td)
            # [FIX ②] 입력 이미지를 ASCII 파일명으로 스테이징
            tmp_in_dir = work_dir / "input_imgs"
            tmp_in_dir.mkdir()
            staged_name = f"cf_input{original_input.suffix or '.png'}"
            staged_input_path = tmp_in_dir / staged_name
            shutil.copy2(input_path, staged_input_path)

            cmd = [
                sys.executable, "-u", str(script),
                "--input_path",      str(tmp_in_dir),
                "--output_path",     str(work_dir),
                "--fidelity_weight", str(float(fidelity)),
                "--upscale",         str(int(upscale)),
                "--bg_upsampler",    bg_upsampler,
            ]
            log.info("CodeFormer subprocess 입력: %s → %s (fidelity=%.2f, upscale=%d×, bg_upsampler=%s)", original_input.name, staged_input_path, float(fidelity), int(upscale), bg_upsampler)
            log.info("CodeFormer subprocess 실행 중… (최초 실행 시 가중치 다운로드로 수 분 조용할 수 있음)")
            _run_subprocess_with_heartbeat(
                cmd,
                cwd=str(repo),
                pulse_msg="  … CodeFormer 진행 중 (모델/추론) …",
            )

            # [FIX ②] glob 탐색 기준을 staged 파일명 stem 으로 변경
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
            shutil.copy2(produced, output_path)
            log.info("CodeFormer subprocess 산출 → %s", output_path)
    
    finally:
        # 임시 파일 정리 (리사이즈된 경우만)
        if input_path != original_input and input_path.exists():
            input_path.unlink(missing_ok=True)
    
    return output_path


# ---------------------------------------------------------------------------
# 통합 복원 디스패처 (Strategy Pattern 적용)
# ---------------------------------------------------------------------------
def _create_restorer_strategy(
    backend: Restorer,
    cfg: PipelineSettings,
) -> "BaseRestorer":
    """[FIX P2-19] Strategy Pattern: 복원 백엔드 Strategy 생성 (레지스트리 사용).

    [REFACTOR P2-19] 직접 import 대신 RestorerRegistry 사용.
    향후 새로운 복원 엔진 추가 시 config.json에만 등록하면 됨.

    Args:
        backend: 복원 백엔드 Enum
        cfg: 파이프라인 설정

    Returns:
        BaseRestorer 인스턴스
    """
    from src.restoration.registry import RestorerRegistry

    # Enum을 레지스트리 이름으로 변환
    if backend is Restorer.CODEFORMER:
        restorer_name = "codeformer_v1"
        restorer_config = {
            "repo": cfg.codeformer_repo,
            "fidelity": cfg.codeformer_fidelity,
            "upscale": cfg.codeformer_upscale,
            "bg_upsampler": cfg.codeformer_bg_upsampler,
        }
    elif backend is Restorer.RESTOREFORMER:
        restorer_name = "restoreformer_v1"
        restorer_config = {
            "repo": cfg.restoreformer_repo,
            "device": cfg.restoreformer_device,
        }
    else:
        raise ValueError(f"지원하지 않는 복원 백엔드: {backend}")

    return RestorerRegistry.create(restorer_name, config=restorer_config)


def run_restorer(
    cfg: PipelineSettings,
    input_path: Path,
    output_path: Path,
    *,
    output_size: Optional[tuple[int, int]] = None,
) -> Path:
    """
    cfg.restorer 에 따라 RestoreFormer++ 또는 CodeFormer 를 실행한다.
    
    [FIX P2-21] Strategy Pattern 적용: BaseRestorer 인터페이스를 사용하여
    복원 백엔드를 유연하게 교체 가능하도록 수정.
    
    codeformer_additional=True 이고 restorer=RESTOREFORMER 이면
    RF++ → CodeFormer 순차 실행.

    호출 측에서 백엔드를 의식하지 않아도 되도록 단일 진입점으로 통합.
    
    [EXTENSION 2026-05-16] 각 복원 엔진에 전처리/후처리 적용 (현재는 더미)
    """
    backend = cfg.restorer
    log.info("복원 백엔드: %s", backend.value)

    # RF++ → CodeFormer 순차 실행
    if backend is Restorer.RESTOREFORMER and cfg.codeformer_additional:
        # RF++ 먼저 실행 (Strategy Pattern 사용)
        rf_strategy = _create_restorer_strategy(Restorer.RESTOREFORMER, cfg)
        rf_output = output_path.parent / f"00_rf_temp_{output_path.name}"
        rf_strategy.restore(
            input_path,
            rf_output,
            device=cfg.restoreformer_device,
            output_size=output_size,
        )
        
        # CodeFormer 추가 실행 (Strategy Pattern 사용)
        cf_strategy = _create_restorer_strategy(Restorer.CODEFORMER, cfg)
        cf_strategy.restore(
            rf_output,
            output_path,
            fidelity=cfg.codeformer_fidelity,
            upscale=cfg.codeformer_upscale,
            bg_upsampler=cfg.codeformer_bg_upsampler,
            output_size=output_size,
        )
        # 임시 파일 삭제
        if rf_output.exists():
            rf_output.unlink()
        return output_path

    # 단일 백엔드 실행 (Strategy Pattern 사용)
    strategy = _create_restorer_strategy(backend, cfg)
    strategy.restore(
        input_path,
        output_path,
        output_size=output_size,
    )
    return output_path


def final_pipeline_artifact_path(res: PipelineResult, out_dir: Path) -> Optional[Path]:
    """미리보기·리포트와 동일 우선순위로 최종 산출 PNG 경로를 고른다.
    
    `res.*` 에 설정된 실제 경로를 먼저 두어 stem 불일치·예전 파일명에도 대응한다.
    """
    stem = res.output_stem
    # 복원 결과만 확인 (모공 완화 제거)
    return _first_existing_file(
        res.restored,
        out_dir / f"01_restored_{stem}.png",
        out_dir / f"00_restored_{stem}.png",
    )


# ---------------------------------------------------------------------------
# 메인 파이프라인
# ---------------------------------------------------------------------------
def run_enhancement_pipeline(
    cfg: PipelineSettings,
    out_dir: Path,
    *,
    input_image: Optional[Path] = None,
    do_restore: bool = True,
) -> PipelineResult:
    """
    파이프라인 진입점.
    
    모드 선택은 _PipelineMode Enum 으로 일원화하여 중첩 if 제거.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = PipelineResult()
    t0_all = time.perf_counter()

    stem = safe_output_stem(input_image)
    res.output_stem = stem

    # 이미지별 폴더 생성 (고객 아이디 또는 원본 이미지 파일명)
    image_folder = out_dir / stem
    image_folder.mkdir(parents=True, exist_ok=True)

    input_resolution: Optional[tuple[int, int]] = None
    if input_image is not None:
        _src_in = Path(input_image).resolve()
        if not _src_in.is_file():
            raise FileNotFoundError(f"입력 이미지를 찾을 수 없습니다: {_src_in}")
        input_image = _stage_pipeline_input_rgb(_src_in, image_folder, stem)
        from PIL import Image

        input_resolution = Image.open(input_image).size

    restore_ok = cfg.restore_ok   # 선택된 백엔드 레포가 유효한지
    backend_name = cfg.restorer.value  # 로그용 이름 ("restoreformer" | "codeformer")

    p_rf_first = image_folder / f"00_restored_{stem}.png"
    p_restored = image_folder / f"01_restored_{stem}.png"

    mode = _choose_mode(
        input_image=input_image,
        do_restore=do_restore,
        restore_ok=restore_ok,
    )

    _in_disp = str(Path(input_image).resolve()) if input_image is not None else "(없음)"
    log.info("파이프라인 - stem=%r 모드=%s 입력=%s 산출=%s", stem, mode.name, _in_disp, image_folder.resolve())

    # ── ANALYZE_ONLY (복원 없이 원본 직접 분석) ───────────────────────────────
    if mode is _PipelineMode.ANALYZE_ONLY:
        if input_image is None:
            raise ValueError(
                "분석하려면 입력 이미지가 필요합니다. "
                "-i 경로를 주거나 images/origin.png 가 있어야 합니다."
            )
        staged = image_folder / f"00_input_{stem}.png"
        if not staged.is_file():
            raise FileNotFoundError(f"정규화된 입력이 없습니다: {staged}")
        # 원본 이미지를 "복원된" 결과로 처리
        res.restored = staged
        res.wall_restore_sec = 0.0
        res.notes.append("복원 생략 - 원본 이미지를 직접 분석")

    # ── RESTORE_ONLY ──────────────────────────────────────────────────────
    elif mode is _PipelineMode.RESTORE_ONLY:
        if input_image is None:
            raise ValueError(
                "복원하려면 입력 이미지가 필요합니다. "
                "-i 경로를 주거나 images/origin.png 가 있어야 합니다."
            )
        staged = image_folder / f"00_input_{stem}.png"
        if not staged.is_file():
            raise FileNotFoundError(f"정규화된 입력이 없습니다: {staged}")
        if do_restore and restore_ok:
            t1 = time.perf_counter()
            res.restored = run_restorer(cfg, staged, p_restored,
                                        output_size=input_resolution)
            res.wall_restore_sec = time.perf_counter() - t1
            _log_stage_timing(backend_name, res.wall_restore_sec)
        elif do_restore and not restore_ok:
            _warn_restorer_missing(res, backend_name)

    res.wall_total_sec = time.perf_counter() - t0_all
    _log_stage_timing("파이프라인 전체", res.wall_total_sec)
    
    # Auto-upload to local DB and Supabase after pipeline completion
    try:
        from src.storage.local_db import LocalImageStorage
        from src.storage.supabase_storage import SupabaseImageStorage
        from src.config.config_manager import ConfigManager
        
        # Initialize local storage
        local_storage = LocalImageStorage()
        
        # Store original image in local DB
        if input_image is not None:
            original_path = image_folder / f"00_input_{stem}.png"
            if original_path.exists():
                local_storage.store_image(stem, "original", original_path)
                log.info(f"Original image stored in local DB: {stem}")
        
        # Store restored image in local DB
        if res.restored and res.restored.exists():
            local_storage.store_image(stem, "restored", res.restored)
            log.info(f"Restored image stored in local DB: {stem}")
        
        # Try to upload to Supabase if enabled and credentials are available
        try:
            config = ConfigManager()
            image_storage_config = config.get("image_storage", {}).get("supabase", {})
            
            if image_storage_config.get("enabled", False):
                supabase_storage = SupabaseImageStorage()
                
                # Upload original image to Supabase
                if input_image is not None:
                    original_path = image_folder / f"00_input_{stem}.png"
                    if original_path.exists():
                        supabase_storage.upload_image(stem, "original", original_path)
                        log.info(f"Original image uploaded to Supabase: {stem}")
                
                # Upload restored image to Supabase
                if res.restored and res.restored.exists():
                    supabase_storage.upload_image(stem, "restored", res.restored)
                    log.info(f"Restored image uploaded to Supabase: {stem}")
            else:
                log.info("Supabase image storage disabled, skipping upload")
                
        except Exception as e:
            log.warning(f"Failed to upload to Supabase: {e}")
            
    except Exception as e:
        log.warning(f"Failed to store images in local DB: {e}")
    
    return res


def _warn_restorer_missing(res: PipelineResult, backend_name: str) -> None:
    if backend_name == Restorer.CODEFORMER.value:
        hint = "git clone https://github.com/sczhou/CodeFormer"
        dir_hint = "CodeFormer"
    else:
        hint = "git clone https://github.com/wzhouxiff/RestoreFormerPlusPlus"
        dir_hint = "RestoreFormerPlusPlus"
    msg = (
        f"{backend_name} 경로 없음 - 복원 생략 "
        f"(프로젝트에 {dir_hint} 클론 필요: {hint})"
    )
    res.notes.append(msg)
    log.error("%s", msg)
    sys.exit(1)
