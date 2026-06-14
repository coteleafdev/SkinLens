# CV 점수 폴백 경로 정리 — 변경 요약

운영 코드 패치: `cv_scoring_fixes.patch` (4개 파일). config 변경: `config.json` (breakpoints 3개).

## 근본 패턴
`_core.analyze_all` 의 bare-함수 폴백(`except` 분기)은 `breakpoints` 섹션 값을 그대로
`_area_to_score`/`_count_to_score` 에 주입한다. 그러나 일부 항목은 (a) config 값의 단위
도메인이 측정과 어긋나거나, (b) 로더가 타입을 잘못 캐스팅해 폴백에서 점수가 붕괴/포화했다.
(주 경로인 전략 분석기는 analyzer-config 에서 읽고 내부 기본값으로 폴백하여 무사했음.)

흥미롭게도 wrinkle 3개 브레이크포인트의 단위 도메인이 서로 뒤바뀌어 있었다(과거 혼동 흔적):
eye/nasolabial = ratio(있어야 할 곳: magnitude), fine_deep = magnitude(있어야 할 곳: ratio).

## A. fine_deep_wrinkle_score — 단위 도메인 분리 (코드+config)
- `wrinkle_texture.py`: ratio 전용 `bp_fine_deep` 파라미터 추가, deep/fine_score 가 사용.
- `wrinkle_analyzer.py`: config 의 `bp_fine_deep` 전달.
- `_core.py`: 3개 wrinkle 호출부에 `bp_fine_deep` 전달.
- `config.json`: `fine_deep_wrinkle_score` magnitude(0~500) → **ratio(0~1)**.
- 효과: 항상 ~100 포화 → 100→49.5 단조. eye/nasolabial 불변.

## B. acne_score / post_acne_pigment_score — int 캐스팅 버그 (코드)
- **정정**: config 값은 정상(graduated 면적 비율)이었음. 원인은 폴백이 면적 비율 bp 를
  `_get_metric_bp_count()`(int 캐스팅, 0.0005→0)로 로드한 것.
- `tone_elasticity.py`: 폴백 `_get_metric_bp_count` → `_get_metric_bp`(float). **config 변경 없음.**
- 효과: acne 이진(100/0) → graduated(100→64.7→…→44.6) 단조. PAP 폴백도 함께 해소.

## C. eye_wrinkle_score / nasolabial_wrinkle_score — 도메인 교정 (config)
- 측정은 raw Sobel magnitude(수십)인데 config 값이 ratio(0~0.6 / 0~0.78)라 폴백에서 0 붕괴.
- 해당 breakpoints 값은 `_core` 만 소비(전략 분석기는 analyzer-config 사용) → config 교정이 안전.
- `config.json`: 두 항목을 내부 기본값과 동일한 **magnitude(0~115)** 로 교정.
- 효과: 폴백 경로 clean eye/nasolabial 0/0 → 97.7/96.9, 정상 단조 응답.

## 회귀 방지
- `test_cv_scoring_synthetic.py` 에 `TestL5_FallbackBreakpointDomain` 추가:
  eye/nasolabial 브레이크포인트가 magnitude 도메인인지(max_x>1) + config-bp 경로로 0 붕괴
  없는지 검증.

## D. pore_sagging_score — 합성 생성기 아티팩트 (프로덕션 무변경)

- **결론: pore_sagging 은 프로덕션 버그가 아님.** 앞서 config-bp 경로 clean≈20 으로 낮게
  나온 원인은, 합성 캔버스의 미세질감이 픽셀 단위 **백색잡음(std=3)** 이라 고역통과 필터인
  Laplacian(pore_sagging 의 지배 입력 e_lc)을 크게 부풀린 것(e_lc≈14.5). 실제 피부 질감은
  저주파이므로 이는 합성 입력의 비현실성 문제.
- 검증: 저주파(blur) 질감에서 e_lc≈4.0 → pore_sagging≈73 으로 정상화되며, 이 영역에서
  **내부 기본 bp 와 config bp 가 거의 일치**(68.5 vs 66.6) → config bp_sagging 도 정상.
- **수정: 운영 코드/ config 무변경.** `synth_faces.make_skin_canvas` 의 미세질감을 약한 blur
  로 저주파화(피부 유사)하도록만 보정 → pore_sagging clean 30→73, 단조성 유지.
  (부수 효과: pore_size·roughness baseline 도 더 현실적으로 상승, 색소 계열 불변.)

## E. PIE 직교화 — redness 와의 표시 중첩 해소 (코드)

- **문제(레이어 B)**: PIE 가 `a*>절대임계` 픽셀 면적을 측정해, 광역/국소 홍조(redness 가
  이미 측정)에도 발화 → 동일 a* 신호를 redness 와 PIE 가 고객 리포트에서 이중 감점.
- **수정(`redness_analyzer.py`)**: PIE 를 'diffuse 배경 제거 후 focal 잔여'로 직교화.
  `a_resid = a* − GaussianBlur(a*, σ=25)` 의 `a_resid > 6` 픽셀만 집계 → 균일·광역 홍조는
  배경과 함께 상쇄되고 국소 염증후 반점만 PIE 트리거.
- **효과(교차간섭 행렬)**: redness 주입 → PIE Δ **−60 → +0.0**, PIE 주입 → redness Δ
  −32 → −1.9. 타깃 반응 유지(redness −29, PIE focal −15.5).
- **테스트**: `inject_pie_focal`(국소 붉은 반점) 추가, PIE 단조성 테스트를 focal 주입기로
  교체. `TestL6_RednessPieOrthogonality` 로 직교성 회귀 고정. redness 주입기는 경계를
  blur 로 부드럽게 해 현실성↑.
- **주의**: 이는 PIE 점수 산출 알고리즘 변경이다. 직교성·방향성은 합성으로 검증되나,
  절대 점수 보정은 실제 임상 데이터로 재검증 권장.

## F. 톤 그룹 직교화 — dullness 를 skin_tone(휘도)과 분리 (코드)

- **문제(레이어 B)**: dullness 가 mean L* 항(L_norm 0.20)을 포함해 skin_tone(ITA=mean L*)과
  중복. 게다가 HSV 채도(S)는 휘도와 결합돼 있어(L*↓ 시 S↑) 단순 L_norm 제거로는 오히려
  결합이 악화됨(순수 L*↓ → dullness +7.9 → +11.3).
- **수정(`tone_elasticity.py`)**: dullness 의 채도 성분을 **LAB 크로마 C*=√(a*²+b*²)** 로
  교체. C* 는 L* 과 직교축이라 순수 휘도 변화에 불변(검증: L*-1.0 시 HSV_S 73→89 출렁 vs
  C* 20.4 불변). dullness = C_norm 0.70 + radiance 0.30.
- **효과(교차간섭)**: 순수 L*↓ → dullness 변동 **0.0**(완전 직교), skin_tone 주입 → dullness
  Δ +0.0. 탈채도 타깃 반응 유지(49.7→9.9). clean 49.2(원래 50.7과 유사).
- **테스트**: `TestL7_ToneGroupOrthogonality`(순수 L* 변화는 dullness 무영향, 탈채도는 감점).
- **잔여(물리적, 버그 아님)**: dullness 주입 → skin_tone Δ +14.2 는 휘도가 아니라 b*(황색도)
  공유 때문 — 탈채도는 실제 색조 변화이고 ITA 가 이를 반영하는 정상 동작. uneven_tone 은
  분산 기반으로 이미 직교.
- **주의**: dullness 점수 산출 변경 — 절대 보정은 임상 재검증 권장.

## G. config 메타데이터 동기화 (권장 3 — config, 점수 영향 없음)

`orthogonal_categories.source_measurements` 를 실제 composition_function 과 일치시킴:
- `pigmentation_cov`: [melasma, freckle, post_acne_pigment] → **[melasma_score]** (코드는 melasma 만 사용)
- `spot_density`: [] → **[freckle_score]** (코드는 freckle 사용)
- `tone_score`: [skin_tone, dullness, uneven] → **[skin_tone_score, uneven_tone_score]**
  (코드는 ITA×0.60 + uniformity×0.40; **dullness 는 어느 직교 카테고리에도 미사용** —
  레이어 B 표시 전용 항목임)
점수 산출은 코드대로라 무변, 메타데이터 정확도만 향상.

## H. blob 검출 크로마 게이트 + 폴백 절벽 제거 (구현 완료 2026-06-10)

> 이전엔 보류였으나(국소 대비 게이트가 clean 미세 pore 를 제거해 절벽 유발), 재보정 설계
> (`H_PORE_RECALIBRATION_DESIGN.md`)에 따라 **구현 완료**. 대상: `pore.py`.

세 부분으로 구성(`pore.py`):
- **Part 3 — 폴백 재보정**: clean baseline Laplacian `L_clean≈4.04`(합성 측정)을 91 에 앵커한
  `_BP_LAPLACIAN_FALLBACK_V2`. 기존 폴백은 clean 을 49.6 으로 매핑해 blob 경로(91.2)와
  불일치 → 절벽 원인이었음. 이제 두 경로가 clean 에서 ~91 로 수렴.
- **Part 2 — 연속 블렌드**: 이분 분기(`count>0 ? blob : 폴백`)를 신뢰도 가중
  `w·score_blob + (1−w)·score_tex`, `w = clamp(gated_count/6, 0, 1)` 로 교체 → 절벽 소멸.
- **Part 1 — 크로마 게이트**: blob 을 **region 피부 baseline 대비 절대 크로마 초과**로 판정,
  유채색 색소(melasma)는 제거하고 무채색 명도 함몰(모공)은 보존. melasma 는 큰 확산 패치라
  *로컬* 크로마 초과가 0 → baseline(중앙값) 대비 비교가 핵심.
- **합성 주입기 현실화**: `inject_melasma` 가 L*만 낮추던 것을 a*/b*(갈색) 추가로 변경(실제
  melasma 는 유채색). 무채색 darkening 으로는 크로마 게이트 검증 불가했기 때문. golden 갱신.

**효과(동일 base, 합성)**:
| | clean | melasma sev 0→1.2 누설 Δ | 진짜 모공 단조 |
|---|---|---|---|
| 신규(gated_blend) | 91.0 | **Δ ≈ 4** | 단조 ✓ |
| legacy | 91.2 | Δ ≈ 55 | — |

melasma→pore_size 누설 폭 약 93% 감소(Δ 55→4), clean baseline·단조성 유지. 회귀 테스트
`TestL8_PoreMelasmaIndependence` 3종 추가, 전체 하니스 86 passed.

- **롤백**: `analyze_pores(..., size_mode="legacy")` 또는 `blob_params={"chroma_gate":False}`.
- **주의**: pore_size 분포 변경 → `pore_score`(직교 가중 0.12) 경유 종합점수 소폭 영향.
  §I 임상 검증과 함께 재보정 권장. 게이트 파라미터(`tau_C=5`, `delta_L=1`)는 실데이터 튜닝 필요.

## I. 종합점수를 직교 합성으로 라우팅 (코드 — 독립성 핵심)

- **문제**: 고객 `overall_score` 가 레이어B 21항목 평탄 가중합(`_compute_overall_score_report`)
  으로 산출돼, (a) 상관 항목 클러스터 중복 가중, (b) acne 단일 가중(0.283)에 의한 focal_lesion
  과대 가중(실효 0.329 vs 설계 0.140), (c) 표시 카테고리(직교 10)와 종합 기반 불일치.
- **수정(`skin_scoring.py`)**: 종합점수를 이미 구축된 **직교 10 카테고리 합성**
  (`_compute_overall_score`+WEIGHTS, m3 기반)으로 라우팅. 차원당 1회 가중 + 표시=종합 일치.
  레이어B 21항목은 표시/LLM 호환(measurements_report)으로 유지, `overall_score_legacy_v21`
  필드로 기존 값 보존(롤백/비교용).
- **효과(동일 입력 비교)**:
  | 시나리오 | 직교(신규) | 레이어B(기존) |
  |---|---|---|
  | 모두 70 | 70.0 | 70.0 |
  | acne만 20 | **74.5** | 63.0 |
  | 주름3개 20 | 70.4 | 72.7 |
  | 색소 20 | 66.8 | 73.0 |
  acne 단일 악화의 과대 페널티(-11.5) 해소, 상관 주름 3항목의 1차원 통합, 설계 가중 복원.
- **주의(필수)**: 고객 종합점수 산출 방식의 근본 변경 → **점수 분포가 달라지므로 임상
  재보정·검증 후 배포**. 롤백은 `overall_score_legacy_v21` 사용 또는 본 패치 hunk 되돌림.

## 검증 (최종)
- 합성 하니스: L2 단조 21항목 + L5 폴백 도메인 + 골든 회귀 전부 통과 (83 passed, 1 skipped).
- 기존 analyzer 통합 테스트 8개 회귀 없음.
- 운영 코드 패치 6파일 + config 3개 브레이크포인트(A,C) — pore_sagging(D)은 테스트 측만 변경.
