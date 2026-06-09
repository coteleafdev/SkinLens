"""ReportGenerationMixin — LLM 소견 '생성/프롬프트' 메서드."""
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
from src.llm.llm_reporter_common import (
    _METRIC_META,
    _get_metric_trust_level,
    _apply_advanced_score_correction,
    _apply_score_correction,
    _monitor_score_difference,
    _is_response_truncated,
    _identify_missing_fields,
    _build_field_completion_prompt,
    _merge_json_responses,
)


class ReportGenerationMixin:
    """소견 생성 메서드. _BaseReporter(self) 의 _provider/_call_llm/설정 사용."""

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
        current_max_tokens = self.max_output_tokens_single
        max_token_increase_retries = 2  # 토큰 증가 재시도 횟수
        
        for attempt in range(self.max_retries + 1 + max_token_increase_retries):
            try:
                if self.progress_callback:
                    self.progress_callback(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1 + max_token_increase_retries})")
                else:
                    log.info(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1 + max_token_increase_retries}, max_tokens={current_max_tokens})")

                # LLM API 호출
                # 점수 제공 시 낮은 temperature (일관성), 소견만 생성 시 높은 temperature (다양성)
                temp_to_use = getattr(self, 'temperature_scoring', self.temperature) if provide_scores else getattr(self, 'temperature_opinion', self.temperature)
                response_text: str = self._call_llm(
                    system_prompt,
                    user_prompt,
                    [image_path],
                    max_output_tokens=current_max_tokens,
                    temperature=temp_to_use,
                )

                # 응답 완전성 검사
                if _is_response_truncated(response_text):
                    if attempt < self.max_retries + max_token_increase_retries:
                        log.warning(
                            "[LLM] 응답 짤림 감지 - 시도=%d, 현재_tokens=%d, 응답길이=%d, 증가후_tokens=%d",
                            attempt + 1,
                            current_max_tokens,
                            len(response_text),
                            int(current_max_tokens * 1.5)
                        )
                        current_max_tokens = int(current_max_tokens * 1.5)  # 1.5배 증가
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        log.error(
                            "[LLM] 응답 짤림 최대 재시도 도달 - 시도=%d, 최종_tokens=%d, 응답길이=%d",
                            attempt + 1,
                            current_max_tokens,
                            len(response_text)
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
                # 응답이 짤렸는지 확인
                if response_text and _is_response_truncated(response_text):
                    if attempt < self.max_retries + max_token_increase_retries:
                        log.warning(
                            "[LLM] JSON 파싱 실패 및 응답 짤림 감지 - 시도=%d, 현재_tokens=%d, 응답길이=%d, 증가후_tokens=%d, 에러=%s",
                            attempt + 1,
                            current_max_tokens,
                            len(response_text),
                            int(current_max_tokens * 1.5),
                            str(e)
                        )
                        current_max_tokens = int(current_max_tokens * 1.5)
                        time.sleep(self.retry_delay)
                        continue
                
                # JSON 파싱 오류는 재시도
                if attempt < self.max_retries:
                    log.warning(f"[LLM] JSON 파싱 실패 (시도 {attempt + 1}/{self.max_retries + 1}): {e}")
                    log.debug(f"[LLM] 응답 텍스트 (첫 500자): {response_text[:500]}")
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
        ref_image_path: str | Path,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        ref_measurements_report: Dict[str, Any],
        ref_overall_score: float,
        ref_perceived_age: float,
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
            ref_image_path,
            orig_measurements_report,
            orig_overall_score,
            orig_perceived_age,
            ref_measurements_report,
            ref_overall_score,
            ref_perceived_age,
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
        ref_image_path: str | Path,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        ref_measurements_report: Dict[str, Any],
        ref_overall_score: float = 0,
        ref_perceived_age: float = 0,
        provide_scores: bool = True,
        product_info: Optional[str] = None,
        survey_info: Optional[str] = None,
        skin_type: Optional[str] = None,
        concerns: Optional[List[str]] = None,
        matched_products: Optional[List[Dict[str, Any]]] = None,
        # CV 점수 모니터링을 위한 매개변수
        orig_cv_measurements: Optional[Dict[str, Any]] = None,
        ref_cv_measurements: Optional[Dict[str, Any]] = None,
        orig_cv_overall: float = 0,
        ref_cv_overall: float = 0,
        orig_cv_age: float = 0,
        ref_cv_age: float = 0,
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
            ref_image_path:            복원 이미지 경로 (GAN 복원본)
            orig_measurements_report:  원본 CV 분석기 측정값
            orig_overall_score:        원본 CV 종합 점수
            orig_perceived_age:        원본 CV 인지 나이
            ref_measurements_report:   복원 CV 측정값 (비교 참고용)
            provide_scores:            CV 점수를 프롬프트에 포함할지 여부
            product_info:              외부에서 주입하는 제품 정보 (없으면 DB 매칭)

        Returns:
            SkinLLMReport: 복원 기준선 보정이 적용된 원본 보고서 1개
        """
        orig_image_path  = Path(orig_image_path)
        ref_image_path = Path(ref_image_path)
        if not orig_image_path.exists():
            raise FileNotFoundError(f"원본 이미지 없음: {orig_image_path}")
        if not ref_image_path.exists():
            raise FileNotFoundError(f"복원 이미지 없음: {ref_image_path}")

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
        # 외부에서 전달된 matched_products가 있으면 사용, 없으면 처방전 기반 매칭
        if matched_products is None:
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
                log.info(f"[RGP] 매칭된 제품 수: {len(matched_products)}")
            except Exception as e:
                log.warning("[RGP] 제품 매칭 실패: %s", e)
                matched_products = []  # 예외 발생 시 빈 리스트로 설정
                product_info = product_info or "[]"
        else:
            # 전달된 matched_products 사용
            product_info = product_info or json.dumps(matched_products, ensure_ascii=False)
            log.info(f"[RGP] 전달된 matched_products 사용: {len(matched_products)}")

        # ── 프롬프트 조립 ─────────────────────────────────────────
        system_prompt = _build_system_prompt()
        user_prompt   = _build_reference_guided_prompt(
            orig_measurements_report=orig_measurements_report,
            orig_overall_score=orig_overall_score,
            orig_perceived_age=orig_perceived_age,
            ref_measurements_report=ref_measurements_report,
            ref_overall_score=ref_overall_score,
            ref_perceived_age=ref_perceived_age,
            provide_scores=provide_scores,
            product_info=product_info,
            prescription_info=prescription_info,
            survey_info=survey_info,
        )

        # ── API 호출 (재시도 포함) ────────────────────────────────
        # 이미지 순서: [원본, 복원] — 프롬프트에서 "이미지 1=원본, 이미지 2=복원"으로 명시
        current_max_tokens = self.max_output_tokens_dual
        max_token_increase_retries = 2  # 토큰 증가 재시도 횟수
        response_text = None  # 초기화 (예외 발생 시 참조 오류 방지)
        
        for attempt in range(self.max_retries + 1 + max_token_increase_retries):
            try:
                if self.progress_callback:
                    self.progress_callback(
                        f"[복원 기반 분석] LLM 소견 생성 중... "
                        f"(시도 {attempt + 1}/{self.max_retries + 1 + max_token_increase_retries})"
                    )
                else:
                    log.info("[RGP] LLM API 호출 시작 (max_tokens=%d)", current_max_tokens)

                # 점수 제공 시 낮은 temperature (일관성), 소견만 생성 시 높은 temperature (다양성)
                temp_to_use = getattr(self, 'temperature_scoring', self.temperature) if provide_scores else getattr(self, 'temperature_opinion', self.temperature)
                response_text = self._call_llm(
                    system_prompt,
                    user_prompt,
                    [orig_image_path, ref_image_path],
                    max_output_tokens=current_max_tokens,
                    temperature=temp_to_use,
                )

                # 응답 완전성 검사
                if _is_response_truncated(response_text):
                    # 누락된 필드 식별 시도
                    try:
                        # 마크다운 코드 블록 제거 후 JSON 파싱 시도
                        clean_response = response_text
                        if clean_response.startswith("```"):
                            lines = clean_response.split("\n")
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            clean_response = "\n".join(lines).strip()
                        
                        # 부분 JSON 파싱 시도
                        partial_json = json.loads(clean_response)
                        
                        # 기대하는 필드 목록
                        expected_fields = [
                            "reference_baseline", "score_reasons", "orig_metric_scores",
                            "orig_metric_opinions", "orig_overall_score", "orig_perceived_age",
                            "orig_overall_opinion", "recommendation", "ref_metric_scores", "ref_metric_reasons"
                        ]
                        
                        missing_fields = _identify_missing_fields(clean_response, expected_fields)
                        
                        if missing_fields and len(missing_fields) < 10:  # 누락된 필드가 적으면 부분 완료 시도
                            log.info(f"[RGP] 응답 짤림 감지 - 누락된 필드 {len(missing_fields)}개: {missing_fields}")
                            
                            # 누락된 필드만 요청
                            completion_prompt = _build_field_completion_prompt(missing_fields, clean_response)
                            completion_response = self._call_llm(
                                system_prompt,
                                completion_prompt,
                                [],  # 이미지 없이 텍스트만
                                max_output_tokens=4096,
                                temperature=getattr(self, 'temperature_opinion', self.temperature),
                            )
                            
                            # 완료 응답 파싱
                            completion_json = json.loads(completion_response)
                            
                            # 응답 병합
                            merged_json = _merge_json_responses(partial_json, completion_json)
                            response_text = json.dumps(merged_json, ensure_ascii=False)
                            
                            log.info(f"[RGP] 누락된 필드 완료 성공 - 병합된 응답 길이: {len(response_text)}")
                        else:
                            # 누락된 필드가 너무 많으면 기존 방식대로 재시도
                            if attempt < self.max_retries + max_token_increase_retries:
                                log.warning(
                                    "[RGP] 응답 짤림 감지 - 누락된 필드가 너무 많음 ({len(missing_fields)}개) - 토큰 증가 재시도"
                                )
                                current_max_tokens = int(current_max_tokens * 1.5)
                                time.sleep(self.retry_delay)
                                continue
                            else:
                                log.error(
                                    "[RGP] 응답 짤림 최대 재시도 도달 - 시도=%d, 최종_tokens=%d, 응답길이=%d",
                                    attempt + 1,
                                    current_max_tokens,
                                    len(response_text)
                                )
                    except (json.JSONDecodeError, Exception) as e:
                        # JSON 파싱 실패하면 기존 방식대로 재시도
                        log.warning(f"[RGP] 부분 JSON 파싱 실패 - 기존 방식 재시도: {e}")
                        if attempt < self.max_retries + max_token_increase_retries:
                            log.warning(
                                "[RGP] 응답 짤림 감지 - 시도=%d, 현재_tokens=%d, 응답길이=%d, 증가후_tokens=%d",
                                attempt + 1,
                                current_max_tokens,
                                len(response_text),
                                int(current_max_tokens * 1.5)
                            )
                            current_max_tokens = int(current_max_tokens * 1.5)
                            time.sleep(self.retry_delay)
                            continue
                        else:
                            log.error(
                                "[RGP] 응답 짤림 최대 재시도 도달 - 시도=%d, 최종_tokens=%d, 응답길이=%d",
                                attempt + 1,
                                current_max_tokens,
                                len(response_text)
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
                # 응답이 짤렸는지 확인
                if response_text and _is_response_truncated(response_text):
                    if attempt < self.max_retries + max_token_increase_retries:
                        log.warning(
                            "[RGP] JSON 파싱 실패 및 응답 짤림 감지 - 시도=%d, 현재_tokens=%d, 응답길이=%d, 증가후_tokens=%d, 에러=%s",
                            attempt + 1,
                            current_max_tokens,
                            len(response_text),
                            int(current_max_tokens * 1.5),
                            str(e)
                        )
                        current_max_tokens = int(current_max_tokens * 1.5)
                        time.sleep(self.retry_delay)
                        continue
                
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
        ref_image_path: str | Path,
        orig_measurements_report: Dict[str, Any],
        orig_overall_score: float,
        orig_perceived_age: float,
        ref_measurements_report: Dict[str, Any],
        ref_overall_score: float,
        ref_perceived_age: float,
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
            ref_image_path: 복원 이미지 경로
            orig_measurements_report: 원본 측정 점수
            orig_overall_score: 원본 종합 점수
            orig_perceived_age: 원본 인지 나이
            ref_measurements_report: 복원 측정 점수
            ref_overall_score: 복원 종합 점수
            ref_perceived_age: 복원 인지 나이
            provide_scores: 점수 제공 여부
            product_info: 맞춤형 화장품 성분 정보
        
        Returns:
            tuple[SkinLLMReport, SkinLLMReport]: (원본 보고서, 복원 보고서)
        """
        # 처방전 계산 (피부 평가 점수 기반)
        from src.prescription.prescription_calculator import create_prescription

        log.info(f"[LLM] 처방전 계산 입력: orig_measurements_report keys={list(orig_measurements_report.keys())[:10]}")
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
        matched_products: List[Dict[str, Any]] = []  # 초기화
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
            matched_products = []  # 예외 발생 시 빈 리스트로 설정
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

        # CV 점수 모니터링을 위해 원본 점수 저장 (provide_scores=False일 때도 필요)
        orig_cv_measurements = orig_measurements_report.copy()
        ref_cv_measurements = ref_measurements_report.copy()
        orig_cv_overall = orig_overall_score
        ref_cv_overall = ref_overall_score
        orig_cv_age = orig_perceived_age
        ref_cv_age = ref_perceived_age

        # provide_scores=False이면 빈 점수를 전달하여 LLM이 직접 점수를 산출하도록 함
        # 하지만 CV 점수 모니터링을 위해 원본 점수는 위에 저장해둠
        if not provide_scores:
            log.info("[generate_dual_report] provide_scores=False → 빈 점수 전달 (LLM이 직접 점수 산출)")
            orig_measurements_report = {}
            ref_measurements_report = {}
            orig_overall_score = 0
            ref_overall_score = 0
            orig_perceived_age = 0
            ref_perceived_age = 0

        if _scoring_mode == "reference_guided":
            log.info("[generate_dual_report] scoring_mode=reference_guided → 복원 기반 모드로 라우팅")
            orig_report = self.generate_reference_guided_report(
                orig_image_path=orig_image_path,
                ref_image_path=ref_image_path,
                orig_measurements_report=orig_measurements_report,
                orig_overall_score=orig_overall_score,
                orig_perceived_age=orig_perceived_age,
                ref_measurements_report=ref_measurements_report,
                ref_overall_score=ref_overall_score,
                ref_perceived_age=ref_perceived_age,
                provide_scores=provide_scores,
                product_info=product_info,
                survey_info=survey_info,
                matched_products=matched_products,
                # CV 점수 모니터링을 위해 저장된 원본 점수 전달
                orig_cv_measurements=orig_cv_measurements,
                ref_cv_measurements=ref_cv_measurements,
                orig_cv_overall=orig_cv_overall,
                ref_cv_overall=ref_cv_overall,
                orig_cv_age=orig_cv_age,
                ref_cv_age=ref_cv_age,
            )
            # RGP 모드에서도 복원 이미지 점수를 생성하여 테이블에 표시
            # LLM 응답에서 ref_metric_scores를 추출하여 ref_metric_opinions 생성
            ref_metric_opinions = []
            
            # orig_report의 raw_response에서 ref_metric_scores 추출
            try:
                response_json = json.loads(orig_report.raw_response)
                ref_metric_scores = response_json.get("ref_metric_scores", {})
                ref_metric_reasons = response_json.get("ref_metric_reasons", {})
                # LLM 응답에서 ref_overall_score 추출 (provide_scores=False일 때 필요)
                llm_ref_overall_score = ref_overall_score
                llm_ref_perceived_age = ref_perceived_age
                if "ref_overall_score" in response_json:
                    llm_ref_overall_score = response_json["ref_overall_score"]
                    log.info(f"[RGP] LLM 응답에서 ref_overall_score 추출: {llm_ref_overall_score}")
                if "ref_perceived_age" in response_json:
                    llm_ref_perceived_age = response_json["ref_perceived_age"]
                    log.info(f"[RGP] LLM 응답에서 ref_perceived_age 추출: {llm_ref_perceived_age}")
                
                # CV 점수 모니터링을 위해 저장된 CV 점수 사용
                cv_measurements_for_monitoring = ref_cv_measurements if ref_cv_measurements else ref_measurements_report
                cv_overall_for_monitoring = ref_cv_overall if ref_cv_overall > 0 else ref_overall_score
                
                for key, display, category, _ in _METRIC_META:
                    if key in ref_metric_scores:
                        llm_score = ref_metric_scores[key]
                    else:
                        llm_score = ref_measurements_report.get(key, 0)
                    # CV 분석기 점수 (저장된 CV 점수 사용)
                    cv_score = cv_measurements_for_monitoring.get(key, 0)
                    # 점수 차이 모니터링
                    _monitor_score_difference(cv_score, llm_score, f"{display}(RGP)")
                    # RGP 모드에서는 복원 이미지 소견을 요청하지 않으므로 빈 문자열 사용
                    opinion = ""
                    reason = ref_metric_reasons.get(key, "")
                    
                    ref_metric_opinions.append(MetricOpinion(
                        key=key,
                        display_name=display,
                        category=category,
                        score=llm_score,
                        grade=_grade_label(llm_score),
                        opinion=opinion,
                        reason=reason,
                    ))
            except Exception as e:
                log.warning(f"[RGP] ref_metric_opinions 생성 실패: {e}")
                ref_metric_opinions = []
            
            # 복원 이미지 종합 점수 모니터링 (저장된 CV 점수 사용)
            _monitor_score_difference(cv_overall_for_monitoring, llm_ref_overall_score, "피부건강지수(RGP)")
            
            ref_report = SkinLLMReport(
                overall_score=llm_ref_overall_score,
                perceived_age=llm_ref_perceived_age,
                metric_opinions=ref_metric_opinions,
                overall_opinion="[reference_guided 모드: 복원 보고서는 별도 생성하지 않음]",
                recommendation="",
                raw_response="",
                matched_products=orig_report.matched_products,
            )
            return orig_report, ref_report

        log.info("[generate_dual_report] scoring_mode=independent → 기존 독립 분석 방식 사용")

        user_prompt = _build_dual_image_prompt(
            orig_measurements_report,
            orig_overall_score,
            orig_perceived_age,
            ref_measurements_report,
            ref_overall_score,
            ref_perceived_age,
            provide_scores=provide_scores,
            product_info=product_info,
            prescription_info=prescription_info,
            survey_info=survey_info,
        )
        
        # 이미지 로드
        orig_image_path = Path(orig_image_path)
        ref_image_path = Path(ref_image_path)
        if not orig_image_path.exists():
            raise FileNotFoundError(f"원본 이미지 파일을 찾을 수 없습니다: {orig_image_path}")
        if not ref_image_path.exists():
            raise FileNotFoundError(f"복원 이미지 파일을 찾을 수 없습니다: {ref_image_path}")
        
        # LLM API 호출 및 JSON 파싱 재시도
        current_max_tokens = self.max_output_tokens_dual
        max_token_increase_retries = 2  # 토큰 증가 재시도 횟수
        
        for attempt in range(self.max_retries + 1 + max_token_increase_retries):
            try:
                if self.progress_callback:
                    self.progress_callback(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1 + max_token_increase_retries})")
                else:
                    log.info(f"LLM 소견 생성 중... (시도 {attempt + 1}/{self.max_retries + 1 + max_token_increase_retries}, max_tokens={current_max_tokens})")

                # LLM API 호출
                # 점수 제공 시 낮은 temperature (일관성), 소견만 생성 시 높은 temperature (다양성)
                temp_to_use = getattr(self, 'temperature_scoring', self.temperature) if provide_scores else getattr(self, 'temperature_opinion', self.temperature)
                response_text: str = self._call_llm(
                    system_prompt,
                    user_prompt,
                    [orig_image_path, ref_image_path],
                    max_output_tokens=current_max_tokens,
                    temperature=temp_to_use,
                )

                # 응답 완전성 검사
                if _is_response_truncated(response_text):
                    # 누락된 필드 식별 시도
                    try:
                        # 마크다운 코드 블록 제거 후 JSON 파싱 시도
                        clean_response = response_text
                        if clean_response.startswith("```"):
                            lines = clean_response.split("\n")
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            clean_response = "\n".join(lines).strip()
                        
                        # 부분 JSON 파싱 시도
                        partial_json = json.loads(clean_response)
                        
                        # 기대하는 필드 목록 (듀얼 모드)
                        expected_fields = [
                            "original_metric_opinions", "restored_metric_opinions",
                            "original_overall_opinion", "restored_overall_opinion",
                            "original_overall_score", "restored_overall_score",
                            "original_perceived_age", "restored_perceived_age",
                            "recommendation"
                        ]
                        
                        missing_fields = _identify_missing_fields(clean_response, expected_fields)
                        
                        if missing_fields and len(missing_fields) < 10:  # 누락된 필드가 적으면 부분 완료 시도
                            log.info(f"[Dual] 응답 짤림 감지 - 누락된 필드 {len(missing_fields)}개: {missing_fields}")
                            
                            # 누락된 필드만 요청
                            completion_prompt = _build_field_completion_prompt(missing_fields, clean_response)
                            completion_response = self._call_llm(
                                system_prompt,
                                completion_prompt,
                                [],  # 이미지 없이 텍스트만
                                max_output_tokens=4096,
                                temperature=getattr(self, 'temperature_opinion', self.temperature),
                            )
                            
                            # 완료 응답 파싱
                            completion_json = json.loads(completion_response)
                            
                            # 응답 병합
                            merged_json = _merge_json_responses(partial_json, completion_json)
                            response_text = json.dumps(merged_json, ensure_ascii=False)
                            
                            log.info(f"[Dual] 누락된 필드 완료 성공 - 병합된 응답 길이: {len(response_text)}")
                        else:
                            # 누락된 필드가 너무 많으면 기존 방식대로 재시도
                            if attempt < self.max_retries + max_token_increase_retries:
                                log.warning(
                                    "[Dual] 응답 짤림 감지 - 누락된 필드가 너무 많음 ({len(missing_fields)}개) - 토큰 증가 재시도"
                                )
                                current_max_tokens = int(current_max_tokens * 1.5)
                                time.sleep(self.retry_delay)
                                continue
                            else:
                                log.error(
                                    "[Dual] 응답 짤림 최대 재시도 도달 - 시도=%d, 최종_tokens=%d, 응답길이=%d",
                                    attempt + 1,
                                    current_max_tokens,
                                    len(response_text)
                                )
                    except (json.JSONDecodeError, Exception) as e:
                        # JSON 파싱 실패하면 기존 방식대로 재시도
                        log.warning(f"[Dual] 부분 JSON 파싱 실패 - 기존 방식 재시도: {e}")
                        if attempt < self.max_retries + max_token_increase_retries:
                            log.warning(
                                "[Dual] 응답 짤림 감지 - 시도=%d, 현재_tokens=%d, 응답길이=%d, 증가후_tokens=%d",
                                attempt + 1,
                                current_max_tokens,
                                len(response_text),
                                int(current_max_tokens * 1.5)
                            )
                            current_max_tokens = int(current_max_tokens * 1.5)
                            time.sleep(self.retry_delay)
                            continue
                        else:
                            log.error(
                                "[Dual] 응답 짤림 최대 재시도 도달 - 시도=%d, 최종_tokens=%d, 응답길이=%d",
                                attempt + 1,
                                current_max_tokens,
                                len(response_text)
                            )

                # 응답 파싱
                return self._parse_dual_response(
                    response_text,
                    orig_measurements_report,
                    orig_overall_score,
                    orig_perceived_age,
                    ref_measurements_report,
                    ref_overall_score,
                    ref_perceived_age,
                    matched_products,  # DB 매칭 제품 전달
                )

            except (json.JSONDecodeError, ValueError) as e:
                # 응답이 짤렸는지 확인
                if response_text and _is_response_truncated(response_text):
                    if attempt < self.max_retries + max_token_increase_retries:
                        log.warning(
                            "[LLM] JSON 파싱 실패 및 응답 짤림 감지 - 시도=%d, 현재_tokens=%d, 응답길이=%d, 증가후_tokens=%d, 에러=%s",
                            attempt + 1,
                            current_max_tokens,
                            len(response_text),
                            int(current_max_tokens * 1.5),
                            str(e)
                        )
                        current_max_tokens = int(current_max_tokens * 1.5)
                        time.sleep(self.retry_delay)
                        continue
                
                # JSON 파싱 오류는 재시도
                if attempt < self.max_retries:
                    log.warning(f"[LLM] JSON 파싱 실패 (시도 {attempt + 1}/{self.max_retries + 1}): {e}")
                    log.debug(f"[LLM] 응답 텍스트 (첫 500자): {response_text[:500]}")
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

