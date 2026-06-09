"""SkinAnalysisBridge — 피부 분석 플랫폼 텔레그램 브리지.

매매/예측 관련 기능 없이 피부 분석 플랫폼 전용으로 재작성.

역할:
    - 분석 결과 전송 (send_analysis_result)
    - 고객 접속 이력 모니터링 (_session_monitor_loop)
    - 서버 장애 즉시 알림 (FaultReporter)
    - 일/주/월간 통계 자동 보고 (_stats_report_loop)
    - 텔레그램 명령 수신 (CommandsMixin)
"""
from __future__ import annotations
import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

from .commands import CommandsMixin
from .monitors import MonitorsMixin
from .notifier import (
    TelegramNotifier,
    FaultReporter,
    StatisticsCollector,
)


class SkinAnalysisBridge(CommandsMixin, MonitorsMixin):
    """피부 분석 플랫폼 텔레그램 브리지.

    Public API:
        start()               — 브리지 시작 (모니터링 스레드 기동)
        stop()                — 브리지 종료
        start_polling()       — 텔레그램 명령 폴링 시작
        send_analysis_result() — 분석 결과 즉시 전송
    """

    def __init__(
        self,
        notifier: TelegramNotifier,
        *,
        session_poll_sec: float = 10.0,
        session_summary_sec: float = 3600.0,
    ) -> None:
        """
        Args:
            notifier:            TelegramNotifier 인스턴스.
            session_poll_sec:    고객 접속 이력 폴링 주기 (초). 기본 10초.
            session_summary_sec: 접속 이력 요약 전송 주기 (초). 기본 1시간.
        """
        self._notifier = notifier

        self._stop_event = threading.Event()
        self._user_pause_event = threading.Event()  # set = 일시정지

        # ── 세션 모니터 설정 ───────────────────────────────────────
        self._session_monitor_interval_sec: float = float(session_poll_sec)
        self._session_summary_interval_sec: float = float(session_summary_sec)
        self._session_monitor_thread: Optional[threading.Thread] = None

        # ── FaultReporter: 장애 즉시 알림 ─────────────────────────
        self.fault_reporter = FaultReporter(
            self._notifier,
            cooldown_sec=60.0,
        )

        # ── StatisticsCollector: 일/주/월간 통계 ──────────────────
        self.stats_collector = StatisticsCollector()
        self._stats_report_thread: Optional[threading.Thread] = None

        # ── 에러 윈도우 (장애 임계치 알림) ────────────────────────
        self._error_window_sec: float    = 600.0
        self._error_threshold: int       = 3
        self._error_events: deque        = deque(maxlen=100)
        self._last_error_alert_epoch: float = 0.0
        self._error_alert_cooldown_sec: float = 600.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_analysis_result(
        self,
        result: Dict[str, Any],
        *,
        image_path: str = "",
    ) -> bool:
        """피부 분석 결과를 텔레그램으로 전송하고 통계에 기록.

        Args:
            result:     SkinAnalyzer.analyze_all() 반환값.
            image_path: 분석 이미지 경로 (메시지에 포함, 선택).
        Returns:
            전송 성공 여부.
        """
        # 통계 기록
        try:
            self.stats_collector.record_analysis_result(result)
        except Exception as exc:
            log.debug("[BRIDGE] stats record 오류: %s", exc)

        if "error" in result:
            err_msg = str(result.get("error", "unknown"))
            log.warning("[BRIDGE] 분석 오류 결과: %s", err_msg)
            return self._notifier.send_text(
                f"⚠️ <b>피부 분석 오류</b>\n<code>{err_msg}</code>"
            )

        overall  = result.get("overall_score", 0.0)
        age      = result.get("perceived_age", 0.0)
        meas     = result.get("measurements_report") or result.get("measurements") or {}
        now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"🔬 <b>피부 분석 완료</b>  |  {now_str}",
            f"📊 종합 점수: <b>{overall:.1f}점</b>  |  인지 나이: <b>{age:.1f}세</b>",
        ]
        if image_path:
            lines.append(f"📁 이미지: <code>{image_path}</code>")

        # 측정 항목 상위 5개 출력
        if meas:
            lines.append("")
            lines.append("📋 주요 항목:")
            sorted_items = sorted(
                [(k, v) for k, v in meas.items() if isinstance(v, (int, float))],
                key=lambda x: float(x[1]),
            )
            for k, v in sorted_items[:5]:
                bar = "▓" * min(int(float(v) / 10), 9) + "░" * (9 - min(int(float(v) / 10), 9))
                lines.append(f"  • {k}: {float(v):.1f}  {bar}")

        text = "\n".join(lines)
        ok = self._notifier.send_text(text)
        if ok:
            try:
                self.stats_collector.record_sent()
            except Exception as e:
                log.debug("stats record_sent 실패: %s", e)
        return ok

    def send_text(self, text: str, **kwargs: Any) -> bool:
        """임의 텍스트 전송 (내부·외부 공용)."""
        return self._notifier.send_text(text, **kwargs)

    def start(self) -> None:
        """브리지를 시작합니다 (모니터링 스레드 기동)."""
        self._stop_event.clear()

        # 세션 모니터 (접속 이력 감시)
        try:
            self._session_monitor_thread = threading.Thread(
                target=self._session_monitor_loop,
                daemon=True,
                name="SessionMonitor",
            )
            self._session_monitor_thread.start()
            log.info(
                "[BRIDGE] 세션/장애 모니터 시작 (폴링: %.0f초, 요약: %.0f초)",
                self._session_monitor_interval_sec,
                self._session_summary_interval_sec,
            )
        except Exception as exc:
            log.warning("[BRIDGE] 세션 모니터 시작 실패: %s", exc)

        # 통계 보고 루프
        try:
            self._stats_report_thread = threading.Thread(
                target=self._stats_report_loop,
                daemon=True,
                name="StatsReport",
            )
            self._stats_report_thread.start()
            log.info("[BRIDGE] 통계 보고 루프 시작 (일/주/월간 자정 자동 전송)")
        except Exception as exc:
            log.warning("[BRIDGE] 통계 보고 루프 시작 실패: %s", exc)

        # 시작 알림
        try:
            self._notifier.send_text("🚀 <b>CÔTELEAF 피부 분석 시스템 시작</b>")
        except Exception as e:
            log.debug("시작 알림 전송 실패: %s", e)

        log.info("[BRIDGE] SkinAnalysisBridge 시작 완료")

    def stop(self) -> None:
        """브리지를 종료합니다."""
        if self._stop_event.is_set():
            return
        self._stop_event.set()

        # 종료 시점 일간 보고 전송
        try:
            from .formatters import format_daily_stats  # noqa: PLC0415
            stats = self.stats_collector.get_daily_stats()
            stats["period_label"] = "종료 시점"
            text = format_daily_stats(stats)
            self._notifier._send_message(text, parse_mode="MarkdownV2")
            log.info("[BRIDGE] 종료 시점 일간 보고 전송 완료")
        except Exception as exc:
            log.warning("[BRIDGE] 종료 시점 보고 전송 실패: %s", exc)

        # 종료 알림
        try:
            self._notifier.send_text("🛑 <b>CÔTELEAF 피부 분석 시스템 종료</b>")
        except Exception as e:
            log.debug("종료 알림 전송 실패: %s", e)

        try:
            self._notifier.stop_polling()
        except Exception as e:
            log.debug("polling 중지 실패: %s", e)

        # 스레드 정리
        for thread_attr in (
            "_session_monitor_thread",
            "_stats_report_thread",
        ):
            try:
                t = getattr(self, thread_attr, None)
                if t and t.is_alive():
                    t.join(timeout=3.0)
            except Exception as e:
                log.debug("스레드 정리 실패: %s", e)

        log.info("[BRIDGE] SkinAnalysisBridge 종료 완료")

    def start_polling(self) -> None:
        """텔레그램 명령 폴링을 시작합니다."""
        self._notifier.start_polling(
            on_command=self._handle_command,
        )


# ──────────────────────────────────────────────
# 팩토리 함수
# ──────────────────────────────────────────────

def load_telegram_config(config_path: str = "") -> Dict[str, Any]:
    """config.secrets.json에서 텔레그램 설정을 로드합니다."""
    import json, os
    from pathlib import Path

    paths = []
    if config_path:
        paths.append(Path(config_path))
    env_path = os.environ.get("APP_SECRETS_CONFIG", "")
    if env_path:
        paths.append(Path(env_path))
    paths += [
        Path("config/config.secrets.json"),
        Path("config.secrets.json"),
    ]
    for p in paths:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                tg = data.get("telegram", {})
                if tg:
                    return tg
            except Exception as e:
                log.debug("telegram config 로드 실패: %s", e)
    return {}


def create_notifier_from_config(config_path: str = "") -> TelegramNotifier:
    """설정 파일에서 TelegramNotifier 인스턴스를 생성합니다."""
    cfg = load_telegram_config(config_path)
    return TelegramNotifier(
        bot_token=cfg.get("bot_token") or "",
        chat_id=cfg.get("chat_id") or "",
    )


def create_bridge_from_config(
    config_path: str = "",
    **kwargs: Any,
) -> SkinAnalysisBridge:
    """설정 파일에서 SkinAnalysisBridge 인스턴스를 생성합니다."""
    notifier = create_notifier_from_config(config_path)
    return SkinAnalysisBridge(notifier, **kwargs)
