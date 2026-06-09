"""
bp_optimizer.py — 브레이크포인트 자동 최적화 파이프라인 (ML v4.0)

현재 skin_scoring.py의 _area_to_score / _count_to_score 브레이크포인트(BP)는
v0.9~v1.0에 걸쳐 83회 이상 수동으로 튜닝됐습니다.
이 모듈은 전문가 레이팅 데이터가 수집될 때 BP를 자동으로 재보정합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
설계 원칙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. 해석 가능성 유지: BP 구조(단조 감소, 고정 x좌표)는 변경하지 않고
     y값(점수)만 최적화합니다. 결과를 사람이 검토할 수 있습니다.

  2. 단조성 보장: 면적 비율이 높을수록 점수가 낮아야 하는 물리적 제약을
     최적화 목적함수에 하드 페널티로 반영합니다.

  3. 데이터 없으면 실행하지 않음: 항목당 GT 샘플이 MIN_SAMPLES(기본 30개)
     미만이면 최적화를 건너뛰고 현재 BP를 유지합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용법
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # 1. GT 데이터 준비 (CSV: cv_value, expert_score, skin_key)
  #    cv_value   : _area_to_score 또는 _count_to_score 에 넘기는 원시 측정값
  #    expert_score: 전문가 레이팅 0~100
  #    skin_key   : 측정 항목명 (예: melasma_score, acne_score)

  from bp_optimizer import BPOptimizer
  opt = BPOptimizer(gt_csv="expert_ratings.csv")

  # 2. 최적화 실행
  results = opt.optimize_all(n_trials=300)

  # 3. 결과 검토 및 코드 패치 프리뷰
  opt.print_patch_preview(results)

  # 4. 확인 후 config.json에 반영
  opt.save_to_config(results, "config/config.json")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python bp_optimizer.py --gt expert_ratings.csv --trials 300 --dry-run
  python bp_optimizer.py --gt expert_ratings.csv --trials 500 --save
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from src.utils.utils import setup_logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  현재 BP 정의 (config.json에서 로드)
#  x좌표는 고정, y값만 최적화 대상
# ─────────────────────────────────────────────────────────────────────────────

def _load_breakpoints_from_config() -> Dict[str, Tuple[List[float], List[float]]]:
    """config.json에서 breakpoints를 로드합니다.
    
    [FIX P2-22] 하드코딩된 CURRENT_BPS 제거. config.json의 breakpoints 섹션 사용.
    """
    try:
        from src.scoring.config._config import _load_scoring_config
        config = _load_scoring_config()
        breakpoints = config.get("breakpoints", {})
        
        result: Dict[str, Tuple[List[float], List[float]]] = {}
        for key, bp_data in breakpoints.items():
            if isinstance(bp_data, list) and all(isinstance(p, list) and len(p) == 2 for p in bp_data):
                xs = [float(p[0]) for p in bp_data]
                ys = [float(p[1]) for p in bp_data]
                result[key] = (xs, ys)
        
        return result
    except Exception as e:
        log.warning("config.json에서 breakpoints 로드 실패: %s", e)
        return {}

#: 항목명 → (x 좌표 리스트, 현재 y 좌표 리스트) 딕셔너리
CURRENT_BPS: Dict[str, Tuple[List[float], List[float]]] = _load_breakpoints_from_config()

# 최적화 제외 항목 (선형 변환 항목)
_SKIP_KEYS = {"skin_tone_score", "dullness_score", "uneven_tone_score", "skin_type_score"}

#: 항목당 최소 GT 샘플 수 (미달 시 최적화 건너뜀)
#: [FIX DESIGN-6] config.json "bp_optimizer.min_samples" 로 재정의 가능
def _load_min_samples() -> int:
    """config.json 의 bp_optimizer.min_samples 를 로드.
    없으면 기본값 30 반환.
    """
    try:
        with open("config/config.json", encoding="utf-8") as f:
            cfg = json.load(f) or {}
        return int(cfg.get("bp_optimizer", {}).get("min_samples", 30))
    except Exception:
        return 30

MIN_SAMPLES: int = _load_min_samples()


# ─────────────────────────────────────────────────────────────────────────────
#  유틸
# ─────────────────────────────────────────────────────────────────────────────

def _area_to_score_bp(ratio: float, bps: List[Tuple[float, float]]) -> float:
    """브레이크포인트 리스트로 면적→점수 변환 (skin_scoring._area_to_score 동일 로직)."""
    if ratio <= bps[0][0]:
        return float(bps[0][1])
    if ratio >= bps[-1][0]:
        return float(bps[-1][1])
    for i in range(len(bps) - 1):
        r0, s0 = bps[i]
        r1, s1 = bps[i + 1]
        if r0 <= ratio <= r1:
            t = (ratio - r0) / (r1 - r0) if r1 != r0 else 0.0
            return float(max(0.0, min(100.0, s0 + t * (s1 - s0))))
    return 0.0


def _rmse(preds: List[float], targets: List[float]) -> float:
    a = np.array(preds, dtype=float)
    b = np.array(targets, dtype=float)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def _is_monotone_decreasing(ys: List[float]) -> bool:
    """y값 리스트가 단조 감소인지 확인 (동일값 허용)."""
    return all(ys[i] >= ys[i + 1] for i in range(len(ys) - 1))


def _is_monotone_increasing(ys: List[float]) -> bool:
    return all(ys[i] <= ys[i + 1] for i in range(len(ys) - 1))


# ─────────────────────────────────────────────────────────────────────────────
#  핵심 클래스
# ─────────────────────────────────────────────────────────────────────────────

class BPOptimizer:
    """브레이크포인트 자동 최적화기.

    Args:
        gt_csv:     GT 데이터 CSV 경로.
                    헤더: skin_key, cv_value, expert_score
        gt_data:    (skin_key → [(cv_val, expert_score), ...]) 직접 주입.
                    gt_csv와 둘 중 하나만 지정.
        n_trials:   Optuna 시도 횟수 기본값 (최적화 시 override 가능).
        min_samples: 항목당 최소 샘플 수.
    """

    def __init__(
        self,
        gt_csv: Optional[str | Path] = None,
        gt_data: Optional[Dict[str, List[Tuple[float, float]]]] = None,
        n_trials: int = 300,
        min_samples: int = MIN_SAMPLES,
    ) -> None:
        if gt_csv is None and gt_data is None:
            raise ValueError("gt_csv 또는 gt_data 중 하나를 지정해야 합니다.")
        self.n_trials = n_trials
        self.min_samples = min_samples
        self._data: Dict[str, List[Tuple[float, float]]] = {}

        if gt_csv is not None:
            self._load_csv(Path(gt_csv))
        if gt_data is not None:
            self._data.update(gt_data)

    # ── CSV 로드 ─────────────────────────────────────────────────────────────

    def _load_csv(self, path: Path) -> None:
        """GT CSV 로드. 헤더: skin_key, cv_value, expert_score."""
        if not path.exists():
            raise FileNotFoundError(f"GT CSV 없음: {path}")
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                key   = row.get("skin_key", "").strip()
                try:
                    cv_v  = float(row["cv_value"])
                    exp_s = float(row["expert_score"])
                except (KeyError, ValueError):
                    continue
                self._data.setdefault(key, []).append((cv_v, exp_s))
        total = sum(len(v) for v in self._data.values())
        log.info("GT 로드 완료: %d개 항목, 총 %d 샘플", len(self._data), total)

    # ── 단일 항목 최적화 ─────────────────────────────────────────────────────

    def optimize_key(
        self,
        skin_key: str,
        n_trials: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """단일 측정 항목 BP 최적화.

        Returns:
            {
                "skin_key": str,
                "xs": List[float],
                "ys_before": List[float],
                "ys_after": List[float],
                "rmse_before": float,
                "rmse_after": float,
                "n_samples": int,
                "skipped": bool,
                "skip_reason": str,
            }
        """
        if skin_key not in CURRENT_BPS:
            return {"skin_key": skin_key, "skipped": True, "skip_reason": "BP 정의 없음"}

        if skin_key in _SKIP_KEYS:
            return {"skin_key": skin_key, "skipped": True, "skip_reason": "선형 변환 항목 (최적화 불필요)"}

        samples = self._data.get(skin_key, [])
        if len(samples) < self.min_samples:
            return {
                "skin_key": skin_key,
                "skipped": True,
                "skip_reason": f"샘플 부족 ({len(samples)} < {self.min_samples})",
            }

        xs, ys_orig = CURRENT_BPS[skin_key]
        n_pts = len(xs)
        is_increasing = ys_orig[-1] > ys_orig[0]  # jawline_blur처럼 오름 방향 BP

        cv_vals = np.array([s[0] for s in samples], dtype=float)
        exp_vals = np.array([s[1] for s in samples], dtype=float)

        bps_orig = list(zip(xs, ys_orig))
        preds_before = [_area_to_score_bp(v, bps_orig) for v in cv_vals]
        rmse_before = _rmse(preds_before, exp_vals)

        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError:
            log.warning("optuna 미설치 — pip install optuna --break-system-packages")
            return {"skin_key": skin_key, "skipped": True, "skip_reason": "optuna 미설치"}

        n = n_trials or self.n_trials

        def objective(trial: "optuna.Trial") -> float:
            # y값만 최적화 (x는 고정)
            # 양 끝점은 0/100으로 고정 (물리적 의미 유지)
            ys: List[float] = []
            for i in range(n_pts):
                if i == 0:
                    ys.append(100.0 if not is_increasing else 0.0)
                elif i == n_pts - 1:
                    ys.append(0.0 if not is_increasing else 100.0)
                else:
                    ys.append(trial.suggest_float(f"y{i}", 0.0, 100.0))

            # 단조성 제약
            if is_increasing:
                if not _is_monotone_increasing(ys):
                    return 1e9
            else:
                if not _is_monotone_decreasing(ys):
                    return 1e9

            bps = list(zip(xs, ys))
            preds = [_area_to_score_bp(v, bps) for v in cv_vals]
            return _rmse(preds, exp_vals)

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=42),
        )
        study.optimize(objective, n_trials=n, show_progress_bar=False)

        best_ys: List[float] = []
        for i in range(n_pts):
            if i == 0:
                best_ys.append(100.0 if not is_increasing else 0.0)
            elif i == n_pts - 1:
                best_ys.append(0.0 if not is_increasing else 100.0)
            else:
                best_ys.append(round(study.best_params[f"y{i}"], 2))

        bps_after = list(zip(xs, best_ys))
        preds_after = [_area_to_score_bp(v, bps_after) for v in cv_vals]
        rmse_after = _rmse(preds_after, exp_vals)

        return {
            "skin_key":    skin_key,
            "xs":          xs,
            "ys_before":   ys_orig,
            "ys_after":    best_ys,
            "rmse_before": round(rmse_before, 3),
            "rmse_after":  round(rmse_after, 3),
            "n_samples":   len(samples),
            "skipped":     False,
            "skip_reason": "",
        }

    # ── 전체 항목 최적화 ─────────────────────────────────────────────────────

    def optimize_all(
        self,
        n_trials: Optional[int] = None,
        keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """모든 항목(또는 지정 항목) BP 최적화.

        Args:
            n_trials: 항목당 Optuna 시도 횟수.
            keys:     최적화할 항목 목록. None이면 CURRENT_BPS 전체.

        Returns:
            항목별 결과 딕셔너리 리스트.
        """
        targets = keys or list(CURRENT_BPS.keys())
        results = []
        for k in targets:
            log.info("최적화 중: %s ...", k)
            r = self.optimize_key(k, n_trials=n_trials)
            if r:
                results.append(r)
                if not r.get("skipped"):
                    imp = r["rmse_before"] - r["rmse_after"]
                    log.info(
                        "  %s: RMSE %.3f → %.3f  (개선 %.3f)",
                        k, r["rmse_before"], r["rmse_after"], imp,
                    )
        return results

    # ── 결과 출력 ─────────────────────────────────────────────────────────────

    @staticmethod
    def print_patch_preview(results: List[Dict[str, Any]]) -> None:
        """최적화 결과를 코드 패치 형식으로 출력."""
        print("\n" + "=" * 70)
        print("  BP 최적화 결과 — skin_scoring.py 패치 프리뷰")
        print("=" * 70)
        for r in results:
            key = r["skin_key"]
            if r.get("skipped"):
                print(f"\n  [{key}] 건너뜀: {r['skip_reason']}")
                continue
            imp = r["rmse_before"] - r["rmse_after"]
            print(f"\n  [{key}]  n={r['n_samples']}  RMSE: {r['rmse_before']:.3f} → {r['rmse_after']:.3f}  (개선 {imp:+.3f})")
            print(f"    xs = {r['xs']}")
            print(f"    전  = {[round(y, 1) for y in r['ys_before']]}")
            print(f"    후  = {[round(y, 1) for y in r['ys_after']]}")
            # 역변환 가이드
            pairs = list(zip(r["xs"], r["ys_after"]))
            bp_str = ", ".join(f"({x}, {round(y,1)})" for x, y in pairs)
            print(f"    → [{bp_str}]")
        print("\n" + "=" * 70)
        print("  검토 후 save_to_config()로 config/config.json에 반영하세요.")
        print("=" * 70 + "\n")

    @staticmethod
    def save_to_config(
        results: List[Dict[str, Any]],
        config_path: str | Path = "config/config.json",
        dry_run: bool = False,
    ) -> None:
        """최적화 결과를 config.json의 optimized_bps 섹션에 저장.

        config.json에 "optimized_bps" 키를 추가/갱신합니다.
        skin_scoring.py는 이 키를 읽어 BP를 동적으로 적용할 수 있습니다.
        (현재 버전에서는 참고용으로만 저장됩니다)
        """
        path = Path(config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        else:
            cfg = {}

        optimized: Dict[str, Any] = cfg.get("optimized_bps", {})
        for r in results:
            if r.get("skipped"):
                continue
            key = r["skin_key"]
            optimized[key] = {
                "xs":          r["xs"],
                "ys":          [round(y, 2) for y in r["ys_after"]],
                "rmse_before": r["rmse_before"],
                "rmse_after":  r["rmse_after"],
                "n_samples":   r["n_samples"],
            }

        cfg["optimized_bps"] = optimized

        if dry_run:
            print(f"[dry-run] 저장 예정: {path}")
            print(json.dumps({"optimized_bps": optimized}, ensure_ascii=False, indent=2))
            return

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        print(f"[저장 완료] {path} — optimized_bps {len(optimized)}개 항목")

    # ── 교차 검증 ─────────────────────────────────────────────────────────────

    def cross_validate(
        self,
        skin_key: str,
        k_folds: int = 5,
        n_trials: int = 100,
    ) -> Dict[str, float]:
        """k-fold 교차 검증으로 과적합 여부 확인.

        Returns:
            {"rmse_train_mean", "rmse_val_mean", "rmse_val_std"}
        """
        samples = self._data.get(skin_key, [])
        if len(samples) < k_folds * 2:
            return {"error": f"샘플 부족 ({len(samples)})"}

        import random
        shuffled = list(samples)
        random.shuffle(shuffled)
        fold_size = len(shuffled) // k_folds

        train_rmses, val_rmses = [], []
        for k in range(k_folds):
            val_start = k * fold_size
            val_end   = val_start + fold_size
            val   = shuffled[val_start:val_end]
            train = shuffled[:val_start] + shuffled[val_end:]

            # train으로 최적화
            orig_data = self._data
            self._data = {skin_key: train}
            res = self.optimize_key(skin_key, n_trials=n_trials)
            self._data = orig_data

            if res is None or res.get("skipped"):
                continue

            # train RMSE
            xs = res["xs"]
            bps_opt = list(zip(xs, res["ys_after"]))
            tr_preds = [_area_to_score_bp(s[0], bps_opt) for s in train]
            train_rmses.append(_rmse(tr_preds, [s[1] for s in train]))

            # val RMSE
            val_preds = [_area_to_score_bp(s[0], bps_opt) for s in val]
            val_rmses.append(_rmse(val_preds, [s[1] for s in val]))

        return {
            "rmse_train_mean": round(float(np.mean(train_rmses)), 3) if train_rmses else -1,
            "rmse_val_mean":   round(float(np.mean(val_rmses)),   3) if val_rmses  else -1,
            "rmse_val_std":    round(float(np.std(val_rmses)),    3) if val_rmses  else -1,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  데모 — 합성 데이터로 동작 확인
# ─────────────────────────────────────────────────────────────────────────────

def _demo() -> None:
    """합성 GT 데이터로 최적화 파이프라인 동작을 시연합니다."""
    import random
    random.seed(0); np.random.seed(0)

    # melasma_score 합성 데이터 (전문가는 낮은 비율에서 매우 민감)
    n = 120
    cv_vals = np.random.exponential(0.008, n).clip(0, 0.055)
    expert  = np.clip(100 - cv_vals * 1400 + np.random.normal(0, 6, n), 0, 100)
    gt_data = {"melasma_score": list(zip(cv_vals.tolist(), expert.tolist()))}

    # freckle_score 합성 데이터
    fc_vals = np.random.exponential(200, n).clip(0, 2100)
    f_exp   = np.clip(100 - fc_vals * 0.045 + np.random.normal(0, 5, n), 0, 100)
    gt_data["freckle_score"] = list(zip(fc_vals.tolist(), f_exp.tolist()))

    opt = BPOptimizer(gt_data=gt_data, n_trials=250, min_samples=30)
    results = opt.optimize_all(keys=["melasma_score", "freckle_score"])
    opt.print_patch_preview(results)
    opt.save_to_config(results, dry_run=True)

    print("\n[교차 검증] melasma_score 5-fold:")
    cv_result = opt.cross_validate("melasma_score", k_folds=5, n_trials=80)
    for k, v in cv_result.items():
        print(f"  {k}: {v}")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    ap = argparse.ArgumentParser(
        description="BP 자동 최적화 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--gt", metavar="CSV", help="GT CSV 파일 경로 (헤더: skin_key, cv_value, expert_score)")
    ap.add_argument("--demo", action="store_true", help="합성 데이터로 데모 실행")
    ap.add_argument("--trials", type=int, default=300, help="항목당 Optuna 시도 횟수 (기본 300)")
    ap.add_argument("--keys", nargs="*", help="최적화할 항목 목록 (미지정시 전체)")
    ap.add_argument("--min-samples", type=int, default=30, help="항목당 최소 GT 샘플 수")
    ap.add_argument("--save", action="store_true", help="결과를 config/config.json에 저장")
    ap.add_argument("--dry-run", action="store_true", help="저장 없이 미리보기만")
    ap.add_argument("--cv", metavar="KEY", help="지정 항목 k-fold 교차 검증 실행")
    ap.add_argument("--config", default="config/config.json", help="설정 파일 경로")
    ns = ap.parse_args()

    setup_logging(level="INFO", mode="cli")
    import logging

    if ns.demo:
        _demo()
        return

    if not ns.gt:
        ap.error("--gt 또는 --demo 중 하나를 지정하세요.")

    opt = BPOptimizer(gt_csv=ns.gt, n_trials=ns.trials, min_samples=ns.min_samples)

    if ns.cv:
        print(f"\n[교차 검증] {ns.cv} 5-fold:")
        r = opt.cross_validate(ns.cv, k_folds=5, n_trials=max(50, ns.trials // 5))
        for k, v in r.items():
            print(f"  {k}: {v}")
        return

    results = opt.optimize_all(keys=ns.keys)
    opt.print_patch_preview(results)

    if ns.save or ns.dry_run:
        opt.save_to_config(results, config_path=ns.config, dry_run=ns.dry_run)


if __name__ == "__main__":
    _cli()
