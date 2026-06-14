#!/usr/bin/env python3
"""
CV 점수 파라미터 튜닝 스크립트

18개 측정항목의 브레이크포인트 파라미터를 자동으로 튜닝하여
테스트 하니스에서 최적의 결과를 찾습니다.

synth_faces.py를 직접 사용하여 합성 이미지를 생성하고
분석기를 실행하여 파라미터를 튜닝합니다.

사용법:
    python scripts/tune_cv_parameters.py --metric melasma_score --iterations 100
    python scripts/tune_cv_parameters.py --all --iterations 50
    python scripts/tune_cv_parameters.py --config config/config.json --output results/tuning_results.json
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
import copy
import random
import numpy as np
from datetime import datetime

# synth_faces.py 및 분석기 import
sys.path.insert(0, str(Path(__file__).parent.parent))
from tests.cv_scoring import synth_faces as S
from src.skin.analyzers.pigmentation import analyze_pigmentation
from src.skin.analyzers.redness import analyze_redness
from src.skin.analyzers.acne import analyze_acne
from src.skin.analyzers.pore import analyze_pores
from src.skin.analyzers.wrinkle_texture import analyze_texture
from src.skin.analyzers.tone_elasticity import analyze_tone_elasticity
from src.skin.analyzers.sebum import analyze_sebum

# 테스트 하니스 경로
TEST_DIR = Path("tests/cv_scoring")
GOLDEN_FILE = TEST_DIR / "golden_scores.json"


class ParameterTuner:
    """CV 점수 파라미터 튜너"""

    def __init__(self, config_path: Path, output_path: Path):
        self.config_path = config_path
        self.output_path = output_path
        self.config = self._load_config()
        self.results = []

    def _load_config(self) -> Dict:
        """config.json 로드"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_config(self, config: Dict):
        """config.json 저장"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _run_test(self, metric: str = None, test_type: str = "monotonicity") -> Dict[str, Any]:
        """synth_faces.py를 사용하여 직접 테스트 실행 및 결과 수집 (프로덕션 버전)"""
        
        if test_type == "monotonicity":
            return self._test_monotonicity(metric)
        elif test_type == "independence":
            return self._test_independence(metric)
        elif test_type == "composite":
            return self._test_composite(metric)
        elif test_type == "regression":
            return self._test_regression(metric)
        elif test_type == "all":
            return self._test_all(metric)
        else:
            return {"error": f"Unknown test type: {test_type}"}

    def _test_monotonicity(self, metric: str) -> Dict[str, Any]:
        """단조성 테스트"""
        try:
            seeds = [0, 42, 100, 200, 300]
            severities = [0, 0.25, 0.5, 0.75, 1.0]
            
            all_scores = []
            monotonic_results = []
            range_results = []
            
            for seed in seeds:
                scores = []
                
                for severity in severities:
                    face = S.make_skin_canvas(seed=seed)
                    injector = self._get_injector(metric)
                    if injector:
                        face = injector(face, severity, seed=seed + 1000)
                    io = S.io_full(face)
                    score = self._run_analyzer(metric, io)
                    scores.append(score)
                
                all_scores.append(scores)
                
                monotonic_passed = True
                for i in range(1, len(scores)):
                    if scores[i] > scores[i-1] + 3.0:
                        monotonic_passed = False
                        break
                monotonic_results.append(monotonic_passed)
                
                range_passed = all(0 <= s <= 100 for s in scores)
                range_results.append(range_passed)
            
            avg_monotonic = sum(monotonic_results) / len(monotonic_results)
            avg_range = sum(range_results) / len(range_results)
            
            avg_scores = np.mean(all_scores, axis=0)
            score_changes = [avg_scores[i] - avg_scores[i-1] for i in range(1, len(avg_scores))]
            avg_change = np.mean(score_changes)
            
            if len(avg_scores) > 1:
                x = np.array(severities)
                y = np.array(avg_scores)
                correlation = np.corrcoef(x, y)[0, 1]
                r_squared = correlation ** 2 if not np.isnan(correlation) else 0
            else:
                r_squared = 0
            
            overall_score = (avg_monotonic * 0.4) + (avg_range * 0.3) + (r_squared * 0.3)
            
            return {
                "test_type": "monotonicity",
                "scores": avg_scores.tolist(),
                "all_scores": all_scores,
                "monotonic_passed": avg_monotonic >= 0.8,
                "range_passed": avg_range >= 0.8,
                "avg_monotonic": avg_monotonic,
                "avg_range": avg_range,
                "r_squared": r_squared,
                "avg_score_change": avg_change,
                "overall_score": overall_score,
                "passed": 1 if overall_score >= 0.7 else 0,
                "failed": 0 if overall_score >= 0.7 else 1,
            }
        except Exception as e:
            return {
                "test_type": "monotonicity",
                "error": str(e),
                "passed": 0,
                "failed": 1,
            }

    def _test_independence(self, metric: str) -> Dict[str, Any]:
        """독립성 테스트: A 주입 시 B 지표 변화 확인"""
        try:
            # 모든 메트릭 목록
            all_metrics = [
                "melasma_score", "freckle_score", "redness_score",
                "post_inflammatory_erythema_score", "acne_score",
                "post_acne_pigment_score", "pore_size_score",
                "pore_sagging_score", "eye_wrinkle_score",
                "nasolabial_wrinkle_score", "fine_deep_wrinkle_score",
                "roughness_score", "skin_tone_score", "dullness_score",
                "uneven_tone_score", "jawline_blur_score",
                "cheek_sagging_score", "skin_type_score"
            ]
            
            independence_results = []
            
            for other_metric in all_metrics:
                if other_metric == metric:
                    continue
                
                # 기준 상태
                base_face = S.make_skin_canvas(seed=42)
                base_io = S.io_full(base_face)
                base_score = self._run_analyzer(other_metric, base_io)
                
                # A 결함 주입
                defected_face = S.make_skin_canvas(seed=42)
                injector = self._get_injector(metric)
                if injector:
                    defected_face = injector(defected_face, 1.0, seed=42)
                defected_io = S.io_full(defected_face)
                defected_score = self._run_analyzer(other_metric, defected_io)
                
                # 변화량 계산
                change = abs(defected_score - base_score)
                independence_passed = change < 12  # 허용 오차 12점
                
                independence_results.append({
                    "other_metric": other_metric,
                    "base_score": base_score,
                    "defected_score": defected_score,
                    "change": change,
                    "passed": independence_passed
                })
            
            # 통계
            passed_count = sum(1 for r in independence_results if r["passed"])
            total_count = len(independence_results)
            avg_independence = passed_count / total_count if total_count > 0 else 0
            
            return {
                "test_type": "independence",
                "independence_results": independence_results,
                "passed_count": passed_count,
                "total_count": total_count,
                "avg_independence": avg_independence,
                "independence_passed": avg_independence >= 0.8,  # 80% 이상 통과
                "passed": 1 if avg_independence >= 0.8 else 0,
                "failed": 0 if avg_independence >= 0.8 else 1,
            }
        except Exception as e:
            return {
                "test_type": "independence",
                "error": str(e),
                "passed": 0,
                "failed": 1,
            }

    def _test_composite(self, metric: str) -> Dict[str, Any]:
        """복합 결함 테스트: 여러 결함 중첩"""
        try:
            # 복합 결함 조합 (관련성 있는 메트릭 그룹)
            composite_groups = {
                "pigmentation": ["melasma_score", "freckle_score", "post_acne_pigment_score"],
                "redness": ["redness_score", "post_inflammatory_erythema_score"],
                "texture": ["roughness_score", "pore_size_score", "pore_sagging_score"],
                "wrinkle": ["eye_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score"],
                "tone": ["skin_tone_score", "dullness_score", "uneven_tone_score"],
            }
            
            # 현재 메트릭의 그룹 찾기
            current_group = None
            for group, metrics in composite_groups.items():
                if metric in metrics:
                    current_group = metrics
                    break
            
            if not current_group:
                return {
                    "test_type": "composite",
                    "error": f"No composite group found for {metric}",
                    "passed": 0,
                    "failed": 1,
                }
            
            # 단일 결함 테스트
            single_face = S.make_skin_canvas(seed=100)
            injector = self._get_injector(metric)
            if injector:
                single_face = injector(single_face, 0.5, seed=100)
            single_io = S.io_full(single_face)
            single_score = self._run_analyzer(metric, single_io)
            
            # 복합 결함 테스트
            composite_face = S.make_skin_canvas(seed=100)
            
            # 그룹 내 다른 메트릭도 주입
            for other_metric in current_group:
                if other_metric != metric:
                    other_injector = self._get_injector(other_metric)
                    if other_injector:
                        composite_face = other_injector(composite_face, 0.3, seed=100 + hash(other_metric))
            
            # 현재 메트릭 주입
            if injector:
                composite_face = injector(composite_face, 0.5, seed=100)
            
            composite_io = S.io_full(composite_face)
            composite_score = self._run_analyzer(metric, composite_io)
            
            # 변화량 계산
            change = abs(composite_score - single_score)
            composite_passed = change < 15  # 허용 오차 15점
            
            return {
                "test_type": "composite",
                "group": current_group,
                "single_score": single_score,
                "composite_score": composite_score,
                "change": change,
                "composite_passed": composite_passed,
                "passed": 1 if composite_passed else 0,
                "failed": 0 if composite_passed else 1,
            }
        except Exception as e:
            return {
                "test_type": "composite",
                "error": str(e),
                "passed": 0,
                "failed": 1,
            }

    def _test_regression(self, metric: str) -> Dict[str, Any]:
        """회귀 테스트: golden score와 비교"""
        try:
            # golden score 로드
            if not GOLDEN_FILE.exists():
                return {
                    "test_type": "regression",
                    "error": "Golden score file not found",
                    "passed": 0,
                    "failed": 1,
                }
            
            with open(GOLDEN_FILE, 'r', encoding='utf-8') as f:
                golden_data = json.load(f)
            
            if metric not in golden_data:
                return {
                    "test_type": "regression",
                    "error": f"Golden score not found for {metric}",
                    "passed": 0,
                    "failed": 1,
                }
            
            golden_score = golden_data[metric]
            
            # 현재 점수 계산
            face = S.make_skin_canvas(seed=0)
            injector = self._get_injector(metric)
            if injector:
                face = injector(face, 0.5, seed=42)
            io = S.io_full(face)
            current_score = self._run_analyzer(metric, io)
            
            # 차이 계산
            diff = abs(current_score - golden_score)
            regression_passed = diff < 5  # 허용 오차 5점
            
            return {
                "test_type": "regression",
                "golden_score": golden_score,
                "current_score": current_score,
                "diff": diff,
                "regression_passed": regression_passed,
                "passed": 1 if regression_passed else 0,
                "failed": 0 if regression_passed else 1,
            }
        except Exception as e:
            return {
                "test_type": "regression",
                "error": str(e),
                "passed": 0,
                "failed": 1,
            }

    def _test_all(self, metric: str) -> Dict[str, Any]:
        """모든 테스트 실행 및 종합 평가"""
        try:
            monotonicity_result = self._test_monotonicity(metric)
            independence_result = self._test_independence(metric)
            composite_result = self._test_composite(metric)
            regression_result = self._test_regression(metric)
            
            # 종합 점수 계산
            # 단조성 30%, 독립성 30%, 복합 20%, 회귀 20%
            weights = {
                "monotonicity": 0.3,
                "independence": 0.3,
                "composite": 0.2,
                "regression": 0.2,
            }
            
            scores = {
                "monotonicity": monotonicity_result.get("overall_score", 0),
                "independence": independence_result.get("avg_independence", 0),
                "composite": 1.0 if composite_result.get("composite_passed", False) else 0,
                "regression": 1.0 if regression_result.get("regression_passed", False) else 0,
            }
            
            overall_score = sum(scores[k] * weights[k] for k in scores)
            
            total_passed = (
                monotonicity_result.get("passed", 0) +
                independence_result.get("passed", 0) +
                composite_result.get("passed", 0) +
                regression_result.get("passed", 0)
            )
            
            total_failed = (
                monotonicity_result.get("failed", 0) +
                independence_result.get("failed", 0) +
                composite_result.get("failed", 0) +
                regression_result.get("failed", 0)
            )
            
            return {
                "test_type": "all",
                "monotonicity": monotonicity_result,
                "independence": independence_result,
                "composite": composite_result,
                "regression": regression_result,
                "scores": scores,
                "overall_score": overall_score,
                "total_passed": total_passed,
                "total_failed": total_failed,
                "passed": 1 if overall_score >= 0.7 else 0,
                "failed": 0 if overall_score >= 0.7 else 1,
            }
        except Exception as e:
            return {
                "test_type": "all",
                "error": str(e),
                "passed": 0,
                "failed": 1,
            }

    def _get_injector(self, metric: str):
        """메트릭별 주입기 반환"""
        injectors = {
            "melasma_score": S.inject_melasma,
            "freckle_score": lambda f, s, seed: S.inject_dark_blobs(f, int(s * 80), seed),
            "redness_score": S.inject_redness,
            "post_inflammatory_erythema_score": S.inject_pie_focal,
            "acne_score": S.inject_acne,
            "post_acne_pigment_score": S.inject_post_acne_pigment,
            "pore_size_score": S.inject_pores,
            "pore_sagging_score": S.inject_pore_sagging,
            "eye_wrinkle_score": lambda f, s, seed: S.inject_wrinkle_lines(f, s, roi="eye", seed=seed),
            "nasolabial_wrinkle_score": lambda f, s, seed: S.inject_wrinkle_lines(f, s, roi="naso", seed=seed),
            "fine_deep_wrinkle_score": S.inject_forehead_lines,
            "roughness_score": S.inject_roughness,
            "skin_tone_score": S.inject_dark_global,
            "dullness_score": S.inject_dullness,
            "uneven_tone_score": S.inject_uneven_tone,
            "jawline_blur_score": S.inject_jawline_blur,
            "cheek_sagging_score": S.inject_vertical_gradient,
            "skin_type_score": S.inject_oily,
        }
        return injectors.get(metric)

    def _run_analyzer(self, metric: str, io: Dict) -> float:
        """메트릭별 분석기 실행"""
        analyzers = {
            "melasma_score": lambda: analyze_pigmentation(io["face"], io["smask_bool"], io["stat"]),
            "freckle_score": lambda: analyze_pigmentation(io["face"], io["smask_bool"], io["stat"]),
            "redness_score": lambda: analyze_redness(io["face"], io["smask"], io["stat"]),
            "post_inflammatory_erythema_score": lambda: analyze_redness(io["face"], io["smask"], io["stat"]),
            "acne_score": lambda: analyze_acne(io["face"], io["smask"], io["stat"]),
            "post_acne_pigment_score": lambda: analyze_pigmentation(io["face"], io["smask_bool"], io["stat"]),
            "pore_size_score": lambda: analyze_pores(io["face"], io["regions"]),
            "pore_sagging_score": lambda: analyze_pores(io["face"], io["regions"]),
            "eye_wrinkle_score": lambda: analyze_texture(io["face"], io["smask"], io["stat"]),
            "nasolabial_wrinkle_score": lambda: analyze_texture(io["face"], io["smask"], io["stat"]),
            "fine_deep_wrinkle_score": lambda: analyze_texture(io["face"], io["smask"], io["stat"]),
            "roughness_score": lambda: analyze_texture(io["face"], io["smask"], io["stat"]),
            "skin_tone_score": lambda: analyze_tone_elasticity(io["face"], io["smask"], io["stat"]),
            "dullness_score": lambda: analyze_tone_elasticity(io["face"], io["smask"], io["stat"]),
            "uneven_tone_score": lambda: analyze_tone_elasticity(io["face"], io["smask"], io["stat"]),
            "jawline_blur_score": lambda: analyze_tone_elasticity(io["face"], io["smask"], io["stat"]),
            "cheek_sagging_score": lambda: analyze_tone_elasticity(io["face"], io["smask"], io["stat"]),
            "skin_type_score": lambda: analyze_sebum(io["face"], io["smask"], io["stat"]),
        }
        
        analyzer = analyzers.get(metric)
        if analyzer:
            result = analyzer()
            return result.get(metric, 0.0)
        return 0.0

    def _get_metric_breakpoints(self, metric: str) -> List[Tuple[str, List[float]]]:
        """특정 메트릭의 브레이크포인트 경로 반환"""
        # 메트릭별 브레이크포인트 경로 매핑
        metric_paths = {
            "melasma_score": ["cv_analyzers", "pigmentation", "bp_melasma"],
            "freckle_score": ["cv_analyzers", "pigmentation", "bp_freckle"],
            "redness_score": ["cv_analyzers", "redness", "bp_redness"],
            "post_inflammatory_erythema_score": ["cv_analyzers", "redness", "bp_pie"],
            "acne_score": ["cv_analyzers", "acne", "bp_acne"],
            "post_acne_pigment_score": ["cv_analyzers", "acne", "bp_pap"],
            "pore_size_score": ["cv_analyzers", "pore", "bp_pore_size"],
            "pore_sagging_score": ["cv_analyzers", "pore", "bp_pore_sagging"],
            "eye_wrinkle_score": ["cv_analyzers", "wrinkle", "bp_eye_wrinkle"],
            "nasolabial_wrinkle_score": ["cv_analyzers", "wrinkle", "bp_nasolabial_wrinkle"],
            "fine_deep_wrinkle_score": ["cv_analyzers", "wrinkle", "bp_forehead_wrinkle"],
            "roughness_score": ["cv_analyzers", "texture", "bp_roughness"],
            "skin_tone_score": ["cv_analyzers", "tone", "bp_skin_tone"],
            "dullness_score": ["cv_analyzers", "tone", "bp_dullness"],
            "uneven_tone_score": ["cv_analyzers", "tone", "bp_uneven_tone"],
            "jawline_blur_score": ["cv_analyzers", "elasticity", "bp_jawline_blur"],
            "cheek_sagging_score": ["cv_analyzers", "elasticity", "bp_cheek_sagging"],
            "skin_type_score": ["cv_analyzers", "sebum", "bp_skin_type"],
        }
        
        if metric not in metric_paths:
            return []
        
        path = metric_paths[metric]
        config_value = self.config
        for key in path:
            config_value = config_value.get(key, {})
        
        if isinstance(config_value, list) and len(config_value) == 5:
            return [(path, config_value)]
        
        return []

    def _get_all_breakpoints(self) -> List[Tuple[str, List[float]]]:
        """모든 브레이크포인트 경로 반환"""
        all_breakpoints = []
        
        # cv_analyzers 섹션 순회
        cv_analyzers = self.config.get("cv_analyzers", {})
        
        for analyzer_name, analyzer_config in cv_analyzers.items():
            for metric_name, metric_config in analyzer_config.items():
                if isinstance(metric_config, dict):
                    for key, value in metric_config.items():
                        if key.startswith("bp_") and isinstance(value, list) and len(value) == 5:
                            path = ["cv_analyzers", analyzer_name, metric_name, key]
                            all_breakpoints.append((path, value))
        
        return all_breakpoints

    def _modify_breakpoint(self, path: List[str], current: List[float], strategy: str = "random") -> List[float]:
        """브레이크포인트 수정"""
        new_bp = current.copy()
        
        if strategy == "random":
            # 랜덤 수정: 각 요소를 ±10% 범위 내에서 수정
            for i in range(len(new_bp)):
                delta = random.uniform(-0.1, 0.1)
                new_bp[i] = max(0, min(100, new_bp[i] * (1 + delta)))
        
        elif strategy == "grid":
            # 그리드 서치: 고정된 스텝으로 수정
            step = 5.0
            idx = random.randint(0, len(new_bp) - 1)
            direction = random.choice([-1, 1])
            new_bp[idx] = max(0, min(100, new_bp[idx] + direction * step))
        
        elif strategy == "adaptive":
            # 적응형: 이전 결과 기반 수정 (단순 구현)
            idx = random.randint(0, len(new_bp) - 1)
            new_bp[idx] = max(0, min(100, new_bp[idx] + random.uniform(-2, 2)))
        
        # 정렬 유지 (브레이크포인트는 단조 증가해야 함)
        new_bp.sort()
        
        return new_bp

    def _apply_breakpoint(self, path: List[str], new_bp: List[float]):
        """브레이크포인트 적용"""
        config_value = self.config
        for key in path[:-1]:
            config_value = config_value[key]
        config_value[path[-1]] = new_bp

    def tune_metric(self, metric: str, iterations: int = 100, strategy: str = "random", test_type: str = "all") -> Dict:
        """단일 메트릭 튜닝 (프로덕션 버전)"""
        print(f"\n{'='*60}")
        print(f"튜닝 시작: {metric}")
        print(f"반복 횟수: {iterations}")
        print(f"전략: {strategy}")
        print(f"테스트 타입: {test_type}")
        print(f"{'='*60}\n")
        
        best_result = None
        best_score = 0
        best_bp = None
        
        breakpoints = self._get_metric_breakpoints(metric)
        if not breakpoints:
            print(f"오류: {metric}의 브레이크포인트를 찾을 수 없음")
            return {"error": f"Breakpoints not found for {metric}"}
        
        original_bp = breakpoints[0][1]
        path = breakpoints[0][0]
        
        for i in range(iterations):
            # 브레이크포인트 수정
            new_bp = self._modify_breakpoint(path, original_bp, strategy)
            self._apply_breakpoint(path, new_bp)
            self._save_config(self.config)
            
            # 테스트 실행
            test_result = self._run_test(metric, test_type)
            
            # 결과 기록
            result = {
                "iteration": i + 1,
                "metric": metric,
                "test_type": test_type,
                "breakpoints": new_bp,
                "test_result": test_result,
                "timestamp": datetime.now().isoformat()
            }
            self.results.append(result)
            
            # 최적 결과 업데이트 (overall_score 기준)
            current_score = test_result.get("overall_score", 0)
            if current_score > best_score:
                best_score = current_score
                best_result = result
                best_bp = new_bp.copy()
                
                if test_type == "all":
                    print(f"  [{i+1}/{iterations}] 새로운 최적: Overall={current_score:.3f}, PASSED={test_result['total_passed']}, FAILED={test_result['total_failed']}")
                else:
                    print(f"  [{i+1}/{iterations}] 새로운 최적: Overall={current_score:.3f}, PASSED={test_result['passed']}, FAILED={test_result['failed']}")
            else:
                if test_type == "all":
                    print(f"  [{i+1}/{iterations}] Overall={current_score:.3f}, PASSED={test_result['total_passed']}, FAILED={test_result['total_failed']}")
                else:
                    print(f"  [{i+1}/{iterations}] Overall={current_score:.3f}, PASSED={test_result['passed']}, FAILED={test_result['failed']}")
        
        # 원래 복원
        self._apply_breakpoint(path, original_bp)
        self._save_config(self.config)
        
        print(f"\n{'='*60}")
        print(f"튜닝 완료: {metric}")
        print(f"최적 Overall Score: {best_score:.3f}")
        print(f"최적 브레이크포인트: {best_bp}")
        print(f"{'='*60}\n")
        
        return {
            "metric": metric,
            "test_type": test_type,
            "best_score": best_score,
            "best_bp": best_bp,
            "best_result": best_result,
            "iterations": iterations
        }

    def tune_all(self, iterations: int = 50, strategy: str = "random", test_type: str = "all") -> Dict:
        """모든 메트릭 튜닝"""
        print(f"\n{'='*60}")
        print(f"전체 튜닝 시작")
        print(f"반복 횟수: {iterations}")
        print(f"전략: {strategy}")
        print(f"테스트 타입: {test_type}")
        print(f"{'='*60}\n")
        
        all_metrics = [
            "melasma_score", "freckle_score", "redness_score",
            "post_inflammatory_erythema_score", "acne_score",
            "post_acne_pigment_score", "pore_size_score",
            "pore_sagging_score", "eye_wrinkle_score",
            "nasolabial_wrinkle_score", "fine_deep_wrinkle_score",
            "roughness_score", "skin_tone_score", "dullness_score",
            "uneven_tone_score", "jawline_blur_score",
            "cheek_sagging_score", "skin_type_score"
        ]
        
        summary = {}
        
        for metric in all_metrics:
            result = self.tune_metric(metric, iterations, strategy, test_type)
            summary[metric] = result
        
        return summary

    def save_results(self):
        """결과 저장"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "config_path": str(self.config_path),
            "results": self.results
        }
        
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n결과 저장: {self.output_path}")


def main():
    parser = argparse.ArgumentParser(description="CV 점수 파라미터 튜닝")
    parser.add_argument("--config", type=Path, default=Path("config/config.json"),
                        help="config.json 경로")
    parser.add_argument("--output", type=Path, default=Path("results/tuning_results.json"),
                        help="결과 출력 경로")
    parser.add_argument("--metric", type=str, help="튜닝할 특정 메트릭")
    parser.add_argument("--all", action="store_true", help="모든 메트릭 튜닝")
    parser.add_argument("--iterations", type=int, default=100,
                        help="반복 횟수 (기본값: 100)")
    parser.add_argument("--strategy", type=str, default="random",
                        choices=["random", "grid", "adaptive"],
                        help="튜닝 전략 (random, grid, adaptive)")
    parser.add_argument("--test-type", type=str, default="all",
                        choices=["monotonicity", "independence", "composite", "regression", "all"],
                        help="테스트 타입 (monotonicity, independence, composite, regression, all)")
    
    args = parser.parse_args()
    
    if not args.metric and not args.all:
        print("오류: --metric 또는 --all 중 하나를 지정해야 합니다")
        sys.exit(1)
    
    tuner = ParameterTuner(args.config, args.output)
    
    if args.metric:
        result = tuner.tune_metric(args.metric, args.iterations, args.strategy, args.test_type)
        print(f"\n최종 결과: {result}")
    elif args.all:
        summary = tuner.tune_all(args.iterations, args.strategy, args.test_type)
        print(f"\n전체 요약:")
        for metric, result in summary.items():
            print(f"  {metric}: Overall Score={result.get('best_score', 0):.3f}")
    
    tuner.save_results()


if __name__ == "__main__":
    main()
