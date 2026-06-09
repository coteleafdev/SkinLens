# -*- coding: utf-8 -*-
"""
src.skin.analyzers.strategies.redness_analyzer — 홍조 분석기 전략

홍조·홍반 카테고리 분석.

분석 항목:
  redness_score                      : 홍조 (global z-score + local + tela)
  post_inflammatory_erythema_score   : 염증후 홍반 (PIE)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from src.skin.analyzers.base import BaseAnalyzer
from src.skin.core.scoring_utils import clamp, area_to_score

log = logging.getLogger(__name__)

# 헬퍼 함수는 scoring_utils에서 import
_clamp = clamp
_area_to_score = area_to_score


# ── 절대 기준 상수 ────────────────────────────────────────────────
NORMAL_A_REF:  float = 134.0   # 정상 동아시아 피부 a* LAB
LOCAL_A_FLOOR: float = 140.0   # 로컬 홍조 임계 최소값
PIE_A_FLOOR:   float = 142.0   # PIE 임계 최소값

_BP_REDNESS = [
    (0.000, 100), (0.015, 85), (0.050, 65), (0.100, 50),
    (0.150, 45),  (0.300, 25), (0.500, 0),
]
_BP_PIE = [
    (0.000, 100), (0.005, 85), (0.015, 65), (0.040, 45),
    (0.080, 25),  (0.150, 0),
]
_TELA_BP = [
    (0.000, 100), (0.006, 90), (0.015, 72), (0.028, 52),
    (0.045, 30),  (0.075, 8),  (0.100, 0),
]


class RednessAnalyzerV1(BaseAnalyzer):
    """홍조 분석기 v1 (현재 알고리즘).
    
    홍조 2항목 분석을 수행합니다.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """홍조 분석기 v1 초기화.
        
        Args:
            config: 분석기 설정
                - clahe_clip: CLAHE clip limit
                - clahe_tile: CLAHE tile grid size
                - bp_redness: 홍조 브레이크포인트
                - bp_pie: PIE 브레이크포인트
        """
        super().__init__(config)
    
    def analyze(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        **kwargs: Any,
    ) -> Dict[str, float]:
        """홍조 분석 수행.
        
        Args:
            face: 얼굴 영상 (BGR, uint8)
            skin_mask: 피부 마스크 (uint8, 0/255)
            regions: ROI 영역 딕셔너리
            **kwargs: 추가 파라미터
                - stat: 피부 통계 (필수)
        
        Returns:
            {"redness_score": float, "post_inflammatory_erythema_score": float}
        """
        self.validate_input(face, skin_mask, regions)
        
        stat = kwargs.get("stat")
        if stat is None:
            raise ValueError("stat 파라미터가 필요합니다.")
        
        # 설정에서 파라미터 로드
        clahe_clip = self.get_config("clahe_clip", 2.0)
        clahe_tile = self.get_config("clahe_tile", (8, 8))
        bp_redness = self.get_config("bp_redness")
        bp_pie = self.get_config("bp_pie")
        
        # 알고리즘 수행
        return self._analyze_redness(
            face=face,
            skin_mask=skin_mask,
            regions=regions,
            stat=stat,
            clahe_clip=clahe_clip,
            clahe_tile=clahe_tile,
            bp_redness=bp_redness,
            bp_pie=bp_pie,
        )
    
    def _analyze_redness(
        self,
        face: np.ndarray,
        skin_mask: np.ndarray,
        regions: Dict[str, np.ndarray],
        stat: Dict[str, float],
        *,
        clahe_clip: float = 2.0,
        clahe_tile: tuple = (8, 8),
        bp_redness: Optional[list] = None,
        bp_pie: Optional[list] = None,
    ) -> Dict[str, float]:
        """홍조 2항목 분석.

        Args:
            face:       얼굴 BGR 이미지
            skin_mask:  피부 마스크
            regions:    {"left_cheek": ..., "right_cheek": ...} 등
            stat:       _skin_stat() 결과 (red_base_a, red_std_a 포함)
            clahe_clip: CLAHE clip limit
            clahe_tile: CLAHE tile grid size
            bp_*:       항목별 브레이크포인트

        Returns:
            {"redness_score": float, "post_inflammatory_erythema_score": float}
        """
        bp_redness = bp_redness or _BP_REDNESS
        bp_pie     = bp_pie     or _BP_PIE

        lab    = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
        a_ch   = lab[:, :, 1].astype(float)
        sk     = skin_mask > 0
        base_a = stat["base_a"]
        std_a  = stat["std_a"]
        kernel3 = np.ones((3, 3), np.uint8)
        skin_px = max(int(np.count_nonzero(sk)), 1)
        fh, fw  = face.shape[:2]

        # cheek 전용 red_base_a / red_std_a
        if "red_base_a" in stat and "red_std_a" in stat:
            red_base_a = float(stat["red_base_a"])
            red_std_a  = float(stat["red_std_a"])
        else:
            cheek_smask = skin_mask.copy()
            cheek_smask[:int(fh * 0.40), :] = 0
            cheek_smask[int(fh * 0.75):, :] = 0
            cheek_smask[:, int(fw * 0.35):int(fw * 0.65)] = 0
            ck = cheek_smask > 0
            if ck.any() and int(np.count_nonzero(ck)) >= 200:
                red_base_a = float(np.median(a_ch[ck]))
                red_std_a  = max(float(np.std(a_ch[ck])), 2.0)
            else:
                red_base_a = base_a
                red_std_a  = max(std_a, 2.0)

        # ── (1) redness_score ────────────────────────────────────────
        # [FIX 2026-05-24] 조명 의존 절대 기준치 문제 수정 - 상대 기준 우선
        # stat["base_a"] 기반 상대 기준 우선, NORMAL_A_REF는 하한 클리핑 용도로만 사용
        mean_a_skin  = float(np.mean(a_ch[sk])) if sk.any() else base_a
        # base_a(상대 기준)를 우선하고, NORMAL_A_REF를 하한 클리핑 용도로만 사용
        ref_a = max(base_a, NORMAL_A_REF)
        global_score = _clamp(100.0 - max(0.0, mean_a_skin - ref_a) * 4.0)

        red_thresh = max(red_base_a + 1.5 * red_std_a, LOCAL_A_FLOOR)
        local_mask = ((a_ch > red_thresh) & sk).astype(np.uint8) * 255
        local_mask = cv2.morphologyEx(local_mask, cv2.MORPH_OPEN, kernel3)
        local_ratio = np.count_nonzero(local_mask) / skin_px
        local_score = _area_to_score(local_ratio, bp_redness)

        # telangiectasia (Canny 혈관 감지)
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=clahe_tile)
        vessel_edges_list: List[np.ndarray] = []
        vessel_mask_px = 0
        kernel_thin = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 7))
        for reg_key in ("left_cheek", "right_cheek"):
            reg = regions.get(reg_key, np.zeros((10, 10, 3), np.uint8))
            if min(reg.shape[:2]) < 10:
                continue
            r_ch  = clahe.apply(reg[:, :, 2])
            edges = cv2.Canny(r_ch, 40, 120)
            thin  = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel_thin)
            vessel_edges_list.append(thin)
            vessel_mask_px += reg.shape[0] * reg.shape[1]

        if vessel_edges_list and vessel_mask_px > 0:
            vessel_density = sum(np.count_nonzero(e) for e in vessel_edges_list) / vessel_mask_px
        else:
            r_enh = clahe.apply(face[:, :, 2].astype(np.uint8))
            cheek_mask_v = np.zeros(face.shape[:2], dtype=np.uint8)
            cv2.rectangle(cheek_mask_v, (0, int(fh * 0.35)), (int(fw * 0.38), int(fh * 0.78)), 255, -1)
            cv2.rectangle(cheek_mask_v, (int(fw * 0.62), int(fh * 0.35)), (fw, int(fh * 0.78)), 255, -1)
            vessel_roi  = cv2.bitwise_and(r_enh, r_enh, mask=cheek_mask_v)
            edges_v     = cv2.Canny(vessel_roi, 40, 120)
            thin_edges  = cv2.morphologyEx(edges_v, cv2.MORPH_OPEN, kernel_thin)
            vessel_density = np.count_nonzero(thin_edges) / max(np.count_nonzero(cheek_mask_v), 1)

        tela_score    = _area_to_score(vessel_density, _TELA_BP)
        # 개선 (2026-05-22): telangiectasia 가중치 상향 (0.10 → 0.15)
        #   - 혈관성 홍조(모세혈관 확장) 중요도 반영
        redness_score = 0.40 * local_score + 0.45 * global_score + 0.15 * tela_score

        # ── (2) post_inflammatory_erythema_score ─────────────────────
        intense_thresh = max(base_a + 1.8 * std_a, PIE_A_FLOOR)
        intense_mask   = ((a_ch > intense_thresh) & sk).astype(np.uint8) * 255
        intense_mask   = cv2.morphologyEx(intense_mask, cv2.MORPH_OPEN, kernel3)
        intense_ratio  = np.count_nonzero(intense_mask) / skin_px
        if int(np.count_nonzero(intense_mask)) >= 50:
            intense_mean = float(np.mean(a_ch[intense_mask > 0]))
            intensity_penalty = min(max(0.0, intense_mean - NORMAL_A_REF - 8.0) * 1.5, 20.0)
        else:
            intensity_penalty = 0.0
        pie_score = _clamp(
            0.55 * _area_to_score(intense_ratio, bp_pie)
            + 0.45 * _clamp(100.0 - intensity_penalty)
        )

        return {
            "redness_score":                   round(_clamp(redness_score), 1),
            "post_inflammatory_erythema_score": round(_clamp(pie_score),    1),
        }
    
    @property
    def name(self) -> str:
        """분석기 이름."""
        return "redness_v1"
    
    @property
    def version(self) -> str:
        """알고리즘 버전."""
        return "1.0.0"


# 하위 호환성을 위한 별칭 함수
def analyze_redness(
    face: np.ndarray,
    skin_mask: np.ndarray,
    regions: Dict[str, np.ndarray],
    stat: Dict[str, float],
    *,
    clahe_clip: float = 2.0,
    clahe_tile: tuple = (8, 8),
    bp_redness: Optional[list] = None,
    bp_pie: Optional[list] = None,
) -> Dict[str, float]:
    """홍조 2항목 분석 (하위 호환성을 위한 별칭 함수).

    Args:
        face:       얼굴 BGR 이미지
        skin_mask:  피부 마스크
        regions:    {"left_cheek": ..., "right_cheek": ...} 등
        stat:       _skin_stat() 결과 (red_base_a, red_std_a 포함)
        clahe_clip: CLAHE clip limit
        clahe_tile: CLAHE tile grid size
        bp_*:       항목별 브레이크포인트

    Returns:
        {"redness_score": float, "post_inflammatory_erythema_score": float}
    """
    analyzer = RednessAnalyzerV1()
    return analyzer._analyze_redness(
        face=face,
        skin_mask=skin_mask,
        regions=regions,
        stat=stat,
        clahe_clip=clahe_clip,
        clahe_tile=clahe_tile,
        bp_redness=bp_redness,
        bp_pie=bp_pie,
    )

