"""tests/cv_scoring/crosstalk_matrix.py — 측정항목 독립성 진단 (교차간섭 행렬).

한 항목용 결함만 주입했을 때 *다른* 전 항목 점수가 얼마나 변하는지(Δ) 측정한다.
- 대각 성분(주입=영향): 의도된 타깃 반응 (커야 정상).
- 비대각 성분: 교차간섭 = 점수 산출이 겹치는 정도 (작아야 독립적).

실행:  python -m tests.cv_scoring.crosstalk_matrix
주의:  큰 비대각 값 중 일부는 '주입기가 광범위'(예: 주름=어두운 선이 freckle blob 에
       잡힘, roughness=전역 노이즈)해서 생긴 것으로, 순수 단일채널 주입으로 재확인이 필요하다.
       genuine 채널 공유(redness↔PIE 등)와 주입기 아티팩트를 구분할 것.
"""
from __future__ import annotations

import numpy as np

from tests.cv_scoring import synth_faces as S
from tests.cv_scoring.test_cv_scoring_synthetic import RUNNERS, VERIFIED_MONOTONIC, ALL_METRICS


def all_scores(face) -> dict:
    """전 항목 점수를 분석기당 1회 호출로 산출."""
    cache = {}
    out = {}
    for m in ALL_METRICS:
        fn = RUNNERS[m]; key = fn.__name__
        if key not in cache:
            cache[key] = fn(face)
        out[m] = cache[key].get(m)
    return out


def compute_matrix(severity_index: int = -1) -> dict:
    """주입항목 → {영향항목: Δ} 행렬 반환."""
    clean = all_scores(S.make_skin_canvas(seed=0))
    rows = {}
    for inj, (injector, sevs) in VERIFIED_MONOTONIC.items():
        sc = all_scores(injector(sevs[severity_index]))
        rows[inj] = {m: round(sc[m] - clean[m], 1) for m in ALL_METRICS}
    return rows


def crosstalk_flags(rows: dict, thresh: float = 8.0):
    """유의한 비대각 교차간섭 목록 (절대값 내림차순)."""
    flags = []
    for inj, deltas in rows.items():
        for m, d in deltas.items():
            if m != inj and abs(d) >= thresh:
                flags.append((inj, m, d))
    return sorted(flags, key=lambda x: -abs(x[2]))


def _short(m: str) -> str:
    return (m.replace("_score", "").replace("_wrinkle", "_wr")
             .replace("post_inflammatory_erythema", "PIE")
             .replace("post_acne_pigment", "PAP"))


if __name__ == "__main__":  # pragma: no cover
    rows = compute_matrix()
    cols = ALL_METRICS
    print("CROSS-TALK Δ (주입↓ 영향→) : 대각=타깃, 비대각=교차간섭\n")
    print("inject\\affect".ljust(14) + " ".join(_short(c)[:7].rjust(7) for c in cols))
    for inj in VERIFIED_MONOTONIC:
        cells = []
        for c in cols:
            d = rows[inj][c]
            mark = "*" if (c != inj and abs(d) >= 8.0) else " "
            cells.append((f"{d:+.0f}{mark}").rjust(7))
        print(_short(inj)[:13].ljust(14) + " ".join(cells))
    print("\n유의 비대각 교차간섭 (|Δ|>=8):")
    for inj, m, d in crosstalk_flags(rows):
        print(f"  {_short(inj):14} → {_short(m):14} {d:+.1f}")
