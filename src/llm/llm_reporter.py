"""
llm_reporter.py — LLM Skin Reporter 핵심 모듈

LLMSkinReporter 클래스를 포함하며, 이미지와 측정 점수를 사용하여
LLM을 통해 피부 분석 소견을 생성하는 핵심 기능을 제공합니다.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.llm.llm_config import (
    get_default_model,
    get_default_max_retries,
    get_default_provider,
)
from src.llm.llm_model_manager import (
    list_available_models,
    _load_llm_api_key,
)
from src.llm.llm_metadata import _get_metric_meta
from src.llm.llm_formatters import (
    _grade_label,
    _analyze_opinion_sentiment,
    _adjust_score_based_on_opinion,
    MetricOpinion,
    SkinLLMReport,
)
from src.llm.llm_prompt_builder import (
    _build_system_prompt,
    _build_user_prompt,
    _build_dual_image_prompt,
    _build_reference_guided_prompt,
)
from src.llm.llm_providers import create_provider, LLMProvider
from src.skin.core.config_parser import get_llm_api_config, get_measurement_count

log = logging.getLogger(__name__)

# 측정항목 메타데이터 (동적 로드)
_METRIC_META: List[tuple[str, str, str, bool]] = _get_metric_meta()


def _apply_score_correction(
    analyzer_score: float,
    llm_score: float,
    mode: str = "hybrid",
    analyzer_weight: float = 0.7,
    llm_weight: float = 0.3,
    dynamic_weighting: bool = False,
    score_difference_threshold: float = 15.0,
) -> float:
    """점수 보정 로직
    
    Args:
        analyzer_score: 자체 분석기 점수
        llm_score: LLM이 측정한 점수
        mode: 보정 모드 ('analyzer', 'llm', 'hybrid')
        analyzer_weight: 자체 분석기 가중치 (hybrid 모드에서만 사용)
        llm_weight: LLM 가중치 (hybrid 모드에서만 사용)
        dynamic_weighting: 동적 가중치 조정 활성화 여부
        score_difference_threshold: 동적 가중치 조정 임계값
    
    Returns:
        보정된 점수
    """
    if mode == "analyzer":
        log.debug(f"[점수 보정] 자체 분석기 점수 사용: {analyzer_score}")
        return analyzer_score
    elif mode == "llm":
        log.debug(f"[점수 보정] LLM 점수 사용: {llm_score}")
        return llm_score
    elif mode == "hybrid":
        # 동적 가중치 조정
        if dynamic_weighting:
            score_diff = abs(analyzer_score - llm_score)
            if score_diff >= score_difference_threshold:
                log.info(
                    f"[점수 보정] 점수 차이 {score_diff:.1f} >= 임계값 {score_difference_threshold}, 자체 분석기 점수 사용"
                )
                return analyzer_score
            else:
                log.debug(
                    f"[점수 보정] 기존 가중치 사용: 점수 차이 {score_diff:.1f} < 임계값 {score_difference_threshold}"
                )
        
        # 가중치 합계 검증
        total_weight = analyzer_weight + llm_weight
        if abs(total_weight - 1.0) > 0.01:
            log.warning(f"[점수 보정] 가중치 합계가 1.0이 아님: {total_weight}, 정규화 수행")
            analyzer_weight /= total_weight
            llm_weight /= total_weight
        
        corrected_score = analyzer_score * analyzer_weight + llm_score * llm_weight
        log.debug(f"[점수 보정] 하이브리드: 자체={analyzer_score}({analyzer_weight}) + LLM={llm_score}({llm_weight}) = {corrected_score}")
        return corrected_score
    else:
        log.warning(f"[점수 보정] 알 수 없는 모드: {mode}, 자체 분석기 점수 사용")
        return analyzer_score


def _monitor_score_difference(
    analyzer_score: float,
    llm_score: float,
    metric_name: str = "종합 점수",
    warning_threshold: float = 20.0,
    critical_threshold: float = 40.0,
) -> None:
    """점수 차이 모니터링 및 로깅
    
    Args:
        analyzer_score: 자체 분석기 점수
        llm_score: LLM이 측정한 점수
        metric_name: 측정항목 이름
        warning_threshold: 경고 임계값 (기본 20점)
        critical_threshold: 심각 임계값 (기본 40점)
    """
    # config에서 임계값 로드 시도
    try:
        from src.skin.core.config_parser import get_llm_api_config
        api_config = get_llm_api_config()
        score_correction_config = api_config.get("score_correction", {})
        monitoring_config = score_correction_config.get("monitoring", {})
        warning_threshold = monitoring_config.get("warning_threshold", 20.0)
        critical_threshold = monitoring_config.get("critical_threshold", 40.0)
    except Exception:
        pass  # 기본값 사용
    
    score_diff = abs(analyzer_score - llm_score)
    
    if score_diff >= critical_threshold:
        log.error(
            f"[점수 차이] {metric_name}: 심각한 차이 발생 "
            f"(자체={analyzer_score:.1f}, LLM={llm_score:.1f}, 차이={score_diff:.1f})"
        )
    elif score_diff >= warning_threshold:
        log.warning(
            f"[점수 차이] {metric_name}: 큰 차이 발생 "
            f"(자체={analyzer_score:.1f}, LLM={llm_score:.1f}, 차이={score_diff:.1f})"
        )
    else:
        log.debug(
            f"[점수 차이] {metric_name}: 정상 범위 "
            f"(자체={analyzer_score:.1f}, LLM={llm_score:.1f}, 차이={score_diff:.1f})"
        )


class LlmSkinReporter:
    """
    원본 이미지 + 측정 점수 → LLM (LLM Vision) → 소견 생성

    Parameters
    ----------
    api_key : str, optional
        Google AI Studio API 키 (https://aistudio.google.com/app/apikey)
        지정하지 않으면 config/secrets.json에서 자동 로드합니다.
    model_name : str
        사용할 LLM 모델. Vision 기능이 있는 모델만 가능.
        기본값: "gemini-2.5-flash"
    max_retries : int
        API 호출 실패 시 재시도 횟수
    retry_delay : float
        재시도 간격(초)
    progress_callback : Callable[[str], None], optional
        진행 상황을 전달받을 콜백 함수
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        provider: Optional[str] = None,  # 프로바이더 이름 (gemini, openai, etc.)
        product_repository: Optional[Any] = None,  # ProductRepository 의존성 주입
    ) -> None:
        # config.json에서 기본값 로드
        if model_name is None:
            model_name = get_default_model()
        if max_retries is None:
            max_retries = get_default_max_retries()
        if provider is None:
            provider = get_default_provider()
        
        # 모델명에서 LLM 제공자 이름 추출 (예: gemini-2.5-flash-image → gemini)
        self.model_name = model_name
        # provider가 지정되지 않으면 모델명에서 추출 (fallback)
        if provider is None:
            # [FIX P1-12] 알려진 모델명 패턴 매핑
            model_to_provider = {
                "gemini": "gemini",
                "gpt": "openai",
                "claude": "anthropic",
                "openai": "openai",
                "anthropic": "anthropic",
            }
            # 경로에서 파일명 추출 (예: models/gemini-2.5-pro → gemini-2.5-pro)
            base_name = model_name.split('/')[-1] if '/' in model_name else model_name
            # 파일명에서 제공자 추출 (예: gemini-2.5-pro → gemini)
            extracted = base_name.split('-')[0] if '-' in base_name else base_name
            provider = model_to_provider.get(extracted.lower(), extracted)
            log.warning("LLM provider가 지정되지 않아 모델명에서 추출했습니다: %s → %s. config.json에 provider 필드를 추가하는 것을 권장합니다.", model_name, provider)
        self.provider_name = provider
        
        # API 설정 로드
        api_config = get_llm_api_config()
        
        # 점수 보정 설정 로그 출력
        score_correction_config = api_config.get("score_correction", {})
        score_correction_enabled = score_correction_config.get("enabled", False)
        score_correction_mode = score_correction_config.get("mode", "hybrid")
        analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
        llm_weight = score_correction_config.get("llm_weight", 0.3)
        
        dynamic_weighting_config = score_correction_config.get("dynamic_weighting", {})
        dynamic_weighting_enabled = dynamic_weighting_config.get("enabled", False)
        score_difference_threshold = dynamic_weighting_config.get("score_difference_threshold", 15.0)
        
        monitoring_config = score_correction_config.get("monitoring", {})
        warning_threshold = monitoring_config.get("warning_threshold", 20.0)
        critical_threshold = monitoring_config.get("critical_threshold", 40.0)
        
        log.info(
            f"[LLM 설정] 점수 보정: enabled={score_correction_enabled}, mode={score_correction_mode}, "
            f"analyzer_weight={analyzer_weight}, llm_weight={llm_weight}"
        )
        log.info(
            f"[LLM 설정] 동적 가중치: enabled={dynamic_weighting_enabled}, "
            f"score_difference_threshold={score_difference_threshold}"
        )
        log.info(
            f"[LLM 설정] 모니터링: warning_threshold={warning_threshold}, critical_threshold={critical_threshold}"
        )

        # api_key가 지정되지 않으면 secrets.json에서 로드
        if api_key is None:
            api_key = _load_llm_api_key(provider)

        if not api_key:
            raise ValueError("LLM API 키가 설정되지 않았습니다. config.secrets.json 또는 환경 변수를 확인하세요.")
        
        # 프로바이더 생성 및 설정
        self._provider: LLMProvider = create_provider(
            provider_name=provider,
            api_key=api_key,
            model_name=model_name,
            temperature=api_config["temperature"],
            max_output_tokens=api_config["max_output_tokens_single"],
        )
        self._provider.configure()
        
        # 사용 가능한 모델 목록 출력
        try:
            available_models = self._provider.list_models()
            if available_models:
                log.info(f"[LLM] 사용 가능한 모델 {len(available_models)}개 중 '{model_name}' 사용")
                log.debug(f"[LLM] 사용 가능한 모델 목록: {', '.join(available_models[:5])}...")
        except Exception as e:
            log.warning(f"[LLM] 사용 가능한 모델 목록 조회 실패: {e}")
        
        log.info(f"[LLM] LLMSkinReporter 초기화 완료 (provider={provider}, model={model_name})")
        self.max_retries = max_retries if max_retries is not None else api_config["max_retries"]
        self.retry_delay = retry_delay if retry_delay is not None else api_config["retry_delay"]
        self.progress_callback = progress_callback
        self._product_repository = product_repository  # 의존성 주입된 ProductRepository
        self.temperature = api_config["temperature"]
        self.max_output_tokens_single = api_config["max_output_tokens_single"]
        self.max_output_tokens_dual = api_config["max_output_tokens_dual"]

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def generate_report(
        self,
        image_path: str | Path,
        provide_scores: bool = True,  # 점수 제공 여부
    ) -> SkinLLMReport:
        """이미지 경로 → 전체 분석 + LLM 소견
        
        Args:
            image_path: 분석할 이미지 경로
            provide_scores: 점수 제공 여부 (True면 LLM가 점수를 산출, False면 원본 점수 사용)
        
        Returns:
            SkinLLMReport: LLM 소견이 포함된 보고서

        Note:
            이 함수는 Layer B(보고서 항목) 기준으로 동작합니다.
            measurements_report(Layer B)를 사용하며, 없을 경우 measurements(Layer A)를 폴백으로 사용합니다.
            하지만 Layer A는 10개 항목만 있으므로 일부 항목이 누락될 수 있습니다.
        """
        from src.scoring.skin_scoring import SkinAnalyzer

        analyzer = SkinAnalyzer()
        analysis_result: Dict[str, Any] = analyzer.analyze_all(str(image_path))
        
        # Layer B 우선, 없으면 Layer A 폴백
        measurements_report: Dict[str, Any] = analysis_result.get("measurements_report") or analysis_result.get("measurements", {})
        overall_score: float = analysis_result.get("overall_score", 0)
        perceived_age: float = analysis_result.get("perceived_age", 0)
        
        return self.generate_report_from_measurements(
            image_path,
            measurements_report,
            overall_score,
            perceived_age,
            provide_scores=provide_scores,
        )

    def generate_report_from_measurements(
        self,
        image_path: str | Path,
        measurements_report: Dict[str, Any],
        overall_score: float,
        perceived_age: float,
        provide_scores: bool = True,
        product_info: Optional[str] = None,
        survey_info: Optional[str] = None,
    ) -> SkinLLMReport:
        """이미지 경로 + 측정 점수 → LLM 소견

        Args:
            image_path: 분석할 이미지 경로
            measurements_report: 측정 점수 딕셔너리
            overall_score: 종합 점수
            perceived_age: 인지 나이
            provide_scores: 점수 제공 여부
            product_info: 맞춤형 화장품 성분 정보

        Returns:
            SkinLLMReport: LLM 소견이 포함된 보고서
        """
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            measurements_report,
            overall_score,
            perceived_age,
            provide_scores=provide_scores,
            product_info=product_info,
            survey_info=survey_info,
        )
        
        # 이미지 로드
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        # LLM API 호출 및 JSON 파싱 재시도
        for attempt in range(self.max_retries + 1):
            try:
                if self.progress_callback:
                    self.progress_callback(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1})")
                else:
                    log.info(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1})")

                # LLM API 호출
                response_text: str = self._call_llm(
                    system_prompt,
                    user_prompt,
                    [image_path],
                    max_output_tokens=self.max_output_tokens_single,
                )

                # 응답 파싱
                report: SkinLLMReport = self._parse_single_response(
                    response_text,
                    measurements_report,
                    overall_score,
                    perceived_age,
                )

                report.model = self.model_name
                return report

            except (json.JSONDecodeError, ValueError) as e:
                # JSON 파싱 오류는 재시도
                if attempt < self.max_retries:
                    log.warning(f"[LLM] JSON 파싱 실패 (시도 {attempt + 1}/{self.max_retries + 1}): {e}")
                    log.debug(f"[LLM] 응답 텍스트 (첫 500자): {response_text[:500]}")
                    # 불완전한 JSON 감지: 마지막 문자가 중괄호나 대괄호로 끝나지 않는 경우
                    if response_text and not response_text.rstrip().endswith('}'):
                        log.warning("[LLM] 응답이 불완전해 보입니다 (JSON이 닫히지 않음). 즉시 재시도합니다.")
                    time.sleep(self.retry_delay)
                else:
                    log.error(f"[LLM] JSON 파싱 최종 실패: {e}")
                    log.debug(f"[LLM] 응답 텍스트 (전체): {response_text}")
                    raise
            except PermissionError as e:
                # 인증 오류(401)는 즉시 실패 - 재시도 불가
                log.error(f"[LLM] API 인증 실패 (재시도 불가): {e}")
                raise
            except ConnectionError as e:
                # 네트워크/서버 오류(429, 500)는 재시도
                if attempt < self.max_retries:
                    log.warning(f"[LLM] API 호출 실패 (시도 {attempt + 1}/{self.max_retries + 1}): {e}")
                    time.sleep(self.retry_delay)
                else:
                    log.error(f"[LLM] API 호출 최종 실패: {e}")
                    raise

    # Backward compatibility alias
    def generate_report_from_dual_images(
        self,
        orig_image_path: str | Path,
        ideal_image_path: str | Path,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        ideal_measurements_report: Dict[str, Any],
        ideal_overall_score: float,
        ideal_perceived_age: float,
        provide_scores: bool = True,
        product_info: Optional[str] = None,
        product_recommendations: Optional[str] = None,  # 하위 호환성을 위한 추가 파라미터
        product_repository: Optional[Any] = None,  # ProductRepository 의존성 주입
        concerns: Optional[List[str]] = None,  # 설문 응답: 고민사항
        skin_type: Optional[str] = None,  # 설문 응답: 피부 타입
        survey_info: Optional[str] = None,  # 설문 정보 JSON
    ) -> tuple[SkinLLMReport, SkinLLMReport]:
        """하위 호환성을 위한 별칭 메서드. generate_dual_report()를 호출합니다."""
        return self.generate_dual_report(
            orig_image_path,
            ideal_image_path,
            orig_measurements_report,
            orig_overall_score,
            orig_perceived_age,
            ideal_measurements_report,
            ideal_overall_score,
            ideal_perceived_age,
            provide_scores,
            product_info,
            product_repository,
            concerns,
            skin_type,
            survey_info,
        )

    def generate_reference_guided_report(
        self,
        orig_image_path: str | Path,
        ideal_image_path: str | Path,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        ideal_measurements_report: Dict[str, Any],
        provide_scores: bool = True,
        product_info: Optional[str] = None,
        survey_info: Optional[str] = None,
        skin_type: Optional[str] = None,
        concerns: Optional[List[str]] = None,
    ) -> SkinLLMReport:
        """복원 이미지를 레퍼런스로 사용하여 원본 점수 정확도를 높인 보고서 반환.

        기존 generate_dual_report()와의 차이:
          - 기존: 두 이미지 각각 독립 분석 → 원본·복원 점수 2세트 반환
          - 신규: 복원본을 기준선으로 원본을 역산 → 원본 점수 1세트 반환 (정확도 향상)

        Gemini에게 전달하는 3단계 지시:
          Step 1. 복원본 기준선 파악
          Step 2. 원본 오탐 요인(조명·반사·초점·색온도·아티팩트) 역산
          Step 3. 보정된 원본 점수 최종 산출

        Args:
            orig_image_path:           원본 이미지 경로
            ideal_image_path:          복원 이미지 경로 (GAN 복원본)
            orig_measurements_report:  원본 CV 분석기 측정값
            orig_overall_score:        원본 CV 종합 점수
            orig_perceived_age:        원본 CV 인지 나이
            ideal_measurements_report: 복원 CV 측정값 (비교 참고용)
            provide_scores:            CV 점수를 프롬프트에 포함할지 여부
            product_info:              외부에서 주입하는 제품 정보 (없으면 DB 매칭)

        Returns:
            SkinLLMReport: 복원 기준선 보정이 적용된 원본 보고서 1개
        """
        orig_image_path  = Path(orig_image_path)
        ideal_image_path = Path(ideal_image_path)
        if not orig_image_path.exists():
            raise FileNotFoundError(f"원본 이미지 없음: {orig_image_path}")
        if not ideal_image_path.exists():
            raise FileNotFoundError(f"복원 이미지 없음: {ideal_image_path}")

        # ── 처방전 계산 ───────────────────────────────────────────
        from src.prescription.prescription_calculator import create_prescription
        full_prescription = create_prescription(
            skin_assessment_scores=orig_measurements_report,
            pcr_result=None,
            age_group_statistics=None,
            age=30,
            gender="female",
            skin_type=skin_type,
            concerns=concerns,
        )
        prescription_info = json.dumps(full_prescription, ensure_ascii=False)

        # ── 제품 매칭 ─────────────────────────────────────────────
        assessment_recipe = full_prescription.get("assessment", {})
        matched_products: List[Dict[str, Any]] = []
        try:
            if self._product_repository:
                matched_products = self._product_repository.match_products_by_prescription(
                    assessment_recipe, max_products=3
                )
            else:
                from src.db.product_repository import ProductRepository
                repo = ProductRepository()
                matched_products = repo.match_products_by_prescription(
                    assessment_recipe, max_products=3
                )
                repo.close()
            product_info = product_info or json.dumps(matched_products, ensure_ascii=False)
        except Exception as e:
            log.warning("[RGP] 제품 매칭 실패: %s", e)
            product_info = product_info or "[]"

        # ── 프롬프트 조립 ─────────────────────────────────────────
        system_prompt = _build_system_prompt()
        user_prompt   = _build_reference_guided_prompt(
            orig_measurements_report=orig_measurements_report,
            orig_overall_score=orig_overall_score,
            orig_perceived_age=orig_perceived_age,
            ideal_measurements_report=ideal_measurements_report,
            provide_scores=provide_scores,
            product_info=product_info,
            prescription_info=prescription_info,
            survey_info=survey_info,
        )

        # ── API 호출 (재시도 포함) ────────────────────────────────
        # 이미지 순서: [원본, 복원] — 프롬프트에서 "이미지 1=원본, 이미지 2=복원"으로 명시
        for attempt in range(self.max_retries + 1):
            try:
                if self.progress_callback:
                    self.progress_callback(
                        f"[복원 기반 분석] LLM 소견 생성 중... "
                        f"(시도 {attempt + 1}/{self.max_retries + 1})"
                    )
                else:
                    log.info(
                        "[RGP] LLM 호출 시도 %d/%d",
                        attempt + 1, self.max_retries + 1,
                    )

                response_text = self._call_llm(
                    system_prompt,
                    user_prompt,
                    [orig_image_path, ideal_image_path],
                    max_output_tokens=self.max_output_tokens_dual,
                )

                report = self._parse_reference_guided_response(
                    response_text,
                    orig_measurements_report,
                    orig_overall_score,
                    orig_perceived_age,
                    matched_products,
                )
                report.model = self.model_name
                return report

            except (json.JSONDecodeError, ValueError) as e:
                if attempt < self.max_retries:
                    log.warning("[RGP] JSON 파싱 실패 (시도 %d): %s", attempt + 1, e)
                    time.sleep(self.retry_delay)
                else:
                    log.error("[RGP] JSON 파싱 최종 실패: %s", e)
                    raise
            except PermissionError as e:
                log.error("[RGP] API 인증 실패: %s", e)
                raise
            except ConnectionError as e:
                if attempt < self.max_retries:
                    log.warning("[RGP] API 호출 실패 (시도 %d): %s", attempt + 1, e)
                    time.sleep(self.retry_delay)
                else:
                    log.error("[RGP] API 최종 실패: %s", e)
                    raise

    def generate_dual_report(
        self,
        orig_image_path: str | Path,
        ideal_image_path: str | Path,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        ideal_measurements_report: Dict[str, Any],
        ideal_overall_score: float,
        ideal_perceived_age: float,
        provide_scores: bool = True,
        product_info: Optional[str] = None,
        product_repository: Optional[Any] = None,  # ProductRepository 의존성 주입
        concerns: Optional[List[str]] = None,  # 설문 응답: 고민사항
        skin_type: Optional[str] = None,  # 설문 응답: 피부 타입
        survey_info: Optional[str] = None,  # 설문 정보 JSON
    ) -> tuple[SkinLLMReport, SkinLLMReport]:
        """듀얼 이미지 분석 (원본 + 복원)
        
        Args:
            orig_image_path: 원본 이미지 경로
            ideal_image_path: 복원 이미지 경로
            orig_measurements_report: 원본 측정 점수
            orig_overall_score: 원본 종합 점수
            orig_perceived_age: 원본 인지 나이
            ideal_measurements_report: 복원 측정 점수
            ideal_overall_score: 복원 종합 점수
            ideal_perceived_age: 복원 인지 나이
            provide_scores: 점수 제공 여부
            product_info: 맞춤형 화장품 성분 정보
        
        Returns:
            tuple[SkinLLMReport, SkinLLMReport]: (원본 보고서, 복원 보고서)
        """
        # 처방전 계산 (피부 평가 점수 기반)
        from src.prescription.prescription_calculator import create_prescription

        full_prescription = create_prescription(
            skin_assessment_scores=orig_measurements_report,
            pcr_result=None,  # PCR 데이터가 없으면 None
            age_group_statistics=None,
            age=30,
            gender="female",
            skin_type=skin_type,
            concerns=concerns,
        )
        log.info(f"[LLM] 처방전 계산 결과: {full_prescription}")

        # 처방 정보를 JSON 문자열로 변환하여 프롬프트에 전달 (base 비율 포함)
        import json
        prescription_info = json.dumps(full_prescription, ensure_ascii=False)

        # 제품 매칭을 위해 assessment_recipe 추출
        assessment_recipe = full_prescription.get("assessment", {})
        
        # 처방전 기반 제품 매칭
        try:
            if product_repository:
                # 의존성 주입된 ProductRepository 사용
                matched_products = product_repository.match_products_by_prescription(
                    assessment_recipe, max_products=3, concerns=concerns, skin_type=skin_type
                )
            elif self._product_repository:
                # 인스턴스 변수의 ProductRepository 사용
                matched_products = self._product_repository.match_products_by_prescription(
                    assessment_recipe, max_products=3, concerns=concerns, skin_type=skin_type
                )
            else:
                # 하위 호환성: 의존성 주입이 없으면 기존 방식대로 생성
                from src.db.product_repository import ProductRepository
                repo = ProductRepository()
                matched_products = repo.match_products_by_prescription(
                    assessment_recipe, max_products=3, concerns=concerns, skin_type=skin_type
                )
                repo.close()

            # 제품 정보를 JSON 문자열로 변환
            product_info = json.dumps(matched_products, ensure_ascii=False)
            log.info(f"[LLM] 매칭된 제품 수: {len(matched_products)}")
        except Exception as e:
            log.warning(f"[LLM] 제품 매칭 실패: {e}")
            product_info = "[]"
        
        system_prompt = _build_system_prompt()

        # ── scoring_mode 분기 ─────────────────────────────────────
        # config.json llm.scoring_mode = "reference_guided" 이면
        # 복원 기반 원본 점수 정확도 향상 모드를 사용한다.
        # "independent"(기본) 이면 기존 독립 분석 방식을 유지한다.
        try:
            from src.skin.core.config_parser import get_llm_api_config as _gcfg
            _scoring_mode = _gcfg().get("scoring_mode", "independent")
        except Exception:
            _scoring_mode = "independent"

        log.info("[generate_dual_report] scoring_mode=%s (config.json llm.scoring_mode)", _scoring_mode)

        if _scoring_mode == "reference_guided":
            log.info("[generate_dual_report] scoring_mode=reference_guided → 복원 기반 모드로 라우팅")
            orig_report = self.generate_reference_guided_report(
                orig_image_path=orig_image_path,
                ideal_image_path=ideal_image_path,
                orig_measurements_report=orig_measurements_report,
                orig_overall_score=orig_overall_score,
                orig_perceived_age=orig_perceived_age,
                ideal_measurements_report=ideal_measurements_report,
                provide_scores=provide_scores,
                product_info=product_info,
                survey_info=survey_info,
            )
            # 복원 보고서는 빈 보고서로 대체 (reference_guided는 원본 1세트만 반환)
            from src.llm.llm_formatters import SkinLLMReport, MetricOpinion
            ideal_report = SkinLLMReport(
                overall_score=ideal_overall_score,
                perceived_age=ideal_perceived_age,
                metric_opinions=[],
                overall_opinion="[reference_guided 모드: 복원 보고서는 별도 생성하지 않음]",
                recommendation="",
                raw_response="",
                matched_products=orig_report.matched_products,
            )
            return orig_report, ideal_report

        log.info("[generate_dual_report] scoring_mode=independent → 기존 독립 분석 방식 사용")

        user_prompt = _build_dual_image_prompt(
            orig_measurements_report,
            orig_overall_score,
            orig_perceived_age,
            ideal_measurements_report,
            ideal_overall_score,
            ideal_perceived_age,
            provide_scores=provide_scores,
            product_info=product_info,
            prescription_info=prescription_info,
            survey_info=survey_info,
        )
        
        # 이미지 로드
        orig_image_path = Path(orig_image_path)
        ideal_image_path = Path(ideal_image_path)
        if not orig_image_path.exists():
            raise FileNotFoundError(f"원본 이미지 파일을 찾을 수 없습니다: {orig_image_path}")
        if not ideal_image_path.exists():
            raise FileNotFoundError(f"복원 이미지 파일을 찾을 수 없습니다: {ideal_image_path}")
        
        # LLM API 호출 및 JSON 파싱 재시도
        for attempt in range(self.max_retries + 1):
            try:
                if self.progress_callback:
                    self.progress_callback(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1})")
                else:
                    log.info(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1})")

                # LLM API 호출
                response_text: str = self._call_llm(
                    system_prompt,
                    user_prompt,
                    [orig_image_path, ideal_image_path],
                    max_output_tokens=self.max_output_tokens_dual,
                )

                # 응답 파싱
                return self._parse_dual_response(
                    response_text,
                    orig_measurements_report,
                    orig_overall_score,
                    orig_perceived_age,
                    ideal_measurements_report,
                    ideal_overall_score,
                    ideal_perceived_age,
                    matched_products,  # DB 매칭 제품 전달
                )

            except (json.JSONDecodeError, ValueError) as e:
                # JSON 파싱 오류는 재시도
                if attempt < self.max_retries:
                    log.warning(f"[LLM] JSON 파싱 실패 (시도 {attempt + 1}/{self.max_retries + 1}): {e}")
                    log.debug(f"[LLM] 응답 텍스트 (첫 500자): {response_text[:500]}")
                    # 불완전한 JSON 감지: 마지막 문자가 중괄호나 대괄호로 끝나지 않는 경우
                    if response_text and not response_text.rstrip().endswith('}'):
                        log.warning("[LLM] 응답이 불완전해 보입니다 (JSON이 닫히지 않음). 즉시 재시도합니다.")
                    time.sleep(self.retry_delay)
                else:
                    log.error(f"[LLM] JSON 파싱 최종 실패: {e}")
                    log.debug(f"[LLM] 응답 텍스트 (전체): {response_text}")
                    raise
            except PermissionError as e:
                # 인증 오류(401)는 즉시 실패 - 재시도 불가
                log.error(f"[LLM] API 인증 실패 (재시도 불가): {e}")
                raise
            except ConnectionError as e:
                # 네트워크/서버 오류(429, 500)는 재시도
                if attempt < self.max_retries:
                    log.warning(f"[LLM] API 호출 실패 (시도 {attempt + 1}/{self.max_retries + 1}): {e}")
                    time.sleep(self.retry_delay)
                else:
                    log.error(f"[LLM] API 호출 최종 실패: {e}")
                    raise

    # ----------------------------------------------------------
    # Private Methods
    # ----------------------------------------------------------

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: List[Path],
        max_output_tokens: int,
    ) -> str:
        """LLM API 호출 (단일 시도)

        참고: 이전 버전에서는 _call_llm_with_retry였으나, 재시도 로직이
        상위 호출부(generate_report, generate_dual_report)로 이동되어
        단일 시도만 수행하도록 단순화되었습니다.
        """
        # 이미지 로드
        import PIL.Image
        images: List[Any] = []
        for img_path in image_paths:
            img = PIL.Image.open(img_path)
            images.append(img)

        # 프로바이더를 통한 API 호출
        response_text: str = self._provider.generate_content(
            prompts=[system_prompt, user_prompt],
            images=images,
        )

        log.info(f"[LLM] API 호출 성공, 응답 길이: {len(response_text)}")
        log.info(f"[LLM] 응답 내용: {response_text[:500]}...")
        log.debug(f"[LLM] 전체 응답:\n{response_text}")
        return response_text

    def _parse_single_response(
        self,
        response_text: str,
        measurements_report: Dict[str, Any],
        overall_score: float,
        perceived_age: float,
    ) -> SkinLLMReport:
        """단일 이미지 응답 파싱"""
        # 마크다운 코드 블록 제거 (```json ... ```)
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]  # 첫 줄 제거
            if lines[-1].startswith("```"):
                lines = lines[:-1]  # 마지막 줄 제거
            response_text = "\n".join(lines).strip()
        
        try:
            # JSON 파싱
            response_json = json.loads(response_text)
        except json.JSONDecodeError as e:
            log.error("[LLM] 단일 응답 JSON 파싱 실패: %s", e)
            # JSON 복구 시도
            recovered = False
            
            # 방법 1: 마지막 중괄호 찾기
            try:
                last_brace = response_text.rfind('}')
                if last_brace > 0:
                    recovered_text = response_text[:last_brace + 1]
                    response_json = json.loads(recovered_text)
                    log.warning("[LLM] JSON 복구 성공 (방법1): 마지막 불완전 부분 제거됨")
                    recovered = True
            except Exception:
                pass
            
            # 방법 2: 문자열이 닫히지 않은 경우 처리
            if not recovered:
                try:
                    quote_count = response_text.count('"')
                    if quote_count % 2 != 0:
                        recovered_text = response_text + '"'
                        response_json = json.loads(recovered_text)
                        log.warning("[LLM] JSON 복구 성공 (방법2): 마지막 따옴표 추가")
                        recovered = True
                except Exception:
                    pass
            
            # 방법 3: 마지막 완전한 객체 찾기
            if not recovered:
                try:
                    brace_count = 0
                    last_complete_pos = -1
                    for i, char in enumerate(reversed(response_text)):
                        if char == '}':
                            brace_count += 1
                        elif char == '{':
                            brace_count -= 1
                        if brace_count == 0:
                            last_complete_pos = len(response_text) - i
                            break
                    
                    if last_complete_pos > 0:
                        recovered_text = response_text[:last_complete_pos]
                        response_json = json.loads(recovered_text)
                        log.warning("[LLM] JSON 복구 성공 (방법3): 마지막 완전한 객체 추출")
                        recovered = True
                except Exception:
                    pass
            
            if not recovered:
                raise ValueError(f"[LLM] 단일 응답 JSON 파싱 실패: {e}")
            
            # metric_scores 및 metric_reasons 파싱
            metric_scores = response_json.get("metric_scores", {})
            metric_reasons = response_json.get("metric_reasons", {})
            
            # metric_opinions 파싱
            metric_opinions = []
            for key, display, category, _ in _METRIC_META:
                # LLM이 산출한 점수 우선, 없으면 시스템 점수 사용
                score = metric_scores.get(key, measurements_report.get(key, 0))
                opinion = response_json.get("metric_opinions", {}).get(key, "")
                reason = metric_reasons.get(key, "")
                
                # 점수 조정 (소견 기반)
                adjusted_score = _adjust_score_based_on_opinion(score, opinion)
                scores_adjusted = abs(adjusted_score - score) > 0.1
                
                metric_opinions.append(MetricOpinion(
                    key=key,
                    display_name=display,
                    category=category,
                    score=adjusted_score,
                    grade=_grade_label(adjusted_score),
                    opinion=opinion,
                    reason=reason,
                ))
            
            # 종합 소견
            overall_opinion = response_json.get("overall_opinion", "")
            recommendation = response_json.get("recommendation", "")
            
            # 점수 보정 적용 (단일 모드)
            final_overall_score = overall_score
            llm_overall_score = None  # 초기화하여 UnboundLocalError 방지
            try:
                api_config = get_llm_api_config()
                score_correction_config = api_config.get("score_correction", {})
                score_correction_enabled = score_correction_config.get("enabled", False)
                
                # 동적 가중치 설정 (score_correction과 독립적으로 작동)
                dynamic_weighting_config = score_correction_config.get("dynamic_weighting", {})
                dynamic_weighting_enabled = dynamic_weighting_config.get("enabled", False)
                score_difference_threshold = dynamic_weighting_config.get("score_difference_threshold", 15.0)
                
                # 점수 보정 또는 동적 가중치 적용
                if score_correction_enabled and "overall_score" in response_json:
                    llm_overall_score = response_json["overall_score"]
                    correction_mode = score_correction_config.get("mode", "hybrid")
                    analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
                    llm_weight = score_correction_config.get("llm_weight", 0.3)
                    
                    # 점수 차이 모니터링 (llm_overall_score 정의 후)
                    _monitor_score_difference(overall_score, llm_overall_score, "종합 점수 (단일 모드)")
                    
                    log.info(f"[점수 보정] 단일 모드 활성화: mode={correction_mode}, analyzer_weight={analyzer_weight}, llm_weight={llm_weight}, dynamic_weighting={dynamic_weighting_enabled}")
                    final_overall_score = _apply_score_correction(
                        overall_score, llm_overall_score,
                        correction_mode, analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                elif dynamic_weighting_enabled and "overall_score" in response_json:
                    # score_correction 비활성화 시에도 동적 가중치 독립 작동
                    llm_overall_score = response_json["overall_score"]
                    analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
                    llm_weight = score_correction_config.get("llm_weight", 0.3)
                    
                    # 점수 차이 모니터링 (llm_overall_score 정의 후)
                    _monitor_score_difference(overall_score, llm_overall_score, "종합 점수 (단일 모드)")
                    
                    log.info(f"[동적 가중치] 단일 모드 독립 작동: score_difference_threshold={score_difference_threshold}, 기본 가중치=자체{analyzer_weight}:LLM{llm_weight}")
                    final_overall_score = _apply_score_correction(
                        overall_score, llm_overall_score,
                        "hybrid", analyzer_weight, llm_weight,  # config 가중치 사용
                        dynamic_weighting_enabled, score_difference_threshold
                    )
            except Exception as e:
                log.warning(f"[점수 보정] 단일 모드 적용 실패, 자체 분석기 점수 사용: {e}")
            
            return SkinLLMReport(
                overall_score=final_overall_score,
                perceived_age=perceived_age,
                metric_opinions=metric_opinions,
                overall_opinion=overall_opinion,
                recommendation=recommendation,
                raw_response=response_text,
                scores_adjusted=scores_adjusted,
                matched_products=[],  # 단일 모드에서는 시스템 매칭 제품 없음
            )
            
        except json.JSONDecodeError as e:
            log.error(f"[LLM] JSON 파싱 실패: {e}")
            raise ValueError(f"LLM 응답 JSON 파싱 실패: {e}")

    def _parse_reference_guided_response(
        self,
        response_text: str,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        matched_products: List[Dict[str, Any]],
    ) -> "SkinLLMReport":
        """복원 기반 레퍼런스 프롬프트 응답 파싱.

        응답 JSON 필드:
          reference_baseline   — 복원본 기준선 서술 (카테고리별)
          score_reasons        — 항목별 점수 산출 이유
          orig_metric_scores   — 18개 항목 최종 점수
          orig_metric_opinions — 18개 항목 소견
          orig_overall_score   — 종합 점수
          orig_perceived_age   — 인지 나이
          orig_overall_opinion — 종합 소견
          recommendation       — 관리 권고사항

        reference_baseline 필드가 없으면 기존 독립 분석 방식으로 폴백한다.
        """
        if not response_text or not response_text.strip():
            raise ValueError("[RGP] LLM 응답이 비어있습니다.")

        # 마크다운 코드블록 제거
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
            response_text = "\n".join(lines).strip()

        try:
            rj = json.loads(response_text)
        except json.JSONDecodeError as e:
            log.error("[RGP] JSON 파싱 실패: %s", e)
            # JSON 복구 시도: 여러 방법으로 복구
            recovered = False
            
            # 방법 1: 마지막 중괄호 찾기
            try:
                last_brace = response_text.rfind('}')
                if last_brace > 0:
                    recovered_text = response_text[:last_brace + 1]
                    rj = json.loads(recovered_text)
                    log.warning("[RGP] JSON 복구 성공 (방법1): 마지막 불완전 부분 제거됨")
                    recovered = True
            except Exception:
                pass
            
            # 방법 2: 문자열이 닫히지 않은 경우 처리
            if not recovered:
                try:
                    # 따옴표 균형 맞추기
                    quote_count = response_text.count('"')
                    if quote_count % 2 != 0:
                        # 마지막 따옴표 추가
                        recovered_text = response_text + '"'
                        rj = json.loads(recovered_text)
                        log.warning("[RGP] JSON 복구 성공 (방법2): 마지막 따옴표 추가")
                        recovered = True
                except Exception:
                    pass
            
            # 방법 3: 마지막 완전한 객체 찾기
            if not recovered:
                try:
                    # 마지막 완전한 중괄호 쌍 찾기
                    brace_count = 0
                    last_complete_pos = -1
                    for i, char in enumerate(reversed(response_text)):
                        if char == '}':
                            brace_count += 1
                        elif char == '{':
                            brace_count -= 1
                        if brace_count == 0:
                            last_complete_pos = len(response_text) - i
                            break
                    
                    if last_complete_pos > 0:
                        recovered_text = response_text[:last_complete_pos]
                        rj = json.loads(recovered_text)
                        log.warning("[RGP] JSON 복구 성공 (방법3): 마지막 완전한 객체 추출")
                        recovered = True
                except Exception:
                    pass
            
            if not recovered:
                raise ValueError(f"[RGP] LLM 응답 JSON 파싱 실패: {e}")

        # ── reference_baseline 존재 여부 확인 ────────────────────
        has_baseline = bool(rj.get("reference_baseline"))
        if not has_baseline:
            log.warning(
                "[RGP] reference_baseline 필드 없음. "
                "Gemini가 3단계 절차를 따르지 않은 것으로 판단. "
                "orig_metric_scores 직접 사용으로 폴백."
            )

        # ── 복원 기준선 로그 ──────────────────────────────────────
        if has_baseline:
            for cat, desc in rj["reference_baseline"].items():
                log.debug("[RGP] 기준선[%s]: %s", cat, desc[:80])

        # ── 항목 점수 파싱 ────────────────────────────────────────
        llm_scores   = rj.get("orig_metric_scores",   {})
        llm_opinions = rj.get("orig_metric_opinions",  {})
        corrections  = rj.get("score_reasons",         {})

        # CV 분석기 점수 보정 설정 로드
        try:
            api_config             = get_llm_api_config()
            sc_cfg                 = api_config.get("score_correction", {})
            sc_enabled             = sc_cfg.get("enabled", False)
            sc_mode                = sc_cfg.get("mode", "hybrid")
            a_weight               = sc_cfg.get("analyzer_weight", 0.7)
            l_weight               = sc_cfg.get("llm_weight", 0.3)
            dw_cfg                 = sc_cfg.get("dynamic_weighting", {})
            dw_enabled             = dw_cfg.get("enabled", False)
            dw_threshold           = dw_cfg.get("score_difference_threshold", 15.0)
        except Exception:
            sc_enabled, sc_mode    = False, "hybrid"
            a_weight, l_weight     = 0.7, 0.3
            dw_enabled, dw_threshold = False, 15.0

        metric_opinions = []
        for key, display, category, _ in _METRIC_META:
            cv_score  = float(orig_measurements_report.get(key, 0) or 0)
            llm_score = float(llm_scores.get(key, cv_score))

            # 보정 이유 로그
            reason = corrections.get(key, "")
            if reason:
                log.debug("[RGP] 보정[%s]: %s", key, reason)
            _monitor_score_difference(cv_score, llm_score, f"{display}(RGP)")

            # 하이브리드 보정
            if sc_enabled:
                final_score = _apply_score_correction(
                    cv_score, llm_score,
                    sc_mode, a_weight, l_weight, dw_enabled, dw_threshold,
                )
            else:
                # 보정 비활성화 → LLM(reference_guided) 점수 우선
                final_score = llm_score

            # 소견에 산출 근거 부기
            base_opinion = llm_opinions.get(key, "")
            if reason and base_opinion:
                opinion_text = f"{base_opinion} [산출근거: {reason}]"
            else:
                opinion_text = base_opinion

            # reference_guided 모드에서는 근거가 이미 소견에 포함되어 있으므로 reason 필드는 비움
            metric_opinions.append(MetricOpinion(
                key=key,
                display_name=display,
                category=category,
                score=final_score,
                grade=_grade_label(final_score),
                opinion=opinion_text,
                reason="",  # reference_guided 모드에서는 중복 표시 방지
            ))

        # ── 종합 점수 ─────────────────────────────────────────────
        llm_overall   = float(rj.get("orig_overall_score",   orig_overall_score))
        llm_age       = float(rj.get("orig_perceived_age",   orig_perceived_age))
        _monitor_score_difference(orig_overall_score, llm_overall, "종합점수(RGP)")

        if sc_enabled:
            final_overall = _apply_score_correction(
                orig_overall_score, llm_overall,
                sc_mode, a_weight, l_weight, dw_enabled, dw_threshold,
            )
        else:
            final_overall = llm_overall

        return SkinLLMReport(
            overall_score=final_overall,
            perceived_age=llm_age,
            metric_opinions=metric_opinions,
            overall_opinion=rj.get("orig_overall_opinion", ""),
            recommendation=rj.get("recommendation", ""),
            raw_response=response_text,
            scores_adjusted=has_baseline,
            matched_products=matched_products,
        )

    def _parse_dual_response(
        self,
        response_text: str,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        ideal_measurements_report: Dict[str, Any],
        ideal_overall_score: float,
        ideal_perceived_age: float,
        matched_products: List[Dict[str, Any]],
    ) -> tuple[SkinLLMReport, SkinLLMReport]:
        """듀얼 이미지 응답 파싱"""
        log.info(f"[LLM] 듀얼 응답 원본 (길이={len(response_text)}): {response_text[:1000]}...")
        if not response_text or response_text.strip() == "":
            raise ValueError("LLM 응답이 비어있습니다.")
        
        # 마크다운 코드 블록 제거 (```json ... ```)
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]  # 첫 줄 제거
            if lines[-1].startswith("```"):
                lines = lines[:-1]  # 마지막 줄 제거
            response_text = "\n".join(lines).strip()
        
        try:
            # JSON 파싱
            response_json = json.loads(response_text)
        except json.JSONDecodeError as e:
            log.error("[LLM] 듀얼 응답 JSON 파싱 실패: %s", e)
            # JSON 복구 시도
            recovered = False
            
            # 방법 1: 마지막 중괄호 찾기
            try:
                last_brace = response_text.rfind('}')
                if last_brace > 0:
                    recovered_text = response_text[:last_brace + 1]
                    response_json = json.loads(recovered_text)
                    log.warning("[LLM] JSON 복구 성공 (방법1): 마지막 불완전 부분 제거됨")
                    recovered = True
            except Exception:
                pass
            
            # 방법 2: 문자열이 닫히지 않은 경우 처리
            if not recovered:
                try:
                    quote_count = response_text.count('"')
                    if quote_count % 2 != 0:
                        recovered_text = response_text + '"'
                        response_json = json.loads(recovered_text)
                        log.warning("[LLM] JSON 복구 성공 (방법2): 마지막 따옴표 추가")
                        recovered = True
                except Exception:
                    pass
            
            # 방법 3: 마지막 완전한 객체 찾기
            if not recovered:
                try:
                    brace_count = 0
                    last_complete_pos = -1
                    for i, char in enumerate(reversed(response_text)):
                        if char == '}':
                            brace_count += 1
                        elif char == '{':
                            brace_count -= 1
                        if brace_count == 0:
                            last_complete_pos = len(response_text) - i
                            break
                    
                    if last_complete_pos > 0:
                        recovered_text = response_text[:last_complete_pos]
                        response_json = json.loads(recovered_text)
                        log.warning("[LLM] JSON 복구 성공 (방법3): 마지막 완전한 객체 추출")
                        recovered = True
                except Exception:
                    pass
            
            if not recovered:
                raise ValueError(f"[LLM] 듀얼 응답 JSON 파싱 실패: {e}")
            
            # 원본 metric_opinions 파싱
            orig_metric_opinions = []
            orig_metric_scores = response_json.get("original_metric_scores", {})
            orig_metric_reasons = response_json.get("original_metric_reasons", {})
            for key, display, category, _ in _METRIC_META:
                # LLM이 측정한 점수를 항상 우선 사용
                if key in orig_metric_scores:
                    score = orig_metric_scores[key]
                else:
                    # LLM 점수가 없으면 원본 측정 점수를 폴백으로 사용
                    score = orig_measurements_report.get(key, 0)
                opinion = response_json.get("original_metric_opinions", {}).get(key, "")
                reason = orig_metric_reasons.get(key, "")
                
                orig_metric_opinions.append(MetricOpinion(
                    key=key,
                    display_name=display,
                    category=category,
                    score=score,
                    grade=_grade_label(score),
                    opinion=opinion,
                    reason=reason,
                ))
            
            # 복원 metric_opinions 파싱
            ideal_metric_opinions = []
            ideal_metric_scores = response_json.get("restored_metric_scores", {})
            ideal_metric_reasons = response_json.get("restored_metric_reasons", {})
            for key, display, category, _ in _METRIC_META:
                # LLM이 측정한 점수를 항상 우선 사용
                if key in ideal_metric_scores:
                    score = ideal_metric_scores[key]
                else:
                    # LLM 점수가 없으면 복원 측정 점수를 폴백으로 사용
                    score = ideal_measurements_report.get(key, 0)
                opinion = response_json.get("restored_metric_opinions", {}).get(key, "")
                reason = ideal_metric_reasons.get(key, "")
                
                ideal_metric_opinions.append(MetricOpinion(
                    key=key,
                    display_name=display,
                    category=category,
                    score=score,
                    grade=_grade_label(score),
                    opinion=opinion,
                    reason=reason,
                ))
            
            # 종합 소견
            orig_overall_opinion = response_json.get("original_overall_opinion", "")
            ideal_overall_opinion = response_json.get("restored_overall_opinion", "")
            recommendation = response_json.get("recommendation", "")

            log.info(f"[LLM] 추출된 필드: original_overall_opinion={len(orig_overall_opinion)}, ideal_overall_opinion={len(ideal_overall_opinion)}, recommendation={len(recommendation)}")
            
            # 점수 미제공 모드인 경우 응답에서 점수 추출
            if "original_overall_score" in response_json:
                llm_orig_overall_score = response_json["original_overall_score"]
            if "restored_overall_score" in response_json:
                llm_ideal_overall_score = response_json["restored_overall_score"]
            if "original_perceived_age" in response_json:
                orig_perceived_age = response_json["original_perceived_age"]
            if "restored_perceived_age" in response_json:
                ideal_perceived_age = response_json["restored_perceived_age"]
            
            # 점수 보정 적용
            try:
                api_config = get_llm_api_config()
                score_correction_config = api_config.get("score_correction", {})
                score_correction_enabled = score_correction_config.get("enabled", False)
                
                # 동적 가중치 설정 (score_correction과 독립적으로 작동)
                dynamic_weighting_config = score_correction_config.get("dynamic_weighting", {})
                dynamic_weighting_enabled = dynamic_weighting_config.get("enabled", False)
                score_difference_threshold = dynamic_weighting_config.get("score_difference_threshold", 15.0)
                
                # 오탐 방지 설정 (자체 분석기 내 원본-복원 점수 차이 기반)
                anomaly_detection_config = score_correction_config.get("anomaly_detection", {})
                anomaly_detection_enabled = anomaly_detection_config.get("enabled", False)
                orig_ideal_diff_threshold = anomaly_detection_config.get("orig_ideal_diff_threshold", 15.0)
                
                if score_correction_enabled:
                    correction_mode = score_correction_config.get("mode", "hybrid")
                    analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
                    llm_weight = score_correction_config.get("llm_weight", 0.3)
                    
                    log.info(f"[점수 보정] 활성화: mode={correction_mode}, analyzer_weight={analyzer_weight}, llm_weight={llm_weight}, dynamic_weighting={dynamic_weighting_enabled}")
                    if anomaly_detection_enabled:
                        log.info(f"[오탐 방지] 활성화: orig_ideal_diff_threshold={orig_ideal_diff_threshold}")
                    
                    # 종합 점수 모니터링
                    _monitor_score_difference(orig_overall_score, llm_orig_overall_score, "종합 점수 (원본)")
                    _monitor_score_difference(ideal_overall_score, llm_ideal_overall_score, "종합 점수 (복원)")
                    
                    # 종합 점수 보정
                    orig_overall_score = _apply_score_correction(
                        orig_overall_score, llm_orig_overall_score,
                        correction_mode, analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    ideal_overall_score = _apply_score_correction(
                        ideal_overall_score, llm_ideal_overall_score,
                        correction_mode, analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    
                    # 개별 항목 점수 보정
                    for i, (key, display, category, _) in enumerate(_METRIC_META):
                        # 원본 점수 보정
                        if key in orig_metric_scores:
                            analyzer_score = orig_measurements_report.get(key, 0)
                            llm_score = orig_metric_scores[key]
                            
                            # 오탐 방지: 자체 분석기 내 원본-복원 점수 차이 확인
                            if anomaly_detection_enabled and key in ideal_measurements_report:
                                orig_analyzer_score = orig_measurements_report.get(key, 0)
                                ideal_analyzer_score = ideal_measurements_report.get(key, 0)
                                orig_ideal_diff = abs(orig_analyzer_score - ideal_analyzer_score)
                                if orig_ideal_diff >= orig_ideal_diff_threshold:
                                    log.info(f"[오탐 방지] {display}: 원본-복원 차이 {orig_ideal_diff:.1f} >= 임계값 {orig_ideal_diff_threshold}, 자체 분석기 점수 사용")
                                    orig_metric_opinions[i].score = orig_analyzer_score
                                    orig_metric_opinions[i].grade = _grade_label(orig_analyzer_score)
                                    continue
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (원본)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                correction_mode, analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold
                            )
                            orig_metric_opinions[i].score = corrected_score
                            orig_metric_opinions[i].grade = _grade_label(corrected_score)
                        
                        # 복원 점수 보정
                        if key in ideal_metric_scores:
                            analyzer_score = ideal_measurements_report.get(key, 0)
                            llm_score = ideal_metric_scores[key]
                            
                            # 오탐 방지: 자체 분석기 내 원본-복원 점수 차이 확인
                            if anomaly_detection_enabled and key in orig_measurements_report:
                                orig_analyzer_score = orig_measurements_report.get(key, 0)
                                ideal_analyzer_score = ideal_measurements_report.get(key, 0)
                                orig_ideal_diff = abs(orig_analyzer_score - ideal_analyzer_score)
                                if orig_ideal_diff >= orig_ideal_diff_threshold:
                                    log.info(f"[오탐 방지] {display}: 원본-복원 차이 {orig_ideal_diff:.1f} >= 임계값 {orig_ideal_diff_threshold}, 자체 분석기 점수 사용")
                                    ideal_metric_opinions[i].score = ideal_analyzer_score
                                    ideal_metric_opinions[i].grade = _grade_label(ideal_analyzer_score)
                                    continue
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (복원)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                correction_mode, analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold
                            )
                            ideal_metric_opinions[i].score = corrected_score
                            ideal_metric_opinions[i].grade = _grade_label(corrected_score)
                elif dynamic_weighting_enabled:
                    # score_correction 비활성화 시에도 동적 가중치 독립 작동
                    analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
                    llm_weight = score_correction_config.get("llm_weight", 0.3)
                    log.info(f"[동적 가중치] 듀얼 모드 독립 작동: score_difference_threshold={score_difference_threshold}, 기본 가중치=자체{analyzer_weight}:LLM{llm_weight}")
                    if anomaly_detection_enabled:
                        log.info(f"[오탐 방지] 활성화: orig_ideal_diff_threshold={orig_ideal_diff_threshold}")
                    
                    # 종합 점수 모니터링
                    _monitor_score_difference(orig_overall_score, llm_orig_overall_score, "종합 점수 (원본)")
                    _monitor_score_difference(ideal_overall_score, llm_ideal_overall_score, "종합 점수 (복원)")
                    
                    # 종합 점수 보정 (config 가중치 사용)
                    orig_overall_score = _apply_score_correction(
                        orig_overall_score, llm_orig_overall_score,
                        "hybrid", analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    ideal_overall_score = _apply_score_correction(
                        ideal_overall_score, llm_ideal_overall_score,
                        "hybrid", analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    
                    # 개별 항목 점수 보정
                    for i, (key, display, category, _) in enumerate(_METRIC_META):
                        # 원본 점수 보정
                        if key in orig_metric_scores:
                            analyzer_score = orig_measurements_report.get(key, 0)
                            llm_score = orig_metric_scores[key]
                            
                            # 오탐 방지: 자체 분석기 내 원본-복원 점수 차이 확인
                            if anomaly_detection_enabled and key in ideal_measurements_report:
                                orig_analyzer_score = orig_measurements_report.get(key, 0)
                                ideal_analyzer_score = ideal_measurements_report.get(key, 0)
                                orig_ideal_diff = abs(orig_analyzer_score - ideal_analyzer_score)
                                if orig_ideal_diff >= orig_ideal_diff_threshold:
                                    log.info(f"[오탐 방지] {display}: 원본-복원 차이 {orig_ideal_diff:.1f} >= 임계값 {orig_ideal_diff_threshold}, 자체 분석기 점수 사용")
                                    orig_metric_opinions[i].score = orig_analyzer_score
                                    orig_metric_opinions[i].grade = _grade_label(orig_analyzer_score)
                                    continue
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (원본)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                "hybrid", analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold
                            )
                            orig_metric_opinions[i].score = corrected_score
                            orig_metric_opinions[i].grade = _grade_label(corrected_score)
                        
                        # 복원 점수 보정
                        if key in ideal_metric_scores:
                            analyzer_score = ideal_measurements_report.get(key, 0)
                            llm_score = ideal_metric_scores[key]
                            
                            # 오탐 방지: 자체 분석기 내 원본-복원 점수 차이 확인
                            if anomaly_detection_enabled and key in orig_measurements_report:
                                orig_analyzer_score = orig_measurements_report.get(key, 0)
                                ideal_analyzer_score = ideal_measurements_report.get(key, 0)
                                orig_ideal_diff = abs(orig_analyzer_score - ideal_analyzer_score)
                                if orig_ideal_diff >= orig_ideal_diff_threshold:
                                    log.info(f"[오탐 방지] {display}: 원본-복원 차이 {orig_ideal_diff:.1f} >= 임계값 {orig_ideal_diff_threshold}, 자체 분석기 점수 사용")
                                    ideal_metric_opinions[i].score = ideal_analyzer_score
                                    ideal_metric_opinions[i].grade = _grade_label(ideal_analyzer_score)
                                    continue
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (복원)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                "hybrid", analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold
                            )
                            ideal_metric_opinions[i].score = corrected_score
                            ideal_metric_opinions[i].grade = _grade_label(corrected_score)
                else:
                    # 점수 보정 비활성화: 점수 차이만 모니터링
                    _monitor_score_difference(orig_overall_score, llm_orig_overall_score, "종합 점수 (원본)")
                    _monitor_score_difference(ideal_overall_score, llm_ideal_overall_score, "종합 점수 (복원)")
                    
                    if anomaly_detection_enabled:
                        log.info(f"[오탐 방지] 활성화: orig_ideal_diff_threshold={orig_ideal_diff_threshold}")
                    
                    # 개별 항목 점수 차이 모니터링 및 오탐 방지
                    for i, (key, display, category, _) in enumerate(_METRIC_META):
                        # 오탐 방지: 자체 분석기 내 원본-복원 점수 차이 확인
                        if anomaly_detection_enabled and key in orig_measurements_report and key in ideal_measurements_report:
                            orig_analyzer_score = orig_measurements_report.get(key, 0)
                            ideal_analyzer_score = ideal_measurements_report.get(key, 0)
                            orig_ideal_diff = abs(orig_analyzer_score - ideal_analyzer_score)
                            if orig_ideal_diff >= orig_ideal_diff_threshold:
                                log.info(f"[오탐 방지] {display}: 원본-복원 차이 {orig_ideal_diff:.1f} >= 임계값 {orig_ideal_diff_threshold}, 자체 분석기 점수 사용")
                                if key in orig_metric_scores:
                                    orig_metric_opinions[i].score = orig_analyzer_score
                                    orig_metric_opinions[i].grade = _grade_label(orig_analyzer_score)
                                if key in ideal_metric_scores:
                                    ideal_metric_opinions[i].score = ideal_analyzer_score
                                    ideal_metric_opinions[i].grade = _grade_label(ideal_analyzer_score)
                                continue
                        
                        # 점수 차이 모니터링
                        if key in orig_metric_scores:
                            analyzer_score = orig_measurements_report.get(key, 0)
                            llm_score = orig_metric_scores[key]
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (원본)")
                        
                        if key in ideal_metric_scores:
                            analyzer_score = ideal_measurements_report.get(key, 0)
                            llm_score = ideal_metric_scores[key]
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (복원)")
                    
                    # LLM 점수 사용
                    orig_overall_score = llm_orig_overall_score
                    ideal_overall_score = llm_ideal_overall_score
            except Exception as e:
                log.warning(f"[점수 보정] 적용 실패, LLM 점수 사용: {e}")
                orig_overall_score = llm_orig_overall_score
                ideal_overall_score = llm_ideal_overall_score
            
            orig_report = SkinLLMReport(
                overall_score=orig_overall_score,
                perceived_age=orig_perceived_age,
                metric_opinions=orig_metric_opinions,
                overall_opinion=orig_overall_opinion,
                recommendation=recommendation,
                raw_response=response_text,
                scores_adjusted=False,  # 듀얼 모드에서는 점수 조정 미사용
                matched_products=matched_products,  # DB 매칭 제품
            )

            ideal_report = SkinLLMReport(
                overall_score=ideal_overall_score,
                perceived_age=ideal_perceived_age,
                metric_opinions=ideal_metric_opinions,
                overall_opinion=ideal_overall_opinion,
                recommendation=recommendation,
                raw_response=response_text,
                scores_adjusted=False,  # 듀얼 모드에서는 점수 조정 미사용
                matched_products=matched_products,  # DB 매칭 제품
            )
            
            return orig_report, ideal_report
            
        except json.JSONDecodeError as e:
            log.error(f"[LLM] JSON 파싱 실패: {e}")
            raise ValueError(f"LLM 응답 JSON 파싱 실패: {e}")
