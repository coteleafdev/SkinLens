# 처방 이력 추적 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 처방 이력 및 효과 추적 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 단일 처방만 지원
- 과거 처방 이력 저장 안 됨
- 처방 효과 추적 불가
- 맞춤형 처방 최적화 어려움

### 1.2 제안된 기능
- 처방 이력 저장 및 관리
- 처방 사용 기록 추적
- 처방 효과 분석 (사용 전후 점수 비교)
- 맞춤형 처방 최적화 알고리즘
- 처방 추천 개선

### 1.3 기대 효과
- 맞춤형 처방 최적화
- 처방 효과 데이터 기반 의사결정
- 사용자 만족도 향상
- 장기적 피부 건강 관리

---

## 2. 데이터 모델 설계

### 2.1 처방 이력 테이블 (prescription_history)
```sql
CREATE TABLE prescription_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT NOT NULL,                    -- 분석 결과 ID
    prescription_id TEXT NOT NULL,           -- 처방 ID
    prescription_data JSON NOT NULL,         -- 처방 상세 데이터
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active',            -- active, completed, discontinued
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (job_id) REFERENCES analyses(id)
);

CREATE INDEX idx_prescription_history_user ON prescription_history(user_id);
CREATE INDEX idx_prescription_history_created ON prescription_history(created_at);
```

### 2.2 처방 사용 기록 테이블 (prescription_usage)
```sql
CREATE TABLE prescription_usage (
    id TEXT PRIMARY KEY,
    prescription_history_id TEXT NOT NULL,
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    compliance_score REAL DEFAULT 1.0,       -- 준수율 (0.0-1.0)
    notes TEXT,
    FOREIGN KEY (prescription_history_id) REFERENCES prescription_history(id)
);

CREATE INDEX idx_prescription_usage_history ON prescription_usage(prescription_history_id);
```

### 2.3 처방 효과 테이블 (prescription_effect)
```sql
CREATE TABLE prescription_effect (
    id TEXT PRIMARY KEY,
    prescription_history_id TEXT NOT NULL,
    before_job_id TEXT NOT NULL,             -- 처방 전 분석 ID
    after_job_id TEXT NOT NULL,              -- 처방 후 분석 ID
    before_scores JSON NOT NULL,             -- 처방 전 점수
    after_scores JSON NOT NULL,              -- 처방 후 점수
    improvements JSON NOT NULL,              -- 개선 데이터
    duration_days INTEGER NOT NULL,          -- 사용 기간 (일)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prescription_history_id) REFERENCES prescription_history(id),
    FOREIGN KEY (before_job_id) REFERENCES analyses(id),
    FOREIGN KEY (after_job_id) REFERENCES analyses(id)
);

CREATE INDEX idx_prescription_effect_history ON prescription_effect(prescription_history_id);
```

---

## 3. 기술 설계

### 3.1 처방 이력 저장
1. 처방 생성 시 `prescription_history` 테이블에 레코드 생성
2. 처방 데이터 (제품 목록, 사용법 등) JSON으로 저장
3. 사용자 ID와 연결하여 이력 관리

### 3.2 처방 사용 기록 추적
1. 사용자가 처방 사용 시 `prescription_usage` 테이블에 기록
2. 준수율 점수 저장 (사용자 자가 보고 또는 앱 내 체크)
3. 사용 노트 저장 (사용자 피드백)

### 3.3 처방 효과 분석
1. 처방 전 분석 결과와 처방 후 분석 결과 비교
2. 각 측정 항목별 점수 변화 계산
3. 전체 평균 점수 변화 계산
4. 사용 기간과 점수 변화 상관관계 분석
5. `prescription_effect` 테이블에 저장

### 3.4 맞춤형 처방 최적화
1. 과거 처방 이력 및 효과 데이터 분석
2. 사용자별 반응 패턴 식별
3. 효과적인 제품 카테고리 및 성분 식별
4. 비효과적인 제품 카테고리 및 성분 식별
5. 새로운 처방 생성 시 최적화 알고리즘 적용

### 3.5 API 엔드포인트

#### 3.5.1 처방 이력 조회
- **경로:** `/v3/prescription/history`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`, `limit`, `offset`
- **응답:**
```json
{
  "prescriptions": [
    {
      "id": "string",
      "prescription_id": "string",
      "prescription_data": {},
      "created_at": "2026-05-24T00:00:00Z",
      "status": "active"
    }
  ],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

#### 3.5.2 처방 사용 기록 저장
- **경로:** `/v3/prescription/{prescription_history_id}/usage`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "compliance_score": 0.8,
  "notes": "string"
}
```
- **응답:**
```json
{
  "id": "string",
  "prescription_history_id": "string",
  "used_at": "2026-05-24T00:00:00Z",
  "compliance_score": 0.8,
  "notes": "string"
}
```

#### 3.5.3 처방 효과 분석
- **경로:** `/v3/prescription/{prescription_history_id}/effect`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "after_job_id": "string"
}
```
- **응답:**
```json
{
  "id": "string",
  "before_scores": {},
  "after_scores": {},
  "improvements": {},
  "duration_days": 30,
  "overall_improvement": {
    "current_average": 57.5,
    "predicted_average": 51.7,
    "improvement": 5.8,
    "percentage": 10.1
  }
}
```

#### 3.5.4 처방 최적화 추천
- **경로:** `/v3/prescription/optimize`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "job_id": "string"
}
```
- **응답:**
```json
{
  "recommendations": {
    "effective_categories": ["세럼", "모이스처라이저"],
    "ineffective_categories": ["토너"],
    "suggested_adjustments": [
      {
        "category": "세럼",
        "reason": "과거 사용 시 hydration_score 15% 개선",
        "confidence": 0.8
      }
    ]
  }
}
```

### 3.6 클라이언트 UI/UX
- **처방 이력 탭:** 과거 처방 목록 표시
- **사용 기록 입력:** 일일 사용 체크 및 준수율 입력
- **효과 분석 차트:** 처방 전후 점수 비교 그래프
- **최적화 추천:** AI 기반 처방 개선 제안 표시
- **시간라인:** 처방 이력 시각적 타임라인

---

## 4. 구현 단계

### 4.1 데이터베이스 스키마 확장 (1일)
- `prescription_history` 테이블 생성
- `prescription_usage` 테이블 생성
- `prescription_effect` 테이블 생성
- 인덱스 생성

### 4.2 백엔드 개발 (4일)
- 처방 이력 저장 로직 구현
- 처방 사용 기록 추적 로직 구현
- 처방 효과 분석 알고리즘 구현
- 맞춤형 처방 최적화 알고리즘 구현
- API 엔드포인트 구현

### 4.3 처방 엔진 통합 (1일)
- 처방 생성 시 이력 저장 로직 통합
- 최적화 알고리즘 처방 엔진에 통합

### 4.4 API 문서 업데이트 (0.5일)
- 새로운 엔드포인트 문서화
- 데이터 구조 문서화

### 4.5 클라이언트 UI 개발 (3일)
- 처방 이력 탭 구현
- 사용 기록 입력 UI 구현
- 효과 분석 차트 구현
- 최적화 추천 UI 구현
- API 연동

### 4.6 테스트 및 디버깅 (2일)
- 기능 테스트
- 데이터 무결성 테스트
- 성능 테스트
- 에러 처리 테스트

**총 예상 소요 시간: 11.5일**

---

## 5. 성능 고려사항

- **데이터베이스 쿼리 최적화:** 인덱스 활용, 쿼리 튜닝
- **효과 분석 캐싱:** (prescription_history_id, after_job_id) 조합으로 캐싱
- **최적화 알고리즘:** 이력 데이터가 많아질수록 계산 시간 증가, 배치 처리 고려
- **데이터 보관 정책:** 오래된 이력 데이터 아카이빙

---

## 6. 성공 지표

- **이력 저장 성공률:** 99% 이상
- **효과 분석 응답 시간:** 1초 이내
- **최적화 추천 정확도:** 사용자 만족도 +15%
- **처방 준수율:** 이력 추적 도입 후 +20%
- **맞춤형 처방 효과:** 평균 점수 개선 +10%
