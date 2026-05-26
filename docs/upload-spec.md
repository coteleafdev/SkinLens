# 업로드 스펙 (Client → Server)

클라이언트(Flutter 앱)가 사진 + 설문을 서버로 업로드할 때 사용하는 요청 포맷.

## 1. 요청 개요

| 항목 | 값 |
| --- | --- |
| Method | `POST` |
| Path | `/v3/analysis/jobs` |
| Content-Type | `multipart/form-data` |
| 인증 | (추후 정의 — 현재 미정) |
| 응답 | `202 Accepted` + `{ "job_id": "<string>" }` |

> 사진은 바이너리 파일 그대로 멀티파트 파트로 보낸다 (base64 X).
> 설문은 멀티파트의 한 텍스트 필드(`survey`)에 **JSON 문자열**로 직렬화해 넣는다.

## 2. 멀티파트 파트 구성

| 파트 이름 | 종류 | 필수 | 설명 |
| --- | --- | --- | --- |
| `images[]` | file (image/jpeg) | ✅ | 얼굴 사진 1~3장. 아래 "이미지 파일" 참고 |
| `angles[]` | text | 권장 | 각 이미지에 대응하는 각도 라벨. `images[]`와 인덱스 일치. 미제공 시 front→left45→right45 자동 할당 |
| `survey` | text (JSON) | ✅ | 설문 응답 + AI 측정용 메타. 아래 "설문 JSON" 참고 |
| `customer_id` | text | | (선택) 로그인 사용자 식별자 |
| `client_meta` | text (JSON) | | 앱 버전 / 플랫폼 등 진단 정보 |

### 이미지 파일

- 3장 (정면 / 좌측 45° / 우측 45°) 한 번에 전송
- 포맷: JPEG
- 권장 해상도: 짧은 변 ≥ 1080px
- 파일명 예: `front.jpg`, `left45.jpg`, `right45.jpg`
- 클라이언트가 촬영 직전 품질 검증(밝기/블러)을 통과한 이미지만 보낸다

### `angles[]` 값

`images[]` 순서와 1:1 매칭. 다음 세 값 중 하나:

- `front` — 정면 **(파이프라인 주 입력으로 사용)**
- `left45` — 좌측 45° (사용자가 고개를 오른쪽으로 살짝 돌린 상태)
- `right45` — 우측 45° (사용자가 고개를 왼쪽으로 살짝 돌린 상태)

서버가 유효하지 않은 값을 수신하면 `400 Bad Request` 로 거부합니다.  
`angles[]` 미제공 시: 첫 번째 이미지=front, 두 번째=left45, 세 번째=right45 자동 할당.  
`front` 이미지가 없으면 첫 번째 업로드 이미지를 front로 사용합니다.

## 3. 설문 JSON (`survey` 필드)

```json
{
  "consent_agreed": true,
  "gender": "female",
  "age_group": "30s",
  "ethnicity": "korean",
  "ethnicity_other": null,

  "skin_types":      ["combination", "sensitive"],
  "skin_interests":  ["pore_care", "wrinkle"],
  "skin_concerns":   ["acne", "red_marks", "pore_sebum"],
  "skin_concerns_other": null,

  "allergies": {
    "herb":      { "has": false, "detail": null },
    "sunlight":  { "has": true,  "detail": "여름철 일광 두드러기" },
    "cosmetics": { "has": false, "brand": null }
  },

  "current_products":       ["cleanser", "toner", "serum", "sunscreen"],
  "current_products_other": null,
  "product_brand":          "예시 브랜드",
  "usage_frequency":        "daily",

  "improvement_goals":       ["pore_reduction", "tone_brightening"],
  "improvement_goals_other": null,
  "priority_first":  "pore_reduction",
  "priority_second": "tone_brightening",

  "preferred_formula": ["light", "fragrance_free"],
  "price_range":      "30k_50k",

  "want_recommendation":   true,
  "want_followup_alert":   true,

  "saved_at": "2026-05-15T10:30:00+09:00"
}
```

### 3.1 enum 값 정의

값은 모두 영문 snake_case로 보낸다. 한국어 라벨은 클라이언트가 표시 시 매핑한다.

#### `gender`

`male` · `female` · `other` · `prefer_not_to_say`

#### `age_group`

`under_20` · `20s` · `30s` · `40s` · `50s` · `60_plus`

#### `ethnicity`

`korean` · `east_asian` · `southeast_asian` · `south_asian` · `caucasian` · `african` · `hispanic` · `other`
→ `other` 일 때 `ethnicity_other`에 자유 입력

#### `skin_types` (멀티, 1개 이상)

`dry` · `normal` · `oily` · `combination` · `sensitive` · `unknown`

#### `skin_interests` (멀티)

`brightening` · `exfoliation` · `wrinkle` · `pore_care` · `anti_aging` · `elasticity` · `hydration_nutrition`

#### `skin_concerns` (멀티, 제한 없음)

`atopy` · `acne` · `red_marks` · `itching` · `dryness_cracking` · `stinging_burning`
· `wrinkle_eye_mouth_nasolabial` · `rough_dull` · `excess_sebum`
· `pigmentation_spots` · `blackheads_whiteheads` · `keratin` · `allergy`
→ 추가 자유 입력은 `skin_concerns_other`

#### `current_products` (멀티)

`cleanser` · `toner` · `essence_serum` · `ampoule` · `cream` · `sunscreen`
· `brightening` · `exfoliating`

#### `usage_frequency`

`daily` · `several_per_week` · `weekly` · `irregular`

#### `improvement_goals` (멀티)

`pigment_spot` · `tone_brightening` · `elasticity` · `wrinkle`
· `redness_relief` · `pore_reduction` · `sebum_control` · `hydration`

#### `priority_first`, `priority_second`

`improvement_goals`에 정의된 enum 값 중 하나씩 (서로 달라야 함)

#### `preferred_formula` (멀티)

`light` · `rich` · `fragrance_free` · `natural_organic` · `low_irritation` · `no_preference`

#### `price_range`

`under_10k` · `10k_30k` · `30k_50k` · `50k_100k` · `over_100k`

### 3.2 nullable 규칙

- 사용자가 입력하지 않은 자유 텍스트 필드는 `null` (빈 문자열 X)
- 멀티 선택 필드는 항상 배열로 보낸다. 선택이 없으면 `[]`
- `consent_agreed`는 필수 (`false`면 서버가 400 반환)

## 4. `client_meta` JSON (선택)

```json
{
  "app_version": "1.0.3",
  "build_number": "42",
  "platform": "ios",
  "os_version": "17.4",
  "device_model": "iPhone 15 Pro",
  "captured_at": "2026-05-15T10:29:45+09:00"
}
```

`platform`: `ios` · `android`

## 5. 응답

### 5.1 성공 — `202 Accepted`

```json
{ "job_id": "j_01HXYZ..." }
```

이후 클라이언트는 기존 폴링 API를 그대로 사용:

- `GET /v3/analysis/jobs/{job_id}` — 상태 조회 (`queued` / `processing` / `succeeded` / `failed`)
- `GET /v3/analysis/jobs/{job_id}/result` — 최종 결과
- `GET /v3/analysis/jobs/{job_id}/artifacts/{name}` — 산출물 (예: `results.json`)

### 5.2 실패

| 코드 | 의미 |
| --- | --- |
| `400` | 필드 누락 / enum 값 불일치 / `consent_agreed=false` |
| `413` | 이미지 용량 초과 |
| `415` | 지원하지 않는 이미지 포맷 |
| `422` | 이미지 품질 미달 (서버 측 검증 실패 시) |
| `500` | 서버 오류 |

에러 응답 바디:

```json
{
  "error": {
    "code": "INVALID_FIELD",
    "field": "survey.gender",
    "message": "gender must be one of [male, female, other, prefer_not_to_say]"
  }
}
```

## 6. cURL 예시

```bash
curl -X POST https://skin.ai.coteleaf.com/v3/analysis/jobs \
  -F "mode=cv_only" \
  -F "customer_id=u_12345" \
  -F "images[]=@front.jpg;type=image/jpeg" \
  -F "images[]=@left45.jpg;type=image/jpeg" \
  -F "images[]=@right45.jpg;type=image/jpeg" \
  -F "angles[]=front" \
  -F "angles[]=left45" \
  -F "angles[]=right45" \
  -F "survey=<survey.json;type=application/json" \
  -F "client_meta=<meta.json;type=application/json"
```

## 7. 변경점 요약 (현행 대비)

현재 클라이언트는 이미지 1장씩 3개의 별도 job을 만들고 설문은 서버로 보내지 않는다.
신규 스펙은 **한 번의 요청에 3장 + 설문**을 묶어 한 job으로 처리.

| 항목 | 현행 | 신규 |
| --- | --- | --- |
| job 단위 | 사진 1장당 1 job | 3장 한 묶음 = 1 job |
| 설문 전송 | 없음 (클라이언트 로컬만) | `survey` 필드로 함께 업로드 |
| 응답 처리 | 3개 job 결과 평균 (클라이언트) | 서버가 3장을 종합한 결과 1건 반환 |

---
