"""
conftest.py — 공통 pytest 설정 및 fixtures

환경 변수, 공통 fixture를 제공합니다.
"""
import os
import sys
from pathlib import Path

# 테스트용 환경변수 설정 (모든 테스트 전에 설정)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-ci")
os.environ.setdefault("ADMIN_PASSWORD", "a")
os.environ.setdefault("ANALYST_PASSWORD", "a")
os.environ.setdefault("CUSTOMER_PASSWORD", "c")

import pytest
import tempfile
import sqlite3
from click.testing import CliRunner
from unittest.mock import patch


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
    response = auth_client.post("/v1/auth/login", data={
        "username": "admin",
        "password": "a"
    })
    if response.status_code == 200:
        return response.json()["access_token"]
    # 환경변수 폴백으로 토큰 생성
    from src.server.deps import create_access_token
    return create_access_token({"sub": "admin", "role": "admin"})


@pytest.fixture(scope="session")
def analyst_token(auth_client):
    """분석가 JWT 토큰 fixture (session-scoped)."""
    response = auth_client.post("/v1/auth/login", data={
        "username": "analyst",
        "password": "a"
    })
    if response.status_code == 200:
        return response.json()["access_token"]
    # 환경변수 폴백으로 토큰 생성
    from src.server.deps import create_access_token
    return create_access_token({"sub": "analyst", "role": "analyst"})


@pytest.fixture(scope="session")
def user_token():
    """일반 사용자 JWT 토큰 fixture (session-scoped, 직접 생성)."""
    from src.server.deps import create_access_token
    return create_access_token({"sub": "user123", "role": "user"})


@pytest.fixture
def skin_analysis_db_with_users(tmp_path):
    """사용자 데이터가 포함된 SkinAnalysisDB fixture."""
    from src.db.skin_analysis_db import SkinAnalysisDB
    from src.server.deps import pwd_context
    
    db_path = str(tmp_path / "skin_analysis_test.db")
    db = SkinAnalysisDB(db_path=db_path)
    
    # 테스트용 사용자 생성 (평문 비밀번호 사용)
    with db._lock:
        cursor = db._conn.cursor()
        
        # 관리자 사용자
        cursor.execute("""
            INSERT OR REPLACE INTO users (username, password_hash, role, customer_id, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, ("admin", "a", "admin", "admin"))
        
        # 분석가 사용자
        cursor.execute("""
            INSERT OR REPLACE INTO users (username, password_hash, role, customer_id, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, ("analyst", "a", "analyst", "analyst"))
        
        # 일반 사용자
        cursor.execute("""
            INSERT OR REPLACE INTO users (username, password_hash, role, customer_id, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, ("customer", "c", "customer", "CUST001"))
        
        db._conn.commit()
    
    yield db
    
    # cleanup
    del db


@pytest.fixture
def authenticated_client(skin_analysis_db_with_users):
    """인증된 FastAPI TestClient fixture (사용자 DB 포함)."""
    # Rate limiting 비활성화 (테스트용)
    def fake_limit(limit_str):
        def decorator(f):
            return f
        return decorator

    import src.server.deps as deps_module
    original_limit = deps_module.limiter.limit
    deps_module.limiter.limit = fake_limit
    
    # 테스트용 DB 경로 설정
    original_db_path = os.environ.get("SKIN_ANALYSIS_DB")
    os.environ["SKIN_ANALYSIS_DB"] = skin_analysis_db_with_users.db_path
    
    from src.server.server import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    yield client
    
    # teardown: 원복
    deps_module.limiter.limit = original_limit
    if original_db_path:
        os.environ["SKIN_ANALYSIS_DB"] = original_db_path
    else:
        os.environ.pop("SKIN_ANALYSIS_DB", None)


@pytest.fixture
def admin_auth_headers(authenticated_client):
    """관리자 인증 헤더 fixture."""
    response = authenticated_client.post("/v1/auth/login", data={
        "username": "admin",
        "password": "a"
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def customer_auth_headers(authenticated_client):
    """고객 인증 헤더 fixture."""
    response = authenticated_client.post("/v1/auth/login", data={
        "username": "customer",
        "password": "c"
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

