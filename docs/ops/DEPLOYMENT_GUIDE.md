# 배포 가이드 (Deployment Guide)

> **프로젝트:** SkinLens v1.0  
> **버전:** v3.6  
> **작성일:** 2026-05-30  
*상태:* 초안

---

## 개요

이 가이드는 SkinLens 시스템을 프로덕션 환경에 배포하는 방법을 설명합니다.

---

## 시스템 요구사항

### 하드웨어

- **CPU:** 4코어 이상 권장
- **RAM:** 16GB 이상 권장
- **GPU:** NVIDIA GPU (CUDA 지원) - 복원 모델 실행용
- **스토리지:** 100GB 이상 SSD

### 소프트웨어

- **OS:** Ubuntu 20.04 LTS 이상 또는 Windows Server 2019 이상
- **Python:** 3.8 이상
- **Docker:** 20.10 이상 (선택)
- **NVIDIA Driver:** 470.x 이상 (GPU 사용 시)

---

## 배포 방법

### 방법 1: Docker 배포 (권장)

#### 1. Docker 이미지 빌드

```bash
docker build -t skinlens:latest .
```

#### 2. Docker Compose 실행

```bash
docker-compose up -d
```

#### 3. 환경 변수 설정

`.env` 파일 생성:

```env
# 서버 설정
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
MAX_UPLOAD_BYTES=20971520

# 데이터베이스
DB_PATH=/data/skinlens.db

# LLM API
LLM_API_KEY=your_api_key_here
LLM_PROVIDER=gemini

# 인증
ADMIN_PASSWORD=$2b$12$...  # bcrypt 해시
ANALYST_PASSWORD=$2b$12$...
CUSTOMER_PASSWORD=$2b$12$...

# 로깅
LOG_LEVEL=INFO
```

---

### 방법 2: 직접 배포

#### 1. 의존성 설치

```bash
pip install -r requirements-core.txt
pip install -r requirements-gpu.txt  # GPU 사용 시
```

#### 2. 환경 변수 설정

```bash
export SERVER_HOST=0.0.0.0
export SERVER_PORT=8000
export DB_PATH=/path/to/database.db
export LLM_API_KEY=your_api_key_here
```

#### 3. 서버 실행

```bash
uvicorn src.server.main:app --host $SERVER_HOST --port $SERVER_PORT
```

---

## 데이터베이스 설정

### SQLite (기본)

```bash
# 데이터베이스 파일 생성
touch /data/skinlens.db

# 권한 설정
chmod 644 /data/skinlens.db
```

### PostgreSQL (선택)

```python
# config/config.json 수정
{
  "database": {
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "name": "skinlens",
    "user": "skinlens",
    "password": "your_password"
  }
}
```

---

## 모델 다운로드

### 복원 모델

```bash
# RestoreFormer++ 모델 다운로드
python scripts/download_models.py --model restoreformer

# CodeFormer 모델 다운로드
python scripts/download_models.py --model codeformer
```

### 분석 모델

분석 모델은 자동으로 다운로드됩니다.

---

## Nginx 설정 (선택)

### 리버스 프록시 설정

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 정적 파일 캐싱
    location /static {
        alias /path/to/static/files;
        expires 30d;
    }

    # 파일 업로드 크기 제한
    client_max_body_size 20M;
}
```

---

## SSL/TLS 설정

### Let's Encrypt 사용

```bash
sudo certbot --nginx -d your-domain.com
```

---

## 백업

### 데이터베이스 백업

```bash
# SQLite 백업
cp /data/skinlens.db /backup/skinlens_$(date +%Y%m%d).db

# 자동 백업 스크립트
# /etc/cron.daily/skinlens-backup.sh
#!/bin/bash
cp /data/skinlens.db /backup/skinlens_$(date +%Y%m%d).db
find /backup -name "skinlens_*.db" -mtime +7 -delete
```

---

## 모니터링

### 로그 확인

```bash
# Docker 로그
docker logs -f skinlens

# 직접 실행 시 로그
tail -f /var/log/skinlens/app.log
```

### 상태 확인

```bash
# API 상태 확인
curl http://localhost:8000/health

# 작업 큐 상태 확인
curl http://localhost:8000/v3/analysis/jobs
```

---

## 보안

보안 관련 상세 가이드는 `SECURITY_GUIDE.md`를 참조하세요.

**주요 항목:**
- 방화벽 설정
- API 키 관리
- 파일 업로드 제한
- HTTPS/SSL 설정

---

## 확장

### 수평 확장

```yaml
# docker-compose.yml
services:
  skinlens:
    image: skinlens:latest
    deploy:
      replicas: 3
    environment:
      - REDIS_URL=redis://redis:6379
```

### 로드 밸런싱

```nginx
upstream skinlens {
    server localhost:8000;
    server localhost:8001;
    server localhost:8002;
}

server {
    location / {
        proxy_pass http://skinlens;
    }
}
```

---

## 트러블슈팅

트러블슈팅 관련 상세 가이드는 `TROUBLESHOOTING_GUIDE.md`를 참조하세요.

**주요 항목:**
- 서버 시작 실패
- GPU 인식 실패
- 메모리 부족
- 이미지 처리 문제
- 데이터베이스 문제

---

*작성일: 2026-05-30*  
*버전: v1.0*  
*마지막 수정: 2026-05-30*
