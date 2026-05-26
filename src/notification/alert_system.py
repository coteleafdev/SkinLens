"""
alert_system.py — 알림 시스템 (Slack, PagerDuty)

기능:
- Slack 알림 전송
- PagerDuty 알림 전송
- 이메일 알림 전송
- 알림 템플릿 관리
"""
import logging
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """알림 설정"""
    slack_webhook_url: Optional[str] = None
    slack_channel: Optional[str] = None
    pagerduty_integration_key: Optional[str] = None
    pagerduty_api_key: Optional[str] = None
    email_enabled: bool = False
    email_smtp_server: Optional[str] = None
    email_smtp_port: int = 587
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[str] = None


class AlertSystem:
    """알림 시스템"""
    
    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or self._load_config_from_env()
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    def _load_config_from_env(self) -> AlertConfig:
        """환경변수에서 설정 로드"""
        return AlertConfig(
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
            slack_channel=os.getenv("SLACK_CHANNEL", "#alerts"),
            pagerduty_integration_key=os.getenv("PAGERDUTY_INTEGRATION_KEY"),
            pagerduty_api_key=os.getenv("PAGERDUTY_API_KEY"),
            email_enabled=os.getenv("EMAIL_ENABLED", "false").lower() == "true",
            email_smtp_server=os.getenv("EMAIL_SMTP_SERVER"),
            email_smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
            email_username=os.getenv("EMAIL_USERNAME"),
            email_password=os.getenv("EMAIL_PASSWORD"),
            email_from=os.getenv("EMAIL_FROM"),
            email_to=os.getenv("EMAIL_TO"),
        )
    
    async def send_incident_alert(
        self,
        incident_id: str,
        incident_type: str,
        severity: str,
        resource_type: str,
        resource_id: str,
        description: Optional[str] = None,
    ):
        """장애 알림 전송"""
        message = self._format_incident_message(
            incident_id, incident_type, severity, resource_type, resource_id, description
        )
        
        # Slack 알림
        if self.config.slack_webhook_url:
            await self._send_slack_alert(message, severity)
        
        # PagerDuty 알림
        if self.config.pagerduty_integration_key and severity in ["P0", "P1"]:
            await self._send_pagerduty_alert(
                incident_id, incident_type, severity, resource_type, resource_id, description
            )
        
        # 이메일 알림
        if self.config.email_enabled:
            await self._send_email_alert(message, severity)
    
    async def send_recovery_alert(
        self,
        incident_id: str,
        action_type: str,
        status: str,
    ):
        """복구 알림 전송"""
        message = self._format_recovery_message(incident_id, action_type, status)
        
        # Slack 알림
        if self.config.slack_webhook_url:
            await self._send_slack_alert(message, "info")
    
    def _format_incident_message(
        self,
        incident_id: str,
        incident_type: str,
        severity: str,
        resource_type: str,
        resource_id: str,
        description: Optional[str],
    ) -> str:
        """장애 메시지 포맷팅"""
        emoji = self._get_severity_emoji(severity)
        message = f"""
{emoji} 장애 감지

**장애 ID:** {incident_id}
**유형:** {incident_type}
**심각도:** {severity}
**리소스:** {resource_type} ({resource_id})
**설명:** {description or 'N/A'}
"""
        return message
    
    def _format_recovery_message(
        self,
        incident_id: str,
        action_type: str,
        status: str,
    ) -> str:
        """복구 메시지 포맷팅"""
        emoji = "✅" if status == "completed" else "⚠️"
        message = f"""
{emoji} 복구 작업

**장애 ID:** {incident_id}
**작업 유형:** {action_type}
**상태:** {status}
"""
        return message
    
    def _get_severity_emoji(self, severity: str) -> str:
        """심각도에 따른 이모지 반환"""
        emoji_map = {
            "P0": "🔴",
            "P1": "🟠",
            "P2": "🟡",
            "P3": "🟢",
        }
        return emoji_map.get(severity, "⚪")
    
    async def _send_slack_alert(self, message: str, severity: str):
        """Slack 알림 전송"""
        try:
            color = self._get_slack_color(severity)
            payload = {
                "channel": self.config.slack_channel,
                "attachments": [
                    {
                        "color": color,
                        "text": message,
                        "mrkdwn_in": ["text"],
                    }
                ],
            }
            
            response = await self.http_client.post(
                self.config.slack_webhook_url,
                json=payload,
            )
            response.raise_for_status()
            log.info("[Alert] Slack 알림 전송 성공")
        except Exception as e:
            log.error(f"[Alert] Slack 알림 전송 실패: {e}")
    
    def _get_slack_color(self, severity: str) -> str:
        """Slack 색상 반환"""
        color_map = {
            "P0": "danger",
            "P1": "warning",
            "P2": "warning",
            "P3": "good",
            "info": "good",
        }
        return color_map.get(severity, "good")
    
    async def _send_pagerduty_alert(
        self,
        incident_id: str,
        incident_type: str,
        severity: str,
        resource_type: str,
        resource_id: str,
        description: Optional[str],
    ):
        """PagerDuty 알림 전송"""
        try:
            payload = {
                "routing_key": self.config.pagerduty_integration_key,
                "event_action": "trigger",
                "payload": {
                    "summary": f"[{severity}] {incident_type}: {resource_type}/{resource_id}",
                    "severity": self._get_pagerduty_severity(severity),
                    "source": "SkinLens",
                    "custom_details": {
                        "incident_id": incident_id,
                        "incident_type": incident_type,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "description": description,
                    },
                },
            }
            
            response = await self.http_client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            response.raise_for_status()
            log.info("[Alert] PagerDuty 알림 전송 성공")
        except Exception as e:
            log.error(f"[Alert] PagerDuty 알림 전송 실패: {e}")
    
    def _get_pagerduty_severity(self, severity: str) -> str:
        """PagerDuty 심각도 반환"""
        severity_map = {
            "P0": "critical",
            "P1": "error",
            "P2": "warning",
            "P3": "info",
        }
        return severity_map.get(severity, "info")
    
    async def _send_email_alert(self, message: str, severity: str):
        """이메일 알림 전송"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg["From"] = self.config.email_from
            msg["To"] = self.config.email_to
            msg["Subject"] = f"[{severity}] SkinLens 장애 알림"
            
            msg.attach(MIMEText(message, "plain"))
            
            with smtplib.SMTP(self.config.email_smtp_server, self.config.email_smtp_port) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
            
            log.info("[Alert] 이메일 알림 전송 성공")
        except Exception as e:
            log.error(f"[Alert] 이메일 알림 전송 실패: {e}")
    
    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.http_client.aclose()
