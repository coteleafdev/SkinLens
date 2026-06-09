"""src.config — 통합 설정 및 ROI 관리 패키지.

[REFACTOR P1] 설정 로직 중앙화 및 ROI 관리 중앙화:
  - ConfigManager: 통합 설정 관리 (config.json, 프롬프트 템플릿)
  - ROIManager: ROI 관리 (FaceROI 래핑, ROI 추출)

사용법:
    from src.config import ConfigManager, ROIManager

    # 설정 관리
    config = ConfigManager.get_instance()
    weights = config.get_measurement_weights()

    # ROI 관리
    roi = ROIManager.get_instance()
    forehead = roi.get_forehead_roi(face)
"""
from src.config.config_manager import ConfigManager, get_config_manager
from src.config.roi_manager import ROIManager, get_roi_manager

__all__ = [
    "ConfigManager",
    "get_config_manager",
    "ROIManager",
    "get_roi_manager",
]
