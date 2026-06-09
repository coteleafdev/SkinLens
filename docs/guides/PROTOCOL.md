# 시스템 프로토콜 (System Protocol)

> **⚠️ 최상위 문서 (Top-Level Document)**: 이 문서는 스마트폰 앱, 웹서버, 엔진서버 간의 통신 프로토콜을 정의하는 최상위 문서입니다. 모든 개발자가 먼저 읽어야 합니다.
> 
> **관련 최상위 문서**: 
> - [ARCHITECTURE.md](ARCHITECTURE.md) - 아키텍처
> - [../api/API_REFERENCE.md](../api/API_REFERENCE.md) - API 레퍼런스

> **문서 버전:** 2.1.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-06-01  
> **상태:** 활성

---

## 개요

이 문서는 스마트폰 앱, 웹서버, 엔진서버 간 통신 프로토콜을 포함한 완성본입니다. 보안, 모니터링, 배포, 테스트 등 운영 전반에 필요한 사항을 포함합니다.

---

## 1. 시스템 아키텍처

### 1.1 전체 구조

```mermaid
graph LR
    subgraph "스마트폰 앱"
        A1[사용자 인터페이스]
        A2[이미지 캡처]
        A3[설문 조사]
    end
    
    subgraph "웹서버"
        B1[인증 서비스<br/>JWT/OAuth]
        B2[API 게이트웨이]
        B3[데이터베이스<br/>고객/설문/결과]
        B4[푸시 서비스<br/>FCM/APNS]
        B5[모니터링<br/>로깅]
    end
    
    subgraph "엔진서버"
        C1[API Layer<br/>FastAPI]
        C2[Business Logic Layer<br/>Pipeline, Scoring]
        C3[Data Layer<br/>SQLite, File System]
        C4[웹훅 서비스]
        C5[WebSocket 서비스]
    end
    
    subgraph "외부 서비스"
        D1[OAuth 제공자]
        D2[LLM API]
        D3[푸시 서비스<br/>FCM/APNS]
        D4[모니터링<br/>Prometheus/Grafana]
    end
    
    A1 -->|로그인| B1
    A3 -->|설문 제출| B2
    A2 -->|이미지 전송| B2
    B1 -->|토큰 발급| A1
    
    B2 -->|분석 요청| C1
    C4 -->|웹훅 알림| B2
    B4 -->|푸시 알림| A1
    A1 -->|WebSocket| C5
    
    B1 -->|OAuth| D1
    C2 -->|LLM 요청| D2
    B5 -->|메트릭| D4
    
    B1 --> B3
    C1 --> C2
    C2 --> C3
```

### 1.2 통신 방식 요약

| 통신 방식 | 방향 | 용도 | 프로토콜 | 보안 |
|----------|------|------|----------|------|
| REST API | 스마트폰 앱 → 웹서버 | 로그인, 설문, 이미지 전송 | HTTPS | TLS 1.3 |
| REST API | 웹서버 → 엔진서버 | 분석 요청, 데이터 조회 | HTTPS | TLS 1.3 |
| 웹훅 | 엔진서버 → 웹서버 | 분석 결과 알림 | HTTPS | HMAC-SHA256 |
| 푸시 알림 | 웹서버 → 스마트폰 앱 | 분석 완료 알림 | FCM/APNS | API Key |
| WebSocket | 클라이언트 ↔ 엔진서버 | 실시간 진행률 전송 | WSS | TLS 1.3 |
| OAuth | 웹서버 ↔ 엔진서버 | 인증 통합 | OAuth 2.0 | PKCE |

---

## 2. 스마트폰 앱 ↔ 웹서버 통신

### 2.1 로그인

**엔드포인트**: `POST /auth/login`

**요청 헤더**:
```
Content-Type: application/json
X-Device-ID: {device_id}
X-App-Version: {app_version}
```

**요청 본문**:
```json
{
  "username": "user@example.com",
  "password": "password123"
}
```

**응답**:
```json
{
  "access_token": "jwt_token_value",
  "refresh_token": "refresh_token_value",
  "token_type": "Bearer",
  "expires_in": 3600,
  "customer_id": "customer-123"
}
```

### 2.2 토큰 갱신

**엔드포인트**: `POST /v1/auth/refresh`

**요청 본문**:
```json
{
  "refresh_token": "refresh_token_value"
}
```

**응답**:
```json
{
  "access_token": "new_jwt_token_value",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 2.3 로그아웃

**엔드포인트**: `POST /v1/auth/logout`

**요청 본문**:
```json
{
  "refresh_token": "refresh_token_value"
}
```

**응답**:
```json
{
  "message": "Logged out successfully"
}
```

### 2.4 비밀번호 변경

**엔드포인트**: `POST /v1/auth/change-password`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**요청 본문**:
```json
{
  "old_password": "old_password",
  "new_password": "new_password"
}
```

**응답**:
```json
{
  "message": "Password changed successfully"
}
```

### 2.5 비밀번호 찾기

**엔드포인트**: `POST /v1/auth/forgot-password`

**요청 본문**:
```json
{
  "username": "user123"
}
```

**응답**:
```json
{
  "message": "If the user exists, a password reset link will be sent",
  "reset_token": "reset_token_value"
}
```

### 2.6 비밀번호 재설정

**엔드포인트**: `POST /v1/auth/reset-password`

**요청 본문**:
```json
{
  "token": "reset_token_value",
  "new_password": "new_password"
}
```

**응답**:
```json
{
  "message": "Password reset successfully"
}
```

### 2.7 설문 데이터 제출

**엔드포인트**: `POST /survey`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**요청 본문**:
```json
{
  "customer_id": "customer-123",
  "survey_data": {
    "age": 30,
    "gender": "female",
    "skin_type": "oily",
    "concerns": ["acne", "pores"],
    "lifestyle": {
      "sleep_hours": 7,
      "water_intake": 2,
      "smoking": false
    }
  }
}
```

**응답**:
```json
{
  "survey_id": "uuid-v4",
  "status": "saved",
  "message": "설문이 저장되었습니다"
}
```

### 2.8 설문 데이터 조회

**엔드포인트**: `GET /v1/customer/my/surveys`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
```json
{
  "surveys": [
    {
      "survey_id": "uuid-v4",
      "customer_id": "customer-123",
      "survey_data": {...},
      "created_at": "2026-06-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

### 2.9 설문 데이터 수정

**엔드포인트**: `PUT /v1/customer/my/surveys/{survey_id}`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**요청 본문**:
```json
{
  "survey_data": {
    "age": 31,
    "gender": "female"
  }
}
```

**응답**:
```json
{
  "message": "Survey updated successfully"
}
```

### 2.10 설문 데이터 삭제

**엔드포인트**: `DELETE /v1/customer/my/surveys/{survey_id}`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
```json
{
  "message": "Survey deleted successfully"
}
```

### 2.11 분석 결과 이미지 다운로드

**엔드포인트**: `GET /v1/customer/my/analyses/{analysis_id}/download?image_type=restored`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
- Content-Type: image/png
- 파일 다운로드

### 2.12 이미지 전송

**엔드포인트**: `POST /analysis/upload`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: multipart/form-data
X-File-Hash: sha256={file_hash}
```

**요청 파라미터**:
- `file`: 이미지 파일 (multipart/form-data, 최대 10MB)
- `survey_id`: 설문 ID (선택)
- `customer_id`: 고객 ID

**응답**:
```json
{
  "job_id": "uuid-v4",
  "status": "pending",
  "message": "분석 작업이 생성되었습니다"
}
```

### 2.13 분석 결과 조회

**엔드포인트**: `GET /analysis/result/{job_id}`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
```json
{
  "job_id": "uuid-v4",
  "status": "succeeded",
  "result": {
    "overall_score_original": 68.4,
    "overall_score_restored": 71.2,
    "skin_types": {
      "melasma_score": 65.0,
      "freckle_score": 60.0,
      "redness_score": 45.0
    },
    "prescription": {
      "M08": 1.3,
      "M14": 1.5,
      "M12": 0.8,
      "M13": 0.8,
      "M11": 2.3
    },
    "llm_report": {
      "recommendations": "...",
      "product_suggestions": [...]
    }
  },
  "artifacts": {
    "restored_image": "https://web-server.com/results/{job_id}/restored.png",
    "input_image": "https://web-server.com/results/{job_id}/input.png"
  },
  "finished_at": "2026-06-01T00:05:00Z"
}
```

### 2.14 프로필 조회

**엔드포인트**: `GET /v1/customer/my/profile`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
```json
{
  "customer_id": "customer-123",
  "username": "user123",
  "role": "customer",
  "is_active": true,
  "created_at": "2026-06-01T00:00:00Z",
  "updated_at": "2026-06-01T00:00:00Z"
}
```

### 2.15 프로필 수정

**엔드포인트**: `PUT /v1/customer/my/profile`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**요청 본문**:
```json
{
  "username": "newusername"
}
```

**응답**:
```json
{
  "message": "Profile updated successfully"
}
```

### 2.16 계정 삭제

**엔드포인트**: `DELETE /v1/customer/my/account`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
```json
{
  "message": "Account deleted successfully"
}
```

### 2.17 장치 목록 조회

**엔드포인트**: `GET /v1/customer/my/devices`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
```json
{
  "devices": [
    {
      "id": 1,
      "device_token": "token123",
      "device_type": "ios",
      "device_name": "iPhone 12",
      "is_active": true,
      "last_used_at": "2026-06-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

### 2.18 장치 등록

**엔드포인트**: `POST /v1/customer/my/devices`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**요청 본문**:
```json
{
  "device_token": "token123",
  "device_type": "ios",
  "device_name": "iPhone 12"
}
```

**응답**:
```json
{
  "message": "Device registered successfully"
}
```

### 2.19 장치 폐기

**엔드포인트**: `DELETE /v1/customer/my/devices/{device_id}`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**응답**:
```json
{
  "message": "Device revoked successfully"
}
```

---

## 3. 웹서버 ↔ 엔진서버 통신

### 3.1 웹훅 등록

**엔드포인트**: `POST /v1/webhooks`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**요청 본문**:
```json
{
  "url": "https://external-server.com/webhook/analysis",
  "events": ["job.completed", "job.failed"],
  "secret_key": "optional_secret_for_signature",
  "retry_policy": {
    "max_retries": 3,
    "retry_delay": 60
  }
}
```

**응답**:
```json
{
  "webhook_id": "uuid-v4",
  "message": "Webhook created successfully"
}
```

### 3.2 웹훅 목록 조회

**엔드포인트**: `GET /v1/webhooks?active_only=true`

**응답**:
```json
{
  "webhooks": [
    {
      "webhook_id": "uuid-v4",
      "url": "https://external-server.com/webhook/analysis",
      "events": ["job.completed", "job.failed"],
      "is_active": true,
      "created_at": "2026-06-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

### 3.3 웹훅 호출 (엔진서버 → 웹서버)

**요청 헤더**:
```
Content-Type: application/json
X-Webhook-Signature: sha256={signature}
X-Webhook-ID: {webhook_id}
X-Webhook-Event: job.completed
```

**요청 본문**:
```json
{
  "event": "job.completed",
  "data": {
    "job_id": "uuid-v4",
    "customer_id": "customer-123",
    "status": "succeeded",
    "finished_at": "2026-06-01T00:05:00Z",
    "result_url": "https://engine-server.com/v1/analysis/jobs/{job_id}/result",
    "artifacts": {
      "results.json": "/v1/analysis/jobs/{job_id}/artifacts/results.json",
      "restored_image": "/v1/analysis/jobs/{job_id}/artifacts/restored.png",
      "input_image": "/v1/analysis/jobs/{job_id}/artifacts/input.png"
    }
  }
}
```

**응답**:
- 성공: HTTP 200
- 실패: HTTP 4xx/5xx (엔진서버는 재시도 정책에 따라 재시도)

### 3.4 웹훅 서명 검증

**서명 생성 (엔진서버)**:
```python
import hmac
import hashlib

signature = hmac.new(
    secret_key.encode(),
    str(payload).encode(),
    hashlib.sha256
).hexdigest()
```

**서명 검증 (웹서버)**:
```python
import hmac
import hashlib

received_signature = request.headers.get("X-Webhook-Signature")
expected_signature = hmac.new(
    secret_key.encode(),
    str(request_body).encode(),
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(received_signature, expected_signature):
    raise SecurityError("Invalid signature")
```

### 3.5 분석 작업 생성

**엔드포인트**: `POST /v1/analysis/jobs`

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
Content-Type: multipart/form-data
X-Request-ID: {uuid}
```

**요청 파라미터**:
- `file`: 이미지 파일 (multipart/form-data, 최대 10MB)
- `customer_id`: 고객 ID (선택)
- `do_restore`: 복원 수행 여부 (기본: true)
- `llm_report`: LLM 보고서 생성 여부 (기본: false)
- `use_multi_view_analysis`: 다중 뷰 분석 사용 여부 (기본: true)

**응답**:
```json
{
  "job_id": "uuid-v4",
  "status": "pending",
  "created_at": "2026-06-01T00:00:00Z"
}
```

### 3.6 작업 상태 조회

**엔드포인트**: `GET /v1/analysis/jobs/{job_id}`

**응답**:
```json
{
  "job_id": "uuid-v4",
  "status": "running",
  "progress": {
    "stage": "analysis",
    "percentage": 30,
    "message": "피부 분석 중..."
  },
  "created_at": "2026-06-01T00:00:00Z",
  "started_at": "2026-06-01T00:00:05Z"
}
```

### 3.7 작업 결과 조회

**엔드포인트**: `GET /v1/analysis/jobs/{job_id}/result`

**응답**:
```json
{
  "job_id": "uuid-v4",
  "status": "succeeded",
  "result": {
    "overall_score_original": 68.4,
    "overall_score_restored": 71.2,
    "skin_types": {
      "melasma_score": 65.0,
      "freckle_score": 60.0,
      "redness_score": 45.0
    },
    "prescription": {
      "M08": 1.3,
      "M14": 1.5,
      "M12": 0.8,
      "M13": 0.8,
      "M11": 2.3
    }
  },
  "artifacts": {
    "results.json": "/v1/analysis/jobs/{job_id}/artifacts/results.json",
    "restored_image": "/v1/analysis/jobs/{job_id}/artifacts/restored.png",
    "input_image": "/v1/analysis/jobs/{job_id}/artifacts/input.png"
  },
  "finished_at": "2026-06-01T00:05:00Z"
}
```

### 3.8 웹서버 → 엔진서버 프록시

**웹서버 로직**:
```python
async def proxy_analysis_upload(
    file: UploadFile,
    customer_id: str,
    survey_id: Optional[str] = None
):
    # 1. 웹서버 DB에 요청 기록
    request_id = db.create_analysis_request(
        customer_id=customer_id,
        survey_id=survey_id,
        status="pending"
    )
    
    # 2. 엔진서버로 요청 전송
    engine_response = await httpx.post(
        f"{ENGINE_SERVER_URL}/v1/analysis/jobs",
        files={"file": await file.read()},
        data={
            "customer_id": customer_id,
            "do_restore": True,
            "llm_report": True
        },
        headers={
            "Authorization": f"Bearer {ENGINE_JWT_TOKEN}",
            "X-Request-ID": str(uuid.uuid4())
        },
        timeout=300  # 5분 타임아웃
    )
    
    job_id = engine_response.json()["job_id"]
    
    # 3. 웹서버 DB에 job_id 저장
    db.update_analysis_request(
        request_id=request_id,
        job_id=job_id,
        status="processing"
    )
    
    return {"job_id": job_id, "request_id": request_id}
```

---

## 4. 웹서버 ↔ 스마트폰 앱 통신

### 4.1 푸시 알림 전송

**푸시 알림 페이로드 (FCM)**:
```json
{
  "to": "device_token",
  "notification": {
    "title": "피부 분석 완료",
    "body": "분석 결과가 도착했습니다. 지금 확인하세요!"
  },
  "data": {
    "job_id": "uuid-v4",
    "type": "analysis_completed"
  }
}
```

**푸시 알림 페이로드 (APNS)**:
```json
{
  "aps": {
    "alert": {
      "title": "피부 분석 완료",
      "body": "분석 결과가 도착했습니다. 지금 확인하세요!"
    }
  },
  "job_id": "uuid-v4",
  "type": "analysis_completed"
}
```

---

## 5. OAuth 통신

### 5.1 OAuth 제공자 등록

**엔드포인트**: `POST /v1/oauth/providers`

**요청 본문**:
```json
{
  "provider_name": "google",
  "client_id": "client-id",
  "client_secret": "client-secret",
  "redirect_uri": "https://external-server.com/oauth/callback",
  "scopes": ["openid", "profile", "email"]
}
```

**응답**:
```json
{
  "provider_id": "uuid-v4",
  "message": "OAuth provider created successfully"
}
```

### 5.2 OAuth 인증 URL 생성

**엔드포인트**: `POST /v1/oauth/authorize`

**요청 본문**:
```json
{
  "provider_name": "google",
  "customer_id": "customer-123"
}
```

**응답**:
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&state=...",
  "state": "uuid-v4"
}
```

### 5.3 OAuth 토큰 교환

**엔드포인트**: `POST /v1/oauth/token`

**요청 본문**:
```json
{
  "provider_name": "google",
  "customer_id": "customer-123",
  "code": "authorization_code"
}
```

**응답**:
```json
{
  "access_token": "access_token_value",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

---

## 6. 데이터 동기화

### 6.1 고객 데이터 동기화

**엔드포인트**: `POST /v1/integration/customers/sync`

**요청 본문**:
```json
{
  "source_system": "external_web_server",
  "target_system": "skin_lens",
  "direction": "in"
}
```

**응답**:
```json
{
  "sync_log_id": "uuid-v4",
  "records_count": 1000,
  "status": "completed"
}
```

### 6.2 제품 데이터 동기화

**엔드포인트**: `POST /v1/integration/products/sync`

**요청 본문**:
```json
{
  "source_system": "external_web_server",
  "target_system": "skin_lens",
  "direction": "in"
}
```

**응답**:
```json
{
  "sync_log_id": "uuid-v4",
  "records_count": 50,
  "status": "completed"
}
```

### 6.3 동기화 로그 조회

**엔드포인트**: `GET /v1/integration/sync-logs?sync_type=customers&status=completed&limit=100`

**응답**:
```json
{
  "logs": [
    {
      "log_id": "uuid-v4",
      "sync_type": "customers",
      "direction": "in",
      "source_system": "external_web_server",
      "target_system": "skin_lens",
      "status": "completed",
      "records_count": 1000,
      "started_at": "2026-06-01T00:00:00Z",
      "finished_at": "2026-06-01T00:01:00Z"
    }
  ],
  "total": 1
}
```

---

## 7. WebSocket 통신

### 7.1 연결

**엔드포인트**: `wss://engine-server.com/v1/ws/jobs/{job_id}`

**연결 파라미터**:
- `job_id`: 작업 ID
- `token`: JWT 토큰 (쿼리 파라미터)

### 7.2 진행률 메시지

**클라이언트 → 서버**:
```json
{
  "type": "subscribe",
  "job_id": "uuid-v4"
}
```

**서버 → 클라이언트**:
```json
{
  "type": "progress",
  "job_id": "uuid-v4",
  "stage": "analysis",
  "percentage": 30,
  "message": "피부 분석 중..."
}
```

### 7.3 연결 관리

**재연결 전략**:
- 초기 지연: 1초
- 최대 지연: 30초
- 최대 재시도: 5회
- 지연 증가: 지수 백오프 (exponential backoff)

**하트비트**:
- 간격: 30초
- 타임아웃: 60초

---

## 8. 인증 및 보안

### 8.1 JWT 인증

모든 API 요청은 JWT 토큰을 사용하여 인증됩니다.

**요청 헤더**:
```
Authorization: Bearer {jwt_token}
```

**토큰 페이로드**:
```json
{
  "sub": "customer-123",
  "role": "customer",
  "exp": 1234567890,
  "iat": 1234567890
}
```

### 8.2 권한 수준

| 역할 | 권한 |
|------|------|
| customer | 자신의 데이터 조회, 분석 요청 |
| admin | 모든 데이터 조회, 웹훅 관리, OAuth 제공자 관리, 데이터 동기화 |

### 8.3 속도 제한

| 엔드포인트 그룹 | 제한 | 기간 |
|----------------|------|------|
| 인증 (/auth/*) | 10 요청 | 1분 |
| 분석 (/analysis/*) | 100 요청 | 1분 |
| 웹훅 (/webhooks/*) | 50 요청 | 1분 |
| 관리자 (/admin/*) | 30 요청 | 1분 |
| 웹훅 호출 | 제한 없음 | - |

### 8.4 보안 요구사항

**TLS/HTTPS**:
- 최소 TLS 버전: 1.3
- 허용되는 암호화 스위트: TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256
- HSTS: max-age=31536000; includeSubDomains

**데이터 암호화**:
- 비밀번호: bcrypt (cost factor 12)
- API 키: AES-256-GCM
- 데이터베이스: SQLite 암호화

**CSRF 방어**:
- SameSite 쿠키: Strict
- CSRF 토큰: 상태 변경 요청에 필수

**XSS 방어**:
- Content-Security-Policy 헤더
- 입력 검증 및 출력 이스케이프

---

## 9. 에러 처리 및 재시도 정책

### 9.1 HTTP 상태 코드

| 상태 코드 | 설명 | 재시도 여부 |
|----------|------|-----------|
| 200 | 성공 | - |
| 400 | 잘못된 요청 | 아니오 |
| 401 | 인증 실패 | 아니오 (토큰 갱신 필요) |
| 403 | 권한 부족 | 아니오 |
| 404 | 리소스 없음 | 아니오 |
| 409 | 충돌 (이미 존재) | 아니오 |
| 429 | 속도 제한 초과 | 예 (지수 백오프) |
| 500 | 서버 오류 | 예 (최대 3회) |
| 502 | 게이트웨이 오류 | 예 (최대 5회) |
| 503 | 서비스 불가 | 예 (최대 5회) |
| 504 | 게이트웨이 타임아웃 | 예 (최대 3회) |

### 9.2 재시도 정책

**일반 API 재시도**:
- 초기 지연: 1초
- 최대 지연: 30초
- 최대 재시도: 3회
- 지연 증가: 지수 백오프

**웹훅 재시도**:
- 초기 지연: 60초
- 최대 지연: 3600초 (1시간)
- 최대 재시도: 10회
- 지연 증가: 지수 백오프

### 9.3 에러 응답 형식

```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE",
  "timestamp": "2026-06-01T00:00:00Z",
  "request_id": "uuid-v4"
}
```

---

## 10. 모니터링 및 로깅

### 10.1 로깅 레벨

| 레벨 | 용도 |
|------|------|
| DEBUG | 디버깅 정보 (개발 환경만) |
| INFO | 일반 작업 정보 |
| WARNING | 경고 (비정상이지만 치명적이지 않음) |
| ERROR | 오류 (작업 실패) |
| CRITICAL | 치명적 오류 (서비스 중단) |

### 10.2 로그 보관 정책

- INFO: 30일
- WARNING: 90일
- ERROR: 180일
- CRITICAL: 365일

### 10.3 모니터링 메트릭

**API 메트릭**:
- 요청 수 (총/성공/실패)
- 응답 시간 (p50, p95, p99)
- 오류율
- 속도 제한 위반 수

**시스템 메트릭**:
- CPU 사용률
- 메모리 사용량
- 디스크 I/O
- 네트워크 트래픽

**비즈니스 메트릭**:
- 분석 작업 수
- 평균 처리 시간
- 웹훅 성공률
- 푸시 전송 성공률

### 10.4 알림 규칙

| 조건 | 심각도 | 알림 채널 |
|------|--------|----------|
| 오류율 > 5% | WARNING | Slack |
| 오류율 > 10% | CRITICAL | Slack + 이메일 |
| 응답 시간 p95 > 5초 | WARNING | Slack |
| 응답 시간 p95 > 10초 | CRITICAL | Slack + 이메일 |
| 서비스 다운 | CRITICAL | Slack + 이메일 + SMS |

---

## 11. API 버전 관리

### 11.1 버전 관리 전략

**URL 기반 버전 관리**:
- 현재 버전: `/v1/`
- 새 버전: `/v2/`
- 하위 호환성 유지 기간: 6개월

**버전 폐기 절차**:
1. 새 버전 출시 (3개월 전 공지)
2. 이전 버전 사용자에게 마이그레이션 가이드 제공
3. 3개월 후 이전 버전 사용 중단 경고
4. 6개월 후 이전 버전 폐기

### 11.2 버전 호환성

**하위 호환성 변경**:
- 새로운 선택적 필드 추가
- 새로운 엔드포인트 추가
- 응답에 새로운 필드 추가

**하위 호환성 파괴 변경**:
- 필수 필드 제거
- 필드 타입 변경
- 엔드포인트 삭제

---

## 12. 테스트 및 검증

### 12.1 단위 테스트

**테스트 범위**:
- API 엔드포인트
- 비즈니스 로직
- 데이터베이스 연산
- 웹훅 처리

**테스트 프레임워크**:
- Python: pytest
- JavaScript: Jest

### 12.2 통합 테스트

**테스트 시나리오**:
1. 로그인 → 설문 제출 → 이미지 전송 → 분석 완료 → 결과 조회
2. 웹훅 등록 → 분석 완료 → 웹훅 호출
3. OAuth 인증 → 토큰 교환 → API 호출

### 12.3 부하 테스트

**테스트 도구**:
- JMeter
- k6
- Locust

**테스트 시나리오**:
- 동시 사용자: 100, 500, 1000
- 요청 속도: 10, 50, 100 req/s
- 지속 시간: 10분, 30분, 1시간

### 12.4 보안 테스트

**테스트 항목**:
- SQL 인젝션
- XSS
- CSRF
- 인증 우회
- 권한 상승
- API 키 유출

---

## 13. 서비스 수준 계약 (SLA)

### 13.1 성능 목표

| 메트릭 | 목표 | 측정 방법 |
|--------|------|-----------|
| API 응답 시간 (p95) | < 2초 | 모든 API 엔드포인트 |
| 분석 작업 완료 시간 | < 5분 | 이미지 분석 작업 |
| 웹훅 응답 시간 | < 1초 | 웹훅 호출 |
| 시스템 가용성 | 99.5% | 월간 가용성 |
| 데이터 일관성 | 99.9% | 데이터 동기화 |

### 13.2 용량 계획

| 동시 사용자 | 요청/초 | CPU | 메모리 | 스토리지 |
|------------|---------|-----|--------|---------|
| 100 | 10 | 2 vCPU | 4GB | 50GB |
| 500 | 50 | 4 vCPU | 8GB | 100GB |
| 1000 | 100 | 8 vCPU | 16GB | 200GB |

### 13.3 장애 대응 시간

| 장애 유형 | 심각도 | 응답 시간 | 해결 시간 |
|----------|--------|-----------|-----------|
| 서비스 다운 | P1 | 15분 | 1시간 |
| 성능 저하 | P2 | 30분 | 4시간 |
| 기능 장애 | P3 | 1시간 | 8시간 |
| 마이너 문제 | P4 | 4시간 | 24시간 |

### 13.4 보고서

SLA 준수 여부는 매월 보고서로 제공됩니다:
- 가용성 보고서
- 성능 보고서
- 장애 발생 보고서
- 개선 계획

---

## 14. 배포 및 운영

### 14.1 배포 전략

**환경**:
- 개발 (dev)
- 스테이징 (staging)
- 프로덕션 (prod)

**배포 방식**:
- 블루/그린 배포
- 롤링 업데이트
- 카나리 배포

### 14.2 환경 변수

**필수 환경 변수**:
```bash
# 데이터베이스
DATABASE_URL=postgresql://user:pass@localhost/db
DB_ENCRYPTION_KEY=your-encryption-key

# 인증
JWT_SECRET_KEY=your-jwt-secret
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret

# 외부 서비스
LLM_API_KEY=your-llm-api-key
FCM_API_KEY=your-fcm-api-key
APNS_KEY_ID=your-apns-key-id
APNS_TEAM_ID=your-apns-team-id

# 엔진서버
ENGINE_SERVER_URL=https://engine-server.com
ENGINE_JWT_TOKEN=your-engine-jwt-token

# 모니터링
SENTRY_DSN=your-sentry-dsn
PROMETHEUS_ENABLED=true
```

### 14.3 롤백 전략

**롤백 조건**:
- 오류율 > 10%
- 응답 시간 p95 > 10초
- 치명적 버그 발견

**롤백 절차**:
1. 이전 버전으로 즉시 롤백
2. 롤백 알림 전송
3. 문제 원인 분석
4. 수정 후 재배포

---

## 15. 성능 최적화

### 15.1 캐싱 전략

**API 응답 캐싱**:
- 분석 결과: 1시간
- 제품 목록: 30분
- 고객 정보: 5분

**CDN 활용**:
- 정적 리소스: 이미지, CSS, JS
- API 응답: 읽기 전용 데이터

### 15.2 대용량 파일 전송

**최적화 방법**:
- 분할 업로드 (chunked upload)
- 압축 전송 (gzip, brotli)
- 진행률 표시
- 일시 중지/재개 지원

### 15.3 데이터베이스 최적화

**인덱싱**:
- 자주 조회하는 필드에 인덱스 추가
- 복합 인덱스 활용

**쿼리 최적화**:
- N+1 쿼리 방지
- 페이지네이션 활용
- 필요한 필드만 선택

---

## 16. 데이터 백업 및 복구

### 16.1 백업 전략

**백업 주기**:
- 전체 백업: 매일 (새벽 2시)
- 증분 백업: 매시간
- 로그 백업: 매일

**백업 보관**:
- 전체 백업: 30일
- 증분 백업: 7일
- 로그 백업: 90일

### 16.2 복구 절차

**복구 시나리오**:
1. 데이터베이스 손상
2. 파일 시스템 손상
3. 서버 전체 손상

**복구 시간 목표 (RTO)**:
- 데이터베이스: 1시간
- 파일 시스템: 2시간
- 서버 전체: 4시간

**데이터 손실 목표 (RPO)**:
- 데이터베이스: 1시간
- 파일 시스템: 1시간

### 16.3 재해 복구 계획

**재해 시나리오**:
- 데이터센터 장애
- 자연재해
- 사이버 공격

**복구 사이트**:
- 웜 스탠바이 (warm standby)
- 데이터 동기화: 실시간
- 장애 조치(Failover) 시간: 30분

---

## 17. 시퀀스 다이어그램

### 17.1 전체 사용자 플로우

```mermaid
sequenceDiagram
    participant App as 스마트폰 앱
    participant Web as 웹서버
    participant Engine as 엔진서버
    participant DB as 데이터베이스
    participant LLM as LLM API
    participant Push as 푸시 서비스
    
    Note over App,Web: 1. 로그인
    App->>Web: POST /auth/login (ID, PW)
    Web-->>App: JWT 토큰
    
    Note over App,Web: 2. 설문 조사
    App->>Web: POST /survey (설문 데이터)
    Web->>DB: 설문 저장
    Web-->>App: 설문 저장 완료
    
    Note over App,Web: 3. 이미지 전송
    App->>Web: POST /analysis/upload (이미지, JWT)
    Web->>Engine: POST /v1/analysis/jobs (이미지, JWT)
    Engine->>DB: 작업 생성
    Engine-->>Web: job_id
    Web-->>App: job_id
    
    Note over Engine: 4. 분석 처리
    Engine->>Engine: 이미지 복원
    Engine->>Engine: 피부 분석
    Engine->>LLM: 보고서 생성 요청
    LLM-->>Engine: 보고서 응답
    Engine->>DB: 결과 저장
    
    Note over Engine,Web: 5. 웹훅 알림
    Engine->>Web: POST webhook (job.completed)
    Web->>DB: 결과 업데이트
    
    Note over Web,Push: 6. 푸시 알림
    Web->>Push: 푸시 전송 요청
    Push->>App: 분석 완료 알림
    
    Note over App,Web: 7. 결과 조회
    App->>Web: GET /analysis/result/{job_id}
    Web-->>App: 분석 결과
```

### 17.2 웹훅 등록 및 호출 흐름

```mermaid
sequenceDiagram
    participant Web as 웹서버
    participant Engine as 엔진서버
    
    Web->>Engine: POST /v1/webhooks (URL, events)
    Engine-->>Web: webhook_id
    
    Note over Engine: 분석 완료
    
    Engine->>Web: POST webhook_url (event, data)
    Web-->>Engine: HTTP 200
```

---

## 18. 구현 참고

### 18.1 웹훅 트리거 함수

```python
async def trigger_webhook(
    webhook_url: str,
    event_type: str,
    payload: Dict[str, Any],
    secret_key: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: int = 60
) -> bool:
    """웹훅 호출 (재시도 포함)"""
    for attempt in range(max_retries):
        try:
            headers = {"Content-Type": "application/json"}
            if secret_key:
                import hmac
                import hashlib
                signature = hmac.new(
                    secret_key.encode(),
                    str(payload).encode(),
                    hashlib.sha256
                ).hexdigest()
                headers["X-Webhook-Signature"] = signature
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    webhook_url,
                    json={"event": event_type, "data": payload},
                    headers=headers,
                )
                if response.status_code == 200:
                    return True
                elif response.status_code >= 500:
                    # 서버 오류: 재시도
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                else:
                    # 클라이언트 오류: 재시도 안 함
                    return False
        except (httpx.HTTPError, ValueError) as e:
            log.error("웹훅 호출 실패 (시도 %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2 ** attempt))
    
    return False
```

### 18.2 웹훅 등록 예시

```python
import httpx

async def register_webhook(webhook_url: str, jwt_token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://engine-server.com/v1/webhooks",
            json={
                "url": webhook_url,
                "events": ["job.completed", "job.failed"],
                "secret_key": "my_secret_key",
                "retry_policy": {
                    "max_retries": 3,
                    "retry_delay": 60
                }
            },
            headers={"Authorization": f"Bearer {jwt_token}"}
        )
        return response.json()
```

### 18.3 WebSocket 클라이언트 예시

```python
import asyncio
import websockets
import json

async def connect_to_websocket(job_id: str, token: str):
    uri = f"wss://engine-server.com/v1/ws/jobs/{job_id}?token={token}"
    
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                # 구독 요청
                await websocket.send(json.dumps({
                    "type": "subscribe",
                    "job_id": job_id
                }))
                
                # 메시지 수신
                async for message in websocket:
                    data = json.loads(message)
                    if data["type"] == "progress":
                        print(f"진행률: {data['percentage']}% - {data['message']}")
                    elif data["type"] == "completed":
                        print("분석 완료!")
                        break
        except Exception as e:
            print(f"연결 오류: {e}, 재연결 중...")
            await asyncio.sleep(5)  # 5초 후 재연결
```

---

## 19. 부록

### 19.1 관련 파일

- `src/server/routers/integration.py`: 웹훅, OAuth, 동기화 API 구현
- `src/server/routers/jobs.py`: 분석 작업 API 구현
- `src/server/routers/websocket.py`: WebSocket 서비스 구현
- `src/db/skin_analysis_db.py`: 웹훅, OAuth 데이터베이스 관리
- `src/server/monitoring.py`: 모니터링 및 로깅 구현

### 19.2 관련 문서

- `docs/guides/ARCHITECTURE.md`: 전체 아키텍처
- `docs/api/API_REFERENCE.md`: API 상세 명세
- `docs/guides/DEPLOYMENT_GUIDE.md`: 배포 가이드
- `docs/guides/MONITORING_GUIDE.md`: 모니터링 가이드

### 19.3 용어 사전

| 용어 | 설명 |
|------|------|
| JWT | JSON Web Token, 인증 토큰 |
| OAuth | Open Authorization, 인증 표준 |
| FCM | Firebase Cloud Messaging, 푸시 서비스 |
| APNS | Apple Push Notification Service, 푸시 서비스 |
| WebSocket | 양방향 통신 프로토콜 |
| HMAC | Hash-based Message Authentication Code, 메시지 인증 코드 |
| TLS | Transport Layer Security, 전송 계층 보안 |
| CSRF | Cross-Site Request Forgery, 사이트 간 요청 위조 |
| XSS | Cross-Site Scripting, 사이트 간 스크립팅 |
| RTO | Recovery Time Objective, 복구 시간 목표 |
| RPO | Recovery Point Objective, 데이터 손실 목표 |
