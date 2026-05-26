"""
analysis_worker.py — 분석 백그라운드 작업자 모듈

피부 분석을 백그라운드 스레드에서 실행하는 Worker 클래스를 제공합니다.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, Signal

from src.scoring.skin_scoring import SkinAnalyzer
from src.gui.dialog_utils import _prepare_analysis_path, _dlog

log = logging.getLogger(__name__)


class _AnalyzeWorker(QObject):
    """듀얼 이미지 분석 백그라운드 작업자"""
    finished = Signal(object, object)  # orig_result, ideal_result
    failed = Signal(str)
    progress = Signal(str)  # 메인 스레드에서 QProgressDialog 라벨 갱신

    def __init__(
        self,
        orig_path: str,
        ideal_path: str,
        *,
        max_side: int,
        use_ref_stat: bool,
    ) -> None:
        super().__init__()
        self._orig_path = orig_path
        self._ideal_path = ideal_path
        self._max_side = max_side
        self._use_ref_stat = use_ref_stat

    def run(self) -> None:
        t0 = time.perf_counter()
        tmp_to_remove: List[Path] = []
        try:
            log.info("워커 스레드 run() 시작")
            # 주의: prepare_analyzer_logging_for_gui() 는 백그라운드 스레드에서 부르면
            # root 로거의 Qt 핸들러와 맞물려 이벤트 루프가 멈출 수 있어 호출하지 않는다.
            self.progress.emit("피부 분석: 분석기 준비…")
            _dlog("워커 run() 시작 (로깅 GUI 통합 생략)", t0=t0)

            self.progress.emit("피부 분석: 분석기 준비…")
            _dlog("SkinAnalyzer() 생성 시작", t0=t0)
            an = SkinAnalyzer()
            _dlog("SkinAnalyzer() 생성 완료", t0=t0)

            orig_in, tmp_o = _prepare_analysis_path(
                Path(self._orig_path), "orig", self._max_side, t0=t0,
            )
            if tmp_o is not None:
                tmp_to_remove.append(tmp_o)
            ideal_in, tmp_i = _prepare_analysis_path(
                Path(self._ideal_path), "ideal", self._max_side, t0=t0,
            )
            if tmp_i is not None:
                tmp_to_remove.append(tmp_i)

            self.progress.emit(
                f"피부 분석: 보정 이미지 처리 중…\n{Path(self._ideal_path).name}",
            )
            _dlog(f"analyze_all(보정) 시작 path={ideal_in!r} ref_stat=없음(기준 생성)", t0=t0)
            ideal = an.analyze_all(ideal_in, debug=False, clahe_preprocessed=False)
            _dlog(
                f"analyze_all(보정) 완료 overall={ideal.get('overall_score')!r}",
                t0=t0,
            )

            ref = ideal.get("skin_stat") if self._use_ref_stat else None

            self.progress.emit(
                f"피부 분석: 원본 처리 중…\n{Path(self._orig_path).name}",
            )
            _dlog(
                f"analyze_all(원본) 시작 path={orig_in!r} "
                f"ref_stat={'있음' if ref is not None else '없음(비활성 또는 없음)'}",
                t0=t0,
            )
            try:
                orig = an.analyze_all(
                    orig_in,
                    debug=False,
                    clahe_preprocessed=False,
                    ref_stat=ref,
                )
            except TypeError as te:
                # skin_scoring 버전에 따라 ref_stat 파라미터가 없을 수 있다.
                if "ref_stat" not in str(te):
                    raise
                _dlog("analyze_all(ref_stat) 미지원 버전 감지 → 원본 ref_stat 없이 재시도", t0=t0)
                orig = an.analyze_all(
                    orig_in,
                    debug=False,
                    clahe_preprocessed=False,
                )
            _dlog(
                f"analyze_all(원본) 완료 overall={orig.get('overall_score')!r}",
                t0=t0,
            )

            self.progress.emit("피부 분석: 결과 표시 준비…")
            self.finished.emit(orig, ideal)
        except Exception as e:
            _dlog(f"예외: {type(e).__name__}: {e}", t0=t0)
            # [FIX freeze] log.exception 대신 _dlog + traceback 사용.
            # GUI Qt 핸들러가 root 로거에 붙어 있으면 워커 스레드에서
            # log.exception 호출 시 GUI 스레드 교착이 발생할 수 있음.
            import traceback as _tb
            _dlog(_tb.format_exc(), t0=t0)
            self.failed.emit(str(e))
        finally:
            for tp in tmp_to_remove:
                try:
                    tp.unlink(missing_ok=True)
                except OSError as e:
                    log.debug("임시 파일 삭제 실패: %s", e)
