"""
test_ip_filter.py — IP 필터링 테스트
"""
import pytest
from fastapi.testclient import TestClient
from src.server.server import app


class TestIPFilter:
    """IP 필터링 테스트"""

    def test_ip_filter_config_from_json(self):
        """config.json에서 IP 필터 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        ip_filter_config = server_config.get("ip_filter", {})

        assert "whitelist" in ip_filter_config
        assert "blacklist" in ip_filter_config
        assert "trust_proxy" in ip_filter_config

    def test_ip_pattern_matching(self):
        """IP 패턴 매칭 테스트"""
        from src.server.middleware.ip_filter import IPFilterMiddleware

        middleware = IPFilterMiddleware(app=None)

        # 개별 IP 매칭
        assert middleware._match_ip_pattern("192.168.1.1", "192.168.1.1")
        assert not middleware._match_ip_pattern("192.168.1.2", "192.168.1.1")

        # CIDR 매칭
        assert middleware._match_ip_pattern("192.168.1.1", "192.168.1.0/24")
        assert middleware._match_ip_pattern("192.168.1.255", "192.168.1.0/24")
        assert not middleware._match_ip_pattern("192.168.2.1", "192.168.1.0/24")

    def test_cidr_matching(self):
        """CIDR 매칭 테스트"""
        from src.server.middleware.ip_filter import IPFilterMiddleware

        middleware = IPFilterMiddleware(app=None)

        # /24 네트워크
        assert middleware._match_cidr("192.168.1.1", "192.168.1.0/24")
        assert middleware._match_cidr("192.168.1.255", "192.168.1.0/24")
        assert not middleware._match_cidr("192.168.2.1", "192.168.1.0/24")

        # /16 네트워크
        assert middleware._match_cidr("192.168.1.1", "192.168.0.0/16")
        assert middleware._match_cidr("192.168.255.255", "192.168.0.0/16")
        assert not middleware._match_cidr("10.0.0.1", "192.168.0.0/16")

    def test_ip_list_matching(self):
        """IP 목록 매칭 테스트"""
        from src.server.middleware.ip_filter import IPFilterMiddleware

        middleware = IPFilterMiddleware(app=None)

        # 개별 IP 목록
        ip_list = ["192.168.1.1", "192.168.1.2"]
        assert middleware._match_ip_list("192.168.1.1", ip_list)
        assert middleware._match_ip_list("192.168.1.2", ip_list)
        assert not middleware._match_ip_list("192.168.1.3", ip_list)

        # CIDR 목록
        cidr_list = ["192.168.1.0/24", "10.0.0.0/8"]
        assert middleware._match_ip_list("192.168.1.1", cidr_list)
        assert middleware._match_ip_list("10.0.0.1", cidr_list)
        assert not middleware._match_ip_list("172.16.0.1", cidr_list)

    def test_invalid_cidr(self):
        """잘못된 CIDR 표기법 테스트"""
        from src.server.middleware.ip_filter import IPFilterMiddleware

        middleware = IPFilterMiddleware(app=None)

        # 잘못된 CIDR
        assert not middleware._match_cidr("192.168.1.1", "invalid-cidr")
        assert not middleware._match_cidr("192.168.1.1", "192.168.1.0/33")  # 잘못된 마스크
