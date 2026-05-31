"""
Tests for customer API endpoints (/v1/customer/my/*)
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from src.db.skin_analysis_db import SkinAnalysisDB


@pytest.fixture
def mock_customer():
    """Mock authenticated customer"""
    return {
        "sub": "test_customer_123",
        "role": "customer",
        "email": "test@example.com"
    }


@pytest.fixture
def mock_db():
    """Mock SkinAnalysisDB"""
    with patch('src.server.routers.customer.SkinAnalysisDB') as mock:
        db_instance = Mock()
        mock.return_value = db_instance
        yield db_instance


class TestCompareAnalyses:
    """Tests for /v1/customer/my/analyses/compare"""
    
    def test_compare_analyses_success(self, client: TestClient, mock_customer, mock_db):
        """Test successful comparison of two analyses"""
        # Mock analysis data
        analysis_1 = {
            "id": 1,
            "created_at": "2026-05-01T00:00:00Z",
            "json_result": {
                "internal_analysis": {
                    "restored": {
                        "overall_score": 60,
                        "melasma_score": 50,
                        "redness_score": 70,
                        "wrinkle_score": 55,
                        "pore_score": 65
                    }
                }
            }
        }
        
        analysis_2 = {
            "id": 2,
            "created_at": "2026-05-15T00:00:00Z",
            "json_result": {
                "internal_analysis": {
                    "restored": {
                        "overall_score": 70,
                        "melasma_score": 55,
                        "redness_score": 65,
                        "wrinkle_score": 60,
                        "pore_score": 70
                    }
                }
            }
        }
        
        mock_db.get_customer_analysis_detail.side_effect = [analysis_1, analysis_2]
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/customer/my/analyses/compare",
                json={"analysis_id_1": 1, "analysis_id_2": 2},
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "analysis_1" in data
        assert "analysis_2" in data
        assert "changes" in data
        assert data["overall_improvement"] == 10  # 70 - 60
    
    def test_compare_analyses_not_found(self, client: TestClient, mock_customer, mock_db):
        """Test comparison with non-existent analysis"""
        mock_db.get_customer_analysis_detail.return_value = None
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/customer/my/analyses/compare",
                json={"analysis_id_1": 999, "analysis_id_2": 2},
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 404


class TestRecommendations:
    """Tests for /v1/customer/my/recommendations"""
    
    def test_get_recommendations_success(self, client: TestClient, mock_customer, mock_db):
        """Test successful retrieval of product recommendations"""
        mock_recommendations = [
            {
                "recommendation_id": 1,
                "product_id": "P001",
                "product_name": "Test Product",
                "match_score": 0.85,
                "category": "세럼"
            }
        ]
        mock_db.get_latest_recommendations.return_value = mock_recommendations
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.get(
                "/v1/customer/my/recommendations",
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) == 1
    
    def test_get_recommendations_with_analysis_id(self, client: TestClient, mock_customer, mock_db):
        """Test recommendations for specific analysis"""
        mock_recommendations = []
        mock_db.get_product_recommendations.return_value = mock_recommendations
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.get(
                "/v1/customer/my/recommendations?analysis_id=1",
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        mock_db.get_product_recommendations.assert_called_once()


class TestBookmarks:
    """Tests for bookmark endpoints"""
    
    def test_add_bookmark_success(self, client: TestClient, mock_customer, mock_db):
        """Test successful bookmark addition"""
        mock_analysis = {"id": 1, "customer_id": "test_customer_123"}
        mock_db.get_customer_analysis_detail.return_value = mock_analysis
        mock_db.add_bookmark.return_value = True
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/customer/my/analyses/1/bookmark",
                json={"notes": "Good result"},
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Bookmark added successfully"
    
    def test_add_bookmark_already_exists(self, client: TestClient, mock_customer, mock_db):
        """Test adding bookmark that already exists"""
        mock_analysis = {"id": 1, "customer_id": "test_customer_123"}
        mock_db.get_customer_analysis_detail.return_value = mock_analysis
        mock_db.add_bookmark.return_value = False
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.post(
                "/v1/customer/my/analyses/1/bookmark",
                json={},
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 409
    
    def test_remove_bookmark_success(self, client: TestClient, mock_customer, mock_db):
        """Test successful bookmark removal"""
        mock_db.remove_bookmark.return_value = True
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.delete(
                "/v1/customer/my/analyses/1/bookmark",
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Bookmark removed successfully"
    
    def test_get_bookmarks_success(self, client: TestClient, mock_customer, mock_db):
        """Test successful retrieval of bookmarks"""
        mock_bookmarks = [
            {
                "bookmark_id": 1,
                "analysis_id": 1,
                "original_filename": "test.jpg",
                "overall_score_restored": 70
            }
        ]
        mock_db.get_bookmarks.return_value = mock_bookmarks
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.get(
                "/v1/customer/my/bookmarks",
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "bookmarks" in data
        assert len(data["bookmarks"]) == 1


class TestNotificationSettings:
    """Tests for notification settings endpoints"""
    
    def test_get_notification_settings_success(self, client: TestClient, mock_customer, mock_db):
        """Test successful retrieval of notification settings"""
        mock_settings = {
            "customer_id": "test_customer_123",
            "analysis_complete": True,
            "score_improvement": True,
            "care_reminder": False,
            "marketing": False,
            "reminder_hours": 168
        }
        mock_db.get_notification_settings.return_value = mock_settings
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.get(
                "/v1/customer/my/notifications/settings",
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["analysis_complete"] == True
        assert data["marketing"] == False
    
    def test_update_notification_settings_success(self, client: TestClient, mock_customer, mock_db):
        """Test successful update of notification settings"""
        mock_db.update_notification_settings.return_value = True
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.put(
                "/v1/customer/my/notifications/settings",
                json={"care_reminder": True, "reminder_hours": 72},
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Notification settings updated successfully"
    
    def test_update_notification_settings_no_fields(self, client: TestClient, mock_customer, mock_db):
        """Test update with no valid fields"""
        mock_db.update_notification_settings.return_value = False
        
        with patch('src.server.routers.customer.get_current_customer', return_value=mock_customer):
            response = client.put(
                "/v1/customer/my/notifications/settings",
                json={},
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 400


class TestUnauthorizedAccess:
    """Tests for unauthorized access prevention"""
    
    def test_unauthorized_compare_analyses(self, client: TestClient):
        """Test that unauthorized users cannot compare analyses"""
        with patch('src.server.routers.customer.get_current_customer', return_value=None):
            response = client.post(
                "/v1/customer/my/analyses/compare",
                json={"analysis_id_1": 1, "analysis_id_2": 2}
            )
        
        assert response.status_code == 401
    
    def test_unauthorized_bookmark(self, client: TestClient):
        """Test that unauthorized users cannot add bookmarks"""
        with patch('src.server.routers.customer.get_current_customer', return_value=None):
            response = client.post(
                "/v1/customer/my/analyses/1/bookmark",
                json={}
            )
        
        assert response.status_code == 401
