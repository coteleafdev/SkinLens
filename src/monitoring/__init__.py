"""src.monitoring — 메트릭 수집 및 모니터링 패키지.

[REFACTOR P3] 메트릭 수집 체계:
  - MetricsCollector: 성능 메트릭 수집
  - 프로파일링 지원
  - 성능 최적화 지원

사용법:
    from src.monitoring import MetricsCollector

    collector = MetricsCollector.get_instance()
    with collector.measure("image_analysis"):
        analyze_image(image_path)
"""
from src.monitoring.metrics_collector import MetricsCollector, get_metrics_collector

__all__ = [
    "MetricsCollector",
    "get_metrics_collector",
]
