"""routers 패키지 — 도메인별 APIRouter 모음."""
from src.server.routers import jobs, logs, stats, auth, customer, admin

__all__ = ["jobs", "logs", "stats", "auth", "customer", "admin"]
