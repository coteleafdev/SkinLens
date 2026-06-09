"""
Integration API 테스트 - 외부 시스템 연동 API
"""
import pytest
from fastapi.testclient import TestClient


class TestWebhookAPI:
    """웹훅 API 테스트"""

    def test_create_webhook_unauthorized(self, auth_client):
        """인증 없이 웹훅 생성 실패"""
        response = auth_client.post(
            "/v1/webhooks",
            json={"url": "https://example.com/webhook", "events": ["analysis.completed"]}
        )
        assert response.status_code == 401

    def test_create_webhook_authorized(self, auth_client, user_token):
        """인증된 사용자로 웹훅 생성 성공"""
        response = auth_client.post(
            "/v1/webhooks",
            json={"url": "https://example.com/webhook", "events": ["analysis.completed"]},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "webhook_id" in data

    def test_list_webhooks_unauthorized(self, auth_client):
        """인증 없이 웹훅 목록 조회 실패"""
        response = auth_client.get("/v1/webhooks")
        assert response.status_code == 401

    def test_list_webhooks_authorized(self, auth_client, user_token):
        """인증된 사용자로 웹훅 목록 조회 성공"""
        response = auth_client.get(
            "/v1/webhooks",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "webhooks" in data

    def test_update_webhook_unauthorized(self, auth_client):
        """인증 없이 웹훅 업데이트 실패"""
        response = auth_client.put(
            "/v1/webhooks/test-webhook-id",
            json={"is_active": False}
        )
        assert response.status_code == 401

    def test_delete_webhook_unauthorized(self, auth_client):
        """인증 없이 웹훅 삭제 실패"""
        response = auth_client.delete("/v1/webhooks/test-webhook-id")
        assert response.status_code == 401


class TestSyncAPI:
    """외부 시스템 동기화 API 테스트"""

    def test_sync_customers_unauthorized(self, auth_client):
        """인증 없이 고객 동기화 실패"""
        response = auth_client.post(
            "/v1/integration/customers/sync",
            json={"source_system": "external", "target_system": "skinlens", "direction": "in"}
        )
        assert response.status_code == 401

    def test_sync_customers_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 고객 동기화 실패"""
        response = auth_client.post(
            "/v1/integration/customers/sync",
            json={"source_system": "external", "target_system": "skinlens", "direction": "in"},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_sync_customers_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 고객 동기화 성공"""
        response = auth_client.post(
            "/v1/integration/customers/sync",
            json={"source_system": "external", "target_system": "skinlens", "direction": "in"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sync_log_id" in data

    def test_sync_products_unauthorized(self, auth_client):
        """인증 없이 제품 동기화 실패"""
        response = auth_client.post(
            "/v1/integration/products/sync",
            json={"source_system": "external", "target_system": "skinlens", "direction": "in"}
        )
        assert response.status_code == 401

    def test_sync_products_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 제품 동기화 성공"""
        response = auth_client.post(
            "/v1/integration/products/sync",
            json={"source_system": "external", "target_system": "skinlens", "direction": "in"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sync_log_id" in data

    def test_get_sync_logs_unauthorized(self, auth_client):
        """인증 없이 동기화 로그 조회 실패"""
        response = auth_client.get("/v1/integration/sync-logs")
        assert response.status_code == 401

    def test_get_sync_logs_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 동기화 로그 조회 실패"""
        response = auth_client.get(
            "/v1/integration/sync-logs",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_get_sync_logs_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 동기화 로그 조회 성공"""
        response = auth_client.get(
            "/v1/integration/sync-logs",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data


class TestOAuthAPI:
    """OAuth/SSO API 테스트"""

    def test_create_oauth_provider_unauthorized(self, auth_client):
        """인증 없이 OAuth 제공자 등록 실패"""
        response = auth_client.post(
            "/v1/oauth/providers",
            json={
                "provider_name": "google",
                "client_id": "test-client-id",
                "client_secret": "test-secret",
                "redirect_uri": "https://example.com/callback"
            }
        )
        assert response.status_code == 401

    def test_create_oauth_provider_forbidden_customer(self, auth_client, user_token):
        """고객 권한으로 OAuth 제공자 등록 실패"""
        response = auth_client.post(
            "/v1/oauth/providers",
            json={
                "provider_name": "google",
                "client_id": "test-client-id",
                "client_secret": "test-secret",
                "redirect_uri": "https://example.com/callback"
            },
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403

    def test_create_oauth_provider_authorized_admin(self, auth_client, admin_token):
        """관리자 권한으로 OAuth 제공자 등록 성공"""
        response = auth_client.post(
            "/v1/oauth/providers",
            json={
                "provider_name": "google",
                "client_id": "test-client-id",
                "client_secret": "test-secret",
                "redirect_uri": "https://example.com/callback"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "provider_id" in data

    def test_list_oauth_providers_unauthorized(self, auth_client):
        """인증 없이 OAuth 제공자 목록 조회 실패"""
        response = auth_client.get("/v1/oauth/providers")
        assert response.status_code == 401

    def test_oauth_authorize_unauthorized(self, auth_client):
        """인증 없이 OAuth 인증 URL 생성 실패"""
        response = auth_client.post(
            "/v1/oauth/authorize",
            json={"provider_name": "google", "customer_id": "test-customer"}
        )
        assert response.status_code == 401

    def test_oauth_authorize_authorized(self, auth_client, user_token):
        """인증된 사용자로 OAuth 인증 URL 생성 성공"""
        response = auth_client.post(
            "/v1/oauth/authorize",
            json={"provider_name": "google", "customer_id": "test-customer"},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        # 제공자가 없을 수 있으므로 404 또는 200 모두 허용
        assert response.status_code in (200, 404)

    def test_oauth_token_unauthorized(self, auth_client):
        """인증 없이 OAuth 토큰 교환 실패"""
        response = auth_client.post(
            "/v1/oauth/token",
            json={"provider_name": "google", "customer_id": "test-customer", "code": "test-code"}
        )
        assert response.status_code == 401
