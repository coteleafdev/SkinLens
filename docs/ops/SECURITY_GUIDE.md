# 보안 가이드 (Security Guide)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.6  
> **작성일:** 2026-05-30  
> **상태:** 초안

---

## 개요

SkinLens는 API 키, 데이터베이스 자격증명, 고객 정보 등 민감한 정보를 처리합니다. 안전한 운용을 위한 보안 가이드입니다.

---

## 1. API 키 관리

### 1.1 LLM/서비스 API 키

**현재 구조:**

**LLM API 키 (GEMINI_API_KEY):**
- 서버: 환경변수 `GEMINI_API_KEY`에서만 로드
- 로컬: `config/config.secrets.json`에서 로드
- 보안: 클라이언트 입력 무시, 환경변수만 사용

**Supabase 키:**
- 환경변수 `SUPABASE_URL`, `SUPABASE_KEY`에서 로드
- `config.json`에도 저장 가능 (비권장)

**Telegram 키:**
- 환경변수 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`에서 로드
- `config/config.secrets.json`에서도 로드 가능

### 1.2 API 액세스 키 (새로운 기능)

**기능:**
- 외부 API 액세스를 위한 API 키 관리
- SHA-256 해시로 안전하게 저장
- 만료일 설정 가능
- 권한 범위 (scopes) 지정 가능

**API 엔드포인트:**
- POST `/v3/admin/api-keys` - API 키 생성
- GET `/v3/admin/api-keys` - API 키 목록 조회
- DELETE `/v3/admin/api-keys/{key_id}` - API 키 폐지

**보안 특징:**
- 키는 생성 시 한 번만 반환 (64자 hex 문자열)
- DB에는 SHA-256 해시만 저장
- 만료일 자동 검증
- 폐지된 키는 즉시 무효화
- 사용 로그 기록 (api_key_usage_logs 테이블)

**사용 예시:**
```bash
# API 키 생성
curl -X POST "http://localhost:8000/v3/admin/api-keys?name=TestKey&owner_id=CUST001&scopes=%5B%22read%22%2C%22write%22%5D" \
  -H "Authorization: Bearer <admin_token>"

# 응답 (api_key는 한 번만 표시됨)
{
  "id": "uuid",
  "api_key": "64-char-hex-string",
  "name": "TestKey",
  "owner_id": "CUST001",
  "scopes": ["read", "write"],
  "expires_at": "2026-06-30T10:00:00Z"
}
```

### 1.3 환경변수 사용 (권장)

**Linux/macOS:**
```bash
# 일시적 설정 (현재 세션만)
export GEMINI_API_KEY="your_api_key"
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_KEY="your_service_role_key"
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# 영구적 설정 (~/.bashrc 또는 ~/.zshrc)
echo 'export GEMINI_API_KEY="your_api_key"' >> ~/.bashrc
echo 'export SUPABASE_URL="https://xxx.supabase.co"' >> ~/.bashrc
echo 'export SUPABASE_KEY="your_service_role_key"' >> ~/.bashrc
echo 'export TELEGRAM_BOT_TOKEN="your_bot_token"' >> ~/.bashrc
echo 'export TELEGRAM_CHAT_ID="your_chat_id"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell):**
```powershell
# 일시적 설정 (현재 세션만)
$env:GEMINI_API_KEY="your_api_key"
$env:SUPABASE_URL="https://xxx.supabase.co"
$env:SUPABASE_KEY="your_service_role_key"
$env:TELEGRAM_BOT_TOKEN="your_bot_token"
$env:TELEGRAM_CHAT_ID="your_chat_id"

# 영구적 설정 (시스템 환경변수)
[System.Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'your_api_key', 'User')
[System.Environment]::SetEnvironmentVariable('SUPABASE_URL', 'https://xxx.supabase.co', 'User')
[System.Environment]::SetEnvironmentVariable('SUPABASE_KEY', 'your_service_role_key', 'User')
[System.Environment]::SetEnvironmentVariable('TELEGRAM_BOT_TOKEN', 'your_bot_token', 'User')
[System.Environment]::SetEnvironmentVariable('TELEGRAM_CHAT_ID', 'your_chat_id', 'User')
```

**Windows (CMD):**
```cmd
# 일시적 설정 (현재 세션만)
set GEMINI_API_KEY=your_api_key
set SUPABASE_URL=https://xxx.supabase.co
set SUPABASE_KEY=your_service_role_key
set TELEGRAM_BOT_TOKEN=your_bot_token
set TELEGRAM_CHAT_ID=your_chat_id

# 영구적 설정 (시스템 환경변수)
setx GEMINI_API_KEY "your_api_key"
setx SUPABASE_URL "https://xxx.supabase.co"
setx SUPABASE_KEY "your_service_role_key"
setx TELEGRAM_BOT_TOKEN "your_bot_token"
setx TELEGRAM_CHAT_ID "your_chat_id"
```

**Docker:**
```bash
# docker run
docker run -e GEMINI_API_KEY="your_api_key" \
           -e SUPABASE_URL="https://xxx.supabase.co" \
           -e SUPABASE_KEY="your_service_role_key" \
           -e TELEGRAM_BOT_TOKEN="your_bot_token" \
           -e TELEGRAM_CHAT_ID="your_chat_id" \
           skinlens:latest

# docker-compose.yml
environment:
  - GEMINI_API_KEY=your_api_key
  - SUPABASE_URL=https://xxx.supabase.co
  - SUPABASE_KEY=your_service_role_key
  - TELEGRAM_BOT_TOKEN=your_bot_token
  - TELEGRAM_CHAT_ID=your_chat_id
```

**.env 파일 (개발 환경):**
```bash
# .env 파일 생성
echo "GEMINI_API_KEY=your_api_key" > .env
echo "SUPABASE_URL=https://xxx.supabase.co" >> .env
echo "SUPABASE_KEY=your_service_role_key" >> .env
echo "TELEGRAM_BOT_TOKEN=your_bot_token" >> .env
echo "TELEGRAM_CHAT_ID=your_chat_id" >> .env

# .env 파일 로드 (python-dotenv 필요)
pip install python-dotenv
python -c "from dotenv import load_dotenv; load_dotenv()"
```

**환경변수 확인:**
```bash
# Linux/macOS
echo $GEMINI_API_KEY
echo $SUPABASE_URL
echo $SUPABASE_KEY
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_CHAT_ID

# Windows PowerShell
echo $env:GEMINI_API_KEY
echo $env:SUPABASE_URL
echo $env:SUPABASE_KEY
echo $env:TELEGRAM_BOT_TOKEN
echo $env:TELEGRAM_CHAT_ID

# Windows CMD
echo %GEMINI_API_KEY%
echo %SUPABASE_URL%
echo %SUPABASE_KEY%
echo %TELEGRAM_BOT_TOKEN%
echo %TELEGRAM_CHAT_ID%
```

### 1.4 secrets.json 파일 관리

- `config/config.secrets.json`은 `.gitignore`에 포함
- 예제 파일: `src/config/config/config.secrets.example.json`
- 실제 파일은 배포 시 수동 생성

### 1.5 Kubernetes Secret (프로덕션)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: skinlens-secrets
type: Opaque
stringData:
  GEMINI_API_KEY: "your_api_key"
  SUPABASE_URL: "https://xxx.supabase.co"
  SUPABASE_KEY: "your_service_role_key"
  TELEGRAM_BOT_TOKEN: "your_bot_token"
  TELEGRAM_CHAT_ID: "your_chat_id"
```

---

## 2. 고객 정보 보호

### 2.1 현재 구조

**고객 정보 필드:**
- `customer_id`: 고객 식별자
- `gender`: 성별
- `age`: 연령
- `race`: 인종
- `region`: 지역

**보안 조치:**
- JWT 인증으로 고객 ID 검증
- `validate_customer_id_match()` 함수로 ID 일치 확인

### 2.2 보안 강화 방안

**1. 데이터 암호화**
- DB 저장 시 민감 필드 암호화
- `customer_id`, `gender`, `age` 등 암호화 저장

**2. 접근 제어**
- 관리자만 전체 고객 정보 접근 가능
- 일반 사용자는 자신의 정보만 접근

**3. 로그 마스킹**
- 로그에 고객 정보 출력 시 마스킹
- `customer_id`: `CUST***` 형식

---

## 3. 이미지 보안

### 3.1 현재 구조

**이미지 저장:**
- 로컬: `results/` 폴더
- 서버: `results/api_jobs/{job_id}/` 폴더

**URL 접근:**
- 서버: `/analysis/jobs/{job_id}/artifacts/{filename}`
- JWT 인증 필요

### 3.2 보안 강화 방안

**1. 이미지 액세스 제어**
- JWT 토큰으로 이미지 접근 제한
- 고객은 자신의 이미지만 접근 가능

**2. 이미지 만료 정책**
- 일정 기간 후 자동 삭제
- `results/api_jobs/` 폴더 정기 정리

**3. URL 서명**
- 일회용 URL 서명 사용
- 만료 시간 설정

---

## 4. 데이터베이스 보안

### 4.1 현재 구조

**로컬 SQLite:**
- `results/skin_analysis.db`
- 파일 시스템 접근 제어 필요

**클라우드 Supabase:**
- Row Level Security (RLS) 활용
- Service Role Key 사용

### 4.2 보안 강화 방안

**1. SQLite 보안**
- 파일 권한: `600` (소유자만 읽기/쓰기)
- 암호화 SQLite 사용 (SQLCipher)

**2. Supabase RLS**
```sql
-- 고객은 자신의 데이터만 접근
CREATE POLICY customer_access ON skin_analyses
  FOR SELECT USING (auth.uid()::text = customer_id);
```

**3. 백업 암호화**
- 백업 파일 암호화
- 암호화 키 별도 관리

---

## 5. 네트워크 보안

### 5.1 현재 구조

**서버:**
- FastAPI 기반
- CORS 설정
- Rate Limiting (역할별)

### 5.2 속도 제한 (Rate Limiting)

**역할별 속도 제한:**
| 역할 | 제한 |
|------|------|
| customer | 30/분 |
| admin | 100/분 |
| analyst | 60/분 |
| default (인증 없음) | 30/분 |

**보안 특징:**
- IP + 역할 기반 속도 제한 키
- 속도 제한 초과 시 HTTP 429 응답
- Retry-After 헤더 포함
- config.json에서 역할별 제한 설정 가능

**설정 예시 (config.json):**
```json
{
  "server": {
    "rate_limiting": {
      "enabled": true,
      "role_limits": {
        "customer": "30/minute",
        "admin": "100/minute",
        "analyst": "60/minute",
        "default": "30/minute"
      }
    }
  }
}
```

### 5.3 요청 로깅 (Request Logging)

**로그 정보:**
- 요청 ID (UUID)
- HTTP 메서드
- 경로
- 쿼리 파라미터
- 클라이언트 IP (X-Forwarded-For, X-Real-IP 지원)
- User-Agent
- 응답 상태 코드
- 처리 시간

**보안 특징:**
- 요청 ID는 응답 헤더 `X-Request-ID`로 제공
- 느린 요청 자동 감지 (기준: 5초)
- 프록시 환경에서 실제 클라이언트 IP 추출

**설정 예시 (config.json):**
```json
{
  "server": {
    "request_logging": {
      "enabled": true,
      "slow_request_threshold": 5.0
    }
  }
}
```

### 5.4 WebSocket 연결 보안

**보안 특징:**
- 최대 연결 수 제한 (기본: 100)
- 연결 타임아웃 (기본: 300초)
- 하트비트 메커니즘으로 비정상 연결 감지
- 자동 연결 종료

**설정 예시 (config.json):**
```json
{
  "server": {
    "websocket": {
      "max_connections": 100,
      "connection_timeout": 300
    }
  }
}
```

### 5.5 보안 강화 방안

**1. HTTPS 강제**
- 모든 요청 HTTPS로 리다이렉트
- SSL/TLS 인증서 사용

**2. IP 화이트리스트/블랙리스트 (구현 완료)**
- 특정 IP만 접근 허용 (화이트리스트)
- 악성 IP 차단 (블랙리스트)
- CIDR 네트워크 범위 지원
- 프록시 환경에서 실제 IP 추출

**설정 예시 (config.json):**
```json
{
  "server": {
    "ip_filter": {
      "whitelist": ["192.168.1.0/24", "10.0.0.1"],
      "blacklist": ["1.2.3.4"],
      "trust_proxy": false
    }
  }
}
```

**3. Security Headers**
```python
# FastAPI Security Headers
app.add_middleware(
    SecureHeadersMiddleware,
    hsts_max_age=31536000,
    hsts_include_subdomains=True,
    hsts_preload=True,
)
```

---

## 6. 작업 큐 및 캐싱

### 6.1 작업 큐 (Job Queue)

**기능:**
- 우선순위 기반 작업 큐 (URGENT > HIGH > NORMAL > LOW)
- 작업 재시도 메커니즘 (최대 재시도 횟수 설정)
- 작업 상태 추적 (PENDING, RUNNING, COMPLETED, FAILED, RETRYING)
- 다중 작업자 지원 (기본: 4)

**API 엔드포인트:**
- GET `/v3/admin/job-queue/stats` - 작업 큐 통계 조회
- GET `/v3/admin/job-queue/{job_id}` - 작업 상태 조회

**설정 예시 (config.json):**
```json
{
  "server": {
    "job_queue": {
      "max_workers": 4
    }
  }
}
```

**보안 특징:**
- 관리자/분석자만 작업 큐 정보 접근 가능
- 작업 실패 시 자동 재시도
- 최대 재시도 초과 시 FAILED 상태

### 6.2 캐싱 (Caching)

**기능:**
- 시스템 메트릭 캐싱 (TTL: 30초)
- ConfigManager 캐싱
- 캐시 통계 조회
- 캐시 초기화 기능

**API 엔드포인트:**
- GET `/v3/admin/cache/stats` - 캐시 통계 조회
- POST `/v3/admin/cache/clear` - 캐시 초기화

**보안 특징:**
- 관리자/분석자만 캐시 관리 가능
- 캐시 초기화 시 감사 로그 기록
- config.json 변경 시 자동 캐시 초기화 (핫 리로드)

---

## 8. 모니터링 및 알림 (Monitoring & Alerts)

### 8.1 Slack 알림

**기능:**
- 에러 발생 시 Slack으로 알림 전송
- 로그 레벨별 색상 구분 (INFO: green, WARNING: orange, ERROR: red)
- 타임스탬프 포함

**설정 예시 (config.json):**
```json
{
  "server": {
    "monitoring": {
      "slack_webhook_url": "https://hooks.slack.com/services/..."
    }
  }
}
```

### 8.2 이메일 알림

**기능:**
- ERROR 레벨 이상 시 이메일 전송
- SMTP 인증 지원
- TLS/STARTTLS 지원

**설정 예시 (config.json):**
```json
{
  "server": {
    "monitoring": {
      "email_smtp_server": "smtp.gmail.com",
      "email_smtp_port": 587,
      "email_username": "user@gmail.com",
      "email_password": "app_password",
      "email_from": "noreply@example.com",
      "email_to": ["admin@example.com"]
    }
  }
}
```

### 8.3 성능 모니터링

**기능:**
- 메트릭 기록 및 조회
- 임계값 초과 시 자동 알림
- 메트릭 초기화 기능

---

## 9. 백업 및 복구 (Backup & Restore)

### 9.1 자동 백업

**기능:**
- 설정된 간격으로 자동 백업
- 데이터베이스 및 결과 파일 백업
- ZIP 압축으로 저장
- 메타데이터 포함

**설정 예시 (config.json):**
```json
{
  "server": {
    "backup": {
      "backup_dir": "backups",
      "db_path": "execution_history.db",
      "max_backups": 7,
      "backup_interval_hours": 24
    }
  }
}
```

### 9.2 백업 관리

**기능:**
- 백업 목록 조회
- 오래된 백업 자동 정리 (max_backups 설정)
- 백업 삭제
- 백업 복구

### 9.3 백업 파일 구조

```
backup_YYYYMMDD_HHMMSS.zip
├── execution_history.db
├── results/
│   └── ...
└── metadata.json
```

### 9.4 복구 기능

**기능:**
- 백업 파일 선택 복구
- 기존 데이터 자동 백업
- 데이터베이스 및 결과 파일 복구
- 복구 실패 시 롤백

---

## 10. 로그 및 감사

### 10.1 현재 구조

**감사 로그:**
- `ExecutionHistoryDB.record_audit_log()`
- 접근, 수정 기록
- API 키 사용 로그 (api_key_usage_logs 테이블)

### 10.2 보안 강화 방안

**1. 로그 보안**
- 민감 정보 마스킹
- 로그 파일 암호화

**2. 감사 추적**
- 모든 DB 변경 사항 기록
- 불규칙 활동 알림

**3. 로그 보관**
- 일정 기간 후 자동 삭제
- 장기 보관용 암호화 아카이브

---

## 11. 보안 체크리스트

**배포 전 확인:**
- [ ] 모든 API 키 환경변수로 설정
- [ ] secrets.json .gitignore 확인
- [ ] HTTPS 설정 완료
- [ ] JWT 인증 활성화
- [ ] 역할별 Rate Limiting 설정
- [ ] 요청 로깅 활성화
- [ ] WebSocket 연결 제한 설정
- [ ] 작업 큐 작업자 수 설정
- [ ] API 키 관리 시스템 활성화
- [ ] DB 암호화 확인
- [ ] 백업 정책 수립
- [ ] 감사 로그 활성화
- [ ] 캐싱 정책 설정
- [ ] 핫 리로드 환경 변수 설정 (개발 환경만)
- [ ] IP 필터링 설정 (필요 시)
- [ ] 모니터링 알림 설정 (Slack/Email)
- [ ] 백업 스케줄링 설정
- [ ] API 버전 관리 설정

---

## 12. 참고 문서

- `DEPLOYMENT_GUIDE.md` - 배포 가이드
- `ARCHITECTURE_GUIDE.md` - 아키텍처 가이드
- `INCIDENT_RESPONSE_GUIDE.md` - 인시던트 대응 가이드

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
