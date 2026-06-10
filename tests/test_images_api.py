"""
Image API endpoints tests.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestImagesAPI:
    """Image API endpoints tests."""

    @pytest.fixture
    def client(self):
        """Test client fixture."""
        from src.server.server import app
        return TestClient(app)

    @pytest.fixture
    def sample_image_data(self):
        """Sample image binary data."""
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # PNG header + dummy data

    def test_get_original_image_local_storage(self, client, sample_image_data):
        """Test getting original image from local storage."""
        with patch('src.server.routers.images.local_storage') as mock_storage:
            mock_storage.get_image_binary.return_value = sample_image_data
            
            response = client.get("/v1/images/test123/original")
            
            assert response.status_code == 200
            assert response.content == sample_image_data
            assert response.headers["content-type"] == "image/png"

    def test_get_original_image_not_found(self, client):
        """Test getting original image when not found."""
        with patch('src.server.routers.images.local_storage') as mock_storage:
            mock_storage.get_image_binary.return_value = None
            
            response = client.get("/v1/images/test123/original")
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_get_restored_image_local_storage(self, client, sample_image_data):
        """Test getting restored image from local storage."""
        with patch('src.server.routers.images.local_storage') as mock_storage:
            mock_storage.get_image_binary.return_value = sample_image_data
            
            response = client.get("/v1/images/test123/restored")
            
            assert response.status_code == 200
            assert response.content == sample_image_data
            assert response.headers["content-type"] == "image/png"

    def test_get_restored_image_not_found(self, client):
        """Test getting restored image when not found."""
        with patch('src.server.routers.images.local_storage') as mock_storage:
            mock_storage.get_image_binary.return_value = None
            
            response = client.get("/v1/images/test123/restored")
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_get_image_metadata(self, client):
        """Test getting image metadata."""
        original_metadata = {
            "file_path": "/path/to/original.png",
            "file_size": 1024000,
            "file_hash": "abc123",
            "created_at": "2026-06-10T00:00:00Z"
        }
        restored_metadata = {
            "file_path": "/path/to/restored.png",
            "file_size": 1536000,
            "file_hash": "def456",
            "created_at": "2026-06-10T00:00:05Z"
        }
        
        with patch('src.server.routers.images.local_storage') as mock_storage:
            mock_storage.get_image.side_effect = lambda customer_id, image_type: (
                original_metadata if image_type == "original" else restored_metadata
            )
            
            response = client.get("/v1/images/test123/metadata")
            
            assert response.status_code == 200
            data = response.json()
            assert data["customer_id"] == "test123"
            assert data["original"]["metadata"] == original_metadata
            assert data["restored"]["metadata"] == restored_metadata
            assert data["original"]["local_url"] == "/v1/images/test123/original"
            assert data["restored"]["local_url"] == "/v1/images/test123/restored"

    def test_get_image_metadata_with_base64(self, client):
        """Test getting image metadata with Base64 encoding."""
        original_metadata = {
            "file_path": "/path/to/original.png",
            "file_size": 1024,
            "file_hash": "abc123",
            "created_at": "2026-06-10T00:00:00Z"
        }
        restored_metadata = {
            "file_path": "/path/to/restored.png",
            "file_size": 1536,
            "file_hash": "def456",
            "created_at": "2026-06-10T00:00:05Z"
        }
        original_base64 = "iVBORw0KGgoAAAANSUhEUgAA"
        restored_base64 = "iVBORw0KGgoAAAANSUhEUgBB"
        
        with patch('src.server.routers.images.local_storage') as mock_storage:
            mock_storage.get_image.side_effect = lambda customer_id, image_type: (
                original_metadata if image_type == "original" else restored_metadata
            )
            mock_storage.get_image_base64.side_effect = lambda customer_id, image_type, max_size: (
                original_base64 if image_type == "original" else restored_base64
            )
            
            response = client.get("/v1/images/test123/metadata?include_base64=true")
            
            assert response.status_code == 200
            data = response.json()
            assert data["original"]["base64"] == original_base64
            assert data["restored"]["base64"] == restored_base64

    def test_get_image_metadata_no_images(self, client):
        """Test getting image metadata when no images exist."""
        with patch('src.server.routers.images.local_storage') as mock_storage:
            mock_storage.get_image.return_value = None
            
            response = client.get("/v1/images/test123/metadata")
            
            assert response.status_code == 200
            data = response.json()
            assert data["customer_id"] == "test123"
            assert data["original"]["metadata"] is None
            assert data["restored"]["metadata"] is None
            assert data["original"]["local_url"] is None
            assert data["restored"]["local_url"] is None

    def test_get_original_image_supabase_redirect(self, client):
        """Test getting original image with Supabase redirect."""
        supabase_url = "https://supabase-url.com/storage/v1/object/public/skin-images/test123/original.png"
        
        with patch('src.server.routers.images.supabase_storage') as mock_supabase:
            mock_supabase.get_image_url.return_value = supabase_url
            
            response = client.get("/v1/images/test123/original")
            
            assert response.status_code == 307  # Redirect
            assert response.headers["location"] == supabase_url

    def test_get_restored_image_supabase_redirect(self, client):
        """Test getting restored image with Supabase redirect."""
        supabase_url = "https://supabase-url.com/storage/v1/object/public/skin-images/test123/restored.png"
        
        with patch('src.server.routers.images.supabase_storage') as mock_supabase:
            mock_supabase.get_image_url.return_value = supabase_url
            
            response = client.get("/v1/images/test123/restored")
            
            assert response.status_code == 307  # Redirect
            assert response.headers["location"] == supabase_url
