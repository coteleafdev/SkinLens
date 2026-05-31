# 트러블슈팅 가이드 (Troubleshooting Guide)

> **문서 버전:** 1.0.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-05-31  
> **상태:** 활성

---

## 개요

SkinLens 운용 중 발생하는 일반적인 문제 해결 방법입니다.

---

## 1. 서버 문제

### 1.1 서버 시작 실패

**증상:**
```
uvicorn src.server.main:app --host 0.0.0.0 --port 8000
# 에러: Address already in use
```

**원인:**
- 포트 8000이 이미 사용 중

**해결:**
```bash
# 포트 사용 프로세스 확인
netstat -tulpn | grep 8000  # Linux
lsof -i :8000  # macOS
netstat -ano | findstr :8000  # Windows

# 프로세스 종료
kill -9 <PID>  # Linux/macOS
taskkill /PID <PID> /F  # Windows

# 또는 다른 포트 사용
uvicorn src.server.main:app --host 0.0.0.0 --port 8001
```

---

### 1.2 GPU 인식 실패

**증상:**
```
torch.cuda.is_available() → False
```

**원인:**
- NVIDIA 드라이버 미설치
- CUDA 미설치
- PyTorch CPU 버전

**해결:**
```bash
# NVIDIA 드라이버 확인
nvidia-smi

# CUDA 버전 확인
nvcc --version

# PyTorch GPU 지원 확인
python -c "import torch; print(torch.cuda.is_available())"

# PyTorch GPU 버전 재설치
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

---

### 1.3 메모리 부족 (OOM)

**증상:**
```
RuntimeError: CUDA out of memory
```

**원인:**
- GPU 메모리 부족
- 배치 크기 너무 큼

**해결:**
```bash
# 배치 크기 감소
# config/config.json 수정
{
  "restoration": {
    "batch_size": 1
  }
}

# GPU 메모리 정리
python -c "import torch; torch.cuda.empty_cache()"

# 스왑 메모리 증설
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## 2. 이미지 처리 문제

### 2.1 이미지 업로드 실패

**증상:**
```
413 Payload Too Large
```

**원인:**
- 파일 크기 제한 초과

**해결:**
```json
// config/config.json
{
  "server": {
    "max_upload_bytes": 52428800  // 50MB
  }
}
```

```nginx
// nginx.conf
client_max_body_size 50M;
```

---

### 2.2 이미지 형식 지원 안함

**증상:**
```
Unsupported image format
```

**원인:**
- 지원하지 않는 이미지 형식

**해결:**
```json
// config/config.json
{
  "server": {
    "allowed_extensions": [".jpg", ".jpeg", ".png", ".webp", ".tiff"]
  }
}
```

---

### 2.3 이미지 복원 실패

**증상:**
```
Restoration failed: model not found
```

**원인:**
- 모델 파일 미존재

**해결:**
```bash
# 모델 다운로드
python scripts/download_models.py --model restoreformer
python scripts/download_models.py --model codeformer

# 모델 경로 확인
ls models/restoreformer/
ls models/codeformer/
```

---

## 3. 데이터베이스 문제

### 3.1 SQLite 잠금

**증상:**
```
sqlite3.OperationalError: database is locked
```

**원인:**
- 동시 쓰기 충돌

**해결:**
```python
# 연결 시 timeout 설정
conn = sqlite3.connect('skin_analysis.db', timeout=30.0)

# WAL 모드 활성화
conn.execute('PRAGMA journal_mode=WAL')
```

---

### 3.2 Supabase 연결 실패

**증상:**
```
Connection refused
```

**원인:**
- 잘못된 URL/Key
- 네트워크 문제

**해결:**
```bash
# 환경변수 확인
echo $SUPABASE_URL
echo $SUPABASE_KEY

# 연결 테스트
curl -I $SUPABASE_URL

# 재설정
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_KEY="your_service_role_key"
```

---

## 4. LLM API 문제

### 4.1 API 키 만료

**증상:**
```
401 Unauthorized
```

**원인:**
- API 키 만료 또는 잘못됨

**해결:**
```bash
# API 키 재설정
export GEMINI_API_KEY="new_api_key"

# 테스트
python -c "from google import genai; genai.configure(api_key=os.environ['GEMINI_API_KEY'])"
```

---

### 4.2 LLM 응답 시간 초과

**증상:**
```
TimeoutError: LLM request timeout
```

**원인:**
- 타임아웃 설정 너무 짧음

**해결:**
```json
// config/config.json
{
  "llm": {
    "timeout_sec": 600
  }
}
```

---

## 5. 로그 분석

### 5.1 로그 위치

| 환경 | 로그 위치 |
|------|-----------|
| 로컬 | `logs/skinlens.log` |
| Docker | `docker logs skinlens` |
| systemd | `journalctl -u skinlens` |

### 5.2 로그 레벨

```python
# config/config.json
{
  "logging": {
    "level": "DEBUG"  // DEBUG, INFO, WARNING, ERROR, CRITICAL
  }
}
```

### 5.3 로그 필터링

```bash
# 에러만 보기
grep ERROR logs/skinlens.log

# 특정 Job 로그
grep "job_id=xxx" logs/skinlens.log

# 최근 100줄
tail -n 100 logs/skinlens.log

# 실시간 모니터링
tail -f logs/skinlens.log
```

---

## 6. 성능 문제

### 6.1 응답 시간 느림

**증상:**
- API 응답 시간 > 30초

**원인:**
- GPU 부하
- 네트워크 지연
- DB 쿼리 최적화 필요

**해결:**
```bash
# GPU 사용량 확인
nvidia-smi

# 네트워크 지연 확인
ping api.skinlens.com

# DB 쿼리 최적화
sqlite3 skin_analysis.db "EXPLAIN QUERY PLAN SELECT * FROM analyses"
```

---

### 6.2 CPU 사용량 높음

**증상:**
- CPU 사용량 > 80%

**원인:**
- 병렬 처리 부족
- 비효율적인 알고리즘

**해결:**
```python
# 병렬 처리 증가
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=4)
```

---

## 7. 네트워크 문제

### 7.1 CORS 에러

**증상:**
```
Access to XMLHttpRequest blocked by CORS policy
```

**원인:**
- CORS 설정 미완료

**해결:**
```python
# src/server/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.skinlens.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### 7.2 Rate Limiting

**증상:**
```
429 Too Many Requests
```

**원인:**
- 요청 수 초과

**해결:**
```python
# config/config.json
{
  "server": {
    "rate_limit": {
      "requests_per_minute": 60
    }
  }
}
```

---

## 8. 진단 도구

### 8.1 헬스체크

```bash
# 서버 상태
curl http://localhost:8000/health

# DB 연결
python -c "from src.db.skin_analysis_db import SkinAnalysisDB; db = SkinAnalysisDB(); print('OK')"

# GPU 상태
nvidia-smi
```

### 8.2 디버그 모드

```bash
# 디버그 모드 실행
python main.py --debug

# 상세 로그
export LOG_LEVEL=DEBUG
```

---

## 참고 문서

- `DEPLOYMENT_GUIDE.md` - 배포 가이드
- `SECURITY_GUIDE.md` - 보안 가이드
- `MONITORING_GUIDE.md` - 모니터링 가이드

---

## 변경 이력

| 문서 버전 | 날짜 | 변경 내용 | 작성자 |
|-----------|------|----------|--------|
| 1.0.0 | 2026-05-31 | 초기 버전 (v3.6에서 마이그레이션) | Cascade |
| 0.6.0 | 2026-05-30 | 트러블슈팅 가이드 초기 작성 | Cascade |
