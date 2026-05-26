"""
conftest.py — 공통 pytest 설정 및 fixtures

환경 변수, 공통 fixture를 제공합니다.
"""
import os
import sys
from pathlib import Path

# 테스트용 환경변수 설정 (모든 테스트 전에 설정)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-ci")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")
os.environ.setdefault("ANALYST_PASSWORD", "analyst123")
os.environ.setdefault("CUSTOMER_PASSWORD", "customer123")

import pytest
import tempfile
import sqlite3
from click.testing import CliRunner


@pytest.fixture
def temp_dir(tmp_path):
    """임시 디렉토리 fixture."""
    return tmp_path


@pytest.fixture
def temp_db(tmp_path):
    """올바른 스키마로 초기화된 임시 DB fixture."""
    path = str(tmp_path / "test.db")
    from src.cli.execution_history import ExecutionHistoryDB
    ExecutionHistoryDB(path)  # 올바른 스키마로 초기화
    yield path
    # cleanup은 tmp_path가 자동 처리


@pytest.fixture
def runner():
    """CLI 테스트용 CliRunner fixture."""
    return CliRunner()


@pytest.fixture(scope="session")
def temp_db_for_api(tmp_path_factory):
    """API 테스트용 임시 DB fixture (session-scoped)."""
    tmp_path = tmp_path_factory.mktemp("api_test_db")
    path = str(tmp_path / "test.db")
    from src.cli.execution_history import ExecutionHistoryDB
    ExecutionHistoryDB(path)  # 올바른 스키마로 초기화
    
    # 환경변수 설정
    original_db = os.environ.get("EXECUTION_HISTORY_DB")
    os.environ["EXECUTION_HISTORY_DB"] = path
    
    yield path
    
    # teardown: 환경변수 원복
    if original_db:
        os.environ["EXECUTION_HISTORY_DB"] = original_db
    else:
        os.environ.pop("EXECUTION_HISTORY_DB", None)


@pytest.fixture(scope="session")
def auth_client(temp_db_for_api):
    """인증된 FastAPI TestClient fixture (session-scoped)."""
    # Rate limiting 비활성화 (테스트용)
    def fake_limit(limit_str):
        def decorator(f):
            return f
        return decorator

    import src.server.deps as deps_module
    original_limit = deps_module.limiter.limit
    deps_module.limiter.limit = fake_limit
    
    from src.server.server import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    yield client
    
    # teardown: 원복
    deps_module.limiter.limit = original_limit


@pytest.fixture(scope="session")
def admin_token(auth_client):
    """관리자 JWT 토큰 fixture (session-scoped)."""
    response = auth_client.post("/v3/auth/login", data={
        "customer_id": "admin",
        "password": "admin123"
    })
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def analyst_token(auth_client):
    """분석가 JWT 토큰 fixture (session-scoped)."""
    response = auth_client.post("/v3/auth/login", data={
        "customer_id": "analyst",
        "password": "analyst123"
    })
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def user_token():
    """일반 사용자 JWT 토큰 fixture (session-scoped, 직접 생성)."""
    from src.server.deps import create_access_token
    return create_access_token({"sub": "user123", "role": "user"})
