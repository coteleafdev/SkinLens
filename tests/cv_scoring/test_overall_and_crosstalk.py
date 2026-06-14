"""tests/cv_scoring/test_overall_and_crosstalk.py — L9~L11 보강 하니스.

기존 test_cv_scoring_synthetic.py(L1~L8)는 18개 *분석기 함수*를 잠근다.
이 모듈은 그 위 단계, 즉 점수 분포를 실제로 바꾸는 부분을 추가로 잠근다:

L9.  [§I] 종합점수 직교 라우팅 + 이중가중 제거 회귀.
       - L9a 조합 레벨(순수): 각 직교 차원을 100→0 으로 떨어뜨리면 Δ == weight×100.
              특히 focal_lesion Δ ≈ 14.0(가중 0.14) — 이중가중 시절 실효 ~0.329(Δ≈33)이
              재발하면 즉시 실패한다.
       - L9b 라우팅 레벨(_legacy_to_current): overall == overall_report,
              legacy_v18 필드 존재(롤백), measurements(레이어 A)=10 직교 키, 결정론.
       - L9c 직교 레버: 한 직교 입력만 악화 → overall 단조 하강, 타 차원 영향 작음.
L10. config 브레이크포인트 이중 소스 도메인 일관성.
       top-level /breakpoints 와 /prescription/measurements/*/breakpoints 가
       같은 metric 에서 도메인(ratio vs magnitude)이 어긋나면 실패.
L11. 교차간섭(crosstalk) 회귀:
       - L11a 독립 보장 쌍: 물리적으로 독립이어야 하고 현재 |Δ|≈0 인 쌍을 잠금(<THRESH).
       - L11b 전체 행렬 스냅샷: 진단 행렬을 골든처럼 고정 → 어떤 쌍이든 변하면 리뷰.

실행:        pytest tests/cv_scoring/test_overall_and_crosstalk.py -v
스냅샷 갱신: CV_CROSSTALK_UPDATE=1 pytest tests/cv_scoring/ -k crosstalk_snapshot
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.cv_scoring import synth_faces as S
from tests.cv_scoring.test_cv_scoring_synthetic import ALL_18


# 18개 분석기 서브점수 키 (레이어 B 입력 = legacy measurements 키)
_SUB18 = list(ALL_18)


def _legacy_result(val: float = 90.0, **override) -> dict:
    """_legacy_to_current 입력용 합성 legacy_result.

    measurements 는 표시(10~90) 공간 값으로 채운다(_legacy_to_current 가 내부에서
    역변환). focal_lesion 은 직교 신호이므로 별도 키로 직접 전달된다.
    """
    m = {k: float(val) for k in _SUB18}
    m["focal_lesion"] = float(override.pop("focal_lesion", 90.0))
    m["skin_type_label"] = "중성"
    m.update(override)
    return {
        "measurements": m,
        "raw_measurements": {},
        "perceived_age": 30.0,
        "skin_stat": {},
    }


# ─────────────────────────────────────────────────────────────────────
# L9a. 조합 레벨 — 직교 가중 1회성 + focal_lesion 이중가중 제거
# ─────────────────────────────────────────────────────────────────────
class TestL9a_OrthogonalWeighting:
    def test_each_dimension_weighted_exactly_once(self):
        from src.skin.compose.score_composition import _compute_overall_score, WEIGHTS
        keys = list(WEIGHTS.keys())
        base = _compute_overall_score({k: 100.0 for k in keys})
        assert abs(base - 100.0) < 1e-6, f"전 차원 100 → 종합 100 이어야 함: {base}"
        for k, w in WEIGHTS.items():
            dropped = _compute_overall_score({**{kk: 100.0 for kk in keys}, k: 0.0})
            delta = base - dropped
            # 차원당 정확히 1회 가중: Δ == weight×100 (가중합 정규화 sum(W)=1.0)
            assert abs(delta - w * 100.0) < 0.5, (
                f"{k}: Δ={delta:.2f} 기대 {w*100:.2f} — 차원 중복/누락 가중 의심")

    def test_focal_lesion_not_double_weighted(self):
        # §I 핵심: focal_lesion 실효 가중이 0.14 여야 한다.
        # 이중가중 회귀(레이어B 평탄합 경로) 시 acne 단일가중으로 실효 ~0.329 → Δ≈33.
        from src.skin.compose.score_composition import _compute_overall_score, WEIGHTS
        keys = list(WEIGHTS.keys())
        base = _compute_overall_score({k: 100.0 for k in keys})
        dropped = _compute_overall_score({**{k: 100.0 for k in keys}, "focal_lesion": 0.0})
        delta = base - dropped
        assert 12.0 <= delta <= 16.0, (
            f"focal_lesion 실효 가중 이상: Δ={delta:.1f} (기대 ~14.0). "
            f"이중가중(Δ≈33) 재발 의심")
        assert abs(WEIGHTS["focal_lesion"] - 0.14) < 1e-6, \
            f"focal_lesion 설계 가중 0.14 변경됨: {WEIGHTS['focal_lesion']}"

    def test_weights_normalized(self):
        from src.skin.compose.score_composition import WEIGHTS
        assert len(WEIGHTS) == 10, f"직교 카테고리 10개 기대, 실제 {len(WEIGHTS)}"
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-6, \
            f"직교 가중 합 1.0 이어야 함: {sum(WEIGHTS.values())}"


# ─────────────────────────────────────────────────────────────────────
# L9b. 라우팅 레벨 — overall==report, v18 롤백 필드, 레이어 A 10키, 결정론
# ─────────────────────────────────────────────────────────────────────
class TestL9b_RoutingContract:
    def _analyzer(self):
        from src.scoring.skin_scoring import SkinAnalyzer
        return SkinAnalyzer()

    def test_overall_equals_report_and_v18_present(self):
        r = self._analyzer()._legacy_to_current(_legacy_result())
        for k in ("overall_score", "overall_score_report",
                  "overall_score_legacy_v18", "measurements", "measurements_report"):
            assert k in r, f"라우팅 출력에 {k} 누락"
        assert r["overall_score"] == r["overall_score_report"], (
            f"표시=종합 기반 불일치: overall={r['overall_score']} "
            f"report={r['overall_score_report']}")

    def test_overall_routes_through_orthogonal_not_v18(self):
        # 직교 라우팅과 레거시 18평탄합은 산출 기반이 달라 일반적으로 값이 갈린다.
        # (동일하면 §I 라우팅이 사실상 적용되지 않은 것)
        r = self._analyzer()._legacy_to_current(_legacy_result())
        assert r["overall_score"] != r["overall_score_legacy_v18"], (
            "직교 종합점수가 legacy_v18 과 동일 — §I 라우팅 미적용 의심")

    def test_layer_a_is_ten_orthogonal_keys(self):
        from src.skin.compose.score_composition import WEIGHTS
        r = self._analyzer()._legacy_to_current(_legacy_result())
        meas = r["measurements"]
        for k in WEIGHTS:
            assert k in meas, f"레이어 A 직교 키 {k} 누락"
        # measurements_report(레이어 B)는 표시/LLM 호환용으로 별도 유지
        assert r["measurements_report"], "레이어 B 보고서 측정 비어있음"

    def test_routing_deterministic(self):
        a = self._analyzer()
        v1 = a._legacy_to_current(_legacy_result())["overall_score"]
        v2 = a._legacy_to_current(_legacy_result())["overall_score"]
        assert v1 == v2, f"라우팅 비결정론: {v1} != {v2}"


# ─────────────────────────────────────────────────────────────────────
# L9c. 직교 레버 — 한 입력만 악화 → 종합 단조 하강
# ─────────────────────────────────────────────────────────────────────
class TestL9c_OrthogonalLevers:
    def _ov(self, **over):
        from src.scoring.skin_scoring import SkinAnalyzer
        return SkinAnalyzer()._legacy_to_current(_legacy_result(**over))["overall_score"]

    def test_focal_worsening_lowers_overall(self):
        base = self._ov()
        worse = self._ov(focal_lesion=10.0)
        assert worse < base, f"focal 악화가 종합을 낮추지 않음: {base}→{worse}"

    def test_wrinkle_worsening_lowers_overall(self):
        base = self._ov()
        worse = self._ov(eye_wrinkle_score=10.0,
                         nasolabial_wrinkle_score=10.0,
                         fine_deep_wrinkle_score=10.0)
        assert worse < base, f"주름 악화가 종합을 낮추지 않음: {base}→{worse}"

    def test_focal_lever_bounded_by_weight(self):
        # focal 만 90→10(표시역변환 후 raw 차이 ~80) 악화 → 종합 하강폭이
        # 가중 0.14 규모를 크게 벗어나면 안 됨(이중가중 누설 방지).
        base = self._ov()
        worse = self._ov(focal_lesion=10.0)
        assert (base - worse) <= 20.0, (
            f"focal 단일 악화로 종합이 {base - worse:.1f} 하강 — 가중 0.14 대비 과대(누설 의심)")


# ─────────────────────────────────────────────────────────────────────
# L10. config 브레이크포인트 이중 소스 도메인 일관성
# ─────────────────────────────────────────────────────────────────────
# top-level /breakpoints(코드가 실제 읽는 SSOT)와 prescription.measurements[*].breakpoints
# 가 같은 metric 에서 도메인이 어긋나면(한쪽 ratio[max≤1], 한쪽 magnitude[max≫1]) 실패.
class TestL10_BreakpointDomainConsistency:
    _WRINKLE = ("eye_wrinkle_score", "nasolabial_wrinkle_score", "fine_deep_wrinkle_score")

    def _config(self):
        from src.scoring.config._config import _load_scoring_config
        return _load_scoring_config()

    @staticmethod
    def _domain(bp) -> str:
        mx = max(float(p[0]) for p in bp)
        return "ratio" if mx <= 1.0 else "magnitude"

    @pytest.mark.parametrize("metric", _WRINKLE)
    def test_top_and_prescription_domains_agree(self, metric):
        cfg = self._config()
        top = (cfg.get("breakpoints", {}) or {}).get(metric)
        pres = (((cfg.get("prescription", {}) or {})
                 .get("measurements", {}) or {})
                .get(metric, {}) or {}).get("breakpoints")
        if not top or not pres or not isinstance(pres, list):
            pytest.skip(f"{metric}: 두 소스 중 하나가 없음(정리되었거나 미존재)")
        dt, dp = self._domain(top), self._domain(pres)
        assert dt == dp, (
            f"{metric} 도메인 불일치 — top-level={dt}(max {max(p[0] for p in top)}) "
            f"vs prescription={dp}(max {max(p[0] for p in pres)}). "
            f"이중 소스 정리(sync_breakpoint_domains.py) 필요")

    def test_live_path_wrinkle_bp_is_magnitude(self):
        # 코드가 실제 읽는 top-level eye/naso 는 magnitude 여야 함(L5 보강).
        from src.scoring._breakpoints import _get_metric_bp
        for m in ("eye_wrinkle_score", "nasolabial_wrinkle_score"):
            mx = max(x for x, _ in _get_metric_bp(m))
            assert mx > 1.0, f"{m} live bp 가 ratio 도메인(max={mx}) — magnitude 여야 함"


# ─────────────────────────────────────────────────────────────────────
# L11. 교차간섭 회귀 (진단 → assertion 승격)
# ─────────────────────────────────────────────────────────────────────
class TestL11a_IndependenceLocks:
    """물리적으로 독립이어야 하고 현재 |Δ|≈0 인 쌍을 회귀로 잠근다.

    여기서 PIE↔PAP, dullness↔skin_type 처럼 *현재 큰 누설*이 있는 쌍은 의도적으로
    제외한다(거짓 직교 주장 방지). 그건 L11b 스냅샷으로만 추적한다.
    """
    _INDEPENDENT = [
        ("melasma_score", "skin_type_score"),
        ("pore_size_score", "skin_tone_score"),
        ("pore_size_score", "dullness_score"),
        ("redness_score", "skin_type_score"),
        ("jawline_blur_score", "melasma_score"),
        ("cheek_sagging_score", "skin_type_score"),
        # ── 직교화 후 승격 (2026-06-12) ──────────────────────────────
        # dullness↔skin_type: analyze_sebum dry_mode="relative"(채도 베이스라인 상대)로
        #   전역 채도 변화 불변화 → 누설 Δ 50→0.
        ("dullness_score", "skin_type_score"),
        # uneven_tone↔PIE: inject_uneven_tone L*-only 수정(a*/b* 보존) → 누설 Δ 64→0.
        ("uneven_tone_score", "post_inflammatory_erythema_score"),
    ]
    _THRESH = 8.0

    @pytest.mark.parametrize("inj,affect", _INDEPENDENT)
    def test_independent_pair_low_crosstalk(self, inj, affect):
        from tests.cv_scoring.test_cv_scoring_synthetic import RUNNERS, VERIFIED_MONOTONIC
        injector, sevs = VERIFIED_MONOTONIC[inj]
        clean_face = S.make_skin_canvas(seed=0)
        clean = RUNNERS[affect](clean_face).get(affect)
        defected = RUNNERS[affect](injector(sevs[-1])).get(affect)
        delta = abs(defected - clean)
        assert delta < self._THRESH, (
            f"{inj} 주입이 독립항목 {affect} 를 Δ={delta:.1f} 이동 — 독립성 위반")


_CROSSTALK_SNAP = Path(__file__).parent / "crosstalk_snapshot.json"
_CROSSTALK_TOL = 2.0


class TestL11b_CrosstalkSnapshotRegression:
    def test_full_matrix_within_snapshot(self):
        from tests.cv_scoring.crosstalk_matrix import compute_matrix
        rows = compute_matrix()
        current = {f"{i}->{j}": rows[i][j] for i in rows for j in rows[i]}
        if os.environ.get("CV_CROSSTALK_UPDATE") or not _CROSSTALK_SNAP.exists():
            _CROSSTALK_SNAP.write_text(json.dumps(current, ensure_ascii=False, indent=2))
            pytest.skip("교차간섭 스냅샷 생성/갱신 — 다음 실행부터 비교")
        snap = json.loads(_CROSSTALK_SNAP.read_text())
        diffs = []
        for k, sv in snap.items():
            cv = current.get(k)
            if cv is None:
                diffs.append(f"{k}: 누락(스냅샷={sv})")
            elif abs(cv - sv) > _CROSSTALK_TOL:
                diffs.append(f"{k}: {cv:+.1f} vs 스냅 {sv:+.1f}")
        assert not diffs, ("교차간섭 회귀 감지(리뷰 필요):\n  " + "\n  ".join(diffs[:40]))
