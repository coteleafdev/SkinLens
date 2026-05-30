# API 레퍼런스 (API Reference)

> **프로젝트:** SkinLens v1.0  
> **버전:** v1.0  
> **작성일:** 2026-05-30  
> **상태:** 초안

---

## 개요

SkinLens REST API 엔드포인트 상세 설명입니다.

**참고 문서:**
- 백엔드 개발자용 상세 가이드: `API_GUIDE.md`
- 데이터 모델: `docs/db/DATA_MODEL.md`
- 보안 가이드: `docs/ops/SECURITY_GUIDE.md`

---

## 기본 정보

**Base URL:**
- 개발: `http://localhost:8000`
- 프로덕션: `https://api.skinlens.com`

**인증:**
- JWT Bearer Token
- Header: `Authorization: Bearer <token>`

**Content-Type:**
- `application/json`
- `multipart/form-data` (이미지 업로드)

**Swagger UI:**
- 개발: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

---

## 1. 인증 (Authentication)

### 1.1 로그인

**POST** `/v1/auth/login`

로그인 및 JWT 토큰 발급

**Request Body:**
```json
{
  "customer_id": "string",
  "password": "string"
}
```

**Response (200 OK):**
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "customer_id": "string",
  "role": "admin|analyst|customer",
  "expires_in": 3600
}
```

---

### 1.2 내 정보 조회

**GET** `/v1/auth/me`

현재 인증된 사용자 정보 조회

**Response (200 OK):**
```json
{
  "customer_id": "string",
  "role": "admin|analyst|customer"
}
```

---

## 2. 분석 Job (Analysis Jobs)

### 2.1 Job 생성

**POST** `/v1/analysis/jobs`

분석 Job을 생성합니다.

**Request Headers:**
```
Authorization: Bearer <jwt_token>
Content-Type: multipart/form-data
```

**Request Body (Form Data):**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| images[] | File | 아니오* | 다중 이미지 (1~3장) |
| angles[] | string | 아니오* | 이미지 각도 (front/left45/right45) |
| image | File | 아니오* | 단일 이미지 (레거시) |
| image_url | string | 아니오* | 이미지 URL (레거시) |
| do_restore | boolean | 아니오 | 복원 수행 여부 (기본: true) |
| include_base64 | boolean | 아니오 | base64 포함 여부 (기본: false) |
| score_safety_net | boolean | 아니오 | 점수 안전장치 (기본: true) |
| llm_report | boolean | 아니오 | LLM 소견 생성 (기본: true) |
| use_multi_view_analysis | boolean | 아니오 | 다중 뷰 분석 (기본: true) |
| customer_id | string | 아니오 | 고객 ID |
| gender | string | 아니오 | 성별 |
| age | integer | 아니오 | 연령 |
| race | string | 아니오 | 인종 |
| region | string | 아니오 | 지역 |
| survey | string | 아니오 | 설문 JSON |
| client_meta | string | 아니오 | 클라이언트 메타 JSON |

*images[], image, image_url 중 하나는 필수

**Response (201 Created):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-05-30T10:00:00Z"
}
```

---

### 2.2 Job 상태 조회

**GET** `/v1/analysis/jobs/{job_id}`

Job 상태를 조회합니다.

**Response (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100,
  "message": "완료",
  "created_at": "2026-05-30T10:00:00Z",
  "started_at": "2026-05-30T10:00:05Z",
  "finished_at": "2026-05-30T10:01:30Z",
  "result": {
    "input_image_url": "/analysis/jobs/{job_id}/artifacts/input.jpg",
    "restored_image_url": "/analysis/jobs/{job_id}/artifacts/restored.png",
    "customer_info": {
      "customer_id": "CUST001",
      "gender": "female",
      "age": 30,
      "race": "asian",
      "region": "KR"
    },
    "analysis_result": {
      "overall_score": 75,
      "measurements": {
        "pigmentation": 65,
        "redness": 70,
        "pores": 80
      }
    }
  }
}
```

---

### 2.3 Job 취소

**DELETE** `/v1/analysis/jobs/{job_id}`

Job을 취소합니다.

**Response (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled"
}
```

---

### 2.4 피부 타입 확인

**POST** `/v1/analysis/jobs/{job_id}/confirm-skin-type`

피부 타입 사용자 확인

**Request Body:**
```json
{
  "skin_types": ["dry", "oily", "combination", "sensitive"]
}
```

**Response (200 OK):**
```json
{
  "job_id": "uuid",
  "skin_types": ["dry", "oily"],
  "skin_type_source": "manual"
}
```

---

### 2.5 이미지 다운로드

**GET** `/v1/analysis/jobs/{job_id}/artifacts/{filename}`

분석 결과 이미지를 다운로드합니다.

**파일명:**
- `original.png`: 원본 이미지
- `restored.png`: 복원 이미지
- `comparison.png`: 비교 이미지
- `results.json`: 분석 결과 JSON

**Response (200 OK):**
- Content-Type: `image/jpeg` 또는 `image/png`
- Binary image data

---

## 3. 고객 (Customer)

### 3.1 내 정보 조회

**GET** `/v1/customer/my/info`

내 고객 정보를 조회합니다.

**Response (200 OK):**
```json
{
  "customer_id": "CUST001",
  "email": "customer@example.com",
  "name": "홍길동",
  "gender": "female",
  "age": 30,
  "race": "asian",
  "region": "KR",
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### 3.2 분석 이력 조회

**GET** `/v1/customer/my/analyses`

내 분석 이력을 조회합니다.

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| limit | integer | 아니오 | 최대 개수 (기본: 20) |
| offset | integer | 아니오 | 오프셋 (기본: 0) |

**Response (200 OK):**
```json
{
  "analyses": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "created_at": "2026-05-30T10:00:00Z",
      "overall_score": 75,
      "input_image_url": "/analysis/jobs/{job_id}/artifacts/input.jpg"
    }
  ],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

---

## 4. 통계 (Stats)

### 4.1 분석 통계 조회

**GET** `/v1/stats/analysis`

분석 통계를 조회합니다.

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| days | integer | 아니오 | 기간 (일, 기본: 7) |
| customer_id | string | 아니오 | 고객 ID (관리자만) |

**Response (200 OK):**
```json
{
  "stats": [
    {
      "date": "2026-05-30",
      "total_analyses": 100,
      "successful": 95,
      "failed": 5,
      "avg_score": 75.5
    }
  ],
  "count": 7
}
```

---

## 5. 헬스체크 (Health)

### 5.1 서버 상태 확인

**GET** `/health`

서버 상태를 확인합니다.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "v3.6",
  "timestamp": "2026-05-30T10:00:00Z"
}
```

---

## 6. 관리자 (Admin)

### 6.1 감사 로그 조회

**GET** `/v1/admin/audit-logs`

감사 로그를 조회합니다 (관리자/분석가 전용).

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| actor_customer_id | string | 아니오 | 행동자 고객 ID |
| target_customer_id | string | 아니오 | 대상 고객 ID |
| days | integer | 아니오 | 기간 (일, 기본: 30) |
| limit | integer | 아니오 | 최대 개수 (기본: 100) |

**Response (200 OK):**
```json
{
  "logs": [
    {
      "id": "uuid",
      "actor_customer_id": "ADMIN001",
      "target_customer_id": "CUST001",
      "endpoint": "/v1/analysis/jobs",
      "method": "POST",
      "user_role": "admin",
      "success": true,
      "created_at": "2026-05-30T10:00:00Z"
    }
  ],
  "count": 100
}
```

---

### 6.2 DB 헬스체크

**GET** `/v1/admin/health/db`

데이터베이스 상태를 확인합니다 (관리자/분석가 전용).

**Response (200 OK):**
```json
{
  "status": "healthy",
  "connection": "ok",
  "latency_ms": 5.2,
  "table_count": 10
}
```

---

### 6.3 로그 레벨 조회

**GET** `/v1/admin/logging/level`

현재 로그 레벨을 조회합니다 (관리자/분석가 전용).

**Response (200 OK):**
```json
{
  "level": "DEBUG",
  "persisted": false
}
```

---

### 6.4 로그 레벨 변경

**PUT** `/v1/admin/logging/level`

로그 레벨을 변경합니다 (관리자/분석가 전용).

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| level | string | 예 | 로그 레벨 (DEBUG, INFO, WARNING, ERROR) |
| persist | boolean | 아니오 | config.json 저장 여부 (기본: false) |

**Response (200 OK):**
```json
{
  "level": "INFO",
  "previous_level": "DEBUG",
  "persisted": true
}
```

---

### 6.5 시스템 메트릭 조회

**GET** `/v1/admin/metrics/system`

시스템 메트릭을 조회합니다 (관리자/분석가 전용).

**Response (200 OK):**
```json
{
  "cpu": {
    "percent": 45.2,
    "count": 8
  },
  "memory": {
    "total_gb": 16.0,
    "available_gb": 8.5,
    "used_gb": 7.5,
    "percent": 46.9
  },
  "disk": {
    "total_gb": 500.0,
    "used_gb": 200.0,
    "free_gb": 300.0,
    "percent": 40.0
  },
  "network": {
    "bytes_sent": 1024000,
    "bytes_recv": 2048000,
    "packets_sent": 1000,
    "packets_recv": 2000
  },
  "process": {
    "pid": 12345,
    "memory_percent": 2.5,
    "cpu_percent": 1.2,
    "num_threads": 8
  },
  "timestamp": "2026-05-30T10:00:00Z"
}
```

---

### 6.6 API 키 생성

**POST** `/v1/admin/api-keys`

API 키를 생성합니다 (관리자/분석가 전용).

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| name | string | 예 | API 키 이름 |
| owner_id | string | 예 | 소유자 ID |
| description | string | 아니오 | 설명 |
| scopes | string | 아니오 | 권한 범위 (JSON 문자열) |
| expires_in_days | integer | 아니오 | 만료일수 |

**Response (200 OK):**
```json
{
  "id": "uuid",
  "api_key": "64-char-hex-string",
  "name": "Test Key",
  "description": "Test API key",
  "owner_id": "CUST001",
  "scopes": ["read", "write"],
  "expires_at": "2026-06-30T10:00:00Z",
  "created_at": "2026-05-30T10:00:00Z"
}
```

---

### 6.7 API 키 목록 조회

**GET** `/v1/admin/api-keys`

API 키 목록을 조회합니다 (관리자/분석가 전용).

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| owner_id | string | 아니오 | 소유자 ID 필터 |
| is_active | boolean | 아니오 | 활성 상태 필터 |
| limit | integer | 아니오 | 최대 개수 (기본: 100) |

**Response (200 OK):**
```json
{
  "api_keys": [
    {
      "id": "uuid",
      "name": "Test Key",
      "owner_id": "CUST001",
      "scopes": ["read", "write"],
      "is_active": true,
      "expires_at": "2026-06-30T10:00:00Z",
      "last_used_at": "2026-05-30T10:00:00Z",
      "created_at": "2026-05-30T10:00:00Z"
    }
  ],
  "count": 10
}
```

---

### 6.8 API 키 폐지

**DELETE** `/v1/admin/api-keys/{key_id}`

API 키를 폐지합니다 (관리자/분석가 전용).

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| reason | string | 아니오 | 폐지 사유 |

**Response (200 OK):**
```json
{
  "message": "API key revoked successfully",
  "key_id": "uuid"
}
```

---

### 6.9 캐시 통계 조회

**GET** `/v1/admin/cache/stats`

캐시 통계를 조회합니다 (관리자/분석가 전용).

**Response (200 OK):**
```json
{
  "metrics_cache": {
    "valid": true,
    "age_seconds": 15.5,
    "ttl": 30,
    "cached": true
  },
  "timestamp": "2026-05-30T10:00:00Z"
}
```

---

### 6.10 캐시 초기화

**POST** `/v1/admin/cache/clear`

캐시를 초기화합니다 (관리자/분석가 전용).

**Query Parameters:**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| cache_type | string | 아니오 | 초기화할 캐시 (all, metrics, config) |

**Response (200 OK):**
```json
{
  "message": "Cache cleared successfully",
  "cleared_caches": ["metrics", "config"],
  "timestamp": "2026-05-30T10:00:00Z"
}
```

---

### 6.11 WebSocket 연결 통계

**GET** `/v1/admin/websocket/stats`

WebSocket 연결 통계를 조회합니다 (관리자/분석가 전용).

**Response (200 OK):**
```json
{
  "active_connections": 5,
  "max_connections": 100,
  "connection_timeout": 300,
  "connections": [
    {
      "job_id": "uuid",
      "connected_at": 1234567890.0,
      "last_heartbeat": 1234567900.0,
      "client_ip": "192.168.1.1"
    }
  ]
}
```

---

### 6.12 작업 큐 통계

**GET** `/v1/admin/job-queue/stats`

작업 큐 통계를 조회합니다 (관리자/분석가 전용).

**Response (200 OK):**
```json
{
  "queue_size": 10,
  "running_jobs": 4,
  "max_workers": 4,
  "job_history_size": 100,
  "running": true
}
```

---

### 6.13 작업 상태 조회

**GET** `/v1/admin/job-queue/{job_id}`

작업 상태를 조회합니다 (관리자/분석가 전용).

**Response (200 OK):**
```json
{
  "job_id": "uuid",
  "status": "running",
  "priority": 2,
  "retry_count": 0,
  "max_retries": 3,
  "error": null,
  "created_at": "2026-05-30T10:00:00Z"
}
```

---

## 7. WebSocket

### 7.1 진행률 트래킹

**WS** `/v1/ws/analyze/{job_id}`

분석 진행률을 실시간으로 수신합니다.

**메시지 형식:**
```json
{
  "type": "progress",
  "stage": "restore",
  "percent": 30,
  "message": "복원 중..."
}
```

**완료 메시지:**
```json
{
  "type": "complete",
  "result": {
    "overall_score": 75,
    "measurements": {...}
  }
}
```

**에러 메시지:**
```json
{
  "type": "error",
  "error": "에러 메시지"
}
```

---

## 에러 코드

| 코드 | 설명 |
|------|------|
| 200 | OK - 성공 |
| 201 | Created - 리소스 생성 |
| 400 | Bad Request - 잘못된 요청 |
| 401 | Unauthorized - 인증 실패 |
| 403 | Forbidden - 권한 없음 |
| 404 | Not Found - 리소스 없음 |
| 429 | Too Many Requests - 요청 초과 |
| 500 | Internal Server Error - 서버 에러 |

**에러 응답 형식:**
```json
{
  "detail": "에러 메시지"
}
```

---

## 속도 제한 (Rate Limiting)

**역할별 속도 제한:**
| 역할 | 제한 |
|------|------|
| customer | 30/분 |
| admin | 100/분 |
| analyst | 60/분 |
| default (인증 없음) | 30/분 |

**엔드포인트별 제한:**
| 엔드포인트 | 제한 |
|-----------|------|
| POST /v1/auth/login | 5/분 |
| POST /v1/analysis/jobs | 30/분 |
| GET /v1/analysis/jobs/{job_id} | 60/분 |
| GET /v1/customer/my/* | 60/분 |
| GET /v1/stats/* | 30/분 |
| 기타 엔드포인트 | 역할별 제한 적용 |

**속도 제한 초과 시:**
- HTTP 429 Too Many Requests
- Retry-After 헤더 포함

---

## 요청 로깅 (Request Logging)

모든 API 요청은 자동으로 로깅됩니다.

**로그 정보:**
- 요청 ID (UUID)
- HTTP 메서드
- 경로
- 쿼리 파라미터
- 클라이언트 IP
- User-Agent
- 응답 상태 코드
- 처리 시간

**요청 ID:**
- 응답 헤더 `X-Request-ID`로 제공
- 요청 추적 및 디버깅에 사용

**느린 요청 경고:**
- 기준: 5초 이상 (config.json에서 설정 가능)
- 로그 레벨: WARNING

---

## 청크 업로드 (Chunk Upload)

대용량 파일을 청크 단위로 업로드하여 네트워크 중단 시 재개 가능.

### 엔드포인트

#### POST /v1/upload/init
업로드 세션 초기화.

**요청 파라미터:**
- `file_name` (string): 파일 이름
- `file_size` (integer): 파일 크기 (bytes)
- `chunk_size` (integer, optional): 청크 크기 (bytes, 기본 5MB)
- `file_hash` (string, optional): 파일 SHA-256 해시

**응답:**
```json
{
  "session_id": "uuid",
  "chunk_size": 5242880,
  "total_chunks": 10,
  "file_name": "image.jpg",
  "file_size": 52428800
}
```

#### POST /v1/upload/chunk
청크 업로드.

**요청 파라미터:**
- `session_id` (string): 업로드 세션 ID
- `chunk_number` (integer): 청크 번호 (0-based)
- `chunk` (file): 청크 데이터

**응답:**
```json
{
  "status": "uploaded",
  "chunk_number": 0,
  "uploaded_chunks": 1,
  "total_chunks": 10
}
```

#### POST /v1/upload/complete
업로드 완료 및 파일 합치기.

**요청 파라미터:**
- `session_id` (string): 업로드 세션 ID

**응답:**
```json
{
  "status": "completed",
  "file_name": "image.jpg",
  "file_size": 52428800,
  "file_path": "/path/to/image.jpg"
}
```

#### POST /v1/upload/cancel
업로드 취소.

**요청 파라미터:**
- `session_id` (string): 업로드 세션 ID

**응답:**
```json
{
  "status": "cancelled",
  "session_id": "uuid"
}
```

#### GET /v1/upload/progress/{session_id}
업로드 진행률 조회.

**응답:**
```json
{
  "session_id": "uuid",
  "file_name": "image.jpg",
  "file_size": 52428800,
  "uploaded_chunks": 5,
  "total_chunks": 10,
  "progress_percent": 50.0,
  "created_at": "2026-05-30T10:00:00Z"
}
```

---

## API 버전 관리 (API Versioning)

버전별 라우팅 및 폐기 정책 지원.

### 응답 헤더

- `API-Version`: 현재 요청의 API 버전
- `API-Current-Version`: 현재 최신 API 버전 (현재 버전과 다를 때)
- `Deprecation`: 폐기된 버전 사용 시 `true`
- `Sunset`: 폐기 예정 일자
- `Warning`: 버전 경고 메시지

### 버전 정책

- **현재 버전**: v1
- **폐기된 버전**: 없음
- **폐기 예정**: 없음

### 사용 예시

```bash
# 현재 버전 사용
curl https://api.example.com/v1/analysis/jobs

# 폐기된 버전 사용 (경고 헤더 포함)
curl https://api.example.com/v1/analysis/jobs
```

---

## IP 필터링 (IP Filtering)

IP 화이트리스트/블랙리스트 기능.

### 설정 (config.json)

```json
{
  "server": {
    "ip_filter": {
      "whitelist": ["192.168.1.0/24", "10.0.0.1"],
      "blacklist": ["1.2.3.4"],
      "trust_proxy": false
    }
  }
}
```

### 기능

- **화이트리스트**: 지정된 IP만 접근 허용
- **블랙리스트**: 지정된 IP 접근 차단
- **CIDR 지원**: 네트워크 범위 지정 가능
- **프록시 지원**: X-Forwarded-For 헤더로 실제 IP 추출

### 응답

차단된 IP 접근 시 HTTP 403 응답.

---

## 모니터링 및 알림 (Monitoring & Alerts)

### Slack 알림

설정 시 에러 발생 시 Slack으로 알림 전송.

### 이메일 알림

설정 시 에러 발생 시 이메일로 알림 전송.

### 설정 (config.json)

```json
{
  "server": {
    "monitoring": {
      "slack_webhook_url": "https://hooks.slack.com/...",
      "email_smtp_server": "smtp.gmail.com",
      "email_smtp_port": 587,
      "email_username": "user@gmail.com",
      "email_password": "password",
      "email_from": "noreply@example.com",
      "email_to": ["admin@example.com"]
    }
  }
}
```

---

## 백업 및 복구 (Backup & Restore)

### 자동 백업

설정된 간격으로 자동 백업 수행.

### 설정 (config.json)

```json
{
  "server": {
    "backup": {
      "backup_dir": "backups",
      "db_path": "execution_history.db",
      "max_backups": 7,
      "backup_interval_hours": 24
    }
  }
}
```

### 백업 파일

- 형식: ZIP
- 포함: 데이터베이스, 결과 파일, 메타데이터
- 명명: `backup_YYYYMMDD_HHMMSS.zip`

### 기능

- 자동 백업 스케줄링
- 오래된 백업 자동 정리
- 백업 목록 조회
- 백업 복구
- 백업 삭제

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
