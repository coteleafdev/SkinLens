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
os.environ.setdefault("TESTING", "true")  # 테스트 모드 활성화
os.environ.setdefault("DISABLE_AUDIT_LOG", "true")  # 감사 로그 비활성화 (방안 3)
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "1")  # refresh_token 만료 시간 단축 (방안 3)

import pytest
import tempfile
import sqlite3
from click.testing import CliRunner
from unittest.mock import patch, Mock
from datetime import timedelta


# 전역 속도 제한 비활성화 fixture (모든 테스트에 적용)
@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """모든 테스트에서 속도 제한 비활성화."""
    # 이제 src.server.deps에서 TESTING_MODE 환경변수로 처리하므로
    # 여기서는 추가 처리가 필요 없음
    yield


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
    
    # SkinAnalysisDB도 초기화 (Admin API 테스트용)
    skin_db_path = str(tmp_path / "skin_analysis_test.db")
    from src.db.skin_analysis_db import SkinAnalysisDB
    skin_db = SkinAnalysisDB(db_path=skin_db_path)
    
    # 스키마 마이그레이션 강제 실행 (api_keys 테이블 생성 등)
    with skin_db._lock:
        cursor = skin_db._conn.cursor()
        
        # 스키마 버전을 40로 설정하여 모든 마이그레이션 실행 (products 테이블 포함)
        cursor.execute("INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (40, CURRENT_TIMESTAMP)")
        
        # api_keys 테이블 생성 (버전 4 마이그레이션)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                owner_id TEXT NOT NULL,
                scopes TEXT,
                is_active INTEGER DEFAULT 1,
                expires_at TIMESTAMP,
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                revoked_at TIMESTAMP,
                revoke_reason TEXT
            )
        """)
        
        # products 테이블 생성 (버전 39 마이그레이션)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT,
                key_ingredients TEXT,
                efficacy TEXT,
                target_skin_types TEXT,
                target_concerns TEXT,
                target_prescription_items TEXT,
                stock_quantity INTEGER DEFAULT 0,
                price REAL DEFAULT 0.0,
                is_active INTEGER DEFAULT 1,
                is_ready_made INTEGER DEFAULT 0,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        skin_db._conn.commit()
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_owner
            ON api_keys(owner_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_active
            ON api_keys(is_active, expires_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_hash
            ON api_keys(key_hash)
        """)
        
        # API 키 사용 로그 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_key_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key_id TEXT NOT NULL,
                endpoint TEXT,
                method TEXT,
                ip_address TEXT,
                user_agent TEXT,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (api_key_id) REFERENCES api_keys(id)
            )
        """)
        
        # 테스트용 사용자 생성 (평문 비밀번호 사용)
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
        
        # Refresh tokens 테이블 (방안 2: 테스트 DB에 추가)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE,
                customer_id TEXT,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_revoked INTEGER DEFAULT 0
            )
        """)
        
        # Password reset tokens 테이블 (방안 2: 테스트 DB에 추가)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                customer_id TEXT,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                used INTEGER DEFAULT 0
            )
        """)
        
        # Enhancements API 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_id TEXT UNIQUE NOT NULL,
                customer_id TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                width INTEGER,
                height INTEGER,
                rotation_angle INTEGER DEFAULT 0,
                upload_status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS push_preferences (
                customer_id TEXT PRIMARY KEY,
                push_enabled INTEGER DEFAULT 1,
                analysis_complete_enabled INTEGER DEFAULT 1,
                promotion_enabled INTEGER DEFAULT 0,
                quiet_hours_start TEXT,
                quiet_hours_end TEXT,
                device_token TEXT,
                platform TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ab_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT UNIQUE NOT NULL,
                description TEXT,
                variant_a_name TEXT NOT NULL,
                variant_b_name TEXT NOT NULL,
                traffic_split REAL DEFAULT 0.5,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ab_test_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                customer_id TEXT NOT NULL,
                variant TEXT NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(test_id, customer_id),
                FOREIGN KEY (test_id) REFERENCES ab_tests(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ab_test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                variant TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                event_count INTEGER DEFAULT 1,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_id) REFERENCES ab_tests(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                metric_unit TEXT,
                tags TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                analysis_id TEXT NOT NULL,
                overall_score_original REAL,
                overall_score_restored REAL,
                measurement_scores TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES users(customer_id)
            )
        """)
        
        skin_db._conn.commit()
    
    # 환경변수에 SkinAnalysisDB 경로도 설정
    original_skin_db = os.environ.get("SKIN_ANALYSIS_DB")
    os.environ["SKIN_ANALYSIS_DB"] = skin_db_path
    
    yield path
    
    # teardown: 환경변수 원복
    if original_db:
        os.environ["EXECUTION_HISTORY_DB"] = original_db
    else:
        os.environ.pop("EXECUTION_HISTORY_DB", None)
    
    if original_skin_db:
        os.environ["SKIN_ANALYSIS_DB"] = original_skin_db
    else:
        os.environ.pop("SKIN_ANALYSIS_DB", None)
    
    # DB 연결 종료
    try:
        skin_db._conn.close()
    except:
        pass


@pytest.fixture(scope="session")
def auth_client(temp_db_for_api):
    """인증된 FastAPI TestClient fixture (session-scoped)."""
    from src.server.server import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    yield client


@pytest.fixture(scope="session")
def admin_token(auth_client):
    """관리자 JWT 토큰 fixture (session-scoped)."""
    # 테스트용 토큰 생성 함수 사용
    from src.server.deps import create_test_token
    return create_test_token("admin", "admin")


@pytest.fixture(scope="session")
def analyst_token(auth_client):
    """분석가 JWT 토큰 fixture (session-scoped)."""
    # 테스트용 토큰 생성 함수 사용
    from src.server.deps import create_test_token
    return create_test_token("analyst", "analyst")


@pytest.fixture(scope="session")
def user_token():
    """일반 사용자 JWT 토큰 fixture (session-scoped, 직접 생성)."""
    from src.server.deps import create_test_token
    return create_test_token("user123", "customer")


@pytest.fixture
def skin_analysis_db_with_users(tmp_path):
    """사용자 데이터가 포함된 SkinAnalysisDB fixture."""
    from src.db.skin_analysis_db import SkinAnalysisDB
    from src.server.deps import pwd_context
    
    db_path = str(tmp_path / "skin_analysis_test.db")
    db = SkinAnalysisDB(db_path=db_path)
    
    # 스키마 마이그레이션 강제 실행 (api_keys 테이블 생성 등)
    with db._lock:
        cursor = db._conn.cursor()
        
        # 스키마 버전을 40로 설정하여 모든 마이그레이션 실행 (products 테이블 포함)
        cursor.execute("INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (40, CURRENT_TIMESTAMP)")
        
        # api_keys 테이블 생성 (버전 4 마이그레이션)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                owner_id TEXT NOT NULL,
                scopes TEXT,
                is_active INTEGER DEFAULT 1,
                expires_at TIMESTAMP,
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                revoked_at TIMESTAMP,
                revoke_reason TEXT
            )
        """)
        
        # products 테이블 생성 (버전 39 마이그레이션)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT,
                key_ingredients TEXT,
                efficacy TEXT,
                target_skin_types TEXT,
                target_concerns TEXT,
                target_prescription_items TEXT,
                stock_quantity INTEGER DEFAULT 0,
                price REAL DEFAULT 0.0,
                is_active INTEGER DEFAULT 1,
                is_ready_made INTEGER DEFAULT 0,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        skin_db._conn.commit()
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_owner
            ON api_keys(owner_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_active
            ON api_keys(is_active, expires_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_hash
            ON api_keys(key_hash)
        """)
        
        # API 키 사용 로그 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_key_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key_id TEXT NOT NULL,
                endpoint TEXT,
                method TEXT,
                ip_address TEXT,
                user_agent TEXT,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (api_key_id) REFERENCES api_keys(id)
            )
        """)
        
        # 테스트용 사용자 생성 (평문 비밀번호 사용)
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
    
    # cleanup: 명시적 연결 종료
    try:
        db._conn.close()
    except:
        pass
    del db


@pytest.fixture
def authenticated_client(skin_analysis_db_with_users):
    """인증된 FastAPI TestClient fixture (사용자 DB 포함)."""
    # 테스트용 DB 경로 설정
    original_db_path = os.environ.get("SKIN_ANALYSIS_DB")
    os.environ["SKIN_ANALYSIS_DB"] = skin_analysis_db_with_users.db_path
    
    from src.server.server import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    yield client
    
    # teardown: 원복
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


@pytest.fixture(autouse=True)
def mock_email_server(monkeypatch):
    """Mock 이메일 서버 fixture (방안 2: Mock 사용)"""
    # 이메일 전송 함수 mock
    def mock_send_email(to: str, subject: str, body: str):
        # 테스트에서는 실제 이메일 전송하지 않음
        pass
    
    # 필요한 경우 src.notification 모듈의 이메일 함수를 mock
    try:
        from src.notification import email_sender
        monkeypatch.setattr(email_sender, "send_email", mock_send_email)
    except ImportError:
        # 모듈이 없으면 무시
        pass
    
    yield

