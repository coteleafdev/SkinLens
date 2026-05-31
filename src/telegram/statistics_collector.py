"""일/주/월간 통계 수집기

피부 분석 결과·세션·장애를 실시간 수집하고 일/주/월간 통계를 집계하는 클래스.
TelegramNotifier, FaultReporter 와 연동하여 bridge가 자동으로 주입한다.
모든 메서드는 thread-safe (내부 Lock 사용).

수집 항목:
    - 피부 분석 결과 (종합 점수, 인지 나이)
    - 고객 접속 이벤트 건수
    - 장애 건수 및 타입별 분류
    - 텔레그램 전송 건수

사용 예::

    collector = StatisticsCollector()
    bridge.stats_collector = collector

    # 분석 결과 기록
    collector.record_analysis_result(result)

    # 일간 통계 dict 조회
    daily = collector.get_daily_stats()

    # 누적 전송 건수 갱신
    collector.record_sent()

    # 세션 이벤트 기록
    collector.record_session_event(event)

    # 장애 기록
    collector.record_fault(fault_type, component, severity)
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Dict

log = logging.getLogger(__name__)


class StatisticsCollector:
    """피부 분석 결과·세션·장애를 실시간 수집하고 일/주/월간 통계를 집계하는 클래스.

    TelegramNotifier, FaultReporter 와 연동하여 bridge가 자동으로 주입한다.
    모든 메서드는 thread-safe (내부 Lock 사용).

    수집 항목:
        - 피부 분석 결과 (종합 점수, 인지 나이)
        - 고객 접속 이벤트 건수
        - 장애 건수 및 타입별 분류
        - 텔레그램 전송 건수

    사용 예::

        collector = StatisticsCollector()
        bridge.stats_collector = collector

        # 분석 결과 기록
        collector.record_analysis_result(result)

        # 일간 통계 dict 조회
        daily = collector.get_daily_stats()

        # 누적 전송 건수 갱신
        collector.record_sent()

        # 세션 이벤트 기록
        collector.record_session_event(event)

        # 장애 기록
        collector.record_fault(fault_type, component, severity)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset_all()

    # ------------------------------------------------------------------
    # 내부 초기화
    # ------------------------------------------------------------------

    def _reset_all(self) -> None:
        """전체 누적 카운터 초기화. 월 교체 시 호출."""
        now = datetime.now()
        self._month_key: str = now.strftime("%Y-%m")
        self._reset_month()

    def _reset_month(self) -> None:
        """월간 카운터 초기화. 일간·주간도 함께 초기화."""
        self._mo_total: int            = 0
        self._mo_errors: int           = 0
        self._mo_sessions: int         = 0
        self._mo_faults: int           = 0
        self._mo_fault_types: Dict[str, int] = {}
        self._mo_score_sum: float      = 0.0
        self._mo_score_max: float      = 0.0
        self._mo_sent: int             = 0
        self._mo_active_days: set      = set()
        # 주차별 분석 건수 (0~4: 0=1주차 ... 4=5주차)
        self._mo_weekly: list          = [0, 0, 0, 0, 0]
        self._reset_week()

    def _reset_week(self) -> None:
        """주간 카운터 초기화."""
        self._wk_total: int            = 0
        self._wk_errors: int           = 0
        self._wk_sessions: int         = 0
        self._wk_faults: int           = 0
        self._wk_fault_types: Dict[str, int] = {}
        self._wk_score_sum: float      = 0.0
        self._wk_score_max: float      = 0.0
        self._wk_sent: int             = 0
        self._wk_active_days: set      = set()
        self._wk_start_date: str       = datetime.now().strftime("%Y-%m-%d")
        self._wk_peak_day: str         = ""
        self._wk_peak_day_count: int   = 0
        self._wk_day_counts: Dict[str, int] = {}
        self._reset_day()

    def _reset_day(self) -> None:
        """일간 카운터 초기화."""
        self._day_total: int           = 0
        self._day_errors: int          = 0
        self._day_sessions: int        = 0
        self._day_faults: int          = 0
        self._day_fault_types: Dict[str, int] = {}
        self._day_score_sum: float     = 0.0
        self._day_score_max: float     = 0.0
        self._day_score_min: float     = 0.0
        self._day_age_sum: float       = 0.0
        self._day_age_count: int       = 0
        self._day_active_days: set     = set()
        self._day_sent: int            = 0
        self._day_key: str             = datetime.now().strftime("%Y-%m-%d")
        self._week_key: str            = datetime.now().strftime("%Y-W%W")

    # ------------------------------------------------------------------
    # 수집 메서드 (thread-safe)
    # ------------------------------------------------------------------

    def _check_rollover(self, now: datetime) -> None:
        """날짜·주·월 교체 여부를 확인하고 필요 시 카운터를 롤오버한다."""
        day_key   = now.strftime("%Y-%m-%d")
        week_key  = now.strftime("%Y-W%W")
        month_key = now.strftime("%Y-%m")

        if month_key != self._month_key:
            # 월 교체
            self._month_key = month_key
            self._reset_month()
            log.info("[STATS] 월간 카운터 초기화: %s", month_key)
        elif week_key != self._week_key:
            # 주 교체
            self._week_key = week_key
            self._reset_week()
            log.info("[STATS] 주간 카운터 초기화: %s", week_key)
        elif day_key != self._day_key:
            # 일 교체
            self._day_key = day_key
            self._reset_day()
            log.info("[STATS] 일간 카운터 초기화: %s", day_key)

    def record_analysis_result(self, result: Dict[str, Any]) -> None:
        """피부 분석 결과 dict 를 수집한다.

        분석 완료 시마다 호출. 오류 결과("error" 키 포함)도 오류 카운터로 기록.

        Args:
            result: SkinAnalyzer.analyze_all() 반환값 또는 오류 dict.
                    {
                        "overall_score":    float,   # 종합 점수 (10~90)
                        "perceived_age":    float,   # 인지 나이
                        "measurements_report": dict,    # 측정항목 점수
                        "error":            str,     # 오류 시에만
                    }
        """
        with self._lock:
            now = datetime.now()
            self._check_rollover(now)
            day_str  = now.strftime("%Y-%m-%d")
            week_idx = (now.day - 1) // 7

            if "error" in result:
                self._day_errors += 1
                self._wk_errors  += 1
                self._mo_errors  += 1
                return

            score = float(result.get("overall_score") or 0.0)
            age   = float(result.get("perceived_age") or 0.0)

            # 일간
            self._day_total     += 1
            self._day_score_sum += score
            self._day_score_max  = max(self._day_score_max, score)
            self._day_score_min  = min(self._day_score_min, score) if self._day_total > 1 else score
            if age > 0:
                self._day_age_sum   += age
                self._day_age_count += 1
            self._day_active_days.add(day_str)

            # 주간
            self._wk_total      += 1
            self._wk_score_sum  += score
            self._wk_score_max   = max(self._wk_score_max, score)
            self._wk_active_days.add(day_str)
            self._wk_day_counts[day_str] = self._wk_day_counts.get(day_str, 0) + 1
            if self._wk_day_counts.get(day_str, 0) > self._wk_peak_day_count:
                self._wk_peak_day       = day_str
                self._wk_peak_day_count = self._wk_day_counts[day_str]

            # 월간
            self._mo_total      += 1
            self._mo_score_sum  += score
            self._mo_score_max   = max(self._mo_score_max, score)
            self._mo_active_days.add(day_str)
            if 0 <= week_idx < 5:
                self._mo_weekly[week_idx] += 1


    def record_sent(self) -> None:
        """텔레그램 전송 1건 기록."""
        with self._lock:
            self._day_sent += 1
            self._wk_sent  += 1
            self._mo_sent  += 1

    def record_session_event(self, event: Dict[str, Any]) -> None:
        """고객 접속 이벤트 1건 기록."""
        with self._lock:
            now = datetime.now()
            self._check_rollover(now)
            self._day_sessions += 1
            self._wk_sessions  += 1
            self._mo_sessions  += 1

    def record_fault(
        self,
        fault_type: str,
        component: str = "",
        severity: str = "error",
    ) -> None:
        """장애 1건 기록."""
        with self._lock:
            now = datetime.now()
            self._check_rollover(now)
            ft = str(fault_type or "unknown")
            self._day_faults += 1
            self._day_fault_types[ft] = self._day_fault_types.get(ft, 0) + 1
            self._wk_faults  += 1
            self._wk_fault_types[ft]  = self._wk_fault_types.get(ft, 0) + 1
            self._mo_faults  += 1
            self._mo_fault_types[ft] = self._mo_fault_types.get(ft, 0) + 1

    # ------------------------------------------------------------------
    # 통계 조회 메서드
    # ------------------------------------------------------------------

    def get_daily_stats(self) -> Dict[str, Any]:
        """일간 통계 dict 반환 (formatters.format_daily_stats 입력 형식)."""
        with self._lock:
            avg_score = (
                self._day_score_sum / self._day_total
                if self._day_total > 0 else 0.0
            )
            avg_age = (
                self._day_age_sum / self._day_age_count
                if self._day_age_count > 0 else 0.0
            )
            return {
                "date":        self._day_key,
                "total":       self._day_total,
                "errors":      self._day_errors,
                "sessions":    self._day_sessions,
                "faults":      self._day_faults,
                "fault_types": dict(self._day_fault_types),
                "avg_score":   avg_score,
                "max_score":   self._day_score_max,
                "min_score":   self._day_score_min,
                "avg_age":     avg_age,
                "sent_count":  self._day_sent,
                "period_label": "오늘",
            }

    def get_weekly_stats(self) -> Dict[str, Any]:
        """주간 통계 dict 반환 (formatters.format_weekly_stats 입력 형식)."""
        with self._lock:
            now = datetime.now()
            avg_score = (
                self._wk_score_sum / self._wk_total
                if self._wk_total > 0 else 0.0
            )
            daily_avg = (
                self._wk_total / len(self._wk_active_days)
                if self._wk_active_days else 0.0
            )
            year, wnum = now.strftime("%Y"), now.strftime("%W")
            return {
                "week_label":      f"{year}-W{wnum}",
                "start_date":      self._wk_start_date,
                "end_date":        now.strftime("%Y-%m-%d"),
                "total":           self._wk_total,
                "errors":          self._wk_errors,
                "sessions":        self._wk_sessions,
                "faults":          self._wk_faults,
                "fault_types":     dict(self._wk_fault_types),
                "avg_score":       avg_score,
                "max_score":       self._wk_score_max,
                "active_days":     len(self._wk_active_days),
                "daily_avg_total": daily_avg,
                "peak_day":        self._wk_peak_day,
                "peak_day_count":  self._wk_peak_day_count,
                "sent_count":      self._wk_sent,
            }

    def get_monthly_stats(self) -> Dict[str, Any]:
        """월간 통계 dict 반환 (formatters.format_monthly_stats 입력 형식)."""
        with self._lock:
            now = datetime.now()
            import calendar as _cal
            total_days = _cal.monthrange(now.year, now.month)[1]
            avg_score = (
                self._mo_score_sum / self._mo_total
                if self._mo_total > 0 else 0.0
            )
            daily_avg = (
                self._mo_total / len(self._mo_active_days)
                if self._mo_active_days else 0.0
            )
            uptime = len(self._mo_active_days) / total_days if total_days > 0 else 0.0

            weekly_totals = list(self._mo_weekly)
            peak_wk, peak_wk_c = 0, 0
            for i, c in enumerate(weekly_totals, 1):
                if c > peak_wk_c:
                    peak_wk, peak_wk_c = i, c

            try:
                month_label = now.strftime("%Y년 %m월").replace(" 0", " ")
            except Exception as exc:
                log.debug("get_monthly_stats: month_label 생성 실패: %s", exc)
                month_label = now.strftime("%Y-%m")

            return {
                "month_label":     month_label,
                "year_month":      self._month_key,
                "total":           self._mo_total,
                "errors":          self._mo_errors,
                "sessions":        self._mo_sessions,
                "faults":          self._mo_faults,
                "fault_types":     dict(self._mo_fault_types),
                "avg_score":       avg_score,
                "max_score":       self._mo_score_max,
                "active_days":     len(self._mo_active_days),
                "daily_avg_total": daily_avg,
                "weekly_totals":   weekly_totals,
                "peak_week":       peak_wk,
                "peak_week_count": peak_wk_c,
                "sent_count":      self._mo_sent,
                "uptime_pct":      uptime,
            }
