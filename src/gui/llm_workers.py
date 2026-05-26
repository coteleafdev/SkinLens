"""
llm_workers.py — LLM 백그라운드 작업자 모듈

LLM 소견 생성을 백그라운드 스레드에서 실행하는 Worker 클래스를 제공합니다.
"""

from __future__ import annotations

import logging
from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class LlmWorker(QObject):
    """듀얼 이미지 LLM 소견 생성 백그라운드 작업자"""
    progress = Signal(str)
    finished = Signal(object, object)  # orig_report, ideal_report
    error = Signal(str)

    def __init__(self, reporter, orig_path, orig_measurements, orig_overall, orig_age,
                 ideal_path, ideal_measurements, ideal_overall, ideal_age, provide_scores):
        super().__init__()
        self.reporter = reporter
        self.orig_path = orig_path
        self.orig_measurements = orig_measurements
        self.orig_overall = orig_overall
        self.orig_age = orig_age
        self.ideal_path = ideal_path
        self.ideal_measurements = ideal_measurements
        self.ideal_overall = ideal_overall
        self.ideal_age = ideal_age
        self.provide_scores = provide_scores

    def run(self):
        try:
            orig_report, ideal_report = self.reporter.generate_report_from_dual_images(
                self.orig_path,           # orig_image_path
                self.ideal_path,          # ideal_image_path
                self.orig_measurements,   # orig_measurements_report
                self.orig_overall,         # orig_overall_score
                self.orig_age,            # orig_perceived_age
                self.ideal_measurements,   # ideal_measurements_report
                self.ideal_overall,       # ideal_overall_score
                self.ideal_age,            # ideal_perceived_age
                self.provide_scores       # provide_scores
            )
            self.finished.emit(orig_report, ideal_report)
        except Exception as e:
            self.error.emit(str(e))


class LlmSingleWorker(QObject):
    """단일 이미지 LLM 소견 생성 백그라운드 작업자"""
    progress = Signal(str)
    finished = Signal(object)
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
            report = self.reporter.generate_report_from_measurements(
                self.image_path,
                self.measurements,
                self.overall_score,
                self.perceived_age,
                self.provide_scores
            )
            self.finished.emit(report)
        except Exception as e:
            self.error.emit(str(e))
