# 장애 대응 가이드 (Incident Response Guide)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.6  
> **작성일:** 2026-05-30  
*상태:* 초안

---

## 개요

이 가이드는 SkinLens 시스템 장애 발생 시 대응 절차를 설명합니다.

---

## 장애 등급

### P0 (Critical)

- **정의:** 서비스 완전 중단
- **예시:** 서버 다운, 데이터베이스 장애
- **대응 시간:** 15분 내
- **복구 목표:** 1시간 내

### P1 (High)

- **정의:** 주요 기능 장애
- **예시:** 분석 불가, 이미지 업로드 실패
- **대응 시간:** 30분 내
- **복구 목표:** 4시간 내

### P2 (Medium)

- **정의:** 부분 기능 장애
- **예시:** LLM API 느림, 일부 메트릭 수집 안됨
- **대응 시간:** 2시간 내
- **복구 목표:** 24시간 내

### P3 (Low)

- **정의:** 사소한 문제
- **예시:** 로그 포맷 오류, UI 버그
- **대응 시간:** 영업일 내
- **복구 목표:** 1주 내

---

## 장애 대응 절차

### 1. 장애 감지

**자동 감지:**
- Prometheus 알림
- Health Check 실패
- 에러율 상승

**수동 감지:**
- 사용자 신고
- 정기 점검

### 2. 장애 분류

**질문:**
1. 서비스가 중단되었는가?
2. 주요 기능이 작동하지 않는가?
3. 사용자 영향도는?
4. 장애 등급은?

### 3. 대응 팀 소집

**P0/P1:**
- 즉시 온콜 호출
- 개발팀, 운영팀, 관리자 참여

**P2/P3:**
- 이메일/Slack 알림
- 영업일 내 대응

### 4. 장애 완화

**즉시 조치:**
- 서비스 재시작
- 롤백 수행
- 트래픽 차단

**임시 조치:**
- 대기 서버로 전환
- 기능 비활성화
- 용량 증설

### 5. 근본 원인 분석

**질문:**
1. 언제부터 발생했는가?
2. 무엇이 변경되었는가?
3. 로그에 무엇이 있는가?
4. 재현 가능한가?

### 6. 영구적 해결

**조치:**
- 버그 수정
- 설정 변경
- 아키텍처 개선
- 테스트 추가

### 7. 사후 분석

**내용:**
- 장애 개요
- 타임라인
- 근본 원인
- 대응 조치
- 개선 계획

---

## 일반적인 장애 시나리오

### 시나리오 1: 서버 다운

**증상:**
- Health Check 실패
- API 응답 없음
- Prometheus 알림

**대응:**
1. 서버 상태 확인: `ssh server`
2. 로그 확인: `docker logs skinlens`
3. 서비스 재시작: `docker-compose restart`
4. 실패 시 롤백: `docker-compose down && docker-compose up -d --scale skinlens=2`

### 시나리오 2: 데이터베이스 장애

**증상:**
- DB 연결 에러
- 쿼리 타임아웃
- 데이터 저장 실패

**대응:**
1. DB 상태 확인: `systemctl status postgresql`
2. 로그 확인: `tail -f /var/log/postgresql/postgresql.log`
3. DB 재시작: `systemctl restart postgresql`
4. 백업 복구: `psql -d skinlens < backup.sql`

### 시나리오 3: GPU 메모리 부족

**증상:**
- CUDA OOM 에러
- 복원 실패
- GPU 사용률 100%

**대응:**
1. GPU 상태 확인: `nvidia-smi`
2. 프로세스 확인: `nvidia-smi pmon`
3. 불필요 프로세스 종료: `kill -9 <pid>`
4. 배치 크기 감소
5. 서버 재시작

### 시나리오 4: LLM API 장애

**증상:**
- LLM 호출 타임아웃
- 소견 생성 실패
- API 키 만료

**대응:**
1. API 상태 확인: `curl https://generativelanguage.googleapis.com/v1/models`
2. API 키 확인: 환경 변수 확인
3. API 키 갱신
4. 재시도 로직 활성화
5. LLM 기능 비활성화 (필요 시)

### 시나리오 5: 디스크 부족

**증상:**
- 파일 저장 실패
- 로그 쓰기 실패
- 디스크 사용률 100%

**대응:**
1. 디스크 확인: `df -h`
2. 오래된 로그 삭제: `find /var/log -name "*.log" -mtime +30 -delete`
3. 오래된 이미지 삭제: `find /data -name "*.png" -mtime +90 -delete`
4. 백업 삭제: `find /backup -name "*.db" -mtime +7 -delete`
5. 용량 증설

---

## 롤백 절차

### 1. Docker 롤백

```bash
# 이전 이미지로 롤백
docker-compose down
docker pull skinlens:previous
docker-compose up -d
```

### 2. 코드 롤백

```bash
# Git 롤백
git log --oneline
git checkout <commit_hash>
docker-compose build
docker-compose up -d
```

### 3. 설정 롤백

```bash
# 설정 파일 복원
cp /backup/config.json /path/to/config.json
docker-compose restart
```

---

## 통신 절차

### 내부 통신

**Slack 채널:**
- `#incidents`: 장애 알림
- `#engineering`: 기술 논의
- `#ops`: 운영 논의

**온콜:**
- P0/P1: 즉시 호출
- P2/P3: 이메일/Slack

### 외부 통신

**고객 통지:**
- P0: 즉시 통지
- P1: 1시간 내 통지
- P2/P3: 정기 업데이트

**통지 내용:**
- 장애 개요
- 영향 범위
- 예상 복구 시간
- 진행 상황

---

## 사후 분석 템플릿

```markdown
# 장애 보고서

## 개요
- **장애 ID:** INC-2026-05-30-001
- **발생 시간:** 2026-05-30 14:00
- **복구 시간:** 2026-05-30 15:30
- **장애 등급:** P1
- **영향 사용자:** 100명

## 타임라인
- 14:00: 장애 감지
- 14:05: 대응 팀 소집
- 14:10: 원인 분석 시작
- 14:30: 임시 조치 완료
- 15:00: 영구적 해결 완료
- 15:30: 서비스 정상화

## 근본 원인
- **원인:** GPU 메모리 부족
- **세부 원인:** 배치 크기 증가로 인한 OOM

## 대응 조치
- **즉시 조치:** 서비스 재시작
- **임시 조치:** 배치 크기 감소
- **영구적 해결:** 메모리 최적화

## 개선 계획
- GPU 메모리 모니터링 강화
- 자동 스케일링 도입
- 배치 크기 동적 조정

## 교훈
- GPU 메모리 모니터링 필요
- 용량 계획 개선 필요
```

---

## 연락처

### 대응 팀

- **개발팀:** dev@skinlens.com
- **운영팀:** ops@skinlens.com
- **관리자:** admin@skinlens.com

### 외부 연락처

- **클라우드 제공자:** AWS/Azure/GCP 지원
- **LLM 제공자:** Google 지원
- **DB 제공자:** PostgreSQL 지원

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
