"""
score_bias_monitor.py — 피부 분석 점수 편향 모니터링 (ML v4.0)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
목적
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ML 모델 개선(적응형 피부 마스크, BP 최적화)이 실제로 이득인지
  정량적으로 추적합니다. 구체적으로:

  1. 피부 밝기(Fitzpatrick 근사) 구간별 점수 분포 비교
     → 어두운 피부에서 점수 하락이 있으면 개선 후보
  2. 항목별 점수 분포 통계 (mean, std, p5, p50, p95)
  3. 분석 실패율 추적 (얼굴 검출 실패 → 폴백 사용 비율)
  4. 버전 간 점수 drift 감지 (기존 결과 DB와 현재 결과 비교)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용법
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  from score_bias_monitor import ScoreBiasMonitor
  mon = ScoreBiasMonitor(db_path="monitor.db")

  # 분석 결과 기록
  mon.record(image_path="face.jpg", result=analyzer.analyze_all("face.jpg"),
             brightness=brightness_estimate, analyzer_version="v3.6")

  # 편향 리포트 출력
  mon.report()

  # 버전 비교
  mon.compare_versions("v3.5", "v3.6")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python score_bias_monitor.py --db monitor.db --report
  python score_bias_monitor.py --db monitor.db --compare v3.5 v3.6
  python score_bias_monitor.py --db monitor.db --brightness-bias
"""
from __future__ import annotations

import argparse
import json
import logging
from src.utils.utils import setup_logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import cv2

log = logging.getLogger(__name__)

# Fitzpatrick 스케일 근사 — ITA 각도 기준
# ITA = arctan((L*-50)/b*) × (180/π)
# Type I>55°, II 41~55°, III 28~41°, IV 10~28°, V -30~10°, VI<-30°
_FITZPATRICK_BINS = [
    ("I (밝음)",  55.0,  90.0),
    ("II",        41.0,  55.0),
    ("III",       28.0,  41.0),
    ("IV",        10.0,  28.0),
    ("V",        -30.0,  10.0),
    ("VI (어두움)", -90.0, -30.0),
]

_SKIN_SCORE_KEYS = [
    "melasma_score", "freckle_score", "redness_score",
    "post_inflammatory_erythema_score", "acne_score", "post_acne_pigment_score",
    "pore_size_score", "pore_sagging_score", "eye_wrinkle_score",
    "nasolabial_wrinkle_score", "fine_deep_wrinkle_score", "roughness_score",
    "skin_tone_score", "dullness_score", "uneven_tone_score",
    "jawline_blur_score", "skin_type_score",
]


# ─────────────────────────────────────────────────────────────────────────────
#  ITA 추정 유틸
# ─────────────────────────────────────────────────────────────────────────────

def estimate_ita_from_image(image_bgr: np.ndarray) -> float:
    """BGR 이미지에서 피부 ITA 각도 추정.

    [FIX DESIGN-5] 기존: 얼굴 중앙 30% 패치 사용
      → 코·인중·입술이 포함돼 ITA 가 붉거나 어둡게 편향됨.
    수정: 좌·우 볼(cheek) 패치를 결합해 추정.
      y: 전체 높이 40~65%, x: 좌 5~30% / 우 70~95%
      피부 톤에 더 충실한 중립 영역이며 조명 편차도 평균화됨.
    cheek 픽셀이 부족하면(<200px) 중앙 패치로 폴백.
    """
    h, w = image_bgr.shape[:2]

    # [FIX DESIGN-5] 좌·우 볼 패치 결합
    y0, y1 = int(h * 0.40), int(h * 0.65)
    patches: List[np.ndarray] = []
    for x0, x1 in [(int(w * 0.05), int(w * 0.30)),
                   (int(w * 0.70), int(w * 0.95))]:
        p = image_bgr[y0:y1, x0:x1]
        if p.size >= 200 * 3:   # 최소 200 픽셀
            patches.append(p)

    if patches:
        patch = np.vstack(patches) if len(patches) > 1 else patches[0]
    else:
        # 폴백: 얼굴 중앙 패치 (옆모습 등 볼 영역이 보이지 않는 경우)
        cy, cx = h // 2, w // 2
        ph, pw = max(h // 6, 10), max(w // 6, 10)
        patch = image_bgr[cy - ph: cy + ph, cx - pw: cx + pw]
        if patch.size == 0:
            patch = image_bgr

    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
    L_ch = lab[:, :, 0].astype(float)
    b_ch = lab[:, :, 2].astype(float)

    L_star = float(np.median(L_ch)) / 255.0 * 100.0
    b_star = float(np.median(b_ch)) - 128.0

    b_denom = b_star if abs(b_star) > 2.0 else (2.0 if b_star >= 0 else -2.0)
    ita = float(np.degrees(np.arctan2(L_star - 50.0, b_denom)))
    return round(ita, 2)


def ita_to_fitzpatrick(ita: float) -> str:
    """ITA 각도 → Fitzpatrick 타입 레이블."""
    for label, lo, hi in _FITZPATRICK_BINS:
        if lo <= ita <= hi:
            return label
    return "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
#  SQLite 기반 모니터
# ─────────────────────────────────────────────────────────────────────────────

class ScoreBiasMonitor:
    """분석 결과를 SQLite DB에 축적하고 편향 리포트를 생성합니다.

    Args:
        db_path: SQLite DB 파일 경로 (없으면 자동 생성).
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS records (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        image_path      TEXT,
        analyzer_version TEXT,
        ita             REAL,
        fitzpatrick     TEXT,
        overall_score   REAL,
        face_detected   INTEGER DEFAULT 1,
        scores_json     TEXT,
        recorded_at     REAL
    );
    CREATE INDEX IF NOT EXISTS idx_version ON records(analyzer_version);
    CREATE INDEX IF NOT EXISTS idx_fitz    ON records(fitzpatrick);
    """

    def __init__(self, db_path: str | Path = "monitor.db") -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # ── 기록 ─────────────────────────────────────────────────────────────────

    def record(
        self,
        result: Dict[str, Any],
        image_path: Optional[str | Path] = None,
        image_bgr: Optional[np.ndarray] = None,
        ita: Optional[float] = None,
        analyzer_version: str = "unknown",
        face_detected: bool = True,
    ) -> None:
        """분석 결과 1건을 DB에 기록합니다.

        ita 또는 image_bgr 중 하나를 제공하면 Fitzpatrick 타입이 결정됩니다.

        Args:
            result:           SkinAnalyzer.analyze_all() 반환값.
            image_path:       원본 이미지 경로 (기록용, 분석 불필요).
            image_bgr:        BGR 이미지 배열 (ITA 추정에 사용).
            ita:              ITA 각도 직접 지정 (image_bgr 우선).
            analyzer_version: 버전 문자열 (예: "v3.6").
            face_detected:    얼굴 검출 성공 여부 (False면 폴백 경로).
        """
        if image_bgr is not None:
            ita_val = estimate_ita_from_image(image_bgr)
        elif ita is not None:
            ita_val = float(ita)
        else:
            ita_val = float("nan")

        fitz = ita_to_fitzpatrick(ita_val) if not np.isnan(ita_val) else "Unknown"

        meas = result.get("measurements_report") or result.get("measurements", {})
        scores = {k: float(meas.get(k, 0) or 0) for k in _SKIN_SCORE_KEYS}
        overall = float(result.get("overall_score_report") or result.get("overall_score") or 0)

        self._conn.execute(
            """
            INSERT INTO records
              (image_path, analyzer_version, ita, fitzpatrick,
               overall_score, face_detected, scores_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(image_path) if image_path else None,
                analyzer_version,
                ita_val if not np.isnan(ita_val) else None,
                fitz,
                overall,
                int(face_detected),
                json.dumps(scores, ensure_ascii=False),
                time.time(),
            ),
        )
        self._conn.commit()

    # ── 조회 ─────────────────────────────────────────────────────────────────

    def _fetch_scores(
        self,
        version: Optional[str] = None,
        fitzpatrick: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """조건에 맞는 레코드 조회."""
        conditions, params = [], []
        if version:
            conditions.append("analyzer_version = ?")
            params.append(version)
        if fitzpatrick:
            conditions.append("fitzpatrick = ?")
            params.append(fitzpatrick)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self._conn.execute(
            f"SELECT scores_json, overall_score, fitzpatrick, face_detected, analyzer_version FROM records {where}",
            params,
        ).fetchall()
        result = []
        for row in rows:
            try:
                scores = json.loads(row[0])
            except Exception:
                scores = {}
            scores["_overall"] = row[1]
            scores["_fitz"]    = row[2]
            scores["_detected"] = row[3]
            scores["_version"] = row[4]
            result.append(scores)
        return result

    def _stats(self, values: List[float]) -> Dict[str, float]:
        """기초 통계."""
        if not values:
            return {"n": 0, "mean": 0, "std": 0, "p5": 0, "p50": 0, "p95": 0}
        a = np.array(values, dtype=float)
        return {
            "n":   len(a),
            "mean": round(float(np.mean(a)), 2),
            "std":  round(float(np.std(a)),  2),
            "p5":   round(float(np.percentile(a, 5)),  2),
            "p50":  round(float(np.percentile(a, 50)), 2),
            "p95":  round(float(np.percentile(a, 95)), 2),
        }

    # ── 리포트 ───────────────────────────────────────────────────────────────

    def report(
        self,
        version: Optional[str] = None,
        top_n_keys: int = 5,
    ) -> None:
        """콘솔 편향 리포트 출력."""
        records = self._fetch_scores(version=version)
        if not records:
            print("[편향 리포트] 기록 없음")
            return

        total = len(records)
        detected = sum(r["_detected"] for r in records)
        print(f"\n{'=' * 65}")
        print(f"  COTELEAF 점수 편향 리포트  (총 {total}건, 버전={version or '전체'})")
        print(f"  얼굴 검출 성공률: {detected}/{total} = {detected/total*100:.1f}%")
        print(f"{'=' * 65}")

        # Fitzpatrick 타입별 overall_score 분포
        print("\n  ■ Fitzpatrick 유형별 종합 점수 분포")
        print(f"  {'유형':<15} {'n':>5} {'mean':>7} {'std':>6} {'p5':>7} {'p50':>7} {'p95':>7}")
        print(f"  {'-'*60}")
        for label, lo, hi in _FITZPATRICK_BINS:
            group = [r["_overall"] for r in records if r.get("_fitz") == label]
            s = self._stats(group)
            if s["n"] == 0:
                continue
            print(
                f"  {label:<15} {s['n']:>5} {s['mean']:>7.1f} {s['std']:>6.1f}"
                f" {s['p5']:>7.1f} {s['p50']:>7.1f} {s['p95']:>7.1f}"
            )

        # 항목별 편향 지표 (Fitzpatrick I vs VI 점수 차이)
        bright = [r for r in records if r.get("_fitz") == "I (밝음)"]
        dark   = [r for r in records if r.get("_fitz") == "VI (어두움)"]
        if bright and dark:
            print("\n  ■ Fitzpatrick I vs VI 항목별 점수 차이 (양수=밝은 피부가 더 높음)")
            diffs = []
            for k in _SKIN_SCORE_KEYS:
                b_mean = np.mean([r.get(k, 0) for r in bright])
                d_mean = np.mean([r.get(k, 0) for r in dark])
                diffs.append((k, round(float(b_mean - d_mean), 2)))
            diffs.sort(key=lambda x: abs(x[1]), reverse=True)
            print(f"  {'항목':<35} {'차이':>8}  (편향 의심 임계: |diff| > 5)")
            print(f"  {'-'*50}")
            for k, diff in diffs[:top_n_keys]:
                flag = " ← 편향 의심" if abs(diff) > 5 else ""
                print(f"  {k:<35} {diff:>+8.2f}{flag}")

        print(f"\n{'=' * 65}\n")

    def compare_versions(self, version_a: str, version_b: str) -> None:
        """두 버전 간 항목별 점수 drift 출력."""
        a_recs = self._fetch_scores(version=version_a)
        b_recs = self._fetch_scores(version=version_b)
        if not a_recs or not b_recs:
            print(f"[버전 비교] 데이터 부족: {version_a}={len(a_recs)}건, {version_b}={len(b_recs)}건")
            return

        print(f"\n{'=' * 65}")
        print(f"  버전 비교: {version_a} → {version_b}")
        print(f"  n({version_a})={len(a_recs)}, n({version_b})={len(b_recs)}")
        print(f"{'=' * 65}")
        print(f"  {'항목':<35} {'before':>8} {'after':>8} {'diff':>7}")
        print(f"  {'-'*60}")

        all_keys = ["_overall"] + _SKIN_SCORE_KEYS
        drifts = []
        for k in all_keys:
            a_mean = float(np.mean([r.get(k, 0) for r in a_recs]))
            b_mean = float(np.mean([r.get(k, 0) for r in b_recs]))
            drifts.append((k, a_mean, b_mean, b_mean - a_mean))

        # [OPT-4] Mann-Whitney U 검정 p값 추가 (scipy 있을 때만)
        try:
            from scipy import stats as _sp_stats
            _has_scipy = True
        except ImportError:
            _has_scipy = False

        drifts.sort(key=lambda x: abs(x[3]), reverse=True)
        for k in [x[0] for x in drifts]:
            a_vals = [r.get(k, 0) for r in a_recs]
            b_vals = [r.get(k, 0) for r in b_recs]
            a_m = float(np.mean(a_vals))
            b_m = float(np.mean(b_vals))
            d   = b_m - a_m
            flag = " ← 큰 변화" if abs(d) > 3 else ""
            if _has_scipy and len(a_vals) >= 5 and len(b_vals) >= 5:
                try:
                    _, p = _sp_stats.mannwhitneyu(a_vals, b_vals, alternative="two-sided")
                    sig = " ★유의(p<0.05)" if p < 0.05 else ""
                    print(f"  {k:<35} {a_m:>8.2f} {b_m:>8.2f} {d:>+7.2f}  p={p:.3f}{flag}{sig}")
                except Exception:
                    print(f"  {k:<35} {a_m:>8.2f} {b_m:>8.2f} {d:>+7.2f}{flag}")
            else:
                print(f"  {k:<35} {a_m:>8.2f} {b_m:>8.2f} {d:>+7.2f}{flag}")
        print(f"\n{'=' * 65}\n")

    def brightness_bias_report(self, version: Optional[str] = None) -> None:
        """ITA 연속값 기반 편향 시각화 (ASCII 산점도)."""
        rows = self._conn.execute(
            "SELECT ita, overall_score FROM records WHERE ita IS NOT NULL"
            + (" AND analyzer_version = ?" if version else ""),
            ([version] if version else []),
        ).fetchall()

        if not rows:
            print("[밝기 편향] ITA 데이터 없음")
            return

        ita_vals  = np.array([r[0] for r in rows])
        ov_vals   = np.array([r[1] for r in rows])

        # 선형 회귀로 편향 기울기 추정
        coef = np.polyfit(ita_vals, ov_vals, 1)
        slope = coef[0]

        print(f"\n{'=' * 55}")
        print(f"  밝기(ITA)–종합점수 상관 분석 (version={version or '전체'})")
        print(f"  기울기: {slope:+.3f} 점/도  (|기울기|>0.2이면 밝기 편향 의심)")
        print(f"  표본수: {len(rows)}")
        if abs(slope) > 0.2:
            print(f"  경고: 밝기에 따른 점수 편향이 감지됩니다.")
            print(f"  → 적응형 피부 마스크 적용 후 재측정을 권장합니다.")
        else:
            print(f"  OK: 밝기 편향이 기준 이하입니다.")
        print(f"{'=' * 55}\n")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ScoreBiasMonitor":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    ap = argparse.ArgumentParser(description="점수 편향 모니터링")
    ap.add_argument("--db", default="monitor.db", help="SQLite DB 경로")
    ap.add_argument("--report", action="store_true", help="전체 편향 리포트 출력")
    ap.add_argument("--version", help="특정 버전만 필터링")
    ap.add_argument("--compare", nargs=2, metavar=("VER_A", "VER_B"), help="두 버전 비교")
    ap.add_argument("--brightness-bias", action="store_true", help="ITA 연속 편향 분석")
    ns = ap.parse_args()

    setup_logging(level="INFO")
    import logging
    mon = ScoreBiasMonitor(db_path=ns.db)

    if ns.report:
        mon.report(version=ns.version)
    if ns.compare:
        mon.compare_versions(ns.compare[0], ns.compare[1])
    if ns.brightness_bias:
        mon.brightness_bias_report(version=ns.version)
    if not any([ns.report, ns.compare, ns.brightness_bias]):
        ap.print_help()

    mon.close()


if __name__ == "__main__":
    _cli()
