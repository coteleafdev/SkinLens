# API 문서 (API Documentation)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.6  
> **작성일:** 2026-05-30  
> **상태:** 초안

---

## 개요

SkinLens API는 FastAPI를 기반으로 구축되었으며, 자동으로 OpenAPI/Swagger 문서가 생성됩니다.

---

## API 엔드포인트

### 인증 (Authentication)

#### POST /v3/auth/login
로그인 및 JWT 토큰 발급

**요청:**
```json
{
  "customer_id": "string",
  "password": "string"
}
```

**응답:**
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "customer_id": "string",
  "role": "admin|analyst|customer",
  "expires_in": 3600
}
```

#### GET /v3/auth/me
현재 인증된 사용자 정보 조회

**응답:**
```json
{
  "customer_id": "string",
  "role": "admin|analyst|customer"
}
```

---

### 분석 작업 (Analysis Jobs)

#### POST /v3/analysis/jobs
새로운 분석 작업 생성

**요청:**
- Content-Type: multipart/form-data
- `image`: 이미지 파일 (필수)
- `customer_id`: 고객 ID (선택)

**응답:**
```json
{
  "job_id": "uuid",
  "status": "pending|processing|completed|failed",
  "created_at": "ISO8601 timestamp"
}
```

#### GET /v3/analysis/jobs/{job_id}
작업 상태 조회

**응답:**
```json
{
  "job_id": "uuid",
  "status": "pending|processing|completed|failed",
  "created_at": "ISO8601 timestamp",
  "updated_at": "ISO8601 timestamp",
  "progress": 0-100
}
```

#### GET /v3/analysis/jobs/{job_id}/result
분석 결과 조회

**응답:**
```json
{
  "job_id": "uuid",
  "original_overall_score": 0-100,
  "restored_overall_score": 0-100,
  "metric_scores": {
    "melasma_score": 0-100,
    "freckle_score": 0-100,
    ...
  },
  "llm_analysis": {
    "opinions": {...},
    "matched_products": [...]
  }
}
```

#### POST /v3/analysis/jobs/{job_id}/confirm-skin-type
피부 타입 사용자 확인

**요청:**
```json
{
  "skin_types": ["dry", "oily", "combination", "sensitive"]
}
```

**응답:**
```json
{
  "job_id": "uuid",
  "skin_types": ["dry", "oily"],
  "skin_type_source": "manual"
}
```

---

### 아티팩트 (Artifacts)

#### GET /v3/analysis/jobs/{job_id}/artifacts/{name}
작업 아티팩트 다운로드

**파일명:**
- `original.png`: 원본 이미지
- `restored.png`: 복원 이미지
- `comparison.png`: 비교 이미지
- `results.json`: 분석 결과 JSON

---

## 인증

모든 API 엔드포인트 (로그인 제외)는 JWT 토큰 인증이 필요합니다.

**헤더:**
```
Authorization: Bearer {access_token}
```

---

## 에러 응답

**HTTP 상태 코드:**
- `200 OK`: 성공
- `400 Bad Request`: 잘못된 요청
- `401 Unauthorized`: 인증 실패
- `403 Forbidden`: 권한 없음
- `404 Not Found`: 리소스 없음
- `500 Internal Server Error`: 서버 오류

**에러 응답 형식:**
```json
{
  "detail": "에러 메시지"
}
```

---

## 속도 제한 (Rate Limiting)

- 로그인: 5회/분
- 분석 작업 생성: 10회/분
- 기타 엔드포인트: 100회/분

---

## Swagger UI

로컬 개발 환경에서 Swagger UI를 통해 API를 테스트할 수 있습니다.

**URL:** `http://localhost:8000/docs`

---

## OpenAPI 스펙

OpenAPI JSON 스펙은 다음 URL에서 확인할 수 있습니다.

**URL:** `http://localhost:8000/openapi.json`

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
