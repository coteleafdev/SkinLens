"""장애 직접 호출 헬퍼

서버 장애를 텔레그램으로 즉시 전송하는 경량 헬퍼.
폴링 방식 없이 예외 핸들러에서 직접 호출합니다.
중복 전송 방지(deduplicate), 쿨다운, critical 재시도를 내장합니다.

사용 예::

    # bridge 또는 pipeline 초기화 시 한 번만 생성
    fault_reporter = FaultReporter(notifier)
    pipeline.fault_reporter = fault_reporter   # 필요한 곳에 주입

    # 예외 핸들러에서 직접 호출
    try:
        ...
    except Exception as exc:
        pipeline.fault_reporter.report(
            fault_type="db_error",
            component="MarketDataStore",
            exc=exc,
            severity="error",
        )

report() 인자::

    fault_type : str   — 'crash'|'oom'|'db_error'|'network'|
                         'timeout'|'api_error'|'data_missing'|'unknown'
    component  : str   — 장애 발생 컴포넌트명
    exc        : Exception | None  — 원본 예외 (None 가능)
    message    : str   — 추가 설명 (exc 있으면 자동 추출)
    severity   : str   — 'critical'|'error'|'warning'  (기본 'error')
    resolved   : bool  — 복구 여부 (기본 False)
    resolve_sec: float — 복구 소요 시간 초 (resolved=True 시)
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class FaultReporter:
    """서버 장애를 텔레그램으로 즉시 전송하는 경량 헬퍼.

    폴링 방식 없이 예외 핸들러에서 직접 호출합니다.
    중복 전송 방지(deduplicate), 쿨다운, critical 재시도를 내장합니다.

    사용 예::

        # bridge 또는 pipeline 초기화 시 한 번만 생성
        fault_reporter = FaultReporter(notifier)
        pipeline.fault_reporter = fault_reporter   # 필요한 곳에 주입

        # 예외 핸들러에서 직접 호출
        try:
            ...
        except Exception as exc:
            pipeline.fault_reporter.report(
                fault_type="db_error",
                component="MarketDataStore",
                exc=exc,
                severity="error",
            )

    report() 인자::

        fault_type : str   — 'crash'|'oom'|'db_error'|'network'|
                             'timeout'|'api_error'|'data_missing'|'unknown'
        component  : str   — 장애 발생 컴포넌트명
        exc        : Exception | None  — 원본 예외 (None 가능)
        message    : str   — 추가 설명 (exc 있으면 자동 추출)
        severity   : str   — 'critical'|'error'|'warning'  (기본 'error')
        resolved   : bool  — 복구 여부 (기본 False)
        resolve_sec: float — 복구 소요 시간 초 (resolved=True 시)
    """

    # critical 장애는 최대 이 횟수까지 재시도
    CRITICAL_MAX_RETRY: int = 3
    CRITICAL_RETRY_DELAY: float = 2.0  # 초

    def __init__(
        self,
        notifier: "TelegramNotifier",
        *,
        cooldown_sec: float = 60.0,
        max_seen: int = 5_000,
    ) -> None:
        """
        Args:
            notifier:     TelegramNotifier 인스턴스.
            cooldown_sec: 동일 컴포넌트+타입 조합의 재알림 최소 간격(초).
                          0 이면 쿨다운 없음.
            max_seen:     deduplicate 캐시 최대 항목 수 (메모리 보호).
        """
        self._notifier = notifier
        self._cooldown_sec = float(cooldown_sec)
        self._max_seen = int(max_seen)
        # key: "component:fault_type" → 마지막 전송 epoch
        self._last_sent: Dict[str, float] = {}
        self._lock = threading.Lock()

    def report(
        self,
        fault_type: str,
        component: str,
        *,
        exc: Optional[Exception] = None,
        message: str = "",
        severity: str = "error",
        resolved: bool = False,
        resolve_sec: Optional[float] = None,
        traceback_str: str = "",
    ) -> bool:
        """장애를 즉시 텔레그램으로 전송.

        동일 component+fault_type 조합은 cooldown_sec 이내 재전송 억제.
        severity='critical' 이면 전송 실패 시 CRITICAL_MAX_RETRY 회 재시도.

        Returns:
            전송 성공 여부.
        """
        import traceback as _tb  # noqa: PLC0415

        # ── 메시지 조립 ───────────────────────────────────────
        msg = message
        if not msg and exc is not None:
            msg = str(exc)
        tb_str = traceback_str
        if not tb_str and exc is not None:
            tb_str = _tb.format_exc(limit=8)

        fault: Dict[str, Any] = {
            "type":        fault_type,
            "component":   component,
            "message":     msg[:400],
            "traceback":   tb_str[:600],
            "severity":    severity,
            "resolved":    resolved,
            "resolve_sec": resolve_sec,
            "ts":          datetime.now(),
        }

        # ── 쿨다운 체크 ──────────────────────────────────────
        ck = f"{component}:{fault_type}"
        now = time.time()
        with self._lock:
            last = self._last_sent.get(ck, 0.0)
            if self._cooldown_sec > 0 and (now - last) < self._cooldown_sec:
                log.debug(
                    "[TG][FAULT] 쿨다운 중 — 전송 억제 component=%s type=%s"
                    " (%.0f초 남음)",
                    component, fault_type,
                    self._cooldown_sec - (now - last),
                )
                return False
            # 캐시 크기 제한
            if len(self._last_sent) >= self._max_seen:
                oldest = min(self._last_sent, key=self._last_sent.get)  # type: ignore[arg-type]
                del self._last_sent[oldest]
            self._last_sent[ck] = now

        # ── 전송 (critical 은 재시도) ─────────────────────────
        max_try = self.CRITICAL_MAX_RETRY if severity == "critical" else 1
        ok = False
        for attempt in range(1, max_try + 1):
            try:
                ok = self._notifier.send_system_fault(fault)
            except Exception as send_exc:
                log.warning(
                    "[TG][FAULT] 전송 예외 (attempt %d/%d): %s",
                    attempt, max_try, send_exc,
                )
                ok = False
            if ok:
                break
            if attempt < max_try:
                time.sleep(self.CRITICAL_RETRY_DELAY)

        if ok:
            log.info(
                "[TG][FAULT] 전송 완료: component=%s type=%s severity=%s",
                component, fault_type, severity,
            )
        else:
            log.error(
                "[TG][FAULT] 전송 실패: component=%s type=%s",
                component, fault_type,
            )
        return ok

    def resolve(
        self,
        fault_type: str,
        component: str,
        *,
        resolve_sec: Optional[float] = None,
        message: str = "",
    ) -> bool:
        """장애 복구 알림을 즉시 전송.

        쿨다운을 무시하고 강제 전송합니다 (복구는 항상 알려야 하므로).

        Args:
            fault_type:  원래 장애 타입.
            component:   원래 컴포넌트명.
            resolve_sec: 복구 소요 시간 초.
            message:     복구 상세 메시지.

        Returns:
            전송 성공 여부.
        """
        fault: Dict[str, Any] = {
            "type":        fault_type,
            "component":   component,
            "message":     message[:400] if message else "장애가 복구되었습니다.",
            "severity":    "warning",
            "resolved":    True,
            "resolve_sec": resolve_sec,
            "ts":          datetime.now(),
        }
        # 쿨다운 캐시 초기화 (이후 동일 장애 발생 시 즉시 전송)
        ck = f"{component}:{fault_type}"
        with self._lock:
            self._last_sent.pop(ck, None)

        try:
            ok = self._notifier.send_system_fault(fault)
        except Exception as exc:
            log.warning("[TG][FAULT] 복구 알림 전송 실패: %s", exc)
            ok = False

        if ok:
            log.info(
                "[TG][FAULT] 복구 알림 전송: component=%s type=%s",
                component, fault_type,
            )
        return ok
