# 트러블슈팅 가이드 (Troubleshooting Guide)

> **문서 버전:** 2.1.0  
> **대상 프로젝트 버전:** 1.0.0  
> **마지막 업데이트:** 2026-06-01  
> **상태:** 활성

---

## 개요

SkinLens 실환경 운영 중 발생할 수 있는 문제 유형별 진단 및 해결 방법입니다. 웹서버와 모바일 앱 각각에 맞는 트러블슈팅 가이드를 제공합니다.

---

## 1. 웹서버 트러블슈팅

### 1.1 웹서버 문제 유형 분류

#### 1.1.1 Docker 설치 및 구축 관련 문제
- Docker 설치 실패
- Docker 이미지 빌드 실패
- Docker Compose 시작 실패
- 컨테이너 실행 실패
- 볼륨 마운트 실패
- 네트워크 연결 실패
- 헬스 체크 실패

#### 1.1.2 엔진 서버 연동 관련 문제
- 엔진 서버 연결 실패
- 엔진 서버 타임아웃
- 엔진 서버 응답 오류
- WebSocket 프록시 실패

#### 1.1.3 API 관련 문제
- 4xx 클라이언트 오류
- 5xx 서버 오류
- 응답 시간 지연
- 인증/인가 실패

#### 1.1.4 데이터베이스 관련 문제
- 웹서버 DB 연결 실패
- 웹서버 DB 잠금 (Lock)
- 쿼리 성능 저하
- 데이터 불일치

#### 1.1.5 푸시 알림 관련 문제
- FCM/APNS 연결 실패
- 토큰 등록 실패
- 알림 전송 실패

#### 1.1.6 시스템 리소스 관련 문제
- CPU 사용량 과다
- 메모리 부족
- 디스크 공간 부족
- 네트워크 연결 문제

---

### 1.2 Docker 설치 및 구축 관련 문제

#### 1.2.1 Docker 설치 실패

**증상**
- `docker: command not found`: Docker 명령어를 찾을 수 없음
- `permission denied`: 권한 거류
- `WSL 2 installation failed`: WSL 2 설치 실패 (Windows)
- `Docker Desktop won't start`: Docker Desktop 시작 실패

**진단 단계**
1. 시스템 버전 확인
2. Docker 설치 상태 확인
3. 사용자 권한 확인
4. WSL 2 상태 확인 (Windows)

**해결 방법**

**Windows:**
```bash
# PowerShell을 관리자 권한으로 실행
# WSL 2 설치 상태 확인
wsl --status

# WSL 2 설치
wsl --install

# 시스템 재부팅 후 확인
wsl --list --verbose

# Docker Desktop 재설치
# 제어판 > 프로그램 및 기능 > Windows 기능 활성화/비활성화
# Hyper-V, Windows Subsystem for Linux 활성화
```

**Linux (Ubuntu/Debian):**
```bash
# Docker 설치 상태 확인
docker --version

# 사용자 권한 확인
groups $USER

# docker 그룹에 사용자 추가
sudo usermod -aG docker $USER

# 로그아웃 후 재로그인
newgrp docker

# Docker 서비스 상태 확인
sudo systemctl status docker

# Docker 서비스 시작
sudo systemctl start docker
sudo systemctl enable docker
```

**macOS:**
```bash
# Docker Desktop 버전 확인
docker --version

# Docker Desktop 재시작
# 메뉴 바 > Docker 아이콘 > Restart

# Docker Desktop 재설치
# Applications 폴더에서 Docker.app 삭제
# 최신 버전 다시 설치
```

**참조**
- [웹서버-엔진서버 연동 가이드 - Docker 설치](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#1-docker-설치)
- [Docker 공식 문서](https://docs.docker.com/engine/install/)

#### 1.2.2 Docker 이미지 빌드 실패

**증상**
- `failed to solve`: 빌드 실패
- `no matching manifest`: 아키텍처 불일치
- `package not found`: 패키지 의존성 오류

**진단 단계**
1. Dockerfile 확인
2. requirements.txt 확인
3. 시스템 아키텍처 확인
4. 네트워크 연결 확인

**해결 방법**

```bash
# Dockerfile 확인
cat Dockerfile

# requirements.txt 확인
cat requirements.txt

# 시스템 아키텍처 확인
uname -m
docker info | grep "Architecture"

# 빌드 캐시 삭제 후 재빌드
docker build --no-cache -t skinlens-engine:1.0.0 .

# 빌드 로그 확인
docker build -t skinlens-engine:1.0.0 . 2>&1 | tee build.log

# 패키지 버전 수정 (requirements.txt)
# 예: torch==2.1.0 → torch==2.0.1
```

**참조**
- [웹서버-엔진서버 연동 가이드 - Docker 이미지 빌드](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#213-docker-이미지-빌드)

#### 1.2.3 Docker Compose 시작 실패

**증상**
- `port is already allocated`: 포트 충돌
- `network not found`: 네트워크 오류
- `volume not found`: 볼륨 오류

**진단 단계**
1. 포트 사용 상태 확인
2. 네트워크 상태 확인
3. 볼륨 상태 확인
4. docker-compose.yml 확인

**해결 방법**

```bash
# 포트 사용 상태 확인 (Windows)
netstat -ano | findstr :8000

# 포트 사용 상태 확인 (Linux/macOS)
lsof -i :8000
netstat -tulpn | grep :8000

# 포트 사용 중인 프로세스 종료
# Windows: taskkill /PID <PID> /F
# Linux: kill -9 <PID>

# docker-compose.yml 확인
cat docker-compose.yml

# 네트워크 확인
docker network ls
docker network inspect skinlens-network

# 볼륨 확인
docker volume ls

# 기존 컨테이너/네트워크/볼륨 삭제 후 재시작
docker-compose down -v
docker-compose up -d

# 로그 확인
docker-compose logs
```

**참조**
- [웹서버-엔진서버 연동 가이드 - Docker Compose 설정](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#222-docker-compose-설정)

#### 1.2.4 컨테이너 실행 실패

**증상**
- `container exited immediately`: 컨테이너 즉시 종료
- `Exit code 1`: 에러로 종료
- `Exit code 137`: 메모리 부족 (OOM Killed)

**진단 단계**
1. 컨테이너 로그 확인
2. 컨테이너 상태 확인
3. 리소스 사용량 확인
4. 애플리케이션 로그 확인

**해결 방법**

```bash
# 컨테이너 상태 확인
docker ps -a

# 컨테이너 로그 확인
docker logs skinlens-engine

# 컨테이너 실시간 로그 확인
docker logs -f skinlens-engine

# 컨테이너 내부 접속
docker exec -it skinlens-engine bash

# 컨테이너 내부 로그 확인
tail -f logs/server.log

# 리소스 사용량 확인
docker stats skinlens-engine

# 메모리 제한 증가 (docker-compose.yml)
# deploy:
#   resources:
#     limits:
#       memory: 4G

# 컨테이너 재시작
docker restart skinlens-engine
```

**참조**
- [웹서버-엔진서버 연동 가이드 - 컨테이너 내부 확인](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#233-컨테이너-내부-확인)

#### 1.2.5 볼륨 마운트 실패

**증상**
- `permission denied`: 디렉토리 권한 문제
- `no such file or directory`: 디렉토리 없음
- `mount point does not exist`: 마운트 포인트 없음

**진단 단계**
1. 디렉토리 존재 확인
2. 디렉토리 권한 확인
3. docker-compose.yml 볼륨 설정 확인
4. SELinux/AppArmor 확인 (Linux)

**해결 방법**

```bash
# 디렉토리 존재 확인
ls -la data/
ls -la logs/

# 디렉토리 생성
mkdir -p data logs

# 디렉토리 권한 수정
chmod 755 data logs
sudo chown -R $USER:$USER data logs

# docker-compose.yml 볼륨 설정 확인
# volumes:
#   - ./data:/app/data
#   - ./logs:/app/logs

# SELinux 확인 (Linux)
getenforce
# SELinux 비활성화 (테스트용)
sudo setenforce 0

# AppArmor 확인 (Linux)
sudo aa-status

# 볼륨 재마운트
docker-compose down
docker-compose up -d
```

**참조**
- [웹서버-엔진서버 연동 가이드 - Docker Compose 설정](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#222-docker-compose-설정)

#### 1.2.6 네트워크 연결 실패

**증상**
- `network unreachable`: 네트워크 도달 불가
- `connection timeout`: 연결 타임아웃
- `DNS resolution failed`: DNS 해결 실패

**진단 단계**
1. 네트워크 상태 확인
2. 방화벽 규칙 확인
3. DNS 확인
4. 프록시 설정 확인

**해결 방법**

```bash
# 네트워크 상태 확인
ping google.com
ping localhost

# 방화벽 규칙 확인 (Linux)
sudo ufw status
sudo iptables -L -n

# 방화벽 규칙 확인 (Windows)
netsh advfirewall show allprofiles

# 포트 개방 (Linux)
sudo ufw allow 8000/tcp
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT

# 포트 개방 (Windows)
netsh advfirewall firewall add rule name="Docker" dir=in action=allow protocol=TCP localport=8000

# DNS 확인
nslookup google.com
cat /etc/resolv.conf

# DNS 서버 변경 (Linux)
sudo nano /etc/resolv.conf
# nameserver 8.8.8.8

# 프록시 설정 확인
echo $HTTP_PROXY
echo $HTTPS_PROXY

# Docker 네트워크 재시작
docker network prune
docker-compose down
docker-compose up -d
```

**참조**
- [웹서버-엔진서버 연동 가이드 - 네트워크 요구사항](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#43-네트워크-요구사항)

#### 1.2.7 헬스 체크 실패

**증상**
- `healthcheck failed`: 헬스 체크 실패
- `unhealthy`: 컨테이너 상태 unhealthy
- `starting timeout`: 시작 타임아웃

**진단 단계**
1. 헬스 체크 설정 확인
2. 서버 시작 시간 확인
3. 헬스 체크 엔드포인트 확인
4. 로그 확인

**해결 방법**

```bash
# 헬스 체크 설정 확인 (docker-compose.yml)
# healthcheck:
#   test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
#   interval: 30s
#   timeout: 10s
#   retries: 3
#   start_period: 40s

# 헬스 체크 엔드포인트 직접 테스트
curl http://localhost:8000/health

# 컨테이너 내부에서 헬스 체크
docker exec skinlens-engine curl http://localhost:8000/health

# start_period 증가 (서버 시작 시간이 긴 경우)
# start_period: 60s

# interval 증가 (헬스 체크 간격 증가)
# interval: 60s

# 로그 확인
docker logs skinlens-engine | grep -i health

# 컨테이너 재시작
docker restart skinlens-engine
```

**참조**
- [웹서버-엔진서버 연동 가이드 - 엔진 서버 실행 확인](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#23-엔진-서버-실행-확인)

---

### 1.3 엔진 서버 연동 관련 문제

#### 1.3.1 엔진 서버 연결 실패

**증상**
- `Connection refused`: 엔진 서버 접속 불가
- `Connection timeout`: 연결 타임아웃
- `DNS resolution failed`: DNS 해결 실패

**진단 단계**
1. 엔진 서버 상태 확인
2. 네트워크 연결 확인
3. 방화벽 규칙 확인
4. DNS 확인

**해결 방법**

```bash
# 엔진 서버 상태 확인
curl http://localhost:8000/health

# 네트워크 연결 확인
ping engine.skinlens.com

# 방화벽 규칙 확인
sudo ufw status
sudo iptables -L

# DNS 확인
nslookup engine.skinlens.com
```

**참조**
- [웹서버-엔진서버 연동 가이드](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#4-사전-요구사항)

#### 1.3.2 엔진 서버 타임아웃

**증상**
- `504 Gateway Timeout`: 게이트웨이 타임아웃
- 요청 응답 시간 > 30초

**진단 단계**
1. 엔진 서버 부하 확인
2. 네트워크 대기 시간 확인
3. 분석 작업 큐 확인

**해결 방법**

```bash
# 엔진 서버 부하 확인
curl http://localhost:8000/metrics

# 타임아웃 설정 증가 (Nginx)
proxy_read_timeout 60s;
proxy_connect_timeout 60s;

# 분석 작업 큐 확인
curl http://localhost:8000/v1/admin/jobs/queue
```

**참조**
- [트러블슈팅 가이드 - API 관련 문제](#2-api-관련-문제)

#### 1.3.3 WebSocket 프록시 실패

**증상**
- WebSocket 연결 실패
- 메시지 전송 안 됨
- 연결 끊김

**진단 단계**
1. Nginx WebSocket 설정 확인
2. 엔진 서버 WebSocket 상태 확인
3. 프록시 로그 확인

**해결 방법**

```nginx
# Nginx WebSocket 설정 확인
location /ws/ {
    proxy_pass http://localhost:8000/v1/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Authorization $http_authorization;
    proxy_read_timeout 3600s;
}
```

**참조**
- [웹서버-엔진서버 연동 가이드](WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md#53-websocket-연동-실시간-진행률)

---

### 1.4 API 관련 문제

#### 1.4.1 4xx 클라이언트 오류

**증상**
- `400 Bad Request`: 요청 파라미터 오류
- `401 Unauthorized`: 인증 실패
- `403 Forbidden`: 권한 부족
- `404 Not Found`: 리소스 없음
- `422 Unprocessable Entity`: 요청 데이터 유효성 검증 실패

**진단 단계**
1. 요청 로그 확인
2. 요청 파라미터 검증
3. 인증 헤더 확인
4. API 스펙 문서 확인

**해결 방법**

```bash
# 요청 로그 확인
tail -f logs/api_requests.log | grep "400"

# 요청 파라미터 검증
curl -X POST http://localhost:80/v1/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "CUST001", "gender": "female", "age": 30}'

# JWT 토큰 확인
curl -X GET http://localhost:80/v1/customer/my/profile \
  -H "Authorization: Bearer <token>"
```

**참조**
- [API 레퍼런스](../api/API_REFERENCE.md)

#### 1.4.2 5xx 서버 오류

**증상**
- `500 Internal Server Error`: 서버 내부 오류
- `502 Bad Gateway`: 게이트웨이 오류
- `503 Service Unavailable`: 서비스 불가
- `504 Gateway Timeout`: 게이트웨이 타임아웃

**진단 단계**
1. 서버 로그 확인
2. 에러 스택 트레이스 확인
3. 서버 상태 확인
4. DB 연결 확인

**해결 방법**

```bash
# 서버 로그 확인
tail -f logs/server.log | grep "ERROR"

# 서버 재시작
systemctl restart webserver

# 엔진 서버 상태 확인
curl http://localhost:8000/health
```

**참조**
- [트러블슈팅 가이드 - 시스템 리소스 관련 문제](#15-시스템-리소스-관련-문제)

---

### 1.5 데이터베이스 관련 문제

#### 1.5.1 웹서버 DB 연결 실패

**증상**
- `Connection refused`: DB 접속 불가
- `Connection timeout`: 연결 타임아웃

**진단 단계**
1. DB 서버 상태 확인
2. DB 연결 문자열 확인
3. DB 사용자 권한 확인

**해결 방법**

```bash
# DB 서버 상태 확인
systemctl status mysql
# 또는
systemctl status postgresql

# DB 연결 테스트
mysql -u username -p -h localhost database_name

# DB 연결 문자열 확인
# config/database.yml 또는 환경 변수 확인
```

**참조**
- [데이터 모델](../db/DATA_MODEL.md)

#### 1.5.2 웹서버 DB 잠금 (Lock)

**증상**
- `Database is locked`: DB 잠금
- 동시 요청 실패
- 트랜잭션 타임아웃

**진단 단계**
1. 잠금 프로세스 확인
2. 트랜잭션 확인
3. 동시 요청 수 확인

**해결 방법**

```bash
# 잠금 프로세스 확인
SHOW PROCESSLIST;

# 잠금 해제
KILL <process_id>;

# 트랜잭션 타임아웃 설정
# DB 설정 파일에서 timeout 설정 증가
```

**참조**
- [데이터 모델](../db/DATA_MODEL.md)

---

### 1.6 푸시 알림 관련 문제

#### 1.6.1 FCM/APNS 연결 실패

**증상**
- 푸시 알림 전송 실패
- 토큰 등록 실패
- 인증 오류

**진단 단계**
1. FCM/APNS 키 확인
2. 토큰 유효성 확인
3. 네트워크 연결 확인

**해결 방법**

```bash
# FCM 키 확인
echo $FCM_API_KEY

# APNS 키 확인
echo $APNS_KEY_PATH

# 토큰 재등록
curl -X POST http://localhost:80/v1/customer/my/push-token \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"token": "new_token", "platform": "ios"}'
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#35-5단계-푸시-알림)

---

### 1.7 시스템 리소스 관련 문제

#### 1.7.1 CPU 사용량 과다

**증상**
- CPU 사용량 > 80%
- 시스템 느림
- 프로세스 응답 없음

**진단 단계**
1. CPU 사용량 확인
2. 프로세스 확인
3. 분석 작업 확인

**해결 방법**

```bash
# CPU 사용량 확인
top
htop

# 프로세스 확인
ps aux | grep python

# 서비스 재시작
systemctl restart webserver
```

**참조**
- [트러블슈팅 가이드 - 모니터링 지표](#3-모니터링-지표)

#### 1.7.2 메모리 부족

**증상**
- `Out of memory`: 메모리 부족
- `Exit code 137`: OOM Killed
- 시스템 느림

**진단 단계**
1. 메모리 사용량 확인
2. 스왑 사용량 확인
3. 프로세스 메모리 확인

**해결 방법**

```bash
# 메모리 사용량 확인
free -h
vmstat

# 스왑 사용량 확인
swapon -s

# 프로세스 메모리 확인
ps aux --sort=-%mem | head

# 불필요한 프로세스 종료
kill -9 <PID>

# 스왑 공간 추가 (Linux)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Docker 메모리 제한 증가 (docker-compose.yml)
# deploy:
#   resources:
#     limits:
#       memory: 4G
```

**참조**
- [트러블슈팅 가이드 - 모니터링 지표](#3-모니터링-지표)

#### 1.7.3 디스크 공간 부족

**증상**
- `No space left on device`: 디스크 공간 부족
- 파일 쓰기 실패
- 로그 파일 증가

**진단 단계**
1. 디스크 사용량 확인
2. 큰 파일 확인
3. 로그 파일 확인

**해결 방법**

```bash
# 디스크 사용량 확인
df -h
du -sh *

# 큰 파일 확인
find / -type f -size +100M 2>/dev/null

# 로그 파일 확인
ls -lh logs/

# 로그 파일 삭제 또는 압축
rm logs/server.log
gzip logs/server.log

# Docker 불필요한 리소스 정리
docker system prune -a

# 불필요한 패키지 정리 (Linux)
sudo apt autoremove
sudo apt clean
```

**참조**
- [트러블슈팅 가이드 - 모니터링 지표](#3-모니터링-지표)

---

## 2. 모바일 앱 트러블슈팅

### 2.1 모바일 앱 문제 유형 분류

#### 2.1.1 네트워크 관련 문제
- 인터넷 연결 없음
- 서버 연결 실패
- 타임아웃
- DNS 해결 실패

#### 2.1.2 인증 관련 문제
- 로그인 실패
- 토큰 만료
- 권한 부족
- 세션 만료

#### 2.1.3 이미지 업로드 관련 문제
- 파일 크기 초과
- 파일 형식 지원 안 함
- 업로드 실패
- 업로드 타임아웃

#### 2.1.4 WebSocket 관련 문제
- WebSocket 연결 실패
- 연결 끊김
- 메시지 수신 안 됨
- 백그라운드 연결 끊김

#### 2.1.5 푸시 알림 관련 문제
- 푸시 알림 수신 안 됨
- 토큰 등록 실패
- 알림 권한 없음
- 백그라운드 알림 안 됨

#### 2.1.6 로컬 DB 관련 문제
- DB 저장 실패
- DB 읽기 실패
- 데이터 불일치

#### 2.1.7 PCR 검사 관련 문제
- PCR 검사 요청 실패
- 키트 발송 안 됨
- 결과 조회 실패
- 상담 예약 실패

#### 2.1.8 주문 관련 문제
- 기성품 목록 조회 실패
- 재고 부족
- 주문 생성 실패
- 결제 실패

#### 2.1.9 오프라인 모드 관련 문제
- 오프라인 요청 큐 실패
- 동기화 실패
- 데이터 손실

---

### 2.2 네트워크 관련 문제

#### 2.2.1 인터넷 연결 없음

**증상**
- `No Internet Connection`: 인터넷 연결 없음
- API 호출 실패

**진단 단계**
1. 네트워크 상태 확인
2. Wi-Fi/셀룰러 데이터 확인
3. 서버 접속 확인

**해결 방법**

**iOS (Swift):**
```swift
import Network

let monitor = NWPathMonitor()
monitor.pathUpdateHandler = { path in
    if path.status == .satisfied {
        print("Connected")
    } else {
        print("Disconnected")
    }
}
monitor.start(queue: DispatchQueue.main)
```

**Android (Kotlin):**
```kotlin
val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
val networkInfo = connectivityManager.activeNetworkInfo

if (networkInfo != null && networkInfo.isConnected) {
    // Connected
} else {
    // Disconnected
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#24-네트워크-요구사항)

#### 2.2.2 서버 연결 실패

**증상**
- `Connection refused`: 서버 접속 불가
- `Connection timeout`: 연결 타임아웃

**진단 단계**
1. 서버 URL 확인
2. 서버 상태 확인
3. 방화벽 확인

**해결 방법**

**iOS (Swift):**
```swift
let url = URL(string: "http://localhost:80/health")!
var request = URLRequest(url: url)
request.timeoutInterval = 30

URLSession.shared.dataTask(with: request) { data, response, error in
    if let error = error {
        print("Connection failed: \(error)")
    }
}.resume()
```

**Android (Kotlin):**
```kotlin
val client = OkHttpClient.Builder()
    .connectTimeout(30, TimeUnit.SECONDS)
    .readTimeout(30, TimeUnit.SECONDS)
    .build()

val request = Request.Builder()
    .url("http://localhost:80/health")
    .build()

client.newCall(request).execute()
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#21-웹서버-정보)

---

### 2.3 인증 관련 문제

#### 2.3.1 로그인 실패

**증상**
- `401 Unauthorized`: 인증 실패
- `Invalid credentials`: 자격 증명 오류

**진단 단계**
1. 사용자 이름/비밀번호 확인
2. 서버 상태 확인
3. 네트워크 연결 확인

**해결 방법**

**iOS (Swift):**
```swift
AuthManager.shared.login(username: "user", password: "pass") { result in
    switch result {
    case .success(let token):
        print("Login success: \(token)")
    case .failure(let error):
        print("Login failed: \(error)")
        // 사용자에게 오류 메시지 표시
    }
}
```

**Android (Kotlin):**
```kotlin
lifecycleScope.launch {
    val result = authManager.login("user", "pass")
    when {
        result.isSuccess -> {
            println("Login success")
        }
        result.isFailure -> {
            println("Login failed: ${result.exceptionOrNull()}")
            // 사용자에게 오류 메시지 표시
        }
    }
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#31-1단계-인증-설정)

#### 2.3.2 토큰 만료

**증상**
- `401 Unauthorized`: 토큰 만료
- `Token has expired`: 토큰 만료

**진단 단계**
1. 토큰 만료 시간 확인
2. 토큰 갱신 로직 확인

**해결 방법**

**iOS (Swift):**
```swift
func refreshToken() {
    let refreshToken = KeychainHelper.getRefreshToken()
    
    let url = URL(string: "\(baseURL)/v1/auth/refresh")!
    var request = URLRequest(url: url)
    request.setValue("Bearer \(refreshToken)", forHTTPHeaderField: "Authorization")
    
    URLSession.shared.dataTask(with: request) { data, response, error in
        if let data = data,
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let newToken = json["access_token"] as? String {
            KeychainHelper.saveAccessToken(newToken)
        }
    }.resume()
}
```

**Android (Kotlin):**
```kotlin
suspend fun refreshToken(): Result<String> {
    val refreshToken = EncryptedSharedPreferencesHelper.getRefreshToken()
    
    return try {
        val response = authApi.refreshToken("Bearer $refreshToken")
        EncryptedSharedPreferencesHelper.saveAccessToken(response.access_token)
        Result.success(response.access_token)
    } catch (e: Exception) {
        Result.failure(e)
    }
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#31-1단계-인증-설정)

---

### 2.4 이미지 업로드 관련 문제

#### 2.4.1 파일 크기 초과

**증상**
- `413 Payload Too Large`: 파일 크기 초과
- 업로드 실패

**진단 단계**
1. 파일 크기 확인
2. 업로드 제한 확인

**해결 방법**

**iOS (Swift):**
```swift
func compressImage(_ image: UIImage, maxSizeKB: Int = 1024) -> Data? {
    var compression: CGFloat = 1.0
    var imageData = image.jpegData(compressionQuality: compression)
    
    while let data = imageData, data.count > maxSizeKB * 1024 && compression > 0.1 {
        compression -= 0.1
        imageData = image.jpegData(compressionQuality: compression)
    }
    
    return imageData
}
```

**Android (Kotlin):**
```kotlin
fun compressImage(bitmap: Bitmap, maxSizeKB: Int = 1024): ByteArray {
    val outputStream = ByteArrayOutputStream()
    var quality = 100
    
    while (outputStream.size() > maxSizeKB * 1024 && quality > 10) {
        outputStream.reset()
        bitmap.compress(Bitmap.CompressFormat.JPEG, quality, outputStream)
        quality -= 10
    }
    
    return outputStream.toByteArray()
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#32-이미지-업로드-및-분석-요청)

#### 2.4.2 파일 형식 지원 안 함

**증상**
- `415 Unsupported Media Type`: 지원하지 않는 형식
- 업로드 실패

**진단 단계**
1. 파일 형식 확인
2. 지원 형식 확인

**해결 방법**

**iOS (Swift):**
```swift
func convertToJPEG(image: UIImage) -> Data? {
    return image.jpegData(compressionQuality: 0.8)
}
```

**Android (Kotlin):**
```kotlin
fun convertToJPEG(bitmap: Bitmap): ByteArray {
    val outputStream = ByteArrayOutputStream()
    bitmap.compress(Bitmap.CompressFormat.JPEG, 80, outputStream)
    return outputStream.toByteArray()
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#32-이미지-업로드-및-분석-요청)

---

### 2.5 WebSocket 관련 문제

#### 2.5.1 WebSocket 연결 실패

**증상**
- WebSocket 연결 실패
- 인증 토큰 만료

**진단 단계**
1. 토큰 유효성 확인
2. 서버 WebSocket 상태 확인
3. 네트워크 연결 확인

**해결 방법**

**iOS (Swift):**
```swift
func connectWebSocket(jobId: String) {
    guard let token = KeychainHelper.getAccessToken() else {
        // 토큰 갱신 후 재시도
        refreshToken()
        return
    }
    
    var request = URLRequest(url: URL(string: "ws://localhost:80/v1/ws/analysis/\(jobId)")!)
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    
    socket = WebSocket(request: request)
    socket?.delegate = self
    socket?.connect()
}
```

**Android (Kotlin):**
```kotlin
fun connectWebSocket(jobId: String) {
    val token = EncryptedSharedPreferencesHelper.getAccessToken() ?: run {
        // 토큰 갱신 후 재시도
        lifecycleScope.launch { refreshToken() }
        return
    }
    
    val request = Request.Builder()
        .url("ws://localhost:80/v1/ws/analysis/$jobId")
        .addHeader("Authorization", "Bearer $token")
        .build()
    
    webSocket = client.newWebSocket(request, listener)
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#33-3단계-실시간-진행률-추적-websocket)

#### 2.5.2 백그라운드 연결 끊김

**증상**
- 앱 백그라운드 전환 시 연결 끊김
- 메시지 수신 안 됨

**진단 단계**
1. 백그라운드 모드 확인
2. WebSocket 연결 상태 확인

**해결 방법**

**iOS (Swift):**
```swift
// Background Task 사용
func setupBackgroundTask() {
    let task = URLSession.shared.downloadTask(with: url) { localURL, response, error in
        // 처리
    }
    task.resume()
    
    // Background Task 등록
    var bgTask: UIBackgroundTaskIdentifier = .invalid
    bgTask = UIApplication.shared.beginBackgroundTask(withName: "WebSocket") {
        UIApplication.shared.endBackgroundTask(bgTask)
    }
}
```

**Android (Kotlin):**
```kotlin
// Foreground Service 사용
class WebSocketService : Service() {
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // WebSocket 연결 유지
        return START_STICKY
    }
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#33-3단계-실시간-진행률-추적-websocket)

---

### 2.6 푸시 알림 관련 문제

#### 2.6.1 푸시 알림 수신 안 됨

**증상**
- 푸시 알림 수신 안 됨
- 토큰 등록 실패

**진단 단계**
1. 알림 권한 확인
2. 토큰 등록 확인
3. 서버 푸시 상태 확인

**해결 방법**

**iOS (Swift):**
```swift
func setupPushNotifications() {
    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
        if granted {
            UIApplication.shared.registerForRemoteNotifications()
        } else {
            // 권한 요청 안내
        }
    }
}

func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
    // 토큰을 서버에 전송
    registerPushToken(token: token)
}
```

**Android (Kotlin):**
```kotlin
class MyFirebaseMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        // 토큰을 서버에 전송
        registerPushToken(token)
    }
    
    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        // 푸시 알림 처리
        val notification = remoteMessage.notification
        showNotification(notification?.title, notification?.body)
    }
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#35-5단계-푸시-알림)

---

### 2.7 로컬 DB 관련 문제

#### 2.7.1 DB 저장 실패

**증상**
- DB 저장 실패
- 데이터 손실

**진단 단계**
1. DB 스키마 확인
2. 데이터 형식 확인
3. 저장 공간 확인

**해결 방법**

**iOS (Swift) - CoreData:**
```swift
func saveAnalysisResult(result: [String: Any], customerId: String) {
    let context = persistentContainer.viewContext
    
    let analysis = Analysis(context: context)
    analysis.jobId = result["job_id"] as? String
    analysis.customerId = customerId
    analysis.overallScore = (result["result"] as? [String: Any])?["overall_score"] as? Double ?? 0.0
    analysis.createdAt = Date()
    
    do {
        try context.save()
    } catch {
        print("Failed to save: \(error)")
        // 에러 처리
    }
}
```

**Android (Kotlin) - Room:**
```kotlin
@Dao
interface AnalysisDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insert(analysis: Analysis)
}

fun saveAnalysisResult(result: JSONObject, customerId: String) {
    val analysis = Analysis(
        jobId = result.getString("job_id"),
        customerId = customerId,
        overallScore = result.getJSONObject("result").getDouble("overall_score"),
        createdAt = System.currentTimeMillis()
    )
    
    try {
        analysisDao.insert(analysis)
    } catch (e: Exception) {
        println("Failed to save: $e")
        // 에러 처리
    }
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#34-4단계-결과-데이터-처리-및-저장)

---

### 2.8 오프라인 모드 관련 문제

#### 2.8.1 오프라인 요청 큐 실패

**증상**
- 오프라인 요청 큐 저장 실패
- 동기화 실패

**진단 단계**
1. 로컬 저장소 확인
2. 큐 크기 확인
3. 동기화 로직 확인

**해결 방법**

**iOS (Swift):**
```swift
class OfflineManager {
    private var pendingRequests: [[String: Any]] = []
    
    func saveRequestForOffline(request: [String: Any]) {
        pendingRequests.append(request)
        UserDefaults.standard.set(pendingRequests, forKey: "pendingRequests")
    }
    
    func syncPendingRequests() {
        for request in pendingRequests {
            // 요청 재전송
            sendRequest(request)
        }
        pendingRequests.removeAll()
        UserDefaults.standard.set(pendingRequests, forKey: "pendingRequests")
    }
}
```

**Android (Kotlin):**
```kotlin
class OfflineManager(private val context: Context) {
    private val prefs = context.getSharedPreferences("offline", Context.MODE_PRIVATE)
    
    fun saveRequestForOffline(request: Map<String, Any>) {
        val requests = getPendingRequests().toMutableList()
        requests.add(request)
        prefs.edit().putStringSet("pending_requests", requests.map { Gson().toJson(it) }.toSet()).apply()
    }
    
    fun syncPendingRequests() {
        val requests = getPendingRequests()
        requests.forEach { request ->
            // 요청 재전송
            sendRequest(request)
        }
        prefs.edit().remove("pending_requests").apply()
    }
}
```

**참조**
- [모바일 앱 연동 가이드](MOBILE_APP_INTEGRATION_GUIDE.md#4-오프라인-모드)

---

### 2.9 PCR 검사 관련 문제

#### 2.9.1 PCR 검사 요청 실패

**증상**
- PCR 검사 요청 시 400/422 오류
- 배송지 정보 누락 오류
- order_id 생성 실패

**진단 단계**
1. 배송지 정보 확인
2. customer_id 확인
3. API 토큰 확인

**해결 방법**

**iOS (Swift):**
```swift
// 배송지 정보 필수 확인
func validateShippingAddress(_ address: ShippingAddress) -> Bool {
    return !address.recipient.isEmpty &&
           !address.phone.isEmpty &&
           !address.address.isEmpty &&
           !address.zip_code.isEmpty
}

// PCR 검사 요청
func requestPCR(customerId: String, shippingAddress: ShippingAddress) {
    guard validateShippingAddress(shippingAddress) else {
        print("배송지 정보가 누락되었습니다.")
        return
    }
    
    PCRManager.shared.requestPCR(
        customerId: customerId,
        testType: "skin_analysis",
        shippingAddress: shippingAddress
    ) { result in
        switch result {
        case .success(let response):
            print("PCR 검사 요청 성공: \(response.request_id)")
            print("주문 ID: \(response.order_id)")
        case .failure(let error):
            print("PCR 검사 요청 실패: \(error)")
        }
    }
}
```

**Android (Kotlin):**
```kotlin
// 배송지 정보 필수 확인
fun validateShippingAddress(address: ShippingAddress): Boolean {
    return address.recipient.isNotEmpty() &&
           address.phone.isNotEmpty() &&
           address.address.isNotEmpty() &&
           address.zip_code.isNotEmpty()
}

// PCR 검사 요청
fun requestPCR(customerId: String, shippingAddress: ShippingAddress) {
    if (!validateShippingAddress(shippingAddress)) {
        Log.e("PCR", "배송지 정보가 누락되었습니다.")
        return
    }
    
    CoroutineScope(Dispatchers.IO).launch {
        val result = PCRManager(context).requestPCR(customerId, "skin_analysis", shippingAddress)
        result.onSuccess { response ->
            Log.d("PCR", "PCR 검사 요청 성공: ${response.request_id}")
            Log.d("PCR", "주문 ID: ${response.order_id}")
        }.onFailure { error ->
            Log.e("PCR", "PCR 검사 요청 실패: ${error.message}")
        }
    }
}
```

**참조**
- [모바일 앱 연동 가이드 - 6단계 PCR 검사](MOBILE_APP_INTEGRATION_GUIDE.md#36-6단계-pcr-검사-요청-및-결과-확인)
- [API 레퍼런스 - PCR 검사 API](../api/API_REFERENCE.md#1015-post-v1apppcrrequest)

#### 2.9.2 키트 발송 안 됨

**증상**
- PCR 검사 요청 성공했으나 키트 발송 안 됨
- order_id가 null 또는 비어있음
- 주문 상태가 "pending"인 상태 유지

**진단 단계**
1. order_id 확인
2. 주문 상태 확인
3. 배송지 정보 확인

**해결 방법**

```bash
# 주문 상태 확인
curl -X GET http://localhost:80/v1/orders/{order_id} \
  -H "Authorization: Bearer {token}"

# 주문 상태가 "pending"인 경우 재시도
curl -X POST http://localhost:80/v1/orders/{order_id}/process \
  -H "Authorization: Bearer {token}"
```

**참조**
- [주문 관리 가이드 - PCR 검사 키트 주문](ORDER_MANAGEMENT_GUIDE.md#pcr-검사-키트-주문)

#### 2.9.3 결과 조회 실패

**증상**
- PCR 검사 결과 조회 시 404 오류
- request_id 불일치
- 결과 데이터가 없음

**진단 단계**
1. request_id 확인
2. customer_id 확인
3. 검사 상태 확인

**해결 방법**

**iOS (Swift):**
```swift
// PCR 검사 이력 조회
func getPCRHistory(customerId: String) {
    PCRManager.shared.getPCRHistory(customerId: customerId) { result in
        switch result {
        case .success(let response):
            print("PCR 검사 이력: \(response.total_requests)개")
            for request in response.requests {
                print("요청 ID: \(request.request_id), 상태: \(request.status)")
            }
        case .failure(let error):
            print("PCR 검사 이력 조회 실패: \(error)")
        }
    }
}
```

**Android (Kotlin):**
```kotlin
// PCR 검사 이력 조회
fun getPCRHistory(customerId: String) {
    CoroutineScope(Dispatchers.IO).launch {
        val result = PCRManager(context).getPCRHistory(customerId)
        result.onSuccess { response ->
            Log.d("PCR", "PCR 검사 이력: ${response.total_requests}개")
            response.requests.forEach { request ->
                Log.d("PCR", "요청 ID: ${request.request_id}, 상태: ${request.status}")
            }
        }.onFailure { error ->
            Log.e("PCR", "PCR 검사 이력 조회 실패: ${error.message}")
        }
    }
}
```

**참조**
- [모바일 앱 연동 가이드 - 6단계 PCR 검사](MOBILE_APP_INTEGRATION_GUIDE.md#36-6단계-pcr-검사-요청-및-결과-확인)

#### 2.9.4 상담 예약 실패

**증상**
- 상담 예약 시 400/422 오류
- scheduled_at 형식 오류
- request_id 불일치

**진단 단계**
1. request_id 확인
2. scheduled_at 형식 확인
3. 상담 가능 시간 확인

**해결 방법**

**iOS (Swift):**
```swift
// 상담 예약
func bookConsultation(customerId: String, requestId: String, scheduledAt: Date) {
    let formatter = ISO8601DateFormatter()
    let scheduledAtString = formatter.string(from: scheduledAt)
    
    PCRManager.shared.bookConsultation(
        customerId: customerId,
        requestId: requestId,
        scheduledAt: scheduledAtString,
        notes: "상담 희망"
    ) { result in
        switch result {
        case .success(let response):
            print("상담 예약 성공: \(response.consultation_id)")
        case .failure(let error):
            print("상담 예약 실패: \(error)")
        }
    }
}
```

**Android (Kotlin):**
```kotlin
// 상담 예약
fun bookConsultation(customerId: String, requestId: String, scheduledAt: LocalDateTime) {
    val formatter = DateTimeFormatter.ISO_DATE_TIME
    val scheduledAtString = scheduledAt.format(formatter)
    
    CoroutineScope(Dispatchers.IO).launch {
        val result = PCRManager(context).bookConsultation(
            customerId, requestId, scheduledAtString, "상담 희망"
        )
        result.onSuccess { response ->
            Log.d("PCR", "상담 예약 성공: ${response.consultation_id}")
        }.onFailure { error ->
            Log.e("PCR", "상담 예약 실패: ${error.message}")
        }
    }
}
```

**참조**
- [모바일 앱 연동 가이드 - 6단계 PCR 검사](MOBILE_APP_INTEGRATION_GUIDE.md#36-6단계-pcr-검사-요청-및-결과-확인)

---

### 2.10 주문 관련 문제

#### 2.10.1 기성품 목록 조회 실패

**증상**
- 기성품 목록 조회 시 401/403 오류
- 인증 토큰 만료
- 권한 부족

**진단 단계**
1. API 토큰 확인
2. 토큰 만료 시간 확인
3. 권한 확인

**해결 방법**

**iOS (Swift):**
```swift
// 기성품 목록 조회
func getReadyMadeProducts() {
    ProductManager.shared.getReadyMadeProducts { result in
        switch result {
        case .success(let response):
            print("기성품 목록: \(response.total_products)개")
            for product in response.ready_made_products {
                print("제품: \(product.product_name), 재고: \(product.stock_quantity)")
            }
        case .failure(let error):
            if let httpResponse = error as? HTTPURLResponse, httpResponse.statusCode == 401 {
                print("토큰 만료. 재로그인 필요.")
                self.relogin()
            } else {
                print("기성품 목록 조회 실패: \(error)")
            }
        }
    }
}
```

**Android (Kotlin):**
```kotlin
// 기성품 목록 조회
fun getReadyMadeProducts() {
    CoroutineScope(Dispatchers.IO).launch {
        val result = ProductManager(context).getReadyMadeProducts()
        result.onSuccess { response ->
            Log.d("Product", "기성품 목록: ${response.total_products}개")
            response.ready_made_products.forEach { product ->
                Log.d("Product", "제품: ${product.product_name}, 재고: ${product.stock_quantity}")
            }
        }.onFailure { error ->
            if (error is HttpException && error.code() == 401) {
                Log.e("Product", "토큰 만료. 재로그인 필요.")
                relogin()
            } else {
                Log.e("Product", "기성품 목록 조회 실패: ${error.message}")
            }
        }
    }
}
```

**참조**
- [모바일 앱 연동 가이드 - 7단계 기성품 구매](MOBILE_APP_INTEGRATION_GUIDE.md#37-7단계-기성품-구매)

#### 2.10.2 재고 부족

**증상**
- 주문 생성 시 재고 부족 오류
- stock_quantity = 0
- 422 Unprocessable Entity

**진단 단계**
1. 재고 확인
2. 다른 제품 확인
3. 재고 보충 확인

**해결 방법**

**iOS (Swift):**
```swift
// 재고 확인 후 주문
func checkStockAndOrder(productId: String, quantity: Int) {
    ProductManager.shared.getReadyMadeProducts { result in
        switch result {
        case .success(let response):
            if let product = response.ready_made_products.first(where: { $0.product_id == productId }) {
                if product.stock_quantity >= quantity {
                    print("재고 충분. 주문 진행.")
                    self.createOrder(productId: productId, quantity: quantity)
                } else {
                    print("재고 부족. 현재 재고: \(product.stock_quantity)")
                    // 다른 제품 추천
                }
            }
        case .failure(let error):
            print("기성품 목록 조회 실패: \(error)")
        }
    }
}
```

**Android (Kotlin):**
```kotlin
// 재고 확인 후 주문
fun checkStockAndOrder(productId: String, quantity: Int) {
    CoroutineScope(Dispatchers.IO).launch {
        val result = ProductManager(context).getReadyMadeProducts()
        result.onSuccess { response ->
            val product = response.ready_made_products.find { it.product_id == productId }
            if (product != null) {
                if (product.stock_quantity >= quantity) {
                    Log.d("Product", "재고 충분. 주문 진행.")
                    createOrder(productId, quantity)
                } else {
                    Log.e("Product", "재고 부족. 현재 재고: ${product.stock_quantity}")
                    // 다른 제품 추천
                }
            }
        }.onFailure { error ->
            Log.e("Product", "기성품 목록 조회 실패: ${error.message}")
        }
    }
}
```

**참조**
- [주문 관리 가이드 - 기성품 주문](ORDER_MANAGEMENT_GUIDE.md#기성품-주문)

#### 2.10.3 주문 생성 실패

**증상**
- 주문 생성 시 400/422 오류
- 배송지 정보 누락
- 결제 정보 누락

**진단 단계**
1. 배송지 정보 확인
2. 결제 정보 확인
3. customer_id 확인

**해결 방법**

**iOS (Swift):**
```swift
// 주문 생성
func createOrder(customerId: String, items: [OrderItem], shippingAddress: ShippingAddress, paymentMethod: String) {
    guard validateShippingAddress(shippingAddress) else {
        print("배송지 정보가 누락되었습니다.")
        return
    }
    
    guard !paymentMethod.isEmpty else {
        print("결제 방법이 누락되었습니다.")
        return
    }
    
    OrderManager.shared.createOrder(
        customerId: customerId,
        items: items,
        shippingAddress: shippingAddress,
        paymentMethod: paymentMethod,
        recommendationSource: "ready_made_product"
    ) { result in
        switch result {
        case .success(let response):
            print("주문 생성 성공: \(response.order_id)")
            print("결제 URL: \(response.payment_url)")
        case .failure(let error):
            print("주문 생성 실패: \(error)")
        }
    }
}
```

**Android (Kotlin):**
```kotlin
// 주문 생성
fun createOrder(customerId: String, items: List<OrderItem>, shippingAddress: ShippingAddress, paymentMethod: String) {
    if (!validateShippingAddress(shippingAddress)) {
        Log.e("Order", "배송지 정보가 누락되었습니다.")
        return
    }
    
    if (paymentMethod.isEmpty()) {
        Log.e("Order", "결제 방법이 누락되었습니다.")
        return
    }
    
    CoroutineScope(Dispatchers.IO).launch {
        val result = OrderManager(context).createOrder(
            customerId, items, shippingAddress, paymentMethod, "ready_made_product"
        )
        result.onSuccess { response ->
            Log.d("Order", "주문 생성 성공: ${response.order_id}")
            Log.d("Order", "결제 URL: ${response.payment_url}")
        }.onFailure { error ->
            Log.e("Order", "주문 생성 실패: ${error.message}")
        }
    }
}
```

**참조**
- [모바일 앱 연동 가이드 - 7단계 기성품 구매](MOBILE_APP_INTEGRATION_GUIDE.md#37-7단계-기성품-구매)
- [주문 관리 가이드 - 기성품 주문](ORDER_MANAGEMENT_GUIDE.md#기성품-주문)

---

## 3. 모니터링 지표

### 3.1 웹서버 모니터링 지표

| 지표 | 설명 | 정상 범위 | 경고 | 위험 |
|------|------|----------|------|------|
| CPU 사용량 | 웹서버 CPU 사용량 | < 70% | 70-90% | > 90% |
| 메모리 사용량 | 웹서버 메모리 사용량 | < 80% | 80-90% | > 90% |
| 디스크 사용량 | 웹서버 디스크 사용량 | < 80% | 80-90% | > 90% |
| API 응답 시간 | 웹서버 API 응답 시간 | < 1s | 1-5s | > 5s |
| 엔진 서버 응답 시간 | 엔진 서버 API 응답 시간 | < 5s | 5-10s | > 10s |
| DB 쿼리 시간 | 웹서버 DB 쿼리 시간 | < 100ms | 100-500ms | > 500ms |

### 3.2 모바일 앱 모니터링 지표

| 지표 | 설명 | 정상 범위 | 경고 | 위험 |
|------|------|----------|------|------|
| API 응답 시간 | 모바일 API 응답 시간 | < 2s | 2-5s | > 5s |
| 분석 완료 시간 | 전체 분석 시간 | < 30s | 30-60s | > 60s |
| 에러율 | API 호출 실패율 | < 5% | 5-10% | > 10% |
| 배터리 소모 | 분석 중 배터리 소모 | < 10% | 10-20% | > 20% |
| 네트워크 사용량 | 분석 중 네트워크 사용량 | < 10MB | 10-20MB | > 20MB |

---

## 4. 로그 확인

### 4.1 웹서버 로그

```
logs/
├── server.log              # 웹서버 로그
├── api_requests.log        # API 요청 로그
├── websocket.log          # WebSocket 로그
├── push_notifications.log  # 푸시 알림 로그
└── error.log              # 에러 로그
```

### 4.2 모바일 앱 로그

**iOS:**
```bash
# Console.app 사용
# 또는
xcrun simctl spawn booted log stream --level debug
```

**Android:**
```bash
# Logcat 사용
adb logcat
# 또는
adb logcat -s SkinLensAPI
```

---

## 5. 긴급 연락처

### 5.1 웹서버

| 역할 | 이름 | 연락처 |
|------|------|--------|
| 웹서버 관리자 | - | - |
| DevOps 엔지니어 | - | - |
| DBA | - | - |

### 5.2 모바일 앱

| 역할 | 이름 | 연락처 |
|------|------|--------|
| iOS 개발팀 리드 | - | - |
| Android 개발팀 리드 | - | - |
| QA 엔지니어 | - | - |

---

**문서 생성일**: 2026-06-01  
**작성자**: Cascade AI Assistant  
**프로젝트**: SkinLens v1
3. 방화벽 확인

#### 해결 방법

```bash
# 네트워크 연결 확인
ping google.com

# 포트 확인
netstat -tlnp | grep 8000

# 방화벽 확인
sudo ufw status

# 포트 열기
sudo ufw allow 8000

# DNS 확인
nslookup google.com

# 서비스 재시작
systemctl restart networking
```

---

## 9. 로그 확인

### 9.1 로그 파일 위치

```
logs/
├── server.log              # 서버 로그
├── api_requests.log        # API 요청 로그
├── analyzer.log            # 분석기 로그
├── safety_net.log          # SafetyNet 로그
├── upload.log              # 업로드 로그
├── llm.log                 # LLM 로그
├── supabase_sync.log       # Supabase 동기화 로그
└── error.log              # 에러 로그
```

### 9.2 로그 확인 명령어

```bash
# 실시간 로그 확인
tail -f logs/server.log

# 에러 로그만 확인
tail -f logs/error.log

# 최근 100줄 확인
tail -n 100 logs/server.log

# 특정 키워드 검색
grep "ERROR" logs/server.log

# 날짜별 로그 확인
grep "2026-06-01" logs/server.log
```

### 9.3 로그 레벨 설정

```bash
# config.json에서 로그 레벨 설정
{
  "logging": {
    "level": "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  }
}
```

---

## 10. 모니터링 지표

### 10.1 핵심 지표

| 지표 | 정상 범위 | 경고 | 위험 |
|------|----------|------|------|
| CPU 사용량 | < 70% | 70-90% | > 90% |
| 메모리 사용량 | < 80% | 80-90% | > 90% |
| 디스크 사용량 | < 80% | 80-90% | > 90% |
| API 응답 시간 | < 1s | 1-5s | > 5s |
| DB 쿼리 시간 | < 100ms | 100-500ms | > 500ms |
| 분석 시간 | < 10s | 10-30s | > 30s |

### 10.2 모니터링 도구

```bash
# 시스템 모니터링
htop
iotop
nethogs

# 애플리케이션 모니터링
curl http://localhost:8000/metrics
curl http://localhost:8000/health

# 로그 모니터링
tail -f logs/server.log
```

---

## 11. 긴급 연락처

### 11.1 내부 연락처

| 역할 | 이름 | 연락처 |
|------|------|--------|
| 시스템 관리자 | - | - |
| 개발팀 리드 | - | - |
| DBA | - | - |
| DevOps 엔지니어 | - | - |

### 11.2 외부 연락처

| 서비스 | 연락처 |
|--------|--------|
| 클라우드 제공자 | - |
| LLM API 지원 | - |
| Supabase 지원 | - |

---

## 12. 에스컬레이션 절차

### 12.1 심각도 수준

**Level 1 (낮음)**
- 영향: 일부 사용자
- 해결 시간: 24시간 이내
- 예: 단일 API 오류

**Level 2 (중간)**
- 영향: 다수 사용자
- 해결 시간: 4시간 이내
- 예: DB 성능 저하

**Level 3 (높음)**
- 영향: 전체 서비스
- 해결 시간: 1시간 이내
- 예: 서버 다운

**Level 4 (긴급)**
- 영향: 비즈니스 중단
- 해결 시간: 15분 이내
- 예: 데이터 손실

### 12.2 에스컬레이션 단계

1. **자체 해결 시도** (30분)
   - 로그 확인
   - 문서 참조
   - 일반적인 해결 방법 시도

2. **팀 내 공유** (1시간)
   - 슬랙/팀 채팅 공유
   - 동료 협력 요청
   - 코드 리뷰

3. **관리자 에스컬레이션** (2시간)
   - 시스템 관리자 연락
   - DevOps 엔지니어 연락
   - 인프라 점검

4. **경영진 보고** (4시간)
   - 상황 보고
   - 영향 평가
   - 해결 계획

---

## 13. 예방 조치

### 13.1 정기 점검

- **매일**: 로그 확인, 시스템 리소스 확인
- **매주**: 백업 확인, 보안 패치 확인
- **매월**: 성능 튜닝, 용량 계획

### 13.2 모니터링 설정

- Prometheus + Grafana
- ELK Stack (Elasticsearch, Logstash, Kibana)
- PagerDuty (알림)

### 13.3 백업 전략

- **DB**: 매일 자동 백업
- **코드**: Git 저장소
- **설정**: config.json 버전 관리
- **로그**: 30일 보관

---

## 14. 부록

### 14.1 유용한 명령어

```bash
# 시스템 정보
uname -a
df -h
free -h
top

# 프로세스 관리
ps aux
kill -9 <PID>
systemctl status skinlens-server

# 네트워크
ping google.com
netstat -tlnp
curl -I http://localhost:8000

# DB
sqlite3 data/skin_analysis.db
.tables
.schema <table_name>
SELECT * FROM <table_name> LIMIT 10;

# 로그
tail -f logs/server.log
grep "ERROR" logs/*.log
find logs/ -name "*.log" -mtime +7 -delete
```

### 14.2 구성 파일

- `config/config.json`: 메인 설정
- `config/logging.json`: 로깅 설정
- `config/auth.json`: 인증 설정
- `config/db.json`: DB 설정

### 14.3 참고 문서

- [API 문서](../api/API_REFERENCE.md)
- [테스트 가이드](TESTING_GUIDE.md)
- [배포 가이드](../ops/DEPLOYMENT_GUIDE.md)
- [아키텍처 문서](ARCHITECTURE.md)

---

**문서 생성일**: 2026-06-01  
**작성자**: Cascade AI Assistant  
**프로젝트**: SkinLens v1
