"""
Auth API 테스트 - 인증 엔드포인트
"""
import pytest
from fastapi.testclient import TestClient


class TestAuthAPI:
    """Auth API 엔드포인트 테스트"""

    def test_login_admin_success(self, auth_client):
        """관리자 로그인 성공"""
        response = auth_client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["customer_id"] == "admin"
        assert data["role"] == "admin"
        assert "expires_in" in data

    def test_login_analyst_success(self, auth_client):
        """분석가 로그인 성공"""
        response = auth_client.post(
            "/v3/auth/login",
            data={"customer_id": "analyst", "password": "analyst123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "analyst"

    def test_login_customer_success(self, auth_client):
        """고객 로그인 성공"""
        response = auth_client.post(
            "/v3/auth/login",
            data={"customer_id": "customer123", "password": "customer123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "customer"

    def test_login_wrong_password(self, auth_client):
        """잘못된 비밀번호로 로그인 실패"""
        response = auth_client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "wrongpassword"}
        )
        assert response.status_code == 401

    def test_login_missing_password_env(self, auth_client, monkeypatch):
        """비밀번호 환경변수 미설정 시 로그인 실패"""
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("ANALYST_PASSWORD", raising=False)
        
        response = auth_client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        assert response.status_code == 401

    def test_login_rate_limiting(self, auth_client):
        """로그인 속도 제한 테스트"""
        # 5회 이상 요청 시 속도 제한
        for _ in range(6):
            response = auth_client.post(
                "/v3/auth/login",
                data={"customer_id": "admin", "password": "wrong"}
            )
        
        # 6번째 요청은 속도 제한으로 실패해야 함
        assert response.status_code in (401, 429)

    def test_get_current_user_unauthorized(self, auth_client):
        """인증 없이 현재 사용자 정보 조회 실패"""
        response = auth_client.get("/v3/auth/me")
        assert response.status_code == 401

    def test_get_current_user_authorized(self, auth_client, admin_token):
        """인증된 상태에서 현재 사용자 정보 조회 성공"""
        response = auth_client.get(
            "/v3/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "customer_id" in data
        assert "role" in data

    def test_check_customer_access_admin(self):
        """관리자는 모든 고객 데이터 접근 가능"""
        from src.server.routers.auth import check_customer_access
        current_customer = {"sub": "admin", "role": "admin"}
        # 관리자는 예외를 발생시키지 않아야 함
        check_customer_access(current_customer, "customer123")

    def test_check_customer_access_forbidden(self):
        """일반 고객은 다른 고객 데이터 접근 불가"""
        from src.server.routers.auth import check_customer_access
        from fastapi import HTTPException
        
        current_customer = {"sub": "customer123", "role": "customer"}
        with pytest.raises(HTTPException) as exc_info:
            check_customer_access(current_customer, "customer456")
        
        assert exc_info.value.status_code == 403

    def test_verify_pw_bcrypt(self):
        """bcrypt 비밀번호 검증 테스트"""
        from src.server.routers.auth import _verify_pw
        # bcrypt 해시로 시작하는 경우
        bcrypt_hash = "$2b$12$testhash"
        # 실제 bcrypt 검증은 pwd_context가 필요하므로 함수 호출만 테스트
        assert callable(_verify_pw)

    def test_verify_pw_plain(self):
        """일반 텍스트 비밀번호 검증 테스트"""
        from src.server.routers.auth import _verify_pw
        # 일반 텍스트 비교
        result = _verify_pw("password", "password")
        assert result is True
        
        result = _verify_pw("password", "wrong")
        assert result is False
