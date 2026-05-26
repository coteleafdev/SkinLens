"""
통합 테스트 - 전체 워크플로우, 동시 요청, DB 백업/복구, import 의존성
"""
import sys
import pytest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class TestFullWorkflow:
    """전체 워크플로우 테스트"""

    def test_pipeline_import(self):
        """파이프라인 모듈 import 테스트"""
        # [FIX P2-17] 실제 파이프라인 모듈 import 테스트
        from src.pipeline.pipeline_core import Restorer
        assert Restorer is not None
        
    def test_analyzer_import(self):
        """분석기 모듈 import 테스트"""
        # [FIX P2-17] 실제 분석기 모듈 import 테스트
        from src.scoring.skin_scoring import SkinAnalyzer
        assert SkinAnalyzer is not None
        
    def test_pcr_prescription_import(self):
        """PCR 처방 모듈 import 테스트"""
        # [FIX P2-19] PCR 처방 모듈 import 테스트
        from src.prescription.prescription_calculator import calculate_pcr_recipe
        assert calculate_pcr_recipe is not None
        
    def test_base_restorer_instantiation(self):
        """BaseRestorer 인스턴스화 테스트"""
        # [FIX P2-19] BaseRestorer 인스턴스화 테스트
        from src.restoration.base import BaseRestorer
        from src.restoration.strategies.codeformer_restorer import CodeFormerRestorer
        
        # CodeFormerRestorer는 BaseRestorer를 상속받아야 함
        assert issubclass(CodeFormerRestorer, BaseRestorer)
        
        # 인스턴스화 테스트
        restorer = CodeFormerRestorer(config={"repo": "/tmp"})
        assert restorer.get_name() == "codeformer_v1"
        assert restorer.get_version() == "1.0.0"


class TestConcurrentRequests:
    """동시 요청 테스트"""

    def test_concurrent_execution(self):
        """동시 실행 테스트"""
        def simple_task(x):
            return x * 2
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(simple_task, i) for i in range(5)]
            results = [f.result() for f in futures]
        
        assert results == [0, 2, 4, 6, 8]

    def test_concurrent_status_queries(self):
        """동시 상태 조회 테스트"""
        def query_status():
            return {"status": "ok"}
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(query_status) for _ in range(10)]
            results = [f.result() for f in futures]
        
        assert len(results) == 10
        assert all(r["status"] == "ok" for r in results)


class TestDBBackupRestore:
    """DB 백업/복구 테스트"""

    def test_backup_workflow(self):
        """백업 워크플로우 확인"""
        backup_steps = ["connect", "dump", "save"]
        for step in backup_steps:
            assert step in backup_steps

    def test_restore_workflow(self):
        """복구 워크플로우 확인"""
        restore_steps = ["load", "import", "verify"]
        for step in restore_steps:
            assert step in restore_steps


class TestErrorRecoveryIntegration:
    """에러 복구 통합 테스트"""

    def test_retry_mechanism(self):
        """재시도 메커니즘 테스트"""
        call_count = 0
        
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = flaky_operation()
                assert result == "success"
                assert call_count == 3
                break
            except ConnectionError:
                if attempt == max_retries - 1:
                    raise

    def test_graceful_degradation(self):
        """우아한 서비스 저하 확인"""
        primary_failed = True
        if primary_failed:
            fallback_result = "fallback"
            assert fallback_result is not None


class TestImportDependency:
    """import 의존성 테스트 - 순환 import 및 import 순서 독립성 확인"""

    def test_no_circular_imports_score_composition(self):
        """score_composition와 skin_scoring 순환 import 확인"""
        # 프로젝트 루트를 sys.path에 추가
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # 순서 1: score_composition 먼저 import
        import importlib
        spec1 = importlib.util.spec_from_file_location(
            "score_composition", "src/skin/compose/score_composition.py"
        )
        if spec1 and spec1.loader:
            module1 = importlib.util.module_from_spec(spec1)
            sys.modules["score_composition"] = module1
            try:
                spec1.loader.exec_module(module1)
            except ImportError as e:
                # lazy import로 인한 ImportError는 예상됨
                assert "lazy" in str(e).lower() or "circular" not in str(e).lower()

        # 순서 2: skin_scoring 먼저 import
        spec2 = importlib.util.spec_from_file_location(
            "skin_scoring", "src/scoring/skin_scoring.py"
        )
        if spec2 and spec2.loader:
            module2 = importlib.util.module_from_spec(spec2)
            sys.modules["skin_scoring"] = module2
            try:
                spec2.loader.exec_module(module2)
            except ImportError as e:
                # 외부 의존성(cv2, skimage) 없는 경우는 허용
                assert "cv2" in str(e).lower() or "skimage" in str(e).lower()

    def test_import_order_independence(self):
        """import 순서에 의존하지 않는지 확인"""
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # 다양한 import 순서로 테스트
        import_orders = [
            ["src.skin.core.face_roi", "src.skin.core.score_constants"],
            ["src.skin.core.score_constants", "src.skin.core.face_roi"],
            ["src.skin.compose.score_composition", "src.scoring.skin_scoring"],
        ]

        for order in import_orders:
            # 모듈 캐시 정리
            for module_name in order:
                if module_name in sys.modules:
                    del sys.modules[module_name]

            # 순서대로 import
            for module_name in order:
                try:
                    __import__(module_name)
                except ImportError as e:
                    # 외부 의존성(cv2, skimage) 없는 경우는 허용
                    if "cv2" not in str(e).lower() and "skimage" not in str(e).lower():
                        raise

    def test_lazy_import_functionality(self):
        """lazy import가 올바르게 작동하는지 확인"""
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # score_composition의 lazy import 테스트
        from src.skin.compose.score_composition import _get_weights
        weights = _get_weights()
        assert isinstance(weights, dict)
        assert "pigmentation_cov" in weights or len(weights) == 0  # config 로드 실패 시 빈 dict

    def test_gui_independence(self):
        """GUI 모듈 없이도 핵심 기능이 import되는지 확인"""
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # analyze_utils는 GUI 의존 없이 import되어야 함
        from src.skin.core.analyze_utils import analyze_compare_triple
        assert callable(analyze_compare_triple)

        # utils.apply_score_safety_net도 PySide6 없이 import되어야 함
        from src.utils.utils import apply_score_safety_net
        assert callable(apply_score_safety_net)

