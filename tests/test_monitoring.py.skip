"""
test_monitoring.py — 모니터링 및 알림 테스트
"""
import pytest
from src.server.monitoring import AlertSystem, PerformanceMonitor, ExceptionReporter


class TestAlertSystem:
    """알림 시스템 테스트"""

    def test_alert_system_initialization(self):
        """알림 시스템 초기화 테스트"""
        alert_system = AlertSystem()
        assert alert_system.slack_webhook_url is None
        assert alert_system.email_smtp_server is None
        assert alert_system.email_to == []

    def test_slack_alert_no_webhook(self):
        """Slack 웹훅 URL이 없는 경우 테스트"""
        alert_system = AlertSystem()
        result = alert_system.send_slack_alert("Test message")
        assert result is False

    def test_email_alert_no_config(self):
        """이메일 설정이 없는 경우 테스트"""
        alert_system = AlertSystem()
        result = alert_system.send_email_alert("Test subject", "Test message")
        assert result is False

    def test_send_alert_no_config(self):
        """설정 없이 알림 전송 테스트"""
        alert_system = AlertSystem()
        # 예외가 발생하지 않아야 함
        alert_system.send_alert("Test message", level="INFO")


class TestPerformanceMonitor:
    """성능 모니터 테스트"""

    def test_performance_monitor_initialization(self):
        """성능 모니터 초기화 테스트"""
        monitor = PerformanceMonitor()
        assert monitor.metrics == {}
        assert monitor.alert_system is None

    def test_record_metric(self):
        """메트릭 기록 테스트"""
        monitor = PerformanceMonitor()
        monitor.record_metric("test_metric", 75.5)

        assert "test_metric" in monitor.metrics
        assert monitor.metrics["test_metric"]["value"] == 75.5
        assert "timestamp" in monitor.metrics["test_metric"]

    def test_record_metric_with_threshold(self):
        """임계값 초과 테스트"""
        monitor = PerformanceMonitor()
        # 임계값 초과 (로그 경고 발생)
        monitor.record_metric("test_metric", 95.0, threshold=90.0)

        assert "test_metric" in monitor.metrics
        assert monitor.metrics["test_metric"]["value"] == 95.0

    def test_get_metrics(self):
        """메트릭 조회 테스트"""
        monitor = PerformanceMonitor()
        monitor.record_metric("metric1", 50.0)
        monitor.record_metric("metric2", 75.0)

        metrics = monitor.get_metrics()
        assert len(metrics) == 2
        assert "metric1" in metrics
        assert "metric2" in metrics

    def test_clear_metrics(self):
        """메트릭 초기화 테스트"""
        monitor = PerformanceMonitor()
        monitor.record_metric("test_metric", 50.0)
        monitor.clear_metrics()

        assert monitor.metrics == {}


class TestExceptionReporter:
    """예외 보고자 테스트"""

    def test_exception_reporter_initialization(self):
        """예외 보고자 초기화 테스트"""
        reporter = ExceptionReporter()
        assert reporter.alert_system is None

    def test_report_exception(self):
        """예외 보고 테스트"""
        reporter = ExceptionReporter()
        # 예외가 발생하지 않아야 함
        try:
            raise ValueError("Test exception")
        except Exception as e:
            reporter.report_exception(e, context={"test": "data"})

    def test_report_exception_no_context(self):
        """컨텍스트 없이 예외 보고 테스트"""
        reporter = ExceptionReporter()
        # 예외가 발생하지 않아야 함
        try:
            raise ValueError("Test exception")
        except Exception as e:
            reporter.report_exception(e)

    def test_monitoring_config_from_json(self):
        """config.json에서 모니터링 설정 로드 확인"""
        from src.utils.config import load_config

        config = load_config()
        server_config = config.get("server", {})
        monitoring_config = server_config.get("monitoring", {})

        assert "slack_webhook_url" in monitoring_config
        assert "email_smtp_server" in monitoring_config
        assert "email_smtp_port" in monitoring_config
        assert "email_to" in monitoring_config
