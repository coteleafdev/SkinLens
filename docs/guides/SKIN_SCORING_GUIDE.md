# SkinLens v1.0 - 스코어링 가이드

> **프로젝트:** SkinLens v1.0
> **기준 파일:** `skin_scoring.py` (v3.6)
> **측정항목 수:** 18개
> **점수 척도:** 내부 0~100 → 표시 10~90 선형 변환
> **운영 점수 기준 (2026년 5월):** 90 이상(매우 우수) / 80~90(우수) / 70~80(양호) / 60~70(집중케어 추천) / 60 미만(개선 필요)
> **설정 관리:** 모든 breakpoints는 `config.json`에서 단일 관리 (코드 하드코딩 제거)
> **마지막 수정:** 2026-05-28

---

## 개요

SkinLens v1.0 피부 분석 시스템은 얼굴 이미지를 분석하여 18개 세부 항목의 점수를 산출하고, 이를 기반으로 종합 피부 점수를 계산합니다.

**참고 문서:**
- 가중치 체계 상세: `weight_system_documentation.md`
- 아키텍처 가이드: `ARCHITECTURE_GUIDE.md`

### 점수 척도

- **내부 점수:** 0점 ~ 100점 (시스템 내부에서 사용하는 원시 점수)
- **표시 점수:** 10점 ~ 90점 (고객에게 표시되는 점수)
- **변환 공식:** `display = 10 + (internal / 100) × 80`
- **높은 점수:** 좋은 상태 (건강한 피부)
- **낮은 점수:** 개선이 필요한 상태

### 설정 관리

**[중요 2026-05-27]** 모든 브레이크포인트는 `config.json`의 `breakpoints` 섹션에서 단일 관리됩니다. 코드에 하드코딩된 상수는 제거되었습니다.

```json
{
  "breakpoints": {
    "area_default": [[0.0, 100.0], [0.01, 80.0], ...],
    "count_default": [[0, 100.0], [5, 80.0], ...],
    "acne_score": [[0, 100], [0.0008, 88], ...],
    "post_acne_pigment_score": [[0, 100], [0.001, 90], ...],
    ...
  }
}
```

- **area_default:** 면적 기반 항목의 기본 breakpoints
- **count_default:** 개수 기반 항목의 기본 breakpoints
- **항목별 breakpoints:** 각 측정항목별로 재정의 가능

---

## 18개 측정항목

### 카테고리별 가중치 배분

| 카테고리 | 항목 | 가중치 | 카테고리 합계 |
|----------|------|--------|--------------|
| 색소 (Pigmentation) | melasma, freckle | 0.090 / 0.080 | **0.170** |
| 홍조, 홍반 (Redness) | redness, post_inflammatory_erythema | 0.080 / 0.070 | **0.150** |
| 트러블·흔적 (Acne & Marks) | acne, post_acne_pigment | 0.279 / 0.060 | **0.339** |
| 모공 (Pore) | pore_size, pore_sagging | 0.060 / 0.060 | **0.120** |
| 주름 (Wrinkle) | eye_wrinkle, nasolabial, fine_deep | 0.050 / 0.040 / 0.040 | **0.130** |
| 텍스처 (Texture) | roughness | 0.075 | **0.075** |
| 톤·밝기 (Tone) | skin_tone, dullness, uneven_tone | 0.045 / 0.050 / 0.030 | **0.125** |
| 탄력 (Elasticity) | jawline_blur, cheek_sagging | 0.040 / 0.020 | **0.060** |
| 피부 타입 (Skin Type) | skin_type | 0.005 | **0.005** |
| **합계** | | | **1.170** |

> **참고:** 가중치 합계가 1.170인 이유는 `acne_score`의 가중치가 0.279로 높게 설정되어 있기 때문입니다. 실제 종합 점수 계산 시 정규화가 적용됩니다.

### 항목별 상세

| # | 항목 (키) | 한글명 | 카테고리 | 가중치 | 측정 원리 |
|---|---|---|---|---|---|
| 1 | `melasma_score` | 기미·잡티 | 색소 | 0.090 | L* 채널에서 피부 톤보다 어두운 영역 면적 비율 |
| 2 | `freckle_score` | 주근깨 | 색소 | 0.080 | gray_inv blob + L* < base-7, 개수 기반 |
| 3 | `redness_score` | 홍조 | 홍조 | 0.080 | a* z-score(전역) + a* > 1.5σ(국소) |
| 4 | `post_inflammatory_erythema_score` | 염증후 홍반 | 홍조 | 0.070 | a* > 2.5σ 강도 + 면적 |
| 5 | `acne_score` | 여드름 | 트러블 | 0.279 | HSV-V 돌출 AND a* > 1.5σ, 입체 병변 탐지 |
| 6 | `post_acne_pigment_score` | 여드름 후 색소 | 트러블 | 0.060 | a* > max(2.2σ, 5.5), 평면 자국 탐지 |
| 7 | `pore_size_score` | 모공 크기 | 모공 | 0.060 | LoG blob sigma 크기 + 밀도 |
| 8 | `pore_sagging_score` | 모공 처짐 | 모공 | 0.060 | 타원비 elongated 윤곽 비율 + Laplacian |
| 9 | `eye_wrinkle_score` | 눈가 주름 | 주름 | 0.050 | Sobel-Y × 0.65 + magnitude, 수직 주름선 강조 |
| 10 | `nasolabial_wrinkle_score` | 팔자 주름 | 주름 | 0.040 | Sobel magnitude, 팔자 ROI |
| 11 | `fine_deep_wrinkle_score` | 잔주름·깊은 주름 | 주름 | 0.040 | BoxFilter local_std 분포, 전체 얼굴 |
| 12 | `roughness_score` | 피부결 거칠기 | 텍스처 | 0.075 | LBP(r=1,2,3) 분산 |
| 13 | `skin_tone_score` | 피부 톤 | 톤 | 0.045 | ITA = arctan2(L*−50, b*) |
| 14 | `dullness_score` | 칙칙함 | 톤 | 0.050 | L_norm(L/155) + S_norm + highlight |
| 15 | `uneven_tone_score` | 톤 불균일 | 톤 | 0.030 | strip-norm L_std + block_std + 비대칭 |
| 16 | `jawline_blur_score` | 턱선 탄력 | 탄력 | 0.040 | Canny edge_strength, 턱선 ROI |
| 17 | `cheek_sagging_score` | 볼 처짐 | 탄력 | 0.020 | 볼 처짐 정도 측정 |
| 18 | `skin_type_score` | 피부 타입 | 피부 타입 | 0.005 | HSV V>215 & S<35 + dry_pixel_ratio |

---

## 측정 독립성 분석

### 판정 기준

| 기호 | 의미 |
|---|---|
| ✅ 독립 | 채널·ROI·임계 조건이 분리되어 동일 병변 이중 반영 없음 |
| ⚠ 부분 중첩 | 일부 조건 공유. 특정 케이스에서 동일 병변 이중 반영 가능 |
| ⚠ 경미 중첩 | 구조적으로 일부 기여하나 실질 영향 미미 |

### 항목별 독립성 요약

| 항목 | 독립성 | 중첩 대상 | 비고 |
|---|---|---|---|
| `melasma_score` | ⚠ 부분 | redness | a* OR 조건 공유, 붉은 기미 케이스 |
| `freckle_score` | ✅ 독립 | — | blob 개수 단위로 melasma와 완전 분리 |
| `redness_score` | ⚠ 부분 | post_inflammatory_erythema, post_acne_pigment | a* 채널 이중 스캔 (낮은 임계) |
| `post_inflammatory_erythema_score` | ⚠ 부분 | redness, post_acne_pigment | a* 채널 이중 스캔 (높은 임계) |
| `acne_score` | ⚠ 부분 | post_acne_pigment | 활성기 붉은 구진 이중 반영 |
| `post_acne_pigment_score` | ⚠ 부분 | redness, post_inflammatory_erythema, acne | a* 고강도 조건, 활성 병변 중복 |
| `pore_size_score` | ✅ 독립 | — | ROI·측정 차원 완전 분리 |
| `pore_sagging_score` | ✅ 독립 | — | ROI·측정 차원 완전 분리 |
| `eye_wrinkle_score` | ✅ 독립 | fine_deep (경미) | ROI 분리로 독립 판정 |
| `nasolabial_wrinkle_score` | ✅ 독립 | fine_deep (경미) | ROI 분리로 독립 판정 |
| `fine_deep_wrinkle_score` | ⚠ 부분 | roughness | 전체 얼굴 표면 이중 측정 |
| `roughness_score` | ⚠ 부분 | fine_deep | 전체 얼굴 표면 이중 측정 |
| `skin_tone_score` | ⚠ 부분 | dullness | L* 절대값 공유, 어두운 피부 이중 감점 |
| `dullness_score` | ✅ 독립 | — | 평균 vs 분산으로 uneven_tone과 독립 |
| `uneven_tone_score` | ✅ 독립 | — | L* 분산, 타 항목과 차원 분리 |
| `jawline_blur_score` | ✅ 독립 | — | 전용 ROI + 전용 채널 |
| `cheek_sagging_score` | ✅ 독립 | — | 전용 ROI + 전용 채널 |
| `skin_type_score` | ✅ 독립 | — | 전용 채널(HSV 각질) + 물리 현상 분리 |

### 주요 중첩 구조

**a* 채널 중첩 군 (4항목):**
```
redness(1.5σ) ⊃ post_inflammatory_erythema(2.5σ) ≈ post_acne_pigment(2.2σ)
                                    ↕ 활성기 중복
                                   acne(HSV-V AND 1.5σ)
```

**L* 채널 중첩 군 (3항목):**
```
skin_tone(ITA: L*/b* 비율) — dullness(L* 절대 평균) — uneven_tone(L* 분산)
     ↕ 부분 중첩                    ↕ 독립
```

---

## 직교 신호 분해

### 개요

SkinLens v1.0은 18개 측정항목을 10개의 직교 내부 신호로 분해하여 더 정교한 분석을 수행합니다.

### 내부 신호 구조

| 신호 ID | 설명 | 관련 측정항목 |
|---------|------|--------------|
| S1 | 색소 강도 | melasma_score, freckle_score |
| S2 | 홍조 강도 | redness_score, post_inflammatory_erythema_score |
| S3 | 트러블 활성도 | acne_score |
| S4 | 색소 잔여 | post_acne_pigment_score |
| S5 | 모공 크기 | pore_size_score |
| S6 | 모공 처짐 | pore_sagging_score |
| S7 | 주름 강도 | eye_wrinkle_score, nasolabial_wrinkle_score |
| S8 | 텍스처 거칠기 | roughness_score |
| S9 | 톤 균형 | skin_tone_score, dullness_score, uneven_tone_score |
| S10 | 탄력 저하 | jawline_blur_score, cheek_sagging_score |

### 분해 원리

- **직교성:** 각 신호는 서로 독립적이며 중복 정보를 최소화
- **계층 구조:** 원시 측정항목 → 내부 신호 → 가중치 체계 → 최종 점수
- **적응형 조정:** 피부 타입, 연령대에 따른 신호 가중치 조정

---

## 가중치 체계

### 개요

SkinLens v1.0은 세 가지 가중치 체계를 지원하여 다양한 분석 시나리오에 대응합니다.

### 가중치 체계 구조

| 체계 | 설명 | 사용 시나리오 |
|------|------|--------------|
| **레이어A** | 최신 가중치 체계 (직교 신호 기반) | 일반 분석, 운영 환경 |
| **레이어B** | 실험적 가중치 체계 (연구용) | 연구 개발, A/B 테스트 |
| **레거시 v2** | 이전 버전 가중치 체계 (호환성) | 하위 호환성 유지 |

### 가중치 적용 로직

```python
# config.json에서 가중치 체계 선택
weight_system = config.get("weights", "layer_a")

# 가중치 로드
if weight_system == "layer_a":
    weights = load_layer_a_weights()
elif weight_system == "layer_b":
    weights = load_layer_b_weights()
else:  # legacy
    weights = load_legacy_weights()

# 직교 신호에 가중치 적용
weighted_signals = apply_weights(internal_signals, weights)

# 최종 점수 계산
final_score = aggregate_weighted_signals(weighted_signals)
```

### config.json 설정

```json
{
  "weights": {
    "_note": "가중치 체계 선택: layer_a (기본), layer_b, legacy_v2",
    "_purpose": "다양한 분석 시나리오에 대응하기 위한 가중치 체계",
    "_relation": "measurement_weights 섹션과 연동",
    "system": "layer_a"
  }
}
```

---

## 주요 약어 정리

### Suffix 약어 (변수명 뒤에 붙는 접미사)

| 약어 | 풀네임 | 의미 |
|---|---|---|
| `_px` | **px**el count | 픽셀 수 (정수) |
| `_bool` | **bool**ean mask | `mask > 0` 으로 변환한 True/False 이진 배열 |
| `_ch` | **ch**annel | LAB·HSV 채널 슬라이스 배열 |
| `_mask` | binary **mask** | 관심 영역을 0/255로 표시한 uint8 배열 |
| `_roi` | **R**egion **O**f **I**nterest | 분석 대상 공간 범위(좌표·슬라이스) |
| `_score` | **score** | 10~90 범위 최종 점수 |
| `_mean` | **mean** | 평균값 |
| `_std` | **st**an**d**ard deviation | 표준편차 |

### Prefix 약어 (변수명 앞에 붙는 접두사)

| 약어 | 풀네임 | 의미 |
|---|---|---|
| `skin_` | **skin** | 전체 피부 영역 기준 |
| `pig_` | **pig**ment | 눈·코·입을 제거한 색소 분석 전용 영역 |
| `ref_` | **ref**erence | 기준(깨끗한) 이미지에서 주입하는 통계 |
| `base_` | **base**line | 피부 마스크 내 중앙값(median) |

### 도메인·색공간 약어

| 약어 | 풀네임 | 의미 |
|---|---|---|
| `LAB` | **L**\*a\*b\* color space | CIE L\*a\*b\* 색공간. L=밝기, a=적-녹, b=황-청 |
| `L` | **L**uminance | LAB 명도 채널 (0~100) |
| `HSV` | **H**ue **S**aturation **V**alue | 색상·채도·명도 색공간 |
| `ITA` | **I**ndividual **T**ypology **A**ngle | 개인 피부톤 각도 |
| `ROI` | **R**egion **O**f **I**nterest | 분석 관심 영역 |
| `LoG` | **L**aplacian **o**f **G**aussian | 가우시안 블러 후 Laplacian 적용 |
| `PIH` | **P**ost-**I**nflammatory **H**yperpigmentation | 염증 후 색소침착 |
| `blob` | **B**inary **L**arge **OB**ject | 연결된 픽셀 덩어리 |

---

## 운영 점수 기준

**새로운 점수 기준 (2026년 5월):**
- **90 이상:** 매우 우수
- **80~90:** 우수
- **70~80:** 양호
- **60~70:** 집중케어 추천
- **60 미만:** 개선 필요

**[참고]** 점수 기준은 `config.json`의 `score_criteria` 섹션에서 관리됩니다. LLM 프롬프트에도 이 기준이 제공되어 독립적인 점수 산출을 유도합니다.

---

## 최신 변경 사항 (2026-05-28)

### 점수 기준 섹션 추가
- **변경**: CV 분석기 측정 점수 대신 점수 평가 기준 제공
- **이유**: LLM이 CV 점수에 의존하지 않고 독립적으로 점수를 산출하도록 유도
- **구현**:
  - `config/config.json`에 `score_criteria` 섹션 추가 (점수 스케일, 등급 라벨)
  - `llm_prompt_builder.py`에 `_build_score_criteria_section()` 함수 추가
  - 프롬프트 템플릿에서 `{cv_scores_section}` → `{score_criteria_section}` 변경

---

## 참고 문서

- `llm_prompt_template.md` - LLM 프롬프트 템플릿 (측정항목 메타데이터 포함)
- `config.json` - 런타임 설정 (측정항목 메타데이터, 가중치 체계 포함)
- `skin_scoring.py` - 스코어링 핵심 로직
- `ARCHITECTURE_GUIDE.md` - 아키텍처 가이드 (직교 신호 분해 상세)

---

*생성일: 2026-05-24*  
*기준 파일: `skin_scoring.py` (v3.4)*
