"""
test_app_features_api.py — 앱 기능 API 테스트

피부 일기, 고객 목표, 업적, 제품 구독, 챌린지 기능 테스트
"""
import pytest
from fastapi.testclient import TestClient
from src.server.server import app


class TestSkinDiaryAPI:
    """피부 일기 API 테스트"""

    def test_create_diary_entry(self, auth_client):
        """피부 일기 엔트리 생성"""
        response = auth_client.post(
            "/v1/app/diary",
            json={
                "customer_id": "customer123",
                "analysis_id": 1,
                "image_url": "https://example.com/image.jpg",
                "overall_score": 75.0,
                "measurement_scores": {"melasma_score": 80, "redness_score": 70},
                "notes": "오늘 피부 상태가 좋음",
                "mood": "happy",
                "weather": "sunny"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "entry_id" in data
        assert data["customer_id"] == "customer123"
        assert data["message"] == "피부 일기 엔트리가 생성되었습니다."

    def test_get_diary_entries(self, auth_client):
        """고객 피부 일기 엔트리 조회"""
        response = auth_client.get("/v1/app/diary/customer123?limit=30")
        assert response.status_code == 200
        data = response.json()
        assert "customer_id" in data
        assert "total_entries" in data
        assert "entries" in data


class TestCustomerGoalsAPI:
    """고객 목표 API 테스트"""

    def test_create_customer_goal(self, auth_client):
        """고객 목표 생성"""
        response = auth_client.post(
            "/v1/app/goals",
            json={
                "customer_id": "customer123",
                "goal_type": "skin_score",
                "target_value": 80.0,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "goal_id" in data
        assert data["customer_id"] == "customer123"
        assert data["goal_type"] == "skin_score"
        assert data["target_value"] == 80.0
        assert data["status"] == "active"

    def test_update_goal_progress(self, auth_client):
        """고객 목표 진행률 업데이트"""
        response = auth_client.put(
            "/v1/app/goals/GOAL-12345678/progress?current_value=50.0"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["goal_id"] == "GOAL-12345678"
        assert data["current_value"] == 50.0

    def test_get_customer_goals(self, auth_client):
        """고객 목표 조회"""
        response = auth_client.get("/v1/app/goals/customer123")
        assert response.status_code == 200
        data = response.json()
        assert "customer_id" in data
        assert "total_goals" in data
        assert "goals" in data


class TestAchievementsAPI:
    """업적 API 테스트"""

    def test_create_achievement(self, auth_client):
        """업적 생성 (관리자용)"""
        response = auth_client.post(
            "/v1/app/achievements",
            json={
                "achievement_id": "ACHV-001",
                "name": "First Analysis",
                "description": "첫 번째 피부 분석 완료",
                "icon": "🎯",
                "requirement_type": "analysis_count",
                "requirement_value": 1.0,
                "reward_points": 100
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["achievement_id"] == "ACHV-001"
        assert data["name"] == "First Analysis"
        assert data["message"] == "업적이 생성되었습니다."

    def test_earn_achievement(self, auth_client):
        """고객 업적 획득"""
        response = auth_client.post(
            "/v1/app/achievements/earn",
            json={
                "customer_id": "customer123",
                "achievement_id": "ACHV-001"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["customer_id"] == "customer123"
        assert data["achievement_id"] == "ACHV-001"
        assert "earned_at" in data

    def test_get_customer_achievements(self, auth_client):
        """고객 업적 조회"""
        response = auth_client.get("/v1/app/achievements/customer123")
        assert response.status_code == 200
        data = response.json()
        assert "customer_id" in data
        assert "total_achievements" in data
        assert "achievements" in data


class TestProductSubscriptionsAPI:
    """제품 구독 API 테스트"""

    def test_create_subscription(self, auth_client):
        """제품 구독 생성"""
        response = auth_client.post(
            "/v1/app/subscriptions",
            json={
                "customer_id": "customer123",
                "product_id": "PROD-001",
                "frequency": "monthly",
                "next_delivery_date": "2026-02-01"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "subscription_id" in data
        assert data["customer_id"] == "customer123"
        assert data["product_id"] == "PROD-001"
        assert data["frequency"] == "monthly"

    def test_get_customer_subscriptions(self, auth_client):
        """고객 구독 조회"""
        response = auth_client.get("/v1/app/subscriptions/customer123")
        assert response.status_code == 200
        data = response.json()
        assert "customer_id" in data
        assert "total_subscriptions" in data
        assert "subscriptions" in data


class TestChallengesAPI:
    """챌린지 API 테스트"""

    def test_create_challenge(self, auth_client):
        """챌린지 생성 (관리자용)"""
        response = auth_client.post(
            "/v1/app/challenges",
            json={
                "challenge_id": "CHLG-001",
                "name": "30-Day Skin Challenge",
                "description": "30일 동안 매일 피부 분석",
                "duration_days": 30,
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "reward_points": 500
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["challenge_id"] == "CHLG-001"
        assert data["name"] == "30-Day Skin Challenge"
        assert data["message"] == "챌린지가 생성되었습니다."

    def test_join_challenge(self, auth_client):
        """챌린지 참여"""
        response = auth_client.post(
            "/v1/app/challenges/join",
            json={
                "customer_id": "customer123",
                "challenge_id": "CHLG-001",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["customer_id"] == "customer123"
        assert data["challenge_id"] == "CHLG-001"
        assert data["message"] == "챌린지에 참여했습니다."

    def test_update_challenge_progress(self, auth_client):
        """챌린지 진행률 업데이트"""
        response = auth_client.put(
            "/v1/app/challenges/progress",
            json={
                "customer_id": "customer123",
                "challenge_id": "CHLG-001",
                "progress": 50.0
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["customer_id"] == "customer123"
        assert data["challenge_id"] == "CHLG-001"
        assert data["progress"] == 50.0

    def test_get_customer_challenges(self, auth_client):
        """고객 챌린지 조회"""
        response = auth_client.get("/v1/app/challenges/customer123")
        assert response.status_code == 200
        data = response.json()
        assert "customer_id" in data
        assert "total_challenges" in data
        assert "challenges" in data
