"""
skin.core.score_constants
=========================
피부 점수 캘리브레이션 상수.

[REFACTOR P2] 함수 내부 상수를 별도 모듈로 추출하여 점수 조정을 코드 수정 없이 가능하게 함.
"""
from __future__ import annotations


class RednessConst:
    """홍조(redness) 캘리브레이션 상수."""
    
    # 정상 동아시아 피부 a* ≈ +4~8 → LAB 132~136, 중간값 134 사용
    NORMAL_A_REF: float = 134.0
    
    # local 임계 절대 하한: a* > 12 (LAB 140) 이상은 반드시 홍조로 탐지
    LOCAL_A_FLOOR: float = 140.0
    
    # PIE 임계 절대 하한: a* > 14 (LAB 142) 이상은 반드시 홍반으로 탐지
    PIE_A_FLOOR: float = 142.0


class MelasmaConst:
    """기미(melasma) 캘리브레이션 상수."""
    
    # 절대 b 임계: 기미 픽셀의 b* 절대 하한
    B_MEL_ABS: float = 149.0
    
    # 절대 a 임계: 기미 픽셀의 a* 절대 하한
    A_MEL_ABS: float = 143.0
