# 푸시 알림 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 분석 완료 시 푸시 알림 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 결과 조회 필요 (수동 확인)
- 분석 완료 시 알림 없음
- 사용자 편의성 낮음
- 실시간 알림 미지원

### 1.2 제안된 기능
- 분석 완료 시 푸시 알림
- 다양한 알림 유형 지원
- 알림 설정 관리
- 알림 히스토리
- 알림 클릭 시 앱 이동

### 1.3 기대 효과
- 사용자 편의성 향상
- 실시간 결과 확인
- 사용자 참여도 증가
- 앱 사용 빈도 증가

---

## 2. 알림 유형

### 2.1 분석 완료 알림
- **트리거:** 분석 작업 완료 시
- **내용:** "피부 분석이 완료되었습니다. 결과를 확인하세요."
- **액션:** 클릭 시 분석 결과 화면으로 이동

### 2.2 처방 생성 완료 알림
- **트리거:** 처방 생성 완료 시
- **내용:** "맞춤형 처방이 생성되었습니다."
- **액션:** 클릭 시 처방 화면으로 이동

### 2.3 복원 완료 알림
- **트리거:** 이미지 복원 완료 시
- **내용:** "이미지 복원이 완료되었습니다."
- **액션:** 클릭 시 복원 결과 화면으로 이동

### 2.4 리마인더 알림 (선택 사항)
- **트리거:** 정기적 분석 리마인더
- **내용:** "지난 분석으로부터 30일이 지났습니다. 새로운 분석을 진행해보세요."
- **액션:** 클릭 시 분석 시작 화면으로 이동

### 2.5 마케팅 알림 (선택 사항)
- **트리거:** 새로운 기능, 이벤트 등
- **내용:** "새로운 기능이 추가되었습니다."
- **액션:** 클릭 시 해당 기능 화면으로 이동

---

## 3. 기술 설계

### 3.1 푸시 알림 아키텍처
1. **FCM (Firebase Cloud Messaging):** Android 푸시 알림
2. **APNs (Apple Push Notification Service):** iOS 푸시 알림
3. **토큰 관리:** 디바이스 토큰 저장 및 관리
4. **알림 서비스:** 알림 전송 서비스
5. **알림 큐:** 알림 전송 큐 (비동기 처리)

### 3.2 데이터 모델 설계

#### 3.2.1 디바이스 토큰 테이블 (device_tokens)
```sql
CREATE TABLE device_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token TEXT NOT NULL,
    platform TEXT NOT NULL,                   -- ios, android
    app_version TEXT,
    os_version TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_device_tokens_user ON device_tokens(user_id);
CREATE INDEX idx_device_tokens_token ON device_tokens(token);
```

#### 3.2.2 알림 히스토리 테이블 (notification_history)
```sql
CREATE TABLE notification_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    notification_type TEXT NOT NULL,          -- analysis_complete, prescription_complete, etc.
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    data JSON,                                 -- 추가 데이터 (job_id 등)
    status TEXT DEFAULT 'sent',               -- sent, failed, clicked
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    clicked_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_notification_history_user ON notification_history(user_id);
CREATE INDEX idx_notification_history_type ON notification_history(notification_type);
CREATE INDEX idx_notification_history_sent ON notification_history(sent_at);
```

#### 3.2.3 알림 설정 테이블 (notification_settings)
```sql
CREATE TABLE notification_settings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    analysis_complete BOOLEAN DEFAULT TRUE,
    prescription_complete BOOLEAN DEFAULT TRUE,
    restoration_complete BOOLEAN DEFAULT TRUE,
    reminder BOOLEAN DEFAULT FALSE,
    marketing BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_notification_settings_user ON notification_settings(user_id);
```

### 3.3 토큰 관리
1. **토큰 등록:** 앱 시작 시 또는 토큰 변경 시 서버에 등록
2. **토큰 갱신:** 토큰 만료 시 자동 갱신
3. **토큰 삭제:** 로그아웃 시 토큰 삭제
4. **토큰 비활성화:** 유효하지 않은 토큰 비활성화

### 3.4 알림 전송 로직
1. 이벤트 발생 (분석 완료 등)
2. 사용자 알림 설정 확인
3. 사용자 디바이스 토큰 조회
4. 알림 메시지 생성
5. FCM/APNs로 알림 전송
6. 전송 결과 저장
7. 실패 시 재시도 로직

### 3.5 API 엔드포인트

#### 3.5.1 디바이스 토큰 등록
- **경로:** `/v1/notifications/register-token`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "token": "string",
  "platform": "ios",
  "app_version": "1.0.0",
  "os_version": "iOS 15.0"
}
```
- **응답:**
```json
{
  "id": "string",
  "status": "registered"
}
```

#### 3.5.2 디바이스 토큰 삭제
- **경로:** `/v1/notifications/unregister-token`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "token": "string"
}
```
- **응답:**
```json
{
  "status": "unregistered"
}
```

#### 3.5.3 알림 설정 조회
- **경로:** `/v1/notifications/settings`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`
- **응답:**
```json
{
  "analysis_complete": true,
  "prescription_complete": true,
  "restoration_complete": true,
  "reminder": false,
  "marketing": false
}
```

#### 3.5.4 알림 설정 업데이트
- **경로:** `/v1/notifications/settings`
- **메서드:** `PUT`
- **요청 바디:**
```json
{
  "user_id": "string",
  "analysis_complete": true,
  "prescription_complete": true,
  "restoration_complete": false,
  "reminder": false,
  "marketing": false
}
```
- **응답:**
```json
{
  "status": "updated"
}
```

#### 3.5.5 알림 히스토리 조회
- **경로:** `/v1/notifications/history`
- **메서드:** `GET`
- **쿼리 파라미터:** `user_id`, `limit`, `offset`
- **응답:**
```json
{
  "notifications": [
    {
      "id": "string",
      "notification_type": "analysis_complete",
      "title": "피부 분석 완료",
      "body": "피부 분석이 완료되었습니다.",
      "data": {
        "job_id": "string"
      },
      "status": "clicked",
      "sent_at": "2026-05-24T00:00:00Z",
      "clicked_at": "2026-05-24T00:01:00Z"
    }
  ],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

### 3.6 클라이언트 구현

#### 3.6.1 Flutter 푸시 알림
1. **firebase_messaging:** FCM 토큰 관리 및 알림 수신
2. **flutter_local_notifications:** 로컬 알림 표시
3. **토큰 등록:** 앱 시작 시 토큰 서버에 등록
4. **알림 핸들러:** 알림 클릭 시 앱 내 이동

#### 3.6.2 알림 설정 UI
- **알림 설정 화면:** 각 알림 유형별 토글 버튼
- **설정 저장:** 설정 변경 시 서버에 동기화
- **설정 불러오기:** 앱 시작 시 설정 불러오기

#### 3.6.3 알림 히스토리 UI
- **알림 히스토리 화면:** 과거 알림 목록 표시
- **알림 상태:** 전송, 클릭 상태 표시
- **알림 삭제:** 오래된 알림 삭제 기능

---

## 4. 구현 단계

### 4.1 백엔드 푸시 알림 서비스 (3일)
- FCM/APNs 통합
- 토큰 관리 로직 구현
- 알림 전송 서비스 구현
- 알림 큐 구현
- 재시도 로직 구현

### 4.2 데이터베이스 스키마 확장 (0.5일)
- `device_tokens` 테이블 생성
- `notification_history` 테이블 생성
- `notification_settings` 테이블 생성
- 인덱스 생성

### 4.3 백엔드 API 엔드포인트 (1일)
- 토큰 등록/삭제 엔드포인트 구현
- 알림 설정 엔드포인트 구현
- 알림 히스토리 엔드포인트 구현

### 4.4 백엔드 이벤트 통합 (1일)
- 분석 완료 이벤트에 알림 전송 통합
- 처방 생성 완료 이벤트에 알림 전송 통합
- 복원 완료 이벤트에 알림 전송 통합

### 4.5 클라이언트 푸시 알림 (2일)
- FCM/APNs 통합
- 토큰 등록 로직 구현
- 알림 수신 핸들러 구현
- 알림 클릭 핸들러 구현

### 4.6 클라이언트 UI (1.5일)
- 알림 설정 화면 구현
- 알림 히스토리 화면 구현
- API 연동

### 4.7 API 문서 업데이트 (0.5일)
- 푸시 알림 엔드포인트 문서화
- 데이터 구조 문서화

### 4.8 테스트 및 디버깅 (2일)
- 토큰 등록 테스트
- 알림 전송 테스트
- 알림 클릭 테스트
- 알림 설정 테스트
- iOS/Android 플랫폼 테스트

**총 예상 소요 시간: 11.5일**

---

## 5. 성능 고려사항

- **알림 전송 지연:** 알림 전송 지연 1초 이내
- **알림 큐:** 대량 알림 전송 시 큐 사용
- **배치 전송:** 대량 사용자에게 알림 전송 시 배치 처리
- **토큰 관리:** 유효하지 않은 토큰 정기적 정리
- **알림 제한:** 과도한 알림 전송 방지 (예: 하루 10회 제한)

---

## 6. 성공 지표

- **알림 전송 성공률:** 95% 이상
- **알림 클릭률:** 30% 이상
- **알림 설정 사용률:** 사용자의 50% 이상 알림 설정 변경
- **앱 사용 빈도:** 푸시 알림 도입 후 앱 사용 빈도 +20%
- **사용자 만족도:** 푸시 알림 도입 후 만족도 +10%
