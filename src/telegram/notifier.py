"""텔레그램 알림 모듈 (CÔTELEAF 피부 분석 플랫폼 전용)

사용법:
    from telegram import SkinAnalysisBridge, create_bridge_from_config

    bridge = create_bridge_from_config("config/config.secrets.json")
    bridge.start()           # 모니터링 스레드 기동
    bridge.start_polling()   # 텔레그램 명령 수신

설정:
    - config.secrets.json: { "telegram": { "bot_token": "...", "chat_id": "..." } }
    - 환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

의존성:
    표준 라이브러리(urllib)만 사용 — 추가 설치 불필요
"""

from __future__ import annotations

import json
import logging
import os
import re
import html
from collections import deque
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import urllib.parse
import urllib.request
import urllib.error

log = logging.getLogger(__name__)
try:
    # Inherit effective level from root so INFO logs (e.g., [TG][SEND]) are not suppressed.
    log.setLevel(logging.NOTSET)
except Exception as exc:
    log.debug("log.setLevel 실패: %s", exc)

try:
    _TG_DEBUG = str(os.environ.get("TELEGRAM_DEBUG") or "").strip().lower() not in ("", "0", "false", "no")
except Exception as exc:
    log.debug("TELEGRAM_DEBUG 환경변수 읽기 실패: %s", exc)
    _TG_DEBUG = False

# ── 포매터는 telegram_formatters.py에서 분리 관리 ────────────────────────────
# SRP 원칙: 순수 함수(포매터)와 I/O 클래스(Notifier/Bridge)를 분리한다.
# 하위 호환을 위해 이 모듈에서 re-export한다.
from src.telegram.telegram_formatters import (
    format_analysis_result,
    format_system_fault,
    format_daily_stats,
    format_weekly_stats,
    format_monthly_stats,
)

# ── 통계 수집기/장애 리포터 분리 ───────────────────────────────────────────────
# SRP 원칙: 통계 수집과 장애 리포팅을 별도 모듈로 분리한다.
# 하위 호환을 위해 이 모듈에서 re-export한다.
from src.telegram.statistics_collector import StatisticsCollector
from src.telegram.fault_reporter import FaultReporter
from .formatters import (  # noqa: E402
    _esc_mdv2,
    _TG_MAX_LEN,
    _TG_TRUNCATE_SUFFIX,
)

__all__ = [
    "TelegramNotifier",
    "StatisticsCollector",
    "FaultReporter",
    "create_notifier_from_config",
]


class TelegramNotifier:
    """텔레그램 봇을 통해 알림을 전송하고, 명령을 수신하는 클래스.

    Args:
        bot_token: 텔레그램 봇 토큰. None이면 환경변수 TELEGRAM_BOT_TOKEN 사용.
        chat_id: 전송 대상 채팅 ID. None이면 환경변수 TELEGRAM_CHAT_ID 사용.
        timeout: HTTP 타임아웃 (초). 기본 30초.
        proxy_url: 프록시 URL (선택).
    """

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = 30.0,
        proxy_url: Optional[str] = None,
    ) -> None:
        self._token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = str(chat_id or os.environ.get("TELEGRAM_CHAT_ID", ""))
        self._timeout = float(timeout)

        # 프록시 설정: proxy_url 지정 시 해당 프록시를 통해 요청
        # 예) "http://127.0.0.1:7890"  또는  "socks5://127.0.0.1:1080"
        # 미지정 시 환경변수 HTTPS_PROXY / HTTP_PROXY 자동 적용 (urllib 기본 동작)
        _proxy_url = proxy_url or os.environ.get("TELEGRAM_PROXY_URL", "")
        if _proxy_url:
            _proxies = {"http": _proxy_url, "https": _proxy_url}
            self._opener: Optional[urllib.request.OpenerDirector] = (
                urllib.request.build_opener(urllib.request.ProxyHandler(_proxies))
            )
        else:
            self._opener = None

        self._send_count_lock = threading.Lock()
        self._send_count_total: int = 0

        self._polling_thread: Optional[threading.Thread] = None
        self._polling_stop = threading.Event()
        self._last_update_id: int = 0

        if not self._token:
            log.warning("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        if not self._chat_id:
            log.warning("TELEGRAM_CHAT_ID가 설정되지 않았습니다.")

    @property
    def is_configured(self) -> bool:
        return bool(self._token) and bool(self._chat_id)

    def get_send_count_total(self) -> int:
        try:
            with self._send_count_lock:
                return int(self._send_count_total)
        except Exception as exc:
            log.debug("get_send_count_total lock 실패: %s", exc)
            try:
                return int(self._send_count_total)
            except Exception as exc2:
                log.debug("get_send_count_total 변환 실패: %s", exc2)
                return 0

    # ──────────────────────────────────────────
    # 공개 메서드
    # ──────────────────────────────────────────

    def send_error(self, result: Dict[str, Any]) -> bool:
        """에러 결과 dict를 텔레그램으로 전송."""
        error_type = str(result.get("error_type", "Unknown"))
        error_msg = str(result.get("error_message", ""))
        text = f"⚠️ <b>오류 발생</b>\n<code>{error_type}</code>\n{error_msg}"
        try:
            next_cnt = int(self.get_send_count_total() or 0) + 1
            text = str(text or "") + f"\n\n<i>TG sent: <code>{int(next_cnt)}</code></i>"
        except Exception as exc:
            log.debug("send_error: next_cnt 계산 실패: %s", exc)
        return self._send_message(
            text,
            parse_mode="HTML",
            debug_context={
                "kind": "error",
                "keys": list(result.keys()),
            },
        )

    def send_text(
        self,
        text: str,
        parse_mode: str = "HTML",
        *,
        debug_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """임의 텍스트를 텔레그램으로 전송."""
        try:
            next_cnt = int(self.get_send_count_total() or 0) + 1
        except Exception as exc:
            log.debug("send_text: next_cnt 계산 실패: %s", exc)
            next_cnt = None

        try:
            if next_cnt is not None:
                if str(parse_mode or "").upper() == "HTML":
                    text = str(text or "") + f"\n\n<i>TG sent: <code>{int(next_cnt)}</code></i>"
                elif str(parse_mode or "") == "":
                    text = str(text or "") + f"\n\nTG sent: {int(next_cnt)}"
        except Exception as exc:
            log.debug("send_text: 텍스트 추가 실패: %s", exc)
        ctx: Dict[str, Any] = {
            "kind": "text",
            "parse_mode": parse_mode,
            "len": len(str(text or "")),
        }
        try:
            if isinstance(debug_context, dict) and debug_context:
                ctx.update(dict(debug_context))
        except Exception as exc:
            log.debug("send_text: debug_context 업데이트 실패: %s", exc)
        return self._send_message(text, parse_mode=parse_mode, debug_context=ctx)

    def send_json_result(self, result: Dict[str, Any]) -> bool:
        """결과를 JSON 코드블록으로 전송 (디버그용)."""
        snippet = json.dumps(result, ensure_ascii=False, indent=2)
        # 텔레그램 메시지 최대 4096자 제한
        if len(snippet) > 3800:
            snippet = snippet[:3800] + "\n... (생략)"
        text = f"<pre>{snippet}</pre>"
        return self._send_message(text, parse_mode="HTML")

    # ------------------------------------------------------------------
    # 고객 접속 이력 / 서버 장애 알림
    # ------------------------------------------------------------------

    def send_session_event(self, event: Dict[str, Any]) -> bool:
        """고객 접속·해제 단건 이벤트를 텔레그램으로 전송.

        Args:
            event: formatters.format_session_event 와 동일한 dict.
                {
                    "type":        "connect" | "disconnect" | "reconnect" |
                                   "timeout" | "auth_fail",
                    "client_id":   str,
                    "ip":          str,          # 선택
                    "user_agent":  str,          # 선택
                    "session_id":  str,          # 선택
                    "duration_sec": float,       # disconnect 시 선택
                    "reason":      str,          # 선택
                    "ts":          datetime,     # 선택, None 이면 now()
                }
        Returns:
            전송 성공 여부
        """
        try:
            from .formatters import format_session_event  # noqa: PLC0415
        except ImportError:
            try:
                from formatters import format_session_event  # noqa: PLC0415
            except ImportError:
                log.warning("[TG][SESSION] formatters import 실패")
                return False
        try:
            text = format_session_event(event)
        except Exception as exc:
            log.warning("[TG][SESSION] 포매터 오류: %s", exc)
            return False
        return self._send_message(text, parse_mode="MarkdownV2",
                                  debug_context={"kind": "session_event",
                                                 "ev_type": str(event.get("type", ""))})

    def send_session_summary(
        self,
        events: list,
        period_label: str = "오늘",
    ) -> bool:
        """접속 이력 다건 요약을 텔레그램으로 전송.

        Args:
            events:       send_session_event 와 동일한 dict 의 list.
            period_label: "오늘" / "최근 1시간" 등 기간 레이블.
        """
        try:
            from .formatters import format_session_summary  # noqa: PLC0415
        except ImportError:
            try:
                from formatters import format_session_summary  # noqa: PLC0415
            except ImportError:
                log.warning("[TG][SESSION] formatters import 실패")
                return False
        try:
            text = format_session_summary(events, period_label)
        except Exception as exc:
            log.warning("[TG][SESSION] 요약 포매터 오류: %s", exc)
            return False
        return self._send_message(text, parse_mode="MarkdownV2",
                                  debug_context={"kind": "session_summary",
                                                 "count": len(events)})

    def send_system_fault(self, fault: Dict[str, Any]) -> bool:
        """서버 장애 이벤트를 텔레그램으로 전송.

        Args:
            fault: formatters.format_system_fault 와 동일한 dict.
                {
                    "type":       "crash" | "oom" | "db_error" | "network" |
                                  "timeout" | "api_error" | "data_missing" | "unknown",
                    "component":  str,
                    "message":    str,
                    "traceback":  str,          # 선택
                    "severity":   "critical" | "error" | "warning",
                    "ts":         datetime,     # 선택
                    "resolved":   bool,
                    "resolve_sec": float,       # 선택
                }
        Returns:
            전송 성공 여부
        """
        try:
            from .formatters import format_system_fault  # noqa: PLC0415
        except ImportError:
            try:
                from formatters import format_system_fault  # noqa: PLC0415
            except ImportError:
                log.warning("[TG][FAULT] formatters import 실패")
                return False
        try:
            text = format_system_fault(fault)
        except Exception as exc:
            log.warning("[TG][FAULT] 포매터 오류: %s", exc)
            return False
        severity = str(fault.get("severity", "error")).lower()
        return self._send_message(text, parse_mode="MarkdownV2",
                                  debug_context={"kind": "system_fault",
                                                 "fault_type": str(fault.get("type", "")),
                                                 "severity": severity})

    # ──────────────────────────────────────────
    # 명령 수신 폴링
    # ──────────────────────────────────────────

    def start_polling(
        self,
        on_command: Callable[[str, int], None],
        poll_interval: float = 2.0,
    ) -> None:
        """백그라운드에서 텔레그램 업데이트를 폴링하며 명령을 수신합니다.

        Args:
            on_command: 명령 수신 시 호출되는 콜백.
                        (command: str, chat_id: int) → None
                        예: on_command("/status", 123456789)
            poll_interval: 폴링 주기 (초). 기본 2초.

        지원 명령:
            /status        — 시스템 상태 조회
            /pause         — 알림 일시정지
            /resume        — 알림 재개
            /daily_stats   — 오늘 일간 통계 즉시 조회
            /weekly_stats  — 이번 주 주간 통계 즉시 조회
            /monthly_stats — 이번 달 월간 통계 즉시 조회
            /help          — 도움말
        """
        if self._polling_thread and self._polling_thread.is_alive():
            log.warning("폴링 스레드가 이미 실행 중입니다.")
            return

        self._polling_stop.clear()

        def _loop() -> None:
            log.info("텔레그램 폴링 시작 (간격: %.1f초)", poll_interval)
            while not self._polling_stop.is_set():
                try:
                    updates = self._get_updates()
                    for update in updates:
                        uid = int(update.get("update_id", 0))
                        if uid <= self._last_update_id:
                            continue
                        self._last_update_id = uid
                        self._dispatch_update(update, on_command)
                except Exception as exc:
                    log.warning("폴링 오류: %s", exc)
                self._polling_stop.wait(timeout=poll_interval)
            log.info("텔레그램 폴링 종료")

        self._polling_thread = threading.Thread(target=_loop, daemon=True, name="TelegramPoller")
        self._polling_thread.start()

    def stop_polling(self) -> None:
        """폴링 스레드를 정지합니다."""
        self._polling_stop.set()

    # ──────────────────────────────────────────
    # 내부 유틸리티
    # ──────────────────────────────────────────

    def _increment_send_count(self) -> None:
        """전송 카운터를 thread-safe하게 1 증가."""
        try:
            with self._send_count_lock:
                self._send_count_total += 1
        except Exception as exc:
            log.debug("_increment_send_count: lock 실패: %s", exc)
            try:
                self._send_count_total += 1
            except Exception as exc2:
                log.debug("_increment_send_count: 증가 실패: %s", exc2)
                pass

    def _api_url(self, method: str) -> str:
        return self.BASE_URL.format(token=self._token, method=method)

    def _http_post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """urllib로 JSON POST 요청. proxy_url 설정 시 프록시를 경유한다.

        네트워크 일시 오류 시 최대 3회 재시도합니다.
        """
        import time
        max_retries = 3
        retry_delay = 1.0  # 초

        for attempt in range(max_retries):
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                _open = self._opener.open if self._opener else urllib.request.urlopen
                with _open(req, timeout=self._timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                try:
                    raw = e.read().decode("utf-8", errors="replace")
                except Exception as exc:
                    log.debug("_http_post: HTTPError 응답 읽기 실패: %s", exc)
                    raw = ""
                try:
                    if raw:
                        return json.loads(raw)
                except Exception as exc:
                    log.debug("_http_post: JSON 파싱 실패: %s", exc)
                    pass
                return {"ok": False, "error_code": getattr(e, "code", None), "description": str(e)}
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < max_retries - 1:
                    log.warning("_http_post: 네트워크 오류, %d초 후 재시도 (%d/%d): %s",
                                 retry_delay, attempt + 1, max_retries, e)
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 지수 백오프
                    continue
                log.error("_http_post: 최대 재시도 횟수 초과: %s", e)
                return {"ok": False, "description": f"Network error after {max_retries} retries: {e}"}
            except Exception as e:
                return {"ok": False, "description": str(e)}

    def _http_get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """urllib로 GET 요청. proxy_url 설정 시 프록시를 경유한다."""
        full_url = url + "?" + urllib.parse.urlencode(params)
        try:
            _open = self._opener.open if self._opener else urllib.request.urlopen
            with _open(full_url, timeout=self._timeout + 2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8", errors="replace")
            except Exception as exc:
                log.debug("_http_get: HTTPError 응답 읽기 실패: %s", exc)
                raw = ""
            try:
                if raw:
                    return json.loads(raw)
            except Exception as exc:
                log.debug("_http_get: JSON 파싱 실패: %s", exc)
                pass
            return {"ok": False, "error_code": getattr(e, "code", None), "description": str(e)}
        except Exception as e:
            return {"ok": False, "description": str(e)}

    def _extract_telegram_byte_offset(self, description: str) -> Optional[int]:
        m = re.search(r"byte offset (\d+)", description)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception as exc:
            log.debug("_extract_telegram_byte_offset: int 변환 실패: %s", exc)
            return None

    def _message_snippet_at_byte_offset(self, text: str, byte_offset: int, context_bytes: int = 160) -> str:
        try:
            b = text.encode("utf-8", errors="replace")
            start = max(0, byte_offset - context_bytes)
            end = min(len(b), byte_offset + context_bytes)
            snippet = b[start:end].decode("utf-8", errors="replace")
            return snippet
        except Exception as exc:
            log.debug("_message_snippet_at_byte_offset: 디코딩 실패: %s", exc)
            return ""

    def _to_plain_text(self, text: str, *, parse_mode: str = "") -> str:
        """parse_mode 기반 포맷 제거 후 읽기 쉬운 plain text로 변환."""
        plain = str(text or "")
        try:
            if str(parse_mode or "").upper() == "HTML":
                # HTML parse_mode 실패 폴백 시 태그가 그대로 노출되지 않도록 제거
                plain = re.sub(r"<br\s*/?>", "\n", plain, flags=re.IGNORECASE)
                plain = re.sub(r"</p\s*>", "\n", plain, flags=re.IGNORECASE)
                plain = re.sub(r"<[^>]+>", "", plain)
                plain = html.unescape(plain)
            else:
                # MarkdownV2/일반 텍스트 폴백: 최소한의 장식 문자 제거
                plain = plain.replace("\\", "")
                plain = plain.replace("*", "").replace("`", "").replace("_", "")
        except Exception as exc:
            log.debug("_to_plain_text: 포맷 제거 실패: %s", exc)
            pass
        return plain

    def _send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        debug_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Telegram sendMessage API 호출."""
        if not self._token or not self._chat_id:
            log.error("봇 토큰 또는 채팅 ID가 설정되지 않았습니다.")
            return False
        try:
            data = self._http_post(
                self._api_url("sendMessage"),
                {
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
            )
            if not data.get("ok"):
                if parse_mode != "":
                    desc = str(data.get("description") or "")
                    offset = self._extract_telegram_byte_offset(desc)
                    snippet = (
                        self._message_snippet_at_byte_offset(text, offset)
                        if offset is not None
                        else ""
                    )
                    text_head = text[:500]
                    log.warning(
                        "메시지 전송 실패 — 일반 텍스트 재시도: %s | offset=%s | snippet=%r | head=%r | len=%d | ctx=%s",
                        desc,
                        offset,
                        snippet,
                        text_head,
                        len(text),
                        debug_context,
                    )
                    return self._send_message_plain(text, parse_mode=parse_mode, debug_context=debug_context)
                log.error("텔레그램 전송 실패: %s", data)
                return False
            try:
                head = str(text or "")
                if len(head) > 200:
                    head = head[:200] + "..."
                try:
                    kind = (debug_context or {}).get("kind") if isinstance(debug_context, dict) else None
                except Exception as exc:
                    log.debug("_send_message: kind 추출 실패: %s", exc)
                    kind = None
                if _TG_DEBUG or kind == "startup":
                    log.info(
                        "[TG][SEND] ok parse_mode=%s len=%d head=%r ctx=%s",
                        parse_mode,
                        len(text or ""),
                        head,
                        debug_context,
                    )
            except Exception as exc:
                log.debug("_send_message: 로깅 실패: %s", exc)
                pass

            try:
                self._increment_send_count()
            except Exception as exc:
                log.debug("_send_message: 전송 카운트 증가 실패: %s", exc)
                pass
            return True
        except Exception as exc:
            log.error("텔레그램 전송 예외: %s", exc)
            return False

    def _send_message_plain(
        self,
        text: str,
        parse_mode: str = "",
        debug_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """마크다운 없이 일반 텍스트로 전송 (폴백)."""
        plain = self._to_plain_text(text, parse_mode=parse_mode)
        try:
            data = self._http_post(
                self._api_url("sendMessage"),
                {"chat_id": self._chat_id, "text": plain, "disable_web_page_preview": True},
            )
            if not data.get("ok"):
                log.error("일반 텍스트 전송도 실패: %s | ctx=%s", data, debug_context)
            ok = bool(data.get("ok"))
            if ok:
                self._increment_send_count()
            return ok
        except Exception as exc:
            log.error("일반 텍스트 전송도 실패: %s", exc)
            return False

    def _get_updates(self) -> list:
        """getUpdates API 호출."""
        params: Dict[str, Any] = {"timeout": 1}
        if self._last_update_id > 0:
            params["offset"] = self._last_update_id + 1
        data = self._http_get(self._api_url("getUpdates"), params)
        if data.get("ok"):
            return data.get("result", [])
        return []

    def _dispatch_update(
        self,
        update: Dict[str, Any],
        on_command: Callable[[str, int], None],
    ) -> None:
        """수신된 업데이트에서 명령어를 추출해 콜백 호출."""
        msg = update.get("message") or {}
        text = str(msg.get("text") or "").strip()
        chat_id = int((msg.get("chat") or {}).get("id") or 0)
        from_id = int((msg.get("from") or {}).get("id") or 0)

        if not text or not chat_id:
            return

        # DS-02: 허가되지 않은 chat_id 로부터의 명령 차단
        if self._chat_id and str(chat_id) != str(self._chat_id):
            log.warning(
                "[TG][SECURITY] 허가되지 않은 chat_id=%d 명령 무시: %r (허가된 chat_id=%s)",
                chat_id, text, self._chat_id,
            )
            return

        try:
            log.info("[TG][RECV] chat=%d from=%d text=%r", chat_id, from_id, text)
        except Exception as exc:
            log.debug("_dispatch_update: 로깅 실패: %s", exc)
            pass

        # 봇 멘션 제거 (예: /status@MyBot → /status)
        # NOTE: '/@' 같은 커스텀 숏컷은 '@'를 포함하므로, 단순 split("@")는 사용하면 안 된다.
        try:
            m = re.match(r"^/([A-Za-z0-9_]+)@[A-Za-z0-9_]+(\s|$)", text)
        except Exception as exc:
            log.debug("_dispatch_update: 정규표현 실패: %s", exc)
            m = None
        if m:
            try:
                text = "/" + str(m.group(1)) + text[m.end(0) - 1 :]
            except Exception as exc:
                log.debug("_dispatch_update: 텍스트 변환 실패 (1): %s", exc)
                try:
                    text = "/" + str(m.group(1))
                except Exception as exc2:
                    log.debug("_dispatch_update: 텍스트 변환 실패 (2): %s", exc2)
                    pass

        if text.startswith("/"):
            log.info("명령 수신: %s (from=%d, chat=%d)", text, from_id, chat_id)
            try:
                on_command(text, chat_id)
            except Exception as exc:
                log.error("명령 처리 오류 (%s): %s", text, exc)


# ──────────────────────────────────────────────
# 설정 로더 (config.secrets.json / 환경변수 통합)
# ──────────────────────────────────────────────

def load_telegram_config(
    secrets_path: Optional[str] = None,
    config_path: str = "config.secrets.json",
) -> Dict[str, Any]:
    """config.secrets.json 또는 환경변수에서 텔레그램 설정을 로드합니다.

    secrets 파일 경로 결정 순서:
      1. secrets_path 인자
      2. 환경변수 APP_SECRETS_CONFIG
      3. config_path 인자 (기본: config.secrets.json)

    우선순위: 환경변수 > secrets 파일

    Returns:
        {"bot_token": str, "chat_id": str}
    """
    import pathlib

    # secrets 파일 경로 결정
    resolved = (
        secrets_path
        or os.environ.get("APP_SECRETS_CONFIG")
        or config_path
    )

    cfg: Dict[str, Any] = {}

    # secrets 파일에서 봇 토큰 / 채팅 ID 읽기
    try:
        path = pathlib.Path(resolved)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            telegram = data.get("telegram") or {}
            if telegram.get("bot_token"):
                cfg["bot_token"] = str(telegram["bot_token"])
            if telegram.get("chat_id"):
                cfg["chat_id"] = str(telegram["chat_id"])
        else:
            log.debug("secrets 파일 없음: %s", path)
    except Exception as exc:
        log.warning("secrets 파일 읽기 실패: %s", exc)

    # 환경변수가 파일보다 우선
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        cfg["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    if os.environ.get("TELEGRAM_CHAT_ID"):
        cfg["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]

    return cfg


def create_notifier_from_config(
    secrets_path: Optional[str] = None,
    **kwargs: Any,
) -> TelegramNotifier:
    """config.secrets.json / 환경변수 / APP_SECRETS_CONFIG 로 TelegramNotifier를 생성합니다.

    secrets 경로는 APP_SECRETS_CONFIG 환경변수로 오버라이드 가능합니다.
    """
    cfg = load_telegram_config(secrets_path)
    return TelegramNotifier(
        bot_token=cfg.get("bot_token") or "",
        chat_id=cfg.get("chat_id") or "",
    )
