# 데이터 모델 (Data Model)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

---

## 개요

SkinLens 데이터베이스 스키마와 JSON 구조 설명입니다.

---

## 1. 데이터베이스 스키마

### 1.1 SQLite (로컬)

**테이블: analyses**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | Primary Key, Auto Increment |
| customer_id | TEXT | 고객 ID (nullable) |
| original_image_path | TEXT | 원본 이미지 경로 |
| restored_image_path | TEXT | 복원 이미지 경로 |
| json_result | TEXT | 분석 결과 JSON |
| input_json | TEXT | 입력 JSON (nullable) |
| original_filename | TEXT | 원본 파일명 |
| overall_score_original | REAL | 원본 종합 점수 |
| overall_score_restored | REAL | 복원 종합 점수 |
| detected_skin_types | TEXT | 감지된 피부 타입 (JSON) |
| skin_type_confidence | REAL | 피부 타입 신뢰도 |
| skin_type_features | TEXT | 피부 타입 특징 (JSON) |
| skin_type_source | TEXT | 피부 타입 소스 |
| created_at | TIMESTAMP | 생성 시간 |

**인덱스:**
- `idx_customer_id`: customer_id
- `idx_created_at`: created_at

---

**테이블: api_keys**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | Primary Key, Auto Increment |
| key_hash | TEXT | API 키 SHA-256 해시 |
| name | TEXT | API 키 이름 |
| description | TEXT | 설명 (nullable) |
| owner_id | TEXT | 소유자 ID |
| scopes | TEXT | 권한 범위 (JSON) |
| is_active | BOOLEAN | 활성 상태 |
| expires_at | TIMESTAMP | 만료일 (nullable) |
| last_used_at | TIMESTAMP | 마지막 사용 시간 (nullable) |
| created_at | TIMESTAMP | 생성 시간 |
| revoked_at | TIMESTAMP | 폐지 시간 (nullable) |
| revoke_reason | TEXT | 폐지 사유 (nullable) |

**인덱스:**
- `idx_key_hash`: key_hash
- `idx_owner_id`: owner_id
- `idx_is_active`: is_active

---

**테이블: api_key_usage_logs**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | Primary Key, Auto Increment |
| api_key_id | INTEGER | API 키 ID (FK) |
| endpoint | TEXT | 요청 엔드포인트 |
| method | TEXT | HTTP 메서드 |
| ip_address | TEXT | 클라이언트 IP |
| user_agent | TEXT | User-Agent |
| success | BOOLEAN | 성공 여부 |
| error_message | TEXT | 에러 메시지 (nullable) |
| created_at | TIMESTAMP | 생성 시간 |

**인덱스:**
- `idx_api_key_id`: api_key_id
- `idx_created_at`: created_at
- `idx_endpoint`: endpoint

---

### 1.2 Supabase (클라우드)

**테이블: skin_analyses**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | Primary Key |
| customer_id | TEXT | 고객 ID (FK) |
| original_image_path | TEXT | 원본 이미지 경로 |
| restored_image_path | TEXT | 복원 이미지 경로 |
| json_result | JSONB | 분석 결과 JSON |
| input_json | JSONB | 입력 JSON (nullable) |
| original_filename | TEXT | 원본 파일명 |
| overall_score_original | INTEGER | 원본 종합 점수 |
| overall_score_restored | INTEGER | 복원 종합 점수 |
| detected_skin_types | JSONB | 감지된 피부 타입 |
| skin_type_confidence | REAL | 피부 타입 신뢰도 |
| skin_type_features | JSONB | 피부 타입 특징 |
| skin_type_source | TEXT | 피부 타입 소스 |
| created_at | TIMESTAMPTZ | 생성 시간 |

**RLS (Row Level Security):**
```sql
-- 고객은 자신의 데이터만 접근
CREATE POLICY customer_access ON skin_analyses
  FOR SELECT USING (auth.uid()::text = customer_id);

-- 관리자는 전체 접근
CREATE POLICY admin_access ON skin_analyses
  FOR ALL USING (auth.jwt()->>'role' = 'admin');
```

---

**테이블: api_keys**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | Primary Key |
| key_hash | TEXT | API 키 SHA-256 해시 |
| name | TEXT | API 키 이름 |
| description | TEXT | 설명 (nullable) |
| owner_id | TEXT | 소유자 ID (FK) |
| scopes | JSONB | 권한 범위 |
| is_active | BOOLEAN | 활성 상태 |
| expires_at | TIMESTAMPTZ | 만료일 (nullable) |
| last_used_at | TIMESTAMPTZ | 마지막 사용 시간 (nullable) |
| created_at | TIMESTAMPTZ | 생성 시간 |
| revoked_at | TIMESTAMPTZ | 폐지 시간 (nullable) |
| revoke_reason | TEXT | 폐지 사유 (nullable) |

**인덱스:**
- `idx_key_hash`: key_hash
- `idx_owner_id`: owner_id
- `idx_is_active`: is_active

---

**테이블: api_key_usage_logs**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | Primary Key |
| api_key_id | UUID | API 키 ID (FK) |
| endpoint | TEXT | 요청 엔드포인트 |
| method | TEXT | HTTP 메서드 |
| ip_address | TEXT | 클라이언트 IP |
| user_agent | TEXT | User-Agent |
| success | BOOLEAN | 성공 여부 |
| error_message | TEXT | 에러 메시지 (nullable) |
| created_at | TIMESTAMPTZ | 생성 시간 |

**인덱스:**
- `idx_api_key_id`: api_key_id
- `idx_created_at`: created_at
- `idx_endpoint`: endpoint

---

## 2. JSON 구조

### 2.1 입력 JSON (Input JSON)

**스마트폰 앱 → 서버**

```json
{
  "survey": {
    "skin_type": "dry",
    "concerns": ["pigmentation", "redness"],
    "age_group": "30s"
  },
  "client_meta": {
    "app_version": "1.0.0",
    "device_model": "iPhone 14",
    "os_version": "iOS 16.0"
  }
}
```

**필드 설명:**
- `survey.skin_type`: 피부 타입 (dry, oily, combination, normal)
- `survey.concerns`: 고민 사항 (pigmentation, redness, pores, wrinkles, acne)
- `survey.age_group`: 연령대 (20s, 30s, 40s, 50s+)
- `client_meta.app_version`: 앱 버전
- `client_meta.device_model`: 기기 모델
- `client_meta.os_version`: OS 버전

---

### 2.2 출력 JSON (Output JSON)

**서버 → 스마트폰 앱**

```json
{
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
    "perceived_age": 28,
    "measurements": {
      "pigmentation": 65,
      "redness": 70,
      "pores": 80,
      "wrinkles": 75,
      "tone": 72,
      "elasticity": 78,
      "dark_circle": 68,
      "sebum": 74
    },
    "measurements_report": {
      "pigmentation": {
        "score": 65,
        "grade": "60~70점",
        "opinion": "색소침착이 약간 있습니다."
      }
    },
    "skin_type_detection": {
      "skin_types": ["dry", "sensitive"],
      "confidence": 0.85,
      "features": {
        "dryness": 0.9,
        "sensitivity": 0.8
      }
    },
    "llm_analysis": {
      "raw_response": "...",
      "overall_opinion": "전반적으로 피부 상태가 양호합니다.",
      "metric_scores": {
        "pigmentation": 65,
        "redness": 70
      },
      "metric_opinions": {
        "pigmentation": "색소침착이 약간 있습니다."
      },
      "recommendation": [
        "살리실산(BHA) 성분 제품 사용",
        "나이아신아마이드 미백 제품 사용"
      ],
      "matched_products": [
        {
          "name": "제품 A",
          "brand": "브랜드 A",
          "category": "serum"
        }
      ]
    }
  },
  "execution_time": {
    "total_sec": 90.5,
    "restore_sec": 45.2,
    "analysis_sec": 45.3
  },
  "metadata": {
    "config": {
      "restorer": "codeformer",
      "llm": "gemini"
    },
    "timestamp": "2026-05-30T10:00:00Z"
  }
}
```

**필드 설명:**
- `input_image_url`: 원본 이미지 URL
- `restored_image_url`: 복원 이미지 URL
- `customer_info`: 고객 정보
- `analysis_result.overall_score`: 종합 점수 (0-100)
- `analysis_result.perceived_age`: 인지 나이
- `analysis_result.measurements`: 측정 점수
- `analysis_result.measurements_report`: 측정 소견
- `analysis_result.skin_type_detection`: 피부 타입 감지
- `analysis_result.llm_analysis`: LLM 분석 결과
- `execution_time`: 실행 시간
- `metadata`: 메타데이터

---

### 2.3 오류 JSON (Error JSON)

```json
{
  "error": true,
  "error_type": "ValueError",
  "error_message": "이미지 파일이 없습니다.",
  "timestamp": "2026-05-30T10:00:00Z",
  "input_image": "/path/to/image.jpg",
  "output_dir": "/path/to/output",
  "customer_info": {
    "customer_id": "CUST001",
    "gender": "female",
    "age": 30,
    "race": "asian",
    "region": "KR"
  }
}
```

---

## 3. 측정 항목 (Measurements)

### 3.1 점수 범위

| 항목 | 범위 | 설명 |
|------|------|------|
| pigmentation | 0-100 | 색소침착 점수 |
| redness | 0-100 | 홍조 점수 |
| pores | 0-100 | 모공 점수 |
| wrinkles | 0-100 | 주름 점수 |
| tone | 0-100 | 피부톤 점수 |
| elasticity | 0-100 | 탄력 점수 |
| dark_circle | 0-100 | 다크서클 점수 |
| sebum | 0-100 | 피지 점수 |

### 3.2 등급 기준

| 점수 | 등급 |
|------|------|
| 90-100 | 90점 이상 |
| 80-89 | 80~90점 |
| 70-79 | 70~80점 |
| 60-69 | 60~70점 |
| 0-59 | 60점 미만 |

---

## 4. 관계 정의

### 4.1 ERD

```
Customer (고객)
  ├── 1:N → Analysis (분석)
  ├── 1:N → Order (주문)
  └── 1:N → PurchaseHistory (구매 이력)

Analysis (분석)
  ├── 1:1 → OriginalImage (원본 이미지)
  ├── 1:1 → RestoredImage (복원 이미지)
  └── 1:N → Measurement (측정 결과)

Order (주문)
  ├── 1:N → OrderItem (주문 항목)
  └── N:1 → Product (제품)
```

---

## 5. 데이터 마이그레이션

### 5.1 SQLite → Supabase

```sql
-- 데이터 내보내기
sqlite3 skin_analysis.db .dump > dump.sql

-- Supabase로 가져오기
psql -h xxx.supabase.co -U postgres -d postgres -f dump.sql
```

### 5.2 버전 마이그레이션

```python
# 마이그레이션 스크립트
def migrate_v1_to_v2():
    # 기존 데이터 백업
    backup_database()
    
    # 스키마 변경
    add_column('analyses', 'skin_type_source', 'TEXT')
    
    # 데이터 마이그레이션
    migrate_data()
    
    # 검증
    validate_migration()
```

---

## 참고 문서

- `API_REFERENCE.md` - API 레퍼런스
- `SECURITY_GUIDE.md` - 보안 가이드
- `ARCHITECTURE_GUIDE.md` - 아키텍처 가이드

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (표준화 적용) | Cascade |
| 0.6.0 | 2026-05-30 | 데이터 모델 문서 초기 작성 | Cascade |
