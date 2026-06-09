"""
request_logging.py — 요청 로깅 및 추적 미들웨어

기능:
- 모든 API 요청 로깅 (IP, User-Agent, 응답 시간, 상태 코드)
- 요청 ID 생성 및 추적
- 느린 요청 감지 및 경고
"""
import logging
import time
import uuid
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """요청 로깅 및 추적 미들웨어"""

    def __init__(self, app, slow_request_threshold: float = 5.0):
        """
        Args:
            app: ASGI 애플리케이션
            slow_request_threshold: 느린 요청 기준 (초)
        """
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold

    async def dispatch(self, request: Request, call_next):
        # 요청 ID 생성
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # 요청 시작 시간
        start_time = time.time()

        # 클라이언트 정보 추출
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "Unknown")
        method = request.method
        path = request.url.path
        query_params = str(request.query_params) if request.query_params else ""

        # 요청 로깅
        log.info(
            "[REQUEST] id=%s method=%s path=%s query=%s ip=%s user_agent=%s",
            request_id,
            method,
            path,
            query_params,
            client_ip,
            user_agent,
        )

        # 요청 처리
        try:
            response = await call_next(request)
        except (RuntimeError, ValueError, OSError, IOError) as e:  # [FIX P2] 구체적 예외
            # 에러 발생 시 로깅
            processing_time = time.time() - start_time
            log.error(
                "[REQUEST_ERROR] id=%s method=%s path=%s ip=%s error=%s processing_time=%.3fs",
                request_id,
                method,
                path,
                client_ip,
                str(e),
                processing_time,
            )
            raise

        # 응답 시간 계산
        processing_time = time.time() - start_time
        status_code = response.status_code

        # 응답 로깅
        log.info(
            "[RESPONSE] id=%s method=%s path=%s status=%d processing_time=%.3fs ip=%s",
            request_id,
            method,
            path,
            status_code,
            processing_time,
            client_ip,
        )

        # 느린 요청 경고
        if processing_time > self.slow_request_threshold:
            log.warning(
                "[SLOW_REQUEST] id=%s method=%s path=%s processing_time=%.3fs ip=%s",
                request_id,
                method,
                path,
                processing_time,
                client_ip,
            )

        # 요청 ID를 응답 헤더에 추가
        response.headers["X-Request-ID"] = request_id

        return response

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 추출 (프록시 환경 고려)"""
        # X-Forwarded-For 헤더 확인 (프록시/로드밸런서 환경)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # 여러 IP가 쉼표로 구분될 수 있음 (첫 번째가 실제 클라이언트)
            return forwarded_for.split(",")[0].strip()

        # X-Real-IP 헤더 확인 (Nginx 등)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # 직접 연결인 경우
        if request.client:
            return request.client.host

        return "Unknown"
