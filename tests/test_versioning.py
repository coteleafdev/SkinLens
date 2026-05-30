"""
test_versioning.py — API 버전 관리 테스트
"""
import pytest
from fastapi.testclient import TestClient
from src.server.server import app


class TestAPIVersioning:
    """API 버전 관리 테스트"""

    def test_version_header_present(self):
        """버전 헤더가 응답에 포함되는지 확인"""
        client = TestClient(app)
        response = client.get("/v3/health")
        assert "API-Version" in response.headers

    def test_current_version_header(self):
        """현재 버전이 아닌 경우 API-Current-Version 헤더 포함"""
        client = TestClient(app)
        # 현재 버전이 v3이므로 /v3/health는 현재 버전
        response = client.get("/v3/health")
        assert "API-Version" in response.headers
        assert response.headers["API-Version"] == "v3"
        # 현재 버전이므로 API-Current-Version 헤더는 없음
        assert "API-Current-Version" not in response.headers

    def test_deprecated_version_warning(self):
        """폐기된 버전 사용 시 경고 헤더 확인"""
        client = TestClient(app)
        # v1은 폐기된 버전으로 설정
        # 실제 라우터가 없으므로 404가 예상되지만 헤더는 확인 가능
        response = client.get("/v1/analysis/jobs")
        # 라우터가 없으면 404지만 미들웨어는 동작
        assert response.status_code == 404
        # 폐기된 버전 경고 헤더 확인
        assert "Deprecation" in response.headers
        assert response.headers["Deprecation"] == "true"

    def test_sunset_version_warning(self):
        """폐기 예정 버전 사용 시 경고 헤더 확인"""
        client = TestClient(app)
        # v2는 폐기 예정 버전으로 설정
        response = client.get("/v2/analysis/jobs")
        # 라우터가 없으면 404지만 미들웨어는 동작
        assert response.status_code == 404
        # 폐기 예정 버전 경고 헤더 확인
        assert "Sunset" in response.headers
        assert response.headers["Sunset"] == "2026-12-31"

    def test_version_config_from_json(self):
        """config.json에서 버전 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        versioning_config = server_config.get("versioning", {})

        assert "current_version" in versioning_config
        assert "deprecated_versions" in versioning_config
        assert "sunset_versions" in versioning_config
        assert versioning_config["current_version"] == "v3"

    def test_version_extraction(self):
        """버전 추출 기능 테스트"""
        from src.server.middleware.versioning import APIVersionMiddleware

        middleware = APIVersionMiddleware(app=None)

        # 버전 추출 테스트
        assert middleware._extract_version("/v3/analysis/jobs") == "v3"
        assert middleware._extract_version("/v2/analysis/jobs") == "v2"
        assert middleware._extract_version("/health") is None
        assert middleware._extract_version("/api/v3/test") is None  # 경로 시작이 아님
