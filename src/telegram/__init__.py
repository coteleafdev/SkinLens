"""telegram — CÔTELEAF 피부 분석 플랫폼 텔레그램 알림 패키지.

패키지 구조:
    telegram/
    ├── __init__.py       ← 공개 API (이 파일)
    ├── notifier.py       ← TelegramNotifier, StatisticsCollector, FaultReporter
    ├── formatters.py     ← MarkdownV2 메시지 포매터 (순수 함수)
    ├── monitors.py       ← MonitorsMixin (하트비트·통계·세션 루프)
    ├── commands.py       ← CommandsMixin (텔레그램 명령 핸들러)
    └── bridge.py         ← SkinAnalysisBridge (통합 진입점)

빠른 시작::

    from telegram import SkinAnalysisBridge, create_bridge_from_config

    # 설정 파일에서 브리지 자동 생성
    bridge = create_bridge_from_config("config/config.secrets.json")
    bridge.start()           # 모니터링 스레드 기동 (세션·하트비트·통계)
    bridge.start_polling()   # 텔레그램 명령 수신 (/status, /daily_stats …)

    # 분석 완료 시 결과 전송
    bridge.send_analysis_result(result, image_path="images/user_001.jpg")

    # 장애 발생 시 즉시 알림
    bridge.fault_reporter.report(
        fault_type="api_error",
        component="LlmSkinReport",
        exc=exc,
        severity="error",
    )

    # 장애 복구 알림
    bridge.fault_reporter.resolve(
        fault_type="api_error",
        component="LlmSkinReport",
        resolve_sec=30.0,
    )

    # 종료
    bridge.stop()

config.secrets.json 형식::

    {
        "telegram": {
            "bot_token": "1234567890:AAxxxx",
            "chat_id":   "-1001234567890"
        }
    }

환경변수로도 설정 가능::

    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...

참고:
    - Python 표준 라이브러리(urllib)만 사용 — 추가 설치 불필요.
    - python-telegram-bot 패키지와 이름이 겹칠 경우 폴더명을
      ``coteleaf_telegram`` 등으로 변경 후 import 경로를 수정하세요.
"""
from __future__ import annotations

# ── 핵심 클래스 ──────────────────────────────────────────────────
from .notifier import (
    TelegramNotifier,
    StatisticsCollector,
    FaultReporter,
)

# ── 통합 브리지 ───────────────────────────────────────────────────
from .bridge import (
    SkinAnalysisBridge,
    create_bridge_from_config,
    create_notifier_from_config,
    load_telegram_config,
)

# ── 포매터 (필요 시 직접 import) ──────────────────────────────────
from .formatters import (
    format_session_event,
    format_session_summary,
    format_system_fault,
    format_daily_stats,
    format_weekly_stats,
    format_monthly_stats,
)

__all__ = [
    # 핵심 클래스
    "TelegramNotifier",
    "StatisticsCollector",
    "FaultReporter",
    # 브리지
    "SkinAnalysisBridge",
    "create_bridge_from_config",
    "create_notifier_from_config",
    "load_telegram_config",
    # 포매터
    "format_session_event",
    "format_session_summary",
    "format_system_fault",
    "format_daily_stats",
    "format_weekly_stats",
    "format_monthly_stats",
]

__version__ = "3.0.0"
