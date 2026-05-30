"""
test_websocket_management.py — WebSocket 연결 관리 테스트
"""
import pytest
from src.server.routers.websocket import ConnectionManager


class TestWebSocketConnectionManager:
    """WebSocket 연결 관리자 테스트"""

    def test_connection_manager_initialization(self):
        """연결 관리자 초기화 테스트"""
        manager = ConnectionManager(max_connections=50, connection_timeout=120)
        assert manager.max_connections == 50
        assert manager.connection_timeout == 120
        assert len(manager.active_connections) == 0

    def test_connection_stats(self):
        """연결 통계 테스트"""
        manager = ConnectionManager()
        stats = manager.get_connection_stats()
        assert "active_connections" in stats
        assert "max_connections" in stats
        assert "connection_timeout" in stats
        assert "connections" in stats
        assert stats["active_connections"] == 0

    def test_websocket_config_from_json(self):
        """config.json에서 WebSocket 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        websocket_config = server_config.get("websocket", {})

        assert "max_connections" in websocket_config
        assert "connection_timeout" in websocket_config
        assert websocket_config["max_connections"] > 0
        assert websocket_config["connection_timeout"] > 0

    def test_disconnect_nonexistent_connection(self):
        """존재하지 않는 연결 해제 테스트 (예외 없이 처리)"""
        manager = ConnectionManager()
        # 존재하지 않는 연결 해제 시도
        manager.disconnect("nonexistent_job_id")
        # 예외가 발생하지 않아야 함
        assert len(manager.active_connections) == 0
