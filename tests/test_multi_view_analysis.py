"""
다중 이미지 분석 통합 단위 테스트

Multi-Image Analysis Integration Unit Tests
"""
import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from typing import Dict, Any

from src.scoring._multi_view import MultiViewMerger, analyze_all_multi


class TestMultiViewMerger:
    """MultiViewMerger 단위 테스트"""
    
    def test_angle_weights_initialization(self):
        """각도별 가중치 초기화 테스트"""
        merger = MultiViewMerger()
        
        # 측면 특화 항목 확인
        assert "pore_sagging_score" in merger.ANGLE_WEIGHTS
        assert merger.ANGLE_WEIGHTS["pore_sagging_score"]["front"] == 0.2
        assert merger.ANGLE_WEIGHTS["pore_sagging_score"]["left"] == 0.4
        assert merger.ANGLE_WEIGHTS["pore_sagging_score"]["right"] == 0.4
        
        # 정면 특화 항목 확인
        assert "melasma_score" in merger.ANGLE_WEIGHTS
        assert merger.ANGLE_WEIGHTS["melasma_score"]["front"] == 0.7
        assert merger.ANGLE_WEIGHTS["melasma_score"]["left"] == 0.15
        assert merger.ANGLE_WEIGHTS["melasma_score"]["right"] == 0.15
        
        # 최대값 기반 항목 확인
        assert "acne_score" in merger.ANGLE_WEIGHTS
        assert merger.ANGLE_WEIGHTS["acne_score"]["method"] == "max"
    
    def test_default_weights(self):
        """기본 가중치 테스트"""
        merger = MultiViewMerger()
        
        assert merger.DEFAULT_WEIGHTS["front"] == 0.33
        assert merger.DEFAULT_WEIGHTS["left"] == 0.33
        assert merger.DEFAULT_WEIGHTS["right"] == 0.33
    
    def test_merge_with_full_analysis(self):
        """전체 분석 결과 병합 테스트"""
        merger = MultiViewMerger()
        
        # 내부 점수 (디스플레이 점수 변환 전)
        front_result = {
            "measurements": {
                "eye_wrinkle_score": 50.0,
                "melasma_score": 60.0,
                "acne_score": 40.0,
            }
        }
        
        left_result = {
            "measurements": {
                "eye_wrinkle_score": 70.0,
                "melasma_score": 65.0,
                "acne_score": 50.0,
            }
        }
        
        right_result = {
            "measurements": {
                "eye_wrinkle_score": 65.0,
                "melasma_score": 63.0,
                "acne_score": 45.0,
            }
        }
        
        result = merger.merge(
            front_result,
            left_result=left_result,
            right_result=right_result,
            debug=False
        )
        
        # 병합 결과 확인 (정확한 계산 대신 방법 확인)
        assert "measurements" in result
        assert "eye_wrinkle_score" in result["measurements"]
        assert "melasma_score" in result["measurements"]
        assert "acne_score" in result["measurements"]
        
        # 각도별 결과 포함 확인
        assert "angle_results" in result
        assert "left" in result["angle_results"]
        assert "right" in result["angle_results"]
        
        # 통합 방법 확인
        assert "multi_view_detail" in result
        assert "eye_wrinkle_score" in result["multi_view_detail"]
        assert result["multi_view_detail"]["eye_wrinkle_score"]["method"] == "weighted_average"
    
    def test_merge_with_max_method(self):
        """최대값 기반 통합 테스트"""
        merger = MultiViewMerger()
        
        front_result = {
            "measurements": {
                "acne_score": 30.0,
            }
        }
        
        left_result = {
            "measurements": {
                "acne_score": 50.0,
            }
        }
        
        right_result = {
            "measurements": {
                "acne_score": 45.0,
            }
        }
        
        result = merger.merge(
            front_result,
            left_result=left_result,
            right_result=right_result,
            debug=False
        )
        
        # 여드름: 최대값 기반 통합 확인
        assert result["measurements"]["acne_score"] == 50.0
        
        # 통합 방법 확인
        assert result["multi_view_detail"]["acne_score"]["method"] == "max"
    
    def test_merge_with_lateral_only(self):
        """레거시 측면 분석만 있는 경우 테스트"""
        merger = MultiViewMerger()
        
        front_result = {
            "measurements": {
                "eye_wrinkle_score": 50,
                "cheek_sagging_score": 60,
            }
        }
        
        left_lateral = {
            "eye_wrinkle_lateral": 70,
            "cheek_sagging_lateral": 80,
        }
        
        right_lateral = {
            "eye_wrinkle_lateral": 65,
            "cheek_sagging_lateral": 75,
        }
        
        result = merger.merge(
            front_result,
            left_lateral=left_lateral,
            right_lateral=right_lateral,
            debug=False
        )
        
        # 레거시 병합 로직 확인
        assert result["measurements"]["eye_wrinkle_score"] is not None
        assert result["measurements"]["cheek_sagging_score"] is not None
    
    def test_merge_with_missing_lateral(self):
        """측면 이미지가 없는 경우 테스트"""
        merger = MultiViewMerger()
        
        front_result = {
            "measurements": {
                "eye_wrinkle_score": 50.0,
                "melasma_score": 60.0,
            }
        }
        
        # 측면 결과가 없는 경우
        result = merger.merge(
            front_result,
            left_result=None,
            right_result=None,
            left_lateral=None,
            right_lateral=None,
            debug=False
        )
        
        # 정면만 사용 (변경 없음)
        assert result["measurements"]["eye_wrinkle_score"] == 50.0
        assert result["measurements"]["melasma_score"] == 60.0


class TestAnalyzeAllMulti:
    """analyze_all_multi 함수 단위 테스트"""
    
    @patch('src.scoring._multi_view._SkinAnalyzerCore')
    @patch('src.scoring._multi_view.FaceDetector')
    def test_analyze_all_multi_with_full_analysis(self, mock_detector, mock_analyzer):
        """전체 분석 모드 테스트"""
        # Mock 설정
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_all.return_value = {
            "measurements": {
                "eye_wrinkle_score": 50,
                "melasma_score": 60,
            }
        }
        mock_analyzer.return_value = mock_analyzer_instance
        
        # 테스트
        with patch('src.scoring._multi_view.Path.exists', return_value=True):
            result = analyze_all_multi(
                front_path="front.jpg",
                left45_path="left.jpg",
                right45_path="right.jpg",
                use_full_analysis=True,
                debug=False
            )
        
        # 전체 분석이 호출되었는지 확인
        assert mock_analyzer_instance.analyze_all.call_count == 3
    
    @patch('src.scoring._multi_view._SkinAnalyzerCore')
    @patch('src.scoring._multi_view.FaceDetector')
    @patch('src.scoring._multi_view.LateralFaceAnalyzer')
    def test_analyze_all_multi_legacy_mode(self, mock_lat_analyzer, mock_detector, mock_analyzer):
        """레거시 모드 테스트"""
        # Mock 설정
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_all.return_value = {
            "measurements": {
                "eye_wrinkle_score": 50,
            }
        }
        mock_analyzer.return_value = mock_analyzer_instance
        
        mock_lat_instance = Mock()
        mock_lat_instance.analyze_lateral.return_value = {
            "eye_wrinkle_lateral": 70,
            "nasolabial_lateral": 60,
            "cheek_sagging_lateral": 80,
            "jawline_lateral": 70,
        }
        mock_lat_analyzer.return_value = mock_lat_instance
        
        # 테스트
        with patch('src.scoring._multi_view.Path.exists', return_value=True):
            result = analyze_all_multi(
                front_path="front.jpg",
                left45_path="left.jpg",
                right45_path="right.jpg",
                use_full_analysis=False,
                debug=False
            )
        
        # 정면 분석만 호출되었는지 확인
        assert mock_analyzer_instance.analyze_all.call_count == 1
        # 측면 분석이 호출되었는지 확인
        assert mock_lat_instance.analyze_lateral.call_count == 2


class TestIntegrationWeights:
    """각도별 가중치 통합 테스트"""
    
    def test_lateral_dominant_weights(self):
        """측면 우세 가중치 테스트"""
        merger = MultiViewMerger()
        
        # 측면 특화 항목
        lateral_dominant = [
            "pore_sagging_score",
            "eye_wrinkle_score",
            "jawline_blur_score",
            "cheek_sagging_score",
        ]
        
        for metric in lateral_dominant:
            weights = merger.ANGLE_WEIGHTS[metric]
            assert weights["front"] == 0.2
            assert weights["left"] == 0.4
            assert weights["right"] == 0.4
            assert weights["front"] < weights["left"]
            assert weights["front"] < weights["right"]
    
    def test_front_dominant_weights(self):
        """정면 우세 가중치 테스트"""
        merger = MultiViewMerger()
        
        # 정면 특화 항목
        front_dominant = [
            "melasma_score",
            "redness_score",
            "skin_tone_score",
            "dullness_score",
            "uneven_tone_score",
            "nasolabial_wrinkle_score",
        ]
        
        for metric in front_dominant:
            weights = merger.ANGLE_WEIGHTS[metric]
            assert weights["front"] == 0.7
            assert weights["left"] == 0.15
            assert weights["right"] == 0.15
            assert weights["front"] > weights["left"]
            assert weights["front"] > weights["right"]
    
    def test_max_method_metrics(self):
        """최대값 기반 항목 테스트"""
        merger = MultiViewMerger()
        
        max_metrics = ["acne_score", "post_acne_pigment_score"]
        
        for metric in max_metrics:
            assert metric in merger.ANGLE_WEIGHTS
            assert merger.ANGLE_WEIGHTS[metric]["method"] == "max"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
