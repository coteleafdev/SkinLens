"""
test_result_parser.py — 결과 파서 단위 테스트

파이프라인 결과에서 점수 추출 유틸리티 테스트
"""
import pytest
from src.db.result_parser import extract_overall_scores


class TestExtractOverallScores:
    """종합 점수 추출 테스트"""
    
    def test_extract_overall_scores_normal(self):
        """정상적인 결과 추출 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score": 75.5,
                "overall_score_report": 80.0
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 75.5
        assert rest == 80.0
    
    def test_extract_overall_scores_no_analysis_result(self):
        """analysis_result 없는 경우 테스트"""
        json_result = {}
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 0.0
        assert rest == 0.0
    
    def test_extract_overall_scores_no_overall_score(self):
        """overall_score 없는 경우 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score_report": 80.0
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        # overall_score가 없으면 0.0
        assert orig == 0.0
        # overall_score_report가 있으면 그 값을 사용
        assert rest == 80.0
    
    def test_extract_overall_scores_no_overall_score_report(self):
        """overall_score_report 없는 경우 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score": 75.5
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 75.5
        assert rest == 75.5  # overall_score와 동일
    
    def test_extract_overall_scores_string_values(self):
        """문자열 값 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score": "75.5",
                "overall_score_report": "80.0"
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 75.5
        assert rest == 80.0
    
    def test_extract_overall_scores_integer_values(self):
        """정수 값 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score": 75,
                "overall_score_report": 80
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 75.0
        assert rest == 80.0
    
    def test_extract_overall_scores_zero(self):
        """0점 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score": 0.0,
                "overall_score_report": 0.0
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 0.0
        assert rest == 0.0
    
    def test_extract_overall_scores_negative(self):
        """음수 값 테스트 (비정상적이지만 처리)"""
        json_result = {
            "analysis_result": {
                "overall_score": -10.0,
                "overall_score_report": -5.0
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == -10.0
        assert rest == -5.0
    
    def test_extract_overall_scores_high_values(self):
        """높은 값 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score": 100.0,
                "overall_score_report": 95.0
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 100.0
        assert rest == 95.0
    
    def test_extract_overall_scores_with_other_fields(self):
        """다른 필드 포함 테스트"""
        json_result = {
            "analysis_result": {
                "overall_score": 75.5,
                "overall_score_report": 80.0,
                "measurements": {
                    "pore_score": 70.0,
                    "wrinkle_score": 80.0
                }
            },
            "metadata": {
                "version": "1.0"
            }
        }
        
        orig, rest = extract_overall_scores(json_result)
        
        assert orig == 75.5
        assert rest == 80.0
