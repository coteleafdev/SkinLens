"""src.monitoring.metrics_collector — 메트릭 수집 체계.

[REFACTOR P3] 메트릭 수집 체계:
  - 성능 메트릭 수집
  - 프로파일링 지원
  - 메트릭 집계 및 리포트
  - 성능 최적화 지원

사용법:
    from src.monitoring.metrics_collector import MetricsCollector

    collector = MetricsCollector.get_instance()
    with collector.measure("image_analysis"):
        analyze_image(image_path)
    
    report = collector.get_report()
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


class MetricsCollector:
    """메트릭 수집자 (싱글톤 - Thread-safe with DCL pattern).
    
    성능 메트릭을 수집하고 집계하여 성능 최적화를 지원합니다.
    """
    
    _instance: Optional["MetricsCollector"] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls) -> "MetricsCollector":
        # Double-Checked Locking pattern for thread-safe singleton
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        
        # 메트릭 저장소
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
    
    # ── 카운터 메트릭 ───────────────────────────────────────────────────
    
    def increment(self, name: str, value: int = 1) -> None:
        """카운터 메트릭을 증가시킵니다.
        
        Args:
            name: 메트릭 이름
            value: 증가값 (기본값: 1)
        """
        self._counters[name] += value
        log.debug("카운터 증가: %s += %d (현재: %d)", name, value, self._counters[name])
    
    def decrement(self, name: str, value: int = 1) -> None:
        """카운터 메트릭을 감소시킵니다.
        
        Args:
            name: 메트릭 이름
            value: 감소값 (기본값: 1)
        """
        self._counters[name] -= value
        log.debug("카운터 감소: %s -= %d (현재: %d)", name, value, self._counters[name])
    
    def get_counter(self, name: str) -> int:
        """카운터 메트릭을 반환합니다.
        
        Args:
            name: 메트릭 이름
        
        Returns:
            카운터 값
        """
        return self._counters.get(name, 0)
    
    # ── 타이머 메트릭 ───────────────────────────────────────────────────
    
    @contextmanager
    def measure(self, name: str):
        """실행 시간을 측정하는 컨텍스트 매니저.
        
        Args:
            name: 메트릭 이름
        
        사용법:
            with collector.measure("image_analysis"):
                analyze_image(image_path)
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start_time
            self._timers[name].append(elapsed)
            log.debug("타이머 기록: %s = %.3f초", name, elapsed)
    
    def record_time(self, name: str, duration: float) -> None:
        """실행 시간을 기록합니다.
        
        Args:
            name: 메트릭 이름
            duration: 실행 시간 (초)
        """
        self._timers[name].append(duration)
        log.debug("타이머 기록: %s = %.3f초", name, duration)
    
    def get_timer_stats(self, name: str) -> Dict[str, float]:
        """타이머 메트릭 통계를 반환합니다.
        
        Args:
            name: 메트릭 이름
        
        Returns:
            {count, min, max, avg, p50, p95, p99} 통계
        """
        times = self._timers.get(name, [])
        
        if not times:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }
        
        sorted_times = sorted(times)
        n = len(sorted_times)
        
        return {
            "count": n,
            "min": sorted_times[0],
            "max": sorted_times[-1],
            "avg": sum(sorted_times) / n,
            "p50": sorted_times[int(n * 0.5)],
            "p95": sorted_times[int(n * 0.95)],
            "p99": sorted_times[int(n * 0.99)],
        }
    
    # ── 게이지 메트릭 ─────────────────────────────────────────────────
    
    def set_gauge(self, name: str, value: float) -> None:
        """게이지 메트릭을 설정합니다.
        
        Args:
            name: 메트릭 이름
            value: 게이지 값
        """
        self._gauges[name] = value
        log.debug("게이지 설정: %s = %.2f", name, value)
    
    def get_gauge(self, name: str) -> float:
        """게이지 메트릭을 반환합니다.
        
        Args:
            name: 메트릭 이름
        
        Returns:
            게이지 값
        """
        return self._gauges.get(name, 0.0)
    
    # ── 히스토그램 메트릭 ───────────────────────────────────────────────
    
    def record_histogram(self, name: str, value: float) -> None:
        """히스토그램 메트릭을 기록합니다.
        
        Args:
            name: 메트릭 이름
            value: 기록할 값
        """
        self._histograms[name].append(value)
        log.debug("히스토그램 기록: %s = %.2f", name, value)
    
    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """히스토그램 메트릭 통계를 반환합니다.
        
        Args:
            name: 메트릭 이름
        
        Returns:
            {count, min, max, avg, p50, p95, p99} 통계
        """
        values = self._histograms.get(name, [])
        
        if not values:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        return {
            "count": n,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "avg": sum(sorted_values) / n,
            "p50": sorted_values[int(n * 0.5)],
            "p95": sorted_values[int(n * 0.95)],
            "p99": sorted_values[int(n * 0.99)],
        }
    
    # ── 리포트 ─────────────────────────────────────────────────────────
    
    def get_report(self) -> Dict[str, Any]:
        """전체 메트릭 리포트를 반환합니다.
        
        Returns:
            {counters, timers, gauges, histograms} 메트릭 요약
        """
        return {
            "counters": dict(self._counters),
            "timers": {name: self.get_timer_stats(name) for name in self._timers},
            "gauges": dict(self._gauges),
            "histograms": {name: self.get_histogram_stats(name) for name in self._histograms},
        }
    
    def print_report(self) -> None:
        """메트릭 리포트를 출력합니다."""
        report = self.get_report()
        
        print("\n=== 메트릭 리포트 ===")
        
        # 카운터
        if report["counters"]:
            print("\n[카운터]")
            for name, value in report["counters"].items():
                print(f"  {name}: {value}")
        
        # 타이머
        if report["timers"]:
            print("\n[타이머]")
            for name, stats in report["timers"].items():
                print(f"  {name}:")
                print(f"    count: {stats['count']}")
                print(f"    avg: {stats['avg']:.3f}s")
                print(f"    p95: {stats['p95']:.3f}s")
                print(f"    p99: {stats['p99']:.3f}s")
        
        # 게이지
        if report["gauges"]:
            print("\n[게이지]")
            for name, value in report["gauges"].items():
                print(f"  {name}: {value:.2f}")
        
        # 히스토그램
        if report["histograms"]:
            print("\n[히스토그램]")
            for name, stats in report["histograms"].items():
                print(f"  {name}:")
                print(f"    count: {stats['count']}")
                print(f"    avg: {stats['avg']:.2f}")
                print(f"    p95: {stats['p95']:.2f}")
        
        print("\n==================\n")
    
    # ── 리셋 ───────────────────────────────────────────────────────────
    
    def reset(self) -> None:
        """모든 메트릭을 초기화합니다."""
        self._counters.clear()
        self._timers.clear()
        self._gauges.clear()
        self._histograms.clear()
        log.debug("메트릭 초기화 완료")
    
    # ── 유틸리티 ───────────────────────────────────────────────────────
    
    @staticmethod
    def get_instance() -> "MetricsCollector":
        """싱글톤 인스턴스를 반환합니다."""
        if MetricsCollector._instance is None:
            MetricsCollector._instance = MetricsCollector()
        return MetricsCollector._instance


# 편의 함수: 싱글톤 인스턴스 접근
get_metrics_collector = MetricsCollector.get_instance
