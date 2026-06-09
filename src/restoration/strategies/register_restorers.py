# -*- coding: utf-8 -*-
"""
src.restoration.strategies.register_restorers — 복원 백엔드 자동 등록

앱 시작 시 이 모듈을 import하여 모든 복원 백엔드를 레지스트리에 등록합니다.

사용 예:
    from src.restoration.strategies.register_restorers import register_all_restorers
    register_all_restorers()
"""
from __future__ import annotations

import logging

from src.restoration.registry import RestorerRegistry
from src.restoration.strategies.codeformer_restorer import CodeFormerRestorer
from src.restoration.strategies.restoreformer_restorer import RestoreFormerRestorer

log = logging.getLogger(__name__)


def register_all_restorers() -> None:
    """모든 복원 백엔드를 레지스트리에 등록."""
    # CodeFormer 등록
    RestorerRegistry.register("codeformer_v1", aliases=["codeformer", "cf_v1"])(CodeFormerRestorer)
    
    # RestoreFormer++ 등록
    RestorerRegistry.register("restoreformer_v1", aliases=["restoreformer", "rf_v1"])(RestoreFormerRestorer)
    
    log.info("모든 복원 백엔드 등록 완료: %s", RestorerRegistry.list_available())


# 모듈 import 시 자동 등록 (선택적)
# register_all_restorers()
