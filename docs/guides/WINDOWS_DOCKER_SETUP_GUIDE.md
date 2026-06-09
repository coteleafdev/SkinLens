# Windows Docker 설치 가이드

> **문서 버전:** 1.0.0  
> **대상 운영체제:** Windows 10/11  
> **마지막 업데이트:** 2026-06-04  
> **상태:** 활성  
> **대상 독자**: 개발자

---

## 개요

이 문서는 Windows에 Docker를 설치하여 SkinLens 시뮬레이션을 실행하기 위한 절차를 안내합니다.

## 1. 사전 요구사항

### 1.1 시스템 요구사항
- Windows 10 64-bit: Pro, Enterprise, 또는 Education (버전 1903 이상)
- Windows 11 64-bit: Home, Pro, Enterprise, 또는 Education
- BIOS에서 가상화 활성화 (필수)
- 최소 4GB RAM (권장 8GB 이상)

### 1.2 BIOS 가상화 설정

#### 1.2.1 가상화 활성화 필요성
- Docker Desktop이 WSL 2 백엔드를 사용
- WSL 2는 가상화 기술(Hyper-V) 필요
- BIOS에서 가상화가 비활성화되면 Docker 작동 안 함

#### 1.2.2 BIOS 진입 방법
컴퓨터 부팅 시 키 누르기 (제조사별 상이):

| 제조사 | 진입 키 |
|--------|---------|
| Dell | F2 또는 F12 |
| HP | F10 또는 ESC |
| Lenovo | F1 또는 F2 |
| ASUS | F2 또는 DEL |
| Samsung | F2 |

#### 1.2.3 가상화 활성화 절차
1. BIOS 메뉴에서 다음 설정 찾기:
   - **Intel VT-x** 또는 **Intel Virtualization Technology**
   - **AMD-V** 또는 **SVM Mode**
   - **Virtualization Technology** 또는 **VT-x**

2. 설정을 **Enabled**로 변경

3. F10으로 저장 후 재부팅

#### 1.2.4 가상화 설정 확인
```bash
# PowerShell에서 실행
systeminfo

# 출력에서 "Hyper-V 요구 사항" 섹션 확인
# "가상화 사용"이 "예"로 표시되어야 함
```

#### 1.2.5 참고 사항
- 일부 노트북은 BIOS가 아니라 UEFI에서 설정
- 보안 부팅(Secure Boot)이 활성화되어 있으면 문제가 될 수 있음
- 문제 발생 시 보안 부팅 일시 비활성화 후 다시 시도

## 2. Docker Desktop 설치

### 2.1 다운로드
1. https://www.docker.com/products/docker-desktop/ 접속
2. Windows용 Docker Desktop 다운로드

### 2.2 설치 절차
```bash
# 다운로드한 설치 파일 실행 (Docker Desktop Installer.exe)
# 설치 마법사 안내에 따라 설치 진행
# 설치 완료 후 시스템 재부팅
```

### 2.3 WSL 2 활성화 (Windows 10/11)
```bash
# PowerShell을 관리자 권한으로 실행
wsl --install
# 재부팅 후 WSL 2 설치 완료
```

### 2.4 Docker Desktop 시작
1. 시작 메뉴에서 Docker Desktop 실행
2. 트레이 아이콘이 녹색으로 변경되면 정상 작동

## 3. 설치 확인

### 3.1 Docker 버전 확인
```bash
# PowerShell 또는 CMD에서 실행
docker --version
docker-compose --version
```

### 3.2 Docker 실행 테스트
```bash
# 테스트 컨테이너 실행
docker run hello-world

# 정상 작동 시 다음 메시지 출력:
# Hello from Docker!
```

## 4. Python 설치 필요 여부

### 4.1 Docker로 시뮬레이션만 하는 경우
- **Python 설치 불필요**
- Docker 컨테이너 내부에 이미 Python 환경이 포함됨
- Dockerfile에 Python 3.10이 포함되어 있음

### 4.2 로컬에서 Python 스크립트를 직접 실행하는 경우
- **Python 설치 필요**
- 예: `python run_engine_server.py`
- 예: `python -m src.server.server`

### 4.3 결론
**Docker 시뮬레이션만 하려면**: Docker Desktop만 설치하면 됩니다. Python은 컨테이너 내부에 포함되어 있습니다.

## 5. SkinLens 시뮬레이션 실행

### 5.1 프로젝트 경로 이동
```bash
cd c:\Project\SkinLens v1
```

### 5.2 엔진 서버만 실행
```bash
docker-compose -f docker-compose.engine.yml up -d
```

### 5.3 전체 시스템 실행
```bash
docker-compose up -d
```

### 5.4 상태 확인
```bash
# 컨테이너 상태 확인
docker ps

# 로그 확인
docker logs skinlens-engine
docker logs skinlens-web
```

### 5.5 컨테이너 중지
```bash
# 전체 시스템 중지
docker-compose down

# 엔진 서버만 중지
docker-compose -f docker-compose.engine.yml down
```

## 6. 문제 해결

### 6.1 Docker Desktop 시작 실패
- BIOS 가상화 설정 확인
- WSL 2 설치 확인
- Windows 업데이트 확인

### 6.2 컨테이너 실행 실패
- 포트 충돌 확인 (8000, 8001)
- 디스크 공간 확인
- Docker Desktop 재시작

### 6.3 WSL 2 관련 문제
```bash
# WSL 업데이트
wsl --update

# WSL 재설치
wsl --unregister docker-desktop
wsl --unregister docker-desktop-data
```

## 7. 참고 문서

- [Docker 공식 문서](https://docs.docker.com/)
- [Docker Compose 문서](https://docs.docker.com/compose/)
- [WSL 2 설치 가이드](https://docs.microsoft.com/ko-kr/windows/wsl/install)
- [WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md](../guides/WEB_SERVER_ENGINE_INTEGRATION_GUIDE.md)

---

## 부록

### A. 빠른 설치 체크리스트

- [ ] BIOS 가상화 활성화
- [ ] Windows 업데이트 완료
- [ ] Docker Desktop 다운로드
- [ ] Docker Desktop 설치
- [ ] 시스템 재부팅
- [ ] WSL 2 설치
- [ ] Docker Desktop 시작
- [ ] Docker 버전 확인
- [ ] 테스트 컨테이너 실행
- [ ] SkinLens 시뮬레이션 실행

### B. 유용한 Docker 명령어

```bash
# 컨테이너 목록 확인
docker ps -a

# 컨테이너 로그 실시간 확인
docker logs -f <컨테이너 이름>

# 컨테이너 진입
docker exec -it <컨테이너 이름> bash

# 이미지 목록 확인
docker images

# 불필요한 리소스 정리
docker system prune -a
```
