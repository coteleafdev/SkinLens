# 모바일 앱 통합 가이드 (Mobile App Integration Guide)

> **프로젝트:** SkinLens v1.0
> **대상:** 스마트폰 앱 개발자 (Flutter, iOS, Android)
> **최종 수정:** 2026-05-24

이 문서는 스마트폰 앱에서 SkinLens v1.0 서버와 통합하여 피부 분석 기능을 구현하는 방법을 설명합니다.

---

## 개요

### 전체 흐름

```mermaid
sequenceDiagram
    participant App as 모바일 앱
    participant Server as SkinLens 서버
    participant DB as 데이터베이스

    App->>Server: 1. 로그인 (JWT 토큰 발급)
    Server-->>App: JWT Access Token

    App->>Server: 2. 설문 데이터 전송 + 이미지 3장 업로드
    Server->>Server: 3. 복원 처리 (RestorerRegistry)
    Server->>Server: 4. 피부 분석 (AnalyzerRegistry)
    Server->>Server: 5. 처방 계산 (PrescriptionCalculator)
    Server->>Server: 6. 제품 매칭 (ProductRepository)
    Server->>Server: 7. AI 소견 생성 (LLMRegistry)
    Server->>DB: 8. 결과 저장
    Server-->>App: 9. 분석 결과 JSON

    App->>Server: 10. 결과 조회 (WebSocket 진행률)
    Server-->>App: 11. 진행률 업데이트
```

---

## 1. 인증 (Authentication)

### 1.1 로그인

**엔드포인트:** `POST /v3/auth/login`

**Request:**
```json
{
  "customer_id": "user123",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 1.2 JWT 토큰 사용

모든 API 요청에 `Authorization` 헤더에 JWT 토큰을 포함:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 2. 설문 데이터 구조

### 2.1 설문 JSON 형식

```json
{
  "consent_agreed": true,
  "gender": "female",
  "age_group": "30s",
  "skin_types": ["combination", "sensitive"],
  "skin_concerns": ["acne", "red_marks", "pigmentation"]
}
```

### 2.2 설문 필드 설명

| 필드 | 타입 | 필수 | 설명 | 가능한 값 |
|------|------|------|------|----------|
| `consent_agreed` | boolean | ✓ | 개인정보 동의 | true/false |
| `gender` | string | ✓ | 성별 | male, female |
| `age_group` | string | ✓ | 연령대 | 10s, 20s, 25s, 30s, 35s, 40s, 50s, 60s |
| `skin_types` | array[string] | ✓ | 피부 타입 | oily, dry, combination, sensitive |
| `skin_concerns` | array[string] | ✓ | 피부 고민사항 | acne, red_marks, pigmentation, wrinkles, pores, dullness, elasticity |

---

## 3. 이미지 업로드

### 3.1 이미지 캡처 가이드

**중요:** 분석 정확도를 위해 **보정 없는 원본 이미지** 촬영을 권장합니다. 스마트폰의 자동 보정, 필터, 뷰티 모드 등을 끄고 촬영해 주세요.

**캡처 각도 (3장):**
- **정면 (front):** 얼굴이 정면을 향하도록
- **좌측 45° (left45):** 얼굴이 왼쪽으로 45도 회전
- **우측 45° (right45):** 얼굴이 오른쪽으로 45도 회전

**이미지 요구사항:**
- 형식: JPEG
- 권장 해상도: 짧은 변 ≥ 1080px
- 조명: 자연광, 그림자 없음
- 표정: 중립, 눈 크게 뜨기
- **보정:** 자동 보정, 필터, 뷰티 모드 끄기 (원본 이미지 촬영)
- **메이크업:** 최소화 (피부 상태 정확 측정을 위해)

### 3.2 분석 Job 생성

**엔드포인트:** `POST /v3/analysis/jobs`

**Request (multipart/form-data):**
```
images[]: (file) 정면 이미지
images[]: (file) 좌측 45° 이미지
images[]: (file) 우측 45° 이미지
angles[]: (string) front
angles[]: (string) left45
angles[]: (string) right45
survey: (string) 설문 JSON (stringified)
client_meta: (string) 클라이언트 메타 JSON (stringified)
customer_id: (string) 고객 ID
use_multi_view_analysis: (bool) 다중 뷰 분석 사용 (기본 true)
```

**client_meta 예시:**
```json
{
  "app_version": "1.0.3",
  "platform": "ios",
  "os_version": "17.4",
  "device_model": "iPhone 14"
}
```

**Response:**
```json
{
  "job_id": "7c45d7d5-2f9e-4e64-bc2a-8d2b1d3b2f91",
  "status": "queued",
  "created_at": "2026-05-24T12:00:00Z"
}
```

---

## 4. 처리 과정

### 4.1 백엔드 처리 단계

서버에서 다음 순서로 처리됩니다:

1. **데이터 검증 및 파싱**
   - 이미지 저장 및 각도 검증
   - 설문 JSON 파싱
   - client_meta 파싱

2. **이미지 전처리**
   - RGB 변환
   - 리사이징 (1024×1365)
   - LANCZOS 리샘플링

3. **복원 처리**
   - RestorerRegistry에서 복원 백엔드 선택 (codeformer_v1)
   - 전처리 훅 호출 (preprocess)
   - CodeFormer/RestoreFormer++ 복원
   - 후처리 훅 호출 (postprocess)

4. **피부 분석**
   - AnalyzerRegistry에서 분석기 선택 (6개 분석기)
   - 18개 측정항목 분석
   - 다중 뷰 분석 (정면 + 좌45° + 우45°)
     - 각도별 특화 항목 가중치 적용
     - 측면 특화: 모공 처짐, 눈가 주름, 턱선 흐림, 볼 처짐 (front: 20%, left: 40%, right: 40%)
     - 정면 특화: 기미, 홍조, 피부 톤, 칙칙함, 톤 불균일, 인중 주름 (front: 70%, left: 15%, right: 15%)
     - 최대값 기반: 여드름, 여드름 후 색소
     - 각도별 개별 결과 포함 (`angle_results`)
   - 직교 신호 분해 (10개 내부 신호)
   - 가중치 체계 적용 (레이어A/레이어B/레거시)

5. **처방 계산**
   - PrescriptionCalculator로 처방전 생성
   - AGE_GROUP_MAPPING으로 나이대 그룹 매핑
   - PCR 규칙 적용 (total/beneficial/trouble/harmful)
   - 믹스 코드 계산 (M01~M10)

6. **제품 매칭**
   - ProductRepository에서 맞춤형 화장품 조회
   - 고민사항 매칭 (+0.5 점)
   - 피부 타입 매칭 (+0.3 점)
   - 측정 점수 기반 매칭 (+0.2 점)
   - match_score 계산 및 정렬

7. **AI 소견 생성**
   - LLMRegistry에서 LLM 선택 (gemini_v1)
   - Gemini API 호출
   - 듀얼 이미지 소견 (원본/복원 비교)
   - 성분 정보 포함

8. **DB 저장**
   - 로컬 SQLite DB 저장
   - Supabase 동기화 (이미지 + 결과)

### 4.2 진행률 추적 (WebSocket)

**엔드포인트:** `WS /v3/ws/analyze/{job_id}`

**메시지 형식:**
```json
{
  "type": "progress",
  "percent": 45,
  "message": "복원 처리 중...",
  "stage": "restoration"
}
```

**진행 단계:**
- `queued`: 대기 중
- `preprocessing`: 이미지 전처리
- `restoration`: 복원 처리
- `analysis`: 피부 분석
- `prescription`: 처방 계산
- `product_matching`: 제품 매칭
- `llm_generation`: AI 소견 생성
- `saving`: DB 저장
- `complete`: 완료

---

## 5. 결과 JSON 형식

### 5.1 전체 결과 구조

```json
{
  "job_id": "7c45d7d5-2f9e-4e64-bc2a-8d2b1d3b2f91",
  "status": "succeeded",
  "timestamp": "2026-05-24T12:01:02.345Z",
  "analysis": {
    "input_image": "/v3/analysis/jobs/.../artifacts/input.jpg",
    "restored_image": "/v3/analysis/jobs/.../artifacts/00_restored.png",
    "metadata": {
      "analyzers": {
        "pigmentation": "pigmentation_v1",
        "redness": "redness_v1",
        "pore": "pore_v1",
        "wrinkle": "wrinkle_v1",
        "tone_elasticity": "tone_elasticity_v1",
        "acne": "acne_v1"
      },
      "restorer": {
        "name": "codeformer_v1",
        "config": {
          "repo": null,
          "fidelity": 1.0,
          "upscale": 1,
          "bg_upsampler": "none"
        }
      },
      "llm": {
        "name": "gemini_v1",
        "model": "models/gemini-2.5-pro"
      }
    },
    "input_json": {
      "survey": {
        "consent_agreed": true,
        "gender": "female",
        "age_group": "30s",
        "skin_types": ["combination", "sensitive"],
        "skin_concerns": ["acne", "red_marks"]
      },
      "client_meta": {
        "app_version": "1.0.3",
        "platform": "ios",
        "os_version": "17.4"
      }
    },
    "internal_analysis": {
      "original": {
        "melasma_score": 56,
        "freckle_score": 80,
        "redness_score": 72,
        "post_inflammatory_erythema_score": 65,
        "acne_score": 50,
        "post_acne_pigment_score": 60,
        "pore_size_score": 70,
        "pore_sagging_score": 68,
        "eye_wrinkle_score": 55,
        "nasolabial_wrinkle_score": 60,
        "fine_deep_wrinkle_score": 58,
        "roughness_score": 62,
        "skin_tone_score": 65,
        "dullness_score": 70,
        "uneven_tone_score": 68,
        "jawline_blur_score": 55,
        "cheek_sagging_score": 60,
        "skin_type_score": 50,
        "overall_score": 62.5
      },
      "restored": {
        "melasma_score": 70,
        "freckle_score": 85,
        "redness_score": 75,
        "post_inflammatory_erythema_score": 70,
        "acne_score": 65,
        "post_acne_pigment_score": 68,
        "pore_size_score": 75,
        "pore_sagging_score": 72,
        "eye_wrinkle_score": 60,
        "nasolabial_wrinkle_score": 65,
        "fine_deep_wrinkle_score": 62,
        "roughness_score": 68,
        "skin_tone_score": 70,
        "dullness_score": 75,
        "uneven_tone_score": 72,
        "jawline_blur_score": 60,
        "cheek_sagging_score": 65,
        "skin_type_score": 55,
        "overall_score": 69.5
      }
    },
    "prescription": {
      "mix_codes": {
        "M01": {"base": 10.0, "items": ["나이아신아마이드", "비타민 C"]},
        "M02": {"base": 15.0, "items": ["레티놀", "펩타이드"]},
        "M10": {"base": 8.0, "items": ["살리실산", "티트리 오일"]}
      },
      "recommendation": "측정된 피부 상태를 기반으로 맞춤형 처방전을 생성했습니다."
    },
    "llm_analysis": {
      "recommendation": "현재 피부 상태를 개선하고 유지하기 위해 다음과 같은 관리를 권장합니다.\n\n1. **색소 및 톤 케어**: 비타민 C, 나이아신아마이드 등 미백 기능성 성분이 포함된 제품을 사용하여 주근깨와 잡티를 관리하고, 칙칙한 피부 톤을 개선하는 것이 중요합니다.\n\n2. **피부결 및 주름 개선**: 레티놀, 레티날 등 비타민 A 유도체나 펩타이드 성분은 피부 세포의 재생을 돕고 콜라겐 생성을 촉진하여 잔주름과 거친 피부결을 개선하는 데 효과적입니다.\n\n...",
      "product_recommendations": {
        "matched_products": [
          {
            "product_id": "P001",
            "product_name": "CÔTELEAF 트러블 케어 세럼",
            "category": "트러블 케어",
            "key_ingredients": ["나이아신아마이드", "살리실산", "티트리 오일"],
            "efficacy": "여드름 억제, 모공 관리, 피부 진정",
            "match_score": 0.95,
            "match_reason": "설문의 피부 고민사항(여드름)과 측정 점수(acne_score: 50) 기반 매칭"
          }
        ],
        "recommendation_summary": "측정된 피부 상태와 설문 응답을 기반으로 당사 맞춤형 화장품 1종을 추천합니다."
      }
    }
  },
  "artifacts": {
    "results.json": "/v3/analysis/jobs/.../artifacts/results.json",
    "input_image": "/v3/analysis/jobs/.../artifacts/input.jpg",
    "restored_image": "/v3/analysis/jobs/.../artifacts/00_restored.png"
  }
}
```

### 5.2 주요 필드 설명

#### 5.2.1 internal_analysis

**original:** 원본 이미지 분석 결과 (18개 측정항목 점수)
- 점수 범위: 0-100
- 높은 점수: 좋은 상태
- 낮은 점수: 개선 필요

**restored:** 복원 이미지 분석 결과 (18개 측정항목 점수)
- 복원 후 개선된 점수

**overall_score:** 종합 점수
- 90 이상: 매우 우수
- 80~90: 우수
- 70~80: 양호
- 60~70: 집중케어 추천
- 60 미만: 개선 필요

#### 5.2.2 prescription

**mix_codes:** 처방 믹스 코드
- M01: 광채 (톤·밝기)
- M02: 주름
- M05: 탄력
- M06: 색소침착
- M07: 홍조
- M08: 피부결
- M09: 모공
- M10: 여드름

**base:** 믹스 비율 (%)
**items:** 포함 성분 목록

#### 5.2.3 llm_analysis

**recommendation:** AI 소견 (한국어)
- 피부 상태 분석
- 개선 제안
- 라이프스타일 권장사항

**product_recommendations:** 맞춤형 화장품 추천
- matched_products: 매칭된 제품 목록 (최대 3개)
- match_score: 매칭 점수 (0-1)
- match_reason: 매칭 사유

---

## 6. 에러 처리

### 6.1 에러 응답 형식

```json
{
  "error": true,
  "error_type": "ValidationError",
  "error_message": "이미지 각도가 유효하지 않습니다.",
  "timestamp": "2026-05-24T12:00:00Z",
  "details": {
    "field": "angles[]",
    "expected": ["front", "left45", "right45"],
    "received": ["front", "left", "right"]
  }
}
```

### 6.2 공통 에러 코드

| 에러 코드 | 설명 | 해결 방법 |
|----------|------|----------|
| 400 | 입력 오류 | 이미지 형식, 각도, 설문 데이터 확인 |
| 401 | 인증 실패 | JWT 토큰 갱신 |
| 404 | 리소스 없음 | job_id 확인 |
| 409 | Job 미완료 | 잠시 후 재시도 |
| 429 | 속도 제한 초과 | 3회/분 제한 준수 |
| 500 | 서버 내부 오류 | 서버 관리자 문의 |

---

## 7. Flutter 예제 코드

### 7.1 로그인

```dart
Future<String> login(String customerId, String password) async {
  final response = await http.post(
    Uri.parse('$baseUrl/v3/auth/login'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'customer_id': customerId,
      'password': password,
    }),
  );

  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return data['access_token'];
  } else {
    throw Exception('로그인 실패');
  }
}
```

### 7.2 이미지 업로드 및 분석 요청

```dart
Future<String> submitAnalysis(
  String token,
  List<File> images,
  Map<String, dynamic> survey,
  Map<String, dynamic> clientMeta,
  String customerId,
) async {
  final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/v3/analysis/jobs'));
  
  // JWT 토큰 추가
  request.headers['Authorization'] = 'Bearer $token';
  
  // 이미지 추가
  final angles = ['front', 'left45', 'right45'];
  for (int i = 0; i < images.length; i++) {
    request.files.add(await http.MultipartFile.fromPath(
      'images[]',
      images[i].path,
    ));
    request.fields['angles[]'] = angles[i];
  }
  
  // 설문 데이터 추가
  request.fields['survey'] = jsonEncode(survey);
  request.fields['client_meta'] = jsonEncode(clientMeta);
  request.fields['customer_id'] = customerId;
  
  final response = await request.send();
  final responseData = await response.stream.bytesToString();
  
  if (response.statusCode == 202) {
    final data = jsonDecode(responseData);
    return data['job_id'];
  } else {
    throw Exception('분석 요청 실패');
  }
}
```

### 7.3 WebSocket 진행률 추적

```dart
void trackProgress(String jobId, String token) {
  final channel = WebSocketChannel.connect(
    Uri.parse('$wsBaseUrl/v3/ws/analyze/$jobId'),
  );
  
  channel.stream.listen(
    (message) {
      final data = jsonDecode(message);
      if (data['type'] == 'progress') {
        print('진행률: ${data['percent']}% - ${data['message']}');
        updateProgressBar(data['percent'], data['message']);
      } else if (data['type'] == 'complete') {
        print('분석 완료');
        channel.sink.close();
      } else if (data['type'] == 'error') {
        print('에러: ${data['error']}');
        channel.sink.close();
      }
    },
    onError: (error) {
      print('WebSocket 에러: $error');
    },
    onDone: () {
      print('WebSocket 연결 종료');
    },
  );
}
```

### 7.4 결과 조회

```dart
Future<Map<String, dynamic>> getResult(String jobId, String token) async {
  final response = await http.get(
    Uri.parse('$baseUrl/v3/analysis/jobs/$jobId/result'),
    headers: {'Authorization': 'Bearer $token'},
  );

  if (response.statusCode == 200) {
    return jsonDecode(response.body);
  } else {
    throw Exception('결과 조회 실패');
  }
}
```

---

## 8. JavaScript 예제 코드

### 8.1 로그인

```javascript
async function login(customerId, password) {
  const response = await fetch(`${baseUrl}/v3/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id: customerId, password }),
  });

  if (response.ok) {
    const data = await response.json();
    return data.access_token;
  } else {
    throw new Error('로그인 실패');
  }
}
```

### 8.2 이미지 업로드 및 분석 요청

```javascript
async function submitAnalysis(token, images, survey, clientMeta, customerId) {
  const formData = new FormData();
  
  // 이미지 추가
  const angles = ['front', 'left45', 'right45'];
  images.forEach((image, index) => {
    formData.append('images[]', image);
    formData.append('angles[]', angles[index]);
  });
  
  // 설문 데이터 추가
  formData.append('survey', JSON.stringify(survey));
  formData.append('client_meta', JSON.stringify(clientMeta));
  formData.append('customer_id', customerId);
  
  const response = await fetch(`${baseUrl}/v3/analysis/jobs`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData,
  });

  if (response.ok) {
    const data = await response.json();
    return data.job_id;
  } else {
    throw new Error('분석 요청 실패');
  }
}
```

### 8.3 WebSocket 진행률 추적

```javascript
function trackProgress(jobId) {
  const ws = new WebSocket(`${wsBaseUrl}/v3/ws/analyze/${jobId}`);
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'progress') {
      console.log(`진행률: ${data.percent}% - ${data.message}`);
      updateProgressBar(data.percent, data.message);
    } else if (data.type === 'complete') {
      console.log('분석 완료');
      ws.close();
    } else if (data.type === 'error') {
      console.error('에러:', data.error);
      ws.close();
    }
  };
  
  ws.onerror = (error) => {
    console.error('WebSocket 에러:', error);
  };
  
  ws.onclose = () => {
    console.log('WebSocket 연결 종료');
  };
}
```

---

## 9. 참고 문서

- [API_GUIDE.md](API_GUIDE.md) - 상세 API 문서
- [data_process_flow.md](data_process_flow.md) - 데이터 처리 흐름 상세
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) - 프로젝트 개요
- [RESTORATION_ENGINE_GUIDE.md](RESTORATION_ENGINE_GUIDE.md) - 복원 엔진 가이드

---

*생성일: 2026-05-24*
