from __future__ import annotations

import logging

log = logging.getLogger(__name__)

import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.scoring.skin_scoring import SkinAnalyzer, get_measurement_categories, REPORT_DISPLAY_NAMES


_RESULTS_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "results" / "logs" / "results.log"


def _hard_exit(code: int = 0) -> None:
    os._exit(code)


def _flatten_keys() -> list[str]:
    keys: list[str] = []
    for _, cat_keys in get_measurement_categories():
        keys.extend(cat_keys)
    return keys


def _append_results_log(lines: list[str]) -> None:
    with _RESULTS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int_display(value: Any) -> str:
    if isinstance(value, (int, float)):
        return str(int(round(float(value))))
    return str(value)


def _avg_values(v1: Any, v2: Any) -> Any:
    if isinstance(v1, dict) and isinstance(v2, dict):
        keys = set(v1.keys()) | set(v2.keys())
        return {k: _avg_values(v1.get(k), v2.get(k)) for k in keys}
    if isinstance(v1, list) and isinstance(v2, list) and len(v1) == len(v2):
        return [_avg_values(a, b) for a, b in zip(v1, v2)]
    if isinstance(v1, tuple) and isinstance(v2, tuple) and len(v1) == len(v2):
        return tuple(_avg_values(a, b) for a, b in zip(v1, v2))
    if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
        return (float(v1) + float(v2)) / 2.0
    if v1 is None:
        return v2
    if v2 is None:
        return v1
    return v1


def analyze_compare_triple(
    orig_path: str | Path,
    ref1_path: str | Path,
    ref2_path: str | Path,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """비교 계산기와 동일: 기준1·2 분석 후 skin_stat 평균을 ref_stat 으로 원본 재분석.
    
    [FIX v1.0] ref_stat 사용 제거: 독립적 측정으로 변경하여 실제 복원 효과를 점수에 반영.
    """
    an = SkinAnalyzer()
    ref1 = an.analyze_all(str(ref1_path), debug=False, clahe_preprocessed=False)
    ref2 = an.analyze_all(str(ref2_path), debug=False, clahe_preprocessed=False)
    # [FIX v1.0] ref_stat 사용 제거: 독립적 측정
    orig = an.analyze_all(
        str(orig_path),
        debug=False,
        clahe_preprocessed=False,
        ref_stat=None,  # 독립적 측정: 기준 이미지 기준 사용 안 함
    )
    return orig, ref1, ref2


def populate_compare_score_table(
    table: QTableWidget,
    lbl_overall: QLabel,
    lbl_age: QLabel,
    orig: Dict[str, Any],
    ref1: Dict[str, Any],
    ref2: Optional[Dict[str, Any]] = None,
    single_output: bool = True,
    show_actual_vs_adjusted: bool = False,
) -> None:
    """테이블에 원본/기준1/기준2 점수를 채웁니다.

    score_offset이 활성화되면 offset을 적용한 점수를 표시합니다.

    Args:
        single_output: True 이면 기준1·기준2가 동일한 복원 산출물임.
                       레이블을 '복원'으로 바꾸고 기준2 열을 숨긴다.
                       (RestoreScoreResultDialog 호출 시 사용)
        show_actual_vs_adjusted: True 이면 실측 점수와 조정된 점수를 모두 보여줌.
                                 (안전장치 적용 전후 비교)
    """
    # score_offset 적용
    def apply_score_offset(score_data, offset_config, weights):
        if not offset_config.get("enabled", False):
            return score_data

        offset = offset_config.get("offset", 0.0)
        if offset == 0.0:
            return score_data

        # 세부항목에 가중치 비례로 offset 배분
        measurements = score_data.get("measurements", {})
        total_weight = sum(weights.get(k, 0.0) for k in measurements.keys())
        adjusted_measurements = {}

        for key, value in measurements.items():
            weight = weights.get(key, 0.0)
            if total_weight > 0 and weight > 0:
                item_offset = offset * (weight / total_weight)
                adjusted_measurements[key] = min(90.0, value + item_offset)
            else:
                adjusted_measurements[key] = value

        # 피부건강지수에 offset 적용
        overall = score_data.get("overall", 0.0)
        adjusted_overall = min(90.0, overall + offset)

        return {
            "overall": adjusted_overall,
            "measurements": adjusted_measurements
        }

    # offset 설정 로드
    try:
        from src.scoring.skin_scoring import _load_scoring_config
        scoring_config = _load_scoring_config()
        offset_config = scoring_config.get("score_offset", {})
        weights = scoring_config.get("measurement_weights", {})
        log.debug("offset_config: %s", offset_config)
        log.debug("offset enabled: %s", offset_config.get('enabled', False))
        log.debug("offset value: %s", offset_config.get('offset', 0.0))
    except Exception as e:
        log.debug("offset 설정 로드 실패: %s", e)
        offset_config = {}
        weights = {}

    # 원본/복원 점수에 offset 적용 (복사본 사용)
    import copy
    orig_adjusted = copy.deepcopy(orig)
    ref1_adjusted = copy.deepcopy(ref1)

    # 원본 점수 offset 적용
    orig_measurements = orig_adjusted.get("measurements_report") or orig_adjusted.get("measurements", {})
    orig_measurements_filtered = {k: v for k, v in orig_measurements.items() if not k.endswith("_raw")}
    orig_overall = float(orig_adjusted.get("overall_score_report", orig_adjusted.get("overall_score", 0)))
    orig_score_data = {
        "overall": orig_overall,
        "measurements": orig_measurements_filtered
    }
    orig_score_adjusted = apply_score_offset(orig_score_data, offset_config, weights)

    # 조정된 원본 점수 적용
    orig_adjusted["overall_score_report"] = orig_score_adjusted["overall"]
    orig_adjusted["overall_score"] = orig_score_adjusted["overall"]
    for key, value in orig_score_adjusted["measurements"].items():
        if key in orig_measurements:
            orig_measurements[key] = value

    # 복원 점수 offset 적용
    ref1_measurements = ref1_adjusted.get("measurements_report") or ref1_adjusted.get("measurements", {})
    ref1_measurements_filtered = {k: v for k, v in ref1_measurements.items() if not k.endswith("_raw")}
    ref1_overall = float(ref1_adjusted.get("overall_score_report", ref1_adjusted.get("overall_score", 0)))
    ref1_score_data = {
        "overall": ref1_overall,
        "measurements": ref1_measurements_filtered
    }
    ref1_score_adjusted = apply_score_offset(ref1_score_data, offset_config, weights)

    # 조정된 복원 점수 적용
    ref1_adjusted["overall_score_report"] = ref1_score_adjusted["overall"]
    ref1_adjusted["overall_score"] = ref1_score_adjusted["overall"]
    for key, value in ref1_score_adjusted["measurements"].items():
        if key in ref1_measurements:
            ref1_measurements[key] = value

    # 조정된 점수 사용
    orig = orig_adjusted
    ref1 = ref1_adjusted

    log.debug("조정된 원본 피부건강지수: %.1f", orig.get('overall_score_report', 0))
    log.debug("조정된 복원 피부건강지수: %.1f", ref1.get('overall_score_report', 0))

    # [FIX v1.0 ⑥] 항목 루프가 measurements_report(레이어 B)이므로 종합도 레이어 B 기준
    def _overall(r: Dict[str, Any]) -> float:
        v = r.get("overall_score_report") or r.get("overall_score")
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _overall_raw(r: Dict[str, Any]) -> float:
        v = r.get("overall_score_report_raw") or r.get("overall_score_raw")
        try:
            val = float(v or 0.0)
            # raw 점수가 없거나 0이면 일반 점수 사용
            if val == 0:
                return _overall(r)
            return val
        except (TypeError, ValueError):
            return _overall(r)

    o_overall  = _overall(orig)
    i1_overall = _overall(ref1)
    i2_overall = _overall(ref2)
    o_overall_raw  = _overall_raw(orig)
    i1_overall_raw = _overall_raw(ref1)
    i2_overall_raw = _overall_raw(ref2)

    if single_output:
        # [FIX v1.0 ②] 복원 팝업 전용 — 기준2 열 불필요, 레이블 명확화
        if show_actual_vs_adjusted:
            # 실측 vs 조정된 점수 비교 모드: 원본 raw, 원본, 복원 raw, 복원
            lbl_overall.setText(
                f"피부건강지수: 원본(raw) {int(round(o_overall_raw))} / 원본 {int(round(o_overall))} / "
                f"복원(raw) {int(round(i2_overall))} / 복원 {int(round(i1_overall))}"
            )
            lbl_age.setText(
                f"인지 나이: 원본 {int(round(orig.get('perceived_age', 0)))}세 / "
                f"복원 {int(round(ref1.get('perceived_age', 0)))}세"
            )
        else:
            lbl_overall.setText(
                f"피부건강지수: 원본(raw) {int(round(o_overall_raw))} / 원본 {int(round(o_overall))} / "
                f"복원(raw) {int(round(i1_overall_raw))} / 복원 {int(round(i1_overall))}"
            )
            lbl_age.setText(
                f"인지 나이: 원본 {int(round(orig.get('perceived_age', 0)))}세 / "
                f"복원 {int(round(ref1.get('perceived_age', 0)))}세"
            )
    else:
        lbl_overall.setText(
            f"피부건강지수 (보고서): 원본 {int(round(o_overall))} (raw: {int(round(o_overall_raw))}) / "
            f"기준1 {int(round(i1_overall))} (raw: {int(round(i1_overall_raw))}) / "
            f"기준2 {int(round(i2_overall))} (raw: {int(round(i2_overall_raw))})"
        )
        lbl_age.setText(
            f"인지 나이: 원본 {int(round(orig.get('perceived_age', 0)))}세 / "
            f"기준1 {int(round(ref1.get('perceived_age', 0)))}세 / "
            f"기준2 {int(round(ref2.get('perceived_age', 0)))}세"
        )

    mo  = orig.get("measurements_report")  or orig.get("measurements", {})
    mi1 = ref1.get("measurements_report") or ref1.get("measurements", {})
    mi2 = ref2.get("measurements_report") or ref2.get("measurements", {})
    keys = _flatten_keys()
    
    # 열 수: 항목, 원본, 원본(raw), 복원/기준1, 복원/기준1(raw), 차이, (기준2, 기준2(raw), 차이2)
    if single_output:
        if show_actual_vs_adjusted:
            # 실측 vs 조정된 점수 비교 모드: 원본 raw, 원본, 복원 raw, 복원, 차이
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(
                ["항목", "원본(raw)", "원본", "복원(raw)", "복원", "차이(복원-원본)"]
            )
        else:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(
                ["항목", "원본(raw)", "원본", "복원(raw)", "복원", "차이(복원-원본)"]
            )
    else:
        table.setColumnCount(9)
        table.setHorizontalHeaderLabels(
            ["항목", "원본", "원본(raw)", "기준1", "기준1(raw)", "차이1", "기준2", "기준2(raw)", "차이2"]
        )
    
    table.setRowCount(len(keys))
    for r, key in enumerate(keys):
        vo  = mo.get(key)
        vo_raw = mo.get(f"{key}_raw")
        vi1 = mi1.get(key)
        vi1_raw = mi1.get(f"{key}_raw")
        vi2 = mi2.get(key)
        vi2_raw = mi2.get(f"{key}_raw")

        try:
            fvo = float(vo)
        except Exception:
            fvo = 0.0
        try:
            fvo_raw = float(vo_raw) if vo_raw is not None else None
        except Exception:
            fvo_raw = None
        # 원본 raw 점수가 없으면 원본 일반점수 사용
        if fvo_raw is None or fvo_raw == 0:
            fvo_raw = fvo
        try:
            fvi1 = float(vi1)
        except Exception:
            fvi1 = 0.0
        try:
            fvi1_raw = float(vi1_raw) if vi1_raw is not None else None
        except Exception:
            fvi1_raw = None
        # 복원 raw 점수가 없으면 복원 일반점수 사용
        if fvi1_raw is None or fvi1_raw == 0:
            fvi1_raw = fvi1
        try:
            fvi2 = float(vi2)
        except Exception:
            fvi2 = 0.0
        try:
            fvi2_raw = float(vi2_raw) if vi2_raw is not None else None
        except Exception:
            fvi2_raw = None
        # vi2 raw 점수가 없으면 vi2 일반점수 사용
        if fvi2_raw is None or fvi2_raw == 0:
            fvi2_raw = fvi2

        display_name = REPORT_DISPLAY_NAMES.get(key, key)
        table.setItem(r, 0, QTableWidgetItem(f"{key} ({display_name})"))

        if single_output:
            # 원본(raw), 원본, 복원(raw), 복원, 차이
            table.setItem(r, 1, QTableWidgetItem(_to_int_display(fvo_raw) if fvo_raw is not None else "-"))  # 원본(raw)
            table.setItem(r, 2, QTableWidgetItem(_to_int_display(vo)))  # 원본
            if show_actual_vs_adjusted:
                # 실측 복원(raw) = vi2, 조정 복원(일반) = vi1
                table.setItem(r, 3, QTableWidgetItem(_to_int_display(vi2)))  # 복원(raw)
                table.setItem(r, 4, QTableWidgetItem(_to_int_display(vi1)))  # 복원(일반)
                table.setItem(r, 5, QTableWidgetItem(f"{int(round(fvi1 - fvo)):+d}"))  # 차이(복원-원본)
            else:
                # 복원(raw) = vi1_raw, 복원(일반) = vi1
                table.setItem(r, 3, QTableWidgetItem(_to_int_display(fvi1_raw) if fvi1_raw is not None else "-"))  # 복원(raw)
                table.setItem(r, 4, QTableWidgetItem(_to_int_display(vi1)))  # 복원(일반)
                table.setItem(r, 5, QTableWidgetItem(f"{int(round(fvi1 - fvo)):+d}"))  # 차이(복원-원본)
        if not single_output:
            table.setItem(r, 1, QTableWidgetItem(_to_int_display(vo)))
            table.setItem(r, 2, QTableWidgetItem(_to_int_display(fvo_raw) if fvo_raw is not None else "-"))
            table.setItem(r, 3, QTableWidgetItem(_to_int_display(vi1)))
            table.setItem(r, 4, QTableWidgetItem(_to_int_display(fvi1_raw) if fvi1_raw is not None else "-"))
            table.setItem(r, 5, QTableWidgetItem(f"{int(round(fvi1 - fvo)):+d}"))
            table.setItem(r, 6, QTableWidgetItem(_to_int_display(vi2)))
            table.setItem(r, 7, QTableWidgetItem(_to_int_display(fvi2_raw) if fvi2_raw is not None else "-"))
            table.setItem(r, 8, QTableWidgetItem(f"{int(round(fvi2 - fvo)):+d}"))


class RestoreScoreResultDialog(QDialog):
    """파이프라인 복원 직후: 원본 vs 복원 산출 4열 비교.

    [FIX v1.0 ②] 기존 6열(기준1/기준2 동일 데이터 중복) → 4열(원본/복원/차이)로 단순화.
    종합 점수도 레이어 B(overall_score_report) 기준으로 통일.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        orig: Dict[str, Any],
        ref1: Dict[str, Any],
        ref2: Dict[str, Any],
        *,
        orig_name: str,
        out_name: str,
        show_actual_vs_adjusted: bool = False,
    ) -> None:
        super().__init__(parent)
        # 프로젝트 이름과 버전 로드
        try:
            from src.utils.config import load_config as _load_config
            config = _load_config()
            project_name = config.get("project", {}).get("name", "SkinLens")
            project_version = config.get("project", {}).get("version", "1.0.0")
            self.setWindowTitle(f"{project_name} v{project_version} - 복원 점수 — 원본「{orig_name}」vs 복원「{out_name}」")
        except Exception:
            self.setWindowTitle(f"SkinLens v1.0.0 - 복원 점수 — 원본「{orig_name}」vs 복원「{out_name}」")
        self.resize(900, 660)
        root = QVBoxLayout(self)

        head_row = QHBoxLayout()
        self.lbl_overall = QLabel()
        self.lbl_age = QLabel()
        head_row.addWidget(self.lbl_overall)
        head_row.addStretch(1)
        head_row.addWidget(self.lbl_age)
        root.addLayout(head_row)

        # 테이블 초기화 (열 수와 헤더는 populate_compare_score_table에서 설정)
        self.table = QTableWidget(0, 6)
        self.table.setColumnWidth(0, 280)  # 항목열 폭
        self.table.setColumnWidth(1, 60)   # 원본(raw)
        self.table.setColumnWidth(2, 60)   # 원본
        self.table.setColumnWidth(3, 60)   # 복원(raw)
        self.table.setColumnWidth(4, 60)   # 복원
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table, 1)

        populate_compare_score_table(
            self.table, self.lbl_overall, self.lbl_age, orig, ideal1, ideal2,
            single_output=True,
            show_actual_vs_adjusted=show_actual_vs_adjusted,
        )

        btn = QPushButton("닫기")
        btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn)
        row.addStretch(1)
        root.addLayout(row)


def show_restore_score_popup(
    orig: Path,
    final_image: Path,
    *,
    parent: Optional[QWidget] = None,
    precomputed_results: Optional[tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = None,
    show_actual_vs_adjusted: bool = False,
) -> None:
    """원본·최종 복원 산출에 대해 analyze_compare_triple 로 분석 후 모달 표시.
    
    Args:
        orig: 원본 이미지 경로
        final_image: 복원 이미지 경로
        parent: 부위젯
        precomputed_results: 미리 계산된 점수 결과 (o, i1, i2) 튜플. 제공되면 분석 건너뜀.
    """
    orig_r = Path(orig).resolve()
    out_r = Path(final_image).resolve()
    if not orig_r.is_file() or not out_r.is_file():
        return
    # QMessageBox/다이얼로그는 반드시 QApplication 이 있어야 Windows 에서도 표시된다.
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication(sys.argv)
    if precomputed_results is not None:
        o, i1, i2 = precomputed_results
    else:
        try:
            o, i1, i2 = analyze_compare_triple(orig_r, out_r, out_r)
        except Exception as e:
            QMessageBox.warning(
                parent,
                "분석 실패",
                f"점수 팝업을 띄우지 못했습니다.\n{e}",
            )
            if owns_app:
                app.quit()
            return

    log_lines = [
        "=" * 72,
        "[skin_analysis_pipeline 복원 후 점수]",
        f"timestamp | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"orig | {orig_r}",
        f"out  | {out_r}",
        "-" * 72,
    ]
    # [FIX v1.0 ③] 피부건강지수도 레이어 B(overall_score_report) 기준으로 로그
    def _ov(r: Dict[str, Any]) -> float:
        v = r.get("overall_score_report") or r.get("overall_score")
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0

    log_lines.append(
        f"overall_score_report | 원본 {int(round(_ov(o)))} | 복원 {int(round(_ov(i1)))} "
        f"| 차이 {int(round(_ov(i1) - _ov(o))):+d}"
    )
    keys = _flatten_keys()
    mo  = o.get("measurements_report") or o.get("measurements", {})
    mi1 = i1.get("measurements_report") or i1.get("measurements", {})
    
    # 톤/피부타입 관련 항목
    tone_type_keys = ["skin_tone_score", "dullness_score", "uneven_tone_score", "skin_type_score"]
    
    for key in keys:
        vo = mo.get(key)
        vi1 = mi1.get(key)
        try:
            fvo = float(vo)
            fvi1 = float(vi1)
        except Exception:
            continue
        
        diff = fvi1 - fvo
        log_line = f"{key} | 원본 {int(round(fvo))} | 복원 {int(round(fvi1))} | 차이 {int(round(diff)):+d}"
        
        # 톤/피부타입 관련 항목은 특별히 강조
        if key in tone_type_keys:
            if diff < 0:
                log_line = f"[악화] {log_line}"
            else:
                log_line = f"[톤/피부타입] {log_line}"
        
        log_lines.append(log_line)
    log_lines.append("=" * 72)
    _append_results_log(log_lines)

    dlg = RestoreScoreResultDialog(
        parent, o, i1, i2,
        orig_name=orig_r.name,
        out_name=out_r.name,
        show_actual_vs_adjusted=show_actual_vs_adjusted,
    )
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    dlg.exec()
    if owns_app:
        app.quit()


class _AnalyzeWorker(QObject):
    finished = Signal(dict, dict, dict)  # orig_result, ref1_result, ref2_result
    failed = Signal(str)

    def __init__(self, orig_path: str, ref1_path: str, ref2_path: str) -> None:
        super().__init__()
        self._orig_path = orig_path
        self._ref1_path = ref1_path
        self._ref2_path = ref2_path

    def run(self) -> None:
        try:
            orig, ref1, ref2 = analyze_compare_triple(
                self._orig_path, self._ref1_path, self._ref2_path,
            )
            self.finished.emit(orig, ref1, ref2)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # 프로젝트 이름과 버전 로드
        try:
            from src.utils.config import load_config as _load_config
            config = _load_config()
            project_name = config.get("project", {}).get("name", "SkinLens")
            project_version = config.get("project", {}).get("version", "1.0.0")
            self.setWindowTitle(f"{project_name} v{project_version} - 비교 계산기")
        except Exception:
            self.setWindowTitle("SkinLens v1.0.0 - 비교 계산기")
        self.resize(1080, 760)

        self._thread: QThread | None = None
        self._worker: _AnalyzeWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)

        path_grid = QGridLayout()
        self.edit_orig = QLineEdit()
        self.edit_ref1 = QLineEdit()
        self.edit_ref2 = QLineEdit()
        btn_orig = QPushButton("원본 선택")
        btn_ref1 = QPushButton("기준1 선택")
        btn_ref2 = QPushButton("기준2 선택")
        btn_run = QPushButton("점수 계산")
        btn_run.setMinimumHeight(36)
        self.btn_run = btn_run

        btn_orig.clicked.connect(self._pick_orig)
        btn_ref1.clicked.connect(self._pick_ref1)
        btn_ref2.clicked.connect(self._pick_ref2)
        btn_run.clicked.connect(self._run_analyze)

        path_grid.addWidget(QLabel("원본 이미지"), 0, 0)
        path_grid.addWidget(self.edit_orig, 0, 1)
        path_grid.addWidget(btn_orig, 0, 2)
        path_grid.addWidget(QLabel("기준 이미지1"), 1, 0)
        path_grid.addWidget(self.edit_ref1, 1, 1)
        path_grid.addWidget(btn_ref1, 1, 2)
        path_grid.addWidget(QLabel("기준 이미지2"), 2, 0)
        path_grid.addWidget(self.edit_ref2, 2, 1)
        path_grid.addWidget(btn_ref2, 2, 2)
        v.addLayout(path_grid)

        head_row = QHBoxLayout()
        self.lbl_overall = QLabel("피부건강지수: 원본 - / 기준1 - / 기준2 -")
        self.lbl_age = QLabel("인지 나이: 원본 - / 기준1 - / 기준2 -")
        head_row.addWidget(self.lbl_overall)
        head_row.addStretch(1)
        head_row.addWidget(self.lbl_age)
        v.addLayout(head_row)

        v.addWidget(btn_run)

        # 테이블 초기화 (열 수와 헤더는 populate_compare_score_table에서 설정)
        self.table = QTableWidget(0, 9)
        self.table.setColumnWidth(0, 240)  # 항목열 폭
        self.table.setColumnWidth(1, 50)   # 원본
        self.table.setColumnWidth(2, 50)   # 원본(raw)
        self.table.setColumnWidth(3, 50)   # 기준1
        self.table.setColumnWidth(4, 50)   # 기준1(raw)
        self.table.setColumnWidth(5, 50)   # 차이1
        self.table.setColumnWidth(6, 50)   # 기준2
        self.table.setColumnWidth(7, 50)   # 기준2(raw)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.table, 1)

        self.status = QLabel("원본/기준1/기준2 이미지를 선택한 뒤 점수 계산을 누르세요.")
        self.status.setStyleSheet("color: #666;")
        v.addWidget(self.status)

        # 닫기 이벤트가 막히는 환경 대비: 강제 종료 단축키
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=lambda: _hard_exit(0))
        QShortcut(QKeySequence("Ctrl+Shift+Q"), self, activated=lambda: _hard_exit(0))

    def _pick_orig(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self,
            "원본 이미지 선택",
            "",
            "이미지 (*.png *.jpg *.jpeg *.webp *.bmp);;모든 파일 (*.*)",
        )
        if p:
            self.edit_orig.setText(p)

    def _pick_ref1(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self,
            "기준 이미지1 선택",
            "",
            "이미지 (*.png *.jpg *.jpeg *.webp *.bmp);;모든 파일 (*.*)",
        )
        if p:
            self.edit_ref1.setText(p)

    def _pick_ref2(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self,
            "기준 이미지2 선택",
            "",
            "이미지 (*.png *.jpg *.jpeg *.webp *.bmp);;모든 파일 (*.*)",
        )
        if p:
            self.edit_ref2.setText(p)

    def _run_analyze(self) -> None:
        orig = Path(self.edit_orig.text().strip())
        ref1 = Path(self.edit_ref1.text().strip())
        ref2 = Path(self.edit_ref2.text().strip())
        if not orig.is_file():
            QMessageBox.warning(self, "입력 오류", "원본 이미지 파일을 확인하세요.")
            return
        if not ref1.is_file():
            QMessageBox.warning(self, "입력 오류", "기준 이미지1 파일을 확인하세요.")
            return
        if not ref2.is_file():
            QMessageBox.warning(self, "입력 오류", "기준 이미지2 파일을 확인하세요.")
            return
        if self._thread is not None:
            try:
                if self._thread.isRunning():
                    QMessageBox.information(self, "진행 중", "이미 계산 중입니다.")
                    return
            except RuntimeError:
                # 이미 deleteLater 된 QThread 참조 정리
                self._thread = None
                self._worker = None

        self.btn_run.setEnabled(False)
        self.status.setText("분석 중...")

        thread = QThread()
        worker = _AnalyzeWorker(str(orig), str(ref1), str(ref2))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, "_thread", None))
        thread.finished.connect(lambda: setattr(self, "_worker", None))

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_finished(self, orig: Dict[str, Any], ref1: Dict[str, Any], ref2: Dict[str, Any]) -> None:
        self.btn_run.setEnabled(True)
        self.status.setText("완료")

        populate_compare_score_table(
            self.table, self.lbl_overall, self.lbl_age, orig, ref1, ref2,
        )

        keys = _flatten_keys()
        mo = orig.get("measurements_report") or orig.get("measurements", {})
        mi1 = ref1.get("measurements_report") or ref1.get("measurements", {})
        mi2 = ref2.get("measurements_report") or ref2.get("measurements", {})
        o_overall = float(orig.get("overall_score", 0.0))
        i1_overall = float(ref1.get("overall_score", 0.0))
        i2_overall = float(ref2.get("overall_score", 0.0))

        log_lines = [
            "=" * 72,
            "[analyzer_compare_gui] 측정 결과",
            f"timestamp | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"overall_score | 원본 {int(round(o_overall))} | 기준1 {int(round(i1_overall))} | 차이1 {int(round(i1_overall - o_overall)):+d} | 기준2 {int(round(i2_overall))} | 차이2 {int(round(i2_overall - o_overall)):+d}",
            f"perceived_age | 원본 {int(round(orig.get('perceived_age', 0)))}세 | 기준1 {int(round(ref1.get('perceived_age', 0)))}세 | 기준2 {int(round(ref2.get('perceived_age', 0)))}세",
            "-" * 72,
        ]
        for key in keys:
            vo = mo.get(key)
            vi1 = mi1.get(key)
            vi2 = mi2.get(key)
            try:
                fvo = float(vo)
            except Exception:
                fvo = 0.0
            try:
                fvi1 = float(vi1)
            except Exception:
                fvi1 = 0.0
            try:
                fvi2 = float(vi2)
            except Exception:
                fvi2 = 0.0
            log_lines.append(
                f"{key} | 원본 {int(round(fvo))} | 기준1 {int(round(fvi1))} | 차이1 {int(round(fvi1 - fvo)):+d} | 기준2 {int(round(fvi2))} | 차이2 {int(round(fvi2 - fvo)):+d}"
            )
        log_lines.append("=" * 72)
        _append_results_log(log_lines)

    def _on_failed(self, msg: str) -> None:
        self.btn_run.setEnabled(True)
        self.status.setText("실패")
        QMessageBox.critical(self, "분석 오류", msg)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        event.accept()
        super().closeEvent(event)


def main() -> int:
    if "--child-gui" not in sys.argv[1:]:
        script = str(Path(__file__).resolve())
        args = [sys.executable, script, "--child-gui"]
        creationflags = 0
        if sys.platform.startswith("win"):
            # 터미널 창 없이 백그라운드 실행
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
        subprocess.Popen(args, creationflags=creationflags, close_fds=True)
        return 0

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    w = MainWindow()
    w.destroyed.connect(lambda *_: QTimer.singleShot(0, app.quit))
    w.destroyed.connect(lambda *_: QTimer.singleShot(250, lambda: app.exit(0)))
    w.destroyed.connect(lambda *_: QTimer.singleShot(1200, lambda: _hard_exit(0)))
    # 창이 실제로 사라졌는데 이벤트 루프가 남는 경우 대비 watchdog
    watchdog = QTimer()
    watchdog.setInterval(500)
    watchdog.timeout.connect(
        lambda: _hard_exit(0)
        if not any(tw.isVisible() for tw in app.topLevelWidgets())
        else None
    )
    watchdog.start()
    w.show()
    code = int(app.exec())
    _hard_exit(code)


if __name__ == "__main__":
    raise SystemExit(main())
