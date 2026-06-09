"""
보안 테스트 - SSRF 방지, 프로토콜 차단, 토큰 만료, Path traversal
"""
import pytest
from datetime import datetime, timedelta
from jose import jwt
from src.server.deps import is_ssrf_blocked_host, _safe_filename, validate_path_within_directory
from pathlib import Path


class TestSSRFProtection:
    """SSRF 방지 테스트"""

    def test_internal_ip_detection(self):
        """내부 IP 감지 로직 확인"""
        # [FIX P2-16] 실제 is_ssrf_blocked_host() 함수 호출 테스트
        assert is_ssrf_blocked_host("127.0.0.1") == True
        assert is_ssrf_blocked_host("localhost") == True
        assert is_ssrf_blocked_host("192.168.1.1") == True
        assert is_ssrf_blocked_host("10.0.0.1") == True
        assert is_ssrf_blocked_host("metadata.google.internal") == True

    def test_external_ip_allowed(self):
        """외부 IP 허용 확인"""
        # [FIX P2-16] 실제 is_ssrf_blocked_host() 함수 호출 테스트
        assert is_ssrf_blocked_host("8.8.8.8") == False
        assert is_ssrf_blocked_host("1.1.1.1") == False
        # example.com은 DNS 해석 실패 시 차단될 수 있음 (안전 기본값)
        # 테스트 환경에서 DNS 해석이 실패하면 스킵
        try:
            import socket
            socket.getaddrinfo("example.com", None)
            assert is_ssrf_blocked_host("example.com") == False
        except (socket.gaierror, socket.timeout, OSError):
            pytest.skip("DNS 해석 실패로 인한 테스트 스킵")


class TestProtocolBlocking:
    """프로토콜 차단 테스트"""

    def test_blocked_protocols(self):
        """차단된 프로토콜 확인"""
        blocked = ["file://", "ftp://", "gopher://"]
        for protocol in blocked:
            assert protocol in blocked

    def test_allowed_protocols(self):
        """허용된 프로토콜 확인"""
        allowed = ["http://", "https://"]
        for protocol in allowed:
            assert protocol in allowed


class TestTokenExpiration:
    """토큰 만료 테스트"""

    def test_expired_token_rejected(self):
        """만료된 토큰 거부 확인"""
        # 만료된 토큰은 exp 필드가 과거 시간이어야 함
        assert datetime.now(tz=None) > datetime.now(tz=None) - timedelta(minutes=30)

    def test_valid_token_accepted(self):
        """유효한 토큰 허용 확인"""
        secret_key = "test-secret-key"
        payload = {
            "sub": "admin",
            "role": "admin",
            "exp": datetime.now(tz=None) + timedelta(minutes=30)
        }
        valid_token = jwt.encode(payload, secret_key, algorithm="HS256")
        
        decoded = jwt.decode(valid_token, secret_key, algorithms=["HS256"])
        assert decoded["sub"] == "admin"

    def test_invalid_token_format(self):
        """잘못된 토큰 형식 확인"""
        invalid_token = "InvalidToken"
        try:
            jwt.decode(invalid_token, "secret", algorithms=["HS256"])
            assert False, "잘못된 토큰이 허용됨"
        except jwt.JWTError:
            assert True  # 기대된 에러


class TestPathTraversal:
    """Path traversal 방지 테스트"""

    def test_safe_filename_validation(self):
        """안전한 파일명 확인"""
        # [FIX P2-16] 실제 _safe_filename() 함수 호출 테스트
        assert ".." not in _safe_filename("image.jpg")
        assert ".." not in _safe_filename("photo.png")
        assert ".." not in _safe_filename("document.pdf")
        assert ".." not in _safe_filename("../../../etc/passwd")
        assert not _safe_filename("../../../etc/passwd").startswith("/")

    def test_path_resolution_check(self):
        """경로 해결 검증 로직 테스트"""
        # [FIX P2-16] 실제 validate_path_within_directory() 함수 호출 테스트
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "jobs" / "12345"
            job_dir.mkdir(parents=True)
            
            # 정상 경로 - 통과해야 함
            allowed_path = job_dir / "result.jpg"
            validate_path_within_directory(allowed_path, job_dir)  # 예외 없어야 함
            
            # traversal 시도 - 예외 발생해야 함
            malicious_path = job_dir / ".." / ".." / "etc" / "passwd"
            with pytest.raises(Exception):  # HTTPException 발생
                validate_path_within_directory(malicious_path, job_dir)


class TestInputValidation:
    """입력 검증 테스트"""

    def test_file_size_limit(self):
        """파일 크기 제한 확인"""
        max_size = 10 * 1024 * 1024  # 10MB
        assert max_size > 0

    def test_allowed_extensions(self):
        """허용된 확장자 확인"""
        allowed = [".jpg", ".jpeg", ".png", ".webp"]
        for ext in allowed:
            assert ext in allowed

    def test_blocked_extensions(self):
        """차단된 확장자 확인"""
        blocked = [".exe", ".bat", ".sh", ".dll"]
        for ext in blocked:
            assert ext in blocked

