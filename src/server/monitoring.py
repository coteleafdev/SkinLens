"""
monitoring.py — 모니터링 및 알림 시스템

기능:
- 에러 알림 (Slack, Email)
- 성능 모니터링
- 예외 발생 시 자동 보고
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime
import requests

log = logging.getLogger(__name__)


class AlertSystem:
    """알림 시스템"""

    def __init__(
        self,
        slack_webhook_url: Optional[str] = None,
        email_smtp_server: Optional[str] = None,
        email_smtp_port: int = 587,
        email_username: Optional[str] = None,
        email_password: Optional[str] = None,
        email_from: Optional[str] = None,
        email_to: Optional[list[str]] = None,
    ):
        """
        Args:
            slack_webhook_url: Slack 웹훅 URL
            email_smtp_server: SMTP 서버
            email_smtp_port: SMTP 포트
            email_username: SMTP 사용자명
            email_password: SMTP 비밀번호
            email_from: 발신자 이메일
            email_to: 수신자 이메일 목록
        """
        self.slack_webhook_url = slack_webhook_url
        self.email_smtp_server = email_smtp_server
        self.email_smtp_port = email_smtp_port
        self.email_username = email_username
        self.email_password = email_password
        self.email_from = email_from
        self.email_to = email_to or []

    def send_slack_alert(self, message: str, level: str = "INFO") -> bool:
        """Slack 알림 전송.

        Args:
            message: 알림 메시지
            level: 로그 레벨 (INFO, WARNING, ERROR)

        Returns:
            전송 성공 여부
        """
        if not self.slack_webhook_url:
            log.warning("Slack 웹훅 URL이 설정되지 않음")
            return False

        try:
            # 색상 설정
            color_map = {
                "INFO": "#36a64f",  # green
                "WARNING": "#ff9900",  # orange
                "ERROR": "#ff0000",  # red
            }
            color = color_map.get(level, "#36a64f")

            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": f"SkinLens Alert [{level}]",
                        "text": message,
                        "footer": "SkinLens Monitoring",
                        "ts": int(datetime.utcnow().timestamp()),
                    }
                ]
            }

            response = requests.post(self.slack_webhook_url, json=payload, timeout=10)
            response.raise_for_status()

            log.info("Slack 알림 전송 성공: level=%s", level)
            return True

        except Exception as e:
            log.error("Slack 알림 전송 실패: %s", e)
            return False

    def send_email_alert(self, subject: str, message: str) -> bool:
        """이메일 알림 전송.

        Args:
            subject: 이메일 제목
            message: 이메일 본문

        Returns:
            전송 성공 여부
        """
        if not self.email_smtp_server or not self.email_to:
            log.warning("이메일 설정이 완료되지 않음")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_from
            msg["To"] = ", ".join(self.email_to)
            msg["Subject"] = subject

            msg.attach(MIMEText(message, "plain", "utf-8"))

            with smtplib.SMTP(self.email_smtp_server, self.email_smtp_port) as server:
                server.starttls()
                if self.email_username and self.email_password:
                    server.login(self.email_username, self.email_password)
                server.send_message(msg)

            log.info("이메일 알림 전송 성공: subject=%s", subject)
            return True

        except Exception as e:
            log.error("이메일 알림 전송 실패: %s", e)
            return False

    def send_alert(self, message: str, level: str = "INFO", subject: Optional[str] = None) -> None:
        """모든 알림 채널로 전송.

        Args:
            message: 알림 메시지
            level: 로그 레벨
            subject: 이메일 제목 (선택적)
        """
        # Slack 알림
        self.send_slack_alert(message, level)

        # 이메일 알림 (ERROR 레벨만)
        if level == "ERROR":
            email_subject = subject or f"SkinLens Alert [{level}]"
            self.send_email_alert(email_subject, message)


class PerformanceMonitor:
    """성능 모니터"""

    def __init__(self, alert_system: Optional[AlertSystem] = None):
        """
        Args:
            alert_system: 알림 시스템
        """
        self.alert_system = alert_system
        self.metrics: Dict[str, Any] = {}

    def record_metric(self, name: str, value: float, threshold: Optional[float] = None) -> None:
        """메트릭 기록.

        Args:
            name: 메트릭 이름
            value: 메트릭 값
            threshold: 경고 임계값
        """
        self.metrics[name] = {
            "value": value,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 임계값 초과 시 알림
        if threshold and value > threshold:
            message = f"메트릭 임계값 초과: {name}={value:.2f} (threshold={threshold})"
            log.warning(message)
            if self.alert_system:
                self.alert_system.send_alert(message, level="WARNING")

    def get_metrics(self) -> Dict[str, Any]:
        """메트릭 조회"""
        return self.metrics

    def clear_metrics(self) -> None:
        """메트릭 초기화"""
        self.metrics.clear()


class ExceptionReporter:
    """예외 보고자"""

    def __init__(self, alert_system: Optional[AlertSystem] = None):
        """
        Args:
            alert_system: 알림 시스템
        """
        self.alert_system = alert_system

    def report_exception(self, exception: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """예외 보고.

        Args:
            exception: 예외 객체
            context: 추가 컨텍스트 정보
        """
        exception_type = type(exception).__name__
        exception_message = str(exception)

        message = f"예외 발생: {exception_type}\n메시지: {exception_message}"

        if context:
            message += f"\n컨텍스트: {context}"

        log.error(message)

        if self.alert_system:
            self.alert_system.send_alert(message, level="ERROR", subject=f"Exception: {exception_type}")


# 전역 인스턴스
_global_alert_system: Optional[AlertSystem] = None
_global_performance_monitor: Optional[PerformanceMonitor] = None
_global_exception_reporter: Optional[ExceptionReporter] = None


def get_alert_system() -> AlertSystem:
    """전역 알림 시스템 반환"""
    global _global_alert_system
    if _global_alert_system is None:
        from src.utils.config import load_config
        config = load_config()
        monitoring_config = config.get("server", {}).get("monitoring", {})

        _global_alert_system = AlertSystem(
            slack_webhook_url=monitoring_config.get("slack_webhook_url"),
            email_smtp_server=monitoring_config.get("email_smtp_server"),
            email_smtp_port=monitoring_config.get("email_smtp_port", 587),
            email_username=monitoring_config.get("email_username"),
            email_password=monitoring_config.get("email_password"),
            email_from=monitoring_config.get("email_from"),
            email_to=monitoring_config.get("email_to", []),
        )
    return _global_alert_system


def get_performance_monitor() -> PerformanceMonitor:
    """전역 성능 모니터 반환"""
    global _global_performance_monitor
    if _global_performance_monitor is None:
        _global_performance_monitor = PerformanceMonitor(alert_system=get_alert_system())
    return _global_performance_monitor


def get_exception_reporter() -> ExceptionReporter:
    """전역 예외 보고자 반환"""
    global _global_exception_reporter
    if _global_exception_reporter is None:
        _global_exception_reporter = ExceptionReporter(alert_system=get_alert_system())
    return _global_exception_reporter
