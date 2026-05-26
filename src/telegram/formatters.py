"""텔레그램 메시지 포매터 모음 (CÔTELEAF 피부 분석 플랫폼 전용).

순수 함수 모음. TelegramNotifier 등 I/O 클래스에 의존하지 않는다.

외부에서 사용 시:
    from telegram.formatters import format_session_event, format_system_fault
    from telegram.formatters import format_daily_stats
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────
_TG_MAX_LEN = 4096
_TG_TRUNCATE_SUFFIX = "\n\n⚠️ \\(메시지 일부 생략\\)"

# ──────────────────────────────────────────────
# 공통 유틸리티
# ──────────────────────────────────────────────

def _esc_mdv2(s: str) -> str:
    """MarkdownV2 특수문자 이스케이프 (모듈 공통).

    텔레그램 MarkdownV2 에서 이스케이프가 필요한 모든 특수문자를 처리한다.
    중복 정의를 방지하기 위해 모든 formatter 가 이 함수를 공유한다.
    """
    for ch in r"\_*[]()~`>#+-=|{}.!":
        s = s.replace(ch, f"\\{ch}")
    return s


# ──────────────────────────────────────────────
# 이모지 매핑
# ──────────────────────────────────────────────

_SESSION_EMOJI = {
    "connect": "🟢",
    "disconnect": "🔴",
    "reconnect": "🟡",
    "timeout": "⏱️",
    "auth_fail": "🔐",
}

_FAULT_EMOJI = {
    "crash": "💥",
    "oom": "🔴",
    "db_error": "🗄️",
    "network": "🌐",
    "timeout": "⏱️",
    "api_error": "📡",
    "data_missing": "❓",
    "unknown": "⚠️",
}

# ──────────────────────────────────────────────
# 메시지 포매터
# ──────────────────────────────────────────────

def format_session_event(event: Dict[str, Any]) -> str:
    """고객 접속/해제 단건 이벤트 → MarkdownV2 텔레그램 메시지.

    Args:
        event: {
            "type":       "connect" | "disconnect" | "reconnect" | "timeout" | "auth_fail",
            "client_id":  str,          # 고객/클라이언트 식별자
            "ip":         str,          # 접속 IP (선택)
            "user_agent": str,          # UA/플랫폼 (선택)
            "session_id": str,          # 세션 ID (선택)
            "duration_sec": float,      # 접속 지속 시간 초 (disconnect 시)
            "reason":     str,          # 해제 사유 (선택)
            "ts":         datetime,     # 이벤트 시각 (선택, None 이면 now())
        }
    Returns:
        MarkdownV2 형식 문자열
    """
    ev_type    = str(event.get("type", "unknown")).lower()
    client_id  = _esc_mdv2(str(event.get("client_id", "unknown")))
    ip         = _esc_mdv2(str(event.get("ip", "")))
    ua         = _esc_mdv2(str(event.get("user_agent", "")))
    session_id = _esc_mdv2(str(event.get("session_id", "")))
    reason     = _esc_mdv2(str(event.get("reason", "")))
    ts: datetime = event.get("ts") or datetime.now()
    ts_str = _esc_mdv2(ts.strftime("%Y-%m-%d %H:%M:%S"))

    emoji = _SESSION_EMOJI.get(ev_type, "❔")

    label_map = {
        "connect":    "접속",
        "disconnect": "해제",
        "reconnect":  "재접속",
        "timeout":    "타임아웃",
        "auth_fail":  "인증 실패",
    }
    label = _esc_mdv2(label_map.get(ev_type, ev_type))

    lines = [
        f"{emoji} *고객 {label}*  |  `{ts_str}`",
        f"👤 클라이언트: `{client_id}`",
    ]
    if ip:
        lines.append(f"🌐 IP: `{ip}`")
    if ua:
        lines.append(f"📱 플랫폼: {ua}")
    if session_id:
        lines.append(f"🔑 세션: `{session_id}`")

    # disconnect/timeout: 지속 시간 표시
    dur = event.get("duration_sec")
    if dur is not None:
        try:
            d = float(dur)
            if d >= 3600:
                dur_str = f"{d/3600:.1f}시간"
            elif d >= 60:
                dur_str = f"{d/60:.0f}분 {int(d)%60}초"
            else:
                dur_str = f"{int(d)}초"
            lines.append(f"⏳ 접속 시간: {_esc_mdv2(dur_str)}")
        except Exception as e:
            logger.debug("접속 시간 계산 실패: %s", e)

    if reason:
        lines.append(f"📝 사유: {reason}")

    return "\n".join(lines)


def format_session_summary(
    events: list[Dict[str, Any]],
    period_label: str = "오늘",
) -> str:
    """접속 이력 다건 요약 → MarkdownV2 텔레그램 메시지.

    Args:
        events:       format_session_event 와 동일 dict 의 list.
        period_label: "오늘" / "최근 1시간" 등 기간 레이블.
    Returns:
        MarkdownV2 형식 문자열
    """
    total      = len(events)
    connects   = sum(1 for e in events if e.get("type") == "connect")
    disconnects= sum(1 for e in events if e.get("type") == "disconnect")
    timeouts   = sum(1 for e in events if e.get("type") == "timeout")
    auth_fails = sum(1 for e in events if e.get("type") == "auth_fail")

    unique_ips = {str(e.get("ip", "")) for e in events if e.get("ip")}
    unique_clients = {str(e.get("client_id", "")) for e in events if e.get("client_id")}

    now_str = _esc_mdv2(datetime.now().strftime("%H:%M:%S"))
    pl = _esc_mdv2(period_label)

    lines = [
        f"📊 *접속 이력 요약* | {pl}  |  `{now_str}`",
        "",
        f"• 총 이벤트: *{total}건*",
        f"• 접속: {connects}건  |  해제: {disconnects}건",
    ]
    if timeouts:
        lines.append(f"• 타임아웃: {timeouts}건")
    if auth_fails:
        lines.append(f"• 인증 실패: {auth_fails}건  ⚠️")

    lines += [
        "",
        f"• 고유 클라이언트: {len(unique_clients)}명",
        f"• 고유 IP: {len(unique_ips)}개",
    ]

    # 최근 5건 간략 표시
    if events:
        lines += ["", "*최근 이벤트*"]
        for e in events[-5:]:
            ev_type = str(e.get("type", "?"))
            cid     = _esc_mdv2(str(e.get("client_id", "?")))
            ts_e    = e.get("ts") or datetime.now()
            t_str   = _esc_mdv2(ts_e.strftime("%H:%M:%S"))
            em      = _SESSION_EMOJI.get(ev_type, "❔")
            lines.append(f"  {em} `{t_str}` {_esc_mdv2(ev_type):10s} `{cid}`")

    return "\n".join(lines)


def format_system_fault(fault: Dict[str, Any]) -> str:
    """서버 장애 이벤트 → MarkdownV2 텔레그램 메시지.

    Args:
        fault: {
            "type":       "crash" | "oom" | "db_error" | "network" |
                          "timeout" | "api_error" | "data_missing" | "unknown",
            "component":  str,          # 장애 발생 컴포넌트명
            "message":    str,          # 오류 메시지 (최대 400자)
            "traceback":  str,          # 스택트레이스 일부 (선택, 최대 600자)
            "severity":   "critical" | "error" | "warning",
            "ts":         datetime,     # 발생 시각 (선택)
            "resolved":   bool,         # 복구 여부 (기본 False)
            "resolve_sec": float,       # 복구 소요 시간 초 (resolved=True 시)
        }
    Returns:
        MarkdownV2 형식 문자열
    """
    fault_type = str(fault.get("type", "unknown")).lower()
    component  = _esc_mdv2(str(fault.get("component", "unknown")))
    message    = _esc_mdv2(str(fault.get("message", ""))[:400])
    traceback  = _esc_mdv2(str(fault.get("traceback", ""))[:600])
    severity   = str(fault.get("severity", "error")).lower()
    resolved   = bool(fault.get("resolved", False))
    ts: datetime = fault.get("ts") or datetime.now()
    ts_str = _esc_mdv2(ts.strftime("%Y-%m-%d %H:%M:%S"))

    emoji = _FAULT_EMOJI.get(fault_type, "⚠️")

    sev_map = {"critical": "🆘 긴급", "error": "🔴 오류", "warning": "🟡 경고"}
    sev_label = _esc_mdv2(sev_map.get(severity, severity))

    status_str = "✅ 복구됨" if resolved else "🔴 미해결"
    resolve_sec = fault.get("resolve_sec")

    lines = [
        f"{emoji} *서버 장애 발생*  |  {sev_label}",
        f"🕐 시각: `{ts_str}`",
        f"⚙️  컴포넌트: `{component}`",
        f"🔖 유형: `{_esc_mdv2(fault_type)}`",
        f"📌 상태: {status_str}",
    ]

    if resolved and resolve_sec is not None:
        try:
            rs = float(resolve_sec)
            r_str = f"{rs:.0f}초" if rs < 60 else f"{rs/60:.1f}분"
            lines.append(f"⏱️  복구 시간: {_esc_mdv2(r_str)}")
        except Exception as e:
            logger.debug("복구 시간 계산 실패: %s", e)

    if message:
        lines += ["", f"📄 *오류 내용*", f"```\n{message}\n```"]

    if traceback:
        lines += ["", f"🔍 *스택트레이스*", f"```\n{traceback}\n```"]

    return "\n".join(lines)

# ──────────────────────────────────────────────
# 일/주/월간 통계 보고 포매터
# ──────────────────────────────────────────────

def _fmt_pct(num: float, denom: float, *, zero: str = "0.0%") -> str:
    """분율 퍼센트 문자열 반환. 분모 0 이면 zero 반환."""
    if denom <= 0:
        return zero
    return f"{num / denom * 100:.1f}%"


def _fmt_signed(val: float, decimals: int = 2) -> str:
    """부호 포함 숫자 문자열."""
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.{decimals}f}"



def format_daily_stats(stats: Dict[str, Any]) -> str:
    """일간 피부 분석 통계 → MarkdownV2 텔레그램 메시지.

    Args:
        stats: StatisticsCollector.get_daily_stats() 반환 dict.
    Returns:
        MarkdownV2 형식 문자열
    """
    date_str  = _esc_mdv2(str(stats.get("date", "")))
    total     = int(stats.get("total", 0))
    errors    = int(stats.get("errors", 0))
    sessions  = int(stats.get("sessions", 0))
    faults    = int(stats.get("faults", 0))
    avg_score = float(stats.get("avg_score", 0.0))
    max_score = float(stats.get("max_score", 0.0))
    min_score = float(stats.get("min_score", 0.0))
    avg_age   = float(stats.get("avg_age", 0.0))
    sent      = int(stats.get("sent_count", 0))
    label     = _esc_mdv2(str(stats.get("period_label", "오늘")))
    err_rate  = _fmt_pct(errors, total + errors)

    lines = [
        f"📅 *일간 통계 보고*  |  {label} `{date_str}`",
        "",
        "🔬 *피부 분석 현황*",
        f"• 총 분석: *{total}건*  (오류 {errors}건  오류율 {err_rate})",
    ]
    if total > 0:
        lines += [
            f"• 평균 점수: *{avg_score:.1f}점*",
            f"• 최고: {max_score:.1f}점  |  최저: {min_score:.1f}점",
        ]
        if avg_age > 0:
            lines.append(f"• 평균 인지 나이: {avg_age:.1f}세")

    if sessions or faults:
        lines += ["", "🌐 *접속 / 장애*"]
        if sessions:
            lines.append(f"• 고객 접속: {sessions}건")
        if faults:
            fault_types = stats.get("fault_types", {})
            ft_str = "  ".join(
                f"{_esc_mdv2(k)} {v}건"
                for k, v in sorted(fault_types.items(), key=lambda x: -x[1])
            )
            lines.append(f"• 장애: {faults}건  {ft_str}".rstrip())

    lines += ["", f"📨 텔레그램 전송: {sent}건"]
    return "\n".join(lines)


def format_weekly_stats(stats: Dict[str, Any]) -> str:
    """주간 피부 분석 통계 → MarkdownV2 텔레그램 메시지."""
    week_lbl  = _esc_mdv2(str(stats.get("week_label", "")))
    start     = _esc_mdv2(str(stats.get("start_date", "")))
    end_d     = _esc_mdv2(str(stats.get("end_date", "")))
    total     = int(stats.get("total", 0))
    errors    = int(stats.get("errors", 0))
    sessions  = int(stats.get("sessions", 0))
    faults    = int(stats.get("faults", 0))
    avg_score = float(stats.get("avg_score", 0.0))
    max_score = float(stats.get("max_score", 0.0))
    active_d  = int(stats.get("active_days", 0))
    daily_avg = float(stats.get("daily_avg_total", 0.0))
    peak_day  = _esc_mdv2(str(stats.get("peak_day", "")))
    peak_cnt  = int(stats.get("peak_day_count", 0))
    sent      = int(stats.get("sent_count", 0))
    err_rate  = _fmt_pct(errors, total + errors)

    lines = [
        f"📆 *주간 통계 보고*  |  {week_lbl}",
        f"({start} ~ {end_d})",
        "",
        "🔬 *피부 분석 현황*",
        f"• 총 분석: *{total}건*  (오류 {errors}건  오류율 {err_rate}  운영 {active_d}일)",
        f"• 일 평균: {daily_avg:.1f}건",
    ]
    if total > 0:
        lines.append(f"• 평균 점수: *{avg_score:.1f}점*  |  최고: {max_score:.1f}점")
    if peak_day:
        lines.append(f"• 최다 분석일: {peak_day}  ({peak_cnt}건)")

    if sessions or faults:
        lines += ["", "🌐 *접속 / 장애*"]
        if sessions:
            lines.append(f"• 고객 접속: {sessions}건")
        if faults:
            fault_types = stats.get("fault_types", {})
            ft_str = "  ".join(
                f"{_esc_mdv2(k)} {v}건"
                for k, v in sorted(fault_types.items(), key=lambda x: -x[1])
            )
            lines.append(f"• 장애: {faults}건  {ft_str}".rstrip())

    lines += ["", f"📨 텔레그램 전송: {sent}건"]
    return "\n".join(lines)


def format_monthly_stats(stats: Dict[str, Any]) -> str:
    """월간 피부 분석 통계 → MarkdownV2 텔레그램 메시지."""
    month_lbl  = _esc_mdv2(str(stats.get("month_label", "")))
    yr_mo      = _esc_mdv2(str(stats.get("year_month", "")))
    total      = int(stats.get("total", 0))
    errors     = int(stats.get("errors", 0))
    sessions   = int(stats.get("sessions", 0))
    faults     = int(stats.get("faults", 0))
    avg_score  = float(stats.get("avg_score", 0.0))
    max_score  = float(stats.get("max_score", 0.0))
    active_d   = int(stats.get("active_days", 0))
    daily_avg  = float(stats.get("daily_avg_total", 0.0))
    weekly_tot = list(stats.get("weekly_totals", []))
    peak_wk    = int(stats.get("peak_week", 0))
    sent       = int(stats.get("sent_count", 0))
    uptime     = float(stats.get("uptime_pct", 0.0))
    err_rate   = _fmt_pct(errors, total + errors)

    lines = [
        f"🗓️ *월간 통계 보고*  |  {month_lbl}  (`{yr_mo}`)",
        "",
        "🔬 *피부 분석 현황*",
        f"• 총 분석: *{total}건*  (오류 {errors}건  오류율 {err_rate})",
        f"• 일 평균: {daily_avg:.1f}건  |  운영일: {active_d}일  (가동률 {uptime:.1%})",
    ]
    if total > 0:
        lines.append(f"• 평균 점수: *{avg_score:.1f}점*  |  최고: {max_score:.1f}점")

    if weekly_tot:
        lines += ["", "📈 *주차별 분석 건수*"]
        wk_max = max(weekly_tot) if weekly_tot and max(weekly_tot) > 0 else 1
        for i, cnt in enumerate(weekly_tot, 1):
            bar = "█" * min(int(cnt / wk_max * 10), 10)
            pk  = " ←최다" if i == peak_wk else ""
            lines.append(f"  {i}주차: {cnt:4d}건  {bar}{_esc_mdv2(pk)}")

    if sessions or faults:
        lines += ["", "🌐 *접속 / 장애*"]
        if sessions:
            lines.append(f"• 고객 접속: {sessions}건")
        if faults:
            fault_types = stats.get("fault_types", {})
            ft_str = "  ".join(
                f"{_esc_mdv2(k)} {v}건"
                for k, v in sorted(fault_types.items(), key=lambda x: -x[1])
            )
            lines.append(f"• 장애: {faults}건  {ft_str}".rstrip())

    lines += ["", f"📨 텔레그램 전송: {sent}건"]
    return "\n".join(lines)
