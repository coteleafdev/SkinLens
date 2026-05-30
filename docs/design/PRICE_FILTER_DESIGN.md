# 가격 필터 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 가격 범위 필터링 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 성분/효능 기반 매칭만 지원
- 가격 정보 반영 안 됨
- 사용자 예산 고려 불가
- 예산 초과 제품 추천 가능

### 1.2 제안된 기능
- 제품 가격 정보 저장
- 가격 범위 필터링
- 예산 기반 추천
- 가격대별 제품 분류
- 가격-성능 비교

### 1.3 기대 효과
- 예산에 맞는 추천
- 사용자 만족도 향상
- 구매 전환율 증가
- 가격 민감도 고려

---

## 2. 데이터 모델 설계

### 2.1 제품 테이블 확장 (products)
```sql
ALTER TABLE products ADD COLUMN price INTEGER;                    -- 가격 (원)
ALTER TABLE products ADD COLUMN currency TEXT DEFAULT 'KRW';      -- 통화
ALTER TABLE products ADD COLUMN price_range TEXT;                 -- 가격대 (low, mid, high)
ALTER TABLE products ADD COLUMN volume TEXT;                       -- 용량 (예: "50ml")
ALTER TABLE products ADD COLUMN price_per_unit REAL;               -- 단위당 가격 (원/ml)
ALTER TABLE products ADD COLUMN discount_price INTEGER;            -- 할인가 (선택 사항)
ALTER TABLE products ADD COLUMN discount_percentage REAL;           -- 할인율 (선택 사항)
```

### 2.2 가격대 정의
- **low:** 0 ~ 30,000원
- **mid:** 30,001 ~ 80,000원
- **high:** 80,001원 이상

---

## 3. 기술 설계

### 3.1 가격 정보 수집
1. 제품 등록 시 가격 정보 입력
2. 용량 정보 입력
3. 단위당 가격 자동 계산 (price / volume)
4. 가격대 자동 분류
5. 할인 정보 입력 (선택 사항)

### 3.2 가격 범위 필터링
1. 사용자가 최소/최대 가격 입력
2. 데이터베이스 쿼리에 가격 범위 조건 추가
3. 가격 범위 내 제품 필터링
4. 기존 매칭 알고리즘과 결합

### 3.3 예산 기반 추천
1. 사용자 예산 입력
2. 예산 내에서 최고 매칭 점수 제품 추천
3. 예산 대비 가성비 분석
4. 예산 내 최적 제품 추천

### 3.4 가격-성능 비교
1. 가격대별 평균 매칭 점수 계산
2. 단위당 가격 대비 효능 분석
3. 가성비 높은 제품 식별
4. 사용자에게 가성비 인사이트 제공

### 3.5 API 엔드포인트

#### 3.5.1 가격 범위 필터링 제품 검색
- **경로:** `/v3/products/search`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "job_id": "string",
  "category": "세럼",
  "min_price": 10000,
  "max_price": 50000,
  "skin_type": "oily"
}
```
- **응답:**
```json
{
  "products": [
    {
      "id": "string",
      "name": "string",
      "price": 35000,
      "currency": "KRW",
      "price_range": "mid",
      "volume": "50ml",
      "price_per_unit": 700.0,
      "matching_score": 0.85
    }
  ],
  "total": 10,
  "price_range_summary": {
    "min_price": 10000,
    "max_price": 50000,
    "average_price": 32500
  }
}
```

#### 3.5.2 예산 기반 추천
- **경로:** `/v3/products/recommend-by-budget`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "job_id": "string",
  "budget": 100000,
  "categories": ["세럼", "모이스처라이저"],
  "skin_type": "oily"
}
```
- **응답:**
```json
{
  "recommendations": [
    {
      "category": "세럼",
      "product": {
        "id": "string",
        "name": "string",
        "price": 45000,
        "matching_score": 0.92
      },
      "value_score": 0.88
    }
  ],
  "total_budget": 100000,
  "total_estimated": 85000,
  "remaining_budget": 15000
}
```

#### 3.5.3 가격대별 제품 통계
- **경로:** `/v3/products/price-statistics`
- **메서드:** `GET`
- **쿼리 파라미터:** `category`, `skin_type`
- **응답:**
```json
{
  "price_ranges": {
    "low": {
      "count": 20,
      "average_price": 18500,
      "average_matching_score": 0.75
    },
    "mid": {
      "count": 35,
      "average_price": 52000,
      "average_matching_score": 0.82
    },
    "high": {
      "count": 15,
      "average_price": 125000,
      "average_matching_score": 0.88
    }
  }
}
```

### 3.6 클라이언트 UI/UX
- **가격 범위 슬라이더:** 최소/최대 가격 조절
- **가격대 필터:** low/mid/high 체크박스
- **예산 입력:** 총 예산 입력 필드
- **가격대별 제품 목록:** 가격대별로 그룹화된 제품 표시
- **가성비 뱃지:** 가성비 높은 제품에 뱃지 표시
- **가격-성능 차트:** 가격대별 평균 매칭 점수 차트

---

## 4. 구현 단계

### 4.1 데이터베이스 스키마 확장 (0.5일)
- `products` 테이블 확장
- 기존 제품 데이터 가격 정보 마이그레이션

### 4.2 백엔드 개발 (2일)
- 가격 범위 필터링 로직 구현
- 예산 기반 추천 알고리즘 구현
- 가격-성능 비교 로직 구현
- API 엔드포인트 구현

### 4.3 제품 매칭 엔진 통합 (0.5일)
- 기존 제품 매칭 알고리즘에 가격 필터 통합

### 4.4 API 문서 업데이트 (0.5일)
- 새로운 엔드포인트 문서화
- 데이터 구조 문서화

### 4.5 클라이언트 UI 개발 (2일)
- 가격 범위 슬라이더 구현
- 가격대 필터 구현
- 예산 입력 UI 구현
- 가성비 뱃지 구현
- API 연동

### 4.6 테스트 및 디버깅 (1일)
- 기능 테스트
- 필터링 정확성 테스트
- 에러 처리 테스트

**총 예상 소요 시간: 6.5일**

---

## 5. 성능 고려사항

- **인덱스 최적화:** price 컬럼에 인덱스 생성
- **캐싱:** 가격대별 통계 캐싱
- **범위 쿼리 최적화:** BETWEEN 쿼리 튜닝

---

## 6. 성공 지표

- **가격 필터 사용률:** 제품 검색의 60% 이상 가격 필터 사용
- **예산 내 추천 정확도:** 예산 내 추천 제품의 90% 이상 예산 충족
- **사용자 만족도:** 가격 필터 도입 후 만족도 +10%
- **구매 전환율:** 예산 기반 추천 후 전환율 +15%
