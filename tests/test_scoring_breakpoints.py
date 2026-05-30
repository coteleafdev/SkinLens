"""
Scoring Breakpoints 테스트 - 점수 브레이크포인트 설정
"""
import pytest
from src.scoring._breakpoints import (
    _get_default_breakpoints,
    _ensure_breakpoints,
    _get_metric_bp,
    _get_metric_bp_count,
    _get_image_processing_params,
    _ensure_image_proc_params,
    _get_clahe_params,
    _get_blob_detection_params,
    _get_freckle_detection_params,
    _clear_breakpoints_cache,
)


class TestScoringBreakpoints:
    """Scoring Breakpoints 테스트"""

    def test_get_default_breakpoints(self):
        """기본 브레이크포인트 로드"""
        bps = _get_default_breakpoints()
        assert isinstance(bps, dict)
        assert "area_default" in bps
        assert "count_default" in bps
        assert isinstance(bps["area_default"], list)
        assert isinstance(bps["count_default"], list)

    def test_ensure_breakpoints_caching(self):
        """브레이크포인트 캐싱 검증"""
        # 첫 번째 호출
        bps1 = _ensure_breakpoints()
        
        # 두 번째 호출 (캐시된 값 반환)
        bps2 = _ensure_breakpoints()
        
        # 같은 객체인지 확인
        assert bps1 is bps2

    def test_get_metric_bp(self):
        """메트릭 브레이크포인트 조회"""
        bp = _get_metric_bp("melasma_score")
        assert isinstance(bp, list)
        assert len(bp) > 0
        # 각 요소는 (float, float) 튜플이어야 함
        for item in bp:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], float)
            assert isinstance(item[1], float)

    def test_get_metric_bp_default(self):
        """존재하지 않는 메트릭에 대한 기본 브레이크포인트"""
        bp = _get_metric_bp("nonexistent_metric")
        assert isinstance(bp, list)
        # area_default를 사용해야 함
        assert len(bp) > 0

    def test_get_metric_bp_count(self):
        """카운트 기반 메트릭 브레이크포인트 조회"""
        bp = _get_metric_bp_count("pore_size_score")
        assert isinstance(bp, list)
        assert len(bp) > 0
        # 각 요소는 (int, float) 튜플이어야 함
        for item in bp:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], int)
            assert isinstance(item[1], float)

    def test_get_metric_bp_count_default(self):
        """존재하지 않는 카운트 메트릭에 대한 기본 브레이크포인트"""
        bp = _get_metric_bp_count("nonexistent_metric")
        assert isinstance(bp, list)
        # count_default를 사용해야 함
        assert len(bp) > 0

    def test_get_image_processing_params(self):
        """이미지 처리 파라미터 로드"""
        params = _get_image_processing_params()
        assert isinstance(params, dict)
        assert "clahe" in params
        assert "blob_detection" in params
        assert "freckle_detection" in params

    def test_ensure_image_proc_params_caching(self):
        """이미지 처리 파라미터 캐싱 검증"""
        # 첫 번째 호출
        params1 = _ensure_image_proc_params()
        
        # 두 번째 호출 (캐시된 값 반환)
        params2 = _ensure_image_proc_params()
        
        # 같은 객체인지 확인
        assert params1 is params2

    def test_get_clahe_params_default(self):
        """기본 CLAHE 파라미터 조회"""
        clip_limit, tile_grid_size = _get_clahe_params(use_pore=False)
        assert isinstance(clip_limit, float)
        assert isinstance(tile_grid_size, tuple)
        assert len(tile_grid_size) == 2
        assert isinstance(tile_grid_size[0], int)
        assert isinstance(tile_grid_size[1], int)

    def test_get_clahe_params_pore(self):
        """기공 모드 CLAHE 파라미터 조회"""
        clip_limit, tile_grid_size = _get_clahe_params(use_pore=True)
        assert isinstance(clip_limit, float)
        assert isinstance(tile_grid_size, tuple)
        # 기공 모드에서는 clip_limit_pore를 사용

    def test_get_blob_detection_params(self):
        """Blob detection 파라미터 조회"""
        params = _get_blob_detection_params()
        assert isinstance(params, dict)
        assert "thresholds" in params
        assert "min_sigma" in params
        assert "max_sigma" in params
        assert "overlap" in params
        assert "num_sigma" in params
        assert isinstance(params["thresholds"], list)
        assert isinstance(params["min_sigma"], float)
        assert isinstance(params["max_sigma"], float)
        assert isinstance(params["overlap"], float)
        assert isinstance(params["num_sigma"], int)

    def test_get_freckle_detection_params(self):
        """Freckle detection 파라미터 조회"""
        params = _get_freckle_detection_params()
        assert isinstance(params, dict)
        assert "threshold" in params
        assert "min_sigma" in params
        assert "max_sigma" in params
        assert "overlap" in params
        assert isinstance(params["threshold"], float)
        assert isinstance(params["min_sigma"], float)
        assert isinstance(params["max_sigma"], float)
        assert isinstance(params["overlap"], float)

    def test_clear_breakpoints_cache(self):
        """브레이크포인트 캐시 초기화"""
        # 캐시 미리 로드
        _ensure_breakpoints()
        _ensure_image_proc_params()
        
        # 캐시 초기화
        _clear_breakpoints_cache()
        
        # 초기화 후 다시 로드 가능해야 함
        bps = _ensure_breakpoints()
        assert isinstance(bps, dict)
        
        params = _ensure_image_proc_params()
        assert isinstance(params, dict)

    def test_breakpoint_structure(self):
        """브레이크포인트 구조 검증"""
        bps = _get_default_breakpoints()
        
        # area_default 구조
        area_bp = bps["area_default"]
        assert isinstance(area_bp, list)
        for item in area_bp:
            assert isinstance(item, list)
            assert len(item) == 2
            assert isinstance(item[0], (int, float))
            assert isinstance(item[1], (int, float))
        
        # count_default 구조
        count_bp = bps["count_default"]
        assert isinstance(count_bp, list)
        for item in count_bp:
            assert isinstance(item, list)
            assert len(item) == 2
            assert isinstance(item[0], (int, float))
            assert isinstance(item[1], (int, float))

    def test_clahe_params_structure(self):
        """CLAHE 파라미터 구조 검증"""
        params = _get_image_processing_params()["clahe"]
        assert "clip_limit" in params
        assert "clip_limit_pore" in params
        assert "tile_grid_size" in params
        assert isinstance(params["clip_limit"], float)
        assert isinstance(params["clip_limit_pore"], float)
        assert isinstance(params["tile_grid_size"], list)

    def test_blob_detection_params_structure(self):
        """Blob detection 파라미터 구조 검증"""
        params = _get_blob_detection_params()
        assert isinstance(params["thresholds"], list)
        assert all(isinstance(t, float) for t in params["thresholds"])

    def test_freckle_detection_params_structure(self):
        """Freckle detection 파라미터 구조 검증"""
        params = _get_freckle_detection_params()
        assert params["threshold"] > 0
        assert params["min_sigma"] > 0
        assert params["max_sigma"] > params["min_sigma"]
        assert 0 < params["overlap"] < 1

    def test_get_metric_bp_various_metrics(self):
        """다양한 메트릭에 대한 브레이크포인트 조회"""
        metrics = [
            "melasma_score", "freckle_score", "redness_score",
            "acne_score", "pore_size_score", "eye_wrinkle_score"
        ]
        
        for metric in metrics:
            bp = _get_metric_bp(metric)
            assert isinstance(bp, list)
            assert len(bp) > 0

    def test_breakpoint_values_range(self):
        """브레이크포인트 값 범위 검증"""
        bp = _get_metric_bp("melasma_score")
        
        # 점수는 0-100 범위여야 함
        for threshold, score in bp:
            assert 0 <= score <= 100
            assert threshold >= 0

    def test_image_processing_params_completeness(self):
        """이미지 처리 파라미터 완전성 검증"""
        params = _get_image_processing_params()
        
        # CLAHE 파라미터
        clahe = params["clahe"]
        assert clahe["clip_limit"] > 0
        assert clahe["clip_limit_pore"] > 0
        assert len(clahe["tile_grid_size"]) == 2
        assert clahe["tile_grid_size"][0] > 0
        assert clahe["tile_grid_size"][1] > 0
        
        # Blob detection 파라미터
        blob = params["blob_detection"]
        assert len(blob["thresholds"]) > 0
        assert blob["min_sigma"] > 0
        assert blob["max_sigma"] > blob["min_sigma"]
        assert 0 < blob["overlap"] < 1
        assert blob["num_sigma"] > 0
        
        # Freckle detection 파라미터
        freckle = params["freckle_detection"]
        assert freckle["threshold"] > 0
        assert freckle["min_sigma"] > 0
        assert freckle["max_sigma"] > freckle["min_sigma"]
        assert 0 < freckle["overlap"] < 1
