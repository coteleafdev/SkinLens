"""
test_restoration_registry.py — 복원 레지스트리 단위 테스트

RestorerRegistry 테스트
"""
import pytest
from src.restoration.base import BaseRestorer
from src.restoration.registry import RestorerRegistry


class TestRestorer1(BaseRestorer):
    """테스트용 복원 클래스 1"""
    
    def restore(self, input_path, output_path, **kwargs):
        return {"output_path": str(output_path)}
    
    def get_name(self):
        return "TestRestorer1"
    
    def get_version(self):
        return "1.0.0"


class TestRestorer2(BaseRestorer):
    """테스트용 복원 클래스 2"""
    
    def restore(self, input_path, output_path, **kwargs):
        return {"output_path": str(output_path)}
    
    def get_name(self):
        return "TestRestorer2"
    
    def get_version(self):
        return "2.0.0"


class TestRestorerRegistry:
    """RestorerRegistry 테스트"""
    
    def setup_method(self):
        """각 테스트 전 레지스트리 초기화"""
        RestorerRegistry.clear()
    
    def teardown_method(self):
        """각 테스트 후 레지스트리 초기화"""
        RestorerRegistry.clear()
    
    def test_singleton(self):
        """싱글톤 패턴 테스트"""
        registry1 = RestorerRegistry()
        registry2 = RestorerRegistry()
        
        assert registry1 is registry2
    
    def test_register(self):
        """복원 백엔드 등록 테스트"""
        @RestorerRegistry.register("test1")
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        assert "test1" in RestorerRegistry._restorers
        assert RestorerRegistry._restorers["test1"] == TestRestorer
    
    def test_register_with_aliases(self):
        """별칭 포함 등록 테스트"""
        @RestorerRegistry.register("test1", aliases=["t1", "test"])
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        assert "test1" in RestorerRegistry._restorers
        assert "t1" in RestorerRegistry._aliases
        assert "test" in RestorerRegistry._aliases
        assert RestorerRegistry._aliases["t1"] == "test1"
        assert RestorerRegistry._aliases["test"] == "test1"
    
    def test_register_with_metadata(self):
        """메타데이터 포함 등록 테스트"""
        metadata = {"version": "1.0.0", "devices": ["cuda", "cpu"]}
        
        @RestorerRegistry.register("test1", metadata=metadata)
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        assert RestorerRegistry._metadata["test1"] == metadata
    
    def test_register_invalid_class(self):
        """잘못된 클래스 등록 테스트"""
        with pytest.raises(TypeError, match="BaseRestorer를 상속받아야 합니다"):
            @RestorerRegistry.register("invalid")
            class InvalidClass:
                pass
    
    def test_register_duplicate_same_class(self):
        """동일 클래스 재등록 테스트"""
        @RestorerRegistry.register("test1")
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        # 동일 클래스로 재등록 - 무시됨
        @RestorerRegistry.register("test1")
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        # 여전히 하나만 등록됨
        assert len([k for k, v in RestorerRegistry._restorers.items() if k == "test1"]) == 1
    
    def test_get_by_name(self):
        """이름으로 조회 테스트"""
        @RestorerRegistry.register("test1")
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        restorer_class = RestorerRegistry.get("test1")
        assert restorer_class == TestRestorer
    
    def test_get_by_alias(self):
        """별칭으로 조회 테스트"""
        @RestorerRegistry.register("test1", aliases=["t1"])
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        restorer_class = RestorerRegistry.get("t1")
        assert restorer_class == TestRestorer
    
    def test_get_not_found(self):
        """존재하지 않는 엔진 조회 테스트"""
        with pytest.raises(ValueError, match="등록되지 않은"):
            RestorerRegistry.get("nonexistent")
    
    def test_list_available(self):
        """사용 가능한 엔진 목록 테스트"""
        @RestorerRegistry.register("test1")
        class TestRestorer1(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer1"
            
            def get_version(self):
                return "1.0.0"
        
        @RestorerRegistry.register("test2")
        class TestRestorer2(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer2"
            
            def get_version(self):
                return "2.0.0"
        
        available = RestorerRegistry.list_available()
        assert "test1" in available
        assert "test2" in available
    
    def test_create(self):
        """인스턴스 생성 테스트"""
        @RestorerRegistry.register("test1")
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        config = {"repo": "/path/to/repo"}
        restorer = RestorerRegistry.create("test1", config=config)
        
        assert isinstance(restorer, TestRestorer)
        assert restorer.config == config
    
    def test_create_by_alias(self):
        """별칭으로 인스턴스 생성 테스트"""
        @RestorerRegistry.register("test1", aliases=["t1"])
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        restorer = RestorerRegistry.create("t1")
        assert isinstance(restorer, TestRestorer)
    
    def test_create_from_config(self):
        """설정에서 인스턴스 생성 테스트"""
        @RestorerRegistry.register("test1")
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        config = {
            "restorer": "test1",
            "restorer_config": {"repo": "/path/to/repo"}
        }
        restorer = RestorerRegistry.create_from_config(config)
        
        assert isinstance(restorer, TestRestorer)
        assert restorer.config == {"repo": "/path/to/repo"}
    
    def test_create_from_config_default(self):
        """기본 엔진으로 인스턴스 생성 테스트"""
        @RestorerRegistry.register("codeformer_v1")
        class CodeFormerRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "CodeFormer"
            
            def get_version(self):
                return "1.0.0"
        
        config = {}
        restorer = RestorerRegistry.create_from_config(config)
        
        assert isinstance(restorer, CodeFormerRestorer)
    
    def test_get_metadata(self):
        """메타데이터 조회 테스트"""
        metadata = {"version": "1.0.0", "devices": ["cuda", "cpu"]}
        
        @RestorerRegistry.register("test1", metadata=metadata)
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        result = RestorerRegistry.get_metadata("test1")
        assert result == metadata
    
    def test_get_metadata_by_alias(self):
        """별칭으로 메타데이터 조회 테스트"""
        metadata = {"version": "1.0.0"}
        
        @RestorerRegistry.register("test1", aliases=["t1"], metadata=metadata)
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        result = RestorerRegistry.get_metadata("t1")
        assert result == metadata
    
    def test_get_metadata_not_found(self):
        """존재하지 않는 엔진 메타데이터 조회 테스트"""
        result = RestorerRegistry.get_metadata("nonexistent")
        assert result == {}
    
    def test_clear(self):
        """레지스트리 초기화 테스트"""
        @RestorerRegistry.register("test1")
        class TestRestorer(BaseRestorer):
            def restore(self, input_path, output_path, **kwargs):
                return {"output_path": str(output_path)}
            
            def get_name(self):
                return "TestRestorer"
            
            def get_version(self):
                return "1.0.0"
        
        assert len(RestorerRegistry._restorers) > 0
        
        RestorerRegistry.clear()
        
        assert len(RestorerRegistry._restorers) == 0
        assert len(RestorerRegistry._aliases) == 0
        assert len(RestorerRegistry._metadata) == 0
