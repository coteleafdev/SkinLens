# A/B 테스트 프레임워크 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 분석 알고리즘 A/B 테스트 프레임워크의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 단일 버전 알고리즘만 운영
- 알고리즘 변경 시 전체 사용자 영향
- A/B 테스트 미지원
- 알고리즘 개선 속도 느림

### 1.2 제안된 기능
- 분석 알고리즘 A/B 테스트
- 사용자 그룹 분할
- 실험 관리 시스템
- 메트릭 추적
- 통계적 유의성 검증
- 자동 승자 선택

### 1.3 기대 효과
- 알고리즘 개선 속도 향상
- 리스크 감소
- 데이터 기반 의사결정
- 사용자 경험 개선

---

## 2. A/B 테스트 아키텍처

### 2.1 테스트 유형
- **분석 알고리즘 테스트:** 새로운 분석 알고리즘 vs 기존 알고리즘
- **처방 알고리즘 테스트:** 새로운 처방 알고리즘 vs 기존 알고리즘
- **UI/UX 테스트:** 새로운 UI vs 기존 UI
- **복원 알고리즘 테스트:** 새로운 복원 알고리즘 vs 기존 알고리즘

### 2.2 사용자 그룹 분할
- **랜덤 분할:** 사용자를 랜덤으로 A/B 그룹에 할당
- **일관성:** 동일 사용자는 동일 그룹 유지
- **분할 비율:** 50:50 또는 사용자 정의 (예: 70:30)
- **세분화:** 피부 타입, 지역 등으로 세분화 가능

### 2.3 메트릭
- **주요 메트릭:** 분석 정확도, 사용자 만족도, 처방 준수율
- **보조 메트릭:** 분석 시간, 복원 시간, 사용자 참여도
- **비즈니스 메트릭:** 구매 전환율, 리텐션, NPS

### 2.4 통계적 유의성
- **p-value:** 0.05 미만 시 유의성
- **신뢰 구간:** 95% 신뢰 구간
- **최소 샘플 크기:** 통계적 유의성을 위한 최소 샘플 크기
- **검정력:** 80% 검정력 목표

---

## 3. 기술 설계

### 3.1 실험 관리
1. **실험 생성:** 새로운 실험 생성
2. **그룹 할당:** 사용자 그룹 할당
3. **실험 시작:** 실험 시작
4. **메트릭 수집:** 메트릭 수집
5. **실험 종료:** 실험 종료
6. **결과 분석:** 결과 분석 및 승자 선택

### 3.2 사용자 그룹 할당
1. **해시 기반 할당:** 사용자 ID 해시로 그룹 할당
2. **일관성 보장:** 동일 사용자는 동일 그룹
3. **분할 비율:** 해시 모듈로 분할 비율 조절
4. **캐싱:** 그룹 할당 결과 캐싱

### 3.3 메트릭 추적
1. **이벤트 추적:** 사용자 행동 이벤트 추적
2. **메트릭 계산:** 메트릭 실시간 계산
3. **집계:** 그룹별 메트릭 집계
4. **비교:** 그룹 간 메트릭 비교

### 3.4 통계적 분석
1. **t-test:** 두 그룹 평균 비교
2. **chi-square test:** 범주형 데이터 비교
3. **신뢰 구간:** 신뢰 구간 계산
4. **유의성 검증:** p-value 계산

### 3.5 데이터 모델 설계

#### 3.5.1 실험 테이블 (experiments)
```sql
CREATE TABLE experiments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    experiment_type TEXT NOT NULL,            -- analysis_algorithm, prescription_algorithm, ui_ux
    status TEXT DEFAULT 'draft',             -- draft, running, completed, stopped
    variant_a JSON NOT NULL,                  -- A 그룹 설정
    variant_b JSON NOT NULL,                  -- B 그룹 설정
    split_ratio REAL DEFAULT 0.5,             -- 분할 비율 (0.0-1.0)
    target_metrics JSON NOT NULL,             -- 목표 메트릭
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_experiments_status ON experiments(status);
CREATE INDEX idx_experiments_type ON experiments(experiment_type);
```

#### 3.5.2 사용자 그룹 할당 테이블 (user_group_assignments)
```sql
CREATE TABLE user_group_assignments (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    group_variant TEXT NOT NULL,                -- A, B
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_user_group_assignments_experiment ON user_group_assignments(experiment_id);
CREATE INDEX idx_user_group_assignments_user ON user_group_assignments(user_id);
CREATE INDEX idx_user_group_assignments_variant ON user_group_assignments(group_variant);
```

#### 3.5.3 메트릭 테이블 (experiment_metrics)
```sql
CREATE TABLE experiment_metrics (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    group_variant TEXT NOT NULL,                -- A, B
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    user_id TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id)
);

CREATE INDEX idx_experiment_metrics_experiment ON experiment_metrics(experiment_id);
CREATE INDEX idx_experiment_metrics_variant ON experiment_metrics(group_variant);
CREATE INDEX idx_experiment_metrics_name ON experiment_metrics(metric_name);
CREATE INDEX idx_experiment_metrics_recorded ON experiment_metrics(recorded_at);
```

#### 3.5.4 실험 결과 테이블 (experiment_results)
```sql
CREATE TABLE experiment_results (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    group_variant TEXT NOT NULL,                -- A, B
    metric_name TEXT NOT NULL,
    mean_value REAL NOT NULL,
    std_deviation REAL,
    sample_size INTEGER NOT NULL,
    confidence_interval_lower REAL,
    confidence_interval_upper REAL,
    p_value REAL,
    is_significant BOOLEAN,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (experiment_id) REFERENCES experiments(id)
);

CREATE INDEX idx_experiment_results_experiment ON experiment_results(experiment_id);
```

### 3.6 API 엔드포인트

#### 3.6.1 실험 생성
- **경로:** `/v1/ab-testing/experiments`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "name": "분석 알고리즘 v2 테스트",
  "description": "새로운 분석 알고리즘 테스트",
  "experiment_type": "analysis_algorithm",
  "variant_a": {
    "algorithm_version": "1.0",
    "parameters": {}
  },
  "variant_b": {
    "algorithm_version": "2.0",
    "parameters": {}
  },
  "split_ratio": 0.5,
  "target_metrics": ["accuracy", "satisfaction"]
}
```
- **응답:**
```json
{
  "id": "string",
  "name": "분석 알고리즘 v2 테스트",
  "status": "draft"
}
```

#### 3.6.2 실험 시작
- **경로:** `/v1/ab-testing/experiments/{experiment_id}/start`
- **메서드:** `PUT`
- **요청 바디:**
```json
{
  "start_time": "2026-05-24T00:00:00Z"
}
```
- **응답:**
```json
{
  "id": "string",
  "status": "running",
  "start_time": "2026-05-24T00:00:00Z"
}
```

#### 3.6.3 사용자 그룹 조회
- **경로:** `/v1/ab-testing/user-group`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`, `experiment_id`
- **응답:**
```json
{
  "experiment_id": "string",
  "user_id": "string",
  "group_variant": "A",
  "variant_config": {
    "algorithm_version": "1.0",
    "parameters": {}
  }
}
```

#### 3.6.4 메트릭 기록
- **경로:** `/v1/ab-testing/metrics`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "experiment_id": "string",
  "user_id": "string",
  "group_variant": "A",
  "metrics": [
    {
      "name": "accuracy",
      "value": 0.85
    },
    {
      "name": "satisfaction",
      "value": 4.5
    }
  ]
}
```
- **응답:**
```json
{
  "status": "recorded"
}
```

#### 3.6.5 실험 결과 조회
- **경로:** `/v1/ab-testing/experiments/{experiment_id}/results`
- **메서드:** `GET`
- **응답:**
```json
{
  "experiment_id": "string",
  "results": [
    {
      "metric_name": "accuracy",
      "variant_a": {
        "mean_value": 0.82,
        "std_deviation": 0.05,
        "sample_size": 1000,
        "confidence_interval": [0.81, 0.83]
      },
      "variant_b": {
        "mean_value": 0.85,
        "std_deviation": 0.04,
        "sample_size": 1000,
        "confidence_interval": [0.84, 0.86]
      },
      "p_value": 0.001,
      "is_significant": true,
      "winner": "B"
    }
  ]
}
```

#### 3.6.6 실험 종료
- **경로:** `/v1/ab-testing/experiments/{experiment_id}/stop`
- **메서드:** `PUT`
- **응답:**
```json
{
  "id": "string",
  "status": "completed",
  "end_time": "2026-05-31T00:00:00Z"
}
```

### 3.7 클라이언트 구현

#### 3.7.1 실험 통합
1. **그룹 할당 요청:** 사용자 그룹 할당 요청
2. **변iant 적용:** 할당된 그룹에 따라 알고리즘 적용
3. **메트릭 기록:** 메트릭 기록
4. **결과 전송:** 결과 서버 전송

#### 3.7.2 분석 알고리즘 A/B 테스트
- **그룹 할당:** 분석 요청 시 그룹 할당
- **알고리즘 선택:** 그룹에 따라 알고리즘 선택
- **결과 비교:** 결과 메트릭 기록

#### 3.7.3 관리자 UI
- **실험 대시보드:** 진행 중인 실험 표시
- **실험 생성:** 새로운 실험 생성
- **결과 분석:** 실험 결과 분석
- **승자 선택:** 승자 선택 및 배포

---

## 4. 구현 단계

### 4.1 백엔드 A/B 테스트 프레임워크 (4일)
- 실험 관리 로직 구현
- 사용자 그룹 할당 로직 구현
- 메트릭 추적 로직 구현
- 통계적 분석 로직 구현

### 4.2 데이터베이스 스키마 확장 (1일)
- `experiments` 테이블 생성
- `user_group_assignments` 테이블 생성
- `experiment_metrics` 테이블 생성
- `experiment_results` 테이블 생성
- 인덱스 생성

### 4.3 백엔드 API 엔드포인트 (2일)
- 실험 관리 엔드포인트 구현
- 그룹 할당 엔드포인트 구현
- 메트릭 기록 엔드포인트 구현
- 결과 조회 엔드포인트 구현

### 4.4 백엔드 통계적 분석 (1.5일)
- t-test 구현
- chi-square test 구현
- 신뢰 구간 계산 구현
- p-value 계산 구현

### 4.5 분석 엔진 통합 (1.5일)
- 분석 알고리즘 A/B 테스트 통합
- 그룹 할당 로직 통합
- 메트릭 기록 통합

### 4.6 클라이언트 A/B 테스트 통합 (2일)
- 그룹 할당 요청 구현
- 알고리즘 선택 로직 구현
- 메트릭 기록 구현

### 4.7 관리자 UI (2일)
- 실험 대시보드 구현
- 실험 생성 UI 구현
- 결과 분석 UI 구현
- API 연동

### 4.8 API 문서 업데이트 (0.5일)
- A/B 테스트 엔드포인트 문서화
- 데이터 구조 문서화

### 4.9 테스트 및 디버깅 (2일)
- 그룹 할당 테스트
- 메트릭 추적 테스트
- 통계적 분석 테스트
- 실험 종단 테스트

**총 예상 소요 시간: 16.5일**

---

## 5. 성능 고려사항

- **그룹 할당 캐싱:** 그룹 할당 결과 캐싱
- **메트릭 배치 처리:** 대량 메트릭 배치 처리
- **실시간 집계:** 메트릭 실시간 집계
- **최소 샘플 크기:** 통계적 유의성을 위한 최소 샘플 크기 모니터링
- **실험 기간:** 최소 2주 권장

---

## 6. 성공 지표

- **실험 생성 수:** 월 5개 이상 실험 생성
- **실험 완료율:** 90% 이상 실험 완료
- **그룹 할당 정확도:** 99% 이상 정확한 그룹 할당
- **메트릭 수집률:** 95% 이상 메트릭 수집
- **알고리즘 개선 속도:** A/B 테스트 도입 후 개선 속도 +50%
- **사용자 경험:** A/B 테스트로 인한 사용자 경험 저하 0%
- **통계적 유의성:** 80% 이상 실험이 통계적 유의성 달성
