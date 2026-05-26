"""PipelineTelegramBridge 분리 모듈.

이 파일은 telegram_notifier.py에서 분리된 Mixin 클래스입니다.
직접 인스턴스화하지 마세요.
"""
from __future__ import annotations
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MonitorsMixin:
    """모니터링 루프 Mixin (피부 분석 플랫폼 전용).

    루프 목록:
        _heartbeat_monitor_loop  — 시스템 정상 작동 하트비트
        _stats_report_loop       — 일/주/월간 통계 자동 보고
        _session_monitor_loop    — 고객 접속 이력 감시
    """

    def _heartbeat_monitor_loop(self) -> None:
        """1시간마다 HEARTBEAT 메시지를 텔레그램으로 전송.

        시스템 상태를 확인하고 정상 작동 중임을 알리는 하트비트 메시지를 전송한다.
        """
        logger.info("[TG][HEARTBEAT] 하트비트 모니터 루프 시작 (간격: %.0f초)", self._heartbeat_interval_sec)

        while not self._stop_event.is_set():
            try:
                # 하트비트 메시지 전송
                try:
                    from datetime import datetime as dt

                    # 시스템 상태 수집
                    status_info = []

                    # 현재 시간
                    status_info.append(f"⏰ 시간: {dt.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    # 시스템 상태
                    status_info.append("✅ 시스템: 정상 작동 중")

                    # 메시지 조합
                    heartbeat_msg = "💓 <b>HEARTBEAT</b>\n\n" + "\n".join(status_info)

                    # 텔레그램 전송
                    self._notifier.send_text(heartbeat_msg, parse_mode="HTML")
                    logger.info("[TG][HEARTBEAT] 하트비트 메시지 전송 완료")

                except Exception as e:
                    logger.error("[TG][HEARTBEAT] 하트비트 메시지 전송 실패: %s", e)

            except Exception as exc:
                logger.warning("[TG][HEARTBEAT] 하트비트 루프 오류: %s", exc)

            # 대기
            self._stop_event.wait(timeout=self._heartbeat_interval_sec)

        logger.info("[TG][HEARTBEAT] 하트비트 모니터 루프 종료")

    def _stats_report_loop(self) -> None:
        """일/주/월간 통계 보고를 자정 기준으로 자동 전송하는 루프.

        전송 타이밍:
            일간: 매일 자정(00:00) — 전날 통계
            주간: 매주 월요일 00:00 — 전주 통계
            월간: 매월 1일 00:00 — 전월 통계

        bridge.stats_collector 가 None 이면 아무것도 하지 않는다.
        """
        logger.info("[TG][STATS] 통계 보고 루프 시작")

        _last_day:   str = datetime.now().strftime("%Y-%m-%d")
        _last_week:  str = datetime.now().strftime("%Y-W%W")
        _last_month: str = datetime.now().strftime("%Y-%m")

        while not self._stop_event.is_set():
            try:
                collector = getattr(self, "stats_collector", None)
                if collector is None:
                    self._stop_event.wait(timeout=60.0)
                    continue

                now       = datetime.now()
                day_key   = now.strftime("%Y-%m-%d")
                week_key  = now.strftime("%Y-W%W")
                month_key = now.strftime("%Y-%m")

                # ── 월간 보고 (월 교체 시 먼저) ───────────────────────
                if month_key != _last_month:
                    try:
                        from .formatters import format_monthly_stats  # noqa: PLC0415
                    except ImportError:
                        from formatters import format_monthly_stats    # noqa: PLC0415
                    try:
                        stats = collector.get_monthly_stats()
                        # 월간은 직전 달 기준 — 롤오버 전 스냅샷이 이미 담겨 있음
                        text = format_monthly_stats(stats)
                        ok = self._notifier._send_message(text, parse_mode="MarkdownV2")
                        if ok:
                            self._record_sent_stats()  # [Fix ④] 전송 건수 기록
                        logger.info(
                            "[TG][STATS] 월간 보고 전송 %s: %s",
                            _last_month, "OK" if ok else "FAIL",
                        )
                    except Exception as exc:
                        logger.error("[TG][STATS] 월간 보고 전송 오류: %s", exc)
                    _last_month = month_key
                    collector._reset_month()

                # ── 주간 보고 (주 교체 시) ────────────────────────────
                elif week_key != _last_week:
                    try:
                        from .formatters import format_weekly_stats  # noqa: PLC0415
                    except ImportError:
                        from formatters import format_weekly_stats    # noqa: PLC0415
                    try:
                        stats = collector.get_weekly_stats()
                        text  = format_weekly_stats(stats)
                        ok = self._notifier._send_message(text, parse_mode="MarkdownV2")
                        if ok:
                            self._record_sent_stats()  # [Fix ④] 전송 건수 기록
                        logger.info(
                            "[TG][STATS] 주간 보고 전송 %s: %s",
                            _last_week, "OK" if ok else "FAIL",
                        )
                    except Exception as exc:
                        logger.error("[TG][STATS] 주간 보고 전송 오류: %s", exc)
                    _last_week = week_key
                    collector._reset_week()

                # ── 일간 보고 (날 교체 시) ────────────────────────────
                if day_key != _last_day:
                    try:
                        from .formatters import format_daily_stats  # noqa: PLC0415
                    except ImportError:
                        from formatters import format_daily_stats    # noqa: PLC0415
                    try:
                        stats = collector.get_daily_stats()
                        text  = format_daily_stats(stats)
                        ok = self._notifier._send_message(text, parse_mode="MarkdownV2")
                        if ok:
                            self._record_sent_stats()  # [Fix ④] 전송 건수 기록
                        logger.info(
                            "[TG][STATS] 일간 보고 전송 %s: %s",
                            _last_day, "OK" if ok else "FAIL",
                        )
                    except Exception as exc:
                        logger.error("[TG][STATS] 일간 보고 전송 오류: %s", exc)
                    _last_day = day_key
                    collector._reset_day()

            except Exception as exc:
                logger.error("[TG][STATS] 통계 보고 루프 오류: %s", exc)

            # 60초마다 날짜 변경 감지 (자정 이후 최대 60초 지연)
            self._stop_event.wait(timeout=60.0)

        logger.info("[TG][STATS] 통계 보고 루프 종료")

    def _record_sent_stats(self) -> None:
        """텔레그램 전송 1건을 stats_collector에 기록하는 헬퍼."""
        try:
            collector = getattr(self, "stats_collector", None)
            if collector is not None:
                collector.record_sent()
        except Exception as exc:
            logger.debug("[STATS] record_sent 오류: %s", exc)

    def _session_monitor_loop(self) -> None:
        """고객 접속 이력을 주기적으로 감시하여 텔레그램 알림 전송.

        동작 방식:
          1. pipeline._session_provider (SessionProvider 프로토콜) 가 있으면
             get_recent_events() → 새 이벤트를 diff하여 단건 알림 전송.
          2. _session_summary_interval_sec 마다 접속 이력 요약 전송.

        ※ 서버 장애는 FaultReporter.report() 직접 호출 방식으로 분리되었습니다.
          pipeline.fault_reporter.report(fault_type=..., component=..., exc=exc)

        SessionProvider 프로토콜 (duck-typing):
            def get_recent_events(self) -> list[dict]: ...
            # 각 dict 는 notifier.send_session_event 의 event dict 형식
        """
        logger.info("[TG][SESSION] 세션 모니터 루프 시작 (간격: %.0f초)", self._session_monitor_interval_sec)

        _seen_session_ids: set[str] = set()   # 이미 알림 보낸 세션 이벤트 deduplicate
        _session_buffer: list[dict] = []      # 요약용 버퍼
        _last_summary_ts: float = time.time()

        while not self._stop_event.is_set():
            try:
                # ── 1. 고객 접속 이벤트 처리 ──────────────────────────
                session_provider = getattr(self._pipeline, "_session_provider", None)
                if session_provider is not None:
                    try:
                        events: list[dict] = list(session_provider.get_recent_events() or [])
                    except Exception as exc:
                        logger.warning("[TG][SESSION] get_recent_events 오류: %s", exc)
                        events = []

                    for ev in events:
                        # 이벤트 고유 키: session_id > (client_id+type+ts문자열) 순으로 생성
                        sid = str(ev.get("session_id") or "")
                        ts_ev = ev.get("ts")
                        ts_key = ts_ev.isoformat() if hasattr(ts_ev, "isoformat") else str(ts_ev or "")
                        ev_key = sid or f"{ev.get('client_id','')}:{ev.get('type','')}:{ts_key}"

                        if ev_key in _seen_session_ids:
                            continue
                        _seen_session_ids.add(ev_key)
                        _session_buffer.append(ev)

                        # 단건 알림 전송
                        try:
                            ok = self._notifier.send_session_event(ev)
                            if ok:
                                self._record_sent_stats()  # [Fix ④] 전송 건수 기록
                            logger.debug(
                                "[TG][SESSION] 이벤트 전송: type=%s client=%s",
                                ev.get("type"), ev.get("client_id"),
                            )
                        except Exception as exc:
                            logger.warning("[TG][SESSION] 단건 알림 전송 실패: %s", exc)

                    # deduplicate 버퍼 크기 제한 (메모리 보호)
                    if len(_seen_session_ids) > 10_000:
                        _seen_session_ids = set(list(_seen_session_ids)[-5_000:])

                # ── 2. 요약 전송 (주기 도달 시) ───────────────────────
                now = time.time()
                if (now - _last_summary_ts) >= self._session_summary_interval_sec:
                    if _session_buffer:
                        try:
                            period_label = f"최근 {int(self._session_summary_interval_sec // 60)}분"
                            self._notifier.send_session_summary(_session_buffer, period_label)
                            logger.info(
                                "[TG][SESSION] 요약 전송: %d건", len(_session_buffer)
                            )
                        except Exception as exc:
                            logger.warning("[TG][SESSION] 요약 전송 실패: %s", exc)
                    _session_buffer = []
                    _last_summary_ts = now

                # ── 3. 서버 장애 ──────────────────────────────────────────
                # [REFACTOR] 폴링 방식 제거 → FaultReporter.report() 직접 호출로 변경.
                # 예외 핸들러에서: pipeline.fault_reporter.report(fault_type=..., exc=exc)

            except Exception as exc:
                logger.error("[TG][SESSION] 세션 모니터 루프 오류: %s", exc)

            self._stop_event.wait(timeout=self._session_monitor_interval_sec)

        logger.info("[TG][SESSION] 세션 모니터 루프 종료")
