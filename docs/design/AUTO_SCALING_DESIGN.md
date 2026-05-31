# 자동 스케일링 설계 (Auto Scaling Design)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

이 문서는 트래픽에 따른 자동 스케일링 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 고정 리소스만 사용
- 트래픽 급증 시 성능 저하
- 유휴 리소스 비용 발생
- 수동 스케일링만 가능

### 1.2 제안된 기능
- 트래픽에 따른 자동 스케일링
- 수평 스케일링 (Horizontal Scaling)
- 수직 스케일링 (Vertical Scaling)
- 스케일링 정책 관리
- 비용 최적화
- 모니터링 및 알림

### 1.3 기대 효과
- 비용 최적화
- 성능 안정성 향상
- 운영 효율성 증대
- 사용자 경험 개선

---

## 2. 스케일링 아키텍처

### 2.1 스케일링 유형
- **수평 스케일링 (Horizontal Scaling):** 인스턴스 수 증감
- **수직 스케일링 (Vertical Scaling):** 인스턴스 사이즈 증감
- **컨테이너 스케일링:** 컨테이너 (Pod/Replica) 수 증감
- **데이터베이스 스케일링:** 읽기 전용 복제본 증감

### 2.2 스케일링 대상
- **API 서버:** FastAPI 서버
- **분석 워커:** 분석 작업 워커
- **복원 워커:** 복원 작업 워커
- **데이터베이스:** PostgreSQL 읽기 전용 복제본
- **캐시:** Redis 클러스터

### 2.3 스케일링 트리거
- **CPU 사용률:** 70% 이상 시 스케일 아웃
- **메모리 사용률:** 80% 이상 시 스케일 아웃
- **요청 큐 길이:** 100 이상 시 스케일 아웃
- **트래픽:** RPS (Requests Per Second) 기반
- **시간 기반:** 특정 시간대 스케일링 (예: 피크 타임)

### 2.4 스케일링 정책
- **스케일 아웃 (Scale Out):** 리소스 증가
- **스케일 인 (Scale In):** 리소스 감소
- **최소/최대 인스턴스:** 최소 2개, 최대 20개
- **쿨다운:** 스케일링 후 5분 쿨다운

---

## 3. 기술 설계

### 3.1 클라우드 제공자
- **AWS:** Auto Scaling Groups, EC2, ECS, Lambda
- **GCP:** Cloud Auto Scaler, Compute Engine, GKE, Cloud Functions
- **Azure:** Virtual Machine Scale Sets, AKS, Azure Functions

### 3.2 Kubernetes 스케일링
1. **HPA (Horizontal Pod Autoscaler):** CPU/메모리 기반 Pod 스케일링
2. **VPA (Vertical Pod Autoscaler):** Pod 리소스 자동 조정
3. **Cluster Autoscaler:** 노드 자동 스케일링
4. **KEDA (Kubernetes Event-driven Autoscaling):** 이벤트 기반 스케일링

### 3.3 모니터링
1. **메트릭 수집:** Prometheus, CloudWatch
2. **로그 수집:** ELK Stack, Cloud Logging
3. **알림:** PagerDuty, Slack 이메일
4. **대시보드:** Grafana, CloudWatch Dashboard

### 3.4 비용 최적화
1. **스팟 인스턴스:** 스팟 인스턴스 사용으로 비용 절감
2. **예약 인스턴스:** 예약 인스턴스로 비용 절감
3. **자동 종료:** 유휴 인스턴스 자동 종료
4. **리소스 태깅:** 비용 추적을 위한 리소스 태깅

### 3.5 스케일링 정책 구성

#### 3.5.1 API 서버 스케일링
- **기준:** CPU 사용률 70%
- **최소 인스턴스:** 2개
- **최대 인스턴스:** 10개
- **스케일 아웃:** CPU 70% 이상 시 1개 증가
- **스케일 인:** CPU 30% 이하 시 1개 감소
- **쿨다운:** 5분

#### 3.5.2 분석 워커 스케일링
- **기준:** 작업 큐 길이 50
- **최소 인스턴스:** 1개
- **최대 인스턴스:** 20개
- **스케일 아웃:** 큐 길이 50 이상 시 2개 증가
- **스케일 인:** 큐 길이 10 이하 시 1개 감소
- **쿨다운:** 3분

#### 3.5.3 데이터베이스 스케일링
- **기준:** CPU 사용률 60%
- **최소 복제본:** 1개 (기본)
- **최대 복제본:** 5개
- **스케일 아웃:** CPU 60% 이상 시 1개 증가
- **스케일 인:** CPU 30% 이하 시 1개 감소
- **쿨다운:** 10분

### 3.6 데이터 모델 설계

#### 3.6.1 스케일링 이벤트 테이블 (scaling_events)
```sql
CREATE TABLE scaling_events (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,               -- api_server, analysis_worker, database
    resource_id TEXT NOT NULL,
    scaling_action TEXT NOT NULL,             -- scale_out, scale_in
    before_value INTEGER NOT NULL,             -- 스케일링 전 인스턴스 수
    after_value INTEGER NOT NULL,              -- 스케일링 후 인스턴스 수
    trigger_metric TEXT NOT NULL,              -- cpu, memory, queue_length
    trigger_value REAL NOT NULL,               -- 트리거 값
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_scaling_events_resource ON scaling_events(resource_type);
CREATE INDEX idx_scaling_events_triggered ON scaling_events(triggered_at);
```

#### 3.6.2 비용 테이블 (cost_metrics)
```sql
CREATE TABLE cost_metrics (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    instance_count INTEGER NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cost_metrics_resource ON cost_metrics(resource_type);
CREATE INDEX idx_cost_metrics_period ON cost_metrics(period_start, period_end);
```

### 3.7 API 엔드포인트

#### 3.7.1 스케일링 정책 조회
- **경로:** `/v1/admin/scaling-policies`
- **메서드:** `GET`
- **응답:**
```json
{
  "policies": [
    {
      "resource_type": "api_server",
      "min_instances": 2,
      "max_instances": 10,
      "target_cpu_percent": 70,
      "scale_out_threshold": 70,
      "scale_in_threshold": 30,
      "cooldown_minutes": 5
    }
  ]
}
```

#### 3.7.2 스케일링 정책 업데이트
- **경로:** `/v1/admin/scaling-policies/{resource_type}`
- **메서드:** `PUT`
- **요청 바디:**
```json
{
  "min_instances": 2,
  "max_instances": 10,
  "target_cpu_percent": 70,
  "scale_out_threshold": 70,
  "scale_in_threshold": 30,
  "cooldown_minutes": 5
}
```
- **응답:**
```json
{
  "status": "updated"
}
```

#### 3.7.3 스케일링 이벤트 조회
- **경로:** `/v1/admin/scaling-events`
- **메서드:** `GET`
- **쿼리 파라미터:** `resource_type`, `start_date`, `end_date`, `limit`, `offset`
- **응답:**
```json
{
  "events": [
    {
      "id": "string",
      "resource_type": "api_server",
      "scaling_action": "scale_out",
      "before_value": 2,
      "after_value": 3,
      "trigger_metric": "cpu",
      "trigger_value": 75.5,
      "triggered_at": "2026-05-24T00:00:00Z"
    }
  ],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

#### 3.7.4 비용 메트릭 조회
- **경로:** `/v1/admin/cost-metrics`
- **메서드:** `GET`
- **쿼리 파라미터:** `resource_type`, `start_date`, `end_date`
- **응답:**
```json
{
  "metrics": [
    {
      "resource_type": "api_server",
      "cost_usd": 150.50,
      "instance_count": 5,
      "period_start": "2026-05-24T00:00:00Z",
      "period_end": "2026-05-25T00:00:00Z"
    }
  ],
  "total_cost_usd": 500.00
}
```

### 3.8 관리자 UI

#### 3.8.1 스케일링 대시보드
- **현재 리소스 상태:** 현재 인스턴스 수, CPU/메모리 사용률
- **스케일링 이벤트:** 최근 스케일링 이벤트 표시
- **비용 메트릭:** 비용 추이 차트
- **스케일링 정책:** 스케일링 정책 표시 및 수정

#### 3.8.2 스케일링 정책 관리
- **정책 설정:** 스케일링 정책 설정 UI
- **정책 수정:** 스케일링 정책 수정 UI
- **정책 테스트:** 스케일링 정책 테스트 기능

---

## 4. 구현 단계

### 4.1 클라우드 인프라 설정 (3일)
- 클라우드 제공자 선택 및 설정
- Auto Scaling 그룹 설정
- 로드 밸런서 설정
- 모니터링 도구 설정

### 4.2 Kubernetes 스케일링 설정 (2일)
- HPA 설정
- VPA 설정
- Cluster Autoscaler 설정
- KEDA 설정 (선택 사항)

### 4.3 스케일링 정책 구현 (2일)
- API 서버 스케일링 정책 구현
- 분석 워커 스케일링 정책 구현
- 데이터베이스 스케일링 정책 구현
- 캐시 스케일링 정책 구현

### 4.4 모니터링 및 알림 (2일)
- Prometheus/CloudWatch 설정
- Grafana/CloudWatch Dashboard 설정
- 알림 설정 (Slack, PagerDuty)
- 로그 수집 설정

### 4.5 비용 최적화 (2일)
- 스팟 인스턴스 설정
- 예약 인스턴스 설정
- 리소스 태깅 구현
- 비용 추적 구현

### 4.6 데이터베이스 스키마 확장 (0.5일)
- `scaling_events` 테이블 생성
- `cost_metrics` 테이블 생성
- 인덱스 생성

### 4.7 백엔드 API 엔드포인트 (1일)
- 스케일링 정책 엔드포인트 구현
- 스케일링 이벤트 엔드포인트 구현
- 비용 메트릭 엔드포인트 구현

### 4.8 관리자 UI (2일)
- 스케일링 대시보드 구현
- 스케일링 정책 관리 UI 구현
- API 연동

### 4.9 API 문서 업데이트 (0.5일)
- 스케일링 엔드포인트 문서화
- 데이터 구조 문서화

### 4.10 테스트 및 디버깅 (3일)
- 스케일링 테스트
- 부하 테스트
- 비용 테스트
- 장애 복구 테스트

**총 예상 소요 시간: 18일**

---

## 5. 성능 고려사항

- **스케일링 속도:** 스케일 아웃 2분 이내 완료
- **쿨다운:** 과도한 스케일링 방지를 위한 쿨다운
- **스케일링 임계값:** 최적의 임계값 튜닝
- **비용 모니터링:** 실시간 비용 모니터링
- **예산 경보:** 예산 초과 시 알림

---

## 6. 성공 지표

- **스케일링 응답 시간:** 2분 이내
- **가용성:** 99.9% 이상
- **비용 절감:** 자동 스케일링 도입 후 비용 20% 절감
- **CPU 사용률:** 평균 50-70% 유지

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (v1.0에서 마이그레이션) | Cascade |
| 0.1.0 | 2026-05-24 | 자동 스케일링 설계 문서 초기 작성 | Cascade |
