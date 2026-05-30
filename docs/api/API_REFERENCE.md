# API 레퍼런스 (API Reference)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.6  
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

**POST** `/v3/auth/login`

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

**GET** `/v3/auth/me`

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

**POST** `/v3/analysis/jobs`

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

**GET** `/v3/analysis/jobs/{job_id}`

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

**DELETE** `/v3/analysis/jobs/{job_id}`

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

**POST** `/v3/analysis/jobs/{job_id}/confirm-skin-type`

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

**GET** `/v3/analysis/jobs/{job_id}/artifacts/{filename}`

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

**GET** `/v3/customer/my/info`

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

**GET** `/v3/customer/my/analyses`

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

**GET** `/v3/stats/analysis`

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

| 엔드포인트 | 제한 |
|-----------|------|
| POST /v3/auth/login | 5/분 |
| POST /v3/analysis/jobs | 30/분 |
| GET /v3/analysis/jobs/{job_id} | 60/분 |
| GET /v3/customer/my/* | 60/분 |
| GET /v3/stats/* | 30/분 |
| 기타 엔드포인트 | 100/분 |

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
