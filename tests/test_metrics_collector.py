"""
MetricsCollector 단위 테스트 - 메트릭 수집, 타이머, 리포트
"""
import pytest


class TestMetricsCollector:
    """MetricsCollector 테스트"""

    def test_singleton_pattern(self):
        """싱글톤 패턴 확인"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        instance1 = MetricsCollector.get_instance()
        instance2 = MetricsCollector.get_instance()
        assert instance1 is instance2

    def test_counter_increment(self):
        """카운터 증가 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()  # 초기화
        
        collector.increment("test_counter", value=5)
        assert collector.get_counter("test_counter") == 5
        
        collector.increment("test_counter", value=3)
        assert collector.get_counter("test_counter") == 8

    def test_counter_decrement(self):
        """카운터 감소 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        collector.increment("test_counter", value=10)
        collector.decrement("test_counter", value=3)
        assert collector.get_counter("test_counter") == 7

    def test_gauge_set(self):
        """게이지 설정 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        collector.set_gauge("test_gauge", 42.5)
        assert collector.get_gauge("test_gauge") == 42.5
        
        collector.set_gauge("test_gauge", 99.9)
        assert collector.get_gauge("test_gauge") == 99.9

    def test_timer_context_manager(self):
        """타이머 컨텍스트 매니저 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        import time
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        with collector.measure("test_operation"):
            time.sleep(0.1)
        
        stats = collector.get_timer_stats("test_operation")
        assert stats["count"] == 1
        assert stats["avg"] >= 0.1

    def test_timer_record_time(self):
        """타이머 직접 기록 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        collector.record_time("test_timer", 0.5)
        collector.record_time("test_timer", 1.0)
        collector.record_time("test_timer", 1.5)
        
        stats = collector.get_timer_stats("test_timer")
        assert stats["count"] == 3
        assert stats["min"] == 0.5
        assert stats["max"] == 1.5
        assert stats["avg"] == 1.0

    def test_histogram_record(self):
        """히스토그램 기록 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        collector.record_histogram("test_histogram", 10.0)
        collector.record_histogram("test_histogram", 20.0)
        collector.record_histogram("test_histogram", 30.0)
        
        stats = collector.get_histogram_stats("test_histogram")
        assert stats["count"] == 3
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert stats["avg"] == 20.0

    def test_get_report(self):
        """메트릭 리포트 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        collector.increment("test_counter", value=5)
        collector.set_gauge("test_gauge", 42.0)
        collector.record_time("test_timer", 0.5)
        
        report = collector.get_report()
        
        assert "counters" in report
        assert "timers" in report
        assert "gauges" in report
        assert "histograms" in report
        assert report["counters"]["test_counter"] == 5
        assert report["gauges"]["test_gauge"] == 42.0

    def test_reset(self):
        """메트릭 초기화 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        
        collector.increment("test_counter", value=5)
        collector.set_gauge("test_gauge", 42.0)
        collector.record_time("test_timer", 0.5)
        
        collector.reset()
        
        assert collector.get_counter("test_counter") == 0
        assert collector.get_gauge("test_gauge") == 0.0
        assert collector.get_timer_stats("test_timer")["count"] == 0

    def test_timer_percentiles(self):
        """타이머 백분위수 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        # 100개의 값 기록 (0.0 ~ 0.99)
        for i in range(100):
            collector.record_time("test_percentiles", i / 100.0)
        
        stats = collector.get_timer_stats("test_percentiles")
        
        assert stats["p50"] >= 0.45  # 대략 중간값
        assert stats["p95"] >= 0.90  # 95번째 백분위수
        assert stats["p99"] >= 0.95  # 99번째 백분위수

    def test_empty_metrics(self):
        """빈 메트릭 테스트"""
        from src.monitoring.metrics_collector import MetricsCollector
        
        collector = MetricsCollector.get_instance()
        collector.reset()
        
        # 존재하지 않는 메트릭 조회
        assert collector.get_counter("nonexistent") == 0
        assert collector.get_gauge("nonexistent") == 0.0
        
        stats = collector.get_timer_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["avg"] == 0.0
