"""SkinAnalysisBridge 텔레그램 명령 핸들러 Mixin.

피부 분석 플랫폼 전용 명령어만 포함.
매매/예측/트레이드 관련 명령 없음.
"""
from __future__ import annotations
import logging
import threading
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class CommandsMixin:
    """텔레그램 명령 핸들러 Mixin (피부 분석 전용).

    지원 명령:
        /status        — 시스템 상태 조회
        /pause         — 알림 일시정지
        /resume        — 알림 재개
        /daily_stats   — 오늘 일간 통계 즉시 조회
        /weekly_stats  — 이번 주 주간 통계 즉시 조회
        /monthly_stats — 이번 달 월간 통계 즉시 조회
        /resource      — 리소스 사용량 조회 (메모리, CPU)
        /history       — 최근 실행 이력 조회
        /history_stats — 기간별 통계 조회
        /history_errors — 최근 에러 이력 조회
        /help          — 도움말
    """

    def _handle_command(self, command: str, chat_id: int) -> None:
        """텔레그램 명령어 처리."""
        parts = command.strip().split(None, 1)
        cmd   = parts[0].lower()
        args  = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/status":
            paused = self._user_pause_event.is_set()
            state  = "⏸ 일시정지" if paused else "▶️ 실행 중"
            sent   = self._notifier.get_send_count_total()
            stats  = getattr(self, "stats_collector", None)
            total_analyses = stats._day_total if stats else 0
            msg = (
                f"📊 <b>시스템 상태</b>\n"
                f"• 상태: {state}\n"
                f"• 오늘 분석: {total_analyses}건\n"
                f"• 텔레그램 전송: {sent}회\n"
                f"• 시각: {datetime.now().strftime('%H:%M:%S')}"
            )
            self._notifier.send_text(msg)

        elif cmd == "/pause":
            self._user_pause_event.set()
            self._notifier.send_text("⏸ <b>알림 일시정지</b>")

        elif cmd == "/resume":
            self._user_pause_event.clear()
            self._notifier.send_text("▶️ <b>알림 재개</b>")

        elif cmd == "/daily_stats":
            collector = getattr(self, "stats_collector", None)
            if collector is None:
                self._notifier.send_text("⚠️ 통계 수집기가 초기화되지 않았습니다.")
                return
            try:
                from .formatters import format_daily_stats  # noqa: PLC0415
            except ImportError:
                from formatters import format_daily_stats    # noqa: PLC0415
            try:
                stats = collector.get_daily_stats()
                stats["period_label"] = "오늘 (수동 조회)"
                self._notifier._send_message(
                    format_daily_stats(stats), parse_mode="MarkdownV2"
                )
            except Exception as exc:
                self._notifier.send_text(f"⚠️ 일간 통계 조회 오류: {exc}")

        elif cmd == "/weekly_stats":
            collector = getattr(self, "stats_collector", None)
            if collector is None:
                self._notifier.send_text("⚠️ 통계 수집기가 초기화되지 않았습니다.")
                return
            try:
                from .formatters import format_weekly_stats  # noqa: PLC0415
            except ImportError:
                from formatters import format_weekly_stats    # noqa: PLC0415
            try:
                self._notifier._send_message(
                    format_weekly_stats(collector.get_weekly_stats()),
                    parse_mode="MarkdownV2",
                )
            except Exception as exc:
                self._notifier.send_text(f"⚠️ 주간 통계 조회 오류: {exc}")

        elif cmd == "/monthly_stats":
            collector = getattr(self, "stats_collector", None)
            if collector is None:
                self._notifier.send_text("⚠️ 통계 수집기가 초기화되지 않았습니다.")
                return
            try:
                from .formatters import format_monthly_stats  # noqa: PLC0415
            except ImportError:
                from formatters import format_monthly_stats    # noqa: PLC0415
            try:
                self._notifier._send_message(
                    format_monthly_stats(collector.get_monthly_stats()),
                    parse_mode="MarkdownV2",
                )
            except Exception as exc:
                self._notifier.send_text(f"⚠️ 월간 통계 조회 오류: {exc}")

        elif cmd == "/resource":
            try:
                from src.cli.execution_history import ExecutionHistoryDB
                from src.utils.config import get_db_path_from_env
            except ImportError:
                self._notifier.send_text("⚠️ execution_history 모듈을 찾을 수 없습니다.")
                return
            
            try:
                db = ExecutionHistoryDB(get_db_path_from_env())
                stats = db.get_statistics(days=1)  # 오늘 통계
                
                msg = (
                    f"📊 <b>리소스 사용량 (오늘)</b>\n\n"
                    f"• 전체 실행: {stats['total_executions']}건\n"
                    f"• 성공률: {stats['success_rate']:.1f}%\n"
                    f"• 평균 점수: {stats['avg_score'] or 'N/A'}\n"
                    f"• 평균 실행 시간: {stats['avg_execution_time_sec'] or 'N/A'}초\n"
                )
                
                if stats['avg_memory_peak_mb']:
                    msg += f"• 평균 메모리 피크: {stats['avg_memory_peak_mb']:.1f}MB\n"
                else:
                    msg += "• 평균 메모리 피크: N/A\n"
                
                if stats['avg_cpu_percent']:
                    msg += f"• 평균 CPU 사용률: {stats['avg_cpu_percent']:.1f}%\n"
                else:
                    msg += "• 평균 CPU 사용률: N/A\n"
                
                self._notifier.send_text(msg)
            except Exception as exc:
                self._notifier.send_text(f"⚠️ 리소스 통계 조회 오류: {exc}")

        elif cmd == "/history":
            try:
                from src.cli.execution_history import ExecutionHistoryDB
                from src.utils.config import get_db_path_from_env
            except ImportError:
                self._notifier.send_text("⚠️ execution_history 모듈을 찾을 수 없습니다.")
                return
            
            try:
                db = ExecutionHistoryDB(get_db_path_from_env())
                rows = db.get_recent_executions(limit=20)
                
                msg = f"📋 <b>최근 실행 이력</b> (최근 20건)\n\n"
                if not rows:
                    msg += "이력이 없습니다."
                else:
                    for row in rows:
                        timestamp = row["timestamp"][:19]  # ISO 타임스탬프에서 날짜/시간만 추출
                        input_path = row["input_path"]
                        success = "✅" if row["success"] else "❌"
                        msg += f"{success} {timestamp} | {input_path}\n"
                
                self._notifier.send_text(msg)
            except Exception as exc:
                self._notifier.send_text(f"⚠️ 실행 이력 조회 오류: {exc}")

        elif cmd == "/history_stats":
            try:
                from src.cli.execution_history import ExecutionHistoryDB
                from src.utils.config import get_db_path_from_env
            except ImportError:
                self._notifier.send_text("⚠️ execution_history 모듈을 찾을 수 없습니다.")
                return
            
            try:
                # 인자 파싱 (기본 7일)
                days = 7
                if args:
                    try:
                        days = int(args)
                    except ValueError:
                        self._notifier.send_text("⚠️ 기간은 숫자여야 합니다. (예: /history_stats 7)")
                        return
                
                db = ExecutionHistoryDB(get_db_path_from_env())
                stats = db.get_statistics(days=days)
                
                msg = (
                    f"📊 <b>실행 통계 (최근 {days}일)</b>\n\n"
                    f"• 전체 실행: {stats['total_executions']}건\n"
                    f"• 성공: {stats['successful_executions']}건 ({stats['success_rate']:.1f}%)\n"
                    f"• 실패: {stats['failed_executions']}건\n"
                )
                
                if stats['avg_score']:
                    msg += f"• 평균 점수: {stats['avg_score']}\n"
                if stats['avg_execution_time_sec']:
                    msg += f"• 평균 실행 시간: {stats['avg_execution_time_sec']}초\n"
                if stats['avg_memory_peak_mb']:
                    msg += f"• 평균 메모리 피크: {stats['avg_memory_peak_mb']}MB\n"
                
                msg += "\n📅 일별 실행 수:\n"
                for date, count in stats['daily_counts'][:7]:  # 최근 7일만 표시
                    msg += f"  {date}: {count}건\n"
                
                self._notifier.send_text(msg)
            except Exception as exc:
                self._notifier.send_text(f"⚠️ 실행 통계 조회 오류: {exc}")

        elif cmd == "/history_errors":
            try:
                from src.cli.execution_history import ExecutionHistoryDB
                from src.utils.config import get_db_path_from_env
            except ImportError:
                self._notifier.send_text("⚠️ execution_history 모듈을 찾을 수 없습니다.")
                return
            
            try:
                db = ExecutionHistoryDB(get_db_path_from_env())
                rows = db.get_error_summary(limit=20)
                
                msg = f"❌ <b>최근 에러 이력</b> (최근 20건)\n\n"
                if not rows:
                    msg += "에러 이력이 없습니다."
                else:
                    for row in rows:
                        timestamp = row["timestamp"][:19]  # ISO 타임스탬프에서 날짜/시간만 추출
                        input_path = row["input_path"]
                        error_msg = row["error_message"] if row["error_message"] else "Unknown"
                        # 에러 메시지가 너무 길면 자름
                        error_short = error_msg[:50] + "..." if len(error_msg) > 50 else error_msg
                        msg += f"🔴 {timestamp} | {input_path}\n   {error_short}\n\n"
                
                self._notifier.send_text(msg)
            except Exception as exc:
                self._notifier.send_text(f"⚠️ 에러 이력 조회 오류: {exc}")

        elif cmd == "/help":
            self._notifier.send_text(
                "📖 <b>CÔTELEAF 피부 분석 봇 명령어</b>\n\n"
                "/status        — 시스템 상태 조회\n"
                "/pause         — 알림 일시정지\n"
                "/resume        — 알림 재개\n"
                "/daily_stats   — 오늘 일간 통계\n"
                "/weekly_stats  — 이번 주 주간 통계\n"
                "/monthly_stats — 이번 달 월간 통계\n"
                "/resource      — 리소스 사용량 조회 (메모리, CPU)\n"
                "/history       — 최근 실행 이력 조회\n"
                "/history_stats [일] — 기간별 통계 조회 (기본 7일)\n"
                "/history_errors — 최근 에러 이력 조회\n"
                "/help          — 이 도움말"
            )

        else:
            self._notifier.send_text(
                f"❓ 알 수 없는 명령: {command}\n/help 를 입력하세요."
            )
