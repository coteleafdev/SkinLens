# 다국어 지원 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 다국어 지원 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 한국어만 지원
- 글로벌 확장 제한
- 해외 사용자 접근 불가
- 국제화(i18n) 미구현

### 1.2 제안된 기능
- 영어, 중국어, 일본어 등 다국어 지원
- 사용자 언어 설정
- 자동 언어 감지
- 다국어 API 응답
- 다국어 UI 지원

### 1.3 기대 효과
- 글로벌 확장
- 해외 사용자 유입
- 시장 점유율 확대
- 국제 경쟁력 강화

---

## 2. 지원 언어

### 2.1 1차 지원 언어
- **한국어 (ko):** 기본 언어
- **영어 (en):** 글로벌 표준
- **중국어 (zh):** 중국 시장
- **일본어 (ja):** 일본 시장

### 2.2 2차 지원 언어 (향후)
- **스페인어 (es):** 라틴 아메리카
- **프랑스어 (fr):** 유럽
- **독일어 (de):** 유럽

---

## 3. 기술 설계

### 3.1 국제화(i18n) 아키텍처
1. **언어 코드 표준:** ISO 639-1 (ko, en, zh, ja)
2. **번역 리소스:** JSON 파일로 번역 텍스트 관리
3. **언어 감지:** Accept-Language 헤더 또는 사용자 설정
4. **언어 전환:** 런타임 언어 변경 지원

### 3.2 번역 리소스 구조
```
locales/
  ko/
    common.json
    analysis.json
    prescription.json
    product.json
  en/
    common.json
    analysis.json
    prescription.json
    product.json
  zh/
    common.json
    analysis.json
    prescription.json
    product.json
  ja/
    common.json
    analysis.json
    prescription.json
    product.json
```

### 3.3 번역 리소스 예시 (common.json)
```json
{
  "app_name": "SkinLens",
  "welcome": "Welcome",
  "skin_analysis": "Skin Analysis",
  "prescription": "Prescription",
  "product_recommendation": "Product Recommendation",
  "settings": "Settings",
  "language": "Language"
}
```

### 3.4 API 다국어 지원
1. **언어 파라미터:** `?lang=en` 또는 헤더 `Accept-Language: en`
2. **다국어 응답:** 요청 언어에 맞는 응답 반환
3. **에러 메시지:** 다국어 에러 메시지
4. **데이터 다국어:** 제품명, 설명 등 다국어 필드

### 3.5 데이터 모델 확장

#### 3.5.1 사용자 테이블 확장 (users)
```sql
ALTER TABLE users ADD COLUMN preferred_language TEXT DEFAULT 'ko';
ALTER TABLE users ADD COLUMN locale TEXT DEFAULT 'ko-KR';
```

#### 3.5.2 제품 테이블 확장 (products)
```sql
ALTER TABLE products ADD COLUMN name_en TEXT;
ALTER TABLE products ADD COLUMN name_zh TEXT;
ALTER TABLE products ADD COLUMN name_ja TEXT;
ALTER TABLE products ADD COLUMN description_en TEXT;
ALTER TABLE products ADD COLUMN description_zh TEXT;
ALTER TABLE products ADD COLUMN description_ja TEXT;
ALTER TABLE products ADD COLUMN ingredients_en TEXT;
ALTER TABLE products ADD COLUMN ingredients_zh TEXT;
ALTER TABLE products ADD COLUMN ingredients_ja TEXT;
```

#### 3.5.3 분석 결과 다국어
분석 결과 JSON에 다국어 필드 추가:
```json
{
  "analysis_result": {
    "summary": {
      "ko": "피부 상태 분석 결과",
      "en": "Skin Analysis Result",
      "zh": "皮肤分析结果",
      "ja": "皮膚分析結果"
    }
  }
}
```

### 3.6 API 엔드포인트 변경

#### 3.6.1 언어 설정
- **경로:** `/v3/users/{user_id}/language`
- **메서드:** `PUT`
- **요청 바디:**
```json
{
  "language": "en",
  "locale": "en-US"
}
```
- **응답:**
```json
{
  "language": "en",
  "locale": "en-US"
}
```

#### 3.6.2 다국어 분석 결과
- **경로:** `/v3/jobs/{job_id}`
- **메서드:** `GET`
- **쿼리 파라미터:** `lang=en`
- **응답:**
```json
{
  "id": "string",
  "result": {
    "summary": "Skin Analysis Result",
    "recommendations": [
      {
        "title": "Hydration Boost",
        "description": "Increase moisture levels"
      }
    ]
  }
}
```

### 3.7 클라이언트 다국어 지원

#### 3.7.1 Flutter 다국어 설정
1. `flutter_localizations` 패키지 사용
2. `intl` 패키지 사용
3. 언어 리소스 파일 관리
4. 언어 전환 기능

#### 3.7.2 언어 전환 UI
- 언어 선택 드롭다운
- 자동 언어 감지 옵션
- 언어 설정 저장

#### 3.7.3 다국어 UI 구현
- 모든 텍스트 리소스에서 번역 키 사용
- 동적 언어 변경 지원
- RTL (Right-to-Left) 언어 지원 (향후)

---

## 4. 구현 단계

### 4.1 백엔드 국제화 (3일)
- 번역 리소스 구조 설계
- 번역 리소스 파일 생성 (ko, en, zh, ja)
- 다국어 미들웨어 구현
- API 응답 다국어 처리

### 4.2 데이터베이스 스키마 확장 (1일)
- `users` 테이블 확장
- `products` 테이블 확장
- 기존 데이터 다국어 마이그레이션

### 4.3 분석 결과 다국어 (2일)
- 분석 결과 다국어 필드 추가
- 분석 엔진 다국어 출력 구현
- 처방 다국어 출력 구현

### 4.4 API 문서 업데이트 (0.5일)
- 다국어 파라미터 문서화
- 다국어 응답 예시 추가

### 4.5 클라이언트 다국어 (3일)
- Flutter 다국어 설정
- 번역 리소스 파일 생성
- 언어 전환 UI 구현
- 모든 UI 텍스트 다국어 적용

### 4.6 번역 작업 (5일)
- 전체 텍스트 번역 (ko → en, zh, ja)
- 전문 번역가 검수
- 번역 품질 테스트

### 4.7 테스트 및 디버깅 (2일)
- 기능 테스트
- 번역 품질 테스트
- 언어 전환 테스트
- 에러 처리 테스트

**총 예상 소요 시간: 16.5일**

---

## 5. 성능 고려사항

- **번역 리소스 캐싱:** 메모리에 번역 리소스 캐싱
- **지연 로딩:** 필요한 언어 리소스만 로드
- **CDN 활용:** 정적 리소스 CDN 배포
- **데이터베이스 쿼리 최적화:** 다국어 필드 쿼리 최적화

---

## 6. 성공 지표

- **언어 지원 완료率:** 4개 언어 100% 지원
- **번역 품질:** 전문 번역가 검수 통과
- **해외 사용자 유입:** 다국어 지원 후 해외 사용자 +50%
- **언어 전환 성공률:** 99% 이상
- **API 응답 시간:** 다국어 처리로 인한 지연 50ms 이내
