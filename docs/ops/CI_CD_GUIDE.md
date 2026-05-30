# CI/CD 통합 가이드

이 문서는 SkinLens v1 프로젝트의 CI/CD 통합 방법을 설명합니다.

## 목차

1. [개요](#개요)
2. [GitHub Actions 워크플로우](#github-actions-워크플로우)
3. [로컬 CI 시뮬레이션](#로컬-ci-시뮬레이션)
4. [커버리지 리포트](#커버리지-리포트)
5. [트러블슈팅](#트러블슈팅)

---

## 개요

**현재 개발 환경**: Python 3.12

SkinLens v1은 GitHub Actions를 사용하여 CI/CD 파이프라인을 구현합니다. 현재 다음 워크플로우가 구성되어 있습니다:

- **test-all.yml**: 전체 테스트 실행 (모든 Python 버전)
- **test-server.yml**: 서버 테스트 실행 (서버 관련 변경 시만)

### CI/CD 철학

1. **자동화**: 모든 푸시와 PR에 대해 자동으로 테스트 실행
2. **다중 버전**: Python 3.9, 3.10, 3.11, 3.12에서 테스트
3. **커버리지**: Codecov를 통한 커버리지 추적
4. **캐싱**: pip 의존성 캐싱으로 빌드 시간 단축
5. **조건부 실행**: 변경된 파일에 따라 워크플로우 선택적 실행

---

## GitHub Actions 워크플로우

### test-all.yml - 전체 테스트 워크플로우

이 워크플로우는 모든 테스트를 실행합니다.

#### 트리거 조건

```yaml
on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
```

- `main` 또는 `develop` 브랜치로 푸시 시 실행
- `main` 또는 `develop` 브랜치로 PR 생성 시 실행

#### 실행 단계

1. **코드 체크아웃**: 저장소 코드 가져오기
2. **Python 설정**: Python 3.9, 3.10, 3.11, 3.12 설정
3. **의존성 캐싱**: pip 캐시로 빌드 시간 단축
4. **의존성 설치**: pytest, pytest-asyncio, pytest-cov, httpx 설치
5. **환경 변수 설정**: 테스트용 환경 변수 설정
6. **테스트 실행**: 모든 테스트 실행 및 커버리지 생성
7. **커버리지 업로드**: Codecov에 커버리지 업로드
8. **결과 아카이빙**: 테스트 결과 아카이빙

#### 환경 변수

```yaml
JWT_SECRET_KEY=test-secret-for-ci
SKIN_API_MAX_UPLOAD_BYTES=10485760
ADMIN_PASSWORD=admin123
ANALYST_PASSWORD=analyst123
```

### test-server.yml - 서버 테스트 워크플로우

이 워크플로우는 서버 관련 테스트만 실행합니다.

#### 트리거 조건

```yaml
on:
  push:
    branches: [ main, develop ]
    paths:
      - 'src/server/**'
      - 'tests/test_server.py'
      - 'tests/test_*_api.py'
  pull_request:
    branches: [ main, develop ]
    paths:
      - 'src/server/**'
      - 'tests/test_server.py'
      - 'tests/test_*_api.py'
```

- 서버 소스 코드 또는 서버 테스트 파일 변경 시에만 실행
- 불필요한 테스트 실행 방지로 CI 시간 단축

#### 실행 단계

test-all.yml과 동일하지만, 다음 테스트만 실행:

```bash
python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py
```

---

## 로컬 CI 시뮬레이션

### 전체 테스트 실행

GitHub Actions와 동일한 환경에서 로컬에서 테스트를 실행하려면:

```bash
# 1. 환경 변수 설정
export JWT_SECRET_KEY=test-secret-for-ci
export SKIN_API_MAX_UPLOAD_BYTES=10485760
export ADMIN_PASSWORD=admin123
export ANALYST_PASSWORD=analyst123

# 2. 의존성 설치
pip install pytest pytest-asyncio pytest-cov httpx

# 3. 테스트 실행
python -m pytest tests/ -v --cov=src --cov-report=xml --cov-report=term-missing

# 4. 커버리지 리포트 확인
# HTML 리포트: htmlcov/index.html
# XML 리포트: coverage.xml
```

또는 배치 파일 사용:

```bash
# Windows
scripts\run_all_tests.bat

# Linux/Mac (bash 스크립트 필요)
bash scripts/run_all_tests.sh
```

### 서버 테스트 실행

서버 테스트만 실행하려면:

```bash
# 1. 환경 변수 설정
export JWT_SECRET_KEY=test-secret-for-ci
export SKIN_API_MAX_UPLOAD_BYTES=10485760
export ADMIN_PASSWORD=admin123
export ANALYST_PASSWORD=analyst123

# 2. 의존성 설치
pip install pytest pytest-asyncio pytest-cov httpx

# 3. 서버 테스트 실행
python -m pytest tests/test_server.py tests/test_auth_api.py tests/test_admin_api.py tests/test_health_api.py tests/test_orders_api.py -v --cov=src/server --cov-report=xml --cov-report=term-missing
```

또는 배치 파일 사용:

```bash
# Windows
scripts\run_server_tests.bat
```

### 특정 Python 버전 테스트

특정 Python 버전에서 테스트하려면:

```bash
# Python 3.9
py -3.9 -m pytest tests/ -v

# Python 3.10
py -3.10 -m pytest tests/ -v

# Python 3.11
py -3.11 -m pytest tests/ -v

# Python 3.12
py -3.12 -m pytest tests/ -v
```

---

## 커버리지 리포트

### Codecov 설정

Codecov를 사용하려면:

1. **Codecov 계정 생성**: https://codecov.io/
2. **저장소 연결**: GitHub 저장소를 Codecov에 연결
3. **토큰 설정**: Codecov 토큰을 GitHub Secrets에 추가
   - Secret 이름: `CODECOV_TOKEN`
   - Secret 값: Codecov에서 제공하는 토큰

### 커버리지 확인

#### GitHub Actions에서

PR 또는 푸시 후 GitHub Actions 탭에서 커버리지 리포트를 확인할 수 있습니다.

#### Codecov에서

Codecov 대시보드에서 다음 정보를 확인할 수 있습니다:

- 전체 커버리지 비율
- 파일별 커버리지
- 라인별 커버리지
- 커버리지 추이 (시간에 따른 변화)
- PR별 커버리지 변화

#### 로컬에서

```bash
# HTML 리포트 생성
python -m pytest tests/ --cov=src --cov-report=html

# 브라우저에서 열기
# Linux/Mac
open htmlcov/index.html

# Windows
start htmlcov/index.html
```

### 커버리지 목표

| 모듈 | 목표 커버리지 | 현재 상태 |
|------|--------------|----------|
| CLI 파이프라인 | 80%+ | ✅ |
| FastAPI 서버 | 80%+ | ✅ |
| 데이터베이스 기능 | 80%+ | ✅ |
| 피부 분석 애널라이저 | 80%+ | ✅ |
| 인증 API | 80%+ | ✅ |
| 관리자 API | 80%+ | ✅ |
| 헬스 체크 API | 80%+ | ✅ |
| 주문 API | 80%+ | ✅ |
| Repository 계층 | 80%+ | ✅ |
| Scoring 모듈 | 80%+ | ✅ |
| 자동 복구 엔진 | 80%+ | ✅ |

---

## 트러블슈팅

### GitHub Actions 실패

#### 1. 의존성 설치 실패

**문제**: pip 설치 실패
```yaml
Error: Could not find a version that satisfies the requirement
```

**해결**:
- `requirements.txt` 파일 확인
- Python 버전 호환성 확인
- 패키지 이름 오타 확인

#### 2. 환경 변수 누락

**문제**: 환경 변수가 설정되지 않음
```yaml
KeyError: 'JWT_SECRET_KEY'
```

**해결**:
- 워크플로우 파일에 환경 변수 설정 확인
- GitHub Secrets에 필요한 변수 추가

#### 3. 테스트 실패

**문제**: 로컬에서는 통과하지만 CI에서 실패
```yaml
FAILED tests/test_example.py::test_case
```

**해결**:
- 환경 차이 확인 (Python 버전, OS)
- 의존성 버전 확인
- 파일 경로 문제 확인 (절대 경로 vs 상대 경로)
- 타이밍 관련 문제 확인 (sleep 추가 등)

#### 4. 커버리지 업로드 실패

**문제**: Codecov 업로드 실패
```yaml
Error: Failed to upload coverage reports
```

**해결**:
- `CODECOV_TOKEN` Secret 확인
- Codecov 계정 확인
- 네트워크 연결 확인

### 로컬 CI 시뮬레이션 실패

#### 1. Python 버전 문제

**문제**: 특정 Python 버전이 설치되지 않음
```bash
py -3.11: command not found
```

**해결**:
```bash
# Python 다중 버전 설치 (pyenv 사용)
# Linux/Mac
brew install pyenv
pyenv install 3.9.0
pyenv install 3.10.0
pyenv install 3.11.0
pyenv install 3.12.0

# Windows
# Python.org에서 각 버전 다운로드 및 설치
```

#### 2. 의존성 충돌

**문제**: 의존성 버전 충돌
```bash
ERROR: pip's dependency resolver does not currently take into account all the packages that are installed
```

**해결**:
```bash
# 가상 환경 사용
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows

# 의존성 재설치
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 추가 리소스

- **GitHub Actions 문서**: https://docs.github.com/en/actions
- **Codecov 문서**: https://docs.codecov.com/
- **pytest 문서**: https://docs.pytest.org/
- **테스트 가이드**: `tests/README.md`
- **서버 테스트 가이드**: `tests/README_SERVER_TESTS.md`

---

## 모범 사례

### PR 생성 전

1. **로컬 테스트 실행**: PR 생성 전 로컬에서 모든 테스트 통과 확인
2. **커버리지 확인**: 새로운 코드가 커버리지 목표를 충족하는지 확인
3. **코드 리뷰**: 변경 사항에 대한 코드 리뷰 수행

### 브랜치 전략

1. **develop 브랜치**: 개발 중인 기능 통합
2. **feature 브랜치**: 새로운 기능 개발
3. **main 브랜치**: 안정적인 릴리스

### CI/CD 최적화

1. **캐싱 활용**: 의존성 캐싱으로 빌드 시간 단축
2. **조건부 실행**: 변경된 파일에 따라 워크플로우 선택적 실행
3. **병렬 실행**: 매트릭스를 사용한 병렬 테스트 실행

---

## 향후 계획

- ⏳ 배포 자동화 (CD)
- ⏳ Docker 이미지 빌드 및 푸시
- ⏳ 통합 테스트 환경 구축
- ⏳ 성능 테스트 추가
- ⏳ 보안 스캔 통합
