"""공유 시크릿 해석 모듈.

server(deps.get_secret_key) 와 engine(_get_secret_key) 이 **동일한 소스**로
HMAC/JWT 시크릿을 해석하도록 단일화한다. 두 프로세스가 서로 다른 기본값을
쓰던 문제(JWT_SECRET_KEY 미설정 시 서명 불일치로 모든 위임이 401)를 구조적으로 제거.

정책:
  - 환경변수(`env_var`, 기본 JWT_SECRET_KEY)가 설정돼 있으면 그 값을 사용.
  - 미설정 + 프로덕션  → RuntimeError 로 **기동 거부(fail-fast)**.
  - 미설정 + 비프로덕션 → 경고 후 개발용 기본값 반환.

의존성 없음(표준 라이브러리만) → server/engine 양쪽에서 안전하게 import 가능.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# server 측 기존 기본값과 동일하게 맞춰 개발 환경 동작을 보존한다.
_DEV_DEFAULT_SECRET = "your-secret-key-change-in-production"

# 프로덕션으로 간주하는 환경 라벨
_PRODUCTION_LABELS = {"prod", "production", "live"}

# 환경 판별에 사용하는 환경변수 후보 (앞에서부터 우선)
_ENV_LABEL_VARS = ("APP_ENV", "ENVIRONMENT", "ENV", "DEPLOY_ENV")


def is_production(explicit: Optional[str] = None) -> bool:
    """프로덕션 환경 여부.

    Parameters
    ----------
    explicit:
        호출측이 이미 환경 라벨을 알고 있으면(예: config 의 ``environment``) 전달.
        None 이면 환경변수(_ENV_LABEL_VARS)로 자동 판별.
    """
    label = explicit
    if not label:
        for var in _ENV_LABEL_VARS:
            val = os.environ.get(var)
            if val:
                label = val
                break
    return (label or "").strip().lower() in _PRODUCTION_LABELS


def get_hmac_secret(
    env_var: str = "JWT_SECRET_KEY",
    *,
    production: Optional[bool] = None,
) -> str:
    """HMAC/JWT 시크릿 반환.

    Parameters
    ----------
    env_var:
        시크릿이 담긴 환경변수 이름. server/engine 이 **동일한 이름**을 써야 한다.
    production:
        프로덕션 여부를 명시(예: config 기반). None 이면 is_production() 자동 판별.

    Raises
    ------
    RuntimeError:
        프로덕션인데 ``env_var`` 가 비어 있는 경우(fail-fast).
    """
    key = os.environ.get(env_var)
    if key:
        return key

    prod = is_production() if production is None else production
    if prod:
        raise RuntimeError(
            f"{env_var} 미설정: 프로덕션 환경에서는 기본 시크릿 사용이 금지됩니다. "
            f"server/engine 양쪽에 동일한 {env_var} 를 설정한 뒤 재기동하세요. (fail-fast)"
        )

    log.warning(
        "%s 미설정 — 개발용 기본 시크릿 사용 중. 프로덕션에서는 기동이 거부됩니다. "
        "server/engine 위임을 쓰려면 양쪽에 동일한 %s 를 설정하세요.",
        env_var,
        env_var,
    )
    return _DEV_DEFAULT_SECRET
