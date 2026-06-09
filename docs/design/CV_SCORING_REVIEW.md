# CV 점수 측정 로직 상세 리뷰

> **문서 버전:** 1.0.0
> **대상 프로젝트:** SkinLens v1
> **작성일:** 2026-06-09
> **상태:** 리뷰 완료
> **목적:** LLM_SCORE_VARIABILITY_SOLUTION.md의 CV anchor 역할 수행 가능성 검증

---

## 0. 요약

현재 CV 파이프라인은 **결정론적 알고리즘**을 기반으로 28개 서브점수를 측정하며, 이를 10개 직교 출력으로 조합합니다. CV anchor 역할 수행이 가능하나, **재현성 검증**과 **파라미터 튜닝**이 필요합니다.

**주요 문제점:**
- 3개 항목 미구현 (PIH, dead_skin_score, smoothness_score)
- skimage 의존성 (blob_log, LBP)
- 하드코딩된 파라미터
- 환경 변수 민감성 검증 필요

---

## 1. 색소 분석 (`src/skin/analyzers/pigmentation.py`)

### 1.1 기미 점수 (melasma_score)

**알고리즘:**
- LAB 색공간 L 채널 strip-normalization
- L 임계값: -2.2 × std_L (capped 4.0-15.0)
- b 채널 임계값: base_b + 0.3 × std_b
- 형태학적 연산: close(7×7), open(5×5)
- 면적 비율 → 브레이크포인트 매핑

**장점:**
- LAB 색공간 사용 (조명 불변성)
- 상대 임계값 (std 기반)
- ROI 제외 (눈, 코, 입, 헤어라인, 목)

**문제점:**
- 하드코딩된 임계값
- 형태학적 커널 크기 고정

### 1.2 주근깨 점수 (freckle_score)

**알고리즘:**
- LoG blob detection (min_sigma=1.0, max_sigma=5.0)
- lentigo와 중복 제거
- L 채널 기준: L < base_L - 10
- 개수 → 브레이크포인트 매핑

**장점:**
- blob detection으로 소형 점 감지
- lentigo와 중복 제거

**문제점:**
- skimage 의존성 (blob_log)
- 하드코딩된 파라미터
- 잡티/검버섯 분리 로직 복잡

### 1.3 여드름 후 색소침착 점수 (pih_score)

**상태:** 미구현 (기본값 100점)

---

## 2. 주름 분석 (`src/skin/analyzers/wrinkle_texture.py`)

### 2.1 눈가 주름 (eye_wrinkle_score)

**알고리즘:**
- Sobel 엣지 검출
- 수직 성분 가중치 0.65, 크기 0.35
- ROI: left_canthus, right_canthus (내부 20-80%)

**장점:**
- Sobel 엣지 검출 (결정론적)
- ROI 기반 분석

**문제점:**
- CLAHE 전처리에 따른 브레이크포인트 다름
- 하드코딩된 가중치

### 2.2 미간 주름 (glabella_wrinkle_score)

**알고리즘:**
- Sobel 엣지 검출
- 수평 성분 가중치 0.65, 크기 0.35
- ROI: glabella

**장점:**
- ROI 기반 분석
- 결정론적

**문제점:**
- 하드코딩된 가중치

### 2.3 팔자 주름 (nasolabial_wrinkle_score)

**알고리즘:**
- Sobel 엣지 검출
- skin_mask 적용 (30% 이상 피부 영역)
- ROI: nasolabial_l, nasolabial_r

**장점:**
- skin_mask 적용으로 피부 영역만 분석
- ROI 기반 분석

**문제점:**
- 복잡한 좌표 계산
- 하드코딩된 좌표 비율

### 2.4 잔주름·깊은 주름 (fine_deep_wrinkle_score)

**알고리즘:**
- 이마 ROI (ROIManager 사용)
- Local standard deviation (9×9 윈도우)
- 임계값: fine(8-20), deep(20)
- 가중치: deep 0.6, fine 0.4

**장점:**
- ROIManager 사용 (중앙화)
- Local std로 깊이 측정
- 이마 ROI로 직교성 확보

**문제점:**
- CLAHE 전처리에 따른 임계값 다름
- 하드코딩된 임계값

---

## 3. 텍스처 분석 (`src/skin/analyzers/wrinkle_texture.py`)

### 3.1 거칠기 점수 (roughness_score)

**알고리즘:**
- LBP (Local Binary Pattern)
- Radius 1, 2, 3
- LBP 분산 → 브레이크포인트 매핑

**장점:**
- LBP는 텍스처 분석에 적합
- 다중 스케일 (radius 1-3)

**문제점:**
- skimage 의존성 (local_binary_pattern)

### 3.2 각질 점수 (dead_skin_score)

**상태:** 미구현 (기본값 100점)

### 3.3 매끄러움 점수 (smoothness_score)

**상태:** 미구현 (기본값 100점)

---

## 4. 복원 품질 분석 (`src/skin/analyzers/wrinkle_texture.py`)

### 4.1 노이즈 점수 (noise_score)

**알고리즘:**
- Gaussian blur 5×5 잔차
- skin_mask 적용
- 잔차 평균 → 브레이크포인트 매핑

**장점:**
- 결정론적
- skin_mask 적용

**문제점:**
- 하드코딩된 브레이크포인트

### 4.2 디테일 점수 (detail_score)

**알고리즘:**
- Gaussian blur 3×3 잔차
- skin_mask 적용
- 잔차 평균 → 브레이크포인트 매핑

**장점:**
- 결정론적
- skin_mask 적용

**문제점:**
- 하드코딩된 브레이크포인트

### 4.3 색상 균형 점수 (color_balance_score)

**알고리즘:**
- LAB 채널 std 평균
- skin_mask 적용
- (l_std + a_std + b_std) / 3 → 브레이크포인트 매핑

**장점:**
- LAB 색공간 사용
- 결정론적

**문제점:**
- 하드코딩된 브레이크포인트

---

## 5. 톤 분석 (`src/skin/analyzers/tone_elasticity.py`)

### 5.1 피부톤 점수 (skin_tone_score)

**알고리즘:**
- ITA (Individual Typology Angle) 기반
- LAB L*, b* 사용
- ITA = arctan2(L* - 50, b*) → 점수 변환

**장점:**
- ITA는 피부톤 분석 표준
- 결정론적

**문제점:**
- 하드코딩된 변환 공식

### 5.2 칙칙함 점수 (dullness_score)

**알고리즘:**
- L_norm 0.20, S_norm 0.50, radiance 0.30 가중치
- 하이라이트 비율 계산

**장점:**
- 다중 요소 고려
- 결정론적

**문제점:**
- 하드코딩된 가중치

### 5.3 얼룩톤 점수 (uneven_tone_score)

**알고리즘:**
- strip-norm L_std + block_std + 비대칭
- 블록 기반 분석 (10×10)
- 좌우 볼 비대칭 계산

**장점:**
- 다중 요소 고려
- 결정론적

**문제점:**
- 하드코딩된 가중치
- 복잡한 블록 분석 로직

---

## 6. 탄력 분석 (`src/skin/analyzers/tone_elasticity.py`)

### 6.1 볼 처짐 점수 (cheek_sagging_score)

**알고리즘:**
- 상하 행 너비 비율 계산
- 밝기 차이 계산
- 너비 비율 + 밝기 차이 → 점수

**장점:**
- 결정론적
- 기하학적 분석

**문제점:**
- 하드코딩된 좌표 비율
- 특수 케이스 처리 복잡

### 6.2 턱선 흐림 점수 (jawline_blur_score)

**알고리즘:**
- Sobel 수직 엣지 검출
- ROI: chin
- 엣지 강도 → 브레이크포인트 매핑

**장점:**
- 결정론적
- ROI 기반 분석

**문제점:**
- 하드코딩된 브레이크포인트

---

## 7. 피부타입 분석 (`src/skin/analyzers/tone_elasticity.py`)

### 7.1 지성 점수 (oily_score)

**알고리즘:**
- T-zone 광택 비율 계산
- HSV V > 210, S < 40 조건
- 광택 비율 → 브레이크포인트 매핑

**장점:**
- 결정론적
- ROI 기반 분석

**문제점:**
- 하드코딩된 임계값

### 7.2 건성 점수 (dry_score)

**알고리즘:**
- U-zone 건조 픽셀 비율 (S < 28)
- 각질 픽셀 비율 (V > 215, S < 35)
- skimage.measure.label로 대형 각질 제거

**장점:**
- 결정론적
- 다중 요소 고려

**문제점:**
- skimage 의존성 (measure.label)
- 하드코딩된 임계값

### 7.3 피지 점수 (sebum_score)

**알고리즘:**
- T-zone 0.6 + U-zone 0.4 가중치
- 광택 비율 → 브레이크포인트 매핑

**장점:**
- 결정론적
- 가중치 기반 조합

**문제점:**
- 하드코딩된 가중치

### 7.4 피부 타입 점수 (skin_type_score)

**알고리즘:**
- oily_score, dry_score 기반 분류
- 임계값 55 기준
- 균형 점수: mean × 0.6 + (100 - diff × 0.5) × 0.4

**장점:**
- 결정론적
- 분류 로직 명확

**문제점:**
- 하드코딩된 임계값

---

## 8. 트러블 분석 (`src/skin/analyzers/tone_elasticity.py`)

### 8.1 여드름 점수 (acne_score)

**알고리즘:**
- HSV 빨간 범위 필터 (S ≥ 60)
- LAB a* 홍반 필터 (2.2σ)
- LAB b* 주근깨 제거 (b* < base_b + 0.5σ)
- HSV V 밝기 필터 (V < 210)
- 밀도 점수 + 강도 점수 + 개수 패널티

**장점:**
- 다중 필터로 오탐 억제
- 결정론적
- 상대 임계값 사용

**문제점:**
- 복잡한 필터 체인
- 하드코딩된 파라미터

### 8.2 여드름 후 색소침착 점수 (post_acne_pigment_score)

**알고리즘:**
- LAB a* 강한 홍반 필터 (1.8σ)
- 활성 여드름 영역 제외
- 면적 비율 → 브레이크포인트 매핑

**장점:**
- 결정론적
- 활성 여드름 제거

**문제점:**
- 하드코딩된 임계값

### 8.3 국소 병변 (focal_lesion)

**알고리즘:**
- 여드름 밀도 점수 (직교 신호)

**장점:**
- 결정론적
- 직교 신호로 활용

---

## 9. 홍조 분석 (`src/skin/analyzers/strategies/redness_analyzer.py`)

### 9.1 홍조 점수 (redness_score)

**알고리즘:**
- global z-score (base_a 기준)
- local 홍조 비율 (1.5σ)
- telangiectasia (Canny 혈관 감지)
- 가중치: local 0.40, global 0.45, tela 0.15

**장점:**
- 다중 요소 고려
- 결정론적
- 상대 기준 우선

**문제점:**
- 하드코딩된 가중치
- Canny 파라미터 고정

### 9.2 염증후 홍반 점수 (post_inflammatory_erythema_score)

**알고리즘:**
- LAB a* 강한 홍반 필터 (1.8σ)
- 강도 패널티 계산
- 면적 비율 + 강도 패널티 조합

**장점:**
- 결정론적
- 강도 고려

**문제점:**
- 하드코딩된 임계값

---

## 10. 모공 분석 (`src/skin/analyzers/pore.py`)

### 10.1 모공 크기 점수 (pore_size_score)

**알고리즘:**
- LoG blob detection (다중 임계값)
- NMS (cKDTree 최적화)
- CLAHE 전처리
- sigma 중앙값 → 브레이크포인트 매핑

**장점:**
- cKDTree 최적화 (O(n log n))
- 다중 임계값
- 결정론적

**문제점:**
- skimage 의존성 (blob_log)
- scipy 의존성 (cKDTree)
- 하드코딩된 파라미터

### 10.2 모공 늘어짐 점수 (pore_sagging_score)

**알고리즘:**
- Otsu 이진화
- 타원 적합 (fitEllipse)
- 타원비 > 1.45 필터
- Laplacian 텍스처 보조

**장점:**
- 결정론적
- 타원비 기준 명확

**문제점:**
- 하드코딩된 임계값
- 복잡한 폴백 로직

---

## 11. 전체 평가

### 11.1 장점

1. **결정론적 알고리즘**: Sobel, Gaussian blur, LAB 변환 등 재현성 높음
2. **ROI 기반 분석**: 특정 영역 집중 분석
3. **skin_mask 적용**: 피부 영역만 분석
4. **직교 신호 분해**: 28개 서브점수 → 10개 직교 출력
5. **상대 임계값**: std 기반 임계값으로 환경 변수 적응

### 11.2 문제점

1. **미구현 항목**: PIH, dead_skin_score, smoothness_score (기본값 100점)
2. **skimage 의존성**: blob_log, LBP, measure.label 등 (선택적 의존이지만 실패 시 폴백 부족)
3. **하드코딩된 파라미터**: 임계값, 가중치, 브레이크포인트
4. **환경 변수 민감성**: 조명, 노이즈에 대한 강건성 검증 필요
5. **재현성 검증 부족**: 동일 이미지 → 동일 점수 검증 필요

### 11.3 권장 개선 방향

1. **MDC 측정**: 각 메트릭별 σ, ICC, MDC 측정
2. **파라미터 외부화**: config 파일로 이동
3. **미구현 항목 구현**: PIH, dead_skin_score, smoothness_score
4. **환경 변수 강건성**: 조명/노이즈 변화에 대한 테스트
5. **skimage 대안**: pure OpenCV 구현 고려
6. **재현성 검증**: 동일 이미지 N회 측정으로 σ 확인

---

## 12. CV Anchor 역할 수행 가능성

### 12.1 결론

**현재 CV 로직은 CV anchor 역할 수행 가능**

이유:
- 결정론적 알고리즘 기반
- 상대 임계값으로 환경 변수 적응
- ROI 기반 정밀 분석
- 직교 신호 분해로 신호 분리

### 12.2 선행 조건

1. **MDC 측정**: 각 메트릭별 신뢰도 확인
2. **파라미터 튜닝**: 하드코딩된 파라미터 최적화
3. **미구현 항목 구현**: 3개 미구현 항목 완성
4. **재현성 검증**: 동일 이미지 → 동일 점수 확인

### 12.3 우선순위

1. **MDC 측정 스크립트 구현** (가장 중요)
2. **미구현 항목 구현**
3. **파라미터 외부화**
4. **환경 변수 강건성 테스트**

---

## 13. 측정항목 목록

### 13.1 색소 (3항목)
- melasma_score
- freckle_score
- pih_score (미구현)

### 13.2 주름 (4항목)
- eye_wrinkle_score
- glabella_wrinkle_score
- nasolabial_wrinkle_score
- fine_deep_wrinkle_score

### 13.3 텍스처 (3항목)
- roughness_score
- dead_skin_score (미구현)
- smoothness_score (미구현)

### 13.4 복원 품질 (3항목)
- noise_score
- detail_score
- color_balance_score

### 13.5 톤 (3항목)
- skin_tone_score
- dullness_score
- uneven_tone_score

### 13.6 탄력 (2항목)
- cheek_sagging_score
- jawline_blur_score

### 13.7 피부타입 (5항목)
- oily_score
- dry_score
- sebum_score
- skin_type_label
- skin_type_score

### 13.8 트러블 (3항목)
- acne_score
- post_acne_pigment_score
- focal_lesion

### 13.9 홍조 (2항목)
- redness_score
- post_inflammatory_erythema_score

### 13.10 모공 (3항목)
- pore_size_score
- pore_count
- pore_sagging_score

**총 28개 항목** (미구현 3개 제외: pih_score, dead_skin_score, smoothness_score)

---

## 참고 문서

- `LLM_SCORE_VARIABILITY_SOLUTION.md` - LLM 점수 변동성 해결 방안
- `src/skin/analyzers/pigmentation.py` - 색소 분석 구현
- `src/skin/analyzers/wrinkle_texture.py` - 주름/텍스처/복원 품질 분석 구현
- `src/skin/analyzers/tone_elasticity.py` - 톤/탄력/피부타입/트러블 분석 구현
- `src/skin/analyzers/strategies/redness_analyzer.py` - 홍조 분석 구현
- `src/skin/analyzers/pore.py` - 모공 분석 구현
