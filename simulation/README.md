# 시뮬레이션

> **문서 버전:** 1.0.0  
> **마지막 업데이트:** 2026-06-03

이 디렉토리는 SkinLens 프로젝트의 모든 시뮬레이션 관련 파일을 포함합니다.

## 구조

```
simulation/
├── docker_simulation.py          # Docker 시뮬레이션 스크립트
├── DOCKER_SIMULATION_GUIDE.md    # Docker 시뮬레이션 가이드
├── run_server_tests.bat          # 서버 테스트 실행 배치 파일
├── SERVER_TEST_GUIDE.md          # 서버 테스트 가이드
├── TESTING_AND_SIMULATION_GUIDE.md # 전체 테스트 및 시뮬레이션 종합 가이드
└── README.md                     # 이 파일
```

## 시뮬레이션 유형

### 1. Docker 시뮬레이션

Docker 컨테이너를 사용하여 SkinLens 엔진 서버와 웹서버를 배포하고 테스트합니다.

**스크립트**: `docker_simulation.py`

**주요 기능**:
- Docker 컨테이너 관리 (빌드, 시작, 중지, 재시작)
- 헬스 체크
- 로그 확인
- 분석 테스트 (사용자 정보 + 이미지 입력)
- 전체 시뮬레이션 자동화

**사용법**:
```bash
# 전체 시뮬레이션
python simulation/docker_simulation.py simulate

# 분석 테스트
python simulation/docker_simulation.py test --image /path/to/image.jpg

# 상태 확인
python simulation/docker_simulation.py status
```

**가이드**: [DOCKER_SIMULATION_GUIDE.md](DOCKER_SIMULATION_GUIDE.md)

### 2. 서버 테스트 시뮬레이션

서버 API 테스트를 자동화하여 실행합니다.

**스크립트**: `run_server_tests.bat`

**주요 기능**:
- 환경 변수 자동 설정
- 의존성 확인
- 서버 테스트 실행 (test_server.py, test_auth_api.py, test_admin_api.py, test_health_api.py, test_orders_api.py)
- 커버리지 보고서 생성

**사용법**:
```bash
# 서버 테스트 실행
simulation\run_server_tests.bat
```

**가이드**: [SERVER_TEST_GUIDE.md](SERVER_TEST_GUIDE.md)

### 3. 전체 테스트 및 시뮬레이션 종합 가이드

모든 테스트 및 시뮬레이션 유형을 통합적으로 설명하는 종합 가이드입니다.

**문서**: `COMPREHENSIVE_GUIDE.md`

**주요 내용**:
- 테스트 및 시뮬레이션 유형 개요
- 사전 요구사항
- 빠른 시작 가이드
- 상세 절차 (Docker, 서버, 단위 테스트)
- 통합 워크플로우 (개발 환경, 배포 전, CI/CD)
- 트러블슈팅 가이드
- CI/CD 통합 예시

**사용법**:
```bash
# 종합 가이드 참조
# 개발 환경 테스트 워크플로우 따르기
# 배포 전 테스트 워크플로우 따르기
```

**가이드**: [TESTING_AND_SIMULATION_GUIDE.md](TESTING_AND_SIMULATION_GUIDE.md)

## 향후 확장

추가적인 시뮬레이션 유형이 이 디렉토리에 추가될 예정입니다:

- 자체 시뮬레이션 (로컬 환경)
- 성능 벤치마킹 시뮬레이션
- 부하 테스트 시뮬레이션
- 통합 테스트 시뮬레이션

## 참고

- 시뮬레이션 스크립트는 프로젝트 루트에서 실행해야 합니다.
- Docker 시뮬레이션을 위해서는 Docker와 Docker Compose가 설치되어 있어야 합니다.
- 서버 테스트를 위해서는 pytest, pytest-asyncio, pytest-cov, httpx가 설치되어 있어야 합니다.
- 자세한 사용법은 각 시뮬레이션의 가이드 문서를 참조하세요.
