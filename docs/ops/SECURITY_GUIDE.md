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

### 1.1 현재 구조

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

### 1.2 환경변수 사용 (권장)

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

### 1.3 secrets.json 파일 관리

- `config/config.secrets.json`은 `.gitignore`에 포함
- 예제 파일: `src/config/config/config.secrets.example.json`
- 실제 파일은 배포 시 수동 생성

### 1.4 Kubernetes Secret (프로덕션)

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
- Rate Limiting

### 5.2 보안 강화 방안

**1. HTTPS 강제**
- 모든 요청 HTTPS로 리다이렉트
- SSL/TLS 인증서 사용

**2. Rate Limiting 강화**
- IP별 요청 제한
- 고객별 요청 제한

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

## 6. 로그 및 감사

### 6.1 현재 구조

**감사 로그:**
- `ExecutionHistoryDB.record_audit_log()`
- 접근, 수정 기록

### 6.2 보안 강화 방안

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

## 7. 보안 체크리스트

**배포 전 확인:**
- [ ] 모든 API 키 환경변수로 설정
- [ ] secrets.json .gitignore 확인
- [ ] HTTPS 설정 완료
- [ ] JWT 인증 활성화
- [ ] Rate Limiting 설정
- [ ] DB 암호화 확인
- [ ] 백업 정책 수립
- [ ] 감사 로그 활성화

---

## 8. 참고 문서

- `DEPLOYMENT_GUIDE.md` - 배포 가이드
- `ARCHITECTURE_GUIDE.md` - 아키텍처 가이드
- `INCIDENT_RESPONSE_GUIDE.md` - 인시던트 대응 가이드

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
