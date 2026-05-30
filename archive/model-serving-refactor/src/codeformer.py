"""
CodeFormer In-Process Wrapper

This module provides in-process execution for CodeFormer model
to eliminate subprocess overhead.

[PROJECT] In-Process Model Serving
[PHASE] Phase 1: Single Model In-Process Test (CodeFormer focus)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch

log = logging.getLogger(__name__)


class CodeFormer:
    """CodeFormer model wrapper for in-process execution."""
    
    def __init__(
        self,
        repo_path: Optional[Path] = None,
        device: Optional[str] = None,
    ):
        """Initialize CodeFormer model.
        
        Args:
            repo_path: Path to CodeFormer repository.
            device: Device to run on ('cuda', 'cpu', or None for auto).
        """
        self.repo_path = repo_path or self._find_repo_path()
        self.device = self._select_device(device)
        self.model = None
        self._loaded = False
        
        log.info(f"CodeFormer wrapper initialized (device: {self.device})")
    
    def _find_repo_path(self) -> Path:
        """Find CodeFormer repository path."""
        # Default: models/CodeFormer relative to project root
        project_root = Path(__file__).resolve().parents[3]  # model-serving-refactor/... → project root
        default_path = project_root / "models" / "CodeFormer"
        
        if default_path.exists():
            return default_path
        
        # Fallback: try relative to src
        alt_path = Path(__file__).resolve().parents[4] / "models" / "CodeFormer"
        if alt_path.exists():
            return alt_path
        
        raise FileNotFoundError(
            f"CodeFormer repository not found. Tried: {default_path}, {alt_path}"
        )
    
    def _select_device(self, device: Optional[str]) -> str:
        """Select device for model execution."""
        if device is not None:
            return device
        
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"
    
    def load(
        self,
        fidelity: float = 0.5,
        upscale: int = 2,
        bg_upsampler: str = "realesrgan",
        detection_model: str = "retinaface_resnet50",
    ) -> None:
        """Load CodeFormer model.
        
        Args:
            fidelity: Fidelity weight for face restoration (0.0-1.0).
            upscale: Upscaling factor (1, 2, 4).
            bg_upsampler: Background upsampler ('realesrgan' or None).
            detection_model: Face detection model.
        
        This method loads the model weights and prepares it for inference.
        The model is loaded once and reused for multiple inferences.
        """
        if self._loaded:
            log.debug("CodeFormer already loaded")
            return
        
        log.info("Loading CodeFormer model...")
        
        try:
            # Add CodeFormer repository to path for facelib import
            import sys
            if str(self.repo_path) not in sys.path:
                sys.path.insert(0, str(self.repo_path))
            
            # Import CodeFormer dependencies
            from basicsr.utils.registry import ARCH_REGISTRY
            from basicsr.utils.download_util import load_file_from_url
            from facelib.utils.face_restoration_helper import FaceRestoreHelper
            from basicsr.utils.misc import get_device
            
            # Store parameters
            self.fidelity = fidelity
            self.upscale = upscale
            self.bg_upsampler_name = bg_upsampler
            self.detection_model = detection_model
            
            # Load CodeFormer model
            # Architecture: dim_embd=512, codebook_size=1024, n_head=8, n_layers=9
            self.model = ARCH_REGISTRY.get('CodeFormer')(
                dim_embd=512,
                codebook_size=1024,
                n_head=8,
                n_layers=9,
                connect_list=['32', '64', '128', '256']
            ).to(self.device)
            
            # Download/load checkpoint
            pretrain_model_url = 'https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth'
            ckpt_path = load_file_from_url(
                url=pretrain_model_url,
                model_dir=str(self.repo_path / "weights" / "CodeFormer"),
                progress=True,
                file_name=None
            )
            
            # Load state dict
            checkpoint = torch.load(ckpt_path, map_location=self.device)['params_ema']
            self.model.load_state_dict(checkpoint)
            self.model.eval()
            
            # Initialize FaceRestoreHelper
            self.face_helper = FaceRestoreHelper(
                upscale,
                face_size=512,
                crop_ratio=(1, 1),
                det_model=detection_model,
                save_ext='png',
                use_parse=True,
                device=self.device
            )
            
            # Load background upsampler if needed
            self.bg_upsampler = None
            if bg_upsampler == "realesrgan":
                self.bg_upsampler = self._load_realesrgan()
            
            self._loaded = True
            log.info("CodeFormer model loaded successfully")
            
        except Exception as e:
            log.error(f"Failed to load CodeFormer: {e}")
            raise
    
    def _load_realesrgan(self):
        """Load RealESRGAN for background upsampling."""
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from basicsr.utils.realesrgan_utils import RealESRGANer
        
        use_half = False
        if torch.cuda.is_available():
            no_half_gpu_list = ['1650', '1660']
            if not any(gpu in torch.cuda.get_device_name(0) for gpu in no_half_gpu_list):
                use_half = True
        
        model = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=2,
        )
        
        upsampler = RealESRGANer(
            scale=2,
            model_path="https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/RealESRGAN_x2plus.pth",
            model=model,
            tile=400,
            tile_pad=40,
            pre_pad=0,
            half=use_half
        )
        
        return upsampler
    
    def __call__(
        self,
        input_path: Path,
        output_path: Path,
        fidelity: float = 0.5,
        upscale: int = 2,
        bg_upsampler: str = "realesrgan",
        has_aligned: bool = False,
        only_center_face: bool = False,
        draw_box: bool = False,
    ) -> Path:
        """Run CodeFormer inference on an image.
        
        Args:
            input_path: Path to input image.
            output_path: Path to save output image.
            fidelity: Fidelity weight (0.0-1.0).
            upscale: Upscaling factor.
            bg_upsampler: Background upsampler.
            has_aligned: Input faces are already cropped and aligned.
            only_center_face: Only restore the center face.
            draw_box: Draw bounding box for detected faces.
        
        Returns:
            Path to output image.
        
        Raises:
            RuntimeError: If model not loaded or inference fails.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        log.info(f"Running CodeFormer inference: {input_path} → {output_path}")
        log.info(f"  Fidelity: {fidelity}, Upscale: {upscale}, BG Upsampler: {bg_upsampler}")
        
        try:
            from basicsr.utils import img2tensor, tensor2img
            from torchvision.transforms.functional import normalize
            from facelib.utils.misc import is_gray
            from basicsr.utils import imwrite
            
            # Clean intermediate results
            self.face_helper.clean_all()
            
            # Read input image
            # Handle Unicode paths on Windows
            import numpy as np
            from PIL import Image
            
            # Use PIL to handle Unicode paths, then convert to OpenCV format
            try:
                pil_img = Image.open(str(input_path))
                pil_img = pil_img.convert('RGB')
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception as e:
                # Fallback to cv2.imread
                img = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
                if img is None:
                    raise ValueError(f"Failed to read image: {input_path}")
            
            # Process faces
            if has_aligned:
                # Input faces are already cropped and aligned
                img = cv2.resize(img, (512, 512), interpolation=cv2.INTER_LINEAR)
                self.face_helper.is_gray = is_gray(img, threshold=10)
                if self.face_helper.is_gray:
                    log.warning("Grayscale input detected")
                self.face_helper.cropped_faces = [img]
            else:
                # Detect faces
                self.face_helper.read_image(img)
                num_det_faces = self.face_helper.get_face_landmarks_5(
                    only_center_face=only_center_face,
                    resize=640,
                    eye_dist_threshold=5
                )
                log.info(f"Detected {num_det_faces} faces")
                
                # Align and warp faces
                self.face_helper.align_warp_face()
            
            # Restore each face
            for idx, cropped_face in enumerate(self.face_helper.cropped_faces):
                # Preprocess
                cropped_face_t = img2tensor(cropped_face / 255., bgr2rgb=True, float32=True)
                normalize(cropped_face_t, (0.5, 0.5, 0.5), (0.5, 0.5, 0.5), inplace=True)
                cropped_face_t = cropped_face_t.unsqueeze(0).to(self.device)
                
                # Inference
                try:
                    with torch.no_grad():
                        output = self.model(cropped_face_t, w=fidelity, adain=True)[0]
                        restored_face = tensor2img(output, rgb2bgr=True, min_max=(-1, 1))
                    del output
                    if self.device == "cuda":
                        torch.cuda.empty_cache()
                except Exception as error:
                    log.error(f"Failed inference for CodeFormer: {error}")
                    restored_face = tensor2img(cropped_face_t, rgb2bgr=True, min_max=(-1, 1))
                
                restored_face = restored_face.astype('uint8')
                self.face_helper.add_restored_face(restored_face, cropped_face)
            
            # Paste back to input image
            if not has_aligned:
                # Upscale background if needed
                bg_img = None
                if self.bg_upsampler is not None:
                    bg_img = self.bg_upsampler.enhance(img, outscale=upscale)[0]
                
                self.face_helper.get_inverse_affine(None)
                restored_img = self.face_helper.paste_faces_to_input_image(
                    upsample_img=bg_img,
                    draw_box=draw_box
                )
            else:
                restored_img = self.face_helper.restored_faces[0]
            
            # Save output
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            imwrite(restored_img, str(output_path))
            
            log.info(f"CodeFormer inference complete: {output_path}")
            return output_path
            
        except Exception as e:
            log.error(f"CodeFormer inference failed: {e}")
            raise RuntimeError(f"Inference failed: {e}") from e
    
    def unload(self) -> None:
        """Unload model to free GPU memory."""
        if self.model is not None:
            del self.model
            if self.device == "cuda":
                torch.cuda.empty_cache()
            self._loaded = False
            log.info("CodeFormer model unloaded")


def restore_image_in_process(
    input_path: Path,
    output_path: Path,
    repo_path: Optional[Path] = None,
    device: Optional[str] = None,
    fidelity: float = 0.5,
    upscale: int = 2,
    bg_upsampler: str = "realesrgan",
    has_aligned: bool = False,
    only_center_face: bool = False,
    draw_box: bool = False,
) -> Path:
    """Convenience function to restore an image in-process with CodeFormer.
    
    This function handles model loading and inference in a single call.
    For repeated use, instantiate CodeFormer directly.
    
    Args:
        input_path: Path to input image.
        output_path: Path to save output image.
        repo_path: Path to CodeFormer repository.
        device: Device to run on.
        fidelity: Fidelity weight.
        upscale: Upscaling factor.
        bg_upsampler: Background upsampler.
        has_aligned: Input faces are already cropped and aligned.
        only_center_face: Only restore the center face.
        draw_box: Draw bounding box for detected faces.
    
    Returns:
        Path to output image.
    """
    model = CodeFormer(repo_path=repo_path, device=device)
    model.load(fidelity=fidelity, upscale=upscale, bg_upsampler=bg_upsampler)
    return model(
        input_path, output_path,
        fidelity=fidelity, upscale=upscale, bg_upsampler=bg_upsampler,
        has_aligned=has_aligned, only_center_face=only_center_face, draw_box=draw_box
    )
