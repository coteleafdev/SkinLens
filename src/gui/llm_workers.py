"""
llm_workers.py — LLM 백그라운드 작업자 모듈

LLM 소견 생성을 백그라운드 스레드에서 실행하는 Worker 클래스를 제공합니다.
"""

from __future__ import annotations

import logging
import time
from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class LlmWorker(QObject):
    """듀얼 이미지 LLM 소견 생성 백그라운드 작업자"""
    progress = Signal(str)
    finished = Signal(object, object, float)  # orig_report, ref_report, elapsed_time
    error = Signal(str)

    def __init__(self, reporter, orig_path, orig_measurements, orig_overall, orig_age,
                 ref_path, ref_measurements, ref_overall, ref_age, provide_scores):
        super().__init__()
        self.reporter = reporter
        self.orig_path = orig_path
        self.orig_measurements = orig_measurements
        self.orig_overall = orig_overall
        self.orig_age = orig_age
        self.ref_path = ref_path
        self.ref_measurements = ref_measurements
        self.ref_overall = ref_overall
        self.ref_age = ref_age
        self.provide_scores = provide_scores

    def run(self):
        try:
            start_time = time.time()
            orig_report, ref_report = self.reporter.generate_report_from_dual_images(
                self.orig_path,           # orig_image_path
                self.ref_path,          # ref_image_path
                self.orig_measurements,   # orig_measurements_report
                self.orig_overall,         # orig_overall_score
                self.orig_age,            # orig_perceived_age
                self.ref_measurements,   # ref_measurements_report
                self.ref_overall,         # ref_overall_score
                self.ref_age,            # ref_perceived_age
                self.provide_scores       # provide_scores
            )
            elapsed_time = time.time() - start_time
            self.finished.emit(orig_report, ref_report, elapsed_time)
        except Exception as e:
            self.error.emit(str(e))


class LlmSingleWorker(QObject):
    """단일 이미지 LLM 소견 생성 백그라운드 작업자"""
    progress = Signal(str)
    finished = Signal(object, float)  # report, elapsed_time
    error = Signal(str)

    def __init__(self, reporter, image_path, measurements, overall_score, perceived_age, provide_scores):
        super().__init__()
        self.reporter = reporter
        self.image_path = image_path
        self.measurements = measurements
        self.overall_score = overall_score
        self.perceived_age = perceived_age
        self.provide_scores = provide_scores

    def run(self):
        try:
            start_time = time.time()
            report = self.reporter.generate_report_from_measurements(
                self.image_path,
                self.measurements,
                self.overall_score,
                self.perceived_age,
                self.provide_scores
            )
            elapsed_time = time.time() - start_time
            self.finished.emit(report, elapsed_time)
        except Exception as e:
            self.error.emit(str(e))
