"""
middleware/versioning.py — API 버전 관리 미들웨어

기능:
- 버전별 라우팅 지원
- 폐기된 버전에 대한 경고 헤더
- 버전 호환성 검증
"""
import logging
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

log = logging.getLogger(__name__)


class APIVersionMiddleware(BaseHTTPMiddleware):
    """API 버전 관리 미들웨어"""

    def __init__(
        self,
        app: ASGIApp,
        current_version: str = "v3",
        deprecated_versions: Optional[list[str]] = None,
        sunset_versions: Optional[dict[str, str]] = None,
    ):
        """
        Args:
            app: ASGI 애플리케이션
            current_version: 현재 API 버전
            deprecated_versions: 폐기된 버전 목록
            sunset_versions: 폐기 예정 버전과 일자 {version: date}
        """
        super().__init__(app)
        self.current_version = current_version
        self.deprecated_versions = deprecated_versions or []
        self.sunset_versions = sunset_versions or {}

    async def dispatch(self, request: Request, call_next):
        # 경로에서 버전 추출
        path = request.url.path
        version = self._extract_version(path)

        if version:
            # 폐기된 버전 확인
            if version in self.deprecated_versions:
                log.warning("폐기된 API 버전 사용: version=%s, path=%s", version, path)

            # 폐기 예정 버전 확인
            if version in self.sunset_versions:
                sunset_date = self.sunset_versions[version]
                log.info("폐기 예정 API 버전 사용: version=%s, sunset=%s, path=%s", version, sunset_date, path)

        response: Response = await call_next(request)

        # 응답 헤더에 버전 정보 추가
        if version:
            response.headers["API-Version"] = version

            # 현재 버전이 아닌 경우 경고 헤더 추가
            if version != self.current_version:
                response.headers["API-Current-Version"] = self.current_version

            # 폐기된 버전 경고
            if version in self.deprecated_versions:
                response.headers["Deprecation"] = "true"
                response.headers["Link"] = f'<{request.url.scheme}://{request.url.netloc}/docs>; rel="deprecation"'
                response.headers["Warning"] = f'299 - "API version {version} is deprecated"'

            # 폐기 예정 버전 경고
            if version in self.sunset_versions:
                sunset_date = self.sunset_versions[version]
                response.headers["Sunset"] = sunset_date
                response.headers["Warning"] = f'299 - "API version {version} will be sunset on {sunset_date}"'

        return response

    def _extract_version(self, path: str) -> Optional[str]:
        """경로에서 버전 추출 (예: /v3/analysis -> v3)"""
        parts = path.strip("/").split("/")
        if parts and parts[0].startswith("v"):
            return parts[0]
        return None
