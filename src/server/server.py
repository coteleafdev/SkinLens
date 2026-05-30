"""
server.py — Skin Analysis API (라우터 분리 버전)

파일 구조:
    src/server/
        deps.py             ← 공유 상수·의존성·유틸 (app 미포함)
        server.py           ← app 생성·미들웨어·라우터 등록 (이 파일)
        routers/
            jobs.py         ← POST/GET /v3/analysis/jobs/*
            logs.py         ← GET /v3/logs/*
            stats.py        ← GET/POST /v3/stats/*
            auth.py         ← POST /v3/auth/login, GET /v3/auth/me
            customer.py     ← GET/DELETE /v3/customer/my/*
            admin.py        ← GET /v3/admin/*, GET /v3/health/db
            orders.py       ← POST/GET /v3/orders/* (주문 관리)
            websocket.py    ← WebSocket 연결
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from src.server.deps import (
    ALLOWED_ORIGINS,
    APP_NAME,
    BACKUP_DIR,
    BACKUP_INTERVAL_H,
    CLEANUP_INTERVAL_H,
    MAX_JOB_AGE_H,
    get_active_jobs_count,
    get_secret_key,
    get_shared_executor,
    jobs_root,
    limiter,
    log,
    read_job_meta,
    set_main_loop,
)
from src.cli.execution_history import ExecutionHistoryDB, setup_db_logging
from src.utils.config import get_db_path_from_env, load_config as _load_config
from src.utils.utils import _load_logging_level
from src.db.skin_analysis_db import SkinAnalysisDB
from src.recovery import RecoveryEngine, HealthMonitor
from src.notification import AlertSystem
from src.i18n import Translator
from src.server.middleware import I18nMiddleware
from src.server.middleware.request_logging import RequestLoggingMiddleware

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

# ── 라우터 임포트 ──────────────────────────────────────────────────────────
from src.server.routers import jobs, logs, stats, auth, customer, admin, websocket, health, orders

# config.json에서 로그 레벨 로드
_log_level = _load_logging_level()
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# DB 로깅 설정 (config.json의 db_logging.enabled 설정에 따름)
setup_db_logging()

log = logging.getLogger(__name__)


# ── 핫 리로드 (config.json 변경 감지) ────────────────────────────────────────

# 환경 변수로 핫 리로드 제어 (기본: 비활성화)
ENABLE_HOT_RELOAD = os.getenv("ENABLE_HOT_RELOAD", "false").lower() in ("true", "1", "yes")

if WATCHDOG_AVAILABLE and ENABLE_HOT_RELOAD:
    class ConfigFileHandler(FileSystemEventHandler):
        """config.json 변경 감지 핸들러."""

        def __init__(self, config_path: Path):
            self.config_path = config_path

        def on_modified(self, event):
            if event.src_path == str(self.config_path):
                log.info("config.json 변경 감지, 캐시 초기화")
                from src.config.config_manager import ConfigManager
                from src.scoring._breakpoints import _clear_breakpoints_cache
                from src.llm.llm_metadata import clear_metadata_cache

                # 캐시 초기화
                ConfigManager._instance = None
                _clear_breakpoints_cache()
                clear_metadata_cache()

                # 로그 레벨 재로드
                new_level = _load_logging_level()
                from src.utils.utils import set_logging_level
                set_logging_level(new_level, force=True)

                log.info("설정 재로드 완료 (로그 레벨: %s)", new_level)

    # config.json 감시 시작
    config_path = Path(__file__).parent.parent.parent / "config" / "config.json"
    if config_path.exists():
        observer = Observer()
        observer.schedule(
            ConfigFileHandler(config_path),
            str(config_path.parent),
            recursive=False
        )
        observer.start()
        log.info("핫 리로드 활성화: %s 감시 중", config_path)
    else:
        log.warning("config.json을 찾을 수 없어 핫 리로드 비활성화")
elif not WATCHDOG_AVAILABLE:
    log.info("watchdog 패키지가 설치되지 않아 핫 리로드 비활성화. pip install watchdog")
else:
    log.info("핫 리로드 비활성화 (ENABLE_HOT_RELOAD=%s). 활성화하려면 환경 변수 설정: ENABLE_HOT_RELOAD=true", ENABLE_HOT_RELOAD)


# ── 백그라운드 태스크 ─────────────────────────────────────────────────────

async def _cleanup_expired_jobs() -> None:
    """만료된 Job 파일 정리 (CLEANUP_INTERVAL_H 마다)."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_H * 3600)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_JOB_AGE_H)
        try:
            for jdir in jobs_root().iterdir():
                meta_path = jdir / "job.json"
                if not meta_path.exists():
                    continue
                try:
                    meta    = read_job_meta(jdir.name)
                    created = datetime.fromisoformat(meta.get("created_at", ""))
                    if created < cutoff and meta.get("status") in ("succeeded", "failed"):
                        shutil.rmtree(jdir, ignore_errors=True)
                        log.info("만료 Job 삭제: %s", jdir.name)
                except Exception as e:
                    log.warning(f"Failed to cleanup job {jdir.name}: {e}", exc_info=True)
        except Exception as e:
            log.warning(f"Cleanup expired jobs failed: {e}", exc_info=True)


async def _auto_backup_task() -> None:
    """DB 자동 백업 (BACKUP_INTERVAL_H 마다).
    
    SQLite WAL 모드에서는 .db, -wal, -shm 파일 모두 백업해야 완전한 백업이 됩니다.
    """
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_H * 3600)
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            eh_db_path  = get_db_path_from_env()
            timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(BACKUP_DIR, f"execution_history_{timestamp}.db")
            
            # WAL 파일 경로
            wal_path = f"{eh_db_path}-wal"
            shm_path = f"{eh_db_path}-shm"
            
            # 메인 DB 파일 백업
            shutil.copy2(eh_db_path, backup_path)
            log.info("DB backup created: %s", backup_path)
            
            # WAL 파일 백업 (존재하는 경우)
            if os.path.exists(wal_path):
                wal_backup_path = f"{backup_path}-wal"
                shutil.copy2(wal_path, wal_backup_path)
                log.info("WAL file backup created: %s", wal_backup_path)
            
            # SHM 파일 백업 (존재하는 경우)
            if os.path.exists(shm_path):
                shm_backup_path = f"{backup_path}-shm"
                shutil.copy2(shm_path, shm_backup_path)
                log.info("SHM file backup created: %s", shm_backup_path)

            cutoff = datetime.now() - timedelta(days=7)
            for fname in os.listdir(BACKUP_DIR):
                fpath = os.path.join(BACKUP_DIR, fname)
                if os.path.isfile(fpath):
                    ftime = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if ftime < cutoff:
                        os.remove(fpath)
                        log.info("Old backup deleted: %s", fname)
        except Exception as e:
            log.error("Auto backup failed: %s", e)


async def _system_health_monitor() -> None:
    """시스템 헬스 DB 기록 (5분마다)."""
    while True:
        try:
            db = ExecutionHistoryDB(get_db_path_from_env())
            db.record_system_health(
                active_jobs=get_active_jobs_count(),
                queue_size=0,
                network_status="ok",
            )
            log.info("시스템 헬스 기록 완료 (active_jobs=%d)", get_active_jobs_count())
        except Exception as e:
            log.warning("시스템 헬스 기록 실패: %s", e)
        await asyncio.sleep(300)


# ── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    if get_secret_key() == "your-secret-key-change-in-production":
        raise RuntimeError(
            "JWT_SECRET_KEY 환경변수가 기본값입니다. "
            "프로덕션 환경에서는 반드시 고유한 시크릿 키를 설정해야 합니다."
        )
    # 캐시 초기화 - config.json 변경 반영
    from src.scoring._breakpoints import _clear_breakpoints_cache
    from src.llm.llm_metadata import clear_metadata_cache
    _clear_breakpoints_cache()
    clear_metadata_cache()
    log.info("메타데이터 캐시 초기화 완료")
    
    # 메인 이벤트 루프 저장 (ThreadPool에서 WebSocket 전달용)
    main_loop = asyncio.get_running_loop()
    set_main_loop(main_loop)
    asyncio.create_task(_cleanup_expired_jobs())
    asyncio.create_task(_system_health_monitor())
    asyncio.create_task(_auto_backup_task())

    # 자동 복구 엔진 초기화
    db = SkinAnalysisDB(db_path="results/skin_analysis.db")
    alert_system = AlertSystem()
    recovery_engine = RecoveryEngine(db, alert_system)
    health_monitor = HealthMonitor(recovery_engine)
    asyncio.create_task(health_monitor.start_monitoring())
    log.info("자동 복구 엔진 시작 완료")

    # 공유 executor 초기화
    executor = get_shared_executor()
    log.info("서버 시작 완료 (%s)", APP_NAME)

    yield

    # shutdown
    log.info("서버 종료 중 - 실행 중인 job 완료 대기...")
    health_monitor.stop_monitoring()
    executor.shutdown(wait=True, cancel_futures=False)
    log.info("모든 job 완료, 서버 종료")


# ── FastAPI 앱 ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Skin Analysis API",
    version="3.1",
    description="CÔTELEAF AI 피부 분석 서버 (라우터 분리 버전)",
    lifespan=lifespan,
)

# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# I18n Middleware
translator = Translator()
app.add_middleware(I18nMiddleware, translator=translator)

# Request Logging Middleware (config.json에서 설정 로드)
server_config = _load_config().get("server", {})
request_logging_config = server_config.get("request_logging", {})
slow_request_threshold = request_logging_config.get("slow_request_threshold", 5.0)
if request_logging_config.get("enabled", True):
    app.add_middleware(RequestLoggingMiddleware, slow_request_threshold=slow_request_threshold)
    log.info("요청 로깅 미들웨어 활성화 (느린 요청 기준: %.1fs)", slow_request_threshold)
else:
    log.info("요청 로깅 미들웨어 비활성화")

# ── 라우터 등록 ───────────────────────────────────────────────────────────
app.include_router(jobs.router)
app.include_router(logs.router)
app.include_router(stats.router)
app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(admin.router)
app.include_router(orders.router)
app.include_router(websocket.router)
app.include_router(health.router)


# ── 직접 실행 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
