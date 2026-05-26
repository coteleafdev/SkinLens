"""
deps.py — 서버 전역 공유 의존성·상태·유틸리티

모든 라우터가 이 모듈에서 import 한다.
FastAPI app 인스턴스 자체는 server.py 에 있고,
여기서는 app 에 의존하지 않는 것만 선언한다.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from urllib.request import urlopen, Request as UrlRequest

from fastapi import Header, HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.cli.execution_history import ExecutionHistoryDB
from src.utils.config import get_db_path_from_env

log = logging.getLogger(__name__)

# ── Rate Limiter ───────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── 역할 / 민감 필드 ──────────────────────────────────────────────────────
ROLES: Dict[str, list] = {
    "customer": ["read_own"],
    "admin":    ["read_all", "write", "delete"],
    "analyst":  ["read_all"],
}

SENSITIVE_FIELDS = [
    "image_path",
    "input_path",
    "output_dir",
    "stack_trace",
    "error_traceback",
]

# ── config.json 로드 함수 ─────────────────────────────────────────────────────
from src.utils.config import load_config as _load_config

# ── 서버 상수 ──────────────────────────────────────────────────────────────
APP_NAME    = "skin-analysis"

# config.json에서 설정 로드 (lazy getter)
def _get_config() -> dict:
    return _load_config()

def get_server_config() -> dict:
    """config.json에서 server 설정을 가져옵니다."""
    return _get_config().get("server", {})

def get_database_config() -> dict:
    """config.json에서 database 설정을 가져옵니다."""
    return _get_config().get("database", {})

def get_jwt_config() -> dict:
    """config.json에서 jwt 설정을 가져옵니다."""
    return _get_config().get("jwt", {})

def get_timeouts_config() -> dict:
    """config.json에서 timeouts 설정을 가져옵니다."""
    return _get_config().get("timeouts", {})

# ── 모듈 레벨 상수 (하위 호환성 유지 - config reload 시 getter 사용 권장) ─────
# 아래 상수들은 모듈 로드 시점에 고정됩니다. config reload를 지원하려면 getter 함수를 사용하세요.

# 하위 호환성을 위한 모듈 레벨 상수 (getter 사용 권장)
_config_cache = _get_config()
_server_config_cache = _config_cache.get("server", {})
_database_config_cache = _config_cache.get("database", {})
_sqlite_config_cache = _database_config_cache.get("sqlite", {})
_supabase_config_cache = _database_config_cache.get("supabase", {})
_jwt_config_cache = _config_cache.get("jwt", {})
_environment_cache = _config_cache.get("environment", "development")

# JWT 설정 (getter 사용 권장)
_SECRET_KEY = os.getenv(_jwt_config_cache.get("secret_key_env", "JWT_SECRET_KEY"), "your-secret-key-change-in-production")
_ALGORITHM = _jwt_config_cache.get("algorithm", "HS256")
_ACCESS_TOKEN_EXPIRE_MINUTES = _jwt_config_cache.get("access_token_expire_minutes", 30)

# 서버 설정 (getter 사용 권장)
_SERVER_HOST = _server_config_cache.get("host", "0.0.0.0")
_SERVER_PORT = _server_config_cache.get("port", 8000)
_SERVER_URL = os.getenv("SERVER_URL", _server_config_cache.get("url", f"http://{_SERVER_HOST}:{_SERVER_PORT}"))
_ALLOWED_EXT = set(_server_config_cache.get("allowed_extensions", [".jpg", ".jpeg", ".png", ".webp"]))
_MAX_UPLOAD_BYTES = int(os.environ.get("SKIN_API_MAX_UPLOAD_BYTES", str(_server_config_cache.get("max_upload_bytes", 20 * 1024 * 1024))))
_ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", _server_config_cache.get("allowed_origins", "*")).split(",")

# ── Job 동시 실행 제어 ─────────────────────────────────────────────────────
_MAX_CONCURRENT_JOBS = int(os.environ.get("SKIN_API_MAX_CONCURRENT", str(_server_config_cache.get("max_concurrent_jobs", 2))))
JOB_SEMAPHORE = threading.Semaphore(_MAX_CONCURRENT_JOBS)

# ── 타임아웃 설정 ────────────────────────────────────────────────────────────
_timeouts_config_cache = get_timeouts_config()
_JOB_SEMAPHORE_TIMEOUT_SEC = _timeouts_config_cache.get("job_semaphore_timeout_sec", 300)

# ── 데이터베이스 설정 ────────────────────────────────────────────────────────
_DEFAULT_DB_PATH = os.getenv("EXECUTION_HISTORY_DB", _sqlite_config_cache.get("path", "execution_history.db"))

# ── Supabase 설정 ─────────────────────────────────────────────────────────
_SUPABASE_ENABLED = _supabase_config_cache.get("enabled", False)
_SUPABASE_URL = os.getenv("SUPABASE_URL", _supabase_config_cache.get("url"))
_SUPABASE_KEY = os.getenv("SUPABASE_KEY", _supabase_config_cache.get("key"))
_SUPABASE_BUCKET = _supabase_config_cache.get("bucket", "skin-images")

_active_jobs_lock:  threading.Lock = threading.Lock()
_active_jobs_count: int = 0

# [FIX 2026-05-24] 중복 선언 제거 - get_shared_executor()의 _shared_executor만 사용
# _MAX_WORKERS = int(os.environ.get("SKIN_API_MAX_WORKERS", "4"))
# executor = ThreadPoolExecutor(max_workers=max(1, _MAX_WORKERS))

# ── 백업·정리 설정 ─────────────────────────────────────────────────────────
_CLEANUP_INTERVAL_H = int(os.environ.get("SKIN_API_CLEANUP_INTERVAL_H", "6"))
_MAX_JOB_AGE_H = int(os.environ.get("SKIN_API_MAX_JOB_AGE_H", "24"))
_BACKUP_INTERVAL_H = int(os.environ.get("SKIN_API_BACKUP_INTERVAL_H", "24"))
_BACKUP_DIR = os.environ.get("SKIN_API_BACKUP_DIR", "backup")

# ── Getter 함수 (config reload 지원) ─────────────────────────────────────────
def get_secret_key() -> str:
    """JWT 시크릿 키 반환 (config reload 지원)."""
    jwt_cfg = get_jwt_config()
    return os.getenv(jwt_cfg.get("secret_key_env", "JWT_SECRET_KEY"), "your-secret-key-change-in-production")

def get_algorithm() -> str:
    """JWT 알고리즘 반환 (config reload 지원)."""
    return get_jwt_config().get("algorithm", "HS256")

def get_access_token_expire_minutes() -> int:
    """JWT 토큰 만료 시간(분) 반환 (config reload 지원)."""
    return get_jwt_config().get("access_token_expire_minutes", 30)

def get_server_host() -> str:
    """서버 호스트 반환 (config reload 지원)."""
    return get_server_config().get("host", "0.0.0.0")

def get_server_port() -> int:
    """서버 포트 반환 (config reload 지원)."""
    return get_server_config().get("port", 8000)

def get_server_url() -> str:
    """서버 URL 반환 (config reload 지원)."""
    server_cfg = get_server_config()
    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 8000)
    return os.getenv("SERVER_URL", server_cfg.get("url", f"http://{host}:{port}"))

def get_allowed_extensions() -> set:
    """허용된 파일 확장자 반환 (config reload 지원)."""
    return set(get_server_config().get("allowed_extensions", [".jpg", ".jpeg", ".png", ".webp"]))

def get_max_upload_bytes() -> int:
    """최대 업로드 바이트 수 반환 (config reload 지원)."""
    server_cfg = get_server_config()
    return int(os.environ.get("SKIN_API_MAX_UPLOAD_BYTES", str(server_cfg.get("max_upload_bytes", 20 * 1024 * 1024))))

def get_allowed_origins() -> list:
    """허용된 CORS origins 반환 (config reload 지원)."""
    server_cfg = get_server_config()
    return os.getenv("ALLOWED_ORIGINS", server_cfg.get("allowed_origins", "*")).split(",")

def get_max_concurrent_jobs() -> int:
    """최대 동시 Job 수 반환 (config reload 지원)."""
    server_cfg = get_server_config()
    return int(os.environ.get("SKIN_API_MAX_CONCURRENT", str(server_cfg.get("max_concurrent_jobs", 2))))

def get_job_semaphore_timeout_sec() -> int:
    """Job 세마포어 타임아웃(초) 반환 (config reload 지원)."""
    return get_timeouts_config().get("job_semaphore_timeout_sec", 300)

def get_default_db_path() -> str:
    """기본 DB 경로 반환 (config reload 지원)."""
    db_cfg = get_database_config()
    sqlite_cfg = db_cfg.get("sqlite", {})
    return os.getenv("EXECUTION_HISTORY_DB", sqlite_cfg.get("path", "execution_history.db"))

def get_supabase_enabled() -> bool:
    """Supabase 사용 여부 반환 (config reload 지원)."""
    return get_database_config().get("supabase", {}).get("enabled", False)

def get_supabase_url() -> Optional[str]:
    """Supabase URL 반환 (config reload 지원)."""
    return os.getenv("SUPABASE_URL", get_database_config().get("supabase", {}).get("url"))

def get_supabase_key() -> Optional[str]:
    """Supabase 키 반환 (config reload 지원)."""
    return os.getenv("SUPABASE_KEY", get_database_config().get("supabase", {}).get("key"))

def get_supabase_bucket() -> str:
    """Supabase 버킷 이름 반환 (config reload 지원)."""
    return get_database_config().get("supabase", {}).get("bucket", "skin-images")

def get_max_workers() -> int:
    """최대 워커 수 반환 (config reload 지원)."""
    return int(os.environ.get("SKIN_API_MAX_WORKERS", "4"))

def get_cleanup_interval_h() -> int:
    """정리 간격(시간) 반환 (config reload 지원)."""
    return int(os.environ.get("SKIN_API_CLEANUP_INTERVAL_H", "6"))

def get_max_job_age_h() -> int:
    """Job 최대 보관 시간(시간) 반환 (config reload 지원)."""
    return int(os.environ.get("SKIN_API_MAX_JOB_AGE_H", "24"))

def get_backup_interval_h() -> int:
    """백업 간격(시간) 반환 (config reload 지원)."""
    return int(os.environ.get("SKIN_API_BACKUP_INTERVAL_H", "24"))

def get_backup_dir() -> str:
    """백업 디렉토리 반환 (config reload 지원)."""
    return os.environ.get("SKIN_API_BACKUP_DIR", "backup")

# 하위 호환성을 위한 별칭 (getter 사용 권장)
# [DEPRECATED] 아래 상수들은 모듈 로드 시점에 고정됩니다.
# config reload를 지원하려면 getter 함수를 사용하세요.
# 향후 버전에서는 제거될 수 있습니다.
config = _config_cache
server_config = _server_config_cache
database_config = _database_config_cache
sqlite_config = _sqlite_config_cache
supabase_config = _supabase_config_cache
jwt_config = _jwt_config_cache
environment = _environment_cache
SECRET_KEY = _SECRET_KEY  # [DEPRECATED] get_secret_key() 사용 권장
ALGORITHM = _ALGORITHM  # [DEPRECATED] get_algorithm() 사용 권장
ACCESS_TOKEN_EXPIRE_MINUTES = _ACCESS_TOKEN_EXPIRE_MINUTES  # [DEPRECATED] get_access_token_expire_minutes() 사용 권장
SERVER_HOST = _SERVER_HOST  # [DEPRECATED] get_server_host() 사용 권장
SERVER_PORT = _SERVER_PORT  # [DEPRECATED] get_server_port() 사용 권장
SERVER_URL = _SERVER_URL  # [DEPRECATED] get_server_url() 사용 권장
ALLOWED_EXT = _ALLOWED_EXT  # [DEPRECATED] get_allowed_extensions() 사용 권장
MAX_UPLOAD_BYTES = _MAX_UPLOAD_BYTES  # [DEPRECATED] get_max_upload_bytes() 사용 권장
ALLOWED_ORIGINS = _ALLOWED_ORIGINS  # [DEPRECATED] get_allowed_origins() 사용 권장
MAX_CONCURRENT_JOBS = _MAX_CONCURRENT_JOBS  # [DEPRECATED] get_max_concurrent_jobs() 사용 권장
JOB_SEMAPHORE_TIMEOUT_SEC = _JOB_SEMAPHORE_TIMEOUT_SEC  # [DEPRECATED] get_job_semaphore_timeout_sec() 사용 권장
DEFAULT_DB_PATH = _DEFAULT_DB_PATH  # [DEPRECATED] get_default_db_path() 사용 권장
SUPABASE_ENABLED = _SUPABASE_ENABLED  # [DEPRECATED] get_supabase_enabled() 사용 권장
SUPABASE_URL = _SUPABASE_URL  # [DEPRECATED] get_supabase_url() 사용 권장
SUPABASE_KEY = _SUPABASE_KEY  # [DEPRECATED] get_supabase_key() 사용 권장
SUPABASE_BUCKET = _SUPABASE_BUCKET  # [DEPRECATED] get_supabase_bucket() 사용 권장
MAX_WORKERS = _MAX_WORKERS  # [DEPRECATED] get_max_workers() 사용 권장
CLEANUP_INTERVAL_H = _CLEANUP_INTERVAL_H  # [DEPRECATED] get_cleanup_interval_h() 사용 권장
MAX_JOB_AGE_H = _MAX_JOB_AGE_H  # [DEPRECATED] get_max_job_age_h() 사용 권장
BACKUP_INTERVAL_H = _BACKUP_INTERVAL_H  # [DEPRECATED] get_backup_interval_h() 사용 권장
BACKUP_DIR = _BACKUP_DIR  # [DEPRECATED] get_backup_dir() 사용 권장


# ── JWT 유틸 ───────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=get_access_token_expire_minutes())
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, get_secret_key(), algorithm=get_algorithm())


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, get_secret_key(), algorithms=[get_algorithm()])
    except JWTError:
        return None


async def get_current_customer(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Bearer 토큰 검증 → 페이로드 반환. 토큰 없으면 401."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


async def require_current_customer(
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Bearer 토큰 필수 검증 → 페이로드 반환. 토큰 없으면 401."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def validate_customer_id_match(
    current_customer: Dict[str, Any],
    target_customer_id: str,
) -> None:
    """JWT의 customer_id(sub)와 요청된 customer_id가 일치하는지 검증.
    
    관리자(admin)는 모든 customer_id에 접근 가능.
    분석가(analyst)는 read_all 권한이 있으면 모든 customer_id 조회 가능.
    일반 고객(customer)은 자신의 customer_id만 접근 가능.
    """
    if current_customer is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user_role = current_customer.get("role", "customer")
    jwt_customer_id = current_customer.get("sub")
    
    if user_role == "admin":
        return
    if user_role == "analyst" and "read_all" in ROLES.get(user_role, []):
        return
    if user_role == "customer" and jwt_customer_id == target_customer_id:
        return
    
    raise HTTPException(
        status_code=403,
        detail=f"Access denied: cannot access data for customer_id={target_customer_id}"
    )


def validate_path_within_directory(
    file_path: Path,
    allowed_directory: Path,
) -> None:
    """Path Traversal 방지: file_path가 allowed_directory 내에 있는지 검증.
    
    Python 3.9+의 Path.is_relative_to()를 사용하여 안전한 경로 검증 수행.
    """
    resolved_file_path = file_path.resolve()
    resolved_allowed_dir = allowed_directory.resolve()
    
    if not resolved_file_path.is_relative_to(resolved_allowed_dir):
        raise HTTPException(
            status_code=400,
            detail="invalid filename: path traversal detected"
        )


# ── 권한 헬퍼 ─────────────────────────────────────────────────────────────

def check_customer_access(
    current_customer_id: Optional[str],
    target_customer_id: Optional[str],
    user_role: str,
) -> bool:
    if user_role == "admin":
        return True
    if user_role == "analyst" and "read_all" in ROLES.get(user_role, []):
        return True
    if user_role == "customer" and current_customer_id == target_customer_id:
        return True
    return False


def filter_sensitive_data(data: Dict[str, Any], user_role: str) -> Dict[str, Any]:
    if user_role == "admin":
        return data
    filtered = data.copy()
    for field in SENSITIVE_FIELDS:
        if field in filtered:
            filtered[field] = "***REDACTED***" if isinstance(filtered[field], str) else filtered.pop(field, None)
    return filtered


def require_roles(*roles: str):
    """엔드포인트 내에서 역할을 강제하는 헬퍼.

    Usage::

        user_role = require_roles("admin", "analyst")(current_customer)
    """
    def _check(current_customer: Optional[Dict[str, Any]]) -> str:
        if current_customer is None:
            raise HTTPException(status_code=401, detail="인증이 필요합니다.")
        role = current_customer.get("role", "customer")
        if role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"권한 없음: {', '.join(roles)} 역할이 필요합니다.",
            )
        return role
    return _check


# ── 감사 로그 ──────────────────────────────────────────────────────────────

def log_audit(
    db: ExecutionHistoryDB,
    actor_customer_id: Optional[str],
    target_customer_id: Optional[str],
    endpoint: str,
    method: str,
    user_role: str,
    request: Any,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    ip_address  = request.client.host if (request and request.client) else None
    user_agent  = request.headers.get("user-agent") if request else None
    db.record_audit_log(
        actor_customer_id=actor_customer_id,
        target_customer_id=target_customer_id,
        endpoint=endpoint,
        method=method,
        user_role=user_role,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        error_message=error_message,
    )


# ── Job 파일시스템 유틸 ────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(name: str) -> str:
    """안전한 파일명 생성 (Path Traversal 취약점 방지)

    Path Traversal 공격 방지를 위해 경로 순회 문자열 제거 후
    os.path.basename을 적용합니다. 허용되지 않는 확장자는 .jpg로 대체합니다.
    """
    # Path Traversal 방지: 경로 순회 문자열 제거
    name = name.replace("..", "").replace("/", "").replace("\\", "")

    # basename 적용 (이중 보호)
    name = os.path.basename(name)

    # 확장자 추출 및 검증
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    allowed = get_allowed_extensions()
    if ext not in allowed:
        ext = ".jpg"

    # 파일명 정제 (영문, 숫자, 하이픈, 언더스코어만 허용)
    stem = re.sub(r"[^\w\-]", "_", stem)[:64]

    return f"{stem or 'upload'}{ext}"


def jobs_root() -> Path:
    return Path(os.environ.get("SKIN_API_JOBS_DIR", "./runtime/results/api_jobs")).resolve()


def job_dir(job_id: str) -> Path:
    return jobs_root() / job_id


def job_meta_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def write_job_meta(job_id: str, meta: Dict[str, Any]) -> None:
    p = job_meta_path(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def read_job_meta(job_id: str) -> Dict[str, Any]:
    p = job_meta_path(job_id)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(job_id)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


# ── SSRF 방어 ─────────────────────────────────────────────────────────────

def is_ssrf_blocked_host(host: str) -> bool:
    """SSRF 방어 - 내부망/루프백/링크로컬/예약 주소 차단.
    
    [FIX 2026-05-24] 도메인명 DNS 해석 후 IP 검증 추가.
    localhost, 클라우드 메타데이터 도메인 차단.
    """
    import socket
    
    # IP 직접 검사
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        pass
    
    # 도메인명 블록리스트
    blocked_domains = {"localhost", "metadata.google.internal", "metadata.azure.internal"}
    if host.lower() in blocked_domains:
        return True
    
    # 도메인 → 모든 IP 해석 후 검사
    try:
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                    return True
            except ValueError:
                continue
    except (socket.gaierror, socket.timeout, OSError):
        # DNS 해석 실패 시 차단 (안전 기본값)
        return True
    
    return False


def download_image_to(url: str, output_path: Path) -> None:
    """원격 URL 이미지를 output_path 에 저장 (SSRF 방어 포함)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("image_url must start with http:// or https://")
    host = parsed.hostname or ""
    if is_ssrf_blocked_host(host):
        raise ValueError(
            f"image_url 호스트({host!r})는 허용되지 않습니다: "
            "내부망·루프백·링크로컬 주소는 사용할 수 없습니다."
        )
    timeout_s = float(os.environ.get("SKIN_API_URL_TIMEOUT", "10"))
    max_bytes = int(os.environ.get("SKIN_API_URL_MAX_BYTES", str(10 * 1024 * 1024)))
    req = UrlRequest(url, headers={"User-Agent": "skin-analysis/3.0"})
    with urlopen(req, timeout=timeout_s) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if content_type and "image/" not in content_type:
            raise ValueError(f"image_url content-type is not image/*: {content_type}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with open(output_path, "wb") as f:
            while chunk := resp.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"image_url is too large (max {max_bytes} bytes)")
                f.write(chunk)


# ── 활성 Job 카운터 (health monitor 용) ───────────────────────────────────

def increment_active_jobs() -> None:
    global _active_jobs_count
    with _active_jobs_lock:
        _active_jobs_count += 1


def decrement_active_jobs() -> None:
    global _active_jobs_count
    with _active_jobs_lock:
        _active_jobs_count -= 1


def get_active_jobs_count() -> int:
    global _active_jobs_count
    with _active_jobs_lock:
        return _active_jobs_count


# ── DB Dependency ───────────────────────────────────────────────────────────

def get_db() -> ExecutionHistoryDB:
    """FastAPI Dependency for ExecutionHistoryDB."""
    return ExecutionHistoryDB(get_db_path_from_env())


# ── Shared Executor ──────────────────────────────────────────────────────────

_shared_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_shared_executor() -> ThreadPoolExecutor:
    """공유 ThreadPoolExecutor 반환 (싱글톤)."""
    global _shared_executor
    with _executor_lock:
        if _shared_executor is None:
            _shared_executor = ThreadPoolExecutor(max_workers=1)
        return _shared_executor


# ── Main Event Loop (ThreadPool에서 WebSocket 전달용) ───────────────────────

_main_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_lock = threading.Lock()


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """메인 이벤트 루프 설정 (server.py lifespan에서 호출)."""
    global _main_loop
    with _loop_lock:
        _main_loop = loop


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """메인 이벤트 루프 반환."""
    global _main_loop
    with _loop_lock:
        return _main_loop
