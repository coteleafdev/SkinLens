# -*- coding: utf-8 -*-
"""
src.restoration — 얼굴 복원 백엔드 패키지

Strategy Pattern을 사용하여 다양한 복원 알고리즘을 유연하게 교체할 수 있습니다.
"""
from __future__ import annotations

from src.restoration.base import BaseRestorer
from src.restoration.registry import RestorerRegistry
from src.restoration.strategies.register_restorers import register_all_restorers

__all__ = [
    "BaseRestorer",
    "RestorerRegistry",
    "register_all_restorers",
]
