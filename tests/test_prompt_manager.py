"""
PromptManager 단위 테스트 - 프롬프트 로드, 버전 관리, A/B 테스트
"""
import tempfile
import pytest
from pathlib import Path


class TestPromptManager:
    """PromptManager 테스트"""

    def test_singleton_pattern(self):
        """싱글톤 패턴 확인"""
        from src.llm.prompt_manager import PromptManager
        
        instance1 = PromptManager.get_instance()
        instance2 = PromptManager.get_instance()
        assert instance1 is instance2

    def test_get_prompt_file_not_found(self):
        """프롬프트 파일 없음 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        pm = PromptManager.get_instance()
        prompt = pm.get_prompt("nonexistent", version="v1")
        
        assert prompt == ""

    def test_get_prompt_from_template(self):
        """템플릿 변수 치환 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 임시 프롬프트 파일 생성
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            prompt_file = Path(tmpdir) / "test_v1.md"
            prompt_file.write_text("Hello {name}, your score is {score}.")
            
            # 템플릿 변수 치환
            result = pm.get_prompt_from_template(
                "test",
                variables={"name": "John", "score": "85"},
                version="v1",
            )
            
            assert result == "Hello John, your score is 85."

    def test_list_available_versions(self):
        """사용 가능한 버전 나열 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            # 여러 버전 파일 생성
            (Path(tmpdir) / "test_v1.md").touch()
            (Path(tmpdir) / "test_v2.md").touch()
            (Path(tmpdir) / "test_v3.md").touch()
            
            versions = pm.list_available_versions("test")
            
            assert "v1" in versions
            assert "v2" in versions
            assert "v3" in versions

    def test_get_latest_version(self):
        """최신 버전 반환 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            # 여러 버전 파일 생성
            (Path(tmpdir) / "test_v1.md").touch()
            (Path(tmpdir) / "test_v2.md").touch()
            (Path(tmpdir) / "test_v3.md").touch()
            
            latest = pm.get_latest_version("test")
            
            assert latest == "v3"

    def test_get_latest_version_no_versions(self):
        """버전 없을 때 기본값 반환 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            latest = pm.get_latest_version("nonexistent")
            
            assert latest == "v1"

    def test_cache_mechanism(self):
        """캐싱 메커니즘 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            prompt_file = Path(tmpdir) / "test_v1.md"
            prompt_file.write_text("Test prompt")
            
            # 첫 번째 로드
            prompt1 = pm.get_prompt("test", version="v1", use_cache=True)
            
            # 두 번째 로드 (캐시 사용)
            prompt2 = pm.get_prompt("test", version="v1", use_cache=True)
            
            assert prompt1 == prompt2
            assert "test_v1" in pm._prompt_cache

    def test_clear_cache(self):
        """캐시 초기화 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            prompt_file = Path(tmpdir) / "test_v1.md"
            prompt_file.write_text("Test prompt")
            
            # 프롬프트 로드
            pm.get_prompt("test", version="v1", use_cache=True)
            assert len(pm._prompt_cache) > 0
            
            # 캐시 초기화
            pm.clear_cache()
            assert len(pm._prompt_cache) == 0

    def test_reload_prompt(self):
        """프롬프트 재로드 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            prompt_file = Path(tmpdir) / "test_v1.md"
            prompt_file.write_text("Original prompt")
            
            # 프롬프트 로드
            pm.get_prompt("test", version="v1", use_cache=True)
            
            # 파일 수정
            prompt_file.write_text("Updated prompt")
            
            # 재로드 전
            cached = pm.get_prompt("test", version="v1", use_cache=True)
            assert cached == "Original prompt"
            
            # 재로드
            pm.reload_prompt("test", version="v1")
            
            # 재로드 후
            reloaded = pm.get_prompt("test", version="v1", use_cache=True)
            assert reloaded == "Updated prompt"

    def test_get_ab_test_prompt(self):
        """A/B 테스트 프롬프트 테스트"""
        from src.llm.prompt_manager import PromptManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PromptManager.__new__(PromptManager)
            pm._initialized = True
            pm._prompts_dir = Path(tmpdir)
            pm._prompt_cache = {}
            
            # A/B 변형 파일 생성
            (Path(tmpdir) / "test_A_v1.md").write_text("Variant A")
            (Path(tmpdir) / "test_B_v1.md").write_text("Variant B")
            
            # A 변형
            prompt_a = pm.get_ab_test_prompt("test", variant="A", version="v1")
            assert prompt_a == "Variant A"
            
            # B 변형
            prompt_b = pm.get_ab_test_prompt("test", variant="B", version="v1")
            assert prompt_b == "Variant B"
