# §H 모공 검출 재보정 설계 (melasma 누설 차단 + 폴백 절벽 제거)

대상 파일: `src/skin/analyzers/pore.py` (`analyze_pores`, `_collect_pore_blobs`)
연계 지표: `pore_size_score` (Layer B) → `pore_score` (Layer A 직교 카테고리)
목표: melasma→pore_size 교차상관 r=0.92 → < 0.30, **동시에** clean 피부 점수 안정.

---

## 1. 문제 정의 (원인은 둘, 둘 다 고쳐야 함)

### 원인 A — 검출 누설 (색맹 검출기)
`_collect_pore_blobs`는 **반전 명도(inverted intensity)** 에 LoG(`blob_log`)를 적용해 어두운 점을
찾습니다. 모공(피부 함몰의 그림자)과 melasma(갈색 색소 반점)는 **둘 다 명도 극소점**이라
검출기가 구분하지 못합니다 → 색소 반점이 모공으로 카운트되어 r=0.92.

### 원인 B — 폴백 절벽 (이분 분기 + 경로 간 보정 불일치)
`analyze_pores` L209–220:
```
if pore_total_count > 0:   # blob 경로: min(size_from_sigma, density) → clean ≈ 91.2
else:                      # Laplacian 폴백: _BP_LAPLACIAN_FALLBACK → clean ≈ 49.6
```
같은 clean 피부인데 두 경로가 **91 vs 49** 로 다르게 보정돼 있습니다(clean 합성 Laplacian
≈4.3 → 폴백 ~49). 따라서 단순 게이트로 blob을 제거해 count→0 이 되면 91→49 **절벽**으로 추락.
이전 프로토타입(국소대비 게이트)이 실패한 이유: 게이트가 melasma뿐 아니라 **흐린 진짜 모공**도
제거 → clean에서 count=0 → 절벽.

---

## 2. 설계 (3부)

### Part 1 — 크로마 인식 게이트 (원인 A 해결, 대비 게이트 대체)
핵심 통찰: **모공은 무채색 명도 함몰, melasma는 유채색 갈색 반점.** 대비가 아니라 **색(LAB 크로마)**
으로 게이트하면, 흐린 진짜 모공(무채색)은 살리고 색소 반점(유채색)만 제거 → 프로토타입의 실패 모드 회피.

각 후보 blob `(y, x, σ)` 에 대해:
- 중심 패치: 반경 ≈ `1.5σ`, 주변 링: 반경 `3σ–5σ`.
- `C* = sqrt(a*² + b*²)` (LAB), `chroma_excess = mean(C*_center) − mean(C*_ring)`.
- `intensity_dip = mean(L_ring) − mean(L_center)`.
- **모공 판정(유지)**: `intensity_dip > δ_L` **AND** `chroma_excess < τ_C`  (어둡지만 무채색)
- **melasma 판정(제거)**: `chroma_excess ≥ τ_C`  (주변보다 갈색 → 색소)

초기값(합성+실데이터로 보정): `δ_L ≈ 4` (L* 단위), `τ_C ≈ 5` (크로마 단위).
구현 위치: `_collect_pore_blobs` 의 NMS 직후, blob 좌표로 원본 LAB에서 패치 샘플링하여 필터.
> 주의: 게이트는 **blob 개수만 줄이고 점수 경로는 Part 2가 흡수** → 절벽 발생 안 함.

### Part 2 — 연속 점수 (원인 B 해결, 이분 분기 제거)
하드 분기를 **신뢰도 가중 블렌드**로 교체:
```
gated_count = len(pores_kept)                 # Part 1 통과 blob 수
score_blob  = min(size_from_sigma, density)   # gated pores 기준 (기존 L209–217)
score_tex   = _area_to_score(e, _BP_LAPLACIAN_FALLBACK_v2)   # Part 3 재보정 폴백
w           = clamp(gated_count / N_REF, 0, 1)   # N_REF ≈ 6
pore_size_score = w * score_blob + (1 - w) * score_tex
```
- gated_count 많음 → w→1 (blob 경로 지배).
- gated_count 0 (clean 이거나 melasma 전량 제거) → w→0 (텍스처 경로) — 그리고 텍스처 경로는
  Part 3로 **clean을 높게** 보정 → 추락 없음.
- count 다∼0 사이를 **연속 전이** → 절벽 소멸.

### Part 3 — 텍스처 폴백 재보정 (두 경로가 clean에서 일치하도록)
현재 `_BP_LAPLACIAN_FALLBACK` 은 clean Laplacian(~4.3)을 ~49로 매핑 → blob 경로(91)와 불일치.
clean 매끄러운 피부 = 모공 적음 = **높은 점수**가 되도록 재앵커.

권장 절차(수치 추정 금지, 측정 기반):
1. clean 기준 Laplacian `L_clean` 측정: 합성 저주파 캔버스 + 실제 clean 샘플 N장에서
   `_pore_texture_laplacian_mean(forehead,cheeks,nose)` 분포의 중앙값.
2. 새 브레이크포인트를 `L_clean → 88` 에 앵커. 예시(측정 후 확정):
   ```
   _BP_LAPLACIAN_FALLBACK_v2 = [
       (0.0, 95), (L_clean, 88), (L_clean*1.8, 72),
       (L_clean*3.0, 55), (L_clean*5.0, 38), (L_clean*8.0, 18), (L_clean*12, 0)
   ]
   ```
3. (선택, 더 견고) **상대 텍스처**: 얼굴 내 가장 매끄러운 패치의 Laplacian을 0-모공 앵커로 삼아
   조명·피부차로 인한 절대 baseline 이동 제거.

→ Part 2+3 로 blob 경로(w→1)와 텍스처 경로(w→0)가 clean에서 **모두 ~88–91** 로 수렴.

---

## 3. 검증 계획 (synth 하니스 + crosstalk)

`tests/cv_scoring/` 에 추가:
1. **연속성**: gated_count 를 高→0 으로 sweep, 단계당 |Δscore| < 8 (91→49 점프 부재 확인).
2. **누설 차단**: clean + melasma 주입(강도 sweep) → pore_size 가 HIGH·평탄 유지,
   `crosstalk: melasma→pore_size |r| < 0.30` (기존 0.92).
3. **진짜 모공 단조성**: 모공 확대 주입 → pore_size 단조 감소(VERIFIED_MONOTONIC 유지).
4. **clean baseline 일치**: clean → pore_size ∈ [85, 95] 이고, w→1 한계와 w→0 한계가 ±5 이내.
5. **회귀**: golden_scores.json pore 항목 허용오차 내, 전체 하니스 83+ pass.
6. **crosstalk 재측정(N 확대)**: melasma↔pore_size 하락 + 신규 누설 무발생 확인
   (`python -m tests.cv_scoring.crosstalk_matrix`).

---

## 4. 구현 순서 (권장)

1. Part 3 먼저 — 폴백 재보정으로 **절벽 자체를 제거**(게이트 없이도 count→0 시 안전).
   → 이 시점에서 검증 1·4 통과해야 함.
2. Part 2 — 블렌드 도입(이분 분기 제거). 검증 1 재확인.
3. Part 1 — 크로마 게이트 추가. 검증 2·3 으로 누설 하락 확인.
4. crosstalk 재측정(검증 6)으로 r=0.92→<0.30 확정.

> 순서가 핵심: **폴백 재보정(Part 3)을 게이트(Part 1)보다 먼저** 해야 게이트가 count를 줄여도
> 추락하지 않는다. 프로토타입 실패는 게이트를 먼저 넣었기 때문.

---

## 5. 위험 / 롤백

- 크로마 게이트 + 블렌드는 pore_size 분포를 바꿈 → pore_size 브레이크포인트 임상 재보정 가능성.
- `pore_size_mode = "legacy" | "gated_blend"` 플래그(config)로 신구 경로 토글, 기본 legacy 로 두고
  검증 후 전환. 롤백 시 플래그만 변경.
- pore_size 는 Layer A `pore_score`(직교 가중 0.12)에 기여하므로 종합점수에도 소폭 영향 →
  §I 임상 검증과 함께 묶어 재보정 권장.
