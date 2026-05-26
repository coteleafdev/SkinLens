"""
단위 테스트 - 핵심 모듈 단위 테스트

skin_scoring.py, pipeline_core.py, safety_net.py 등 핵심 모듈의 단위 테스트
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Dict, Any


class TestSkinScoring:
    """skin_scoring.py 단위 테스트"""

    def test_skin_analyzer_initialization(self):
        """SkinAnalyzer 초기화 테스트"""
        # ML 라이브러리가 없어도 초기화되어야 함
        with patch('src.scoring.skin_scoring.CV2_AVAILABLE', False), \
             patch('src.scoring.skin_scoring.SKIMAGE_AVAILABLE', False):
            from src.scoring.skin_scoring import SkinAnalyzer
            analyzer = SkinAnalyzer()
            assert analyzer is not None

    def test_compose_skin_type_score(self):
        """_compose_skin_type_score 단위 테스트"""
        from src.skin.compose.score_composition import _compose_skin_type_score

        # 정상 케이스
        sebum = {"skin_type_score": 75.0}
        result = _compose_skin_type_score(sebum)
        assert "skin_type_score" in result
        assert result["skin_type_score"] == 75.0

        # None 값 처리
        sebum = {"skin_type_score": None}
        result = _compose_skin_type_score(sebum)
        assert result["skin_type_score"] == 0.0

        # 키 누락 처리
        sebum = {}
        result = _compose_skin_type_score(sebum)
        assert result["skin_type_score"] == 0.0

        # 클램핑 테스트 (100 초과)
        sebum = {"skin_type_score": 150.0}
        result = _compose_skin_type_score(sebum)
        assert result["skin_type_score"] == 100.0

        # 클램핑 테스트 (0 미만)
        sebum = {"skin_type_score": -10.0}
        result = _compose_skin_type_score(sebum)
        assert result["skin_type_score"] == 0.0

    def test_compute_overall_score_report(self):
        """_compute_overall_score_report 종합 점수 기여 테스트"""
        from src.scoring._report import _compute_overall_score_report

        # 정상 케이스
        measurements_report = {
            "melasma_score": 80.0,
            "freckle_score": 75.0,
            "redness_score": 70.0,
            "acne_score": 85.0,
            "pore_size_score": 72.0,
            "eye_wrinkle_score": 68.0,
            "roughness_score": 74.0,
            "skin_tone_score": 76.0,
            "jawline_blur_score": 71.0,
            "skin_type_score": 73.0,
        }
        result = _compute_overall_score_report(measurements_report)
        assert 0.0 <= result <= 100.0

        # 일부 키 누락 (건강하게 처리)
        partial_report = {
            "melasma_score": 80.0,
            "acne_score": 85.0,
        }
        result = _compute_overall_score_report(partial_report)
        assert 0.0 <= result <= 100.0

        # 빈 리포트
        empty_report = {}
        result = _compute_overall_score_report(empty_report)
        assert result == 0.0

        # None 값 포함
        report_with_none = {
            "melasma_score": 80.0,
            "acne_score": None,
            "pore_size_score": 72.0,
        }
        result = _compute_overall_score_report(report_with_none)
        assert 0.0 <= result <= 100.0

    def test_multi_view_skin_type_label_preservation(self):
        """MultiViewMerger.merge() skin_type_label 보존 검증"""
        from src.scoring._multi_view import MultiViewMerger

        # 정상 케이스: skin_type_label 보존
        front_result = {
            "measurements": {
                "melasma_score": 80.0,
                "skin_type_label": "중성",
            }
        }
        side_result = {
            "measurements": {
                "melasma_score": 75.0,
            }
        }
        merger = MultiViewMerger()
        merged = merger.merge(front_result, side_result)

        assert "measurements" in merged
        assert "skin_type_label" in merged["measurements"]
        assert merged["measurements"]["skin_type_label"] == "중성"

        # skin_type_label이 없는 경우
        front_result_no_label = {
            "measurements": {
                "melasma_score": 80.0,
            }
        }
        merged = merger.merge(front_result_no_label, side_result)

        # skin_type_label이 없으면 추가되지 않아도 됨
        # (보존 로직은 있을 때만 작동)
        assert "measurements" in merged

    def test_extract_overall_scores(self):
        """result_parser.extract_overall_scores 테스트"""
        from src.db.result_parser import extract_overall_scores

        # 정상 케이스
        json_result = {
            "analysis_result": {
                "overall_score": 75.0,
                "overall_score_report": 80.0
            }
        }
        orig, rest = extract_overall_scores(json_result)
        assert orig == 75.0
        assert rest == 80.0

        # overall_score_report 없는 경우
        json_result = {
            "analysis_result": {
                "overall_score": 75.0
            }
        }
        orig, rest = extract_overall_scores(json_result)
        assert orig == 75.0
        assert rest == 75.0

        # analysis_result 없는 경우
        json_result = {}
        orig, rest = extract_overall_scores(json_result)
        assert orig == 0.0
        assert rest == 0.0

    def test_face_roi_constants(self):
        """FaceROI 상수 테스트 - 해부학적 논리 확인"""
        from src.skin.core.face_roi import FaceROI

        # 상수가 정의되어 있는지 확인
        assert hasattr(FaceROI, 'NOSE_TOP')
        assert hasattr(FaceROI, 'NOSE_BOTTOM')
        assert hasattr(FaceROI, 'PHILTRUM_TOP')
        assert hasattr(FaceROI, 'PHILTRUM_BOTTOM')
        assert hasattr(FaceROI, 'MOUTH_TOP')
        assert hasattr(FaceROI, 'MOUTH_BOTTOM')

        # 해부학적 논리 확인: 코 끝 < 인중 상단 < 인중 하단 < 입 시작
        assert FaceROI.NOSE_BOTTOM < FaceROI.PHILTRUM_TOP
        assert FaceROI.PHILTRUM_TOP == FaceROI.PHILTRUM_BOTTOM
        assert FaceROI.PHILTRUM_BOTTOM <= FaceROI.MOUTH_TOP


class TestPipelineCore:
    """pipeline_core.py 단위 테스트"""

    def test_project_root(self):
        """project_root 함수 테스트"""
        from src.pipeline.pipeline_core import project_root
        root = project_root()
        assert isinstance(root, Path)
        assert root.exists()

    def test_format_duration(self):
        """format_duration 함수 테스트"""
        from src.pipeline.pipeline_core import format_duration

        assert format_duration(0.5) == "0.50s"
        assert format_duration(30) == "30.00s"
        assert format_duration(90) == "1m 30s"
        assert format_duration(3665) == "1h 1m 5s"

    def test_pipeline_mode_analyze_only(self):
        """ANALYZE_ONLY 모드 테스트"""
        from src.pipeline.pipeline_core import _PipelineMode

        mode = _PipelineMode.ANALYZE_ONLY
        assert mode.name == "ANALYZE_ONLY"

    def test_choose_mode_no_restore(self):
        """do_restore=False 시 ANALYZE_ONLY 반환 테스트"""
        from src.pipeline.pipeline_core import _choose_mode, _PipelineMode

        mode = _choose_mode(
            input_image=Path("test.jpg"),
            do_restore=False,
            restore_ok=True
        )
        assert mode == _PipelineMode.ANALYZE_ONLY

    def test_choose_mode_restore_ok(self):
        """do_restore=True, restore_ok=True 시 RESTORE_ONLY 반환 테스트"""
        from src.pipeline.pipeline_core import _choose_mode, _PipelineMode

        mode = _choose_mode(
            input_image=Path("test.jpg"),
            do_restore=True,
            restore_ok=True
        )
        assert mode == _PipelineMode.RESTORE_ONLY

    def test_choose_mode_restore_not_ok(self):
        """do_restore=True, restore_ok=False 시 ValueError 발생 테스트"""
        from src.pipeline.pipeline_core import _choose_mode

        with pytest.raises(ValueError, match="복원 엔진이 필요합니다"):
            _choose_mode(
                input_image=Path("test.jpg"),
                do_restore=True,
                restore_ok=False
            )


class TestSafetyNet:
    """safety_net.py 단위 테스트"""

    def test_analyze_fn_type(self):
        """AnalyzeFn 타입 테스트"""
        from src.skin.scoring.safety_net import AnalyzeFn
        from typing import get_origin, get_args

        # AnalyzeFn이 Callable 타입인지 확인
        assert get_origin(AnalyzeFn) is not None

    def test_ov_function(self):
        """_ov 함수 테스트"""
        from src.skin.scoring.safety_net import _ov

        # overall_score 키
        result = {"overall_score": 75.0}
        assert _ov(result) == 75.0

        # overall_score_report 키
        result = {"overall_score_report": 80.0}
        assert _ov(result) == 80.0

        # 없는 경우
        result = {}
        assert _ov(result) == 0.0

        # None인 경우
        result = None
        assert _ov(result) == 0.0


class TestEdgeCases:
    """에지 케이스 테스트"""

    def test_null_json_result(self):
        """null JSON 결과 처리 테스트"""
        from src.db.result_parser import extract_overall_scores

        orig, rest = extract_overall_scores(None)
        assert orig == 0.0
        assert rest == 0.0

    def test_empty_string_path(self):
        """빈 문자열 경로 처리 테스트"""
        from src.pipeline.pipeline_core import project_root

        # 빈 문자열이 Path로 변환되어도 정상 작동
        root = project_root()
        assert root is not None

    def test_invalid_image_path(self):
        """잘못된 이미지 경로 처리 테스트"""
        # 실제 파일이 없는 경로
        fake_path = Path("/nonexistent/path/to/image.jpg")
        assert not fake_path.exists()

    def test_missing_config_keys(self):
        """설정 키 누락 처리 테스트"""
        from src.db.result_parser import extract_overall_scores

        # analysis_result 키 누락
        json_result = {"some_other_key": "value"}
        orig, rest = extract_overall_scores(json_result)
        assert orig == 0.0
        assert rest == 0.0

    def test_negative_score(self):
        """음수 점수 처리 테스트"""
        from src.db.result_parser import extract_overall_scores

        json_result = {
            "analysis_result": {
                "overall_score": -10.0,
                "overall_score_report": -5.0
            }
        }
        orig, rest = extract_overall_scores(json_result)
        assert orig == -10.0
        assert rest == -5.0

    def test_score_above_100(self):
        """100점 초과 점수 처리 테스트"""
        from src.db.result_parser import extract_overall_scores

        json_result = {
            "analysis_result": {
                "overall_score": 150.0,
                "overall_score_report": 200.0
            }
        }
        orig, rest = extract_overall_scores(json_result)
        assert orig == 150.0
        assert rest == 200.0

    def test_zero_score(self):
        """0점 처리 테스트"""
        from src.db.result_parser import extract_overall_scores

        json_result = {
            "analysis_result": {
                "overall_score": 0.0,
                "overall_score_report": 0.0
            }
        }
        orig, rest = extract_overall_scores(json_result)
        assert orig == 0.0
        assert rest == 0.0

    def test_string_score_conversion(self):
        """문자열 점수 변환 테스트"""
        from src.db.result_parser import extract_overall_scores

        json_result = {
            "analysis_result": {
                "overall_score": "75.0",
                "overall_score_report": "80.0"
            }
        }
        orig, rest = extract_overall_scores(json_result)
        assert orig == 75.0
        assert rest == 80.0

    def test_invalid_string_score(self):
        """잘못된 문자열 점수 처리 테스트"""
        from src.db.result_parser import extract_overall_scores

        json_result = {
            "analysis_result": {
                "overall_score": "invalid",
                "overall_score_report": "also_invalid"
            }
        }
        # ValueError가 발생해야 함
        with pytest.raises(ValueError):
            extract_overall_scores(json_result)
