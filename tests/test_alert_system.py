"""
test_alert_system.py — 알림 시스템 단위 테스트

Slack, PagerDuty, 이메일 알림 시스템 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.notification.alert_system import AlertSystem, AlertConfig


class TestAlertConfig:
    """AlertConfig 테스트"""
    
    def test_alert_config_default_values(self):
        """AlertConfig 기본값 테스트"""
        config = AlertConfig()
        
        assert config.slack_webhook_url is None
        assert config.slack_channel is None
        assert config.pagerduty_integration_key is None
        assert config.pagerduty_api_key is None
        assert config.email_enabled is False
        assert config.email_smtp_server is None
        assert config.email_smtp_port == 587
        assert config.email_username is None
        assert config.email_password is None
        assert config.email_from is None
        assert config.email_to is None
    
    def test_alert_config_custom_values(self):
        """AlertConfig 사용자 정의값 테스트"""
        config = AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
            slack_channel="#alerts",
            pagerduty_integration_key="test-key",
            pagerduty_api_key="test-api-key",
            email_enabled=True,
            email_smtp_server="smtp.example.com",
            email_smtp_port=25,
            email_username="user@example.com",
            email_password="password",
            email_from="noreply@example.com",
            email_to="admin@example.com"
        )
        
        assert config.slack_webhook_url == "https://hooks.slack.com/test"
        assert config.slack_channel == "#alerts"
        assert config.pagerduty_integration_key == "test-key"
        assert config.pagerduty_api_key == "test-api-key"
        assert config.email_enabled is True
        assert config.email_smtp_server == "smtp.example.com"
        assert config.email_smtp_port == 25
        assert config.email_username == "user@example.com"
        assert config.email_password == "password"
        assert config.email_from == "noreply@example.com"
        assert config.email_to == "admin@example.com"


class TestAlertSystem:
    """AlertSystem 테스트"""
    
    @pytest.fixture
    def mock_config(self):
        """테스트용 설정 fixture"""
        return AlertConfig(
            slack_webhook_url="https://hooks.slack.com/test",
            slack_channel="#alerts",
            pagerduty_integration_key="test-key",
            pagerduty_api_key="test-api-key",
            email_enabled=False  # 이메일은 테스트에서 비활성화
        )
    
    @pytest.fixture
    def alert_system(self, mock_config):
        """AlertSystem fixture"""
        with patch('src.notification.alert_system.httpx.AsyncClient'):
            system = AlertSystem(config=mock_config)
            yield system
    
    def test_init_with_config(self, mock_config):
        """설정으로 초기화 테스트"""
        with patch('src.notification.alert_system.httpx.AsyncClient'):
            system = AlertSystem(config=mock_config)
            assert system.config == mock_config
    
    def test_init_without_config(self):
        """환경변수로 초기화 테스트"""
        with patch.dict('os.environ', {
            'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/env',
            'SLACK_CHANNEL': '#env-alerts',
            'PAGERDUTY_INTEGRATION_KEY': 'env-key',
            'PAGERDUTY_API_KEY': 'env-api-key',
            'EMAIL_ENABLED': 'true',
            'EMAIL_SMTP_SERVER': 'smtp.env.com',
            'EMAIL_SMTP_PORT': '25',
            'EMAIL_USERNAME': 'env@example.com',
            'EMAIL_PASSWORD': 'env-password',
            'EMAIL_FROM': 'env-noreply@example.com',
            'EMAIL_TO': 'env-admin@example.com'
        }):
            with patch('src.notification.alert_system.httpx.AsyncClient'):
                system = AlertSystem()
                
                assert system.config.slack_webhook_url == 'https://hooks.slack.com/env'
                assert system.config.slack_channel == '#env-alerts'
                assert system.config.pagerduty_integration_key == 'env-key'
                assert system.config.pagerduty_api_key == 'env-api-key'
                assert system.config.email_enabled is True
                assert system.config.email_smtp_server == 'smtp.env.com'
                assert system.config.email_smtp_port == 25
                assert system.config.email_username == 'env@example.com'
                assert system.config.email_password == 'env-password'
                assert system.config.email_from == 'env-noreply@example.com'
                assert system.config.email_to == 'env-admin@example.com'
    
    def test_format_incident_message(self, alert_system):
        """장애 메시지 포맷팅 테스트"""
        message = alert_system._format_incident_message(
            incident_id="INC-001",
            incident_type="Server Down",
            severity="P0",
            resource_type="Server",
            resource_id="srv-001",
            description="Server not responding"
        )
        
        assert "INC-001" in message
        assert "Server Down" in message
        assert "P0" in message
        assert "Server" in message
        assert "srv-001" in message
        assert "Server not responding" in message
        assert "🔴" in message  # P0 emoji
    
    def test_format_incident_message_no_description(self, alert_system):
        """설명 없는 장애 메시지 포맷팅 테스트"""
        message = alert_system._format_incident_message(
            incident_id="INC-002",
            incident_type="High CPU",
            severity="P1",
            resource_type="Server",
            resource_id="srv-002",
            description=None
        )
        
        assert "N/A" in message
    
    def test_format_recovery_message(self, alert_system):
        """복구 메시지 포맷팅 테스트"""
        message = alert_system._format_recovery_message(
            incident_id="INC-001",
            action_type="Restart",
            status="completed"
        )
        
        assert "INC-001" in message
        assert "Restart" in message
        assert "completed" in message
        assert "✅" in message  # completed emoji
    
    def test_format_recovery_message_warning(self, alert_system):
        """경고 상태 복구 메시지 포맷팅 테스트"""
        message = alert_system._format_recovery_message(
            incident_id="INC-002",
            action_type="Scale",
            status="partial"
        )
        
        assert "⚠️" in message  # partial emoji
    
    def test_get_severity_emoji(self, alert_system):
        """심각도 이모지 테스트"""
        assert alert_system._get_severity_emoji("P0") == "🔴"
        assert alert_system._get_severity_emoji("P1") == "🟠"
        assert alert_system._get_severity_emoji("P2") == "🟡"
        assert alert_system._get_severity_emoji("P3") == "🟢"
        assert alert_system._get_severity_emoji("unknown") == "⚪"
    
    def test_get_slack_color(self, alert_system):
        """Slack 색상 테스트"""
        assert alert_system._get_slack_color("P0") == "danger"
        assert alert_system._get_slack_color("P1") == "warning"
        assert alert_system._get_slack_color("P2") == "warning"
        assert alert_system._get_slack_color("P3") == "good"
        assert alert_system._get_slack_color("info") == "good"
        assert alert_system._get_slack_color("unknown") == "good"
    
    def test_get_pagerduty_severity(self, alert_system):
        """PagerDuty 심각도 테스트"""
        assert alert_system._get_pagerduty_severity("P0") == "critical"
        assert alert_system._get_pagerduty_severity("P1") == "error"
        assert alert_system._get_pagerduty_severity("P2") == "warning"
        assert alert_system._get_pagerduty_severity("P3") == "info"
        assert alert_system._get_pagerduty_severity("unknown") == "info"
    
    @pytest.mark.asyncio
    async def test_send_incident_alert_slack_only(self, alert_system):
        """Slack만 사용하는 장애 알림 테스트"""
        alert_system.config.pagerduty_integration_key = None
        alert_system.config.email_enabled = False
        
        alert_system._send_slack_alert = AsyncMock()
        
        await alert_system.send_incident_alert(
            incident_id="INC-001",
            incident_type="Server Down",
            severity="P0",
            resource_type="Server",
            resource_id="srv-001",
            description="Server not responding"
        )
        
        alert_system._send_slack_alert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_incident_alert_pagerduty_p0(self, alert_system):
        """P0 심각도에서 PagerDuty 알림 테스트"""
        alert_system._send_slack_alert = AsyncMock()
        alert_system._send_pagerduty_alert = AsyncMock()
        
        await alert_system.send_incident_alert(
            incident_id="INC-001",
            incident_type="Server Down",
            severity="P0",
            resource_type="Server",
            resource_id="srv-001",
            description="Server not responding"
        )
        
        alert_system._send_slack_alert.assert_called_once()
        alert_system._send_pagerduty_alert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_incident_alert_pagerduty_p2(self, alert_system):
        """P2 심각도에서 PagerDuty 알림 테스트 (P0, P1만 전송)"""
        alert_system._send_slack_alert = AsyncMock()
        alert_system._send_pagerduty_alert = AsyncMock()
        
        await alert_system.send_incident_alert(
            incident_id="INC-002",
            incident_type="High CPU",
            severity="P2",
            resource_type="Server",
            resource_id="srv-002",
            description="CPU usage high"
        )
        
        alert_system._send_slack_alert.assert_called_once()
        alert_system._send_pagerduty_alert.assert_not_called()  # P2는 PagerDuty로 전송 안함
    
    @pytest.mark.asyncio
    async def test_send_recovery_alert(self, alert_system):
        """복구 알림 테스트"""
        alert_system._send_slack_alert = AsyncMock()
        
        await alert_system.send_recovery_alert(
            incident_id="INC-001",
            action_type="Restart",
            status="completed"
        )
        
        alert_system._send_slack_alert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_slack_alert_success(self, alert_system):
        """Slack 알림 전송 성공 테스트"""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        
        alert_system.http_client.post = AsyncMock(return_value=mock_response)
        
        await alert_system._send_slack_alert("Test message", "P0")
        
        alert_system.http_client.post.assert_called_once()
        call_args = alert_system.http_client.post.call_args
        assert call_args[0][0] == alert_system.config.slack_webhook_url
        assert "attachments" in call_args[1]["json"]
    
    @pytest.mark.asyncio
    async def test_send_slack_alert_failure(self, alert_system):
        """Slack 알림 전송 실패 테스트"""
        alert_system.http_client.post = AsyncMock(side_effect=Exception("Network error"))
        
        # 예외가 발생해도 함수는 계속 실행되어야 함
        await alert_system._send_slack_alert("Test message", "P0")
        
        # 에러 로깅만 수행되고 예외는 발생하지 않음
        alert_system.http_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_pagerduty_alert_success(self, alert_system):
        """PagerDuty 알림 전송 성공 테스트"""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        
        alert_system.http_client.post = AsyncMock(return_value=mock_response)
        
        await alert_system._send_pagerduty_alert(
            incident_id="INC-001",
            incident_type="Server Down",
            severity="P0",
            resource_type="Server",
            resource_id="srv-001",
            description="Server not responding"
        )
        
        alert_system.http_client.post.assert_called_once()
        call_args = alert_system.http_client.post.call_args
        assert call_args[0][0] == "https://events.pagerduty.com/v2/enqueue"
        assert "routing_key" in call_args[1]["json"]
    
    @pytest.mark.asyncio
    async def test_send_pagerduty_alert_failure(self, alert_system):
        """PagerDuty 알림 전송 실패 테스트"""
        alert_system.http_client.post = AsyncMock(side_effect=Exception("Network error"))
        
        # 예외가 발생해도 함수는 계속 실행되어야 함
        await alert_system._send_pagerduty_alert(
            incident_id="INC-001",
            incident_type="Server Down",
            severity="P0",
            resource_type="Server",
            resource_id="srv-001",
            description="Server not responding"
        )
        
        alert_system.http_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_email_alert_disabled(self, alert_system):
        """이메일 비활성화 테스트"""
        alert_system.config.email_enabled = False
        
        # 이메일이 비활성화되면 전송되지 않아야 함
        # 실제 전송 로직은 테스트하지 않음 (SMTP 서버 필요)
        await alert_system._send_email_alert("Test message", "P0")
    
    @pytest.mark.asyncio
    async def test_close(self, alert_system):
        """HTTP 클라이언트 종료 테스트"""
        alert_system.http_client.aclose = AsyncMock()
        
        await alert_system.close()
        
        alert_system.http_client.aclose.assert_called_once()
