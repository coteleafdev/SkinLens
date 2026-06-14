"""tests/cv_scoring/synth_faces.py — CV 점수 검증용 합성 얼굴 생성기 + 입력 빌더.

실제 사람 얼굴 사진 없이 "정답(ground truth)을 아는" 입력을 절차적으로 생성한다.
각 결함을 정해진 강도로 주입하므로 단조성/결정론/범위/독립성을 자동 검증할 수 있다.

설계 원칙
--------
- 모든 생성은 ``seed`` 로 완전 결정론(동일 seed → 동일 픽셀).
- 결함 강도는 단일 스칼라(severity/count)로 제어 → 단조성 테스트에 직접 사용.
- 한 종류의 결함만 주입 → "측정 독립성"(타 항목 불변) 검증에 사용.

검출기 보정 메모 (실측 기반)
--------------------------
- freckle: blob_log(sigma 1~5, thr 0.08) 로 검출 후 lentigo(sigma 3~14) 중심과
  겹치면 제외된다. 따라서 freckle 을 트리거하려면 **반경 2px**(특성 sigma≈1.4,
  lentigo 하한 3 미만) + **darken 45**(thr 0.08 및 L*−10 동시 통과) 가 최적이다.
  반경을 키우거나 darken 을 60+ 로 올리면 lentigo 로 흡수되어 freckle 카운트에서 빠진다.
- redness/PIE: a* 를 너무 올리면(severity≳0.8) 픽셀이 피부 마스크 범위를 벗어나
  오히려 검출이 줄어든다. severity ≤ 0.6 구간에서 단조롭다.

분석기 dtype 계약
----------------
분석기는 피부 마스크를 **bool** 로 받기를 기대한다(strip_normalize_L 등이
boolean 인덱싱 사용). ``io_full()`` 이 변환을 처리한다.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import cv2

_DEFAULT_SKIN_BGR: Tuple[int, int, int] = (150, 180, 210)  # Fitzpatrick III 근처


# ── 기본 캔버스 ──────────────────────────────────────────────────────
def make_skin_canvas(h: int = 420, w: int = 420,
                     bgr: Tuple[int, int, int] = _DEFAULT_SKIN_BGR,
                     micro_texture: float = 3.0, seed: int = 0) -> np.ndarray:
    """결함 없는 균일 피부 캔버스(+피부 유사 저주파 미세 질감).

    [중요] 질감 노이즈는 약하게 blur 하여 '저주파'로 만든다. 픽셀 단위 백색잡음은
    고역통과 필터(Laplacian/LBP)를 크게 부풀려 pore_sagging·roughness 같은 텍스처
    지표의 깨끗한-얼굴 baseline 을 비현실적으로 낮춘다. 실제 피부 질감은 저주파이므로
    blur 로 근사한다(이 보정 전 clean pore_sagging≈30 → 보정 후 ≈73).
    """
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), bgr, np.uint8).astype(float)
    noise = rng.normal(0.0, micro_texture, (h, w, 3))
    noise = cv2.GaussianBlur(noise, (3, 3), 0)   # 저주파화 (피부 유사)
    return np.clip(img + noise, 0, 255).astype(np.uint8)


# ── 결함 주입기 (검증됨) ─────────────────────────────────────────────
def inject_dark_blobs(img: np.ndarray, count: int, *,
                      radius: int = 2, darken: int = 45, seed: int = 0) -> np.ndarray:
    """어두운 소형 blob 주입 — freckle 검출기에 맞춰 보정(r=2, darken=45). 색소 계열."""
    rng = np.random.default_rng(seed + 1000)
    out = img.copy(); h, w = out.shape[:2]
    for _ in range(count):
        cx, cy = int(rng.integers(70, w - 70)), int(rng.integers(70, h - 70))
        c = out[cy, cx].astype(int)
        cv2.circle(out, (cx, cy), radius, tuple(int(max(0, v - darken)) for v in c), -1)
    return cv2.GaussianBlur(out, (3, 3), 0)


def inject_melasma(img: np.ndarray, severity: float) -> np.ndarray:
    """결정론적 비중첩 그리드의 큰 소프트 패치로 L*↓ — 면적형 색소(melasma). sev 0~1.

    melasma 는 면적 기반이라 freckle 용 소형 blob(r=2)으로는 움직이지 않는다.
    프로덕션 면적 브레이크포인트에서 단조롭도록 큰 패치(r≈26)를 사용한다.
    """
    out = img.copy(); h, w = out.shape[:2]
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB).astype(float)
    n = int(round(float(severity) * 9)); cols, rad, ldrop = 3, 26, 24.0
    for i in range(n):
        r_i, c_i = divmod(i, cols)
        cx, cy = int(w * (0.25 + 0.25 * c_i)), int(h * (0.42 + 0.12 * r_i))
        m = np.zeros((h, w), np.float32)
        cv2.circle(m, (cx, cy), rad, 1.0, -1)
        m = cv2.GaussianBlur(m, (21, 21), 0)
        lab[:, :, 0] -= m * ldrop          # L*↓ (어두워짐)
        lab[:, :, 1] += m * 7.0            # a*↑ (적갈색) — 실제 melasma 는 유채색
        lab[:, :, 2] += m * 9.0            # b*↑ (황갈색)
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def inject_redness(img: np.ndarray, severity: float, *, seed: int = 0) -> np.ndarray:
    """볼 영역 a*(적색) 상승 — redness/PIE. severity ≤ 0.6 권장.

    [2026-06-10] 경계를 blur 로 부드럽게(soft-edged) 한다. 실제 diffuse 홍조는 경계가
    매끄럽고, 딱딱한 사각 경계는 PIE focal 잔여 검출을 인위적으로 자극하기 때문이다.
    """
    out = img.copy(); h, w = out.shape[:2]
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB).astype(float)
    cheek = np.zeros((h, w), np.float32)
    cheek[int(h * 0.40):int(h * 0.75), :int(w * 0.35)] = 1.0
    cheek[int(h * 0.40):int(h * 0.75), int(w * 0.65):] = 1.0
    cheek = cv2.GaussianBlur(cheek, (0, 0), sigmaX=18)   # soft-edged diffuse
    lab[:, :, 1] += 25.0 * float(severity) * cheek
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def inject_pie_focal(img: np.ndarray, severity: float, *, seed: int = 77) -> np.ndarray:
    """국소 염증후 홍반(PIE): 작고 이산적인 붉은 반점(a*↑) — diffuse redness 와 구분.

    PIE 직교화(focal 잔여 측정) 이후, PIE 는 광역 홍조가 아니라 '국소 반점'에 반응한다.
    이 주입기는 cheek 에 작은 원형 a* 스파이크를 흩뿌려 그 focal 신호를 만든다.
    """
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB).astype(np.int16)
    mask = np.zeros((h, w), np.uint8)
    for _ in range(int(round(severity * 28))):
        cy = int(rng.integers(int(h * 0.42), int(h * 0.72)))
        cx = (int(rng.integers(int(w * 0.06), int(w * 0.28)))
              if rng.random() < 0.5 else
              int(rng.integers(int(w * 0.72), int(w * 0.94))))
        cv2.circle(mask, (cx, cy), 3, 255, -1)
    m = mask > 0
    lab[:, :, 1][m] += 40   # 국소 a* 강하게 (focal residual)
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def inject_uneven_tone(img: np.ndarray, severity: float, *, seed: int = 5) -> np.ndarray:
    """국소 L* 패치로 명도 분산↑ — uneven_tone. severity 0~1.

    [FIX 2026-06-12] L* 채널만 가산 변조한다. 이전 구현은 cv2.circle 에 LAB 색
    (L,0,0) 을 채워 a*/b* 를 0(극단 녹청)으로 만들어 PIE(focal a*)·tone 으로 누설됐다
    (uneven_tone→PIE Δ≈−64 의 원인). 이제 크로마를 보존해 순수 L* 결함만 주입한다.
    """
    rng = np.random.default_rng(seed)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(float)
    h, w = img.shape[:2]
    L = lab[:, :, 0]
    for _ in range(int(severity * 40)):
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        rad = int(rng.integers(15, 40)); d = float(rng.normal(0, 18))
        patch = np.zeros((h, w), np.uint8)
        cv2.circle(patch, (cx, cy), rad, 1, -1)
        L[patch > 0] = np.clip(L[patch > 0] + d, 0, 255)   # L* 만 변조, a*/b* 보존
    lab[:, :, 0] = L
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def inject_roughness(img: np.ndarray, severity: float, *, seed: int = 0) -> np.ndarray:
    """고주파 노이즈 — roughness. severity 0~1."""
    rng = np.random.default_rng(seed + 2000)
    out = img.astype(float) + rng.normal(0.0, 18.0 * float(severity), img.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def inject_wrinkle_lines(img: np.ndarray, severity: float, *, roi: str = "eye",
                         seed: int = 3) -> np.ndarray:
    """ROI(eye/nasolabial)에 어두운 수평 선 — 주름. severity 0~1."""
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    if roi == "eye":
        y0, y1, x0, x1 = int(h * 0.18), int(h * 0.45), 0, int(w * 0.30)
    else:  # nasolabial
        y0, y1, x0, x1 = int(h * 0.48), int(h * 0.80), 0, int(w * 0.30)
    for _ in range(int(severity * 12)):
        yy = int(rng.integers(y0, y1))
        cv2.line(out, (x0, yy), (x1, yy), (90, 110, 130), 1)
    return out


def inject_pores(img: np.ndarray, severity: float, *, seed: int = 11) -> np.ndarray:
    """T존에 미세 어두운 점 밀도↑ — pore_size. severity 0~1."""
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    for _ in range(int(severity * 300)):
        cy = int(rng.integers(int(h * 0.30), int(h * 0.65)))
        cx = int(rng.integers(int(w * 0.35), int(w * 0.65)))
        c = out[cy, cx].astype(int)
        cv2.circle(out, (cx, cy), 1, tuple(int(max(0, v - 25)) for v in c), -1)
    return out


def inject_jawline_blur(img: np.ndarray, severity: float) -> np.ndarray:
    """전역 blur 로 edge 강도↓ — jawline_blur(탄력). severity 0~1."""
    k = 1 + 2 * int(severity * 4)
    return cv2.GaussianBlur(img, (k, k), 0) if k > 1 else img.copy()


def inject_oily(img: np.ndarray, severity: float, *, seed: int = 13) -> np.ndarray:
    """밝은 하이라이트(고V·저S) — skin_type(유분). severity 0~1."""
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    for _ in range(int(severity * 30)):
        cy, cx = int(rng.integers(0, h)), int(rng.integers(0, w))
        cv2.circle(out, (cx, cy), 5, (240, 240, 245), -1)
    return cv2.GaussianBlur(out, (5, 5), 0)


def _acne_roi_points(h, w, n, rng):
    """acne ROI(눈/코/입 제외) 내부 점 — 이마 + 외측 볼."""
    pts = []; tries = 0
    while len(pts) < n and tries < n * 20:
        tries += 1
        if rng.random() < 0.5:                      # 이마
            cy = int(rng.integers(int(h * 0.06), int(h * 0.15)))
            cx = int(rng.integers(int(w * 0.18), int(w * 0.82)))
        else:                                       # 외측 볼
            cy = int(rng.integers(int(h * 0.50), int(h * 0.59)))
            cx = (int(rng.integers(int(w * 0.06), int(w * 0.25))) if rng.random() < 0.5
                  else int(rng.integers(int(w * 0.75), int(w * 0.94))))
        pts.append((cx, cy))
    return pts


def inject_acne(img: np.ndarray, severity: float, *, seed: int = 9) -> np.ndarray:
    """HSV H∈[165,180] 크림슨 병변 — acne 5단 필터 통과(포화 홍반, b* 낮음). sev 0~1.

    [보정 핵심] acne 는 HSV 빨강범위(S≥60, V<210) AND a*↑ AND b*<base_b+0.5σ 를 동시
    요구한다. 단순 빨강(BGR)은 b*가 높아(황색) b* 필터에 걸리고, LAB a*만 올리면
    마젠타(H≈150)가 되어 빨강범위를 벗어난다. H≈172 크림슨이 두 조건을 모두 만족한다.
    주의: config 의 acne_score 브레이크포인트가 전 구간 x=0(붕괴)이라 점수가 사실상
    이진(결함 0개=100, 그 외≈0)으로 응답한다 — config 점검 권장.
    """
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
    mask = np.zeros((h, w), np.uint8)
    for cx, cy in _acne_roi_points(h, w, int(round(severity * 20)), rng):
        cv2.circle(mask, (cx, cy), 4, 255, -1)
    m = mask > 0
    hsv[:, :, 0][m] = 172; hsv[:, :, 1][m] = 190; hsv[:, :, 2][m] = 150
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def inject_post_acne_pigment(img: np.ndarray, severity: float, *, seed: int = 41) -> np.ndarray:
    """갈색 평면 자국(a*↑ b*↑) — post_acne_pigment(PAP). sev 0~1.

    크림슨(acne)과 달리 b*도 올려 갈색 계열로 만들어 PAP(고a* 평면) 검출을 트리거한다.
    """
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB).astype(np.int16)
    mask = np.zeros((h, w), np.uint8)
    for cx, cy in _acne_roi_points(h, w, int(round(severity * 25)), rng):
        cv2.circle(mask, (cx, cy), 4, 255, -1)
    m = mask > 0
    lab[:, :, 1][m] += 35; lab[:, :, 2][m] += 20
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def inject_dullness(img: np.ndarray, severity: float) -> np.ndarray:
    """전역 탈채도(+약한 V 감소) — dullness(칙칙함). sev 0~1.

    [보정 핵심] dullness = L_norm×0.20 + S_norm×0.50 + radiance×0.30 으로 **채도(S)가
    지배항**이며 높을수록 점수가 높다(덜 칙칙=좋음). 따라서 L*를 낮추는 게 아니라
    채도를 낮춰야(칙칙=무채색화) 점수가 단조 감소한다.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(float)
    hsv[:, :, 1] *= (1.0 - 0.75 * float(severity))
    hsv[:, :, 2] *= (1.0 - 0.15 * float(severity))
    return cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)


def inject_dark_global(img: np.ndarray, severity: float) -> np.ndarray:
    """전역 L*↓ — skin_tone(ITA) 하강. sev 0~1."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(float)
    lab[:, :, 0] = np.clip(lab[:, :, 0] - 45.0 * float(severity), 0, 255)
    return cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)


def inject_vertical_gradient(img: np.ndarray, severity: float) -> np.ndarray:
    """상부 밝고 하부 어두운 수직 밝기 구배 — cheek_sagging(상하 밝기차↑). sev 0~1."""
    out = img.astype(float); h = out.shape[0]
    ramp = np.linspace(1.0 + 0.4 * severity, 1.0 - 0.4 * severity, h)[:, None, None]
    return np.clip(out * ramp, 0, 255).astype(np.uint8)


def inject_pore_sagging(img: np.ndarray, severity: float, *, seed: int = 51) -> np.ndarray:
    """볼에 세로로 길쭉한 어두운 타원 구조 — pore_sagging(타원비↑). sev 0~1."""
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    for _ in range(int(severity * 60)):
        cy = int(rng.integers(int(h * 0.45), int(h * 0.70)))
        cx = int(rng.integers(int(w * 0.05), int(w * 0.30)))
        c = out[cy, cx].astype(int)
        cv2.ellipse(out, (cx, cy), (2, 6), 0, 0, 360,
                    tuple(int(max(0, v - 30)) for v in c), -1)
    return out


def inject_forehead_lines(img: np.ndarray, severity: float, *, seed: int = 31) -> np.ndarray:
    """이마에 두꺼운 가로선으로 local_std↑ — fine_deep_wrinkle(이마 깊은 주름). sev 0~1.

    fine_deep 은 forehead ROI 의 local_std 비율을 측정한다(roughness 와 직교).
    """
    out = img.copy(); h, w = out.shape[:2]; rng = np.random.default_rng(seed)
    for _ in range(int(severity * 22)):
        yy = int(rng.integers(int(h * 0.02), int(h * 0.17)))
        cv2.line(out, (int(w * 0.12), yy), (int(w * 0.88), yy), (45, 60, 80), 2)
    return out


def inject_pih(img: np.ndarray, severity: float, *, seed: int = 42) -> np.ndarray:
    """여드름 후 색소침착 (PIH) 주입
    
    LAB a* 채널 감지 임계값: 130
    LAB a* 채널: 녹색(-) ~ 빨간색(+), PIH는 빨간색/갈색 반점
    """
    np.random.seed(seed)
    h, w = img.shape[:2]
    result = img.copy()
    
    # BGR에서 직접 빨간색/갈색 반점 추가
    # LAB a* 채널 증가를 위해 빨간색 채널 강화
    num_spots = int(30 + severity * 100)
    for _ in range(num_spots):
        y = np.random.randint(int(h * 0.2), int(h * 0.8))
        x = np.random.randint(int(w * 0.2), int(w * 0.8))
        radius = int(6 + severity * 15)
        
        # 강한 빨간색/갈색 톤 (BGR: 낮은 B, 낮은 G, 높은 R)
        # 이는 LAB a* 채널을 증가시킴
        overlay = result.copy()
        cv2.circle(overlay, (x, y), radius, (20, 40, 220), -1)
        cv2.addWeighted(overlay, 0.7, result, 0.3, 0, result)
    
    return result


def inject_dead_skin(img: np.ndarray, severity: float, *, seed: int = 52) -> np.ndarray:
    """각질 (dead skin) 주입
    
    HSV 감지 임계값:
    - 채도(S) < 40 (낮은 채도)
    - 명도(V) > 180 (높은 명도)
    - 엣지 > 30 (높은 엣지)
    """
    np.random.seed(seed)
    h, w = img.shape[:2]
    result = img.copy()
    
    # 밝은 흰색 반점 + 엣지 추가
    num_spots = int(80 + severity * 200)
    for _ in range(num_spots):
        y = np.random.randint(int(h * 0.2), int(h * 0.8))
        x = np.random.randint(int(w * 0.2), int(w * 0.8))
        radius = int(5 + severity * 15)
        
        # 밝은 흰색 톤 (HSV: 낮은 채도, 높은 명도)
        cv2.circle(result, (x, y), radius, (245, 245, 245), -1)
        
        # 엣지 강화를 위해 반점 테두리 추가
        cv2.circle(result, (x, y), radius, (200, 200, 200), 1)
    
    return result


def inject_smoothness(img: np.ndarray, severity: float, *, seed: int = 62) -> np.ndarray:
    """매끄러움 (smoothness) 주입 - 그라디언트 감소
    
    severity가 높을수록 더 거칠음 (그라디언트 증가)
    severity가 낮을수록 더 매끄러움 (그라디언트 감소)
    """
    np.random.seed(seed)
    h, w = img.shape[:2]
    
    # severity가 높을수록 더 거칠음 (노이즈 추가)
    # severity가 낮을수록 더 매끄러움 (블러)
    if severity < 0.5:
        # 낮은 severity: 블러로 매끄러움 증가
        blur_strength = int(1 + (0.5 - severity) * 10)
        result = cv2.GaussianBlur(img, (blur_strength * 2 + 1, blur_strength * 2 + 1), 0)
    else:
        # 높은 severity: 노이즈로 거칠음 증가
        noise_amount = max(1, int((severity - 0.5) * 50))
        noise = np.random.randint(-noise_amount, noise_amount, img.shape, dtype=np.int16)
        result = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    return result


# ── 입력 빌더 (face → smask_bool, stat, regions) ─────────────────────
def _build_regions(face: np.ndarray) -> Dict[str, np.ndarray]:
    """_core._extract_face 의 ROI 슬라이싱을 검출 없이 그대로 복제."""
    from src.skin.core.face_roi import FaceROI as R
    from src.scoring._core import _safe_vstack, _safe_hstack
    fh, fw = face.shape[:2]; x1, x2 = int(fw * 0.35), int(fw * 0.65)
    return {
        "forehead": face[0:int(fh * R.FOREHEAD_BOTTOM), :],
        "left_eye": face[int(fh * R.EYE_TOP - 0.02):int(fh * R.EYE_BOTTOM - 0.03), 0:int(fw * 0.30)],
        "right_eye": face[int(fh * R.EYE_TOP - 0.02):int(fh * R.EYE_BOTTOM - 0.03), int(fw * 0.70):],
        "nose": face[int(fh * 0.30):int(fh * 0.65), x1:x2],
        "left_cheek": face[int(fh * R.CHEEK_TOP):int(fh * R.CHEEK_BOTTOM), 0:int(fw * 0.30)],
        "right_cheek": face[int(fh * R.CHEEK_TOP):int(fh * R.CHEEK_BOTTOM), int(fw * 0.70):],
        "chin": face[int(fh * R.CHIN_TOP):, :],
        "lower_face": face[int(fh * R.LOWER_FACE_TOP):, :],
        "t_zone": _safe_vstack([face[0:int(fh * 0.30), x1:x2], face[int(fh * 0.30):int(fh * 0.65), x1:x2]]),
        "u_zone": _safe_hstack([face[int(fh * 0.40):, 0:int(fw * 0.35)], face[int(fh * 0.40):, int(fw * 0.65):]]),
        "left_canthus": face[int(fh * R.FOREHEAD_BOTTOM - 0.05):int(fh * R.NOSE_TOP), 0:int(fw * 0.25)],
        "right_canthus": face[int(fh * R.FOREHEAD_BOTTOM - 0.05):int(fh * R.NOSE_TOP), int(fw * 0.75):],
        "glabella": face[int(fh * R.GLABELLA_TOP):int(fh * R.GLABELLA_BOTTOM), int(fw * 0.40):int(fw * 0.60)],
        "nasolabial_l": face[int(fh * R.NOSE_TOP):int(fh * 0.80), 0:int(fw * 0.30)],
        "nasolabial_r": face[int(fh * R.NOSE_TOP):int(fh * 0.80), int(fw * 0.70):],
        "lower_cheek_l": face[int(fh * R.LOWER_CHEEK_TOP):int(fh * R.LOWER_CHEEK_BOTTOM), 0:int(fw * 0.30)],
        "lower_cheek_r": face[int(fh * R.LOWER_CHEEK_TOP):int(fh * R.LOWER_CHEEK_BOTTOM), int(fw * 0.70):],
    }


def io_full(face: np.ndarray) -> Dict[str, object]:
    """분석기 호출용 묶음 생성.

    마스크 dtype 계약이 분석기마다 다르다(실측):
      - pigmentation : **bool** 필요 (strip_normalize_L 의 boolean 인덱싱)
      - wrinkles     : **uint8** 필요 (cv2.resize 가 bool 미지원)
      - 그 외        : uint8 로 동작 확인됨
    따라서 둘 다 제공하고 러너가 골라 쓴다.
    """
    from src.skin.core.image_utils import skin_mask, skin_stat
    sm = skin_mask(face)                       # uint8 (0/255)
    stat = skin_stat(cv2.cvtColor(face, cv2.COLOR_BGR2LAB), sm)
    for ch in ("L", "a", "b"):
        stat[f"pig_base_{ch}"] = stat[f"base_{ch}"]; stat[f"pig_std_{ch}"] = stat[f"std_{ch}"]
    stat["red_base_a"] = stat["base_a"]; stat["red_std_a"] = max(stat["std_a"], 2.0)
    return {
        "face": face,
        "smask": sm,                           # uint8 (기본)
        "smask_bool": sm.astype(bool),         # pigmentation 전용
        "stat": stat,
        "regions": _build_regions(face),
    }
