# 제품 리뷰 통합 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 실제 사용자 리뷰 점수를 제품 매칭에 반영하는 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 제품 정보만 매칭 (성분, 카테고리 등)
- 실제 사용자 리뷰 점수 반영 안 됨
- 추천 정확도 한계
- 사용자 경험 부족

### 1.2 제안된 기능
- 실제 사용자 리뷰 점수 수집 및 저장
- 리뷰 점수를 제품 매칭 알고리즘에 반영
- 리뷰 기반 제품 랭킹
- 사용자 피드백 수집 시스템
- 리뷰 분석 및 인사이트 제공

### 1.3 기대 효과
- 추천 정확도 향상
- 사용자 신뢰도 증대
- 제품 품질 개선 피드백 루프
- 사용자 참여도 증가

---

## 2. 데이터 모델 설계

### 2.1 제품 리뷰 테이블 (product_reviews)
```sql
CREATE TABLE product_reviews (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    job_id TEXT,                              -- (선택 사항) 연결된 분석 결과
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    title TEXT,
    content TEXT,
    skin_type TEXT,                           -- 리뷰어 피부 타입
    skin_concerns JSON,                       -- 리뷰어 피부 고민
    effectiveness_scores JSON,                 -- 효과 점수 (예: {"hydration": 4, "oiliness": 3})
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_verified BOOLEAN DEFAULT FALSE,        -- 검증된 리뷰 여부
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_product_reviews_product ON product_reviews(product_id);
CREATE INDEX idx_product_reviews_user ON product_reviews(user_id);
CREATE INDEX idx_product_reviews_rating ON product_reviews(rating);
CREATE INDEX idx_product_reviews_skin_type ON product_reviews(skin_type);
```

### 2.2 제품 리뷰 집계 테이블 (product_review_aggregates)
```sql
CREATE TABLE product_review_aggregates (
    product_id TEXT PRIMARY KEY,
    total_reviews INTEGER DEFAULT 0,
    average_rating REAL DEFAULT 0.0,
    rating_distribution JSON,                 -- {"1": 10, "2": 5, "3": 20, "4": 30, "5": 35}
    skin_type_ratings JSON,                  -- {"oily": 4.2, "dry": 3.8, "combination": 4.0, "sensitive": 3.5}
    effectiveness_averages JSON,              -- {"hydration": 4.1, "oiliness": 3.9}
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);
```

### 2.3 제품 테이블 확장 (products)
```sql
ALTER TABLE products ADD COLUMN review_score REAL DEFAULT 0.0;
ALTER TABLE products ADD COLUMN total_reviews INTEGER DEFAULT 0;
ALTER TABLE products ADD COLUMN review_weight REAL DEFAULT 0.5;  -- 리뷰 점수 가중치 (0.0-1.0)
```

---

## 3. 기술 설계

### 3.1 리뷰 수집
1. 사용자가 제품 사용 후 리뷰 작성
2. 리뷰 데이터 (별점, 제목, 내용, 피부 타입, 효과 점수) 저장
3. 제품별 리뷰 집계 업데이트
4. 리뷰 검증 (선택 사항: 실제 구매 확인)

### 3.2 리뷰 점수 집계
1. 제품별 평균 별점 계산
2. 별점 분포 계산
3. 피부 타입별 평균 별점 계산
4. 효과 점수별 평균 계산
5. `product_review_aggregates` 테이블에 저장
6. 주기적 배치 작업으로 업데이트

### 3.3 리뷰 기반 제품 매칭
1. 기존 제품 매칭 알고리즘 (성분, 카테고리 기반)
2. 리뷰 점수 가중치 적용
3. 피부 타입별 리뷰 점수 반영
4. 최종 매칭 점수 계산:
   ```
   final_score = (base_score * (1 - review_weight)) + (review_score * review_weight)
   ```
5. 리뷰 점수가 높은 제품 우선 추천

### 3.4 리뷰 분석 및 인사이트
1. 제품별 리뷰 트렌드 분석
2. 피부 타입별 선호 제품 식별
3. 효과 점수가 높은 제품 카테고리 식별
4. 사용자에게 인사이트 제공

### 3.5 API 엔드포인트

#### 3.5.1 리뷰 작성
- **경로:** `/v3/products/{product_id}/reviews`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "job_id": "string",
  "rating": 5,
  "title": "string",
  "content": "string",
  "skin_type": "oily",
  "skin_concerns": ["acne", "pores"],
  "effectiveness_scores": {
    "hydration": 4,
    "oiliness": 5,
    "pore_size": 4
  }
}
```
- **응답:**
```json
{
  "id": "string",
  "product_id": "string",
  "rating": 5,
  "created_at": "2026-05-24T00:00:00Z"
}
```

#### 3.5.2 제품 리뷰 조회
- **경로:** `/v3/products/{product_id}/reviews`
- **메서드:** `GET`
- **쿼리 파라미터:** `skin_type`, `min_rating`, `limit`, `offset`
- **응답:**
```json
{
  "reviews": [
    {
      "id": "string",
      "rating": 5,
      "title": "string",
      "content": "string",
      "skin_type": "oily",
      "effectiveness_scores": {},
      "created_at": "2026-05-24T00:00:00Z"
    }
  ],
  "aggregates": {
    "total_reviews": 100,
    "average_rating": 4.2,
    "rating_distribution": {},
    "skin_type_ratings": {},
    "effectiveness_averages": {}
  },
  "total": 100,
  "limit": 10,
  "offset": 0
}
```

#### 3.5.3 리뷰 기반 제품 추천
- **경로:** `/v3/products/recommend`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "job_id": "string",
  "skin_type": "oily",
  "include_review_score": true,
  "review_weight": 0.5
}
```
- **응답:**
```json
{
  "products": [
    {
      "id": "string",
      "name": "string",
      "base_score": 0.85,
      "review_score": 0.92,
      "final_score": 0.885,
      "total_reviews": 50,
      "average_rating": 4.5
    }
  ]
}
```

### 3.6 클라이언트 UI/UX
- **리뷰 작성 폼:** 별점, 제목, 내용, 피부 타입, 효과 점수 입력
- **리뷰 목록:** 제품별 리뷰 목록 표시
- **리뷰 필터:** 피부 타입, 최소 별점 필터링
- **리뷰 통계:** 평균 별점, 별점 분포, 피부 타입별 별점 차트
- **추천 제품:** 리뷰 점수 반영된 추천 제품 표시

---

## 4. 구현 단계

### 4.1 데이터베이스 스키마 확장 (1일)
- `product_reviews` 테이블 생성
- `product_review_aggregates` 테이블 생성
- `products` 테이블 확장
- 인덱스 생성

### 4.2 백엔드 개발 (4일)
- 리뷰 수집 로직 구현
- 리뷰 점수 집계 로직 구현
- 리뷰 기반 제품 매칭 알고리즘 구현
- 리뷰 분석 로직 구현
- API 엔드포인트 구현

### 4.3 제품 매칭 엔진 통합 (1일)
- 기존 제품 매칭 알고리즘에 리뷰 점수 통합
- 가중치 조절 기능 추가

### 4.4 배치 작업 구현 (0.5일)
- 리뷰 집계 주기적 업데이트 배치 작업

### 4.5 API 문서 업데이트 (0.5일)
- 새로운 엔드포인트 문서화
- 데이터 구조 문서화

### 4.6 클라이언트 UI 개발 (3일)
- 리뷰 작성 폼 구현
- 리뷰 목록 및 필터 구현
- 리뷰 통계 차트 구현
- 추천 제품 UI 업데이트
- API 연동

### 4.7 테스트 및 디버깅 (2일)
- 기능 테스트
- 데이터 무결성 테스트
- 성능 테스트
- 에러 처리 테스트

**총 예상 소요 시간: 12일**

---

## 5. 성능 고려사항

- **리뷰 집계 캐싱:** `product_review_aggregates` 테이블로 캐싱
- **배치 작업:** 리뷰 집계는 주기적 배치로 처리
- **인덱스 최적화:** 자주 조회하는 컬럼에 인덱스 생성
- **리뷰 로드 밸런싱:** 리뷰가 많은 제품 페이지네이션

---

## 6. 성공 지표

- **리뷰 수집률:** 제품 사용자의 30% 이상 리뷰 작성
- **추천 정확도:** 리뷰 통합 후 추천 정확도 +20%
- **사용자 만족도:** 리뷰 기반 추천 후 만족도 +15%
- **리뷰 응답 시간:** 0.5초 이내
- **집계 업데이트 지연:** 최대 1시간 이내
