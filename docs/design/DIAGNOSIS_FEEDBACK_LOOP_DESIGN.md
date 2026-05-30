# 소견 피드백 루프 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 소견에 대한 사용자 피드백 수집 및 LLM 재학습 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 일방향 소견 제공
- 사용자 피드백 수집 안 됨
- 소견 품질 개선 어려움
- LLM 모델 정적 유지

### 1.2 제안된 기능
- 소견에 대한 사용자 피드백 수집
- 피드백 데이터 저장 및 분석
- LLM 재학습 파이프라인
- 소견 품질 지속 개선
- A/B 테스팅 지원

### 1.3 기대 효과
- 소견 품질 지속 개선
- 사용자 만족도 향상
- 모델 성능 최적화
- 개인화된 소견 제공

---

## 2. 피드백 데이터 모델 설계

### 2.1 소견 피드백 테이블 (diagnosis_feedback)
```sql
CREATE TABLE diagnosis_feedback (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,              -- rating, correction, suggestion
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    correction_text TEXT,                     -- 사용자 수정 소견
    suggestion_text TEXT,                     -- 사용자 제안
    feedback_section TEXT,                    -- 피드백 대상 섹션 (summary, recommendations, etc.)
    original_text TEXT,                       -- 원본 소견 텍스트
    is_helpful BOOLEAN,                       -- 도움이 되었는지 여부
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES analyses(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_diagnosis_feedback_job ON diagnosis_feedback(job_id);
CREATE INDEX idx_diagnosis_feedback_user ON diagnosis_feedback(user_id);
CREATE INDEX idx_diagnosis_feedback_type ON diagnosis_feedback(feedback_type);
```

### 2.2 피드백 집계 테이블 (diagnosis_feedback_aggregates)
```sql
CREATE TABLE diagnosis_feedback_aggregates (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    total_feedback INTEGER DEFAULT 0,
    average_rating REAL DEFAULT 0.0,
    helpful_count INTEGER DEFAULT 0,
    correction_count INTEGER DEFAULT 0,
    suggestion_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES analyses(id)
);
```

### 2.3 LLM 학습 데이터 테이블 (llm_training_data)
```sql
CREATE TABLE llm_training_data (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    input_data JSON NOT NULL,                 -- 분석 입력 데이터
    original_output TEXT NOT NULL,            -- 원본 LLM 출력
    corrected_output TEXT,                    -- 수정된 출력 (피드백 기반)
    feedback_id TEXT,                         -- 연결된 피드백 ID
    is_approved BOOLEAN DEFAULT FALSE,        -- 학습 데이터 승인 여부
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES analyses(id),
    FOREIGN KEY (feedback_id) REFERENCES diagnosis_feedback(id)
);

CREATE INDEX idx_llm_training_data_job ON llm_training_data(job_id);
CREATE INDEX idx_llm_training_data_approved ON llm_training_data(is_approved);
```

---

## 3. 기술 설계

### 3.1 피드백 수집
1. 소견 표시 후 피드백 요청
2. 피드백 유형 선택 (별점, 수정, 제안)
3. 피드백 데이터 저장
4. 피드백 집계 업데이트

### 3.2 피드백 유형
- **별점 (rating):** 1-5점으로 소견 품질 평가
- **수정 (correction):** 사용자가 직접 소견 수정
- **제안 (suggestion):** 소견 개선 제안
- **도움 여부 (helpful):** 소견이 도움이 되었는지 여부

### 3.3 피드백 분석
1. 피드백 패턴 분석
2. 자주 수정되는 섹션 식별
3. 낮은 별점 소견 특성 분석
4. 개선 필요 영역 식별

### 3.4 LLM 재학습 파이프라인
1. **데이터 수집:** 피드백 데이터 수집
2. **데이터 전처리:** 피드백 데이터 정제 및 포맷팅
3. **데이터 승인:** 수동 검수 또는 자동 필터링
4. **파인튜닝:** 승인된 데이터로 LLM 파인튜닝
5. **모델 평가:** 재학습 모델 성능 평가
6. **A/B 테스팅:**新旧 모델 비교 테스트
7. **배포:** 성능 개선 시 모델 배포

### 3.5 A/B 테스팅
1. 사용자 그룹 분할 (A 그룹: 기존 모델, B 그룹: 새 모델)
2. 소견 품질 비교 (별점, 도움 여부)
3. 통계적 유의성 검증
4. 우수 모델 선택 및 전면 배포

### 3.6 API 엔드포인트

#### 3.6.1 피드백 제출
- **경로:** `/v1/diagnosis/{job_id}/feedback`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "feedback_type": "rating",
  "rating": 4,
  "feedback_section": "summary",
  "is_helpful": true
}
```
- **응답:**
```json
{
  "id": "string",
  "job_id": "string",
  "feedback_type": "rating",
  "created_at": "2026-05-24T00:00:00Z"
}
```

#### 3.6.2 소견 수정
- **경로:** `/v1/diagnosis/{job_id}/correct`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "feedback_section": "summary",
  "original_text": "피부 상태가 좋지 않습니다",
  "correction_text": "피부 수분이 부족하고 유분이 많습니다"
}
```
- **응답:**
```json
{
  "id": "string",
  "job_id": "string",
  "feedback_type": "correction",
  "created_at": "2026-05-24T00:00:00Z"
}
```

#### 3.6.3 피드백 통계 조회
- **경로:** `/v1/diagnosis/feedback-statistics`
- **메서드:** `GET`
- **쿼리 파라미터:** `start_date`, `end_date`
- **응답:**
```json
{
  "total_feedback": 1000,
  "average_rating": 4.2,
  "helpful_percentage": 85,
  "feedback_by_type": {
    "rating": 700,
    "correction": 200,
    "suggestion": 100
  },
  "feedback_by_section": {
    "summary": 300,
    "recommendations": 400,
    "analysis": 300
  }
}
```

#### 3.6.4 학습 데이터 승인
- **경로:** `/v1/admin/training-data/{id}/approve`
- **메서드:** `PUT`
- **요청 바디:**
```json
{
  "is_approved": true
}
```
- **응답:**
```json
{
  "id": "string",
  "is_approved": true
}
```

### 3.7 클라이언트 UI/UX
- **피드백 버튼:** 소견 하단에 피드백 버튼 표시
- **별점 UI:** 1-5점 별점 선택 UI
- **수정 UI:** 소견 텍스트 직접 수정 가능
- **제안 UI:** 개선 제안 입력 폼
- **도움 여부:** "도움이 되었나요?" 토글
- **피드백 감사 메시지:** 피드백 제출 후 감사 메시지

---

## 4. 구현 단계

### 4.1 데이터베이스 스키마 확장 (1일)
- `diagnosis_feedback` 테이블 생성
- `diagnosis_feedback_aggregates` 테이블 생성
- `llm_training_data` 테이블 생성
- 인덱스 생성

### 4.2 백엔드 개발 (3일)
- 피드백 수집 로직 구현
- 피드백 집계 로직 구현
- 피드백 분석 로직 구현
- API 엔드포인트 구현

### 4.3 LLM 재학습 파이프라인 (5일)
- 데이터 전처리 파이프라인 구현
- 파인튜닝 스크립트 구현
- 모델 평가 스크립트 구현
- A/B 테스팅 시스템 구현
- 배포 파이프라인 구현

### 4.4 소견 엔진 통합 (1일)
- 피드백 데이터 소견 엔진에 통합
- A/B 테스팅 소견 엔진에 통합

### 4.5 API 문서 업데이트 (0.5일)
- 새로운 엔드포인트 문서화
- 데이터 구조 문서화

### 4.6 클라이언트 UI 개발 (2일)
- 피드백 버튼 구현
- 별점 UI 구현
- 수정 UI 구현
- 제안 UI 구현
- API 연동

### 4.7 테스트 및 디버깅 (2일)
- 기능 테스트
- 피드백 수집 테스트
- 재학습 파이프라인 테스트
- A/B 테스팅 테스트

**총 예상 소요 시간: 14.5일**

---

## 5. 성능 고려사항

- **피드백 데이터 배치 처리:** 대량 피드백 데이터 배치 처리
- **LLM 재학습 스케줄링:** 주기적 재학습 (예: 월 1회)
- **A/B 테스팅 부하:** 테스트 그룹 분배 로직 최적화
- **데이터 보관 정책:** 오래된 피드백 데이터 아카이빙

---

## 6. 성공 지표

- **피드백 수집률:** 소견 조회의 20% 이상 피드백 제출
- **평균 별점:** 4.0 이상 유지
- **도움 여부:** 80% 이상 긍정 응답
- **소견 품질 개선:** 재학습 후 평균 별점 +0.3
- **모델 성능:** 재학습 모델이 기존 모델 대비 5% 이상 성능 향상
