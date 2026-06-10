"""
App Features API endpoints tests.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestAppFeaturesAPI:
    """App Features API endpoints tests."""

    @pytest.fixture
    def client(self):
        """Test client fixture."""
        from src.server.server import app
        return TestClient(app)

    @pytest.fixture
    def mock_db(self):
        """Mock database fixture."""
        with patch('src.server.routers.app_features.SkinAnalysisDB') as mock:
            db_instance = MagicMock()
            mock.return_value = db_instance
            yield db_instance

    # ── 피부 일기 API ─────────────────────────────────────────────────────────────

    def test_create_diary_entry(self, client, mock_db):
        """Test creating a skin diary entry."""
        mock_db.create_skin_diary_entry.return_value = None
        
        response = client.post(
            "/v1/app/diary",
            json={
                "customer_id": "test_customer",
                "overall_score": 75.5,
                "notes": "Today was a good skin day"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "entry_id" in data
        assert data["customer_id"] == "test_customer"

    def test_get_diary_entries(self, client, mock_db):
        """Test getting skin diary entries."""
        mock_db.get_skin_diary_entries.return_value = [
            {"entry_id": "DIARY-001", "customer_id": "test_customer", "notes": "Entry 1"},
            {"entry_id": "DIARY-002", "customer_id": "test_customer", "notes": "Entry 2"}
        ]
        
        response = client.get("/v1/app/diary/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert len(data["entries"]) == 2

    # ── 고객 목표 API ─────────────────────────────────────────────────────────────

    def test_create_customer_goal(self, client, mock_db):
        """Test creating a customer goal."""
        mock_db.create_customer_goal.return_value = None
        
        response = client.post(
            "/v1/app/goals",
            json={
                "customer_id": "test_customer",
                "goal_type": "improve_skin_score",
                "target_value": 80.0
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "goal_id" in data

    def test_update_goal_progress(self, client, mock_db):
        """Test updating goal progress."""
        mock_db.update_customer_goal_progress.return_value = None
        
        response = client.put(
            "/v1/app/goals/GOAL-001/progress",
            params={"current_value": 75.0}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["current_value"] == 75.0

    def test_get_customer_goals(self, client, mock_db):
        """Test getting customer goals."""
        mock_db.get_customer_goals.return_value = [
            {"goal_id": "GOAL-001", "customer_id": "test_customer", "goal_type": "improve_skin_score"}
        ]
        
        response = client.get("/v1/app/goals/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "goals" in data

    # ── 업적 API ─────────────────────────────────────────────────────────────────

    def test_create_achievement(self, client, mock_db):
        """Test creating an achievement (admin)."""
        mock_db.create_achievement.return_value = None
        
        response = client.post(
            "/v1/app/achievements",
            json={
                "achievement_id": "ACH-001",
                "name": "First Analysis",
                "description": "Complete your first skin analysis"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "achievement_id" in data

    def test_earn_achievement(self, client, mock_db):
        """Test earning an achievement."""
        mock_db.earn_achievement.return_value = None
        
        response = client.post(
            "/v1/app/achievements/earn",
            json={
                "customer_id": "test_customer",
                "achievement_id": "ACH-001"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "earned_at" in data

    def test_get_customer_achievements(self, client, mock_db):
        """Test getting customer achievements."""
        mock_db.get_customer_achievements.return_value = [
            {"achievement_id": "ACH-001", "customer_id": "test_customer", "earned_at": "2026-06-10"}
        ]
        
        response = client.get("/v1/app/achievements/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "achievements" in data

    # ── 제품 구독 API ─────────────────────────────────────────────────────────────

    def test_create_subscription(self, client, mock_db):
        """Test creating a product subscription."""
        mock_db.create_product_subscription.return_value = None
        
        response = client.post(
            "/v1/app/subscriptions",
            json={
                "customer_id": "test_customer",
                "product_id": "PROD-001",
                "plan_type": "monthly"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "subscription_id" in data

    def test_get_customer_subscriptions(self, client, mock_db):
        """Test getting customer subscriptions."""
        mock_db.get_customer_subscriptions.return_value = [
            {"subscription_id": "SUB-001", "customer_id": "test_customer", "product_id": "PROD-001"}
        ]
        
        response = client.get("/v1/app/subscriptions/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "subscriptions" in data

    # ── 챌린지 API ───────────────────────────────────────────────────────────────

    def test_create_challenge(self, client, mock_db):
        """Test creating a challenge (admin)."""
        mock_db.create_challenge.return_value = None
        
        response = client.post(
            "/v1/app/challenges",
            json={
                "challenge_id": "CHAL-001",
                "name": "30-Day Skin Challenge",
                "description": "Improve your skin in 30 days"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "challenge_id" in data

    def test_join_challenge(self, client, mock_db):
        """Test joining a challenge."""
        mock_db.join_challenge.return_value = None
        
        response = client.post(
            "/v1/app/challenges/join",
            json={
                "customer_id": "test_customer",
                "challenge_id": "CHAL-001"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "joined_at" in data

    def test_update_challenge_progress(self, client, mock_db):
        """Test updating challenge progress."""
        mock_db.update_challenge_progress.return_value = None
        
        response = client.put(
            "/v1/app/challenges/progress",
            json={
                "customer_id": "test_customer",
                "challenge_id": "CHAL-001",
                "current_value": 15.0
            }
        )
        
        assert response.status_code == 200

    def test_get_customer_challenges(self, client, mock_db):
        """Test getting customer challenges."""
        mock_db.get_customer_challenges.return_value = [
            {"challenge_id": "CHAL-001", "customer_id": "test_customer", "progress": 50.0}
        ]
        
        response = client.get("/v1/app/challenges/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "challenges" in data

    # ── PCR 검사 API ─────────────────────────────────────────────────────────────

    def test_create_pcr_test_request(self, client, mock_db):
        """Test creating a PCR test request."""
        mock_db.create_pcr_test_request.return_value = None
        
        response = client.post(
            "/v1/app/pcr/request",
            json={
                "customer_id": "test_customer",
                "test_type": "skin_sensitivity"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data

    def test_get_pcr_test_results(self, client, mock_db):
        """Test getting PCR test results."""
        mock_db.get_pcr_test_results_by_customer.return_value = [
            {"request_id": "PCR-001", "customer_id": "test_customer", "result": "positive"}
        ]
        
        response = client.get("/v1/app/pcr/results/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    def test_get_pcr_test_history(self, client, mock_db):
        """Test getting PCR test history."""
        mock_db.get_pcr_test_history.return_value = [
            {"request_id": "PCR-001", "customer_id": "test_customer", "test_date": "2026-06-10"}
        ]
        
        response = client.get("/v1/app/pcr/history/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "history" in data

    def test_create_pcr_consultation(self, client, mock_db):
        """Test creating a PCR consultation."""
        mock_db.create_pcr_consultation.return_value = None
        
        response = client.post(
            "/v1/app/pcr/consultation",
            json={
                "customer_id": "test_customer",
                "preferred_date": "2026-06-15",
                "preferred_time": "10:00"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "consultation_id" in data

    def test_get_pcr_consultations(self, client, mock_db):
        """Test getting PCR consultations."""
        mock_db.get_pcr_consultations.return_value = [
            {"consultation_id": "CONS-001", "customer_id": "test_customer", "status": "scheduled"}
        ]
        
        response = client.get("/v1/app/pcr/consultations/test_customer")
        
        assert response.status_code == 200
        data = response.json()
        assert "consultations" in data
