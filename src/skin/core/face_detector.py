"""
skin.core.face_detector
=======================
얼굴 검출기 모듈 — MediaPipe tasks API + Haar Cascade 이중 백엔드.

[REFACTOR P3] skin_scoring.py 에서 분리.
  _MediaPipeFaceDetector, _HaarFaceDetector, FaceDetector
  _try_import_mediapipe

하위 호환:
  skin_scoring 에서 "from skin.core.face_detector import FaceDetector" 로 재노출.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None

import numpy as np

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  얼굴 검출기
# ──────────────────────────────────────────────────────────────

def _try_import_mediapipe() -> Optional[Any]:
    """MediaPipe tasks API 사용 가능 여부를 런타임에 확인.

    [ML v4.0] MediaPipe 0.10.x tasks API 기반 얼굴 검출기.
    tasks API는 .task 모델 파일이 필요하므로, 파일 존재 여부와
    임포트 성공 여부를 모두 확인한다.
    실패 시 None을 반환해 Haar Cascade 폴백을 유도한다.
    """
    try:
        from mediapipe.tasks.python import vision as mp_vision
        from mediapipe.tasks.python.core.base_options_c import BaseOptions
        return (mp_vision, BaseOptions)
    except Exception:
        return None


class _MediaPipeFaceDetector:
    """MediaPipe tasks FaceDetector 래퍼.

    [ML v4.0] MediaPipe 0.10.x tasks API 기반 고정밀 얼굴 검출기.
    Haar Cascade 대비 어두운 피부·측면·저조도 환경에서 검출률이 높다.

    model_path: .tflite 모델 파일 경로.
        배포 패키지에 포함하거나 download_model()로 자동 다운로드.
        (예: blaze_face_short_range.tflite)
    """

    # 기본 모델 파일명 후보 (프로젝트 루트 또는 config/ 에 배치)
    _DEFAULT_MODEL_NAMES = [
        "blaze_face_short_range.tflite",
        "face_detector.tflite",
        "config/blaze_face_short_range.tflite",
        "config/face_detector.tflite",
    ]

    # 공식 다운로드 URL (float16, 버전 1)
    MODEL_DOWNLOAD_URL = (
        "https://storage.googleapis.com/mediapipe-models/"
        "face_detector/blaze_face_short_range/float16/1/"
        "blaze_face_short_range.tflite"
    )
    MODEL_SAVE_NAME = "blaze_face_short_range.tflite"

    def __init__(self, model_path: Optional[str] = None) -> None:
        from mediapipe.tasks.python import vision as mp_vision
        from mediapipe.tasks.python.core.base_options_c import BaseOptions

        resolved = self._resolve_model(model_path)
        if resolved is None:
            raise FileNotFoundError(
                "MediaPipe 모델 파일을 찾을 수 없습니다.\n"
                "아래 명령으로 다운로드 후 프로젝트 루트에 저장하세요:\n\n"
                f"  wget -O blaze_face_short_range.tflite \\\n"
                f"    {_MediaPipeFaceDetector.MODEL_DOWNLOAD_URL}\n\n"
                "또는 Python에서:\n"
                "  from skin_scoring import _MediaPipeFaceDetector\n"
                "  _MediaPipeFaceDetector.download_model()\n"
            )
        opts = mp_vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(resolved)),
            min_detection_confidence=0.40,
            min_suppression_threshold=0.30,
        )
        self._detector = mp_vision.FaceDetector.create_from_options(opts)
        log.info("[ML v4.0] MediaPipe FaceDetector 초기화 완료: %s", resolved)

    @classmethod
    def download_model(
        cls,
        dest: Optional[str | Path] = None,
        force: bool = False,
    ) -> Path:
        """공식 URL에서 모델 파일을 다운로드합니다.

        Args:
            dest: 저장 경로. None이면 프로젝트 루트에 blaze_face_short_range.tflite 로 저장.
            force: True면 이미 파일이 있어도 재다운로드.

        Returns:
            저장된 파일 경로.

        Example::
            from skin_scoring import _MediaPipeFaceDetector
            _MediaPipeFaceDetector.download_model()
        """
        import urllib.request

        save_path = Path(dest) if dest else Path(__file__).parent / cls.MODEL_SAVE_NAME

        if save_path.exists() and not force:
            log.info("모델 파일 이미 존재: %s (force=True로 재다운로드 가능)", save_path)
            return save_path

        log.info("MediaPipe 모델 다운로드 중: %s", cls.MODEL_DOWNLOAD_URL)
        print(f"[다운로드] {cls.MODEL_DOWNLOAD_URL}\n    → {save_path}")

        def _progress(block_num: int, block_size: int, total_size: int) -> None:
            if total_size > 0:
                pct = min(block_num * block_size / total_size * 100, 100)
                print(f"\r    진행: {pct:.1f}%", end="", flush=True)

        save_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(cls.MODEL_DOWNLOAD_URL, str(save_path), _progress)
        print(f"\n    완료: {save_path.stat().st_size // 1024} KB")
        return save_path

    @classmethod
    def _resolve_model(cls, model_path: Optional[str]) -> Optional[Path]:
        """모델 파일 경로 탐색."""
        candidates = []
        if model_path:
            candidates.append(Path(model_path))
        # 스크립트 위치 기준 탐색
        base = Path(__file__).parent
        candidates.extend(base / n for n in cls._DEFAULT_MODEL_NAMES)
        for p in candidates:
            if p.is_file():
                return p
        return None

    def detect_face(
        self, image: np.ndarray, debug: bool = False
    ) -> Optional[Tuple[int, int, int, int]]:
        """BGR 이미지에서 얼굴 bbox (x, y, w, h) 반환."""
        if not CV2_AVAILABLE:
            raise ImportError("cv2가 설치되지 않았습니다")
        import mediapipe as mp
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(mp_img)
        if not result.detections:
            return None
        best = max(result.detections, key=lambda d: (
            d.bounding_box.width * d.bounding_box.height
        ))
        bb = best.bounding_box
        x, y = max(0, bb.origin_x), max(0, bb.origin_y)
        w, h = bb.width, bb.height
        if debug:
            log.debug("[MP] 검출 bbox x=%d y=%d w=%d h=%d", x, y, w, h)
        return (x, y, w, h)

    def close(self) -> None:
        try:
            self._detector.close()
        except Exception as e:
            log.debug("detector close 실패: %s", e)


class _HaarFaceDetector:
    """Haar Cascade 얼굴 검출기 (폴백용).

    [ML v4.0] MediaPipe 미사용 환경 또는 모델 파일 없을 때의 폴백.
    루프 수를 3×4×7=84회 → 1×4×5=20회로 축소해 타임아웃 위험 감소.
    """

    def __init__(self) -> None:
        if not CV2_AVAILABLE:
            raise ImportError("cv2가 설치되지 않았습니다")
        self.detectors: List = []
        for name in [
            "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt2.xml",
            "haarcascade_profileface.xml",
        ]:
            try:
                clf = cv2.CascadeClassifier(cv2.data.haarcascades + name)
                if not clf.empty():
                    self.detectors.append((name.replace(".xml", ""), clf))
            except Exception as e:
                log.debug("haarcascade 로드 실패: %s", e)
        if not self.detectors:
            raise RuntimeError("사용 가능한 얼굴 검출기가 없습니다")
        log.info("[Haar] %d개 검출기 초기화", len(self.detectors))

    def detect_face(
        self, image: np.ndarray, debug: bool = False
    ) -> Optional[Tuple[int, int, int, int]]:
        if not CV2_AVAILABLE:
            raise ImportError("cv2가 설치되지 않았습니다")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        preps = [
            ("원본",        gray),
            ("히스토그램",   cv2.equalizeHist(gray)),
            ("밝기+",       cv2.convertScaleAbs(gray, alpha=1.2, beta=30)),
            ("밝기-",       cv2.convertScaleAbs(gray, alpha=0.8, beta=-30)),
        ]
        # [ML v4.0] 84회 → 20회 축소: 가장 검출률 높은 config만 유지
        configs = [
            (1.05, 3, (30, 30)),
            (1.1,  3, (30, 30)),
            (1.2,  3, (20, 20)),
            (1.1,  2, (20, 20)),
            (1.3,  2, (20, 20)),
        ]
        for det_name, det in self.detectors:
            for prep_name, prep_img in preps:
                for scale, neighbors, min_size in configs:
                    try:
                        faces = det.detectMultiScale(
                            prep_img, scaleFactor=scale,
                            minNeighbors=neighbors, minSize=min_size,
                            flags=cv2.CASCADE_SCALE_IMAGE,
                        )
                        if len(faces) > 0:
                            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                            if debug:
                                log.debug(
                                    "[Haar] 검출 [%s][%s] x=%d y=%d w=%d h=%d",
                                    det_name, prep_name, x, y, w, h,
                                )
                            return (x, y, w, h)
                    except Exception:
                        continue
        return None


class FaceDetector:
    """얼굴 검출기 — MediaPipe 우선, Haar Cascade 폴백.

    [ML v4.0] 검출 백엔드를 자동 선택:
      1순위: MediaPipe tasks FaceDetector (blaze_face_short_range.tflite 필요)
             어두운 피부·측면·저조도에서 Haar 대비 검출률 크게 향상.
             모델 파일 다운로드: _MediaPipeFaceDetector.download_model()
      2순위: Haar Cascade (추가 파일 불필요, 현재와 동일한 폴백 동작)

    사용법:
        det = FaceDetector()                          # 자동 선택
        det = FaceDetector(backend="mediapipe")       # MediaPipe 강제
        det = FaceDetector(backend="haar")            # Haar 강제
        det = FaceDetector(mediapipe_model_path="blaze_face_short_range.tflite")
    """

    def __init__(
        self,
        backend: str = "auto",
        mediapipe_model_path: Optional[str] = None,
    ) -> None:
        self._backend_name = "unknown"
        self._impl: Any = None

        use_mp = backend in ("auto", "mediapipe")
        use_haar_only = backend == "haar"

        if use_mp and not use_haar_only:
            mp_api = _try_import_mediapipe()
            if mp_api is not None:
                try:
                    self._impl = _MediaPipeFaceDetector(mediapipe_model_path)
                    self._backend_name = "mediapipe"
                    return
                except FileNotFoundError as e:
                    if backend == "mediapipe":
                        raise
                    log.info("[ML v4.0] %s → Haar Cascade 폴백", e)
                except Exception as e:
                    if backend == "mediapipe":
                        raise
                    log.warning("[ML v4.0] MediaPipe 초기화 실패 (%s) → Haar 폴백", e)

        # Haar 폴백
        self._impl = _HaarFaceDetector()
        self._backend_name = "haar"

    @property
    def backend(self) -> str:
        """현재 사용 중인 백엔드 이름."""
        return self._backend_name

    def detect_face(
        self, image: np.ndarray, debug: bool = False
    ) -> Optional[Tuple[int, int, int, int]]:
        """얼굴 bbox (x, y, w, h) 반환. 검출 실패 시 None."""
        return self._impl.detect_face(image, debug=debug)
