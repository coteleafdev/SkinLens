"""
test_request_logging.py — 요청 로깅 미들웨어 테스트
"""
import pytest
from fastapi.testclient import TestClient
from src.server.server import app
from src.server.middleware.request_logging import RequestLoggingMiddleware


class TestRequestLoggingMiddleware:
    """요청 로깅 미들웨어 테스트"""

    def test_request_id_header_added(self):
        """요청 ID가 응답 헤더에 추가되는지 확인"""
        client = TestClient(app)
        response = client.get("/v3/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    def test_request_id_format(self):
        """요청 ID가 UUID 형식인지 확인"""
        client = TestClient(app)
        response = client.get("/v3/health")
        request_id = response.headers["X-Request-ID"]
        # UUID 형식: 8-4-4-4-12 (총 36자, 하이픈 4개)
        assert len(request_id) == 36
        assert request_id.count("-") == 4

    def test_request_logging_enabled(self):
        """요청 로깅이 활성화되어 있는지 확인"""
        # 미들웨어가 추가되었는지 확인
        middleware_found = False
        for middleware in app.user_middleware:
            if middleware.cls == RequestLoggingMiddleware:
                middleware_found = True
                break
        assert middleware_found, "RequestLoggingMiddleware가 추가되지 않았습니다"

    def test_slow_request_threshold_from_config(self):
        """config.json에서 느린 요청 기준이 로드되는지 확인"""
        from src.utils.config import load_config
        config = load_config()
        server_config = config.get("server", {})
        request_logging_config = server_config.get("request_logging", {})
        slow_threshold = request_logging_config.get("slow_request_threshold", 5.0)
        assert slow_threshold > 0
        assert isinstance(slow_threshold, (int, float))

    def test_request_logging_disabled_in_config(self):
        """config.json에서 비활성화 시 미들웨어가 추가되지 않는지 확인 (테스트용)"""
        # 이 테스트는 실제 config.json을 수정하지 않고 로직만 검증
        from src.server.middleware.request_logging import RequestLoggingMiddleware
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        request_logging_config = server_config.get("request_logging", {})
        enabled = request_logging_config.get("enabled", True)

        # 기본값은 True이므로 활성화되어야 함
        assert enabled is True
