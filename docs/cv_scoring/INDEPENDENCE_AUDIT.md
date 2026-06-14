# 측정항목 점수 독립성 감사 (Cross-Talk Audit)

## 방법
1. **교차간섭 행렬**: 한 항목용 합성 결함만 주입 → 18개 점수 변화량(Δ) 측정. 비대각=중첩.
   (`tests/cv_scoring/crosstalk_matrix.py`)
2. **순수 단일채널 주입**으로 genuine 채널 공유와 주입기 아티팩트 분리.
3. **정적 코드 분석**: 각 분석기의 채널·ROI·임계.
4. **합성(composition) 감사**: 레이어 A(직교 10) / 레이어 B(표시 21) 분리 확인.

## 핵심 결론
- **종합점수(레이어 A, 직교 10항목)는 잘 직교화돼 있다.** a* 이중계상 방지를 위해 PIE 가
  직교 합성에서 의도적으로 제거됐고(`_compose_redness_lesion_scores`: "PIE 완전 제거"),
  각 신호가 1회만 반영된다. **PAP 이중계상 없음**(실측: PAP 주입 시 pigmentation_cov 구성요소
  melasma Δ=0; PAP 는 focal_lesion 에서만 사용).
- **표시 점수(레이어 B, 고객 노출 raw 18~21항목)는 독립적이지 않다.** 동일 물리 신호가
  여러 표시 점수를 동시에 끌어내린다 — 이것이 점검 대상의 실제 중첩이다.

## A. 채널 공유 중첩 (genuine — 순수 단일채널 주입으로 확증)

### A-1. a* 홍반 그룹: redness · PIE · acne · PAP
순수 cheek a* 상승만으로:
| a* 상승 | redness | PIE | acne | PAP |
|---|---|---|---|---|
| +0.3 | −25.6 | −0.1 | 0 | 0 |
| +0.6 | −31.9 | **−60.0** | 0 | 0 |

→ 단일 홍반 신호가 redness 와 PIE 를 **동시 감점**. 코드상 모두 a* 임계 사용:
`redness: a*>red_base_a+kσ`(cheek), `PIE: a* 고임계`, `acne: a*>base_a+2.2σ`(acne ROI),
`PAP: a*>max(base_a+1.8σ,142)`(pig ROI). acne/PAP 는 임계가 높아 약한 홍조엔 무반응이나,
강한 병변은 PIE 를 함께 끌어내림(행렬: acne→PIE −17, PAP→PIE −19).
- **레이어 A 영향: 없음**(PIE 직교 제거됨, redness/acne/PAP 별 카테고리).
- **레이어 B 영향: 있음** — 고객 리포트에 redness 와 PIE 가 같은 홍반으로 둘 다 감점되어 노출.
- **[해소 2026-06-10]** PIE 를 focal 잔여(diffuse 배경 제거)로 직교화 → redness 주입 시
  PIE Δ −60→+0.0. `crosstalk_matrix` 로 회귀 고정(`TestL6`). 상세: CHANGES.md §E.

### A-2. L* 톤 그룹: skin_tone · dullness · uneven_tone
순수 전역 L* 하강만으로: skin_tone −25.1, dullness +7.9(경미), uneven/skin_type 무반응.
→ skin_tone(ITA)과 dullness(L_norm)가 평균 L* 를 공유(경미 중첩). 코드상 둘 다 `L_mean` 사용.
- **[해소 2026-06-10]** dullness 를 LAB 크로마 C* 기반으로 재정의 → 순수 L* 변화에 불변. §F.
- 레이어 A: tone_score 한 카테고리로 묶여 1회 반영(완화됨).
- 레이어 B: skin_tone·dullness 가 어두운 피부에서 동반 감점.

## B. 형태(blob/texture) 누설 — 부분/특징크기 의존
- **dark-blob**: 순수 소형 점(freckle 타깃)은 freckle 만 움직이고 pore/melasma 무반응(격리 양호).
  그러나 **큰 어두운 패치(melasma)→pore_size −55**, **소형 점(pore)→freckle −26** 처럼
  blob_log 검출기들이 특징 크기에 따라 비대칭 누설. 형태(선형/원형)·크기 판별이 부족.
- **texture/edge**: roughness(LBP)·fine_deep(이마 local_std)·eye/nasolabial(Sobel)·
  jawline(Canny)·pore_sagging(Laplacian)이 모두 고주파 강도변화를 읽어, 전역 질감이 누설.

## C. 주입기 아티팩트 (점수 버그 아님 — 구분 필요)
행렬의 일부 큰 비대각 값은 합성 주입기가 광범위해서 생긴 것:
- `eye/nasolabial/fine_deep 주입 → freckle −98~−100`: 주입한 **어두운 주름 선**이 freckle
  blob_log 에 검출됨. (단, freckle 검출기가 선형 특징을 배제 못 하는 약한 실제 한계도 시사)
- `roughness 주입 → 거의 전 texture 지표`: 전역 백색노이즈가 모든 고주파 지표를 자극.
이들은 "측정 A 가 측정 B 를 점수로 중첩"이 아니라 "주입한 결함이 물리적으로 여러 특징을 가짐".

## D. config 메타데이터 불일치 (유지보수 이슈 — 점수 영향 없음)
`orthogonal_categories.source_measurements` 가 실제 합성 함수와 어긋남:
- `pigmentation_cov`: config=[melasma, freckle, **post_acne_pigment**] / 코드=melasma 만 사용.
- `spot_density`: config=[] / 코드=freckle 사용.
→ 점수는 코드대로 정상이나 메타데이터가 오해를 유발. 동기화 권장.

## 권장 사항
1. **레이어 B 표시 중첩 해소(우선)**: 
   - ✅ **[완료]** a* 그룹 redness↔PIE: PIE focal 잔여 직교화로 해소(§E, TestL6).
   - ✅ **[완료]** L* 톤: dullness 를 LAB 크로마 C*(휘도 직교축) 기반으로 재정의 → 순수 L*
     변화 시 dullness 변동 0.0(§F, TestL7). uneven_tone 은 분산 기반으로 이미 직교.
     잔여 dullness↔skin_tone(+14)은 b* 공유에 의한 물리적 결합(이중계상 아님).
2. **blob 검출기 형태 판별 강화**: 
   - freckle 은 이미 크기 게이트(br>8) 보유 → 대형 패치 차단됨. 주름선→freckle 은 합성
     하드라인 아티팩트(실제 주름은 연속 음영)로, 프로덕션 영향 제한적.
   - ⏸ **[보류]** pore 국소대비 게이트: melasma 누설을 줄이나 clean 미세pore 를 0 으로 밀어
     pore_size 의 count=0 폴백 불연속(91.2→49.6)을 건드림 → 별도 재보정 과제로 권고(§H).
3. ✅ **[완료]** config 메타데이터 동기화: pigmentation_cov/spot_density/tone_score 의
   source_measurements 를 실제 composition_function 과 일치(§G).
4. **회귀 고정**: `crosstalk_matrix.py` 를 CI 에 포함해, 독립이어야 할 쌍의 비대각 Δ 가
   임계를 넘으면 경고.

## 산출물
- `crosstalk_matrix.py`: 재사용 가능한 교차간섭 진단 도구 (`python -m tests.cv_scoring.crosstalk_matrix`).

---

# 부록: measurement_weights 소비 추적 — 종합점수 중복 가중 위험 (확정)

## 추적 경로 (정적 분석)
고객 노출 `overall_score` 의 산출 경로:
```
skin_scoring.py: SkinAnalyzer → self._layer_b.build(...) → overall_v18
  └ _report.py ReportLayer.build(): overall_raw = _compute_overall_score_report(m18)
      └ _compute_overall_score_report(): Σ mᵢ·wᵢ / Σw,  w = get_measurement_weights() (레이어B 18개)
```
직교 10 카테고리 합성(`_compute_overall_score`/`_compose_*`, score_composition.py)은 계산되어
**표시용 per-카테고리 점수(m3)** 로만 쓰이고, **종합점수에는 반영되지 않는다.**
즉 라이브 종합점수 = **18개 레이어B 항목의 평탄 가중합**.

## 확정된 위험
1. **중복 가중**: 상관된 항목 클러스터(주름 eye/naso/fine, 톤 skin_tone/dullness/uneven 등)가
   각자의 가중치를 합산해 그 공유 신호를 과대표현. (PIE·dullness 직교화로 일부 완화됐으나
   클러스터 내 잔여 상관은 여전.)
2. **설계와 불일치(정량)**: 차원별 실효 가중치가 직교 설계와 크게 다름.

   | 차원 | 레이어B 합산(라이브) | 직교 WEIGHTS(설계) |
   |---|---|---|
   | pigmentation | 0.117 | 0.220 |
   | erythema(redness+PIE) | 0.117 | 0.120 |
   | **focal_lesion(acne+PAP)** | **0.329** | **0.140** |
   | pore | 0.132 | 0.120 |
   | wrinkle | 0.121 | 0.160 |
   | roughness | 0.049 | 0.050 |
   | tone | 0.086 | 0.100 |
   | elasticity | 0.045 | 0.050 |
   | skin_type | 0.005 | 0.040 |

   특히 **focal_lesion 이 acne 단일 가중(0.283) 때문에 0.329 로, 직교 설계(0.140)의 2.3배**
   과대 가중. skin_type 은 0.005 로 과소(설계 0.040).

## 무관 확인 (중복 가중 아님)
- `apply_score_offset`(score_postprocess.py): measurement_weights 를 **전역 offset 의 비례
  배분**에만 사용. 종합 합산 아님 → 위험 없음.
- SafetyNet(`score_safety_net`): `max_score_limit`(90) **상한 클램프**만. 가중 합산 아님.

## 권장
- ✅ **[구현 완료 2026-06-10]** 종합점수를 직교 10 카테고리 합성으로 라우팅(`skin_scoring.py`,
  CHANGES §I). 동일 입력 비교: acne만 20 → 직교 74.5 vs 기존 63.0(과대 페널티 해소).
  레이어B 21항목은 표시 전용 유지, overall_score_legacy_v21 로 롤백 가능.
- 부수 효과: acne 과대 가중 해소. **단 종합점수 분포가 달라지므로 임상 재보정·검증 필요.**
- 대안(소폭): 라이브 경로를 유지하되 measurement_weights 를 직교 차원 합이 설계와 맞도록
  재정규화(특히 acne 가중 하향). 구조 변경 최소, 그러나 중복 가중 근본 해소는 아님.
