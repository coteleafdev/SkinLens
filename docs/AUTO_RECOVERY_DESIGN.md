# 장애 자동 복구 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 장애 감지 시 자동 복구 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 장애 발생 시 수동 복구만 가능
- 복구 시간 길어짐
- 운영자 개입 필요
- 서비스 중단 시간 길어짐

### 1.2 제안된 기능
- 장애 자동 감지
- 자동 복구 프로세스
- 롤백 기능
- 장애 알림
- 복구 상태 모니터링
- 복구 로그 기록

### 1.3 기대 효과
- 운영 안정성 향상
- 복구 시간 단축
- 운영 부하 감소
- 서비스 중단 시간 감소

---

## 2. 장애 유형

### 2.1 서버 장애
- **API 서버 다운:** API 서버 프로세스 종료
- **워커 다운:** 분석/복원 워커 프로세스 종료
- **CPU 과부하:** CPU 사용률 90% 이상
- **메모리 부족:** 메모리 사용률 95% 이상

### 2.2 데이터베이스 장애
- **데이터베이스 다운:** 데이터베이스 서버 다운
- **연결 실패:** 데이터베이스 연결 실패
- **쿼리 타임아웃:** 쿼리 응답 시간 초과
- **디스크 부족:** 디스크 사용률 90% 이상

### 2.3 네트워크 장애
- **네트워크 단절:** 외부 네트워크 단절
- **DNS 장애:** DNS 해결 실패
- **로드 밸런서 장애:** 로드 밸런서 다운

### 2.4 애플리케이션 장애
- **애플리케이션 크래시:** 애플리케이션 예외 종료
- **메모리 누수:** 메모리 누수로 인한 성능 저하
- **데드락:** 데이터베이스 데드락

### 2.5 스토리지 장애
- **디스크 장애:** 디스크 장애
- **S3 장애:** S3 접근 실패
- **백업 장애:** 백업 실패

---

## 3. 자동 복구 아키텍처

### 3.1 장애 감지
1. **헬스 체크:** 주기적 헬스 체크
2. **메트릭 모니터링:** CPU, 메모리, 디스크 모니터링
3. **로그 모니터링:** 에러 로그 모니터링
4. **심장 박동 (Heartbeat):** 서비스 간 심장 박동 확인

### 3.2 복구 전략
- **재시작 (Restart):** 서비스 재시작
- **장애 조치 (Failover):** 대기 서버로 전환
- **스케일 아웃 (Scale Out):** 인스턴스 추가
- **롤백 (Rollback):** 이전 버전으로 롤백
- **데이터 복구:** 백업에서 데이터 복구

### 3.3 복구 우선순위
1. **P0 (Critical):** API 서버, 데이터베이스 (즉시 복구)
2. **P1 (High):** 분석 워커, 복원 워커 (5분 내 복구)
3. **P2 (Medium):** 캐시, 메시지 큐 (15분 내 복구)
4. **P3 (Low):** 로그, 모니터링 (1시간 내 복구)

### 3.4 롤백 전략
- **자동 롤백:** 복구 실패 시 자동 롤백
- **수동 롤백:** 운영자 수동 롤백
- **롤백 지점:** 안정적인 상태로 롤백
- **롤백 로그:** 롤백 기록

---

## 4. 기술 설계

### 4.1 장애 감지 시스템
1. **Prometheus Alertmanager:** 메트릭 기반 알림
2. **Health Check API:** 헬스 체크 엔드포인트
3. **Custom Monitoring:** 커스텀 모니터링 스크립트
4. **Log Aggregation:** ELK Stack으로 로그 수집

### 4.2 자동 복구 엔진
1. **복구 플레이북:** 각 장애 유형별 복구 플레이북
2. **복구 실행기:** 복구 플레이북 실행
3. **상태 추적:** 복구 상태 추적
4. **롤백 관리자:** 롤백 관리

### 4.3 복구 프로세스

#### 4.3.1 API 서버 장애 복구
1. 장애 감지 (헬스 체크 실패)
2. 서비스 재시작
3. 재시작 실패 시 장애 조치
4. 장애 조치 실패 시 롤백
5. 알림 전송

#### 4.3.2 데이터베이스 장애 복구
1. 장애 감지 (연결 실패)
2. 읽기 전용 복제본으로 전환
3. 마스터 복구 시도
4. 복구 실패 시 백업에서 복구
5. 알림 전송

#### 4.3.3 워커 장애 복구
1. 장애 감지 (프로세스 다운)
2. 워커 재시작
3. 재시작 실패 시 새 워커 생성
4. 작업 큐 재할당
5. 알림 전송

### 4.4 데이터 모델 설계

#### 4.4.1 장애 이벤트 테이블 (incident_events)
```sql
CREATE TABLE incident_events (
    id TEXT PRIMARY KEY,
    incident_type TEXT NOT NULL,               -- server_down, database_down, network_failure
    severity TEXT NOT NULL,                   -- P0, P1, P2, P3
    resource_type TEXT NOT NULL,              -- api_server, database, worker
    resource_id TEXT NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    status TEXT DEFAULT 'detected',           -- detected, recovering, resolved, failed
    description TEXT,
    FOREIGN KEY (resource_id) REFERENCES resources(id)
);

CREATE INDEX idx_incident_events_type ON incident_events(incident_type);
CREATE INDEX idx_incident_events_severity ON incident_events(severity);
CREATE INDEX idx_incident_events_detected ON incident_events(detected_at);
```

#### 4.4.2 복구 작업 테이블 (recovery_actions)
```sql
CREATE TABLE recovery_actions (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    action_type TEXT NOT NULL,                 -- restart, failover, rollback, scale_out
    action_status TEXT DEFAULT 'pending',     -- pending, in_progress, completed, failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    rollback_at TIMESTAMP,
    error_message TEXT,
    FOREIGN KEY (incident_id) REFERENCES incident_events(id)
);

CREATE INDEX idx_recovery_actions_incident ON recovery_actions(incident_id);
CREATE INDEX idx_recovery_actions_status ON recovery_actions(action_status);
```

#### 4.4.3 복구 로그 테이블 (recovery_logs)
```sql
CREATE TABLE recovery_logs (
    id TEXT PRIMARY KEY,
    recovery_action_id TEXT NOT NULL,
    log_level TEXT NOT NULL,                  -- info, warning, error
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recovery_action_id) REFERENCES recovery_actions(id)
);

CREATE INDEX idx_recovery_logs_action ON recovery_logs(recovery_action_id);
CREATE INDEX idx_recovery_logs_created ON recovery_logs(created_at);
```

### 4.5 API 엔드포인트

#### 4.5.1 헬스 체크
- **경로:** `/v3/health`
- **메서드:** `GET`
- **응답:**
```json
{
  "status": "healthy",
  "services": {
    "api_server": "healthy",
    "database": "healthy",
    "redis": "healthy",
    "s3": "healthy"
  },
  "timestamp": "2026-05-24T00:00:00Z"
}
```

#### 4.5.2 장애 이벤트 조회
- **경로:** `/v3/admin/incidents`
- **메서드:** `GET`
- **쿼리 파라미터:** `severity`, `status`, `start_date`, `end_date`, `limit`, `offset`
- **응답:**
```json
{
  "incidents": [
    {
      "id": "string",
      "incident_type": "server_down",
      "severity": "P0",
      "resource_type": "api_server",
      "resource_id": "string",
      "detected_at": "2026-05-24T00:00:00Z",
      "resolved_at": "2026-05-24T00:05:00Z",
      "status": "resolved"
    }
  ],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

#### 4.5.3 복구 작업 조회
- **경로:** `/v3/admin/incidents/{incident_id}/recovery-actions`
- **메서드:** `GET`
- **응답:**
```json
{
  "recovery_actions": [
    {
      "id": "string",
      "action_type": "restart",
      "action_status": "completed",
      "started_at": "2026-05-24T00:00:00Z",
      "completed_at": "2026-05-24T00:01:00Z"
    }
  ]
}
```

#### 4.5.4 수동 복구 트리거
- **경로:** `/v3/admin/incidents/{incident_id}/recover`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "action_type": "restart",
  "force": false
}
```
- **응답:**
```json
{
  "recovery_action_id": "string",
  "status": "in_progress"
}
```

#### 4.5.5 롤백 트리거
- **경로:** `/v3/admin/recovery-actions/{action_id}/rollback`
- **메서드:** `POST`
- **응답:**
```json
{
  "status": "rolling_back"
}
```

### 4.6 관리자 UI

#### 4.6.1 장애 대시보드
- **현재 장애:** 진행 중인 장애 표시
- **장애 이력:** 과거 장애 이력 표시
- **복구 상태:** 복구 작업 상태 표시
- **서비스 상태:** 각 서비스 상태 표시

#### 4.6.2 복구 관리
- **수동 복구:** 수동 복구 트리거
- **롤백:** 롤백 트리거
- **복구 로그:** 복구 로그 조회
- **복구 플레이북:** 복구 플레이북 관리

---

## 5. 구현 단계

### 4.1 장애 감지 시스템 (3일)
- Prometheus Alertmanager 설정
- Health Check API 구현
- Custom Monitoring 구현
- Log Aggregation 설정

### 4.2 자동 복구 엔진 (4일)
- 복구 플레이북 작성
- 복구 실행기 구현
- 상태 추적 구현
- 롤백 관리자 구현

### 4.3 데이터베이스 스키마 확장 (0.5일)
- `incident_events` 테이블 생성
- `recovery_actions` 테이블 생성
- `recovery_logs` 테이블 생성
- 인덱스 생성

### 4.4 백엔드 API 엔드포인트 (1.5일)
- 헬스 체크 엔드포인트 구현
- 장애 이벤트 엔드포인트 구현
- 복구 작업 엔드포인트 구현
- 롤백 엔드포인트 구현

### 4.5 알림 시스템 (1일)
- Slack 알림 구현
- PagerDuty 알림 구현
- 이메일 알림 구현
- 알림 템플릿 구현

### 4.6 관리자 UI (2일)
- 장애 대시보드 구현
- 복구 관리 UI 구현
- 복구 로그 UI 구현
- API 연동

### 4.7 API 문서 업데이트 (0.5일)
- 장애 복구 엔드포인트 문서화
- 데이터 구조 문서화

### 4.8 테스트 및 디버깅 (3일)
- 장애 감지 테스트
- 자동 복구 테스트
- 롤백 테스트
- 장애 시뮬레이션 테스트

**총 예상 소요 시간: 15.5일**

---

## 5. 성능 고려사항

- **장애 감지 시간:** 30초 이내
- **복구 시작 시간:** 감지 후 1분 이내
- **복구 완료 시간:** P0 장애 5분 이내, P1 장애 15분 이내
- **롤백 시간:** 2분 이내
- **알림 지연:** 1분 이내
- **거짓 양성:** 거짓 양성 최소화

---

## 6. 성공 지표

- **장애 감지율:** 95% 이상
- **자동 복구 성공률:** 90% 이상
- **평균 복구 시간 (MTTR):** 10분 이내
- **서비스 가용성:** 99.9% 이상
- **거짓 양성률:** 5% 이하
- **운영자 개입:** 자동 복구로 인한 운영자 개입 70% 감소
- **서비스 중단 시간:** 자동 복구 도입 후 중단 시간 50% 감소
