"""src.scoring._logging — 피부 분석 로깅 설정.

[REFACTOR] skin_scoring.py에서 분리.
  - _configure_analyzer_logging
  - prepare_analyzer_logging_for_gui
  - restore_analyzer_logging_after_gui
"""
from __future__ import annotations

import logging
import sys

_ANALYZER_DEFAULT_STDERR_HANDLER: logging.Handler | None = None
_ANALYZER_LOGGING_CONFIGURED: bool = False


def configure_analyzer_logging() -> None:
    global _ANALYZER_DEFAULT_STDERR_HANDLER, _ANALYZER_LOGGING_CONFIGURED
    if _ANALYZER_LOGGING_CONFIGURED:
        return
    _ANALYZER_LOGGING_CONFIGURED = True
    pkg = logging.getLogger("skin_scoring")
    pkg.setLevel(logging.DEBUG)
    if pkg.handlers:
        return
    h = logging.StreamHandler(sys.stderr)
    h.setLevel(logging.DEBUG)
    h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    _ANALYZER_DEFAULT_STDERR_HANDLER = h
    pkg.addHandler(h)
    pkg.propagate = False


# 하위 호환 alias
_configure_analyzer_logging = configure_analyzer_logging


def prepare_analyzer_logging_for_gui() -> None:
    global _ANALYZER_DEFAULT_STDERR_HANDLER
    pkg = logging.getLogger("skin_scoring")
    if _ANALYZER_DEFAULT_STDERR_HANDLER is not None and _ANALYZER_DEFAULT_STDERR_HANDLER in pkg.handlers:
        pkg.removeHandler(_ANALYZER_DEFAULT_STDERR_HANDLER)
    pkg.setLevel(logging.DEBUG)
    pkg.propagate = True


def restore_analyzer_logging_after_gui() -> None:
    global _ANALYZER_DEFAULT_STDERR_HANDLER
    pkg = logging.getLogger("skin_scoring")
    pkg.propagate = False
    if _ANALYZER_DEFAULT_STDERR_HANDLER is not None and _ANALYZER_DEFAULT_STDERR_HANDLER not in pkg.handlers:
        pkg.addHandler(_ANALYZER_DEFAULT_STDERR_HANDLER)
