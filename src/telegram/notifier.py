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
# 일/주/월간 통계 수집기
# ──────────────────────────────────────────────

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
            self._mo_fault_types[ft]  = self._mo_fault_types.get(ft, 0) + 1

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


# ──────────────────────────────────────────────
# 장애 직접 호출 헬퍼
# ──────────────────────────────────────────────

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
