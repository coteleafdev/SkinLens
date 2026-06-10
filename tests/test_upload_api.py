"""
Upload API endpoints tests.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestUploadAPI:
    """Upload API endpoints tests."""

    @pytest.fixture
    def client(self):
        """Test client fixture."""
        from src.server.server import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Auth headers fixture."""
        return {"Authorization": "Bearer test_token"}

    @pytest.fixture
    def mock_customer(self):
        """Mock customer fixture."""
        return {
            "sub": "test_customer_123",
            "role": "customer",
            "username": "testuser"
        }

    def test_init_upload_success(self, client, auth_headers, mock_customer):
        """Test successful upload session initialization."""
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/upload/init",
                params={
                    "file_name": "test_image.jpg",
                    "file_size": 1024000,
                    "chunk_size": 524288
                },
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["file_name"] == "test_image.jpg"
            assert data["file_size"] == 1024000
            assert data["total_chunks"] > 0

    def test_init_upload_unauthorized(self, client):
        """Test upload initialization without authentication."""
        response = client.post(
            "/v1/upload/init",
            params={
                "file_name": "test_image.jpg",
                "file_size": 1024000
            }
        )
        
        assert response.status_code == 401

    def test_init_upload_invalid_filename(self, client, auth_headers, mock_customer):
        """Test upload initialization with invalid filename."""
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/upload/init",
                params={
                    "file_name": "../../../etc/passwd",
                    "file_size": 1024000
                },
                headers=auth_headers
            )
            
            assert response.status_code == 400

    def test_init_upload_file_too_large(self, client, auth_headers, mock_customer):
        """Test upload initialization with file size exceeding limit."""
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            with patch('src.server.routers.upload.get_max_upload_bytes', return_value=1048576):
                response = client.post(
                    "/v1/upload/init",
                    params={
                        "file_name": "large_file.jpg",
                        "file_size": 10485760  # 10MB
                    },
                    headers=auth_headers
                )
                
                assert response.status_code == 400
                assert "exceeds maximum" in response.json()["detail"].lower()

    def test_upload_chunk_success(self, client, auth_headers, mock_customer):
        """Test successful chunk upload."""
        # First initialize session
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            init_response = client.post(
                "/v1/upload/init",
                params={
                    "file_name": "test_image.jpg",
                    "file_size": 1024000,
                    "chunk_size": 524288
                },
                headers=auth_headers
            )
            session_id = init_response.json()["session_id"]
        
        # Upload chunk
        chunk_data = b"fake chunk data" * 1000
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            response = client.post(
                f"/v1/upload/chunk",
                params={
                    "session_id": session_id,
                    "chunk_number": 0
                },
                files={"chunk": ("chunk_0.bin", chunk_data, "application/octet-stream")},
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["chunk_number"] == 0
            assert data["uploaded"] > 0

    def test_upload_chunk_unauthorized(self, client):
        """Test chunk upload without authentication."""
        response = client.post(
            "/v1/upload/chunk",
            params={
                "session_id": "test_session",
                "chunk_number": 0
            },
            files={"chunk": ("chunk_0.bin", b"data", "application/octet-stream")}
        )
        
        assert response.status_code == 401

    def test_upload_chunk_session_not_found(self, client, auth_headers, mock_customer):
        """Test chunk upload with invalid session ID."""
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/upload/chunk",
                params={
                    "session_id": "nonexistent_session",
                    "chunk_number": 0
                },
                files={"chunk": ("chunk_0.bin", b"data", "application/octet-stream")},
                headers=auth_headers
            )
            
            assert response.status_code == 404

    def test_complete_upload_success(self, client, auth_headers, mock_customer):
        """Test successful upload completion."""
        # Initialize session
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            init_response = client.post(
                "/v1/upload/init",
                params={
                    "file_name": "test_image.jpg",
                    "file_size": 1024,
                    "chunk_size": 512
                },
                headers=auth_headers
            )
            session_id = init_response.json()["session_id"]
        
        # Upload chunks
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            client.post(
                "/v1/upload/chunk",
                params={"session_id": session_id, "chunk_number": 0},
                files={"chunk": ("chunk_0.bin", b"data" * 256, "application/octet-stream")},
                headers=auth_headers
            )
            client.post(
                "/v1/upload/chunk",
                params={"session_id": session_id, "chunk_number": 1},
                files={"chunk": ("chunk_1.bin", b"data" * 256, "application/octet-stream")},
                headers=auth_headers
            )
        
        # Complete upload
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            with patch('src.server.routers.upload.validate_path_within_directory', return_value=True):
                response = client.post(
                    "/v1/upload/complete",
                    params={"session_id": session_id},
                    headers=auth_headers
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "completed"
                assert "file_path" in data

    def test_complete_upload_unauthorized(self, client):
        """Test upload completion without authentication."""
        response = client.post(
            "/v1/upload/complete",
            params={"session_id": "test_session"}
        )
        
        assert response.status_code == 401

    def test_cancel_upload_success(self, client, auth_headers, mock_customer):
        """Test successful upload cancellation."""
        # Initialize session
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            init_response = client.post(
                "/v1/upload/init",
                params={
                    "file_name": "test_image.jpg",
                    "file_size": 1024000
                },
                headers=auth_headers
            )
            session_id = init_response.json()["session_id"]
        
        # Cancel upload
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/upload/cancel",
                params={"session_id": session_id},
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cancelled"

    def test_cancel_upload_unauthorized(self, client):
        """Test upload cancellation without authentication."""
        response = client.post(
            "/v1/upload/cancel",
            params={"session_id": "test_session"}
        )
        
        assert response.status_code == 401

    def test_get_upload_progress_success(self, client, auth_headers, mock_customer):
        """Test successful upload progress retrieval."""
        # Initialize session
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            init_response = client.post(
                "/v1/upload/init",
                params={
                    "file_name": "test_image.jpg",
                    "file_size": 1024000
                },
                headers=auth_headers
            )
            session_id = init_response.json()["session_id"]
        
        # Get progress
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            response = client.get(
                f"/v1/upload/progress/{session_id}",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "progress" in data
            assert "uploaded_chunks" in data
            assert "total_chunks" in data

    def test_get_upload_progress_not_found(self, client, auth_headers, mock_customer):
        """Test upload progress for non-existent session."""
        with patch('src.server.routers.upload.get_current_customer', return_value=mock_customer):
            response = client.get(
                "/v1/upload/progress/nonexistent_session",
                headers=auth_headers
            )
            
            assert response.status_code == 404
