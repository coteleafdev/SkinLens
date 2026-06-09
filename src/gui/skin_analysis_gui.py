"""
skin_analysis_gui.py — PySide6 기반 SkinAnalysisWindow.

pipeline_core 에 대한 의존만 가짐. torch/diffusers 직접 import 없음.
"""
from __future__ import annotations

import json
import logging
import sys
import os
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

from PySide6.QtCore import QCoreApplication, QEvent, QProcess, QProcessEnvironment, QThread, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QFont, QImageReader, QPixmap
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.pipeline.pipeline_core import (
    Restorer,
    first_existing_file,
    project_root,
    format_torch_cuda_status,
    safe_output_stem,
)
from src.gui.skin_measurement_chart_dialog import (
    resolve_ref_image_path,
)
from src.skin.core.config_parser import get_measurement_count


_OPEN_PREVIEW_DIALOGS: list[QDialog] = []


def _force_terminate_process(code: int = 0) -> None:
    """Windows에서 잔여 Qt/스레드 상태와 무관하게 현재 프로세스를 강제 종료."""
    pid = os.getpid()
    if sys.platform.startswith("win"):
        try:
            # 내부 종료 훅이 막혀도 외부 taskkill 이 현재 프로세스를 강제 종료하도록 한다.
            subprocess.Popen(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as ex:
            log.error("[오류] taskkill 실행 실패: %r", ex)
            pass
    os._exit(code)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _safe_output_stem_gui(input_path_str: str, text2img: bool) -> str:
    if text2img:
        return safe_output_stem(None)
    return safe_output_stem(Path(input_path_str)) if input_path_str else safe_output_stem(None)


def _image_path_pixel_size(path: Path) -> Optional[tuple[int, int]]:
    r = QImageReader(str(path))
    if not r.canRead():
        return None
    s = r.size()
    if not s.isValid():
        return None
    return (s.width(), s.height())


def _format_pixel_dims(path: Optional[Path]) -> str:
    if path is None:
        return "—"
    if not path.is_file():
        return "—"
    wh = _image_path_pixel_size(path)
    if wh is None:
        return "알 수 없음"
    w, h = wh
    return f"{w}×{h} px"


def _center_window_on_screen(win: QMainWindow) -> None:
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    geo = win.frameGeometry()
    geo.moveCenter(screen.availableGeometry().center())
    win.move(geo.topLeft())


def _show_non_modal_dialog(dlg: QDialog) -> None:
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    _OPEN_PREVIEW_DIALOGS.append(dlg)
    dlg.destroyed.connect(
        lambda *_: _OPEN_PREVIEW_DIALOGS.remove(dlg) if dlg in _OPEN_PREVIEW_DIALOGS else None
    )
    dlg.show()


def _show_image_preview_dialog(path: Path, parent: Optional[QWidget]) -> None:
    """미리보기 썸네일에서 연 이미지를 화면에 맞게 확대해 표시."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"미리보기 — {path.name}")
    dlg.setWindowModality(Qt.WindowModality.NonModal)
    lay = QVBoxLayout(dlg)
    pm = QPixmap(str(path))
    if pm.isNull():
        QMessageBox.warning(dlg, "미리보기", "이미지를 불러올 수 없습니다.")
        return
    screen = QApplication.primaryScreen()
    ag = screen.availableGeometry() if screen is not None else None
    max_w = max(480, int(ag.width() * 0.92)) if ag is not None else 1200
    max_h = max(360, int(ag.height() * 0.85)) if ag is not None else 800
    if pm.width() > max_w or pm.height() > max_h:
        pm = pm.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    img = QLabel()
    img.setPixmap(pm)
    img.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(img)
    row = QHBoxLayout()
    row.addStretch(1)
    btn = QPushButton("닫기")
    btn.setMinimumWidth(100)
    btn.clicked.connect(dlg.accept)
    row.addWidget(btn)
    row.addStretch(1)
    lay.addLayout(row)
    dlg.resize(pm.width() + 40, pm.height() + 88)
    _show_non_modal_dialog(dlg)


def _show_double_image_preview_dialog(
    parent: Optional[QWidget],
    paths: tuple[Optional[Path], Optional[Path]],
) -> None:
    """원본·기준 두 칸에 해당하는 이미지를 한 창에 나란히 확대."""
    titles = ("원본", "기준")
    if not any(p is not None and p.is_file() for p in paths):
        QMessageBox.information(parent, "미리보기", "표시할 이미지가 없습니다.")
        return
    dlg = QDialog(parent)
    dlg.setWindowTitle("미리보기 — 크게보기")
    dlg.setWindowModality(Qt.WindowModality.NonModal)
    root_lay = QVBoxLayout(dlg)
    screen = QApplication.primaryScreen()
    ag = screen.availableGeometry() if screen is not None else None
    max_total_w = int(ag.width() * 0.96) if ag is not None else 1400
    max_h = max(260, int(ag.height() * 0.78)) if ag is not None else 700
    cell_max_w = max(180, (max_total_w - 96) // 2)

    row_widget = QWidget()
    row = QHBoxLayout(row_widget)
    row.setSpacing(10)
    for path, title in zip(paths, titles):
        col = QVBoxLayout()
        cap = QLabel(title)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet("font-weight: bold;")
        col.addWidget(cap)
        if path is not None and path.is_file():
            pm = QPixmap(str(path))
            if not pm.isNull():
                if pm.width() > cell_max_w or pm.height() > max_h:
                    pm = pm.scaled(
                        cell_max_w, max_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                img_l = QLabel()
                img_l.setPixmap(pm)
                img_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                img_l.setCursor(Qt.CursorShape.PointingHandCursor)
                img_l.setToolTip("클릭하면 이 이미지만 더 크게")

                def _make_single_popup_handler(p: Path):
                    def _on_press(ev) -> None:
                        if ev.button() == Qt.MouseButton.LeftButton:
                            # mouse 이벤트 스택 안에서 중첩 모달 exec 하면 이후 클릭이 막히는 경우 방지
                            QTimer.singleShot(0, lambda: _show_image_preview_dialog(p, dlg))

                    return _on_press

                img_l.mousePressEvent = _make_single_popup_handler(path)  # type: ignore[assignment]
                col.addWidget(img_l, 1)
            else:
                err = QLabel("불러오기 실패")
                err.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col.addWidget(err)
        else:
            empty = QLabel("— 없음 —")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #888;")
            col.addWidget(empty)
        cell = QWidget()
        cell.setLayout(col)
        row.addWidget(cell, 1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(row_widget)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setMinimumHeight(min(max_h + 72, int(ag.height() * 0.82)) if ag is not None else max_h + 72)
    root_lay.addWidget(scroll)
    btn_row = QHBoxLayout()
    btn_row.addStretch(1)
    btn = QPushButton("닫기")
    btn.clicked.connect(dlg.accept)
    btn_row.addWidget(btn)
    btn_row.addStretch(1)
    root_lay.addLayout(btn_row)
    dlg.resize(min(max_total_w, cell_max_w * 3 + 120), min(max_h + 160, int(ag.height() * 0.9)) if ag is not None else max_h + 160)
    _show_non_modal_dialog(dlg)


class ClickablePreviewLabel(QLabel):
    """유효한 이미지가 올라간 경우 클릭 시 확대 다이얼로그."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._image_path: Optional[Path] = None

    def set_image_path(self, path: Optional[Path]) -> None:
        self._image_path = path if path is not None and path.is_file() else None
        if self._image_path is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("클릭하면 크게 보기")
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._image_path is not None:
            path = self._image_path
            win = self.window()
            parent_w = win if isinstance(win, QWidget) else None

            def _open_preview() -> None:
                _show_image_preview_dialog(path, parent_w)
                if parent_w is not None:
                    parent_w.activateWindow()

            # 현재 mouse 이벤트 처리가 끝난 뒤 모달을 띄워 연속 확대가 되도록 함
            QTimer.singleShot(0, _open_preview)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# 메인 윈도우
# ---------------------------------------------------------------------------
class SkinAnalysisWindow(QMainWindow):
    _PREVIEW_W = 320
    _PREVIEW_H = 320

    def __init__(self) -> None:
        super().__init__()
        # 프로젝트 이름과 버전 로드
        import json
        try:
            config_path = Path(__file__).resolve().parents[2] / "config" / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    project_name = config.get("project", {}).get("name", "SkinLens")
                    project_version = config.get("project", {}).get("version", "1.0.0")
                    self.setWindowTitle(f"{project_name} v{project_version} (강제종료: Ctrl+Q)")
            else:
                self.setWindowTitle("SkinLens v1.0.0 (강제종료: Ctrl+Q)")
        except Exception:
            self.setWindowTitle("SkinLens v1.0.0 (강제종료: Ctrl+Q)")
        self.setMinimumSize(1040, 980)
        self.resize(1180, 1280)
        self._root = project_root()
        self._process: QProcess | None = None
        self._compare_process: QProcess | None = None  # 측정항목 비교 서브프로세스
        # skin_measurement_chart_dialog: 종료 시 스레드·타이머 정리용
        self._skin_compare_thread: QThread | None = None
        self._skin_compare_timer: QTimer | None = None

        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)

        tabs = QTabWidget()
        main_lay.addWidget(tabs)

        self._build_tab_io(tabs)

        # 실행 패널 + 프로그레스바
        g_run = QGroupBox("파이프라인 실행")
        v_run = QVBoxLayout(g_run)
        row_run = QHBoxLayout()
        self.btn_run = QPushButton("실행")
        self.btn_run.setMinimumHeight(36)
        self.btn_stop = QPushButton("중지")
        self.btn_stop.setEnabled(False)
        self.btn_run.clicked.connect(self._run_pipeline)
        self.btn_stop.clicked.connect(self._stop_pipeline)
        row_run.addWidget(self.btn_run)
        row_run.addWidget(self.btn_stop)
        row_run.addStretch(1)
        v_run.addLayout(row_run)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # 불확정 모드 (busy indicator)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        v_run.addWidget(self.progress)

        main_lay.addWidget(g_run)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        main_lay.addWidget(sep)

        self._build_preview_panel(main_lay)

        main_lay.addWidget(QLabel("로그"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setMinimumHeight(200)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_lay.addWidget(self.log, 1)

        self._connect_signals()
        self._refresh_previews()

        # 종료가 막힌 환경 대비: 언제든 강제 종료 단축키 제공
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=lambda: os._exit(0))
        QShortcut(QKeySequence("Ctrl+Shift+Q"), self, activated=lambda: os._exit(0))
        QShortcut(QKeySequence("Ctrl+Alt+Q"), self, activated=lambda: os._exit(0))
        QShortcut(QKeySequence("Ctrl+Alt+F4"), self, activated=lambda: os._exit(0))
        QShortcut(QKeySequence("Ctrl+Alt+X"), self, activated=lambda: os._exit(0))

    def closeEvent(self, event: QCloseEvent) -> None:
        """메인 창 닫기 요청 시 강제 종료."""
        # 비교 서브프로세스 종료
        cp = getattr(self, "_compare_process", None)
        if cp is not None and cp.state() != QProcess.NotRunning:
            cp.kill()
        # 열려 있는 비교 다이얼로그 닫기 (서브프로세스이므로 직접 제어 불가, 프로세스만 종료)
        try:
            from src.gui.skin_measurement_chart_dialog import close_all_compare_dialogs, _OPEN_COMPARE_DIALOGS
            # 다이얼로그를 실제로 닫음
            for dlg in list(_OPEN_COMPARE_DIALOGS):
                try:
                    dlg.reject()  # reject로 닫기 시도
                    dlg.close()   # close로 닫기 시도
                except Exception as e:
                    log.debug("다이얼로그 정리 실패: %s", e)
            # 리스트 비우기
            _OPEN_COMPARE_DIALOGS.clear()
        except Exception as e:
            log.debug("비교 다이얼로그 정리 실패: %s", e)
        # 스레드 종료 시도
        t = getattr(self, "_skin_compare_thread", None)
        if t is not None and t.isRunning():
            t.terminate()
        # 프로세스 종료
        mp = getattr(self, "_process", None)
        if mp is not None and mp.state() != QProcess.NotRunning:
            mp.kill()
        # QApplication.quit()로 전체 애플리케이션 종료 시도
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
        except Exception as e:
            log.debug("QApplication.quit() 실패: %s", e)
        # event.accept() 없이 바로 강제 종료
        _force_terminate_process(0)

    def event(self, e):  # noqa: ANN001
        # titlebar X / Alt+F4 close 이벤트를 여기서도 즉시 처리.
        try:
            if e is not None and e.type() == QEvent.Type.Close:
                # event.accept() 대신 바로 강제 종료
                _force_terminate_process(0)
                return True  # 이벤트 처리 완료
            return super().event(e)
        except Exception:
            return super().event(e)

    # ── 탭 빌더 ────────────────────────────────────────────────────────────
    def _build_tab_io(self, tabs: QTabWidget) -> None:
        tab = QWidget()
        tabs.addTab(tab, "입출력·모드")
        lay = QVBoxLayout(tab)

        g_paths = QGroupBox("입력·산출")
        fl = QFormLayout(g_paths)

        self.edit_input = QLineEdit()
        self.edit_input.setPlaceholderText("이미지 파일 경로…")
        btn_in = QPushButton("파일 선택…")
        btn_in.clicked.connect(self._pick_input_file)
        fl.addRow("입력 이미지:", self._hbox(self.edit_input, btn_in))

        self.edit_input_json = QLineEdit()
        self.edit_input_json.setPlaceholderText("설문 JSON 파일 경로… (선택사항)")
        btn_in_json = QPushButton("파일 선택…")
        btn_in_json.clicked.connect(self._pick_input_json_file)
        fl.addRow("설문 JSON:", self._hbox(self.edit_input_json, btn_in_json))

        self.edit_customer_id = QLineEdit()
        self.edit_customer_id.setPlaceholderText("고객 ID (선택사항)")
        fl.addRow("고객 ID:", self.edit_customer_id)

        self.lbl_io_input_px = QLabel("—")
        self.lbl_io_input_px.setStyleSheet("color: #444;")
        fl.addRow("입력 해상도 (px):", self.lbl_io_input_px)

        self.edit_out = QLineEdit(str(self._root / "results"))
        btn_out = QPushButton("폴더 선택…")
        btn_out.clicked.connect(self._pick_out_dir)
        fl.addRow("산출 폴더:", self._hbox(self.edit_out, btn_out))

        self.lbl_io_output_px = QLabel("—")
        self.lbl_io_output_px.setStyleSheet("color: #444;")
        self.lbl_io_output_px.setWordWrap(True)
        fl.addRow("산출 해상도 (미리보기):", self.lbl_io_output_px)

        lay.addWidget(g_paths)

        # 얼굴 복원 백엔드 선택
        g_rest = QGroupBox("얼굴 복원 백엔드")
        fl_rest = QFormLayout(g_rest)
        
        # 첫 번째 행: 라디오 버튼 + 체크박스
        h_row1 = QHBoxLayout()
        self.radio_restorer_rf = QRadioButton("RestoreFormer++")
        self.radio_restorer_cf = QRadioButton("CodeFormer")
        self.radio_restorer_cf.setChecked(True)  # 기본 CodeFormer 선택
        self.radio_restorer_rf.setToolTip("RestoreFormerPlusPlus/inference.py")
        self.radio_restorer_cf.setToolTip("CodeFormer/inference_codeformer.py")
        self._grp_restorer = QButtonGroup(self)
        self._grp_restorer.addButton(self.radio_restorer_rf)
        self._grp_restorer.addButton(self.radio_restorer_cf)
        self._grp_restorer.setExclusive(True)
        h_row1.addWidget(self.radio_restorer_rf)
        h_row1.addWidget(self.radio_restorer_cf)
        h_row1.addSpacing(20)
        h_row1.addStretch(1)
        fl_rest.addRow("백엔드:", h_row1)
        
        # config.json에서 기본값 로드
        # fidelity는 1.0(원본충실)을 기본으로 사용하여 사용자 설정 존중
        # upscale은 1(업스케일 없음)을 기본으로 사용
        try:
            from src.scoring.skin_scoring import _load_scoring_config
            config = _load_scoring_config()
            restoration = config.get("restoration", {})
            cf_fidelity_default = restoration.get("codeformer_fidelity", 1.0)
            cf_upscale_default = restoration.get("codeformer_upscale", 1)
            cf_additional_default = restoration.get("codeformer_additional", True)
            cf_bg_upsampler_default = restoration.get("codeformer_bg_upsampler", "none")
        except Exception as e:
            log.debug("복원 설정 로드 실패: %s, 기본값 사용", e)
            cf_fidelity_default = 1.0  # 원본 충실 기본
            cf_upscale_default = 1  # 업스케일 없음 기본
            cf_additional_default = True
            cf_bg_upsampler_default = "none"
        
        # 두 번째 행: fidelity + upscale
        h_row2 = QHBoxLayout()
        self.spin_cf_fidelity = QDoubleSpinBox()
        self.spin_cf_fidelity.setRange(0.0, 1.0)
        self.spin_cf_fidelity.setDecimals(2)
        self.spin_cf_fidelity.setValue(cf_fidelity_default)
        self.spin_cf_fidelity.setToolTip("0=강한 보정, 1=원본 충실")
        self.spin_cf_fidelity.setFixedWidth(70)
        h_row2.addWidget(QLabel("fidelity:"))
        h_row2.addWidget(self.spin_cf_fidelity)
        h_row2.addSpacing(15)
        self.spin_cf_upscale = QSpinBox()
        self.spin_cf_upscale.setRange(1, 4)
        self.spin_cf_upscale.setValue(cf_upscale_default)
        self.spin_cf_upscale.setFixedWidth(50)
        h_row2.addWidget(QLabel("업스케일:"))
        h_row2.addWidget(self.spin_cf_upscale)
        h_row2.addStretch(1)
        fl_rest.addRow("CF:", h_row2)

        # 세 번째 행: RF++ device 선택
        h_row3 = QHBoxLayout()
        self.combo_rf_device = QComboBox()
        self.combo_rf_device.addItems(["자동 감지", "CUDA", "CPU"])
        self.combo_rf_device.setCurrentIndex(0)  # 기본: 자동 감지
        self.combo_rf_device.setFixedWidth(120)
        self.combo_rf_device.setToolTip("RestoreFormer++ 실행 디바이스")
        h_row3.addWidget(QLabel("RF++ 디바이스:"))
        h_row3.addWidget(self.combo_rf_device)
        h_row3.addStretch(1)
        fl_rest.addRow("", h_row3)
        
        self.radio_restorer_rf.toggled.connect(self._sync_restorer_panels)
        self.radio_restorer_cf.toggled.connect(self._sync_restorer_panels)
        self._sync_restorer_panels()

        g_mode = QGroupBox("동작 모드")
        v_mode = QVBoxLayout(g_mode)
        v_mode.setSpacing(8)
        v_mode.setContentsMargins(10, 10, 10, 10)
        
        self.chk_restore = QCheckBox("복원 실행 (RF++ 또는 CodeFormer, 끄면 --no-restore)")
        self.chk_restore.setChecked(True)
        self.chk_restore_only = QCheckBox("복원 전용 — 원본 복사 후 RF만 (--restore-only)")
        self.chk_restore_only.setVisible(False)  # 숨김
        self.chk_text2img = QCheckBox("text2img만 (입력 이미지 무시, --text2img)")
        self.chk_text2img.setVisible(False)  # 숨김

        measurement_count = get_measurement_count()
        self.chk_restore_score_popup = QCheckBox(
            f"복원 후 점수 팝업 ({measurement_count}개 항목 + 피부건강지수 표시, --restore-score-popup)"
        )
        self.chk_restore_score_popup.setChecked(False)
        self.chk_restore_score_popup.setVisible(False)  # 숨김
        self.chk_llm_scores = QCheckBox(
            f"LLM에 점수 제공 ({measurement_count}개 항목 점수와 평가 기준 제공, --llm-scores)"
        )
        # config.json에서 기본값 로드
        gui_defaults = {}
        try:
            config_path = Path(__file__).resolve().parents[2] / "config" / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    gui_defaults = config.get("gui_defaults", {})
        except Exception as e:
            log.debug("GUI 기본값 로드 실패: %s", e)
        
        self.chk_llm_scores.setChecked(gui_defaults.get("llm_scores", False))
        self.chk_analyzer_score_tune = QCheckBox(
            f"복원 후 {measurement_count}개 항목 점수 자동 튜닝 (--no-analyzer-score-tune 으로 끄기)"
        )
        self.chk_analyzer_score_tune.setChecked(gui_defaults.get("analyzer_score_tune", True))
        self.chk_analyzer_score_tune.setToolTip(
            "켜면 복원(RF++/CF) 후 분석 점수 경향에 맞춰 CodeFormer "
            "fidelity·후처리(모공/톤/주름/트러블)를 가산합니다."
        )
        self.chk_score_safety_net = QCheckBox("점수 안전장치 (기준 점수 < 원본 점수 시 조정)")
        self.chk_score_safety_net.setChecked(gui_defaults.get("score_safety_net", True))
        self.chk_score_safety_net.setToolTip(
            "켜면 기준이미지 점수가 원본보다 1점 미만일 때 가장 가중치가 높은 항목 점수를 조정하여 피부건강지수가 1점 오르도록 함. "
            "기본 켬, 끄려면 --no-score-safety-net"
        )

        # 체크박스들을 횡으로 배치 (2행)
        h_row1 = QHBoxLayout()
        h_row1.addWidget(self.chk_restore)
        h_row1.addWidget(self.chk_restore_score_popup)
        h_row1.addWidget(self.chk_llm_scores)
        h_row1.addStretch(1)

        h_row2 = QHBoxLayout()
        h_row2.addWidget(self.chk_analyzer_score_tune)
        h_row2.addWidget(self.chk_score_safety_net)
        h_row2.addStretch(1)
        
        v_mode.addLayout(h_row1)
        v_mode.addLayout(h_row2)
        
        # 숨겨진 체크박스들은 레이아웃에 추가하지 않음 (기능 유지를 위해 객체는 존재)
        lay.addWidget(g_mode)
        lay.addSpacing(10)
        lay.addWidget(g_rest)

        lay.addStretch()

    def _build_preview_panel(self, parent_lay: QVBoxLayout) -> None:
        g = QGroupBox("미리보기 (원본 · 복원)")
        g.setMinimumHeight(self._PREVIEW_H + 128)
        outer = QVBoxLayout(g)
        row = QHBoxLayout()

        self.lbl_orig_cap = QLabel("원본")
        self.lbl_orig_cap.setStyleSheet("font-weight: bold;")
        self.lbl_orig_px = QLabel("—")
        self.lbl_orig_px.setStyleSheet("color: #888; font-size: 11px;")
        self.lbl_orig = ClickablePreviewLabel()
        self._style_preview_label(self.lbl_orig)

        self.lbl_rf_cap = QLabel("복원")
        self.lbl_rf_cap.setStyleSheet("font-weight: bold;")
        self.lbl_rf_px = QLabel("—")
        self.lbl_rf_px.setStyleSheet("color: #888; font-size: 11px;")
        self.lbl_rf = ClickablePreviewLabel()
        self._style_preview_label(self.lbl_rf)

        for cap, px_lbl, img in (
            (self.lbl_orig_cap, self.lbl_orig_px, self.lbl_orig),
            (self.lbl_rf_cap, self.lbl_rf_px, self.lbl_rf),
        ):
            col = QVBoxLayout()
            col.addWidget(cap)
            col.addWidget(px_lbl)
            col.addWidget(img, 0, Qt.AlignHCenter)
            row.addLayout(col, 1)
        outer.addLayout(row)

        btn_prev = QPushButton("미리보기 새로고침")
        btn_prev.setToolTip("현재 입력 경로·산출 폴더 기준으로 이미지를 다시 불러옵니다.")
        btn_prev.clicked.connect(self._refresh_previews)
        btn_all = QPushButton("크게보기")
        btn_all.setToolTip(
            "원본·기준 이미지를 한 창에 나란히 크게 표시합니다. "
            "각 썸네일을 클릭해도 개별 확대가 됩니다."
        )
        btn_all.clicked.connect(self._show_all_previews_large)
        row_btn = QHBoxLayout()
        row_btn.addStretch(1)
        row_btn.addWidget(btn_prev)
        row_btn.addWidget(btn_all)
        row_btn.addStretch(1)
        outer.addLayout(row_btn)
        parent_lay.addWidget(g)

    # ── 유틸 ───────────────────────────────────────────────────────────────
    @staticmethod
    def _hbox(widget: QWidget, btn: QWidget) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget, 1)
        lay.addWidget(btn)
        return w

    @staticmethod
    def _dspin(
        lo: float, hi: float, val: float,
        step: float = 0.05, dec: int = 2,
    ) -> QDoubleSpinBox:
        """QDoubleSpinBox 생성 헬퍼 — 탭 빌더 공용."""
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(dec)
        s.setValue(val)
        return s

    def _style_preview_label(self, lab: QLabel) -> None:
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setFixedSize(self._PREVIEW_W, self._PREVIEW_H)
        lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        lab.setStyleSheet("QLabel { border: 1px solid #888; background: #2a2a2a; color: #aaa; }")
        lab.setScaledContents(False)

    def _fit_pixmap(self, pm: QPixmap) -> QPixmap:
        if pm.isNull():
            return pm
        return pm.scaled(
            self._PREVIEW_W, self._PREVIEW_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _set_preview_image(self, lab: QLabel, path: Optional[Path], empty_text: str) -> None:
        clickable = lab if isinstance(lab, ClickablePreviewLabel) else None
        if path is None or not path.is_file():
            lab.setPixmap(QPixmap())
            lab.setText(empty_text)
            if clickable is not None:
                clickable.set_image_path(None)
            return
        pm = QPixmap(str(path))
        if pm.isNull():
            lab.setPixmap(QPixmap())
            lab.setText("이미지를 불러올 수 없습니다")
            if clickable is not None:
                clickable.set_image_path(None)
            return
        lab.setPixmap(self._fit_pixmap(pm))
        lab.setText("")
        if clickable is not None:
            clickable.set_image_path(path)

    def _resolve_preview_paths(self) -> tuple[Optional[Path], Optional[Path]]:
        """원본, 복원 순 경로(파일이 없으면 None)."""
        orig: Optional[Path] = None
        if not self.chk_text2img.isChecked():
            p = self.edit_input.text().strip()
            if p:
                cand = Path(p)
                if cand.is_file():
                    orig = cand
        mid: Optional[Path] = None
        out = Path(self.edit_out.text().strip() or ".")
        if out.is_dir():
            # 고객 아이디 우선, 없으면 원본 이미지 파일명 사용
            customer_id = self.edit_customer_id.text().strip()
            folder_name = customer_id if customer_id else _safe_output_stem_gui(
                self.edit_input.text().strip(),
                self.chk_text2img.isChecked(),
            )
            # [FIX ⑤] pipeline_core.final_pipeline_artifact_path 와 동일 우선순위
            mid = first_existing_file(
                out / f"01_restored_{folder_name}.png",        # 복원 결과
                out / f"00_restored_{folder_name}.png",        # 복원 결과
                out / "00_restored.png",
                out / "01_restored.png",
            )
        return orig, mid

    def _show_all_previews_large(self) -> None:
        orig, mid = self._resolve_preview_paths()
        _show_double_image_preview_dialog(self, (orig, mid))


    # ── 시그널 연결 ─────────────────────────────────────────────────────────
    def _connect_signals(self) -> None:
        self.chk_restore_only.toggled.connect(self._sync_mode_enables)
        self.chk_text2img.toggled.connect(self._sync_mode_enables)
        self.edit_input.textChanged.connect(lambda _: self._refresh_original_preview_only())
        self.edit_out.textChanged.connect(lambda _: self._refresh_previews())
        self.chk_text2img.toggled.connect(lambda _: self._refresh_original_preview_only())

    def _sync_mode_enables(self) -> None:
        ro = self.chk_restore_only.isChecked()
        t2i = self.chk_text2img.isChecked()
        self.chk_restore_only.setEnabled(not t2i)
        self.chk_text2img.setEnabled(not ro)
        if ro or t2i:
            self.chk_restore_only.setChecked(False)
            self.chk_text2img.setChecked(False)

    # ── 파일 다이얼로그 ─────────────────────────────────────────────────────
    def _pick_input_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "입력 이미지 선택",
            str(self._root / "images"),
            "이미지 (*.png *.jpg *.jpeg *.webp *.bmp);;모든 파일 (*.*)",
        )
        if path:
            self.edit_input.setText(path)
            self._refresh_original_preview_only()

    def _pick_input_json_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "설문 JSON 파일 선택",
            str(self._root),
            "JSON (*.json);;모든 파일 (*.*)",
        )
        if path:
            self.edit_input_json.setText(path)

    def _pick_out_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "산출 폴더", self.edit_out.text() or str(self._root))
        if path:
            self.edit_out.setText(path)

    def _sync_restorer_panels(self) -> None:
        use_rf = self.radio_restorer_rf.isChecked()
        # RF++ 선택 시에만 RF++ device 콤보박스 활성화
        self.combo_rf_device.setEnabled(use_rf)

    # ── 미리보기 ────────────────────────────────────────────────────────────
    def _refresh_original_preview_only(self) -> None:
        self.lbl_orig_cap.setText("원본")
        if self.chk_text2img.isChecked():
            self.lbl_orig_px.setText("—")
            self.lbl_io_input_px.setText("— (text2img)")
            self._set_preview_image(self.lbl_orig, None, "text2img 모드 (입력 원본 없음)")
            return
        p = self.edit_input.text().strip()
        if not p:
            self.lbl_orig_px.setText("—")
            self.lbl_io_input_px.setText("—")
            self._set_preview_image(self.lbl_orig, None, "입력 파일을 선택하세요")
            return
        inp = Path(p)
        px = _format_pixel_dims(inp if inp.is_file() else None)
        self.lbl_orig_px.setText(px)
        self.lbl_io_input_px.setText(px)
        self._set_preview_image(self.lbl_orig, inp, "파일 없음")

    def _refresh_previews(self) -> None:
        self._refresh_original_preview_only()
        out = Path(self.edit_out.text().strip() or ".")
        if not out.is_dir():
            self.lbl_rf_px.setText("—")
            self.lbl_io_output_px.setText("—")
            self._set_preview_image(self.lbl_rf, None, "산출 폴더 없음")
            return

        # 고객 아이디 우선, 없으면 원본 이미지 파일명 사용
        customer_id = self.edit_customer_id.text().strip()
        folder_name = customer_id if customer_id else _safe_output_stem_gui(
            self.edit_input.text().strip(),
            self.chk_text2img.isChecked(),
        )
        # [FIX ⑤] pipeline_core.final_pipeline_artifact_path 와 동일 우선순위
        prf = first_existing_file(
            out / f"01_restored_{folder_name}.png",        # 복원 결과
            out / f"00_restored_{folder_name}.png",        # 복원 결과
            out / "00_restored.png",
            out / "01_restored.png",
        )
        out_parts: list[str] = []
        if prf is not None:
            if prf.name.startswith("00_restored"):
                role = "RF++"
            else:
                role = "복원"
            self.lbl_rf_cap.setText(f"{role} ({prf.name})")
            self.lbl_rf_px.setText(_format_pixel_dims(prf))
            out_parts.append(f"복원 {self.lbl_rf_px.text()}")
            self._set_preview_image(self.lbl_rf, prf, "")
        else:
            self.lbl_rf_cap.setText(f"복원 (*_restored.png)")
            self.lbl_rf_px.setText("—")
            self._set_preview_image(self.lbl_rf, None, "실행 후 표시")

        self.lbl_io_output_px.setText("  |  ".join(out_parts) if out_parts else "—")

    # ── 검증 ────────────────────────────────────────────────────────────────
    def _validate(self) -> bool:
        if self.chk_restore_only.isChecked() and self.chk_text2img.isChecked():
            QMessageBox.warning(self, "설정 오류", "--restore-only 와 --text2img 은 함께 쓸 수 없습니다.")
            return False
        if not self.chk_text2img.isChecked():
            p = self.edit_input.text().strip()
            if not p:
                QMessageBox.warning(self, "입력 오류", "입력 이미지를 선택하거나 text2img 모드를 켜세요.")
                return False
            if not Path(p).is_file():
                QMessageBox.warning(self, "입력 오류", f"파일이 없습니다:\n{p}")
                return False
        return True

    # ── args 빌드 ───────────────────────────────────────────────────────────
    def _build_args(self) -> list[str]:
        """GUI 설정 → CLI args 변환. 경로에 공백 포함 시에도 QProcess 가 올바르게 처리함."""
        script = str(Path(__file__).resolve().parent / "skin_analysis_pipeline.py")
        args: list[str] = [script, "--cli"]

        # GUI 비동기 모드 확인 (환경 변수)
        import os
        gui_async = os.environ.get("GUI_ASYNC_MODE") == "1"
        if gui_async:
            args.append("--async")
            self._append_log("[GUI 파이프라인] 비동기 모드로 실행")
        else:
            self._append_log("[GUI 파이프라인] 동기 모드로 실행")

        if self.chk_text2img.isChecked():
            args.append("--text2img")
        else:
            args.extend(["-i", self.edit_input.text().strip()])

        # 설문 JSON 파일 추가
        input_json_path = self.edit_input_json.text().strip()
        if input_json_path:
            args.extend(["--input-json", input_json_path])

        # 고객 ID 추가 (없으면 입력 파일명 사용)
        customer_id = self.edit_customer_id.text().strip()
        if not customer_id:
            # 입력 파일명에서 파일명 추출 (확장자 제거)
            input_path = self.edit_input.text().strip()
            if input_path:
                customer_id = Path(input_path).stem
        if customer_id:
            args.extend(["--customer-id", customer_id])

        args.extend(["--out-dir", self.edit_out.text().strip()])

        # JSON 저장 활성화 (GUI 모드에서도 결과 JSON 저장)
        args.append("--save-json")

        if self.chk_restore_only.isChecked():
            args.append("--restore-only")
        if not self.chk_restore.isChecked():
            args.append("--no-restore")
        
        # GUI 모드에서 비교창 열기 (비동기 모드 제외)
        if not gui_async:
            args.append("--restore-score-popup")
        if self.chk_llm_scores.isChecked():
            args.append("--llm-scores")  # 내부 측정 점수 제공
        if not self.chk_analyzer_score_tune.isChecked():
            args.append("--no-analyzer-score-tune")
        # 점수 안전장치 끄기 — 기본 켜짐이므로 체크 해제 시만 인자 전달
        if not self.chk_score_safety_net.isChecked():
            args.append("--no-score-safety-net")

        if self.radio_restorer_cf.isChecked():
            args.extend(["--restorer", Restorer.CODEFORMER.value])
            args.extend([
                "--cf-fidelity", str(self.spin_cf_fidelity.value()),
                "--cf-upscale", str(self.spin_cf_upscale.value()),
            ])
        else:
            args.extend(["--restorer", Restorer.RESTOREFORMER.value])
            # RF++ device 설정
            rf_device_idx = self.combo_rf_device.currentIndex()
            if rf_device_idx == 1:  # CUDA
                args.append("--restoreformer-device")
                args.append("cuda")
            elif rf_device_idx == 2:  # CPU
                args.append("--restoreformer-device")
                args.append("cpu")
            # 0이면 자동 감지 (인자 전달 안 함)

        return args

    # ── 실행 / 중지 ─────────────────────────────────────────────────────────
    def _append_log(self, text: str) -> None:
        self.log.appendPlainText(text.rstrip("\n"))
        # 로그 파일에도 기록
        log.info(text.rstrip("\n"))

    def _update_log_file_with_customer_id(self, customer_id: str) -> None:
        """customer_id를 사용하여 로그 파일명을 변경합니다."""
        import logging
        from datetime import datetime
        from pathlib import Path
        import shutil
        
        # 현재 로그 파일 핸들러 찾기
        root_logger = logging.getLogger()
        file_handler = None
        for handler in root_logger.handlers:
            if isinstance(handler, logging.FileHandler):
                file_handler = handler
                break
        
        if file_handler:
            # 새 로그 파일 경로 생성
            old_path = Path(file_handler.baseFilename)
            log_dir = old_path.parent
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_path = log_dir / f"skinlens_gui_{customer_id}_{timestamp}.log"
            
            # 기존 핸들러 제거 및 닫기
            root_logger.removeHandler(file_handler)
            file_handler.close()
            
            # 기존 로그 파일 내용을 새 파일로 복사
            if old_path.exists():
                shutil.copy2(old_path, new_path)
                old_path.unlink()  # 기존 파일 삭제
            
            # 새 핸들러 추가
            new_handler = logging.FileHandler(new_path, encoding='utf-8')
            new_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s:%(pathname)s:%(lineno)d: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            new_handler.setFormatter(formatter)
            root_logger.addHandler(new_handler)
            
            log.info(f"로그 파일 변경: {old_path} -> {new_path}")

    def _run_pipeline(self) -> None:
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            return
        if not self._validate():
            return

        args = self._build_args()
        
        # customer_id 추출 (로그 파일명 변경용)
        customer_id = self.edit_customer_id.text().strip()
        if not customer_id:
            input_path = self.edit_input.text().strip()
            if input_path:
                customer_id = Path(input_path).stem
        
        # customer_id가 있으면 로그 파일 핸들러 교체
        if customer_id:
            self._update_log_file_with_customer_id(customer_id)
        
        self._append_log("=== 명령 ===")
        self._append_log(f'"{sys.executable}" ' + " ".join(f'"{a}"' if " " in a else a for a in args))
        self._append_log(f"[CUDA] {format_torch_cuda_status()}")
        self._append_log("=== 출력 ===")

        self._process = QProcess(self)
        self._process.setProgram(sys.executable)
        self._process.setArguments(args)
        self._process.setWorkingDirectory(str(self._root))
        # [FIX ②] stdout/stderr 통합 — 서브프로세스(RF++/CF) stderr 출력도 로그창에 표시
        # 순서 보장: 분리 처리 시 버퍼 타이밍 차이로 로그가 뒤섞이는 문제 방지
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        # 자식 프로세스는 로그 파일에 기록하지 않음 (GUI 로그창만 기록)
        env.insert("SKINLENS_CHILD_PROCESS", "1")
        self._process.setProcessEnvironment(env)

        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)  # 진행 표시 시작
        self._process.start()

    def _on_stdout(self) -> None:
        if self._process:
            data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
            for line in data.splitlines():   # [FIX ⑦] 멀티라인 분리 출력
                if line.strip():
                    self._append_log(line)

    def _on_stderr(self) -> None:
        # [FIX ②] MergedChannels 설정으로 stderr 가 stdout 으로 통합되어 이 슬롯은 호출되지 않음.
        # 하위 호환·수동 연결 시 대비해 구현은 유지.
        if self._process:
            data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
            for line in data.splitlines():
                if line.strip():
                    self._append_log(line)

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)  # 진행 표시 종료
        self._append_log(f"=== 종료 코드: {code} ({status}) ===")
        self._process = None
        
        self._refresh_previews()

        # 파이프라인 완료 후 측정항목 비교 자동 실행
        if code == 0:  # 성공 시에만 실행
            try:
                orig = Path(self.edit_input.text().strip()) if not self.chk_text2img.isChecked() else None
                if orig and orig.is_file():
                    # 산출 폴더에서 기준 이미지 찾기
                    out_dir = Path(self.edit_out.text().strip())
                    # 고객 아이디 우선, 없으면 원본 이미지 파일명 사용
                    customer_id = self.edit_customer_id.text().strip()
                    folder_name = customer_id if customer_id else orig.stem
                    # 이미지별 폴더 구조로 경로 업데이트
                    image_folder = out_dir / folder_name
                    # 기준 이미지 경로 우선순위 (skin_measurement_chart_dialog과 동일)
                    ideal_candidates = [
                        image_folder / f"01_restored_{folder_name}.png",  # RESTORE_ONLY 모드 기본
                        image_folder / f"00_restored_{folder_name}.png",
                        out_dir / f"01_restored_{folder_name}.png",  # 하위 호환성
                        out_dir / f"00_restored_{folder_name}.png",
                        out_dir / "00_restored.png",
                        out_dir / "01_restored.png",
                    ]
                    ideal = None
                    for candidate in ideal_candidates:
                        if candidate.is_file():
                            ideal = candidate
                            break
                    if ideal and ideal.is_file():
                        self._append_log("[진행] 측정항목 비교 다이얼로그 표시")
                        # 별도 프로세스로 안전하게 실행 (프로세스 격리)
                        self._launch_compare_subprocess(orig, ideal)
                    else:
                        self._append_log("[경고] 기준 이미지를 찾을 수 없습니다.")
            except Exception as e:
                self._append_log(f"[경고] 측정항목 비교 다이얼로그 표시 실패: {e}")

    def _stop_pipeline(self) -> None:
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.kill()
            self._append_log("=== 사용자 중지 ===")
            self.progress.setVisible(False)

    def _launch_compare_subprocess(self, orig: Path, ideal: Path) -> None:
        """측정항목 비교 다이얼로그를 별도 프로세스로 안전하게 실행."""
        try:
            # skin_analysis_pipeline.py 경로 확인
            current_file = Path(__file__).parent / "skin_analysis_pipeline.py"
            
            if not current_file.exists():
                self._append_log("[오류] 비교 다이얼로그 실행 파일을 찾을 수 없습니다.")
                return

            # QProcess로 별도 프로세스 실행
            proc = QProcess(self)
            proc.setProgram(str(Path(sys.executable).resolve()))
            proc_args = [
                "-B",  # .pyc 파일 생성 비활성화 (캐시 문제 방지)
                str(current_file),
                "--compare",
                str(orig.resolve()),
                str(ideal.resolve())
            ]
            # JSON 파일 경로 찾기 (메인 프로세스에서 저장된 LLM 결과)
            json_path = None
            staged_files = list(ideal.parent.glob("00_input_*.png"))
            if staged_files:
                input_filename = staged_files[0].stem
            else:
                input_filename = orig.stem
            json_path = ideal.parent / f"{input_filename}.json"
            if json_path.exists():
                proc_args.append("--llm-json")
                proc_args.append(str(json_path))
                log.debug(f"JSON 파일 경로 전달: {json_path}")
                self._append_log(f"[DEBUG] JSON 파일 경로 전달: {json_path}")
                # --llm-scores도 전달 (서브프로세스에서 LLM 점수 표시용)
                if self.chk_llm_scores.isChecked():
                    proc_args.append("--llm-scores")
            else:
                log.debug(f"JSON 파일을 찾을 수 없음: {json_path}")
                self._append_log(f"[DEBUG] JSON 파일을 찾을 수 없음: {json_path}")
            
            log.debug("proc_args = %s", proc_args)
            self._append_log(f"[DEBUG] 실행 인자: {proc_args}")
            
            proc.setArguments(proc_args)
            
            # 출력 처리 (stdout/stderr 모두)
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            proc.readyReadStandardOutput.connect(lambda: self._on_compare_stdout(proc))
            proc.finished.connect(lambda code, status: self._on_compare_finished(code, status))
            
            self._compare_process = proc
            proc.start()
            measurement_count = get_measurement_count()
            self._append_log(f"[{measurement_count}비교] 서브프로세스 시작: {current_file.name}")
            self._append_log(f"[{measurement_count}비교] 인자: {' '.join(proc_args)}")
        except Exception as e:
            import traceback
            self._append_log(f"[오류] 비교 다이얼로그 서브프로세스 시작 실패: {e}")
            self._append_log(f"[오류] 상세: {traceback.format_exc()}")

    def _on_compare_stdout(self, proc: QProcess) -> None:
        """비교 서브프로세스 stdout/stderr 처리."""
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        measurement_count = get_measurement_count()
        for line in data.splitlines():
            if line.strip():
                self._append_log(f"[{measurement_count}비교] " + line)

    def _on_compare_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        """비교 서브프로세스 종료 처리."""
        measurement_count = get_measurement_count()
        self._append_log(f"[{measurement_count}비교] 종료 code={code} status={status}")
        self._compare_process = None


def main():
    """GUI 메인 진입점."""
    app = QApplication(sys.argv)
    window = SkinAnalysisWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
