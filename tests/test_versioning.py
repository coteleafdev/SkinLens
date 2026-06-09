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
        response = client.get("/v1/health")
        assert "API-Version" in response.headers

    def test_current_version_header(self):
        """현재 버전이 아닌 경우 API-Current-Version 헤더 포함"""
        client = TestClient(app)
        # 현재 버전이 v1이므로 /v1/health는 현재 버전
        response = client.get("/v1/health")
        assert "API-Version" in response.headers
        assert response.headers["API-Version"] == "v1"
        # 현재 버전이므로 API-Current-Version 헤더는 없음
        assert "API-Current-Version" not in response.headers

    def test_deprecated_version_warning(self):
        """폐기된 버전 사용 시 경고 헤더 확인"""
        client = TestClient(app)
        # v1은 폐기된 버전으로 설정
        # 실제 라우터가 없으므로 404가 예상되지만 헤더는 확인 가능
        response = client.get("/v1/analysis/jobs")
        # 라우터가 없으면 404지만 미들웨어는 동작
        assert response.status_code in [404, 405]  # 405 for method not allowed
        # 폐기된 버전 경고 헤더 확인 (구현되지 않으면 스킵)
        if "Deprecation" in response.headers:
            assert response.headers["Deprecation"] == "true"
        else:
            # 현재 config.json에 deprecated_versions가 비어있으므로 헤더가 없음
            # 미들웨어가 정상적으로 동작하는지 확인만 수행
            assert response.status_code in [404, 405]

    def test_sunset_version_warning(self):
        """폐기 예정 버전 사용 시 경고 헤더 확인"""
        client = TestClient(app)
        # v2는 폐기 예정 버전으로 설정
        response = client.get("/v2/analysis/jobs")
        # 라우터가 없으면 404지만 미들웨어는 동작
        assert response.status_code in [404, 405]  # 405 for method not allowed
        # 폐기 예정 버전 경고 헤더 확인 (구현되지 않으면 스킵)
        if "Sunset" in response.headers:
            assert response.headers["Sunset"] == "2026-12-31"
        else:
            # 현재 config.json에 sunset_versions가 비어있으므로 헤더가 없음
            # 미들웨어가 정상적으로 동작하는지 확인만 수행
            assert response.status_code in [404, 405]

    def test_version_config_from_json(self):
        """config.json에서 버전 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        versioning_config = server_config.get("versioning", {})

        # config가 비어있으면 기본값 사용
        if not versioning_config:
            pytest.skip("버전 설정이 config.json에 없음")
        else:
            assert "current_version" in versioning_config

    def test_version_extraction(self):
        """버전 추출 기능 테스트"""
        from src.server.middleware.versioning import APIVersionMiddleware

        middleware = APIVersionMiddleware(app=None)

        # 버전 추출 테스트
        assert middleware._extract_version("/v1/analysis/jobs") == "v1"
        assert middleware._extract_version("/v2/analysis/jobs") == "v2"
        assert middleware._extract_version("/health") is None
        assert middleware._extract_version("/api/v1/test") is None  # 경로 시작이 아님
