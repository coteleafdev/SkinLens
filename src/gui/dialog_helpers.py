"""
dialog_helpers.py — 다이얼로그 헬퍼 모듈

스레드 관리, 진입점 함수, 경로 해결 함수를 제공합니다.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QCoreApplication, QEventLoop, QThread, Qt, QTimer
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from src.scoring.skin_scoring import SkinAnalyzer
from src.gui.analysis_worker import _AnalyzeWorker
from src.gui.dialog_utils import (
    _env_debug_enabled,
    _analysis_hard_timeout_seconds,
    _OPEN_COMPARE_DIALOGS,
    _COMPARE_THREADS,
    _COMPARE_WORKERS,
)
from src.gui.compare_dialog import SkinMeasurementCompareDialog
from src.skin.core.config_parser import get_measurement_count

log = logging.getLogger(__name__)


def _skin_compare_attach(parent: Optional, thread: QThread, timer: QTimer) -> None:
    """SkinAnalysisWindow.closeEvent 에서 스레드·타이머를 끊을 수 있도록 참조를 건다."""
    if parent is None:
        return
    try:
        parent._skin_compare_thread = thread  # type: ignore[attr-defined]
        parent._skin_compare_timer = timer  # type: ignore[attr-defined]
    except Exception as e:
        log.debug("스레드/타이머 부착 실패: %s", e)


def _skin_compare_detach(parent: Optional) -> None:
    if parent is None:
        return
    try:
        parent._skin_compare_thread = None  # type: ignore[attr-defined]
        parent._skin_compare_timer = None  # type: ignore[attr-defined]
    except Exception as e:
        log.debug("스레드/타이머 분리 실패: %s", e)


def show_skin_measurement_compare_dialog(
    parent: Optional,
    orig_path: Path,
    ideal_path: Path,
    llm_scores: bool = False,  # LLM 점수 제공 여부 (기본값: False)
    modal: bool = False,  # 모달 표시 여부 (서브프로세스용)
    llm_json_path: Path = None,  # LLM JSON 파일 경로 (메인 프로세스에서 전달)
) -> Optional:
    """원본·보정 PNG 경로로 분석 후 다이얼로그 표시.
    
    Returns:
        modal=True인 경우 다이얼로그 객체 반환, modal=False인 경우 None 반환
    """
    import time
    start_time = time.time()
    log.debug(f"show_skin_measurement_compare_dialog 시작: modal={modal}, llm_scores={llm_scores}, llm_json_path={llm_json_path} (True=점수 제공, False=점수 미제공)")
    
    # modal=True인 경우: 동기로 분석 수행 (서브프로세스용)
    if modal:
        log.debug("modal=True: 동기 분석 모드로 전환")
        try:
            # 분석 실행 (동기)
            analyzer = SkinAnalyzer()
            log.info("피부 비교 분석 시작 (동기): orig=%s ideal=%s", orig_path, ideal_path)
            analysis_start = time.time()
            result_orig = analyzer.analyze_all(str(orig_path.resolve()))
            result_ideal = analyzer.analyze_all(str(ideal_path.resolve()))
            analysis_time = time.time() - analysis_start
            log.debug(f"modal=True: 피부 분석 완료, 소요시간 {analysis_time:.2f}초")
            log.debug(f"modal=True: result_orig keys={list(result_orig.keys())}")
            log.debug(f"modal=True: result_ideal keys={list(result_ideal.keys())}")
            log.info("피부 비교 분석 완료 (동기)")
            
            # JSON 파일 경로 결정: llm_json_path가 있으면 우선 사용
            gemini_orig_result = None
            gemini_ideal_result = None
            if llm_json_path and llm_json_path.exists():
                results_json_path = llm_json_path
                log.debug(f"modal=True: 전달된 JSON 파일 사용: {results_json_path}")
            else:
                # 입력 이미지 파일명으로 JSON 읽기
                # 스테이징된 파일명(00_input_*)이 있으면 우선 사용
                staged_files = list(ideal_path.parent.glob("00_input_*.png"))
                if staged_files:
                    input_filename = staged_files[0].stem  # 확장자 제거 (예: 00_input_색소침착_트러블_홍조)
                else:
                    input_filename = orig_path.stem  # 원본 파일명
                results_json_path = ideal_path.parent / f"{input_filename}.json"
                log.debug(f"modal=True: 자동 감지된 JSON 파일: {results_json_path}")
            
            if results_json_path.exists():
                try:
                    with open(results_json_path, "r", encoding="utf-8") as f:
                        results_data = json.load(f)
                    gemini_analysis = results_data.get("gemini_analysis", {})
                    if "original" in gemini_analysis and "restored" in gemini_analysis:
                        # Gemini 결과를 SkinGeminiReport 객체로 변환
                        from src.llm.llm_formatters import SkinLLMReport, MetricOpinion
                        
                        orig_data = gemini_analysis["original"]
                        gemini_orig_result = SkinLLMReport(
                            overall_opinion=orig_data.get("overall_opinion", ""),
                            overall_score=orig_data.get("overall_score", 0),
                            perceived_age=orig_data.get("perceived_age", 0),
                            metric_opinions=[
                                MetricOpinion(
                                    key=m.get("key", ""),
                                    display_name=m["display_name"],
                                    category=m.get("category", ""),
                                    score=m["score"],
                                    opinion=m["opinion"],
                                    grade=m["grade"]
                                )
                                for m in orig_data.get("metric_opinions", [])
                            ],
                            raw_response=orig_data.get("raw_response", "")
                        )
                        
                        ideal_data = gemini_analysis["restored"]
                        gemini_ideal_result = SkinLLMReport(
                            overall_opinion=ideal_data.get("overall_opinion", ""),
                            overall_score=ideal_data.get("overall_score", 0),
                            perceived_age=ideal_data.get("perceived_age", 0),
                            metric_opinions=[
                                MetricOpinion(
                                    key=m.get("key", ""),
                                    display_name=m["display_name"],
                                    category=m.get("category", ""),
                                    score=m["score"],
                                    opinion=m["opinion"],
                                    grade=m["grade"]
                                )
                                for m in ideal_data.get("metric_opinions", [])
                            ],
                            raw_response=ideal_data.get("raw_response", "")
                        )
                        log.debug(f"modal=True: Gemini 결과 로드 완료 ({results_json_path.name})")
                except Exception as e:
                    log.debug(f"modal=True: results.json 읽기 실패: {e}")
            
            # 다이얼로그 생성
            log.debug(f"modal=True: 다이얼로그 생성 시작, llm_scores={llm_scores} (True=점수 제공, False=점수 미제공)")
            dialog_start = time.time()
            # 안전장치 적용 여부 확인
            safety_net_applied = result_ideal.get("safety_net_adjusted", False)
            # JSON에서 LLM 결과를 성공적으로 읽었으면 LLM 재호출 방지
            # llm_json_path가 전달되었고 JSON에서 읽었으면 무조건 False로 설정
            # 빈 결과여도 JSON에서 읽었으면 LLM 재호출 방지 (LLM 호출은 1회만 수행)
            if llm_json_path and llm_json_path.exists() and gemini_orig_result is not None and gemini_ideal_result is not None:
                llm_provide_scores = False
                log.debug(f"modal=True: JSON에서 LLM 결과 읽음, llm_provide_scores=False (LLM 재호출 방지)")
            else:
                llm_provide_scores = True  # JSON에서 읽지 못했으면 항상 LLM 소견 생성
                log.debug(f"modal=True: JSON에서 LLM 결과를 읽지 못함, llm_provide_scores=True (LLM 소견 생성)")
            dlg = SkinMeasurementCompareDialog(
                parent, orig_path, ideal_path,
                result_orig,  # type: ignore[arg-type]
                result_ideal,  # type: ignore[arg-type]
                llm_scores=llm_scores,  # --llm-scores true면 점수 제공
                llm_provide_scores=llm_provide_scores,  # JSON에서 읽었으면 False로 설정하여 LLM 재호출 방지
                llm_orig_report=gemini_orig_result,
                llm_ideal_report=gemini_ideal_result,
                safety_net_applied=safety_net_applied,
            )
            dialog_time = time.time() - dialog_start
            log.debug(f"modal=True: 다이얼로그 생성 완료, 소요시간 {dialog_time:.2f}초, dlg._llm_scores={dlg._llm_scores} (True=점수 제공, False=점수 미제공)")
            
            total_time = time.time() - start_time
            log.debug(f"modal=True: 전체 처리 완료, 총 소요시간 {total_time:.2f}초 (분석: {analysis_time:.2f}초, 다이얼로그: {dialog_time:.2f}초)")
            return dlg
        except Exception as e:
            total_time = time.time() - start_time
            log.debug(f"modal=True: 동기 분석 실패, 소요시간 {total_time:.2f}초, 오류: {e}")
            import traceback
            log.debug(f"traceback: {traceback.format_exc()}")
            if parent:
                QMessageBox.critical(parent, "분석 오류", f"분석 실패:\n{str(e)}")
            return None
    
    # modal=False인 경우: 기존 비동기 스레드 방식 사용
    try:
        if not orig_path.is_file():
            if parent:
                QMessageBox.warning(parent, "분석", f"원본 파일이 없습니다:\n{orig_path}")
            else:
                print(f"원본 파일이 없습니다: {orig_path}", file=sys.stderr)
            return
        if not ideal_path.is_file():
            if parent:
                QMessageBox.warning(parent, "분석", f"보정(이상) 이미지가 없습니다:\n{ideal_path}")
            else:
                print(f"보정(이상) 이미지가 없습니다: {ideal_path}", file=sys.stderr)
            return
        log.debug("파일 확인 완료: orig=%s, ideal=%s", orig_path.name, ideal_path.name)

        measurement_count = get_measurement_count()
        prog = QProgressDialog(f"피부 분석 실행 중… ({measurement_count}항목×2)", "중단", 0, 0, parent or None)
        # 항상 ApplicationModal로 설정하여 이벤트 루프 문제 방지
        prog.setWindowModality(Qt.WindowModality.ApplicationModal)
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        prog.show()
        QCoreApplication.processEvents()

        t_ui = time.perf_counter()
        log.info(
            "피부 비교 분석 시작 orig=%s ideal=%s debug_env=%s",
            orig_path,
            ideal_path,
            _env_debug_enabled(),
        )
        # [FIX] 파이프라인과 동일한 설정 사용
        # 파이프라인에서는 이미지 크기 조정을 내부적으로 처리하므로 max_side 제한 없음
        max_side = 0  # 파이프라인과 동일한 설정 (제한 없음)
        # 파이프라인에서는 ref_stat을 전달하지 않으므로 여기서도 비활성화
        use_ref = False  # 파이프라인과 동일한 설정
        if _env_debug_enabled():
            print(
                f"[skin_measurement_chart] UI: ProgressDialog 표시 후 processEvents "
                f"(+{time.perf_counter() - t_ui:.3f}s) — "
                f"max_side={max_side} ref_stat={use_ref}",
                flush=True,
            )

        thread = QThread()
        worker = _AnalyzeWorker(
            str(orig_path.resolve()),
            str(ideal_path.resolve()),
            max_side=max_side,
            use_ref_stat=use_ref,
        )
        worker.moveToThread(thread)
        # 진행 중 GC 로 워커/스레드가 사라지지 않도록 참조 유지
        prog.setProperty("_skin_an_thread", thread)
        prog.setProperty("_skin_an_worker", worker)
        # 전역 리스트에 추가하여 조기 파괴 방지
        _COMPARE_THREADS.append(thread)
        _COMPARE_WORKERS.append(worker)

        progress_holder: list[str] = [""]
        t_wall = time.time()
        hard_timeout_sec = _analysis_hard_timeout_seconds()
        aborted: list[bool] = [False]
        cleaned: list[bool] = [False]
        llm_scores_holder: list[bool] = [llm_scores]  # 클로저로 전달
        modal_holder: list[bool] = [modal]  # 모달 표시 여부
        dialog_holder: list[Optional] = [None]  # 다이얼로그 객체 저장 (modal=True용)

        def _cleanup_once(*, terminate_thread: bool = False) -> None:
            if cleaned[0]:
                return
            cleaned[0] = True
            try:
                tick_timer.stop()
            except Exception:
                log.debug("tick_timer.stop() 실패")
            _skin_compare_detach(parent)
            try:
                prog.blockSignals(True)
                prog.close()
            except Exception:
                log.debug("프로그레스 바 종료 실패")
            # 전역 리스트에서 제거
            if thread in _COMPARE_THREADS:
                _COMPARE_THREADS.remove(thread)
            if worker in _COMPARE_WORKERS:
                _COMPARE_WORKERS.remove(worker)
            # 스레드 종료 시도 (GUI 블로킹 방지를 위해 wait 제거)
            try:
                if terminate_thread and thread.isRunning():
                    thread.terminate()
                else:
                    thread.quit()
                # wait 제거: GUI 블로킹 방지
                # thread.wait(3000)  # 최대 3초 대기
                # 스레드가 여전히 실행 중이면 강제 종료
                if thread.isRunning():
                    thread.terminate()
                # wait 제거: GUI 블로킹 방지
                # thread.wait(1000)  # 추가 1초 대기
            except Exception:
                log.debug("스레드 종료 실패")
            # 워커 삭제
            try:
                worker.deleteLater()
            except Exception:
                log.debug("워커 삭제 실패")
            # 스레드 삭제
            try:
                thread.deleteLater()
            except Exception:
                log.debug("스레드 삭제 실패")

        def _abort_analysis(reason: str) -> None:
            if aborted[0]:
                return
            aborted[0] = True
            log.warning("피부 비교 분석 중단: %s", reason)
            _cleanup_once(terminate_thread=True)

        def on_worker_progress(s: str) -> None:
            progress_holder[0] = s
            sec = int(time.time() - t_wall)
            prog.setLabelText(f"{s}\n(경과 약 {sec}초)")

        worker.progress.connect(
            on_worker_progress,
            Qt.ConnectionType.QueuedConnection,
        )

        tick_timer = QTimer(parent or None)
        tick_timer.setInterval(400)

        def on_tick() -> None:
            if not prog.isVisible():
                tick_timer.stop()
                return
            if hard_timeout_sec > 0 and (time.time() - t_wall) >= hard_timeout_sec:
                _abort_analysis(f"hard timeout({hard_timeout_sec}s)")
                if parent:
                    QMessageBox.critical(
                        parent,
                        "분석 오류",
                        f"피부 분석이 {hard_timeout_sec}초를 넘겨 중단했습니다.\n"
                        "이미지가 큰 경우 AI_SKIN_ANALYSIS_MAX_SIDE 를 낮춰 다시 시도하세요.",
                    )
                else:
                    print(
                        f"피부 분석이 {hard_timeout_sec}초를 넘겨 중단했습니다.\n"
                        "이미지가 큰 경우 AI_SKIN_ANALYSIS_MAX_SIDE 를 낮춰 다시 시도하세요.",
                        file=sys.stderr
                    )
                return
            base = progress_holder[0] or "피부 분석 실행 중…"
            sec = int(time.time() - t_wall)
            prog.setLabelText(
                f"{base}\n(경과 약 {sec}초 · 동일 해상도여도 분석에 수 분 걸릴 수 있음)",
            )

        tick_timer.timeout.connect(on_tick)
        tick_timer.start()

        # worker.finished / failed 가 PySide 에서 파이썬 슬롯일 때 워커 스레드에서
        # 실행될 수 있음 → tick_timer.stop·GUI·thread.wait 가 잘못된 스레드에서 호출되고
        # (터미널: QObject::killTimer: Timers cannot be stopped from another thread)
        # 워커 스레드에서 thread.wait() 하면 자기 자신 대기로 무한 정지.
        # QTimer.singleShot(0, prog, …) 로 반드시 GUI 스레드에서 마무리한다.
        def _finish_on_gui_thread_success(o: object, i: object) -> None:
            if aborted[0] or cleaned[0]:
                log.debug("_finish_on_gui_thread_success: 이미 중단됨")
                return
            aborted[0] = True
            elapsed_time = time.time() - t_wall
            log.debug("_finish_on_gui_thread_success: 다이얼로그 표시 예약, 소요시간 %.2f초", elapsed_time)
            log.info("피부 비교 분석 완료 → 결과 다이얼로그 표시")
            _cleanup_once(terminate_thread=False)
            # 다이얼로그 생성과 표시를 비동기로 처리하여 프리징 방지
            QTimer.singleShot(0, lambda: _show_compare_dialog(parent, orig_path, ideal_path, o, i))

        def _show_compare_dialog(parent: Optional, orig_path: Path, ideal_path: Path, o: object, i: object) -> None:
            """비교 다이얼로그를 비동기로 표시."""
            try:
                log.debug("다이얼로그 생성 시작, llm_scores=%s (True=점수 제공, False=점수 미제공)", llm_scores_holder[0])
                dialog_start = time.time()
                # 안전장치 적용 여부 확인
                safety_net_applied = i.get("safety_net_adjusted", False) if hasattr(i, 'get') else False
                dlg = SkinMeasurementCompareDialog(
                    parent, orig_path, ideal_path,
                    o,  # type: ignore[arg-type]
                    i,  # type: ignore[arg-type]
                    llm_scores=llm_scores_holder[0],  # --llm-scores true면 점수 제공
                    llm_provide_scores=True,  # 항상 LLM 소견 생성
                    safety_net_applied=safety_net_applied,
                )
                dialog_time = time.time() - dialog_start
                log.debug("다이얼로그 생성 완료, 소요시간 %.2f초, dlg._llm_scores=%s (True=점수 제공, False=점수 미제공)", dialog_time, dlg._llm_scores)
                
                total_time = time.time() - t_wall
                log.debug("modal=False: 전체 처리 완료, 총 소요시간 %.2f초 (분석: %.2f초, 다이얼로그: %.2f초)", total_time, total_time - dialog_time, dialog_time)
                
                # 다이얼로그를 완전히 독립적인 윈도우로 설정 (메인 창 닫기 방지)
                dlg.setWindowFlags(
                    dlg.windowFlags() |
                    Qt.WindowType.WindowStaysOnTopHint |
                    Qt.WindowType.Window
                )
                _OPEN_COMPARE_DIALOGS.append(dlg)
                dlg.destroyed.connect(lambda *_: _OPEN_COMPARE_DIALOGS.remove(dlg) if dlg in _OPEN_COMPARE_DIALOGS else None)
                
                # 모달 표시 여부에 따라 다르게 처리
                if modal_holder[0]:
                    # 모달 표시: 다이얼로그 객체 저장하여 반환
                    dialog_holder[0] = dlg
                    log.debug("다이얼로그 모달 저장 완료: dialog_holder[0]=%s", dlg)
                else:
                    # modeless 표시
                    log.debug("다이얼로그 show() 호출")
                    dlg.show()
                    log.debug("다이얼로그 show() 완료")
                
                # 이벤트 처리하여 다이얼로그가 즉시 표시되도록 함
                QCoreApplication.processEvents()
                log.debug("다이얼로그 표시 완료")
            except Exception as e:
                import traceback
                log.debug("다이얼로그 표시 실패: %s", e)
                log.debug("traceback: %s", traceback.format_exc())
                log.error("비교 다이얼로그 표시 실패: %s", e)

        def _finish_on_gui_thread_error(msg: str) -> None:
            if aborted[0] or cleaned[0]:
                return
            aborted[0] = True
            elapsed_time = time.time() - t_wall
            log.debug("modal=False: 피부 분석 실패, 소요시간 %.2f초, 오류: %s", elapsed_time, msg)
            log.error("피부 비교 분석 실패: %s", msg)
            _cleanup_once(terminate_thread=False)
            if parent:
                QMessageBox.critical(parent, "분석 오류", msg)
            else:
                print(f"분석 오류: {msg}", file=sys.stderr)

        def on_ok(o: object, i: object) -> None:
            if aborted[0] or cleaned[0]:
                return
            QTimer.singleShot(
                0,
                prog,
                lambda o=o, i=i: _finish_on_gui_thread_success(o, i),
            )

        def on_err(msg: str) -> None:
            if aborted[0] or cleaned[0]:
                return
            QTimer.singleShot(
                0,
                prog,
                lambda m=msg: _finish_on_gui_thread_error(m),
            )

        thread.started.connect(worker.run)
        worker.finished.connect(on_ok)
        worker.failed.connect(on_err)
        thread.finished.connect(lambda: log.debug("QThread finished"))
        prog.canceled.connect(lambda: _abort_analysis("user cancel"))
        
        log.info("스레드 시작 전: thread=%s, worker=%s", thread, worker)
        thread.start()
        log.info("스레드 시작 완료")
        _skin_compare_attach(parent, thread, tick_timer)
        progress_holder[0] = "피부 분석: 스레드 시작…"
        QCoreApplication.processEvents()
        
        # modal=True인 경우 다이얼로그가 생성될 때까지 대기
        if modal:
            log.debug("modal=True: 다이얼로그 생성 대기 시작")
            loop = QEventLoop()
            # 다이얼로그가 생성되면 루프 종료
            def check_dialog():
                if dialog_holder[0] is not None:
                    log.debug("modal=True: 다이얼로그 생성됨, 루프 종료")
                    loop.quit()
                else:
                    QTimer.singleShot(100, check_dialog)
            QTimer.singleShot(100, check_dialog)
            loop.exec()
            log.debug("modal=True: 루프 종료, 다이얼로그 반환")
            return dialog_holder[0]
        
        # modal=False인 경우 None 반환
        elapsed_time = time.time() - start_time
        log.debug("modal=False: None 반환, 총 소요시간 %.2f초", elapsed_time)
        return None
    except Exception as e:
        elapsed_time = time.time() - start_time
        log.debug("예외 발생, 소요시간 %.2f초, 오류: %s", elapsed_time, e)
        measurement_count = get_measurement_count()
        log.exception(f"{measurement_count}항목 비교 다이얼로그 표시 중 오류 발생")
        if parent:
            QMessageBox.critical(
                parent,
                f"{measurement_count}항목 비교 오류",
                f"오류가 발생했습니다:\n{str(e)}"
            )
        else:
            print(f"{measurement_count}항목 비교 오류: {str(e)}", file=sys.stderr)
        if modal:
            return None
        return None


def resolve_ideal_image_path(
    orig: Optional[Path],
    mid: Optional[Path],
) -> Optional[Path]:
    """미리보기와 동일 우선순위: 복원 산출."""
    if mid is not None and mid.is_file():
        return mid
    return None
