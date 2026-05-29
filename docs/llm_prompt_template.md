# Gemini AI 피부 분석 프롬프트 템플릿

**버전**: v1.0  
**마지막 수정**: 2026-05-27  
**상태**: Production

<!--
[REFACTOR 2026-05-24] 설정 데이터는 config.json으로 이전 완료.
이 파일은 순수 프롬프트 템플릿으로 유지됩니다.

설정 데이터 이전 내역:
- MEASUREMENT_WEIGHTS → config.json measurement_weights
- ACTUAL_RANGES → config.json actual_ranges
- SCORE_MAPPING → config.json score_mapping
- SCORE_CRITERIA → config.json score_criteria
- RECOMMENDATION_GUIDELINES → config.json recommendation_guidelines
- METRIC_META → config.json measurements 섹션
- DISPLAY_NAMES → config.json measurements 섹션 (name_ko, name_en)

[NOTE] 프롬프트 버전 관리:
- 이 파일의 버전을 변경할 때는 docs/AB_TESTING_FRAMEWORK_DESIGN.md를 참조하여 A/B 테스트 절차를 따르십시오.
- 버전 변경 시 src/llm/prompt_manager.py의 버전 매핑도 업데이트해야 합니다.
-->

<!-- METRIC_META_START -->
## 측정항목 메타데이터

**참고**: 측정항목 개수는 유동적입니다. 필요에 따라 항목을 추가하거나 삭제할 수 있습니다.

(key, 한글명, 카테고리, 높을수록 좋음 여부)

### 색소 (Pigmentation)
- melasma_score: 기미·잡티: True
- freckle_score: 주근깨: True

### 홍조, 홍반 (Redness)
- redness_score: 홍조: True
- post_inflammatory_erythema_score: 염증후 홍반: True

### 트러블·흔적 (Acne & Marks)
- acne_score: 여드름: True
- post_acne_pigment_score: 여드름 후 색소: True

### 모공 (Pore)
- pore_size_score: 모공 크기: True
- pore_sagging_score: 모공 처짐: True

### 주름 (Wrinkle)
- eye_wrinkle_score: 눈가 주름: True
- nasolabial_wrinkle_score: 팔자 주름: True
- fine_deep_wrinkle_score: 잔주름·깊은 주름: True

### 텍스처 (Texture)
- roughness_score: 피부결 거칠기: True

### 톤·밝기 (Tone)
- skin_tone_score: 피부 톤: True
- dullness_score: 칙칙함: True
- uneven_tone_score: 톤 불균일: True

### 탄력 (Elasticity)
- jawline_blur_score: 턱선 탄력: True
- cheek_sagging_score: 볼 처짐: True

### 피부 타입 (Skin Type)
- skin_type_score: 피부 타입: True

<!-- METRIC_META_END -->

<!-- DISPLAY_NAMES_START -->
## 디스플레이 이름

**참고**: 각 측정항목의 표시 이름입니다. 영문 이름도 포함할 수 있습니다.

### 디스플레이 이름 매핑
- melasma_score: 기미·잡티 (Melasma)
- freckle_score: 주근깨 (Freckle)
- redness_score: 홍조 (Redness)
- post_inflammatory_erythema_score: 염증후 홍반 (Inflammation)
- acne_score: 여드름 (Acne)
- post_acne_pigment_score: 여드름 후 색소 (Post-Acne Pigment)
- pore_size_score: 모공 크기 (Pore Size)
- pore_sagging_score: 모공 처짐 (Pore Sagging)
- eye_wrinkle_score: 눈가 주름 (Eye Wrinkle)
- nasolabial_wrinkle_score: 팔자 주름 (Nasolabial)
- fine_deep_wrinkle_score: 잔주름·깊은 주름 (Fine/Deep)
- roughness_score: 피부결 거칠기 (Roughness)
- skin_tone_score: 피부 톤 (Skin Tone)
- dullness_score: 칙칙함 (Dullness)
- uneven_tone_score: 톤 불균일 (Unevenness)
- jawline_blur_score: 턱선 탄력 (Jawline)
- cheek_sagging_score: 볼 처짐 (Cheek Sagging)
- skin_type_score: 피부 타입 (Skin Type)
<!-- DISPLAY_NAMES_END -->

<!--
[REFACTOR 2026-05-24] 설정 데이터는 config.json으로 이전 완료.
다음 섹션들은 제거됨:
- MEASUREMENT_WEIGHTS_START/END → config.json measurement_weights
- ACTUAL_RANGES_START/END → config.json actual_ranges
- SCORE_MAPPING_START/END → config.json score_mapping
- SCORE_CRITERIA_START/END → config.json score_criteria
- RECOMMENDATION_GUIDELINES_START/END → config.json recommendation_guidelines
-->

<!-- PRODUCT_RECOMMENDATIONS_SCHEMA_START -->
## 맞춤형 화장품 추천 구조

**참고**: 맞춤형 화장품 추천(product_recommendations)의 JSON 구조 스키마입니다.

**목적**: 측정된 피부 상태와 설문 응답을 기반으로 맞춤형 화장품을 추천할 때 사용하는 데이터 구조입니다.

**JSON 구조**:
```json
{
  "matched_products": [
    {
      "product_id": "제품 ID (문자열)",
      "product_name": "제품명 (문자열)",
      "category": "카테고리 (문자열, 예: 세안제, 토너, 세럼, 크림, 선크림)",
      "key_ingredients": ["주요 성분 목록 (문자열 배열)"],
      "efficacy": "효능 설명 (문자열)",
      "match_score": 0.95,
      "match_reason": "매칭 이유 (문자열, 선택사항)"
    }
  ],
  "recommendation_summary": "추천 요약 (문자열)"
}
```

**필드 설명**:
- `matched_products`: 매칭된 제품 목록 배열
  - `product_id`: 제품 고유 식별자
  - `product_name`: 제품 이름
  - `category`: 제품 카테고리
  - `key_ingredients`: 주요 성분 목록
  - `efficacy`: 제품 효능 설명
  - `match_score`: 매칭 점수 (0.0 ~ 1.0, 높을수록 적합)
  - `match_reason`: 매칭 이유 (선택사항)
- `recommendation_summary`: 전체 추천 요약 문장

**사용처**:
- GUI(image_enhancer.py)에서 화장품 매칭 결과를 LLM에 전달
- LLM이 추천 제품을 기반으로 소견에 반영
<!-- PRODUCT_RECOMMENDATIONS_SCHEMA_END -->

<!-- PRESCRIPTION_CONFIG_START -->
## 처방전 설정

**참고**: 피부 평가 점수 및 PCR 결과 기반 처방전 계산 설정입니다.

**목적**: 피부 상태에 따른 맞춤형 화장품 조성원료(A-Mix, M-Mix) 처방 비율을 결정합니다.

### 피부 평가 항목 → 믹스 코드 매핑

**참고**: 18개 고객님 표현용 측정항목 → 14개 처방 항목(A01-A14) 매핑입니다.

| 18개 측정항목 | 처방 항목 | 믹스 코드 | 설명 |
|------------|---------|---------|------|
| dullness_score | radiance | A01 | 광채 |
| eye_wrinkle_score, nasolabial_wrinkle_score, fine_deep_wrinkle_score | wrinkle | A02 | 주름 |
| - | dark_circle_v2 | A03 | 다크서클 (현재 미사용) |
| - | oiliness | A04 | 유분 (현재 미사용) |
| jawline_blur_score | firmness | A05 | 탄력 |
| melasma_score, freckle_score, post_acne_pigment_score | age_spot | A06 | 색소침착 |
| redness_score, post_inflammatory_erythema_score | redness | A07 | 홍조 |
| - | droopy_lower_eyelid | A08 | 하안검 처짐 (현재 미사용) |
| pore_size_score, pore_sagging_score | pore | A09 | 모공 |
| roughness_score | texture | A10 | 피부결 |
| - | eye_bag | A11 | 눈밑 지방 (현재 미사용) |
| - | droopy_upper_eyelid | A12 | 상안검 처짐 (현재 미사용) |
| - | moisture | A13 | 수분 (현재 미사용) |
| acne_score | acne | A14 | 여드름 |

**매핑 규칙**:
- 하나의 처방 항목에 여러 측정항목이 매핑될 수 있음 (예: age_spot ← melasma_score, freckle_score, post_acne_pigment_score)
- 매핑된 측정항목 중 가장 낮은 점수를 기준으로 처방 비율 결정
- 현재 미사용 항목은 향후 확장을 위해 예약됨

### 점수 → 처방 비율 변환 규칙

| 점수 범위 | 등급 | 처방 비율 | 설명 |
|---------|------|---------|------|
| 76-100점 | Good | 0% | 처방 없음 |
| 41-75점 | Moderate | 1.0% ~ 3.0% | 선형 계산 |
| 0-40점 | Critical | 3.0% | 최대 처방 |

**선형 계산 공식 (41-75점)**:
```
percentage = 3.0 - ((score - 41.0) * 2.0 / 34.0)
```

- 41점: 3.0%
- 75점: 1.0%
- 0.1% 단위로 반올림
- 범위 제한: 1.0% ~ 3.0%

### PCR 처방 규칙

#### 총량 (total) - M10, PM04

| rV 범위 | 처방 |
|--------|------|
| rV ≥ 0 | 처방 없음 |
| -10 < rV < 0 | M10 1.5% |
| -20 < rV ≤ -10 | M10 2.0% |
| -30 < rV ≤ -20 | PM04 2.5% |
| rV ≤ -30 | PM04 3.0% |

#### 유익균 (beneficial) - PM01, PM05

| rV 범위 | 처방 |
|--------|------|
| rV ≥ 0 | 처방 없음 |
| -10 < rV < 0 | PM01 1.5% |
| -20 < rV ≤ -10 | PM01 2.0% |
| -30 < rV ≤ -20 | PM05 2.5% |
| rV ≤ -30 | PM05 3.0% |

#### 트러블균 (trouble) - PM02, PM06

| rV 범위 | 처방 |
|--------|------|
| rV ≤ 0 | 처방 없음 |
| 0 < rV ≤ 10 | PM02 1.5% |
| 10 < rV ≤ 20 | PM02 2.0% |
| 20 < rV ≤ 30 | PM06 2.5% |
| rV > 30 | PM06 3.0% |

#### 유해균 (harmful) - PM03, PM07

| rV 범위 | 처방 |
|--------|------|
| rV ≤ 0 | 처방 없음 |
| 0 < rV ≤ 10 | PM03 1.5% |
| 10 < rV ≤ 20 | PM03 2.0% |
| 20 < rV ≤ 30 | PM07 2.5% |
| rV > 30 | PM07 3.0% |

**사용처**:
- src/prescription/prescription_calculator.py에서 처방전 계산
- 피부 평가 점수 기반 처방 (calculate_skin_assessment_recipe)
- PCR 결과 기반 처방 (calculate_pcr_recipe)
<!-- PRESCRIPTION_CONFIG_END -->

<!-- ANALYZER_VERSION_MAPPING_START -->
## 분석기 버전 매핑

### 개요

18개 측정항목 각각에 사용할 분석기 버전을 config.json에서 동적으로 설정하여, 알고리즘 버전업 시 코드 수정 없이 유연하게 대응합니다.

### 왜 6종의 분석기인가?

18개 측정항목에 대해 6종의 분석기만 사용하는 이유는 **하나의 분석기가 여러 관련 측정항목을 동시에 계산**하기 때문입니다.

**설계 이유**:
1. **효율성**: 관련된 항목을 한 번의 이미지 처리로 계산하여 중복 연산 방지
2. **논리적 그룹화**: 같은 도메인의 항목을 하나의 분석기로 관리하여 일관성 유지
3. **데이터 의존성**: 일부 항목은 다른 항목의 결과를 필요로 하여 통합 계산

**완전 독립성**:
- [REFACTOR 2026-05-23] 모든 분석기가 서로 독립적
- tone_elasticity_v1이 내부에서 주름 분석 로직 포함
- 외부 wrinkle 분석기 의존성 제거
- **이론적으로 병렬 실행 가능** (현재 구현은 순차 실행)
- 향후 병렬화 구현 시 성능 향상 기대

### 분석기별 담당 측정항목

| 분석기 버전 | 담당 측정항목 (개수) | 설명 |
|------------|------------------|------|
| pigmentation_v1 | melasma_score, freckle_score (2개) | 색소 관련 항목을 한 번에 계산 |
| redness_v1 | redness_score, post_inflammatory_erythema_score (2개) | 홍조 관련 항목을 한 번에 계산 |
| acne_v1 | acne_score, post_acne_pigment_score (2개) | 여드름 및 여드름 후 색소 항목 계산 |
| pore_v1 | pore_size_score, pore_sagging_score (2개) | 모공 관련 항목을 한 번에 계산 |
| wrinkle_v1 | eye_wrinkle_score, nasolabial_wrinkle_score, fine_deep_wrinkle_score (3개) | 주름 관련 항목을 한 번에 계산 |
| tone_elasticity_v1 | skin_tone_score, dullness_score, uneven_tone_score, jawline_blur_score, cheek_sagging_score, skin_type_score (6개) | 톤/탄력/피부타입 관련 항목을 한 번에 계산 (내부 주름 분석 포함) |
| — | roughness_score (1개) | `analyze_texture()` 순수 함수로 계산 (레지스트리 없음) |

### 매핑 테이블

| 18개 측정항목 | 분석기 버전 | 설명 |
|------------|-----------|------|
| melasma_score | pigmentation_v1 | 기미·잡티 분석기 v1 |
| freckle_score | pigmentation_v1 | 주근깨 분석기 v1 |
| redness_score | redness_v1 | 홍조 분석기 v1 |
| post_inflammatory_erythema_score | redness_v1 | 염증후 홍반 분석기 v1 |
| acne_score | acne_v1 | 여드름 분석기 v1 |
| post_acne_pigment_score | acne_v1 | 여드름 후 색소 분석기 v1 |
| pore_size_score | pore_v1 | 모공 크기 분석기 v1 |
| pore_sagging_score | pore_v1 | 모공 처짐 분석기 v1 |
| eye_wrinkle_score | wrinkle_v1 | 눈가 주름 분석기 v1 |
| nasolabial_wrinkle_score | wrinkle_v1 | 팔자 주름 분석기 v1 |
| fine_deep_wrinkle_score | wrinkle_v1 | 잔주름·깊은 주름 분석기 v1 |
| roughness_score | — | `analyze_texture()` 순수 함수 (레지스트리 없음) |
| skin_tone_score | tone_elasticity_v1 | 피부 톤 분석기 v1 |
| dullness_score | tone_elasticity_v1 | 칙칙함 분석기 v1 |
| uneven_tone_score | tone_elasticity_v1 | 톤 불균일 분석기 v1 |
| jawline_blur_score | tone_elasticity_v1 | 턱선 탄력 분석기 v1 |
| cheek_sagging_score | tone_elasticity_v1 | 볼 처짐 분석기 v1 |
| skin_type_score | tone_elasticity_v1 | 피부 타입 분석기 v1 |

### 버전업 절차

1. **새로운 분석기 버전 구현**
   - `src/skin/analyzers/strategies/`에 새로운 분석기 클래스 생성
   - `@AnalyzerRegistry.register("pigmentation_v2")` 데코레이터로 등록

2. **config.json 매핑 수정**
   - `measurement_analyzers` 섹션에서 해당 측정항목의 분석기 버전 변경
   - 예: `"melasma_score": "pigmentation_v2"`

3. **자동 반영**
   - 다음 분석 실행 시 새로운 분석기 버전 자동 적용
   - 코드 수정 불필요

### 사용처

- **config.json**: `measurement_analyzers` 섹션
- **src/skin/analyzers/registry.py**: `get_for_measurement()` 메서드
- **src/scoring/_core.py**: 측정항목별 분석기 로드 로직

### 예시

**pigmentation_v2로 업그레이드 시**:
```json
{
  "measurement_analyzers": {
    "melasma_score": "pigmentation_v2",
    "freckle_score": "pigmentation_v2",
    ...
  }
}
```

**코드 변경 없이 자동 적용됨**:
```python
# _core.py에서 자동으로 pigmentation_v2 사용
pig_analyzer = AnalyzerRegistry.get_for_measurement("melasma_score")
```
<!-- ANALYZER_VERSION_MAPPING_END -->

<!-- SYSTEM_PROMPT_START -->
## System Prompt

당신은 CÔTELEAF 피부 AI 분석 시스템의 전문 피부과 소견 작성 엔진입니다.
다음 규칙을 엄격히 따르십시오:

1. 응답은 반드시 JSON 형식만 출력하십시오. Markdown 코드블록(```) 없이 순수 JSON만 출력.
2. JSON은 반드시 완전하고 유효해야 합니다. 모든 문자열은 큰따옴표(")로 감싸고, 모든 중괄호와 대괄호를 닫으십시오.
3. 응답이 중단되지 않도록 모든 필드를 완전히 작성하십시오. 특히 문자열 필드는 반드시 닫는 큰따옴표를 포함해야 합니다.
4. 각 항목 소견은 2~3문장, 구체적이고 전문적인 한국어로 작성.
5. 점수 10~90 기준: SCORE_CRITERIA 섹션의 점수 기준을 참조하십시오.
6. 이미지를 직접 참고하여 점수와 이미지 상태가 일치하는 소견을 작성.
7. 종합 소견은 5~8문장, 전반적 피부 상태 평가와 개선 방향 포함.
8. 관리 권고사항은 RECOMMENDATION_GUIDELINES 섹션의 가이드라인을 참조하여 작성.
9. 의학적 진단이 아닌 피부 관리 관점의 소견임을 전제로 작성.
<!-- SYSTEM_PROMPT_END -->

---

## 단일 이미지 모드 (Single Image Mode)

**설명**: 원본 이미지만 사용하여 피부 분석 소견을 작성합니다.

<!-- SINGLE_IMAGE_USER_PROMPT_START -->
## User Prompt Template

## CÔTELEAF 피부 분석 결과
- 종합 점수: {overall_score}점 (10~90 스케일)
- 인지 나이: {perceived_age}세

## 18개 항목별 측정 점수 (10~90 스케일, 높을수록 양호)

### [색소]
  - 기미·잡티: {melasma_score}점 → {grade}
  - 주근깨: {freckle_score}점 → {grade}

### [홍조]
  - 홍조: {redness_score}점 → {grade}
  - 염증후 홍반: {post_inflammatory_erythema_score}점 → {grade}

### [트러블]
  - 여드름: {acne_score}점 → {grade}
  - 여드름 후 색소: {post_acne_pigment_score}점 → {grade}

### [모공]
  - 모공 크기: {pore_size_score}점 → {grade}
  - 모공 처짐: {pore_sagging_score}점 → {grade}

### [주름]
  - 눈가 주름: {eye_wrinkle_score}점 → {grade}
  - 팔자 주름: {nasolabial_wrinkle_score}점 → {grade}
  - 잔주름·깊은 주름: {fine_deep_wrinkle_score}점 → {grade}

### [텍스처]
  - 피부결 거칠기: {roughness_score}점 → {grade}

### [톤]
  - 피부 톤: {skin_tone_score}점 → {grade}
  - 칙칙함: {dullness_score}점 → {grade}
  - 톤 불균일: {uneven_tone_score}점 → {grade}

### [탄력]
  - 턱선 탄력: {jawline_blur_score}점 → {grade}
  - 볼 처짐: {cheek_sagging_score}점 → {grade}

### [피부 타입]
  - 피부 타입: {skin_type_score}점 / {skin_type_label} → {grade}

## 요청
첨부된 얼굴 원본 사진과 위 측정 점수를 함께 참고하여 아래 JSON 형식으로 응답하시오.

### 소견 작성 가이드라인
- **개별 항목 소견 작성 시 전체 피부 상태와 일관성을 유지하시오.**
- 종합 점수가 낮은 경우(예: 여드름 점수가 낮음), 관련 항목(여드름 후 색소, 염증성 홍조 등)의 소견도 이를 반영하여 작성하시오.
- 특정 항목 점수가 우수하더라도, 전체 피부 문제(예: 여드름)와 관련이 있다면 그 맥락을 소견에 포함하시오.
- 예: 여드름 점수가 낮고 주근깨 점수가 높더라도, 실제 이미지에서 여드름이 관찰된다면 주근깨 소견에도 '여드름으로 인한 붉은 자국' 등의 맥락을 반영하시오.
- 개별 항목 소견은 2~3문장으로 간결하되, 전체 피부 상태와의 연관성을 명확히 하시오.

```json 없이 순수 JSON만 출력:
{
  "metric_scores": {
    "melasma_score": 70.0,
    "freckle_score": 65.0,
    "redness_score": 68.0,
    "post_inflammatory_erythema_score": 72.0,
    "acne_score": 50.0,
    "post_acne_pigment_score": 68.0,
    "pore_size_score": 66.0,
    "pore_sagging_score": 64.0,
    "eye_wrinkle_score": 78.0,
    "nasolabial_wrinkle_score": 78.0,
    "fine_deep_wrinkle_score": 78.0,
    "roughness_score": 71.0,
    "skin_tone_score": 50.0,
    "dullness_score": 76.0,
    "uneven_tone_score": 67.0,
    "jawline_blur_score": 80.0,
    "cheek_sagging_score": 75.0,
    "skin_type_score": 78.0
  },
  "metric_reasons": {
    "melasma_score": "점수 근거 (1~2문장)",
    "freckle_score": "점수 근거 (1~2문장)",
    "redness_score": "점수 근거 (1~2문장)",
    "post_inflammatory_erythema_score": "점수 근거 (1~2문장)",
    "acne_score": "점수 근거 (1~2문장)",
    "post_acne_pigment_score": "점수 근거 (1~2문장)",
    "pore_size_score": "점수 근거 (1~2문장)",
    "pore_sagging_score": "점수 근거 (1~2문장)",
    "eye_wrinkle_score": "점수 근거 (1~2문장)",
    "nasolabial_wrinkle_score": "점수 근거 (1~2문장)",
    "fine_deep_wrinkle_score": "점수 근거 (1~2문장)",
    "roughness_score": "점수 근거 (1~2문장)",
    "skin_tone_score": "점수 근거 (1~2문장)",
    "dullness_score": "점수 근거 (1~2문장)",
    "uneven_tone_score": "점수 근거 (1~2문장)",
    "jawline_blur_score": "점수 근거 (1~2문장)",
    "cheek_sagging_score": "점수 근거 (1~2문장)",
    "skin_type_score": "점수 근거 (1~2문장)"
  },
  "metric_opinions": {
    "melasma_score": "소견 텍스트 (2~3문장)",
    "freckle_score": "소견 텍스트 (2~3문장)",
    "redness_score": "소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "소견 텍스트 (2~3문장)",
    "acne_score": "소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "소견 텍스트 (2~3문장)",
    "pore_size_score": "소견 텍스트 (2~3문장)",
    "pore_sagging_score": "소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "소견 텍스트 (2~3문장)",
    "roughness_score": "소견 텍스트 (2~3문장)",
    "skin_tone_score": "소견 텍스트 (2~3문장)",
    "dullness_score": "소견 텍스트 (2~3문장)",
    "uneven_tone_score": "소견 텍스트 (2~3문장)",
    "jawline_blur_score": "소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "소견 텍스트 (2~3문장)",
    "skin_type_score": "소견 텍스트 (2~3문장)"
  },
  "overall_opinion": "종합 소견 5~8문장",
  "recommendation": "관리 권고사항 (번호 목록 형식)"
}
```
<!-- SINGLE_IMAGE_USER_PROMPT_END -->

---

## 듀얼 이미지 모드 (Dual Image Mode)

**설명**: 원본 이미지와 복원 이미지를 함께 사용하여 두 이미지의 피부 상태를 비교 분석하고 각각에 대한 소견을 작성합니다.

<!-- REFERENCE_GUIDED_PROMPT_START -->
## CÔTELEAF 피부 분석 요청 — 복원 기반 원본 점수 정확도 향상 모드

첨부 이미지:
- **이미지 1**: 원본 얼굴 사진 (분석 대상)
- **이미지 2**: GAN 복원 얼굴 사진 (레퍼런스 — 조명·노이즈·압축 아티팩트 제거 상태)

---

## 분석 절차 (반드시 아래 순서대로 수행하십시오)

### Step 1. 복원본 기준선 파악 (이미지 2 먼저 분석)

복원 이미지에서 각 카테고리의 실제 피부 구조를 파악하고
`reference_baseline` 필드에 서술하십시오.

- **주름**: 눈가·팔자·이마 주름의 위치, 방향, 깊이
- **모공**: 코·볼 영역의 분포, 크기 범위
- **색소**: 기미·주근깨·여드름 후 색소의 위치, 농도, 범위
- **탄력**: 턱선 명확도, 볼 처짐 정도, 피부 탄력선
- **홍조**: 홍조·염증후 홍반의 분포 부위와 강도
- **트러블**: 여드름의 분포, 크기, 염증 정도
- **피부결**: 피부 표면의 거칠기 정도
- **톤**: 피부 톤의 밝기, 칙칙함, 불균일 정도
- **피부 타입**: 유분·수분 밸런스 상태

### Step 2. 원본 오탐 요인 역산 (이미지 1 분석)

원본 이미지에서 Step 1의 구조가 아래 요인에 의해
가려지거나 과장된 정도를 판단하십시오.
산출이 적용된 항목과 이유를 `correction_reasons` 필드에 기재하십시오.

| 오탐 요인 | 설명 |
|---|---|
| 조명 불균일 | 그림자가 주름·음영처럼 보이는 영역 |
| 광택·반사 | 피부 유분이 홍조·발적처럼 보이는 영역 |
| 초점 흐림 | 모공 경계가 불명확한 영역 |
| 색온도 편차 | 전반적 피부 톤 왜곡 (기미·톤 항목 영향) |
| 압축 아티팩트 | 색소 경계 번짐 (주근깨·기미 항목 영향) |

### Step 3. 최종 원본 점수 산출

Step 1(기준선)과 Step 2(보정)를 통합하여
원본 이미지의 18개 항목 점수(10~90 스케일)를 산출하십시오.

---

## 점수 평가 기준

{score_criteria_section}

---

## 항목별 구체적 점수 기준

### 트러블 (acne_score)

**보수적 산출 원칙:**
- 여드름 개수, 크기, 염증 정도를 엄격하게 판단하여 점수를 산출하십시오.
- 애매한 경우는 더 낮은 등급의 점수를 부여하십시오.
- 명확하지 않아도 의심스러운 여드름은 포함하여 판단하십시오.
- 조명으로 가려진 여드름도 고려하십시오.

**개수 기준:**
- 0개: 90점
- 1~3개: 75~85점
- 4~10개: 60~70점
- 11~20개: 45~55점
- 20개 이상: 10~40점

**염증 정도 보정:**
- 염증 없음: 기준 점수
- 경미한 염증(붉은기): -5점
- 중간 염증(농포): -10점
- 심한 염증(화농성): -15점

**크기 보정:**
- 작은 여드름(<2mm): 기준 점수
- 중간 여드름(2~3mm): -3점/개
- 큰 여드름(>3mm): -5점/개

**최종 점수 범위:** 10~90점

---

### 색소 (melasma_score, freckle_score)

**보수적 산출 원칙:**
- 기미, 주근깨의 범위와 농도를 엄격하게 판단하여 점수를 산출하십시오.
- 애매한 색소 침착도 포함하여 판단하십시오.
- 조명 그림자로 인한 가짜 색소도 고려하십시오.
- 흐릿한 색소도 실제 색소로 간주하십시오.

**기미 (melasma_score):**
- 없음: 90점
- 옅은 기미(광대 주변 흐릿): 70~80점
- 뚜렷한 기미(광대 주변 명확): 55~65점
- 넓은 기미(광대 외 얼굴 전체): 40~50점
- 심한 기미(농도 진함): 10~35점

**주근깨 (freckle_score):**
- 없음: 90점
- 1~5개: 80~85점
- 6~15개: 65~75점
- 16~30개: 50~60점
- 30개 이상: 10~45점

**농도 보정:**
- 옅은 갈색: 기준 점수
- 중간 갈색: -5점
- 진한 갈색: -10점

**최종 점수 범위:** 10~90점

---

### 홍조 (redness_score, post_inflammatory_erythema_score)

**보수적 산출 원칙:**
- 홍조, 홍반의 범위와 강도를 엄격하게 판단하여 점수를 산출하십시오.
- 애매한 붉은기도 포함하여 판단하십시오.
- 조명 반사로 인한 가짜 홍조도 고려하십시오.
- 흐릿한 홍조도 실제 홍조로 간주하십시오.

**홍조 (redness_score):**
- 없음: 90점
- 경미한 홍조(볼에 흐릿): 70~80점
- 뚜렷한 홍조(볼에 명확): 55~65점
- 넓은 홍조(볼 외 턱/이마): 40~50점
- 심한 홍조(전체 얼굴): 10~35점

**염증후 홍반 (post_inflammatory_erythema_score):**
- 없음: 90점
- 1~2개의 작은 자국: 75~85점
- 3~5개의 자국: 60~70점
- 6~10개의 자국: 45~55점
- 10개 이상의 자국: 10~40점

**강도 보정:**
- 옅은 붉은기: 기준 점수
- 중간 붉은기: -5점
- 진한 붉은기: -10점

**최종 점수 범위:** 10~90점

---

### 모공 (pore_size_score, pore_sagging_score)

**보수적 산출 원칙:**
- 모공 크기와 처짐 정도를 엄격하게 판단하여 점수를 산출하십시오.
- 애매한 모공도 포함하여 판단하십시오.
- 조명 각도로 인한 가짜 모공 그림자도 고려하십시오.
- 흐릿한 모공도 실제 모공으로 간주하십시오.

**모공 크기 (pore_size_score):**
- 매우 작음: 90점
- 작음: 75~85점
- 보통: 60~70점
- 큼: 45~55점
- 매우 큼: 10~40점

**모공 처짐 (pore_sagging_score):**
- 없음(원형 유지): 90점
- 경미한 처짐(약간 타원형): 75~85점
- 중간 처짐(세로형): 60~70점
- 심한 처짐(긴 세로형): 45~55점
- 매우 심한 처짐: 10~40점

**분포 보정:**
- 국소적(코만): 기준 점수
- 부분적(코+볼): -5점
- 전체적(전체 얼굴): -10점

**최종 점수 범위:** 10~90점

---

## 처방전 정보

{prescription_info}

---

## 맞춤형 제품 정보

{product_info}

---

## 소견 작성 가이드라인

- 각 항목 소견은 2~3문장으로 작성하되, Step 2에서 적용한 보정 내용을 반영하십시오.
- 종합 소견은 5~8문장으로 작성하고, 복원 기준선과 원본 상태의 차이를 서술하십시오.
- 소견 작성 시 "고객님" 표현을 사용하십시오.
- 점수 기준: SCORE_CRITERIA 섹션 참조 (10~90 스케일).
- **트러블, 색소, 홍조, 모공 점수는 반드시 "항목별 구체적 점수 기준" 섹션의 기준을 따르십시오.**
- JSON 출력 시 반드시 모든 문자열을 큰따옴표(")로 감싸고 모든 괄호를 닫으십시오.

## 응답 형식 (순수 JSON — ```json 없이)

{
  "reference_baseline": {
    "주름": "복원본에서 관찰된 주름 기준선 서술",
    "모공": "복원본에서 관찰된 모공 기준선 서술",
    "색소": "복원본에서 관찰된 색소 기준선 서술",
    "탄력": "복원본에서 관찰된 탄력 기준선 서술",
    "홍조": "복원본에서 관찰된 홍조 기준선 서술",
    "트러블": "복원본에서 관찰된 트러블 기준선 서술",
    "피부결": "복원본에서 관찰된 피부결 기준선 서술",
    "톤": "복원본에서 관찰된 톤 기준선 서술",
    "피부 타입": "복원본에서 관찰된 피부 타입 기준선 서술"
  },
  "correction_reasons": {
    "melasma_score":                       "산출 이유 (1~2문장)",
    "freckle_score":                       "산출 이유 (1~2문장)",
    "redness_score":                       "산출 이유 (1~2문장)",
    "post_inflammatory_erythema_score":    "산출 이유 (1~2문장)",
    "acne_score":                          "산출 이유 (1~2문장)",
    "post_acne_pigment_score":             "산출 이유 (1~2문장)",
    "pore_size_score":                     "산출 이유 (1~2문장)",
    "pore_sagging_score":                  "산출 이유 (1~2문장)",
    "eye_wrinkle_score":                   "산출 이유 (1~2문장)",
    "nasolabial_wrinkle_score":            "산출 이유 (1~2문장)",
    "fine_deep_wrinkle_score":             "산출 이유 (1~2문장)",
    "roughness_score":                     "산출 이유 (1~2문장)",
    "skin_tone_score":                     "산출 이유 (1~2문장)",
    "dullness_score":                      "산출 이유 (1~2문장)",
    "uneven_tone_score":                   "산출 이유 (1~2문장)",
    "jawline_blur_score":                  "산출 이유 (1~2문장)",
    "cheek_sagging_score":                 "산출 이유 (1~2문장)",
    "skin_type_score":                     "산출 이유 (1~2문장)"
  },
  "orig_metric_scores": {
    "melasma_score": 70.0,
    "freckle_score": 65.0,
    "redness_score": 68.0,
    "post_inflammatory_erythema_score": 72.0,
    "acne_score": 85.0,
    "post_acne_pigment_score": 75.0,
    "pore_size_score": 66.0,
    "pore_sagging_score": 64.0,
    "eye_wrinkle_score": 72.0,
    "nasolabial_wrinkle_score": 70.0,
    "fine_deep_wrinkle_score": 74.0,
    "roughness_score": 71.0,
    "skin_tone_score": 68.0,
    "dullness_score": 76.0,
    "uneven_tone_score": 67.0,
    "jawline_blur_score": 80.0,
    "cheek_sagging_score": 75.0,
    "skin_type_score": 78.0
  },
  "orig_metric_opinions": {
    "melasma_score": "원본 소견 (Step 2 보정 내용 반영, 2~3문장)",
    "freckle_score": "원본 소견",
    "redness_score": "원본 소견",
    "post_inflammatory_erythema_score": "원본 소견",
    "acne_score": "원본 소견",
    "post_acne_pigment_score": "원본 소견",
    "pore_size_score": "원본 소견",
    "pore_sagging_score": "원본 소견",
    "eye_wrinkle_score": "원본 소견",
    "nasolabial_wrinkle_score": "원본 소견",
    "fine_deep_wrinkle_score": "원본 소견",
    "roughness_score": "원본 소견",
    "skin_tone_score": "원본 소견",
    "dullness_score": "원본 소견",
    "uneven_tone_score": "원본 소견",
    "jawline_blur_score": "원본 소견",
    "cheek_sagging_score": "원본 소견",
    "skin_type_score": "원본 소견"
  },
  "orig_overall_score": 74.5,
  "orig_perceived_age": 38.0,
  "orig_overall_opinion": "종합 소견 5~8문장 (복원 기준선과 비교하여 원본 상태를 서술)",
  "recommendation": "관리 권고사항 (번호 목록)"
}
<!-- REFERENCE_GUIDED_PROMPT_END -->

<!-- DUAL_IMAGE_USER_PROMPT_START -->
## User Prompt Template

## CÔTELEAF 피부 분석 요청 (원본 vs 복원)

첨부된 두 장의 얼굴 사진(원본, 복원)을 분석하여 각 이미지에 대한 18개 항목 점수(10~90 스케일)를 직접 산출하고 소견을 작성하시오.

**점수 평가 기준**: SCORE_CRITERIA 섹션의 점수 기준을 참조하여 점수를 산출하십시오.

## 시스템 분석기 측정 점수 (참고용)

### 원본 이미지 (시스템 분석기 로직)
- 종합 점수: {orig_overall_score}점 (10~90 스케일)
- 인지 나이: {orig_perceived_age}세

### 복원 이미지 (시스템 분석기 로직)
- 종합 점수: {ideal_overall_score}점 (10~90 스케일)
- 인지 나이: {ideal_perceived_age}세

**참고**: 위 점수는 시스템 분석기 로직으로 측정한 점수입니다. LLM은 이 점수를 참고하되, 직접 이미지를 분석하여 독자적인 점수를 산출하십시오.

### 색소 (Pigmentation)
- 기미·잡티 (melasma_score): 피부색소 침착 정도
- 주근깨 (freckle_score): 멜라닌 색소 침착 정도

### 홍조 (Redness)
- 홍조 (redness_score): 피부 발적 정도
- 염증후 홍반 (post_inflammatory_erythema_score): 염증 후 남은 붉은 자국

### 트러블 (Acne & Marks)
- 여드름 (acne_score): 여드름 발생 정도
- 여드름 후 색소 (post_acne_pigment_score): 여드름 흔터 색소 침착

### 모공 (Pore)
- 모공 크기 (pore_size_score): 모공의 크기 정도
- 모공 처짐 (pore_sagging_score): 모공의 처짐 정도

### 주름 (Wrinkle)
- 눈가 주름 (eye_wrinkle_score): 눈 주위 주름 정도
- 팔자 주름 (nasolabial_wrinkle_score): 팔자 주름 정도
- 잔주름·깊은 주름 (fine_deep_wrinkle_score): 잔주름 및 깊은 주름 정도

### 텍스처 (Texture)
- 피부결 거칠기 (roughness_score): 피부 표면 거칠기 정도

### 톤 (Tone)
- 피부 톤 (skin_tone_score): 피부색의 밝기와 균일성
- 칙칙함 (dullness_score): 피부의 광택 저하 정도
- 톤 불균일 (uneven_tone_score): 피부색 불균형 정도

### 탄력 (Elasticity)
- 턱선 탄력 (jawline_blur_score): 턱선의 명확성
- 볼 처짐 (cheek_sagging_score): 볼 처짐 정도

### 피부 타입 (Skin Type)
- 피부 타입 (skin_type_score): 피부 타입 (지성·건성·복합성·중성)

---

## 맞춤형 처방전 정보 (M-Mix)
**중요**: 처방전은 시스템 자체 로직에 의해 이미 계산된 결과입니다. LLM은 이 처방전 정보를 참고하여 제품 추천 설명만 작성하십시오. 처방전을 다시 계산하거나 수정하지 마십시오.

피부 평가 점수 기반으로 계산된 처방전 비율입니다:
{prescription_info}

**처방 항목 설명**:
- M01: 톤&밝기 (dullness_score) - 비타민C, 나이아신아마이드 성분
- M02: 주름 (eye_wrinkle_score, nasolabial_wrinkle_score, fine_deep_wrinkle_score) - 레티놀, 펩타이드, 아데노신 성분
- M04: 탄력&처짐 (jawline_blur_score, cheek_sagging_score) - 콜라겐, 엘라스틴 성분
- M05: 색소침착 (melasma_score, freckle_score, post_acne_pigment_score) - 비타민C, 나이아신아마이드, 알부틴, 트라넥삼산 성분
- M06: 홍조 (redness_score, post_inflammatory_erythema_score) - 시카, 판테놀, 알란토인 성분
- M07: 모공 (pore_size_score, pore_sagging_score) - 살리실산, BHA, PHA 성분
- M08: 피부결 (roughness_score) - AHA, 효소, 각질 제거 성분
- M10: 트러블 (acne_score) - 살리실산, 티트리 오일, 나이아신아마이드 성분

**제품 추천 가이드라인**:
- 처방전 비율이 높은 항목(0.5% 이상)에 해당하는 성분이 포함된 제품을 우선 추천하십시오.
- 처방전 비율이 0%인 항목은 해당 카테고리의 제품을 추천하지 않으십시오.
- 제품은 실제 시판 중인 제품을 기준으로 하되, 성분 조성이 처방전과 일치하는 제품을 선택하십시오.
- 제품명은 "꼬드리브" 브랜드를 사용하십시오. (예: 꼬드리브 비타-C 앰플, 꼬드리브 레티놀 크림)

## 매칭된 제품 정보
**중요**: 아래 제품 목록은 시스템이 처방전 기반으로 이미 매칭한 실제 제품입니다. LLM은 제품명, 카테고리, 성분을 그대로 사용하여 추천 설명을 작성하십시오. 제품명을 변경하거나 새로운 제품명을 생성하지 마십시오.

{product_info}

---

## 요청
첨부된 두 장의 얼굴 사진(원본, 복원)과 위 측정 점수, 처방전 정보를 함께 참고하여 아래 JSON 형식으로 응답하시오.

### 소견 작성 가이드라인 (듀얼 이미지 모드)
- **원본 이미지와 복원 이미지를 비교하여 각각에 대한 소견을 작성하시오.**
- 원본 이미지 소견은 원본의 피부 상태를 기준으로 작성하시오.
- 복원 이미지 소견은 복원 후의 피부 상태를 기준으로 작성하시오.
- 두 이미지 간의 차이점을 명확히 구분하여 소견에 반영하시오.
- 종합 소견은 원본과 복원 이미지의 전반적 피부 상태를 비교하여 작성하시오.
- 관리 권고사항은 복원 이미지의 상태를 기준으로 작성하되, 원본과의 차이를 고려하시오.
- 소견 작성 시 "고객님" 표현을 사용하십시오.
- 개별 항목 소견은 2~3문장으로 간결하되, 각 이미지의 특성을 명확히 반영하시오.
- **JSON 출력 시 반드시 모든 문자열을 큰따옴표(")로 감싸고, 모든 중괄호와 대괄호를 닫으십시오. 응답이 중단되지 않도록 모든 필드를 완전히 작성하십시오.**

```json 없이 순수 JSON만 출력:
{
  "original_metric_scores": {
    "melasma_score": 70.0,
    "freckle_score": 65.0,
    "redness_score": 68.0,
    "post_inflammatory_erythema_score": 72.0,
    "acne_score": 50.0,
    "post_acne_pigment_score": 68.0,
    "pore_size_score": 66.0,
    "pore_sagging_score": 64.0,
    "eye_wrinkle_score": 78.0,
    "nasolabial_wrinkle_score": 78.0,
    "fine_deep_wrinkle_score": 78.0,
    "roughness_score": 71.0,
    "skin_tone_score": 50.0,
    "dullness_score": 76.0,
    "uneven_tone_score": 67.0,
    "jawline_blur_score": 80.0,
    "cheek_sagging_score": 75.0,
    "skin_type_score": 78.0
  },
  "restored_metric_scores": {
    "melasma_score": 70.0,
    "freckle_score": 82.0,
    "redness_score": 67.0,
    "post_inflammatory_erythema_score": 72.0,
    "acne_score": 50.0,
    "post_acne_pigment_score": 82.0,
    "pore_size_score": 66.0,
    "pore_sagging_score": 68.0,
    "eye_wrinkle_score": 78.0,
    "nasolabial_wrinkle_score": 78.0,
    "fine_deep_wrinkle_score": 78.0,
    "roughness_score": 71.0,
    "skin_tone_score": 50.0,
    "dullness_score": 76.0,
    "uneven_tone_score": 67.0,
    "jawline_blur_score": 80.0,
    "cheek_sagging_score": 75.0,
    "skin_type_score": 78.0
  },
  "original_metric_reasons": {
    "melasma_score": "원본 이미지 점수 근거 (1~2문장)",
    "freckle_score": "원본 이미지 점수 근거 (1~2문장)",
    "redness_score": "원본 이미지 점수 근거 (1~2문장)",
    "post_inflammatory_erythema_score": "원본 이미지 점수 근거 (1~2문장)",
    "acne_score": "원본 이미지 점수 근거 (1~2문장)",
    "post_acne_pigment_score": "원본 이미지 점수 근거 (1~2문장)",
    "pore_size_score": "원본 이미지 점수 근거 (1~2문장)",
    "pore_sagging_score": "원본 이미지 점수 근거 (1~2문장)",
    "eye_wrinkle_score": "원본 이미지 점수 근거 (1~2문장)",
    "nasolabial_wrinkle_score": "원본 이미지 점수 근거 (1~2문장)",
    "fine_deep_wrinkle_score": "원본 이미지 점수 근거 (1~2문장)",
    "roughness_score": "원본 이미지 점수 근거 (1~2문장)",
    "skin_tone_score": "원본 이미지 점수 근거 (1~2문장)",
    "dullness_score": "원본 이미지 점수 근거 (1~2문장)",
    "uneven_tone_score": "원본 이미지 점수 근거 (1~2문장)",
    "jawline_blur_score": "원본 이미지 점수 근거 (1~2문장)",
    "cheek_sagging_score": "원본 이미지 점수 근거 (1~2문장)",
    "skin_type_score": "원본 이미지 점수 근거 (1~2문장)"
  },
  "restored_metric_reasons": {
    "melasma_score": "복원 이미지 점수 근거 (1~2문장)",
    "freckle_score": "복원 이미지 점수 근거 (1~2문장)",
    "redness_score": "복원 이미지 점수 근거 (1~2문장)",
    "post_inflammatory_erythema_score": "복원 이미지 점수 근거 (1~2문장)",
    "acne_score": "복원 이미지 점수 근거 (1~2문장)",
    "post_acne_pigment_score": "복원 이미지 점수 근거 (1~2문장)",
    "pore_size_score": "복원 이미지 점수 근거 (1~2문장)",
    "pore_sagging_score": "복원 이미지 점수 근거 (1~2문장)",
    "eye_wrinkle_score": "복원 이미지 점수 근거 (1~2문장)",
    "nasolabial_wrinkle_score": "복원 이미지 점수 근거 (1~2문장)",
    "fine_deep_wrinkle_score": "복원 이미지 점수 근거 (1~2문장)",
    "roughness_score": "복원 이미지 점수 근거 (1~2문장)",
    "skin_tone_score": "복원 이미지 점수 근거 (1~2문장)",
    "dullness_score": "복원 이미지 점수 근거 (1~2문장)",
    "uneven_tone_score": "복원 이미지 점수 근거 (1~2문장)",
    "jawline_blur_score": "복원 이미지 점수 근거 (1~2문장)",
    "cheek_sagging_score": "복원 이미지 점수 근거 (1~2문장)",
    "skin_type_score": "복원 이미지 점수 근거 (1~2문장)"
  },
  "original_metric_opinions": {
    "melasma_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "freckle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "redness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "acne_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "pore_size_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "pore_sagging_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "roughness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "skin_tone_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "dullness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "uneven_tone_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "jawline_blur_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "skin_type_score": "원본 이미지 소견 텍스트 (2~3문장)"
  },
  "restored_metric_opinions": {
    "melasma_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "freckle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "redness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "acne_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "pore_size_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "pore_sagging_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "roughness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "skin_tone_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "dullness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "uneven_tone_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "jawline_blur_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "skin_type_score": "복원 이미지 소견 텍스트 (2~3문장)"
  },
  "original_overall_opinion": "원본 이미지 종합 소견 5~8문장",
  "restored_overall_opinion": "복원 이미지 종합 소견 5~8문장",
  "recommendation": "관리 권고사항 (번호 목록 형식)"
}
```

---

## 18개 측정 항목 상세

### 색소 (Pigmentation)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 기미·잡티 | melasma_score | 피부색소 침착 정도 |
| 주근깨 | freckle_score | 멜라닌 색소 침착 정도 |

### 홍조 (Redness)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 홍조 | redness_score | 피부 발적 정도 |
| 염증후 홍반 | post_inflammatory_erythema_score | 염증 후 남은 붉은 자국 |

### 트러블 (Acne & Marks)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 여드름 | acne_score | 여드름 발생 정도 |
| 여드름 후 색소 | post_acne_pigment_score | 여드름 흔터 색소 침착 |

### 모공 (Pore)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 모공 크기 | pore_size_score | 모공의 크기 정도 |
| 모공 처짐 | pore_sagging_score | 모공의 처짐 정도 |

### 주름 (Wrinkle)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 눈가 주름 | eye_wrinkle_score | 눈 주위 주름 정도 |
| 팔자 주름 | nasolabial_wrinkle_score | 팔자 주름 정도 |
| 잔주름·깊은 주름 | fine_deep_wrinkle_score | 잔주름 및 깊은 주름 정도 |

### 텍스처 (Texture)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 피부결 거칠기 | roughness_score | 피부 표면 거칠기 정도 |

### 톤 (Tone)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 피부 톤 | skin_tone_score | 피부 톤 밝기 |
| 칙칙함 | dullness_score | 피부 칙칙함 정도 |
| 톤 불균일 | uneven_tone_score | 피부 톤 불균일 정도 |

### 탄력 (Elasticity)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 턱선 탄력 | jawline_blur_score | 턱선 탄력 정도 |
| 볼 처짐 | cheek_sagging_score | 볼 처짐 정도 |

### 피부 타입 (Skin Type)
| 항목명 | 키 | 설명 |
|--------|-----|------|
| 피부 타입 | skin_type_score | 피부 타입 (지성·건성·복합성·중성) |

## 응답 JSON 구조

### 단일 이미지 모드 응답 JSON 구조

```json
{
  "metric_opinions": {
    "melasma_score": "소견 텍스트 (2~3문장)",
    "freckle_score": "소견 텍스트 (2~3문장)",
    "redness_score": "소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "소견 텍스트 (2~3문장)",
    "acne_score": "소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "소견 텍스트 (2~3문장)",
    "pore_size_score": "소견 텍스트 (2~3문장)",
    "pore_sagging_score": "소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "소견 텍스트 (2~3문장)",
    "roughness_score": "소견 텍스트 (2~3문장)",
    "skin_tone_score": "소견 텍스트 (2~3문장)",
    "dullness_score": "소견 텍스트 (2~3문장)",
    "uneven_tone_score": "소견 텍스트 (2~3문장)",
    "jawline_blur_score": "소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "소견 텍스트 (2~3문장)",
    "skin_type_score": "소견 텍스트 (2~3문장)"
  },
  "overall_opinion": "종합 소견 5~8문장 (전반적 피부 상태 평가와 개선 방향 포함)",
  "recommendation": "관리 권고사항 (3~5가지 항목, 구체적 케어 방법)"
}
```

### 듀얼 이미지 모드 응답 JSON 구조

```json
{
  "original_metric_opinions": {
    "melasma_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "freckle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "redness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "acne_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "pore_size_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "pore_sagging_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "roughness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "skin_tone_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "dullness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "uneven_tone_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "jawline_blur_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "skin_type_score": "원본 이미지 소견 텍스트 (2~3문장)"
  },
  "restored_metric_opinions": {
    "melasma_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "freckle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "redness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "acne_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "pore_size_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "pore_sagging_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "roughness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "skin_tone_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "dullness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "uneven_tone_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "jawline_blur_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "skin_type_score": "복원 이미지 소견 텍스트 (2~3문장)"
  },
  "original_overall_opinion": "원본 이미지 종합 소견 5~8문장",
  "restored_overall_opinion": "복원 이미지 종합 소견 5~8문장",
  "recommendation": "관리 권고사항 (번호 목록 형식)",
  "product_recommendations": {
    "matched_products": [
      {
        "product_id": "제품 ID",
        "product_name": "제품명",
        "category": "제품 카테고리",
        "key_ingredients": ["주요 성분1", "주요 성분2"],
        "efficacy": "제품 효능 설명",
        "match_score": 0.9,
        "match_reason": "매칭 이유"
      }
    ],
    "recommendation_summary": "전체 추천 요약 문장"
  }
}
```
<!-- DUAL_IMAGE_USER_PROMPT_END -->

---

## 듀얼 이미지 모드 - 점수 미제공 (Dual Image Mode - No Scores)

**설명**: 원본 이미지와 복원 이미지만 전달하여 Gemini가 직접 18개 항목 점수를 계산하고 소견을 작성합니다. 기존 측정 점수는 전달하지 않습니다.

<!-- DUAL_IMAGE_USER_PROMPT_NO_SCORES_START -->
## User Prompt Template (점수 미제공 모드)

## 꼬드리브 피부 분석 요청

첨부된 두 장의 얼굴 사진(원본, 복원)을 분석하여 각 이미지에 대한 18개 항목 점수(10~90 스케일)를 직접 산출하고 소견을 작성하시오.

**점수 평가 기준**: SCORE_CRITERIA 섹션의 점수 기준을 참조하여 점수를 산출하십시오.

### 색소 (Pigmentation)
- 기미·잡티 (melasma_score): 피부색소 침착 정도
- 주근깨 (freckle_score): 멜라닌 색소 침착 정도

### 홍조 (Redness)
- 홍조 (redness_score): 피부 발적 정도
- 염증후 홍반 (post_inflammatory_erythema_score): 염증 후 남은 붉은 자국

### 트러블 (Acne & Marks)
- 여드름 (acne_score): 여드름 발생 정도
- 여드름 후 색소 (post_acne_pigment_score): 여드름 흔터 색소 침착

### 모공 (Pore)
- 모공 크기 (pore_size_score): 모공의 크기 정도
- 모공 처짐 (pore_sagging_score): 모공의 처짐 정도

### 주름 (Wrinkle)
- 눈가 주름 (eye_wrinkle_score): 눈 주위 주름 정도
- 팔자 주름 (nasolabial_wrinkle_score): 팔자 주름 정도
- 잔주름·깊은 주름 (fine_deep_wrinkle_score): 잔주름 및 깊은 주름 정도

### 텍스처 (Texture)
- 피부결 거칠기 (roughness_score): 피부 표면 거칠기 정도

### 톤 (Tone)
- 피부 톤 (skin_tone_score): 피부색의 밝기와 균일성
- 칙칙함 (dullness_score): 피부의 광택 저하 정도
- 톤 불균일 (uneven_tone_score): 피부색 불균형 정도

### 탄력 (Elasticity)
- 턱선 탄력 (jawline_blur_score): 턱선의 명확성
- 볼 처짐 (cheek_sagging_score): 볼 처짐 정도

### 피부 타입 (Skin Type)
- 피부 타입 (skin_type_score): 피부 타입 (지성·건성·복합성·중성)

---

## 맞춤형 화장품 추천 안내
분석된 피부 상태를 기반으로 맞춤형 화장품을 추천하십시오. 다음 카테고리를 고려하여 제품을 선택하십시오:
- 색소 관리 (기미, 주근깨): 비타민C, 나이아신아마이드, 알부틴, 트라넥삼산 성분
- 주름 관리: 레티놀, 펩타이드, 아데노신 성분
- 홍조/민감성: 시카, 판테놀, 알란토인 성분
- 모공 관리: 살리실산, BHA, PHA 성분
- 피부결: AHA, 효소, 각질 제거 성분
- 수분/보습: 히알루론산, 세라마이드, 글리세린 성분
- 여드름: 살리실산, 티트리 오일, 나이아신아마이드 성분

---

## 요청
첨부된 두 이미지(원본, 복원)를 직접 분석하여 각 이미지에 대한 18개 항목 점수(10~90 스케일)를 각각 산출하고, 아래 JSON 형식으로 응답하시오.

### 소견 작성 가이드라인 (듀얼 이미지 점수 미제공 모드)
- **원본 이미지와 복원 이미지를 직접 분석하여 각각에 대한 점수와 소견을 작성하시오.**
- 점수는 10~90 스케일로 산출하며, 높을수록 양호한 상태임
- 원본 이미지 소견은 원본의 피부 상태를 기준으로 작성하시오.
- 복원 이미지 소견은 복원 후의 피부 상태를 기준으로 작성하시오.
- 두 이미지 간의 차이점을 명확히 구분하여 소견에 반영하시오.
- 종합 소견은 원본과 복원 이미지의 전반적 피부 상태를 비교하여 작성하시오.
- 관리 권고사항은 복원 이미지의 상태를 기준으로 작성하되, 원본과의 차이를 고려하시오.
- 소견 작성 시 "고객님" 표현을 사용하십시오.
- 개별 항목 소견은 2~3문장으로 간결하되, 각 이미지의 특성을 명확히 반영하시오.
- **JSON 출력 시 반드시 모든 문자열을 큰따옴표(")로 감싸고, 모든 중괄호와 대괄호를 닫으십시오. 응답이 중단되지 않도록 모든 필드를 완전히 작성하십시오.**

```json 없이 순수 JSON만 출력:
{{
  "original_metric_scores": {{
    "melasma_score": 70.0,
    "freckle_score": 65.0,
    "redness_score": 68.0,
    "post_inflammatory_erythema_score": 72.0,
    "acne_score": 50.0,
    "post_acne_pigment_score": 68.0,
    "pore_size_score": 66.0,
    "pore_sagging_score": 64.0,
    "eye_wrinkle_score": 78.0,
    "nasolabial_wrinkle_score": 78.0,
    "fine_deep_wrinkle_score": 78.0,
    "roughness_score": 71.0,
    "skin_tone_score": 50.0,
    "dullness_score": 76.0,
    "uneven_tone_score": 67.0,
    "jawline_blur_score": 80.0,
    "cheek_sagging_score": 75.0,
    "skin_type_score": 78.0
  }},
  "restored_metric_scores": {{
    "melasma_score": 70.0,
    "freckle_score": 82.0,
    "redness_score": 67.0,
    "post_inflammatory_erythema_score": 72.0,
    "acne_score": 50.0,
    "post_acne_pigment_score": 82.0,
    "pore_size_score": 66.0,
    "pore_sagging_score": 68.0,
    "eye_wrinkle_score": 78.0,
    "nasolabial_wrinkle_score": 78.0,
    "fine_deep_wrinkle_score": 80.0,
    "roughness_score": 74.0,
    "skin_tone_score": 50.0,
    "dullness_score": 76.0,
    "uneven_tone_score": 80.0,
    "jawline_blur_score": 80.0,
    "cheek_sagging_score": 78.0,
    "skin_type_score": 78.0
  }},
  "original_metric_opinions": {{
    "melasma_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "freckle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "redness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "acne_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "pore_size_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "pore_sagging_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "roughness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "skin_tone_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "dullness_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "uneven_tone_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "jawline_blur_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "원본 이미지 소견 텍스트 (2~3문장)",
    "skin_type_score": "원본 이미지 소견 텍스트 (2~3문장)"
  }},
  "restored_metric_opinions": {{
    "melasma_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "freckle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "redness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "post_inflammatory_erythema_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "acne_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "post_acne_pigment_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "pore_size_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "pore_sagging_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "eye_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "nasolabial_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "fine_deep_wrinkle_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "roughness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "skin_tone_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "dullness_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "uneven_tone_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "jawline_blur_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "cheek_sagging_score": "복원 이미지 소견 텍스트 (2~3문장)",
    "skin_type_score": "복원 이미지 소견 텍스트 (2~3문장)"
  }},
  "original_overall_score": 65.0,
  "original_perceived_age": 22.0,
  "restored_overall_score": 70.0,
  "restored_perceived_age": 21.0,
  "original_overall_opinion": "원본 이미지 종합 소견 5~8문장",
  "restored_overall_opinion": "복원 이미지 종합 소견 5~8문장",
  "recommendation": "관리 권고사항 (번호 목록 형식)",
  "product_recommendations": {{
    "matched_products": [
      {{
        "product_id": "제품 ID",
        "product_name": "제품명",
        "category": "제품 카테고리",
        "key_ingredients": ["주요 성분1", "주요 성분2"],
        "efficacy": "제품 효능 설명",
        "match_score": 0.9,
        "match_reason": "매칭 이유"
      }}
    ],
    "recommendation_summary": "전체 추천 요약 문장"
  }}
}}
```
<!-- DUAL_IMAGE_USER_PROMPT_NO_SCORES_END -->

---

## API 설정

### Gemini API 호출 설정
- **Temperature**: 0.3 (일관된 의료 소견용)
- **Max Output Tokens**: 
  - 단일 이미지 모드: 8192
  - 듀얼 이미지 모드: 16384 (두 이미지에 대한 소견을 위해 증가)
- **Max Retries**: 3
- **Retry Delay**: 2초

### 점수 제공 모드 (provide_scores)
- **True**: 점수를 제공하여 소견에 기반한 점수 조정 수행
- **False**: 점수를 제공하지 않고, Gemini가 직접 점수를 산출하도록 요청


