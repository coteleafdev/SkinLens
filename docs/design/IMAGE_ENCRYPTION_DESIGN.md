# 이미지 암호화 설계 (Image Encryption Design)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

이 문서는 클라이언트 단계에서 이미지 암호화 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 이미지 일반 저장 (암호화 없음)
- 서버에 원본 이미지 전송
- 개인정보 유출 위험
- 규제 준수 부족

### 1.2 제안된 기능
- 클라이언트 단계 이미지 암호화
- 암호화된 이미지 서버 전송
- 사용자별 암호화 키 관리
- 분석 시 복호화
- 선택적 암호화 (사용자 옵션)

### 1.3 기대 효과
- 개인정보 보호 강화
- 데이터 유출 방지
- 규제 준수 (GDPR, CCPA 등)
- 사용자 신뢰도 향상

---

## 2. 암호화 아키텍처

### 2.1 암호화 방식
1. **대칭키 암호화:** AES-256-GCM 사용
2. **키 관리:** 사용자별 고유 키
3. **키 파생:** PBKDF2 또는 Argon2 사용
4. **키 교환:** Diffie-Hellman 또는 ECDH (선택 사항)

### 2.2 암호화 흐름
1. **클라이언트:** 이미지 캡처
2. **암호화:** 클라이언트에서 이미지 암호화
3. **전송:** 암호화된 이미지 서버 전송
4. **저장:** 암호화된 이미지 서버 저장
5. **복호화:** 분석 시 서버에서 복호화
6. **분석:** 복호화된 이미지로 분석
7. **삭제:** 분석 후 암호화된 이미지 유지 또는 삭제

### 2.3 키 관리 전략
1. **사용자 키:** 사용자별 고유 암호화 키
2. **키 저장:** 클라이언트 보안 저장소 (Keychain/Keystore)
3. **키 백업:** 선택적 키 백업 (암호화된 형태)
4. **키 갱신:** 주기적 키 갱신 (선택 사항)
5. **키 삭제:** 계정 삭제 시 키 삭제

### 2.4 보안 고려사항
- **클라이언트 암호화:** 서버에 원본 이미지 전송 안 함
- **키 보호:** 키는 클라이언트 보안 저장소에 저장
- **전송 암호화:** HTTPS로 전송
- **솔트 사용:** 키 파생 시 솔트 사용
- **IV 사용:** 각 암호화에 고유 IV 사용

---

## 3. 기술 설계

### 3.1 암호화 알고리즘
- **알고리즘:** AES-256-GCM
- **키 길이:** 256비트
- **IV 길이:** 96비트 (12바이트)
- **인증 태그:** 128비트 (16바이트)
- **모드:** GCM (Galois/Counter Mode) - 기밀성 + 무결성

### 3.2 키 파생
- **알고리즘:** PBKDF2 또는 Argon2
- **입력:** 사용자 비밀번호 또는 랜덤 시드
- **솔트:** 랜덤 솔트 (16바이트)
- **반복 횟수:** PBKDF2: 100,000회, Argon2: 메모리 64MB, 시간 3회
- **출력:** 256비트 키

### 3.3 암호화 프로세스
1. 이미지를 바이트로 변환
2. 랜덤 IV 생성
3. AES-256-GCM으로 암호화
4. 암호화된 데이터 + IV + 인증 태그 결합
5. Base64로 인코딩 (선택 사항)
6. 서버 전송

### 3.4 복호화 프로세스
1. 암호화된 데이터 수신
2. Base64 디코딩 (선택 사항)
3. IV, 인증 태그, 암호화된 데이터 분리
4. AES-256-GCM으로 복호화
5. 인증 태그 검증
6. 원본 이미지 복원

### 3.5 데이터 모델 설계

#### 3.5.1 암호화 테이블 (encryption_keys)
```sql
CREATE TABLE encryption_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    key_salt BLOB NOT NULL,                   -- 키 파생 솔트
    key_version INTEGER DEFAULT 1,           -- 키 버전
    algorithm TEXT DEFAULT 'AES-256-GCM',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_encryption_keys_user ON encryption_keys(user_id);
```

#### 3.5.2 암호화된 이미지 메타데이터
기존 `analyses` 테이블 확장:
```sql
ALTER TABLE analyses ADD COLUMN is_encrypted BOOLEAN DEFAULT FALSE;
ALTER TABLE analyses ADD COLUMN encryption_key_version INTEGER;
ALTER TABLE analyses ADD COLUMN encryption_iv BLOB;
```

### 3.6 API 엔드포인트

#### 3.6.1 암호화 키 등록
- **경로:** `/v1/encryption/register-key`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "key_salt_base64": "string",
  "key_version": 1,
  "algorithm": "AES-256-GCM"
}
```
- **응답:**
```json
{
  "id": "string",
  "key_version": 1,
  "status": "registered"
}
```

#### 3.6.2 암호화된 이미지 업로드
- **경로:** `/v1/jobs/create`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "image_encrypted_base64": "string",
  "encryption_iv_base64": "string",
  "encryption_key_version": 1,
  "is_encrypted": true
}
```
- **응답:**
```json
{
  "job_id": "string",
  "status": "created"
}
```

#### 3.6.3 암호화 설정 조회
- **경로:** `/v1/encryption/settings`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`
- **응답:**
```json
{
  "is_encryption_enabled": true,
  "key_version": 1,
  "algorithm": "AES-256-GCM"
}
```

#### 3.6.4 암호화 설정 업데이트
- **경로:** `/v1/encryption/settings`
- **메서드:** `PUT`
- **요청 바디:**
```json
{
  "user_id": "string",
  "is_encryption_enabled": true
}
```
- **응답:**
```json
{
  "status": "updated"
}
```

### 3.7 클라이언트 구현

#### 3.7.1 Flutter 암호화
1. **encrypt:** AES 암호화 패키지
2. **flutter_secure_storage:** 보안 저장소
3. **crypto:** 암호화 유틸리티

#### 3.7.2 키 관리
- **키 생성:** 랜덤 키 생성 또는 비밀번호 기반 키 파생
- **키 저장:** flutter_secure_storage에 저장
- **키 로드:** 저장된 키 로드
- **키 삭제:** 계정 삭제 시 키 삭제

#### 3.7.3 암호화 UI
- **암호화 설정:** 암호화 활성화/비활성화 토글
- **암호화 상태:** 현재 암호화 상태 표시
- **키 관리:** 키 재설정 옵션
- **보안 알림:** 암호화 관련 보안 알림

---

## 4. 구현 단계

### 4.1 백엔드 암호화 지원 (2일)
- 암호화된 이미지 수신 로직 구현
- 복호화 로직 구현
- 암호화 키 관리 로직 구현
- 데이터베이스 스키마 확장

### 4.2 데이터베이스 스키마 확장 (0.5일)
- `encryption_keys` 테이블 생성
- `analyses` 테이블 확장
- 인덱스 생성

### 4.3 백엔드 API 엔드포인트 (1일)
- 암호화 키 등록 엔드포인트 구현
- 암호화된 이미지 업로드 지원
- 암호화 설정 엔드포인트 구현

### 4.4 백엔드 보안 (1일)
- 복호화 로직 보안 검증
- 키 관리 보안 검증
- 에러 처리 구현
- 로깅 구현

### 4.5 클라이언트 암호화 (2일)
- AES-256-GCM 암호화 구현
- 키 파생 구현
- 키 저장 구현
- 암호화/복호화 테스트

### 4.6 클라이언트 UI (1일)
- 암호화 설정 UI 구현
- 암호화 상태 표시 구현
- 키 관리 UI 구현
- API 연동

### 4.7 API 문서 업데이트 (0.5일)
- 암호화 엔드포인트 문서화
- 데이터 구조 문서화
- 보안 가이드 문서화

### 4.8 테스트 및 디버깅 (2일)
- 암호화/복호화 테스트
- 키 관리 테스트
- 보안 테스트
- 성능 테스트
- 다양한 이미지 크기 테스트

**총 예상 소요 시간: 10일**

---

## 5. 성능 고려사항

- **암호화 시간:** 5MB 이미지 기준 1초 이내
- **복호화 시간:** 5MB 이미지 기준 1초 이내
- **키 파생 시간:** 0.5초 이내
- **메모리 사용:** 암호화 시 메모리 사용량 최적화
- **배터리 소모:** 암호화 배터리 소모 최적화
- **암호화 선택적:** 사용자가 암호화 선택 가능 (성능 우선 시)

---

## 6. 성공 지표

- **암호화 성공률:** 99% 이상
- **복호화 성공률:** 99% 이상
- **암호화 사용률:** 사용자의 70% 이상 암호화 사용

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (v1.0에서 마이그레이션) | Cascade |
| 0.1.0 | 2026-05-24 | 이미지 암호화 설계 문서 초기 작성 | Cascade |
