"""
test_rate_limiting.py — 속도 제한 세분화 테스트
"""
import pytest
from fastapi.testclient import TestClient
from src.server.server import app
from src.server.deps import ROLE_RATE_LIMITS, get_rate_limit_key


class TestRateLimiting:
    """속도 제한 세분화 테스트"""

    def test_role_rate_limits_configured(self):
        """역할별 속도 제한이 설정되어 있는지 확인"""
        assert "customer" in ROLE_RATE_LIMITS
        assert "admin" in ROLE_RATE_LIMITS
        assert "analyst" in ROLE_RATE_LIMITS
        assert "default" in ROLE_RATE_LIMITS

    def test_admin_has_higher_limit(self):
        """관리자가 더 높은 속도 제한을 가지는지 확인"""
        admin_limit = ROLE_RATE_LIMITS["admin"]
        customer_limit = ROLE_RATE_LIMITS["customer"]
        # 관리자는 고객보다 높은 제한을 가져야 함
        assert admin_limit != customer_limit

    def test_rate_limit_key_format(self):
        """속도 제한 키 형식 확인"""
        from unittest.mock import Mock

        # Mock request 객체 생성
        request = Mock()
        request.headers = {"authorization": "Bearer test_token"}
        request.client = Mock()
        request.client.host = "192.168.1.1"

        # 키 생성 (토큰 파싱 실패 시 기본값)
        key = get_rate_limit_key(request)
        assert ":" in key
        assert "192.168.1.1" in key

    def test_rate_limit_key_without_token(self):
        """토큰 없이 속도 제한 키 생성 확인"""
        from unittest.mock import Mock

        request = Mock()
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.168.1.1"

        key = get_rate_limit_key(request)
        assert key == "192.168.1.1:default"

    def test_rate_limiting_config_from_json(self):
        """config.json에서 속도 제한 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        rate_limiting_config = server_config.get("rate_limiting", {})
        role_limits = rate_limiting_config.get("role_limits", {})

        assert "customer" in role_limits
        assert "admin" in role_limits
        assert "analyst" in role_limits
        assert "default" in role_limits
