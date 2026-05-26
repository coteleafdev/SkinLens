# 오프라인 모드 설계 문서

> **프로젝트:** SkinLens v1.0
> **작성일:** 2026-05-24
> **버전:** 1.0

이 문서는 오프라인 환경에서 기본 분석을 가능하게 하는 오프라인 모드 기능의 기술 설계를 설명합니다.

---

## 1. 개요

### 1.1 현재 상황
- 항상 온라인 연결 필요
- 네트워크 불안정 환경에서 사용 불가
- 서버 다운시 서비스 중단
- 데이터 로컬 저장 안 됨

### 1.2 제안된 기능
- 오프라인 기본 분석 지원
- 로컬 모델 캐싱
- 데이터 오프라인 저장
- 온라인 시 데이터 동기화
- 네트워크 상태 감지

### 1.3 기대 효과
- 네트워크 불안정 환경 대응
- 서비스 가용성 향상
- 사용자 경험 개선
- 데이터 손실 방지

---

## 2. 오프라인 기능 범위

### 2.1 오프라인 지원 기능
- **기본 피부 분석:** 로컬 모델로 기본 피부 상태 분석
- **이미지 캡처 및 저장:** 분석할 이미지 로컬 저장
- **분석 결과 로컬 저장:** 오프라인 분석 결과 로컬 저장
- **과거 결과 조회:** 로컬에 저장된 과거 분석 결과 조회
- **데이터 동기화:** 온라인 시 서버와 데이터 동기화

### 2.2 오프라인 미지원 기능
- **고급 분석:** 서버 전용 고급 분석 모델
- **복원:** 고성능 복원 엔진 (서버 GPU 필요)
- **제품 추천:** 실시간 제품 데이터베이스 조회 필요
- **처방 생성:** 복잡한 처방 알고리즘 (서버 필요)
- **LLM 소견:** 대규모 LLM 모델 (서버 필요)

---

## 3. 기술 설계

### 3.1 로컬 모델 아키텍처
1. **경량 모델:** 모바일 디바이스에서 실행 가능한 경량 모델
2. **모델 캐싱:** 온라인 시 모델 다운로드 및 로컬 캐싱
3. **모델 업데이트:** 주기적 모델 업데이트 확인
4. **모델 버전 관리:** 여러 모델 버전 관리

### 3.2 지원할 로컬 모델
- **MediaPipe Face Mesh:** 얼굴 랜드마크 추출 (경량)
- **경량 피부 분석 모델:** 기본 피부 상태 분석 (TensorFlow Lite)
- **간단한 분류 모델:** 피부 타입 분류 (LightGBM 또는 TensorFlow Lite)

### 3.3 데이터 동기화 전략
1. **오프라인 데이터 저장:** 로컬 데이터베이스 (SQLite)에 저장
2. **동기화 큐:** 동기화 필요한 데이터 큐에 저장
3. **충돌 해결:** 타임스탬프 기반 충돌 해결
4. **증분 동기화:** 변경된 데이터만 동기화
5. **배치 동기화:** 대량 데이터 배치 동기화

### 3.4 네트워크 상태 감지
1. **네트워크 연결 감지:** periodic ping 또는 connectivity_plus
2. **온라인/오프라인 모드 전환:** 자동 전환
3. **사용자 알림:** 네트워크 상태 변경 시 사용자 알림
4. **동기화 트리거:** 온라인 시 자동 동기화

### 3.5 데이터 모델 설계

#### 3.5.1 로컬 데이터베이스 (SQLite)
```sql
-- 로컬 분석 결과 테이블
CREATE TABLE local_analyses (
    id TEXT PRIMARY KEY,
    job_id TEXT,                              -- 서버 동기화 후 할당
    image_path TEXT NOT NULL,                 -- 로컬 이미지 경로
    analysis_result JSON NOT NULL,            -- 분석 결과
    is_synced BOOLEAN DEFAULT FALSE,          -- 서버 동기화 여부
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    synced_at TIMESTAMP
);

-- 동기화 큐 테이블
CREATE TABLE sync_queue (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,                -- analysis, feedback, etc.
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,                    -- create, update, delete
    data JSON NOT NULL,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 모델 버전 테이블
CREATE TABLE model_versions (
    id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    file_path TEXT NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.6 API 엔드포인트

#### 3.6.1 동기화 요청
- **경로:** `/v3/sync`
- **메서드:** `POST`
- **요청 바디:**
```json
{
  "user_id": "string",
  "local_analyses": [
    {
      "id": "string",
      "image_base64": "string",
      "analysis_result": {}
    }
  ],
  "last_sync_timestamp": "2026-05-24T00:00:00Z"
}
```
- **응답:**
```json
{
  "synced_analyses": [
    {
      "local_id": "string",
      "job_id": "string",
      "status": "synced"
    }
  ],
  "server_analyses": [
    {
      "job_id": "string",
      "analysis_result": {}
    }
  ],
  "model_updates": [
    {
      "model_name": "skin_analyzer",
      "version": "1.2.0",
      "download_url": "string"
    }
  ]
}
```

#### 3.6.2 모델 다운로드
- **경로:** `/v3/models/{model_name}/download`
- **메서드:** `GET`
- **쿼리 파라미터:** `version`
- **응답:** 모델 파일 (바이너리)

#### 3.6.3 모델 버전 조회
- **경로:** `/v3/models/versions`
- **메서드:** `GET`
- **응답:**
```json
{
  "models": [
    {
      "name": "skin_analyzer",
      "latest_version": "1.2.0",
      "min_compatible_version": "1.0.0",
      "size_mb": 50
    }
  ]
}
```

### 3.7 클라이언트 아키텍처

#### 3.7.1 Flutter 오프라인 지원
1. **connectivity_plus:** 네트워크 상태 감지
2. **sqflite:** 로컬 데이터베이스
3. **path_provider:** 로컬 파일 저장
4. **tflite_flutter:** TensorFlow Lite 모델 실행
5. **dio:** HTTP 요청 (오프라인 캐싱 지원)

#### 3.7.2 오프라인 모드 UI
- **네트워크 상태 표시:** 상단 바에 온라인/오프라인 상태 표시
- **오프라인 배너:** 오프라인 시 배너 표시
- **기능 제한 표시:** 오프라인 미지원 기능 비활성화
- **동기화 버튼:** 수동 동기화 버튼
- **동기화 진행률:** 동기화 진행률 표시

---

## 4. 구현 단계

### 4.1 로컬 모델 준비 (3일)
- 경량 피부 분석 모델 개발
- TensorFlow Lite로 모델 변환
- 모델 성능 최적화
- 모델 테스트

### 4.2 백엔드 개발 (2일)
- 동기화 API 엔드포인트 구현
- 모델 다운로드 엔드포인트 구현
- 모델 버전 관리 시스템 구현
- 데이터 병합 로직 구현

### 4.3 클라이언트 로컬 데이터베이스 (1일)
- SQLite 데이터베이스 구현
- 로컬 분석 결과 저장 로직 구현
- 동기화 큐 구현

### 4.4 클라이언트 오프라인 분석 (3일)
- 로컬 모델 통합
- 오프라인 분석 파이프라인 구현
- 로컬 이미지 처리 구현

### 4.5 클라이언트 동기화 (2일)
- 네트워크 상태 감지 구현
- 자동 동기화 로직 구현
- 수동 동기화 UI 구현
- 충돌 해결 로직 구현

### 4.6 클라이언트 UI 개발 (2일)
- 네트워크 상태 표시 구현
- 오프라인 배너 구현
- 기능 제한 표시 구현
- 동기화 진행률 표시 구현

### 4.7 API 문서 업데이트 (0.5일)
- 동기화 엔드포인트 문서화
- 모델 다운로드 엔드포인트 문서화

### 4.8 테스트 및 디버깅 (3일)
- 오프라인 분석 테스트
- 동기화 테스트
- 충돌 해결 테스트
- 네트워크 전환 테스트
- 성능 테스트

**총 예상 소요 시간: 16.5일**

---

## 5. 성능 고려사항

- **로컬 모델 크기:** 모델 크기 최적화 (50MB 이하)
- **로컬 분석 시간:** 모바일 디바이스에서 5초 이내
- **동기화 효율:** 증분 동기화로 데이터 전송 최소화
- **배터리 소모:** 로컬 분석 배터리 소모 최적화
- **저장 공간:** 로컬 데이터 저장 공간 최적화

---

## 6. 성공 지표

- **오프라인 분석 성공률:** 95% 이상
- **로컬 분석 시간:** 5초 이내
- **동기화 성공률:** 99% 이상
- **데이터 손실률:** 0.1% 이하
- **오프라인 모드 사용률:** 전체 사용의 20% 이상
- **사용자 만족도:** 오프라인 모드 도입 후 만족도 +15%
