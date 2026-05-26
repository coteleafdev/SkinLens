# 얼굴 인증 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 얼굴 인증 (생체 인증) 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- JWT 토큰만 사용
- 비밀번호 기반 인증
- 2FA (2단계 인증) 미지원
- 보안 취약성 존재

### 1.2 제안된 기능
- 얼굴 인증 (생체 인증)
- 얼굴 데이터 등록
- 얼굴 인증 로그인
- 생체 인증 + JWT 결합
- 인증 실패 처리

### 1.3 기대 효과
- 보안 강화
- 사용자 편의성 향상
- 비밀번호 없는 로그인
- 계정 보호 강화

---

## 2. 얼굴 인증 아키텍처

### 2.1 인증 방식
1. **얼굴 등록:** 사용자 얼굴 데이터 등록
2. **얼굴 인증:** 로그인 시 얼굴 인증
3. **이중 인증:** 얼굴 인증 + JWT 토큰
4. **폴백:** 얼굴 인증 실패 시 비밀번호 로그인

### 2.2 얼굴 인식 기술
- **MediaPipe Face Mesh:** 얼굴 랜드마크 추출
- **Face Embedding:** 얼굴 특징 벡터 추출
- **유사도 계산:** 등록된 얼굴과 입력 얼굴 유사도 계산
- **임계값:** 인증 성공/실패 결정 임계값

### 2.3 보안 고려사항
- **얼굴 데이터 암호화:** 얼굴 임베딩 데이터 암호화 저장
- **라이브니스 감지:** 실제 얼굴인지 확인 (anti-spoofing)
- **임베딩만 저장:** 원본 이미지 저장 안 함
- **전송 암호화:** HTTPS로 전송
- **속도 제한:** 인증 시도 횟수 제한

---

## 3. 기술 설계

### 3.1 얼굴 등록 프로세스
1. 사용자가 얼굴 등록 요청
2. 여러 각도에서 얼굴 이미지 캡처 (3-5장)
3. 얼굴 랜드마크 추출
4. 얼굴 임베딩 생성
5. 임베딩 평균화
6. 암호화하여 저장
7. 등록 완료

### 3.2 얼굴 인증 프로세스
1. 사용자가 얼굴 인증 요청
2. 얼굴 이미지 캡처
3. 얼굴 랜드마크 추출
4. 얼굴 임베딩 생성
5. 저장된 임베딩과 유사도 계산 (Cosine Similarity)
6. 유사도가 임계값 이상이면 인증 성공
7. JWT 토큰 발급
8. 로그인 완료

### 3.3 라이브니스 감지 (Anti-Spoofing)
1. **눈 깜빡임 감지:** 실제 얼굴인지 확인
2. **머리 움직임 감지:** 3D 얼굴인지 확인
3. **조명 분석:** 사진/비디오 감지
4. **텍스처 분석:** 화면 재생 감지

### 3.4 데이터 모델 설계

#### 3.4.1 얼굴 데이터 테이블 (face_data)
```sql
CREATE TABLE face_data (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    face_embedding BLOB NOT NULL,             -- 암호화된 얼굴 임베딩
    embedding_version TEXT DEFAULT '1.0',     -- 임베딩 모델 버전
    registration_images_count INTEGER DEFAULT 0, -- 등록 시 사용한 이미지 수
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_face_data_user ON face_data(user_id);
```

#### 3.4.2 인증 시도 테이블 (authentication_attempts)
```sql
CREATE TABLE authentication_attempts (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    auth_type TEXT NOT NULL,                  -- face, password, otp
    success BOOLEAN NOT NULL,
    similarity_score REAL,                    -- 얼굴 인증 유사도 점수
    failure_reason TEXT,                      -- 실패 사유
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_authentication_attempts_user ON authentication_attempts(user_id);
CREATE INDEX idx_authentication_attempts_created ON authentication_attempts(created_at);
```

### 3.5 API 엔드포인트

#### 3.5.1 얼굴 등록
- **경로:** `/v3/auth/face/register`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "face_images": [
    {
      "image_base64": "string",
      "angle": "front"
    },
    {
      "image_base64": "string",
      "angle": "left"
    },
    {
      "image_base64": "string",
      "angle": "right"
    }
  ]
}
```
- **응답:**
```json
{
  "status": "registered",
  "embedding_version": "1.0",
  "images_count": 3
}
```

#### 3.5.2 얼굴 인증
- **경로:** `/v3/auth/face/authenticate`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "face_image_base64": "string"
}
```
- **응답:**
```json
{
  "success": true,
  "similarity_score": 0.92,
  "token": "string",
  "refresh_token": "string",
  "user": {
    "id": "string",
    "email": "string"
  }
}
```

#### 3.5.3 얼굴 데이터 삭제
- **경로:** `/v3/auth/face/delete`
- **메서드:** `DELETE`
- **요청 바디:**
```json
{
  "user_id": "string"
}
```
- **응답:**
```json
{
  "status": "deleted"
}
```

#### 3.5.4 인증 시도 히스토리
- **경로:** `/v3/auth/attempts`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`, `limit`, `offset`
- **응답:**
```json
{
  "attempts": [
    {
      "auth_type": "face",
      "success": true,
      "similarity_score": 0.92,
      "created_at": "2026-05-24T00:00:00Z"
    }
  ],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

### 3.6 클라이언트 구현

#### 3.6.1 Flutter 얼굴 인증
1. **camera:** 카메라 접근
2. **google_ml_kit:** ML Kit 얼굴 인식
3. **local_auth:** 생체 인증 (Face ID/Touch ID)
4. **image_picker:** 이미지 선택

#### 3.6.2 얼굴 등록 UI
- **카메라 프리뷰:** 실시간 카메라 프리뷰
- **가이드라인:** 얼굴 위치 가이드라인
- **다중 각도 캡처:** 정면, 좌측, 우측 캡처
- **진행률 표시:** 등록 진행률 표시
- **성공/실패 피드백:** 등록 결과 피드백

#### 3.6.3 얼굴 인증 UI
- **카메라 프리뷰:** 실시간 카메라 프리뷰
- **얼굴 감지:** 얼굴 감지 시 자동 캡처
- **인증 진행률:** 인증 진행률 표시
- **성공/실패 피드백:** 인증 결과 피드백
- **폴백 옵션:** 비밀번호 로그인 옵션

#### 3.6.4 보안 UI
- **얼굴 데이터 관리:** 얼굴 데이터 삭제 옵션
- **인증 히스토리:** 인증 시도 히스토리 조회
- **보안 설정:** 생체 인증 설정

---

## 4. 구현 단계

### 4.1 백엔드 얼굴 인식 (3일)
- 얼굴 임베딩 모델 통합
- 얼굴 등록 로직 구현
- 얼굴 인증 로직 구현
- 유사도 계산 구현
- 라이브니스 감지 구현

### 4.2 데이터베이스 스키마 확장 (0.5일)
- `face_data` 테이블 생성
- `authentication_attempts` 테이블 생성
- 인덱스 생성

### 4.3 백엔드 API 엔드포인트 (1.5일)
- 얼굴 등록 엔드포인트 구현
- 얼굴 인증 엔드포인트 구현
- 얼굴 데이터 삭제 엔드포인트 구현
- 인증 시도 히스토리 엔드포인트 구현

### 4.4 백엔드 보안 (1일)
- 얼굴 데이터 암호화 구현
- 속도 제한 구현
- 인증 실패 처리 구현
- 로그 모니터링 구현

### 4.5 클라이언트 얼굴 인증 (2일)
- 카메라 통합
- 얼굴 감지 구현
- 얼굴 등록 UI 구현
- 얼굴 인증 UI 구현

### 4.6 클라이언트 보안 UI (1일)
- 얼굴 데이터 관리 UI 구현
- 인증 히스토리 UI 구현
- 보안 설정 UI 구현
- API 연동

### 4.7 API 문서 업데이트 (0.5일)
- 얼굴 인증 엔드포인트 문서화
- 데이터 구조 문서화
- 보안 가이드 문서화

### 4.8 테스트 및 디버깅 (2일)
- 얼굴 등록 테스트
- 얼굴 인증 테스트
- 라이브니스 감지 테스트
- 보안 테스트
- 다양한 조건 테스트 (조명, 각도 등)

**총 예상 소요 시간: 11.5일**

---

## 5. 성능 고려사항

- **얼굴 인증 시간:** 2초 이내
- **얼굴 등록 시간:** 10초 이내
- **임베딩 크기:** 128D 또는 256D 벡터
- **유사도 임계값:** 0.8 (조정 가능)
- **속도 제한:** 5분 내 5회 시도 제한
- **암호화:** AES-256 사용

---

## 6. 성공 지표

- **얼굴 인증 성공률:** 95% 이상
- **거짓 수용률 (FAR):** 0.1% 이하
- **거짓 거부률 (FRR):** 5% 이하
- **얼굴 등록 완료율:** 90% 이상
- **얼굴 인증 사용률:** 사용자의 60% 이상 사용
- **보안 사고:** 얼굴 인증 도입 후 보안 사고 0건
- **사용자 만족도:** 얼굴 인증 도입 후 만족도 +15%
