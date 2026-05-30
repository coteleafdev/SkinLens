# 처방 효과 예측 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 처방 사용 후 예상 점수 개선 시뮬레이션 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 처방전만 제공
- 사용자가 처방 사용 후 어떤 효과가 있을지 알 수 없음
- 사용자 동기 부여 부족

### 1.2 제안된 기능
- 처방 사용 후 예상 점수 개선 시뮬레이션
- 각 측정 항목별 예상 개선幅度 표시
- 시각적 그래프로 개선 예상 표시
- 사용자 맞춤형 예측 모델

### 1.3 기대 효과
- 사용자 동기 부여
- 처방 준수율 향상
- 사용자 만족도 증대

---

## 2. 예측 모델 설계

### 2.1 기본 예측 로직
각 제품 카테고리별 기본 개선률 적용:
- **세안제:** oiliness_score, pore_size_score 개선
- **토너:** hydration_score, redness_score 개선
- **세럼:** hydration_score, inflammation_score 개선
- **모이스처라이저:** hydration_score, dryness_score 개선
- **선크림:** redness_score, inflammation_score 개선

### 2.2 개선률 정의
기본 개선률 (제품 사용 4주 후 예상):
- **경량 개선:** 5-10% 점수 향상
- **중간 개선:** 10-20% 점수 향상
- **강력 개선:** 20-30% 점수 향상

개선률 결정 요인:
- 제품 성분 분석
- 사용자 피부 타입 매칭
- 현재 점수 레벨 (낮은 점수일 때 더 큰 개선 예상)

### 2.3 피부 타입별 맞춤 예측
- **지성:** oiliness_score, pore_size_score 개선률 증가
- **건성:** hydration_score, dryness_score 개선률 증가
- **복합성:** T-zone/U-zone별 차별화된 개선률
- **민감성:** redness_score, inflammation_score 개선률 증가

---

## 3. 기술 설계

### 3.1 예측 알고리즘
1. 현재 분석 결과에서 각 측정 항목 점수 추출
2. 처방된 제품 목록 및 카테고리 식별
3. 제품 카테고리별 타겟 측정 항목 매핑
4. 기본 개선률 적용
5. 피부 타입별 보정 계수 적용
6. 현재 점수 레벨별 보정 적용
7. 최종 예상 점수 계산

### 3.2 데이터 구조
**예측 결과:**
```json
{
  "current_scores": {
    "oiliness_score": 65,
    "pore_size_score": 70,
    "hydration_score": 45,
    "dryness_score": 55,
    "redness_score": 60,
    "inflammation_score": 50
  },
  "predicted_scores": {
    "oiliness_score": 55,
    "pore_size_score": 60,
    "hydration_score": 60,
    "dryness_score": 45,
    "redness_score": 50,
    "inflammation_score": 40
  },
  "improvements": {
    "oiliness_score": {
      "current": 65,
      "predicted": 55,
      "improvement": 10,
      "percentage": 15.4
    },
    "pore_size_score": {
      "current": 70,
      "predicted": 60,
      "improvement": 10,
      "percentage": 14.3
    }
  },
  "overall_improvement": {
    "current_average": 57.5,
    "predicted_average": 51.7,
    "improvement": 5.8,
    "percentage": 10.1
  },
  "timeframe": "4주",
  "confidence": 0.75
}
```

### 3.3 API 엔드포인트
- **경로:** `/v3/prescription/predict-effect`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "job_id": "string",
  "prescription_id": "string"
}
```
- **응답:**
```json
{
  "current_scores": {},
  "predicted_scores": {},
  "improvements": {},
  "overall_improvement": {},
  "timeframe": "4주",
  "confidence": 0.75
}
```

### 3.4 클라이언트 UI/UX
- **시각적 그래프:** 현재 점수 vs 예상 점수 바 차트
- **개선幅度 표시:** 각 항목별 개선 백분율 표시
- **전체 개선 요약:** 전체 평균 점수 개선幅度 표시
- **시간 프레임:** "4주 후 예상" 등 텍스트 표시
- **신뢰도 표시:** 예측 신뢰도 표시 (예: 75% 신뢰도)

---

## 4. 구현 단계

### 4.1 백엔드 개발 (3일)
- 예측 알고리즘 구현
- 제품 카테고리별 타겟 항목 매핑
- 피부 타입별 보정 계수 구현
- API 엔드포인트 구현

### 4.2 데이터 모델 확장 (1일)
- 제품 성분 데이터베이스 확장
- 개선률 기본값 설정
- 피부 타입별 보정 계수 저장

### 4.3 API 문서 업데이트 (0.5일)
- 새로운 예측 엔드포인트 문서화
- 데이터 구조 문서화

### 4.4 클라이언트 UI 개발 (2일)
- 시각적 그래프 구현
- 개선幅度 표시 UI 구현
- API 연동

### 4.5 테스트 및 디버깅 (1.5일)
- 기능 테스트
- 정확도 검증
- 에러 처리 테스트

**총 예상 소요 시간: 8일**

---

## 5. 성능 고려사항

- **예측 계산:** 간단한 수식 기반이므로 빠른 응답 가능
- **캐싱:** (job_id, prescription_id) 조합으로 캐싱
- **머신러닝 고려:** 향후 실제 사용 데이터로 모델 개선 가능

---

## 6. 성공 지표

- **예측 응답 시간:** 0.5초 이내
- **사용자 동기 부여:** 처방 준수율 +25%
- **사용자 만족도:** 기능 도입 후 긍정적 피드백 +20%
- **예측 정확도:** 실제 개선과 예측 간 상관계수 0.6 이상 목표
