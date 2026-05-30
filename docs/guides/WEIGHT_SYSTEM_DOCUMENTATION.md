# 가중치 체계 문서화

> **작성일:** 2026-05-24  
> **버전:** 1.0  
> **목적:** SkinLens v1.0의 가중치 체계 삼원화 구조 설명

---

## 개요

SkinLens v1.0은 **두 가지 가중치 체계**를 사용합니다. 각 체계는 다른 목적을 가지며, 서로 다른 항목과 합계를 가집니다.

| 체계 | 항목 수 | 합계 | 사용처 | 소스 |
|------|---------|------|--------|------|
| 레이어 A (직교 가중치) | 10개 | 1.000 | 표시 종합 점수 | `config.json → prescription.orthogonal_categories` |
| 레이어 B (보고서 가중치) | 21개 | 1.199 | Safety Net, LLM 입력 | `LLM_PROMPT_TEMPLATE.md → MEASUREMENT_WEIGHTS` |

---

## 레이어 A: 직교 가중치 (표시용)

### 목적
- **사용자에게 표시되는 종합 점수** 계산
- 10개 직교 항목 기반
- 직교성 보장 (항목 간 상관관계 최소화)

### 항목 및 가중치

| 직교 항목 | 가중치 | 한글명 | 영문명 | 소스 측정항목 |
|-----------|--------|--------|--------|--------------|
| pigmentation_cov | 0.120 | 색소침착 커버리지 | Pigmentation Coverage | melasma_score, freckle_score, post_acne_pigment_score |
| spot_density | 0.100 | 반점 밀도 | Spot Density | - |
| diffuse_redness | 0.120 | 확산성 홍조 | Diffuse Redness | redness_score |
| focal_lesion | 0.140 | 국소 병변 | Focal Lesion | acne_score, post_acne_pigment_score |
| pore_score | 0.120 | 모공 점수 | Pore Score | pore_size_score, pore_sagging_score |
| wrinkle_score | 0.160 | 주름 점수 | Wrinkle Score | eye_wrinkle_score, nasolabial_wrinkle_score, fine_deep_wrinkle_score |
| roughness_score | 0.050 | 거칠기 점수 | Roughness Score | roughness_score |
| tone_score | 0.100 | 톤 점수 | Tone Score | skin_tone_score, dullness_score, uneven_tone_score |
| elasticity_score | 0.050 | 탄력 점수 | Elasticity Score | jawline_blur_score, cheek_sagging_score |
| skin_type_score | 0.040 | 피부 타입 점수 | Skin Type Score | skin_type_score |

**합계:** 1.000

### 소스 코드 경로
- **설정:** `config.json → prescription → orthogonal_categories`
- **로드 함수:** `src/skin/compose/score_composition.py → _get_weights()`
- **사용:** `src/scoring/skin_scoring.py → _legacy_to_current()`

### 계산 방법
```python
overall_score = sum(orthogonal_score * weight for orthogonal_score, weight in orthogonal_items) / sum(weights)
```

---

## 레이어 B: 보고서 가중치 (Safety Net/LLM용)

### 목적
- **Safety Net 판단 기준** (복원 품질 포함)
- **LLM 리포트 입력** (21개 항목)
- 복원 후 노이즈 감소가 Safety Net 합격에 영향

### 항목 및 가중치

| 항목 | 가중치 | 비고 |
|------|--------|------|
| melasma_score | 0.059 | |
| freckle_score | 0.059 | |
| redness_score | 0.118 | |
| acne_score | 0.279 | 가장 높은 가중치 |
| post_acne_pigment_score | 0.059 | |
| pore_size_score | 0.059 | |
| pore_sagging_score | 0.059 | |
| eye_wrinkle_score | 0.059 | |
| nasolabial_wrinkle_score | 0.059 | |
| fine_deep_wrinkle_score | 0.059 | |
| roughness_score | 0.059 | |
| skin_tone_score | 0.059 | |
| dullness_score | 0.059 | |
| uneven_tone_score | 0.059 | |
| jawline_blur_score | 0.059 | |
| cheek_sagging_score | 0.059 | |
| skin_type_score | 0.059 | |
| **noise_score** | 0.130 | 복원품질 (레이어 A에 없음) |
| **detail_score** | 0.070 | 복원품질 (레이어 A에 없음) |
| **color_balance_score** | 0.070 | 복원품질 (레이어 A에 없음) |

**합계:** 1.199

### 소스 코드 경로
- **설정:** `docs/LLM_PROMPT_TEMPLATE.md → MEASUREMENT_WEIGHTS`
- **로드 함수:** `src/scoring/config/_config.py → get_measurement_weights()`
- **사용:** `src/scoring/_report.py → LayerB.build()`
- **안전장치 로직:** `src/skin/scoring/safety_net.py → apply_safety_net_logic()`

### 계산 방법
```python
overall_score = sum(measurement * weight for measurement, weight in measurement_items) / sum(weights)
```

### 안전장치 동작 (2026-05-25 수정)
- **패스스루 조건:** 복원 점수가 원본 점수보다 5점 이상 낮지 않으면 안전장치 적용하지 않음
- **목적:** 과도한 클램프로 인한 점수 하락 방지
- **수정 전 문제:** 개별 항목 클램프와 재계산 로직으로 인해 점수가 75.7 → 17.2로 급락
- **수정 후:** 합리적인 점수 범위 내에서는 분석기 점수 그대로 유지

---

## 가중치 체계 비교

### 차이점 요약

| 특성 | 레이어 A (직교) | 레이어 B (보고서) |
|------|----------------|------------------|
| 항목 수 | 10개 | 21개 |
| 합계 | 1.000 | 1.199 |
| 복원품질 포함 | ❌ | ✅ (noise, detail, color_balance) |
| 사용자 표시 | ✅ | ❌ |
| Safety Net | ❌ | ✅ |
| LLM 입력 | ❌ | ✅ |
| 직교성 보장 | ✅ | ❌ |

### 주요 차이점 설명

1. **복원품질 항목 포함 여부**
   - 레이어 B에는 `noise_score`, `detail_score`, `color_balance_score`가 포함됨
   - 복원 후 노이즈 감소가 Safety Net 합격에 긍정적 영향
   - 레이어 A는 복원품질을 제외한 순수 피부 상태만 평가

2. **가중치 합계 차이**
   - 레이어 A: 1.000 (정규화됨)
   - 레이어 B: 1.199 (복원품질 추가로 합계 증가)
   - 계산 시 합계로 나누어 정규화

3. **사용처 분리**
   - 사용자가 보는 점수 = 레이어 A (직교 10개)
   - 시스템 판단 기준 = 레이어 B (보고서 21개)

---

## 설계 의도

### 왜 이원화인가?

1. **사용자 경험 vs 시스템 안정성**
   - 사용자: 순수 피부 상태 점수 (복원품질 제외)
   - 시스템: 복원 품질 포함 전체 평가

2. **직교성 vs 포괄성**
   - 레이어 A: 직교성 보장 (중복 평가 방지)
   - 레이어 B: 포괄적 평가 (모든 측정항목 포함)

---

## 향후 개선 방안

### 통합 방안 (논의 필요)

1. **단일 가중치 체계로 통합**
   - 복원품질 항목을 직교 항목으로 분리하여 레이어 A에 포함
   - Safety Net과 사용자 표시에 동일한 가중치 사용

2. **명시적 설정 분리**
   - `display_weights` (사용자 표시용)
   - `safety_net_weights` (시스템 판단용)
   - `llm_weights` (LLM 입력용)

3. **문서화 강화**
   - 각 가중치 체계의 목적과 사용처 명시
   - config.json 내 주석 추가

---

## 참고

- **config.json:** `config/config.json`
- **LLM 프롬프트 템플릿:** `docs/LLM_PROMPT_TEMPLATE.md`
- **스코어 합성:** `src/skin/compose/score_composition.py`
- **레이어 B:** `src/scoring/_report.py`
- **코드 리뷰:** `SkinLens_v1_Parts_Review.md` (B-1 섹션)
