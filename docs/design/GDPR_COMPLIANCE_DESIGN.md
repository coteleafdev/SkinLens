# GDPR 준수 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 GDPR (General Data Protection Regulation) 준수를 위한 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 기본 개인정보 보호만 제공
- 데이터 삭제 권한 미지원
- 데이터 이동 권한 미지원
- 유럽 시장 진입 제한

### 1.2 제안된 기능
- 데이터 삭제 권한 (Right to Erasure)
- 데이터 이동 권한 (Right to Data Portability)
- 데이터 접근 권한 (Right to Access)
- 데이터 처리 동의 관리
- 동의 철회 기능
- 데이터 보유 기간 관리

### 1.3 기대 효과
- 유럽 시장 진입
- 규제 준수
- 사용자 신뢰도 향상
- 법적 리스크 감소

---

## 2. GDPR 요구사항

### 2.1 데이터 주체 권리
- **접근 권한 (Right to Access):** 사용자가 자신의 데이터에 접근할 권리
- **삭제 권한 (Right to Erasure):** 사용자가 자신의 데이터 삭제를 요청할 권리
- **이동 권한 (Right to Data Portability):** 사용자가 자신의 데이터를 다른 서비스로 이동할 권리
- **수정 권한 (Right to Rectification):** 사용자가 부정확한 데이터 수정을 요청할 권리
- **반대 권한 (Right to Object):** 사용자가 데이터 처리에 반대할 권리
- **동의 철회 권한 (Right to Withdraw Consent):** 사용자가 동의를 철회할 권리

### 2.2 데이터 보유 기간
- **분석 결과:** 2년 보유 (사용자 요청 시 즉시 삭제)
- **이미지:** 1년 보유 (사용자 요청 시 즉시 삭제)
- **로그 데이터:** 6개월 보유
- **동의 기록:** 3년 보유

### 2.3 동의 관리
- **명시적 동의:** 데이터 처리에 대한 명시적 동의
- **동의 기록:** 동의 시점, 동의 내용 기록
- **동의 철회:** 언제든지 동의 철회 가능
- **동의 범위:** 각 데이터 처리 유형별 동의

---

## 3. 기술 설계

### 3.1 데이터 삭제 프로세스
1. 사용자가 데이터 삭제 요청
2. 삭제 요청 검증 (신원 확인)
3. 삭제 범위 확인 (전체 또는 특정 데이터)
4. 데이터베이스에서 데이터 삭제
5. 백업에서 데이터 삭제 (보유 기간 경과 후)
6. 삭제 완료 알림
7. 삭제 기록 저장

### 3.2 데이터 이동 프로세스
1. 사용자가 데이터 이동 요청
2. 이동 요청 검증 (신원 확인)
3. 사용자 데이터 수집
4. 데이터 포맷팅 (JSON, CSV 등)
5. 데이터 압축
6. 다운로드 링크 생성
7. 이동 완료 알림

### 3.3 데이터 접근 프로세스
1. 사용자가 데이터 접근 요청
2. 접근 요청 검증 (신원 확인)
3. 사용자 데이터 수집
4. 데이터 요약 생성
5. 데이터 표시
6. 접근 기록 저장

### 3.4 동의 관리 프로세스
1. 사용자 등록 시 동의 요청
2. 동의 내용 명시
3. 동의 기록 저장
4. 동의 철회 기능 제공
5. 동의 변경 시 알림

### 3.5 데이터 모델 설계

#### 3.5.1 동의 테이블 (consents)
```sql
CREATE TABLE consents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    consent_type TEXT NOT NULL,                -- data_processing, marketing, analytics
    consent_given BOOLEAN NOT NULL,
    consent_text TEXT NOT NULL,                -- 동의 내용
    consent_version TEXT NOT NULL,             -- 동의 버전
    given_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    withdrawn_at TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_consents_user ON consents(user_id);
CREATE INDEX idx_consents_type ON consents(consent_type);
```

#### 3.5.2 데이터 삭제 요청 테이블 (data_deletion_requests)
```sql
CREATE TABLE data_deletion_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    request_type TEXT NOT NULL,                 -- full, partial
    data_types JSON,                          -- 삭제할 데이터 유형
    status TEXT DEFAULT 'pending',             -- pending, processing, completed, failed
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    failure_reason TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_data_deletion_requests_user ON data_deletion_requests(user_id);
CREATE INDEX idx_data_deletion_requests_status ON data_deletion_requests(status);
```

#### 3.5.3 데이터 이동 요청 테이블 (data_portability_requests)
```sql
CREATE TABLE data_portability_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    format TEXT DEFAULT 'json',                -- json, csv
    status TEXT DEFAULT 'pending',             -- pending, processing, completed, failed
    download_url TEXT,
    expires_at TIMESTAMP,
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    failure_reason TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_data_portability_requests_user ON data_portability_requests(user_id);
CREATE INDEX idx_data_portability_requests_status ON data_portability_requests(status);
```

#### 3.5.4 데이터 접근 로그 테이블 (data_access_logs)
```sql
CREATE TABLE data_access_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    access_type TEXT NOT NULL,                  -- view, export, delete
    data_types JSON,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_data_access_logs_user ON data_access_logs(user_id);
CREATE INDEX idx_data_access_logs_accessed ON data_access_logs(accessed_at);
```

### 3.6 API 엔드포인트

#### 3.6.1 동의 등록
- **경로:** `/v1/gdpr/consent`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "consent_type": "data_processing",
  "consent_given": true,
  "consent_version": "1.0"
}
```
- **응답:**
```json
{
  "id": "string",
  "status": "recorded"
}
```

#### 3.6.2 동의 철회
- **경로:** `/v1/gdpr/consent/{consent_id}/withdraw`
- **메서드:** `PUT`
- **요청 바디:**
```json
{
  "user_id": "string"
}
```
- **응답:**
```json
{
  "status": "withdrawn"
}
```

#### 3.6.3 동의 조회
- **경로:** `/v1/gdpr/consents`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`
- **응답:**
```json
{
  "consents": [
    {
      "id": "string",
      "consent_type": "data_processing",
      "consent_given": true,
      "given_at": "2026-05-24T00:00:00Z",
      "withdrawn_at": null
    }
  ]
}
```

#### 3.6.4 데이터 삭제 요청
- **경로:** `/v1/gdpr/data-deletion`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "request_type": "full",
  "data_types": ["analyses", "images", "prescriptions"]
}
```
- **응답:**
```json
{
  "id": "string",
  "status": "pending",
  "estimated_completion": "2026-05-24T01:00:00Z"
}
```

#### 3.6.5 데이터 삭제 상태 조회
- **경로:** `/v1/gdpr/data-deletion/{request_id}`
- **메서드:** `GET`
- **응답:**
```json
{
  "id": "string",
  "status": "completed",
  "requested_at": "2026-05-24T00:00:00Z",
  "completed_at": "2026-05-24T00:30:00Z"
}
```

#### 3.6.6 데이터 이동 요청
- **경로:** `/v1/gdpr/data-portability`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "format": "json"
}
```
- **응답:**
```json
{
  "id": "string",
  "status": "pending",
  "estimated_completion": "2026-05-24T01:00:00Z"
}
```

#### 3.6.7 데이터 이동 다운로드
- **경로:** `/v1/gdpr/data-portability/{request_id}/download`
- **메서드:** `GET`
- **응답:** 데이터 파일 (JSON/CSV)

#### 3.6.8 데이터 접근 요청
- **경로:** `/v1/gdpr/data-access`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`
- **응답:**
```json
{
  "user_data": {
    "profile": {},
    "analyses": [],
    "prescriptions": [],
    "consents": []
  },
  "data_summary": {
    "total_analyses": 10,
    "total_prescriptions": 5,
    "data_size_mb": 25.5
  }
}
```

### 3.7 클라이언트 구현

#### 3.7.1 Flutter GDPR UI
1. **설정 화면:** GDPR 관련 설정
2. **동의 관리:** 동의 확인 및 철회
3. **데이터 삭제:** 데이터 삭제 요청
4. **데이터 이동:** 데이터 이동 요청
5. **데이터 접근:** 데이터 접근 및 확인

#### 3.7.2 동의 UI
- **동의 화면:** 등록 시 동의 요청
- **동의 관리 화면:** 현재 동의 상태 표시
- **동의 철회 버튼:** 동의 철회 기능

#### 3.7.3 데이터 삭제 UI
- **데이터 삭제 요청 화면:** 삭제 범위 선택
- **삭제 진행률:** 삭제 진행률 표시
- **삭제 완료 알림:** 삭제 완료 알림

#### 3.7.4 데이터 이동 UI
- **데이터 이동 요청 화면:** 포맷 선택
- **다운로드 링크:** 다운로드 링크 표시
- **이동 완료 알림:** 이동 완료 알림

#### 3.7.5 데이터 접근 UI
- **데이터 접근 화면:** 사용자 데이터 표시
- **데이터 요약:** 데이터 요약 정보
- **데이터 내보내기:** 데이터 내보내기 기능

---

## 4. 구현 단계

### 4.1 백엔드 GDPR 로직 (3일)
- 데이터 삭제 로직 구현
- 데이터 이동 로직 구현
- 데이터 접근 로직 구현
- 동의 관리 로직 구현

### 4.2 데이터베이스 스키마 확장 (1일)
- `consents` 테이블 생성
- `data_deletion_requests` 테이블 생성
- `data_portability_requests` 테이블 생성
- `data_access_logs` 테이블 생성
- 인덱스 생성

### 4.3 백엔드 API 엔드포인트 (2일)
- 동의 엔드포인트 구현
- 데이터 삭제 엔드포인트 구현
- 데이터 이동 엔드포인트 구현
- 데이터 접근 엔드포인트 구현

### 4.4 백엔드 데이터 보유 기간 (1일)
- 데이터 보유 기간 정책 구현
- 자동 삭제 배치 작업 구현
- 백업 정리 작업 구현

### 4.5 클라이언트 GDPR UI (2일)
- 동의 관리 UI 구현
- 데이터 삭제 UI 구현
- 데이터 이동 UI 구현
- 데이터 접근 UI 구현

### 4.6 클라이언트 동의 화면 (1일)
- 등록 시 동의 화면 구현
- 동의 내용 표시
- 동의 기록 구현

### 4.7 API 문서 업데이트 (0.5일)
- GDPR 엔드포인트 문서화
- 데이터 구조 문서화
- GDPR 가이드 문서화

### 4.8 테스트 및 디버깅 (2일)
- 데이터 삭제 테스트
- 데이터 이동 테스트
- 데이터 접근 테스트
- 동의 관리 테스트
- 규정 준수 테스트

**총 예상 소요 시간: 12.5일**

---

## 5. 성능 고려사항

- **데이터 삭제 시간:** 대량 데이터 삭제 시 배치 처리
- **데이터 이동 시간:** 대량 데이터 이동 시 비동기 처리
- **다운로드 링크 만료:** 7일 후 만료
- **데이터 압축:** 대량 데이터 압축
- **삭제 요청 큐:** 삭제 요청 큐로 처리
- **로그 저장:** 접근 로그 장기 저장

---

## 6. 성공 지표

- **데이터 삭제 완료율:** 99% 이상
- **데이터 이동 완료율:** 99% 이상
- **데이터 접근 응답 시간:** 5초 이내
- **동의 기록 완료율:** 100%
- **규정 준수:** GDPR 규정 100% 준수
- **사용자 신뢰도:** GDPR 준수 후 신뢰도 +25%
- **유럽 시장 진입:** 유럽 시장 진입 성공
