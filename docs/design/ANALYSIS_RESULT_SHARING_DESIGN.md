# 분석 결과 공유 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 분석 결과 SNS 공유 및 PDF 보고서 다운로드 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 분석 결과 개인용만 제공
- SNS 공유 기능 없음
- PDF 보고서 다운로드 불가
- 바이럴 마케팅 기회 부족

### 1.2 제안된 기능
- SNS 공유 (Instagram, Facebook, Twitter, KakaoTalk)
- PDF 보고서 다운로드
- 공유용 이미지 생성
- 공용 링크 생성
- 공유 통계 추적

### 1.3 기대 효과
- 바이럴 마케팅
- 사용자 유입 증가
- 브랜드 인지도 향상
- 사용자 참여도 증가

---

## 2. 공유 기능

### 2.1 SNS 공유
- **Instagram:** 이미지 + 캡션 공유
- **Facebook:** 이미지 + 텍스트 공유
- **Twitter:** 이미지 + 텍스트 공유
- **KakaoTalk:** 이미지 + 텍스트 공유
- **링크 복사:** 공용 링크 복사

### 2.2 PDF 보고서
- **분석 결과 요약:** 주요 분석 결과
- **점수 차트:** 각 측정 항목 점수 그래프
- **처방 정보:** 추천 처방 상세
- **제품 추천:** 추천 제품 목록
- **이미지 포함:** 분석된 이미지
- **브랜딩:** 로고 및 브랜딩 요소

### 2.3 공유용 이미지
- **요약 카드:** 주요 결과를 요약한 카드 이미지
- **점수 비교:** 전후 점수 비교 이미지
- **브랜딩:** 로고 및 워터마크 포함
- **SNS 최적화:** 각 SNS 플랫폼에 맞는 크기

---

## 3. 기술 설계

### 3.1 공유용 이미지 생성
1. **템플릿 기반 생성:** 미리 정의된 템플릿 사용
2. **동적 콘텐츠:** 분석 결과 동적 삽입
3. **이미지 라이브러리:** Pillow (Python) 또는 Canvas (Flutter)
4. **캐싱:** 생성된 이미지 캐싱
5. **다양한 크기:** SNS 플랫폼별 최적 크기

### 3.2 PDF 생성
1. **PDF 라이브러리:** ReportLab (Python) 또는 pdf (Flutter)
2. **템플릿:** PDF 템플릿 설계
3. **동적 콘텐츠:** 분석 결과 동적 삽입
4. **차트 생성:** 점수 차트 이미지 생성 및 삽입
5. **브랜딩:** 로고 및 스타일 적용
6. **암호화:** 선택적 PDF 암호화

### 3.3 공용 링크 생성
1. **고유 링크 생성:** 분석 결과별 고유 링크
2. **만료 설정:** 링크 만료 기간 설정 (예: 7일)
3. **액세스 제어:** 비밀번호 또는 로그인 요구
4. **링크 추적:** 링크 클릭 통계 추적

### 3.4 데이터 모델 설계

#### 3.4.1 공유 링크 테이블 (share_links)
```sql
CREATE TABLE share_links (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    share_token TEXT NOT NULL UNIQUE,         -- 공유 토큰
    link_type TEXT NOT NULL,                  -- sns, pdf, public
    expires_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES analyses(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_share_links_token ON share_links(share_token);
CREATE INDEX idx_share_links_job ON share_links(job_id);
```

#### 3.4.2 공유 통계 테이블 (share_statistics)
```sql
CREATE TABLE share_statistics (
    id TEXT PRIMARY KEY,
    share_link_id TEXT NOT NULL,
    platform TEXT,                            -- instagram, facebook, etc.
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_agent TEXT,
    ip_address TEXT,
    FOREIGN KEY (share_link_id) REFERENCES share_links(id)
);

CREATE INDEX idx_share_statistics_link ON share_statistics(share_link_id);
CREATE INDEX idx_share_statistics_platform ON share_statistics(platform);
```

### 3.5 API 엔드포인트

#### 3.5.1 공유용 이미지 생성
- **경로:** `/v1/sharing/{job_id}/share-image`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "template": "summary",
  "platform": "instagram"
}
```
- **응답:**
```json
{
  "image_base64": "string",
  "image_url": "string",
  "template": "summary",
  "platform": "instagram"
}
```

#### 3.5.2 PDF 보고서 생성
- **경로:** `/v1/sharing/{job_id}/pdf`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "include_images": true,
  "include_prescription": true,
  "language": "ko"
}
```
- **응답:**
```json
{
  "pdf_base64": "string",
  "pdf_url": "string",
  "download_url": "string"
}
```

#### 3.5.3 공용 링크 생성
- **경로:** `/v1/sharing/{job_id}/public-link`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "expires_in_days": 7,
  "password": "string"
}
```
- **응답:**
```json
{
  "share_token": "string",
  "public_url": "https://skinlens.app/share/abc123",
  "expires_at": "2026-05-31T00:00:00Z",
  "qr_code_base64": "string"
}
```

#### 3.5.4 공용 링크 조회
- **경로:** `/v1/sharing/public/{share_token}`
- **메서드:** `GET`
- **응답:**
```json
{
  "job_id": "string",
  "analysis_result": {},
  "is_expired": false
}
```

#### 3.5.5 공유 통계 조회
- **경로:** `/v1/sharing/{job_id}/statistics`
- **메서드:** `GET`
- **응답:**
```json
{
  "total_access": 100,
  "by_platform": {
    "instagram": 40,
    "facebook": 30,
    "twitter": 20,
    "kakao": 10
  },
  "daily_access": [
    {
      "date": "2026-05-24",
      "count": 20
    }
  ]
}
```

### 3.6 클라이언트 구현

#### 3.6.1 Flutter SNS 공유
1. **share_plus:** SNS 공유 플러그인
2. **url_launcher:** 링크 열기
3. **qr_flutter:** QR 코드 생성
4. **image_gallery_saver:** 이미지 저장

#### 3.6.2 공유 UI
- **공유 버튼:** 분석 결과 화면에 공유 버튼
- **공유 옵션:** SNS 플랫폼 선택
- **PDF 다운로드:** PDF 다운로드 버튼
- **공용 링크:** 링크 복사 및 QR 코드
- **공유 통계:** 공유 통계 화면

#### 3.6.3 공유용 이미지 템플릿
- **요약 카드:** 주요 결과 요약
- **점수 차트:** 점수 비교 차트
- **전후 비교:** 복원 전후 비교
- **브랜딩:** 로고 및 워터마크

---

## 4. 구현 단계

### 4.1 백엔드 이미지 생성 (2일)
- 공유용 이미지 템플릿 설계
- 이미지 생성 서비스 구현
- 다양한 크기 지원
- 이미지 캐싱 구현

### 4.2 백엔드 PDF 생성 (2일)
- PDF 템플릿 설계
- PDF 생성 서비스 구현
- 차트 생성 및 삽입
- 다국어 지원

### 4.3 데이터베이스 스키마 확장 (0.5일)
- `share_links` 테이블 생성
- `share_statistics` 테이블 생성
- 인덱스 생성

### 4.4 백엔드 API 엔드포인트 (1.5일)
- 공유용 이미지 엔드포인트 구현
- PDF 생성 엔드포인트 구현
- 공용 링크 엔드포인트 구현
- 공유 통계 엔드포인트 구현

### 4.5 클라이언트 공유 기능 (2일)
- SNS 공유 통합
- PDF 다운로드 구현
- 공용 링크 생성 구현
- QR 코드 생성 구현

### 4.6 클라이언트 UI (1.5일)
- 공유 버튼 구현
- 공유 옵션 UI 구현
- 공유 통계 화면 구현
- API 연동

### 4.7 API 문서 업데이트 (0.5일)
- 공유 엔드포인트 문서화
- 데이터 구조 문서화

### 4.8 테스트 및 디버깅 (2일)
- 이미지 생성 테스트
- PDF 생성 테스트
- SNS 공유 테스트
- 공용 링크 테스트
- 다양한 플랫폼 테스트

**총 예상 소요 시간: 12일**

---

## 5. 성능 고려사항

- **이미지 생성 시간:** 2초 이내
- **PDF 생성 시간:** 5초 이내
- **이미지 캐싱:** 생성된 이미지 캐싱
- **PDF 캐싱:** 생성된 PDF 캐싱
- **CDN 활용:** 공유용 이미지 CDN 배포
- **링크 만료:** 만료된 링크 정기적 정리

---

## 6. 성공 지표

- **공유율:** 분석 결과의 15% 이상 공유
- **SNS별 공유 비율:** Instagram 40%, Facebook 30%, KakaoTalk 20%, 기타 10%
- **PDF 다운로드율:** 분석 결과의 10% 이상 다운로드
- **공유 링크 클릭률:** 공유 링크의 30% 이상 클릭
- **바이럴 효과:** 공유를 통한 신규 사용자 유입 +25%
- **사용자 만족도:** 공유 기능 도입 후 만족도 +10%
