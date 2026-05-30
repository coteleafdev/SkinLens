"""
test_upload.py — 청크 업로드 테스트
"""
import pytest
from fastapi.testclient import TestClient
from src.server.server import app
from io import BytesIO


class TestChunkUpload:
    """청크 업로드 테스트"""

    def test_init_upload_unauthorized(self):
        """인증 없이 업로드 세션 초기화 시도"""
        client = TestClient(app)
        response = client.post(
            "/v3/upload/init",
            params={
                "file_name": "test.jpg",
                "file_size": 1024,
                "chunk_size": 512,
            }
        )
        assert response.status_code == 401

    def test_init_upload_authorized(self):
        """인증된 사용자로 업로드 세션 초기화"""
        client = TestClient(app)
        # 먼저 로그인
        login_response = client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        token = login_response.json()["access_token"]

        # 업로드 세션 초기화
        response = client.post(
            "/v3/upload/init",
            params={
                "file_name": "test.jpg",
                "file_size": 1024,
                "chunk_size": 512,
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["file_name"] == "test.jpg"
        assert data["file_size"] == 1024
        assert data["total_chunks"] == 2  # 1024 / 512 = 2

    def test_init_upload_file_size_exceeded(self):
        """파일 크기 초과 테스트"""
        client = TestClient(app)
        # 먼저 로그인
        login_response = client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        token = login_response.json()["access_token"]

        # 너무 큰 파일로 초기화 시도
        response = client.post(
            "/v3/upload/init",
            params={
                "file_name": "large.jpg",
                "file_size": 100 * 1024 * 1024 * 1024,  # 100GB
                "chunk_size": 5 * 1024 * 1024,
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400
        assert "exceeds maximum allowed size" in response.json()["detail"]

    def test_upload_chunk_invalid_session(self):
        """유효하지 않은 세션으로 청크 업로드 시도"""
        client = TestClient(app)
        # 먼저 로그인
        login_response = client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        token = login_response.json()["access_token"]

        # 존재하지 않는 세션으로 청크 업로드
        chunk_data = BytesIO(b"test data")
        response = client.post(
            "/v3/upload/chunk",
            params={
                "session_id": "nonexistent-session",
                "chunk_number": 0,
            },
            files={"chunk": ("chunk_0", chunk_data, "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

    def test_upload_progress_invalid_session(self):
        """유효하지 않은 세션으로 진행률 조회 시도"""
        client = TestClient(app)
        # 먼저 로그인
        login_response = client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        token = login_response.json()["access_token"]

        # 존재하지 않는 세션으로 진행률 조회
        response = client.get(
            "/v3/upload/progress/nonexistent-session",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

    def test_cancel_upload_invalid_session(self):
        """유효하지 않은 세션으로 취소 시도"""
        client = TestClient(app)
        # 먼저 로그인
        login_response = client.post(
            "/v3/auth/login",
            data={"customer_id": "admin", "password": "admin123"}
        )
        token = login_response.json()["access_token"]

        # 존재하지 않는 세션으로 취소
        response = client.post(
            "/v3/upload/cancel",
            params={"session_id": "nonexistent-session"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404
