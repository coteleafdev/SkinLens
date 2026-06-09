"""
middleware/ip_filter.py — IP 화이트리스트/블랙리스트 미들웨어

기능:
- IP 화이트리스트 (허용된 IP만 접근)
- IP 블랙리스트 (차단된 IP 접근 금지)
- 프록시 환경에서 실제 IP 추출 (X-Forwarded-For, X-Real-IP)
"""
import logging
from typing import Optional, List
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

log = logging.getLogger(__name__)


class IPFilterMiddleware(BaseHTTPMiddleware):
    """IP 필터링 미들웨어"""

    def __init__(
        self,
        app: ASGIApp,
        whitelist: Optional[List[str]] = None,
        blacklist: Optional[List[str]] = None,
        trust_proxy: bool = False,
    ):
        """
        Args:
            app: ASGI 애플리케이션
            whitelist: 허용된 IP 목록 (CIDR 또는 개별 IP)
            blacklist: 차단된 IP 목록 (CIDR 또는 개별 IP)
            trust_proxy: 프록시 신뢰 여부 (X-Forwarded-For 헤더 사용)
        """
        super().__init__(app)
        self.whitelist = whitelist or []
        self.blacklist = blacklist or []
        self.trust_proxy = trust_proxy

    async def dispatch(self, request: Request, call_next):
        # 클라이언트 IP 추출
        client_ip = self._get_client_ip(request)

        # 블랙리스트 확인
        if self._is_ip_blocked(client_ip):
            log.warning("블랙리스트 IP 접근 차단: ip=%s, path=%s", client_ip, request.url.path)
            raise HTTPException(status_code=403, detail="IP address is blocked")

        # 화이트리스트 확인
        if self.whitelist and not self._is_ip_allowed(client_ip):
            log.warning("화이트리스트에 없는 IP 접근 차단: ip=%s, path=%s", client_ip, request.url.path)
            raise HTTPException(status_code=403, detail="IP address is not allowed")

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 추출"""
        if self.trust_proxy:
            # X-Forwarded-For 헤더 확인 (프록시 환경)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # 첫 번째 IP가 실제 클라이언트 IP
                return forwarded_for.split(",")[0].strip()

            # X-Real-IP 헤더 확인
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip

        # 직접 연결 IP
        return request.client.host if request.client else "unknown"

    def _is_ip_blocked(self, ip: str) -> bool:
        """IP가 블랙리스트에 있는지 확인"""
        return self._match_ip_list(ip, self.blacklist)

    def _is_ip_allowed(self, ip: str) -> bool:
        """IP가 화이트리스트에 있는지 확인"""
        return self._match_ip_list(ip, self.whitelist)

    def _match_ip_list(self, ip: str, ip_list: List[str]) -> bool:
        """IP가 목록에 있는지 확인 (CIDR 지원)"""
        for pattern in ip_list:
            if self._match_ip_pattern(ip, pattern):
                return True
        return False

    def _match_ip_pattern(self, ip: str, pattern: str) -> bool:
        """IP 패턴 매칭 (CIDR 지원)"""
        if "/" in pattern:
            # CIDR 표기법
            return self._match_cidr(ip, pattern)
        else:
            # 개별 IP
            return ip == pattern

    def _match_cidr(self, ip: str, cidr: str) -> bool:
        """CIDR 매칭"""
        try:
            import ipaddress
            network = ipaddress.ip_network(cidr, strict=False)
            addr = ipaddress.ip_address(ip)
            return addr in network
        except (ValueError, ipaddress.AddressValueError):
            log.warning("잘못된 CIDR 표기법: %s", cidr)
            return False
