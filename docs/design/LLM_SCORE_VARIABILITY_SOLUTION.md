# LLM 측정 점수 변동성 해결 방안

> **문서 버전:** 1.2.0
> **대상 프로젝트:** SkinLens v1
> **작성일:** 2026-06-09
> **상태:** 제안 단계
> **변경:** MULTI_COMPARISON_DESIGN.md 병합 - 비교 방식 디자인 포함, 상세 설명 추가

---

## 0. 요약 (TL;DR)

LLM 점수가 호출마다 0~9점 변동하는 문제는 **"줄여야 할 잡음"이 아니라 "LLM을 측정기로 잘못 쓰고 있다"는 신호**다. 따라서 최선의 해법은 변동성을 평활화하는 것이 아니라 **측정기의 역할을 결정론적 CV 파이프라인으로 옮기고, LLM은 보조·정성 역할로 제약**하는 것이다.

**권장 결정 규칙:**

> 정량 점수 = CV(결정론) backbone + LLM은 rubric·reference anchor로 제약한 보조 성분.
> 시계열 추적은 **단일 pairwise 호출**(temperature≈0, N회 median)로 수행.
> 세션 간 변화가 **MDC(최소 검출 가능 변화)** 를 넘고, CV·LLM이 방향까지 일치할 때만 "개선/악화"로 판정.

**우선순위(가성비 순):** ③ pairwise + ④ MDC → ① CV anchor → ② 출력 제약 → ⑤ 캘리브레이션.

---

## 1. 문제 재정의

### 1.1 변동성의 본질

| 관찰 | 잘못된 해석 | 올바른 해석 |
|------|------------|------------|
| 같은 이미지가 호출마다 0~9점 다름 | "LLM 점수를 더 안정화하면 된다" | "LLM은 재현 가능한 절대 스칼라(absolute scalar)를 내는 도구가 아니다" |

LLM을 **측정기(instrument)** 로 쓰는 한 변동성은 본질적으로 남는다. 측정기에 요구되는 핵심 속성은 **재현성(test-retest reliability)** 인데, 확률적 생성 모델은 이 속성을 보장하지 못한다.

### 1.2 변동성의 3가지 원인과 직접 대응

| 원인 | 대응 계층 |
|------|----------|
| LLM 모델의 확률적 특성 | ② temperature≈0 + N회 median |
| 이미지 인식의 미세한 차이 | ② 고정 reference anchor / 동일 전처리 |
| 프롬프트 해석의 변동 | ② rubric anchoring + 이산 band + structured output |

### 1.3 변동성이 가장 아픈 지점

분산은 **두 절대 점수의 차이를 계산할 때 누적**된다.

```
Var(S2 − S1) = Var(S1) + Var(S2) ≈ 2σ²   →  차이의 표준편차 = σ√2
```

즉 "1차 채점 → 2차 채점 → 차이"라는 시계열 추적 방식이 변동성을 **두 배로 증폭**시킨다. 제품 효과 추적이 어려운 근본 원인이 여기에 있다(③에서 해결).

**수학적 배경:**
- 두 독립 랜덤 변수 X, Y의 차이 D = X - Y의 분산: Var(D) = Var(X) + Var(Y)
- X와 Y가 동일한 분포에서 나온 경우: Var(D) = 2σ²
- 표준편차: SD(D) = √(2σ²) = σ√2 ≈ 1.414σ
- 95% 신뢰구간: ±1.96 × σ√2 ≈ ±2.77σ

**실제 예시:**
- LLM 점수 표준편차 σ = 3점인 경우
- 두 세션 차이의 표준편차 = 3 × 1.414 = 4.24점
- 95% 신뢰구간 = ±2.77 × 3 = ±8.31점
- 즉, 실제 변화가 없어도 -8점 ~ +8점 범위에서 차이가 나타날 수 있음

---

## 2. 권장 아키텍처 (5계층)

### ① 측정기는 CV, LLM은 보조

- 결정론적 CV 파이프라인(HSV saturation, LAB a*/b* 필터 등)은 동일 이미지 → 항상 동일 점수. **재현 가능한 숫자가 필요하면 이것이 측정기다.**
- 정량 점수의 backbone = CV. LLM은 CV가 못 잡는 것(전체적 인상, 인지나이, 맥락 해석, 사람이 읽을 서술)에만 사용.
- **주의:** LLM 점수가 합성 점수에 가중 반영되는 구조라면, LLM 분산은 그 가중치에 비례해 최종 점수로 전파된다. 변동성 큰 성분의 비중을 낮추는 것 자체가 레버다.

**CV 파이프라인 예시:**
- **색소 침착도**: HSV 채도 채널에서 특정 범위 픽셀 비율 계산
- **색조 균일성**: LAB 색공간에서 a*, b* 채널의 표준편차 계산
- **주름 깊이**: 엣지 검출 + 그라디언트 강도 분석
- **피부 결 텍스처**: Gabor 필터 또는 Local Binary Pattern (LBP) 특징 추출

**장점:**
- 재현성: 동일 이미지 → 항상 동일 결과
- 속도: GPU 가속 가능, LLM 호출보다 빠름
- 비용: API 호출 비용 없음
- 디버깅: 결정론적이라 문제 원인 파악 용이

**단점:**
- 복잡한 패턴 인식 어려움 (전체적 인상, 맥락)
- 높은 수준의 추론 부족 (인지나이, 종합적 판단)
- 초기 개발 비용: 알고리즘 설계 및 튜닝 필요

### ② LLM이 점수를 내야 할 때 — 출력 공간 제약

LLM 채점을 완전히 없앨 수 없는 경우, 출력 공간을 좁혀 분산을 억제한다.

- **샘플링:** `temperature ≈ 0`, 가능하면 seed 고정.
- **집계:** N회 호출 후 **median**(평균 아님 — 이상치에 강건). 분산은 σ/√N로 감소. 단, *체계적 bias는 평균으로 제거되지 않음*에 유의.
- **reference anchor:** 알려진 점수의 고정 기준 이미지를 함께 입력하고 그에 *상대적으로* 채점(기존 reference-guided scoring 강화).
- **rubric anchoring:** 각 점수 band를 구체 기준으로 고정.
  - 예: `40~50 = 3개 존 이상에서 기미 가시, 경계 흐림` 등.
- **이산화:** 연속 0~100 대신 ordinal band(예: 1~5 Likert)로 받고 필요 시 세분화. 연속 척도는 허위 정밀도와 분산만 키운다.
- **structured output 강제** + (선택) **CV prior로 bound:** "CV가 X로 측정했다, ±Δ 내에서 근거가 있을 때만 조정하라"로 드리프트 한계 설정.

**상세 설명:**

**Temperature 설정:**
- `temperature = 0`: 가장 결정론적 출력, 재현성 최대
- `temperature = 0.1-0.3`: 약간의 창의성 허용, 변동성 적게 증가
- `temperature > 0.5`: 창의성 증가, 변동성 크게 증가 (권장하지 않음)

**Median vs Mean:**
- Median: 이상치에 강건, 비대칭 분포에서 안정적
- Mean: 이상치에 민감, 정규분포 가정 시 최적
- LLM 출력은 종종 비대칭 분포를 따르므로 median 권장

**N회 호출 효과:**
- N=1: σ (기준)
- N=3: σ/√3 ≈ 0.58σ (42% 감소)
- N=5: σ/√5 ≈ 0.45σ (55% 감소)
- N=10: σ/√10 ≈ 0.32σ (68% 감소)
- 비용 고려: N=5가 가성비 좋음

**Rubric Anchoring 예시:**
```
점수 band 정의:
- 0-20점: 심각 - 전체 얼굴의 50% 이상에서 문제 심각
- 21-40점: 중등 - 20-50% 범위에서 문제 가시
- 41-60점: 경미 - 5-20% 범위에서 문제 가시
- 61-80점: 양호 - 5% 미만에서만 문제 가시
- 81-100점: 우수 - 문제 거의 없음
```

**이산화 장점:**
- LLM이 연속 척도에서 허위 정밀도를 만들어내는 것 방지
- 0~100점 대신 1~5점 척도 사용 시 분산 감소
- 필요 시 1~10점, 1~20점으로 세분화 가능

### ③ 시계열 추적 — 단일 pairwise 호출 (추적 한정 최대 레버)

절대 점수 차이(분산 누적 2σ²)를 버리고, **두 이미지를 한 호출에 함께 넣어 상대 판단**시킨다.

- stochastic draw가 한 번뿐 → 분산 누적 회피.
- 상대 판단이 절대 캘리브레이션보다 통계적으로 훨씬 안정적(LLM-as-judge / Bradley–Terry에서 확립).

```
[기존]  S1 = LLM(img1),  S2 = LLM(img2),  Δ = S2 − S1     # Var(Δ) ≈ 2σ²
[권장]  Δ = LLM(img1, img2)                                 # 단일 draw, 상대 판단
```

> **중요:** 비교에 사용하는 두 이미지는 **변환을 대칭으로** 맞출 것(`복원1 vs 복원2` 또는 `원본1 vs 원본2`). 비대칭(복원1 vs 원본2)은 복원 부드러움 편향이 체계적으로 섞임 — 아래 "비교 방식 디자인" 섹� 참조.

### ④ 노이즈 바닥 정량화 — MDC (실제 통증의 직접 해법)

"이 변화가 진짜냐"의 정답은 통계다.

1. **같은 이미지**를 전체 스코어링 파이프라인에 N회(예: 20) 통과시켜 메트릭별 표준편차 σ 측정 → 측정 노이즈 바닥.
2. 두 세션 차이를 보므로 차이의 SD = σ√2.
   ```
   MDC₉₅ ≈ 1.96 × σ√2 ≈ 2.77 × σ
   ```
3. **세션 간 변화 > MDC** 일 때만 "개선/악화"로 보고. 이하는 "변화 없음(노이즈 범위)".

> 효과: "3점 올랐는데 진짜인가요?" → "σ가 2.5라 MDC가 약 7점, 따라서 노이즈"라고 정직하게 답변 가능. 고객 피드백 일관성 문제가 여기서 해소됨.

**MDC (Minimal Detectable Change) 상세 설명:**

**통계적 배경:**
- MDC는 측정 도구가 실제 변화를 감지할 수 있는 최소 크기
- 95% 신뢰수준에서 계산: MDC₉₅ = 1.96 × SEM × √2
- SEM (Standard Error of Measurement) = SD × √(1 - reliability)
- reliability가 높을수록(재현성이 좋을수록) MDC 감소

**계산 예시:**
```
기미 점수 측정 결과 (N=20):
- 평균: 48.5점
- 표준편차 (SD): 3.2점
- 신뢰도 (ICC): 0.85

SEM = 3.2 × √(1 - 0.85) = 3.2 × 0.387 = 1.24점
MDC₉₅ = 1.96 × 1.24 × √2 = 3.44점

해석:
- 기미 점수가 3.44점 이상 변해야 "실제 변화"로 간주
- 3점 변화는 노이즈 범위로 간주
```

**실제 적용 시나리오:**
```
1차 측정: 기미 45점
2차 측정: 기미 50점
변화량: +5점

MDC₉₅ = 3.44점
판정: 5점 > 3.44점 → "개선"으로 판정

1차 측정: 기미 45점
2차 측정: 기미 47점
변화량: +2점

MDC₉₅ = 3.44점
판정: 2점 < 3.44점 → "변화 없음(노이즈 범위)"으로 판정
```

**메트릭별 MDC 예시:**
| 메트릭 | SD | ICC | SEM | MDC₉₅ | 해석 |
|--------|----|----|----|----|----|
| 기미 점수 | 3.2 | 0.85 | 1.24 | 3.44 | 3.44점 이상 변화 필요 |
| 주근깨 점수 | 2.8 | 0.82 | 1.19 | 3.31 | 3.31점 이상 변화 필요 |
| 주름 점수 | 4.1 | 0.78 | 1.92 | 5.38 | 5.38점 이상 변화 필요 |
| 인지나이 | 2.5 | 0.88 | 0.87 | 2.42 | 2.42세 이상 변화 필요 |

### ⑤ 캘리브레이션 / 노이즈 모델링 (지속 운영)

- (선택) ICC(급내 상관)까지 측정하면 SEM = SD√(1−ICC), MDC₉₅ = 2.77 × SEM 로 정교화.
- 메트릭별 σ·MDC를 DB에 저장하고 모델/프롬프트 버전이 바뀔 때마다 재측정.

**ICC (Intraclass Correlation Coefficient) 상세 설명:**

**ICC의 의미:**
- ICC는 측정 도구의 신뢰도(reliability)를 나타내는 지표
- 0~1 범위, 1에 가까울수록 신뢰도 높음
- 일반적으로 ICC > 0.75: 우수, 0.5-0.75: 중등, < 0.5: 불량

**ICC 계산 방법:**
```
ICC(3,1) - 일방 분산 분석, 단일 측정자, 절대 일치
ICC(3,k) - 일방 분산 분석, 단일 측정자, 평균 측정값

Python scipy.stats.intraclass_corr 사용 가능
```

**신뢰도 등급별 해석:**
| ICC 범위 | 신뢰도 등급 | 해석 | MDC 영향 |
|----------|-----------|------|----------|
| 0.9-1.0 | 우수 | 매우 신뢰할 수 있음 | MDC 매우 낮음 |
| 0.75-0.9 | 양호 | 신뢰할 수 있음 | MDC 낮음 |
| 0.5-0.75 | 중등 | 어느 정도 신뢰 가능 | MDC 중간 |
| < 0.5 | 불량 | 신뢰하기 어려움 | MDC 높음 |

**지속 운영 절차:**
1. **초기 캘리브레이션**: 각 메트릭별 N=20회 측정으로 σ, ICC, MDC 산출
2. **주기적 재측정**: 월 1회 또는 모델/프롬프트 업데이트 시 재측정
3. **버전 관리**: 각 측정 결과에 모델/프롬프트 버전 태그 부착
4. **추세 분석**: 시간에 따른 σ, ICC 변화 추적
5. **경고 시스템**: MDC가 임계값(예: 10점) 이상으로 증가 시 알림

**데이터베이스 저장 예시:**
```sql
INSERT INTO score_reliability (metric, sigma, mdc95, n_runs, model_version, prompt_version, measured_at)
VALUES 
('pigmentation_score', 3.2, 3.44, 20, 'gpt-4-v1', 'v1.2', '2026-06-09'),
('freckle_score', 2.8, 3.31, 20, 'gpt-4-v1', 'v1.2', '2026-06-09');
```

---

## 3. 비교 방식 디자인

### 3.1 비교 방식 분류

**대칭 비교 (권장):**
- **복원1 vs 복원2**: 환경 변수 제거 후 순수 변화 파악
- **원본1 vs 원본2**: 복원 과정을 거치지 않은 원천 비교

**비대칭 비교 (주의 필요):**
- **복원1 vs 원본2**: 환경 변수 제거된 기준으로 실제 피부 변화 파악
- **복원2 vs 원본1**: 비대칭 편향 존재

### 3.2 복원 모델의 부드러움 효과

복원 이미지는 원본 이미지의 문제점(조명, 노이즈, 압축 아티팩트)을 개선하지만, 다음과 같은 문제가 있습니다:

1. **GAN 복원 모델의 부드러움 효과**
   - GAN 복원 모델은 피부 결을 부드럽게 만드는 경향
   - 미세한 주름, 색소가 복원 과정에서 부드럽게 처리됨
   - 실제 피부 개선보다 복원 효과가 더 크게 나타날 수 있음

2. **복원1 vs 복원2 비교의 문제**
   - 복원1과 복원2 모두 복원 모델의 부드러움 효과 적용
   - 두 이미지 간 차이가 실제 피부 변화보다 작을 수 있음
   - 미세한 개선 감지 어려움

3. **원본 정보 손실**
   - 복원 과정에서 원본의 미세한 피부 정보 손실
   - 실제 피부 개선이 복원 효과에 묻힐 수 있음

### 3.3 다중 비교 방안 (Multi-Comparison Approach)

**추천 방식:**
- **주요 비교**: 복원1 vs 원본2 (실제 피부 변화)
- **보조 비교**: 복원1 vs 복원2 (환경 변수 제거 후 변화)
- **원천 비교**: 원본1 vs 원본2 (실제 원본 간 변화)
- **종합 판정**: 세 가지 비교 결과를 종합하여 개선도 산출

**각 비교 방식의 역할:**

1. **복원1 vs 원본2 (주요 비교)**
   - 목적: 환경 변수 제거된 기준으로 실제 피부 변화 파악
   - 장점: 복원 모델의 부드러움 효과가 원본2에 적용되지 않음
   - 단점: 원본2의 환경 변수가 점수에 영향

2. **복원1 vs 복원2 (보조 비교)**
   - 목적: 환경 변수 제거 후의 순수한 피부 변화 파악
   - 장점: 환경 변수가 제거되어 일관된 비교
   - 단점: 복원 모델의 부드러움 효과가 중복 적용됨

3. **원본1 vs 원본2 (원천 비교)**
   - 목적: 실제 원본 이미지 간의 변화 파악
   - 장점: 복원 과정을 거치지 않은 순수한 원본 비교
   - 단점: 환경 변수(조명, 노이즈)가 다르면 비교 어려움, LLM 점수 변동성 존재

**종합 판정 로직:**

```
개선도 = (복원1 vs 원본2 점수 차이 × 0.5) 
       + (복원1 vs 복원2 점수 차이 × 0.3)
       + (원본1 vs 원본2 점수 차이 × 0.2)

환경 변수 보정:
- 원본1 vs 원본2 비교 시 조명/노이즈 차이가 크면 가중치 감소
- 복원1 vs 복원2 비교 시 복원 품질이 낮으면 가중치 감소
- 복원1 vs 원본2 비교 시 환경 변수가 적절하면 가중치 증가
```

**수학적 설명:**

```
[기본 정의]
원본 이미지 = 피부 상태 + 환경 변수 (조명, 노이즈, 압축)
복원 이미지 = 피부 상태 (환경 변수 제거) + 복원 부드러움 효과

[세 가지 비교 방식]
1. 복원1 vs 원본2 (주요 비교)
   복원1 = 피부 상태1 + 복원 부드러움 (기준)
   원본2 = 피부 상태2 + 환경 변수 (실제)
   비교 = 원본2 - 복원1 = (피부 상태2 - 피부 상태1) + (환경 변수 - 복원 부드러움)
        = 실제 피부 변화 + 환경 영향

2. 복원1 vs 복원2 (보조 비교)
   복원1 = 피부 상태1 + 복원 부드러움
   복원2 = 피부 상태2 + 복원 부드러움
   비교 = 복원2 - 복원1 = (피부 상태2 - 피부 상태1)
        = 순수한 피부 변화 (하지만 복원 부드러움 효과가 중복됨)

3. 원본1 vs 원본2 (원천 비교)
   원본1 = 피부 상태1 + 환경 변수1
   원본2 = 피부 상태2 + 환경 변수2
   비교 = 원본2 - 원본1 = (피부 상태2 - 피부 상태1) + (환경 변수2 - 환경 변수1)
        = 실제 피부 변화 + 환경 변수 차이
```

**실제 예시:**

| 항목 | 원본1 | 원본2 | 복원1 | 복원2 | 복원1 vs 원본2 | 복원1 vs 복원2 | 원본1 vs 원본2 |
|------|-------|-------|-------|-------|----------------|----------------|----------------|
| 조명 | 어두움 | 밝음 | 표준 | 표준 | 고려 필요 | 일관 | 차이 큼 |
| 노이즈 | 높음 | 낮음 | 제거됨 | 제거됨 | 고려 필요 | 일관 | 차이 있음 |
| 기미 점수 | 45±5 | 55±5 | 45±2 | 55±2 | 55 vs 45 = +10 | 55 vs 45 = +10 | 55 vs 45 = +10 |
| 주근깨 점수 | 20±5 | 30±5 | 20±2 | 30±2 | 30 vs 20 = +10 | 30 vs 20 = +10 | 30 vs 20 = +10 |
| 복원 부드러움 | 없음 | 없음 | 있음 | 있음 | 원본2에 없음 | 둘 다 있음 | 없음 |
| 환경 변수 | 있음 | 있음 | 제거됨 | 제거됨 | 원본2에 있음 | 제거됨 | 다름 |

**결론:**
- **복원1 vs 원본2** 비교가 실제 피부 개선 파악에 가장 적합 (주요)
- **복원1 vs 복원2** 비교는 환경 변수 제거 후 순수 변화 파악 (보조)
- **원본1 vs 원본2** 비교는 복원 과정을 거치지 않은 원천 비교 (참고)
- 세 가지 방식을 결합하여 종합 판정

---

## 4. 우선순위 (가성비)

| 순위 | 계층 | 효과 | 구현 비용 | 비고 |
|------|------|------|----------|------|
| 1 | ③ pairwise + ④ MDC | 추적 신뢰성 즉효 | **낮음** | 가장 먼저 |
| 2 | ① CV anchor | 변동성 대부분 제거 | 중 | 진짜 best |
| 3 | ② 출력 제약 | 잔여 분산 억제 | 중 | LLM 채점 유지 시 |
| 4 | ⑤ 캘리브레이션 | 정직한 보고/장기 운영 | 낮음~중 | 지속 |

> 딱 하나만 먼저 한다면 **③ + ④**. 추적 신뢰성에 즉효이고 구현 비용이 가장 낮다.

---

## 5. 기술 구현 방안

### 5.1 MDC 측정 스크립트 (계층 ④)

**신규 파일:** `tools/measure_score_reliability.py`

```python
import statistics
from pathlib import Path
from typing import Dict, Any
import logging

def measure_mdc(image_path: str | Path, n_runs: int = 20) -> dict:
    """같은 이미지를 N회 스코어링해 메트릭별 σ·MDC 산출.
    
    Args:
        image_path: 측정할 이미지 경로
        n_runs: 반복 측정 횟수 (기본값: 20)
    
    Returns:
        dict: 메트릭별 통계 정보 {metric: {mean, sigma, mdc95}}
    
    Raises:
        ValueError: n_runs < 3인 경우
        RuntimeError: 스코어링 파이프라인 실패 시
    """
    if n_runs < 3:
        raise ValueError("n_runs must be at least 3 for reliable statistics")
    
    runs: list[dict[str, float]] = []
    failed_runs = 0
    
    for i in range(n_runs):
        try:
            report = score_image(image_path)          # 기존 스코어링 파이프라인
            runs.append(report.metric_scores)         # {metric: score}
        except Exception as e:
            failed_runs += 1
            logging.warning(f"Run {i+1} failed: {e}")
            continue
    
    if len(runs) < 3:
        raise RuntimeError(f"Too many failed runs: {failed_runs}/{n_runs}")
    
    result = {}
    metrics = runs[0].keys()
    for m in metrics:
        vals = [r[m] for r in runs if m in r]
        if len(vals) < 3:
            logging.warning(f"Metric {m} has insufficient data: {len(vals)}")
            continue
        
        sigma = statistics.pstdev(vals)
        result[m] = {
            "mean": statistics.fmean(vals),
            "sigma": sigma,
            "mdc95": 2.77 * sigma,                 # 1.96 * σ * √2
            "n_samples": len(vals),
            "failed_runs": failed_runs
        }
    
    return result
```

**구현 고려사항:**
- **병렬 처리**: N회 측정을 병렬로 실행하여 시간 단축 (concurrent.futures 사용)
- **캐싱**: 동일 이미지에 대한 이전 측정 결과 캐싱
- **진행 표시**: 장기 실행 시 진행률 표시 (tqdm 사용)
- **결과 저장**: 측정 결과를 JSON 파일로 자동 저장
- **모니터링**: API 호출 비용 추적

### 5.2 pairwise 비교 프롬프트 빌더 (계층 ③)

**파일:** `src/llm/llm_prompt_builder.py`

```python
def _build_pairwise_comparison_prompt(
    metric_rubric: Dict[str, str],          # 메트릭별 점수 band 정의(rubric anchor)
    reference_anchor: Optional[str] = None, # 알려진 점수의 기준 이미지 설명
    provide_scores: bool = True,
) -> str:
    """두 이미지를 함께 보고 '상대 변화량'을 판단하는 프롬프트.
    절대 점수를 두 번 매기지 않고 단일 호출로 Δ를 산출한다."""
```

**프롬프트 템플릿(`LLM_PROMPT_TEMPLATE.md`) 골자:**

```markdown
<!-- PAIRWISE_COMPARISON_PROMPT_START -->
첨부 이미지:
- 이미지 A: 1차 (기준)
- 이미지 B: 2차 (비교 대상)
* 두 이미지는 동일한 변환(복원/원본)이 적용되어 있다.

분석: 각 측정항목에 대해 A 대비 B의 상대 변화만 판단하라.
- 절대 점수를 새로 매기지 말 것.
- 출력은 항목별 {direction: improved|worsened|stable, delta: -N..+N, 근거}.
- delta는 정수 band(예: -3..+3)로만 제시.
<!-- PAIRWISE_COMPARISON_PROMPT_END -->
```

### 5.3 샘플링·집계 (계층 ②)

```python
def stable_llm_score(call_fn, n: int = 5) -> float:
    """temperature≈0로 N회 호출 후 median(이상치 강건)."""
    samples = [call_fn(temperature=0.0) for _ in range(n)]
    return statistics.median(samples)
```

### 5.4 DB 스키마 — 신뢰성 메타데이터 (계층 ④/⑤)

**파일:** `src/db/skin_analysis_db.py`

```sql
CREATE TABLE score_reliability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric TEXT NOT NULL,
    sigma REAL NOT NULL,
    mdc95 REAL NOT NULL,
    n_runs INTEGER NOT NULL,
    model_version TEXT NOT NULL,      -- 모델/프롬프트 버전별 재측정
    prompt_version TEXT,
    measured_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_reliability_metric ON score_reliability(metric, model_version);
```

### 5.6 다중 비교 구현 (비교 방식 디자인)

**파일:** `src/llm/llm_generation.py`

**함수명:** `generate_restoration_guided_original_comparison_report`

```python
def generate_restoration_guided_original_comparison_report(
    self,
    restoration1_image_path: str | Path,
    original2_image_path: str | Path,
    restoration1_measurements_report: Dict[str, Any],
    restoration1_overall_score: float,
    restoration1_perceived_age: float,
    original2_measurements_report: Dict[str, Any],
    original2_overall_score: float = 0,
    original2_perceived_age: float = 0,
    provide_scores: bool = True,
    product_info: Optional[str] = None,
    prescription_info: Optional[str] = None,
    survey_info: Optional[str] = None,
) -> "SkinLLMReport":
    """복원 기준 원본 비교 보고서 생성.
    
    복원1 이미지를 기준으로 원본2 이미지를 평가하여
    제품 효과 개선 여부를 판단합니다.
    """
```

**파일:** `src/llm/llm_prompt_builder.py`

**함수명:** `_build_restoration_guided_original_comparison_prompt`

```python
def _build_restoration_guided_original_comparison_prompt(
    restoration1_measurements_report: Dict[str, Any],
    restoration1_overall_score: float,
    restoration1_perceived_age: float,
    original2_measurements_report: Dict[str, Any],
    original2_overall_score: float = 0,
    original2_perceived_age: float = 0,
    provide_scores: bool = True,
    product_info: Optional[str] = None,
    prescription_info: Optional[str] = None,
    survey_info: Optional[str] = None,
) -> str:
    """복원 기준 원본 비교 프롬프트 구성."""
```

**프롬프트 템플릿(`LLM_PROMPT_TEMPLATE.md`):**

```markdown
<!-- RESTORATION_GUIDED_ORIGINAL_COMPARISON_PROMPT_START -->
## CÔTELEAF 복원 기준 원본 비교 분석

첨부 이미지:
- **이미지 1**: 1차 복원 이미지 (기준 - 환경 변수 제거됨)
- **이미지 2**: 2차 원본 이미지 (비교 대상 - 실제 피부 상태)

## 분석 목적
제품 사용 전후의 피부 개선 여부를 판단하기 위해
복원 기준 이미지와 실제 원본 이미지를 비교합니다.

## 분석 절차
1. 이미지1(복원 기준)과 이미지2(실제 원본)를 비교
2. 각 측정항목별 개선/악화 판정
3. 점수 차이 계산
4. 종합 개선도 평가
5. 환경 변수(조명, 노이즈)를 고려하여 실제 피부 변화 판단
<!-- RESTORATION_GUIDED_ORIGINAL_COMPARISON_PROMPT_END -->
```

**파일:** `src/llm/llm_parsing.py`

**함수명:** `_parse_restoration_guided_original_comparison_response`

```python
def _parse_restoration_guided_original_comparison_response(
    self,
    response_text: str,
    restoration1_measurements_report: Dict[str, Any],
    restoration1_overall_score: float,
    restoration1_perceived_age: float,
    matched_products: List[Dict[str, Any]],
) -> "SkinLLMReport":
    """복원 기준 원본 비교 응답 파싱."""
```

**파일:** `src/db/skin_analysis_db.py`

**새로운 테이블:** `restoration_guided_original_comparisons`

```sql
CREATE TABLE restoration_guided_original_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    restoration1_image_path TEXT NOT NULL,
    original2_image_path TEXT NOT NULL,
    restoration1_overall_score REAL,
    original2_overall_score REAL,
    score_difference REAL,
    improvement_status TEXT,  -- 'improved', 'worsened', 'stable'
    comparison_date TEXT NOT NULL,
    comparison_result_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**파일:** `src/gui/compare_dialog.py`

**새로운 기능:**
- "복원 기준 원본 비교" 버튼
- 복원1 이미지 선택
- 원본2 이미지 선택
- 비교 결과 표시

**표시 항목:**
- 총점 차이
- 인지나이 차이
- 항목별 개선/악화 목록
- 개선도 시각화 (그래프)
- 환경 변수 고려 판정

**API 엔드포인트:** `POST /v1/analysis/restoration-guided-original-comparison`

```json
{
  "customer_id": "customer123",
  "restoration1_image_path": "/path/to/restoration1.png",
  "original2_image_path": "/path/to/original2.png",
  "restoration1_measurements": {...},
  "original2_measurements": {...}
}
```

### 5.7 판정 로직 (결정 규칙)

```python
def judge_change(delta: float, mdc95: float, cv_dir: int, llm_dir: int) -> str:
    """MDC를 넘고 CV·LLM 방향이 일치할 때만 개선/악화 판정.
    
    Args:
        delta: 세션 간 점수 차이 (2차 - 1차)
        mdc95: 최소 검출 가능 변화 (95% 신뢰수준)
        cv_dir: CV 기반 방향 (+1: 개선, -1: 악화, 0: 변화 없음)
        llm_dir: LLM 기반 방향 (+1: 개선, -1: 악화, 0: 변화 없음)
    
    Returns:
        str: 판정 결과 ('improved', 'worsened', 'stable', 'uncertain')
    
    Examples:
        >>> judge_change(5.0, 3.44, 1, 1)
        'improved'
        >>> judge_change(2.0, 3.44, 1, 1)
        'stable'
        >>> judge_change(5.0, 3.44, 1, -1)
        'uncertain'
    """
    if abs(delta) < mdc95:
        return "stable"                       # 노이즈 범위
    if cv_dir != llm_dir:
        return "uncertain"                    # 방향 불일치 → 보류
    return "improved" if delta > 0 else "worsened"
```

**판정 로직 상세 설명:**

**4가지 판정 결과:**
1. **improved**: 실제 개선 확인
   - 조건: |delta| > MDC이고 CV·LLM 방향 모두 양수
   - 의미: 통계적으로 유의미한 개선, 두 측정 방법 일치

2. **worsened**: 실제 악화 확인
   - 조건: |delta| > MDC이고 CV·LLM 방향 모두 음수
   - 의미: 통계적으로 유의미한 악화, 두 측정 방법 일치

3. **stable**: 변화 없음 (노이즈 범위)
   - 조건: |delta| ≤ MDC
   - 의미: 변화가 측정 노이즈 범위 내, 실제 변화 불확실

4. **uncertain**: 방향 불일치
   - 조건: |delta| > MDC이지만 CV·LLM 방향 불일치
   - 의미: 변화는 유의미하나 방향이 모호, 추가 분석 필요

**실제 적용 예시:**
```
예시 1: 명확한 개선
- delta = +5.0점
- MDC = 3.44점
- CV 방향 = +1 (개선)
- LLM 방향 = +1 (개선)
- 판정: improved (5.0 > 3.44, 방향 일치)

예시 2: 노이즈 범위
- delta = +2.0점
- MDC = 3.44점
- CV 방향 = +1 (개선)
- LLM 방향 = +1 (개선)
- 판정: stable (2.0 < 3.44, 노이즈 범위)

예시 3: 방향 불일치
- delta = +5.0점
- MDC = 3.44점
- CV 방향 = +1 (개선)
- LLM 방향 = -1 (악화)
- 판정: uncertain (방향 불일치, 추가 분석 필요)
```

**고급 판정 로직 (선택적):**
```python
def judge_change_advanced(
    delta: float, 
    mdc95: float, 
    cv_dir: int, 
    llm_dir: int,
    cv_confidence: float = 1.0,
    llm_confidence: float = 1.0
) -> tuple[str, float]:
    """가중치 기반 고급 판정 로직.
    
    Args:
        cv_confidence: CV 측정 신뢰도 (0-1)
        llm_confidence: LLM 측정 신뢰도 (0-1)
    
    Returns:
        tuple: (판정 결과, 신뢰도 점수)
    """
    if abs(delta) < mdc95:
        return "stable", 0.0
    
    # 가중치 계산
    total_weight = cv_confidence + llm_confidence
    cv_weight = cv_confidence / total_weight
    llm_weight = llm_confidence / total_weight
    
    # 가중 방향 계산
    weighted_dir = cv_dir * cv_weight + llm_dir * llm_weight
    
    if abs(weighted_dir) < 0.3:  # 방향 모호
        return "uncertain", abs(weighted_dir)
    
    confidence_score = abs(weighted_dir)
    return ("improved" if weighted_dir > 0 else "worsened"), confidence_score
```

---

## 6. 향후 작업 항목

### Phase 1 — 추적 신뢰성 (우선)
- [ ] `tools/measure_score_reliability.py` 구현 → 메트릭별 σ·MDC 산출
- [ ] `score_reliability` 테이블 생성 및 저장 로직
- [ ] `judge_change` 결정 규칙 구현 (MDC 임계 + 방향 일치)

### Phase 2 — pairwise 비교
- [ ] `_build_pairwise_comparison_prompt` 구현
- [ ] `PAIRWISE_COMPARISON_PROMPT` 템플릿 추가
- [ ] 대칭 변환 강제(복원-복원 또는 원본-원본) 검증

### Phase 3 — 다중 비교 구현
- [ ] `generate_restoration_guided_original_comparison_report` 함수 구현
- [ ] `_build_restoration_guided_original_comparison_prompt` 함수 구현
- [ ] `_parse_restoration_guided_original_comparison_response` 함수 구현
- [ ] `RESTORATION_GUIDED_ORIGINAL_COMPARISON_PROMPT` 템플릿 추가
- [ ] `restoration_guided_original_comparisons` 테이블 생성
- [ ] 비교 결과 저장 로직 구현
- [ ] GUI 비교 기능 추가
- [ ] 비교 결과 시각화
- [ ] 개선도 그래프 구현
- [ ] 환경 변수 고려 판정 표시
- [ ] `/v1/analysis/restoration-guided-original-comparison` 엔드포인트 구현

### Phase 4 — 출력 제약·집계
- [ ] `stable_llm_score` (temp 0 + N회 median) 적용
- [ ] rubric anchoring 정의 (메트릭별 band 기준)
- [ ] reference anchor 이미지 주입 강화
- [ ] 이산 band + structured output 적용

### Phase 5 — CV anchor
- [ ] 정량 점수 backbone을 CV로 전환, LLM은 보조/정성으로 재배치
- [ ] LLM 성분 가중치 재산정 (분산 전파 고려)

### Phase 6 — 캘리브레이션 운영
- [ ] ICC 기반 SEM/MDC 정교화 (선택)
- [ ] 모델/프롬프트 버전 변경 시 자동 재측정 훅

---

## 7. 참고 문서
- `src/llm/llm_generation.py`, `src/llm/llm_prompt_builder.py`, `src/llm/llm_parsing.py`
- `src/llm/LLM_PROMPT_TEMPLATE.md`
- `src/db/skin_analysis_db.py`
- `src/gui/compare_dialog.py`
- `docs/guides/LLM_PROMPT_TEMPLATE.md` - LLM 프롬프트 가이드

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-06-09 | 초기 버전 작성 | Claude |
| 1.1.0 | 2026-06-09 | MULTI_COMPARISON_DESIGN.md 병합 - 비교 방식 디자인 포함 | Cascade |
| 1.2.0 | 2026-06-09 | 상세 설명 추가 - 수학적 배경, CV 파이프라인 예시, MDC 상세 설명, ICC 설명, 구현 고려사항, 판정 로직 상세 설명 | Cascade |
