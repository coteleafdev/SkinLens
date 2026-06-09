#!/usr/bin/env python3
"""
Unit tests for pipeline_runner.py

파이프라인 실행기의 기능을 테스트합니다.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.pipeline.pipeline_runner import run_pipeline, run_pipeline_async, _convert_scores_to_int


class TestConvertScoresToInt:
    """점수 변환 함수 테스트."""

    def test_convert_overall_score_to_int(self):
        """전체 점수를 정수로 변환합니다."""
        result = {
            "internal_analysis": {
                "original": {
                    "overall_score": 73.7,
                    "perceived_age": 38.5,
                }
            }
        }
        converted = _convert_scores_to_int(result)
        assert converted["internal_analysis"]["original"]["overall_score"] == 74
        assert converted["internal_analysis"]["original"]["perceived_age"] == 38  # round(38.5) = 38 (banker's rounding)

    def test_convert_scores_dict_to_int(self):
        """점수 딕셔너리를 정수로 변환합니다."""
        result = {
            "internal_analysis": {
                "original": {
                    "scores": {
                        "melasma_score": 75.3,
                        "freckle_score": 82.7,
                    }
                }
            }
        }
        converted = _convert_scores_to_int(result)
        assert converted["internal_analysis"]["original"]["scores"]["melasma_score"] == 75
        assert converted["internal_analysis"]["original"]["scores"]["freckle_score"] == 83

    def test_convert_llm_scores_to_int(self):
        """LLM 점수를 정수로 변환합니다."""
        result = {
            "llm_analysis": {
                "original": {
                    "overall_score": 73.7,
                    "perceived_age": 38.5,
                    "metric_opinions": [
                        {"score": 75.3},
                        {"score": 82.7},
                    ]
                }
            }
        }
        converted = _convert_scores_to_int(result)
        assert converted["llm_analysis"]["original"]["overall_score"] == 74
        assert converted["llm_analysis"]["original"]["perceived_age"] == 38  # round(38.5) = 38 (banker's rounding)
        assert converted["llm_analysis"]["original"]["metric_opinions"][0]["score"] == 75
        assert converted["llm_analysis"]["original"]["metric_opinions"][1]["score"] == 83

    def test_no_scores_returns_unchanged(self):
        """점수가 없는 경우 변경하지 않습니다."""
        result = {"internal_analysis": {"original": {}}}
        converted = _convert_scores_to_int(result)
        assert converted == result


class TestRunPipeline:
    """파이프라인 실행 함수 테스트."""

    @patch('src.pipeline.pipeline_runner.run_enhancement_pipeline')
    def test_run_pipeline_calls_pipeline_core(self, mock_run_enhancement):
        """파이프라인 코어 함수를 호출합니다."""
        from src.pipeline.pipeline_core import PipelineResult
        mock_result = PipelineResult(
            output_stem="test",
            restored=Path("output/test.png"),
            wall_restore_sec=5.0,
            wall_total_sec=5.5,
        )
        mock_run_enhancement.return_value = mock_result

        input_image = Path("test.jpg")
        output_dir = Path("output")

        result = run_pipeline(input_image, output_dir)

        mock_run_enhancement.assert_called_once()
        assert result["output_stem"] == "test"
        assert "test.png" in result["restored"]

    @patch('src.pipeline.pipeline_runner.run_enhancement_pipeline')
    def test_run_pipeline_with_parameters(self, mock_run_enhancement):
        """파라미터를 전달하여 파이프라인을 실행합니다."""
        from src.pipeline.pipeline_core import PipelineResult
        mock_result = PipelineResult(
            output_stem="test",
            restored=Path("output/test.png"),
        )
        mock_run_enhancement.return_value = mock_result

        input_image = Path("test.jpg")
        output_dir = Path("output")

        result = run_pipeline(
            input_image,
            output_dir,
            llm_report=False,
        )

        # PipelineSettings가 올바르게 설정되었는지 확인
        call_args = mock_run_enhancement.call_args
        settings = call_args.kwargs.get('cfg')
        assert settings.llm_report is False


class TestRunPipelineAsync:
    """비동기 파이프라인 실행 함수 테스트."""

    @pytest.mark.asyncio
    @patch('src.pipeline.pipeline_runner.run_pipeline')
    async def test_run_pipeline_async_calls_sync_pipeline(self, mock_run_pipeline):
        """동기 파이프라인을 비동기로 호출합니다."""
        mock_run_pipeline.return_value = {"output_stem": "test", "restored": "output/test.png"}

        input_image = Path("test.jpg")
        output_dir = Path("output")

        result = await run_pipeline_async(input_image, output_dir)

        mock_run_pipeline.assert_called_once()
        assert result["output_stem"] == "test"
        assert "test.png" in result["restored"]

    @pytest.mark.asyncio
    @patch('src.pipeline.pipeline_runner.run_pipeline')
    async def test_run_pipeline_async_with_parameters(self, mock_run_pipeline):
        """파라미터를 전달하여 비동기 파이프라인을 실행합니다."""
        mock_run_pipeline.return_value = {"output_stem": "test", "restored": "output/test.png"}

        input_image = Path("test.jpg")
        output_dir = Path("output")

        result = await run_pipeline_async(
            input_image,
            output_dir,
            llm_report=False,
        )

        mock_run_pipeline.assert_called_once()
        call_kwargs = mock_run_pipeline.call_args.kwargs
        assert call_kwargs['llm_report'] is False
