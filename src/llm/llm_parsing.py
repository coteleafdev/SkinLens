"""ResponseParsingMixin — LLM 응답 '파싱→구조화' 메서드."""
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


class ResponseParsingMixin:
    """LLM 원응답을 SkinLLMReport 로 파싱. self 설정/헬퍼 사용."""

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
            
            # 방법 4: 마지막 콤마 뒤 잘린 부분 제거
            if not recovered:
                try:
                    # 마지막 콤마 찾기
                    last_comma = response_text.rfind(',')
                    if last_comma > 0:
                        # 마지막 콤마 뒤를 제거하고 중괄호 닫기
                        recovered_text = response_text[:last_comma] + '\n}'
                        rj = json.loads(recovered_text)
                        log.warning("[RGP] JSON 복구 성공 (방법4): 마지막 콤마 뒤 잘린 부분 제거")
                        recovered = True
                except Exception:
                    pass
            
            if not recovered:
                log.error("[RGP] JSON 복구 실패, 빈 결과 반환")
                # 빈 결과 반환
                return SkinLLMReport(
                    overall_opinion="",
                    overall_score=0,
                    perceived_age=0,
                    metric_opinions=[],
                    raw_response=response_text
                )

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
        
        log.info("[RGP] 기준선 로그 완료, 항목 점수 파싱 시작")

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
            log.info(f"[RGP] 점수 보정 설정: sc_enabled={sc_enabled}, sc_mode={sc_mode}, a_weight={a_weight}, l_weight={l_weight}, dw_enabled={dw_enabled}")
        except Exception as e:
            log.warning(f"[RGP] 점수 보정 설정 로드 실패: {e}")
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

            # 하이브리드 보정 (복원 기반 모드: 점수 차이가 크면 LLM 점수 우선)
            if sc_enabled:
                final_score = _apply_score_correction(
                    cv_score, llm_score,
                    sc_mode, a_weight, l_weight, dw_enabled, dw_threshold,
                    prefer_llm_on_large_diff=True,  # 복원 기반 모드에서 LLM 점수 우선
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
        _monitor_score_difference(orig_overall_score, llm_overall, "피부건강지수(RGP)")

        if sc_enabled:
            final_overall = _apply_score_correction(
                orig_overall_score, llm_overall,
                sc_mode, a_weight, l_weight, dw_enabled, dw_threshold,
                prefer_llm_on_large_diff=True,  # 복원 기반 모드에서 LLM 점수 우선
            )
        else:
            final_overall = llm_overall

        log.info(f"[RGP] SkinLLMReport 생성: matched_products={len(matched_products)}")
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
        ref_measurements_report: Dict[str, Any],
        ref_overall_score: float,
        ref_perceived_age: float,
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
            
            # 방법 4: 마지막 콤마 뒤 잘린 부분 제거
            if not recovered:
                try:
                    last_comma = response_text.rfind(',')
                    if last_comma > 0:
                        recovered_text = response_text[:last_comma] + '\n}'
                        response_json = json.loads(recovered_text)
                        log.warning("[LLM] JSON 복구 성공 (방법4): 마지막 콤마 뒤 잘린 부분 제거")
                        recovered = True
                except Exception:
                    pass
            
            if not recovered:
                raise ValueError(f"[LLM] 듀얼 응답 JSON 파싱 실패: {e}")
            
            # 원본 metric_opinions 파싱
            orig_metric_opinions = []
            orig_metric_scores = response_json.get("orig_metric_scores", {})
            orig_metric_reasons = response_json.get("orig_metric_reasons", {})
            for key, display, category, _ in _METRIC_META:
                # LLM이 측정한 점수를 항상 우선 사용
                if key in orig_metric_scores:
                    score = orig_metric_scores[key]
                else:
                    # LLM 점수가 없으면 원본 측정 점수를 폴백으로 사용
                    score = orig_measurements_report.get(key, 0)
                opinion = response_json.get("orig_metric_opinions", {}).get(key, "")
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
            
            # 복원 metric_opinions 파싱 (RGP 모드에서는 복원 이미지 소견을 요청하지 않음)
            ref_metric_opinions = []
            ref_metric_scores = response_json.get("ref_metric_scores", {})
            ref_metric_reasons = response_json.get("ref_metric_reasons", {})
            for key, display, category, _ in _METRIC_META:
                # LLM이 측정한 점수를 항상 우선 사용
                if key in ref_metric_scores:
                    score = ref_metric_scores[key]
                else:
                    # LLM 점수가 없으면 복원 측정 점수를 폴백으로 사용
                    score = ref_measurements_report.get(key, 0)
                # RGP 모드에서는 복원 이미지 소견을 요청하지 않으므로 빈 문자열 사용
                opinion = ""
                reason = ref_metric_reasons.get(key, "")

                ref_metric_opinions.append(MetricOpinion(
                    key=key,
                    display_name=display,
                    category=category,
                    score=score,
                    grade=_grade_label(score),
                    opinion=opinion,
                    reason=reason,
                ))
            
            # 종합 소견
            orig_overall_opinion = response_json.get("orig_overall_opinion", "")
            ref_overall_opinion = response_json.get("ref_overall_opinion", "")
            recommendation = response_json.get("recommendation", "")

            log.info(f"[LLM] 추출된 필드: original_overall_opinion={len(orig_overall_opinion)}, ref_overall_opinion={len(ref_overall_opinion)}, recommendation={len(recommendation)}")
            
            # 점수 미제공 모드인 경우 응답에서 점수 추출
            if "orig_overall_score" in response_json:
                llm_orig_overall_score = response_json["orig_overall_score"]
            if "ref_overall_score" in response_json:
                llm_ref_overall_score = response_json["ref_overall_score"]
            if "orig_perceived_age" in response_json:
                orig_perceived_age = response_json["orig_perceived_age"]
            if "ref_perceived_age" in response_json:
                ref_perceived_age = response_json["ref_perceived_age"]
            
            # 점수 보정 적용
            try:
                api_config = get_llm_api_config()
                score_correction_config = api_config.get("score_correction", {})
                score_correction_enabled = score_correction_config.get("enabled", False)
                log.info(f"[점수 보정] generate_dual_report: score_correction_config={score_correction_config}, score_correction_enabled={score_correction_enabled}")
                
                # 동적 가중치 설정 (score_correction과 독립적으로 작동)
                dynamic_weighting_config = score_correction_config.get("dynamic_weighting", {})
                dynamic_weighting_enabled = dynamic_weighting_config.get("enabled", False)
                score_difference_threshold = dynamic_weighting_config.get("score_difference_threshold", 15.0)
                
                # 오탐 방지 설정 (자체 분석기와 LLM의 원본-복원 차이 쌍 비교 기반)
                anomaly_detection_config = score_correction_config.get("anomaly_detection", {})
                anomaly_detection_enabled = anomaly_detection_config.get("enabled", False)
                diff_comparison_threshold = anomaly_detection_config.get("diff_comparison_threshold", 15.0)
                
                if score_correction_enabled:
                    correction_mode = score_correction_config.get("mode", "hybrid")
                    analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
                    llm_weight = score_correction_config.get("llm_weight", 0.3)
                    
                    log.info(f"[점수 보정] 활성화: mode={correction_mode}, analyzer_weight={analyzer_weight}, llm_weight={llm_weight}, dynamic_weighting={dynamic_weighting_enabled}")
                    if anomaly_detection_enabled:
                        log.info(f"[오탐 방지] 활성화: diff_comparison_threshold={diff_comparison_threshold}")
                    
                    # 종합 점수 모니터링
                    _monitor_score_difference(orig_overall_score, llm_orig_overall_score, "종합 점수 (원본)")
                    _monitor_score_difference(ref_overall_score, llm_ref_overall_score, "종합 점수 (복원)")
                    
                    # 종합 점수 보정
                    orig_overall_score = _apply_score_correction(
                        orig_overall_score, llm_orig_overall_score,
                        correction_mode, analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    ref_overall_score = _apply_score_correction(
                        ref_overall_score, llm_ref_overall_score,
                        correction_mode, analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    
                    # 개별 항목 점수 보정
                    log.info(f"[점수 보정] 개별 항목 점수 보정 시작: orig_metric_scores={len(orig_metric_scores)}개, ref_metric_scores={len(ref_metric_scores)}개")
                    for i, (key, display, category, _) in enumerate(_METRIC_META):
                        # 오탐 방지: 자체 분석기와 LLM의 원본-복원 차이 쌍 비교
                        if anomaly_detection_enabled and key in orig_measurements_report and key in ref_measurements_report and key in orig_metric_scores and key in ref_metric_scores:
                            orig_analyzer_score = orig_measurements_report.get(key, 0)
                            ref_analyzer_score = ref_measurements_report.get(key, 0)
                            orig_llm_score = orig_metric_scores[key]
                            ref_llm_score = ref_metric_scores[key]
                            
                            # 자체 분석기 원본-복원 차이
                            analyzer_diff = abs(orig_analyzer_score - ref_analyzer_score)
                            # LLM 원본-복원 차이
                            llm_diff = abs(orig_llm_score - ref_llm_score)
                            # 차이 비교: 자체 분석기 차이 - LLM 차이
                            diff_comparison = analyzer_diff - llm_diff
                            
                            if diff_comparison >= diff_comparison_threshold:
                                log.info(f"[오탐 방지] {display}: 자체 분석기 차이 {analyzer_diff:.1f} - LLM 차이 {llm_diff:.1f} = {diff_comparison:.1f} >= 임계값 {diff_comparison_threshold}, LLM 오탐으로 간주하여 자체 분석기 점수 사용")
                                orig_metric_opinions[i].score = orig_analyzer_score
                                orig_metric_opinions[i].grade = _grade_label(orig_analyzer_score)
                                ref_metric_opinions[i].score = ref_analyzer_score
                                ref_metric_opinions[i].grade = _grade_label(ref_analyzer_score)
                                continue
                            else:
                                log.debug(f"[오탐 방지] {display}: 자체 분석기 차이 {analyzer_diff:.1f} - LLM 차이 {llm_diff:.1f} = {diff_comparison:.1f} < 임계값 {diff_comparison_threshold}, LLM 정상 동작으로 간주하여 LLM 점수 사용")
                        
                        # 원본 점수 보정
                        if key in orig_metric_scores:
                            analyzer_score = orig_measurements_report.get(key, 0)
                            llm_score = orig_metric_scores[key]
                            
                            log.debug(f"[점수 보정] {display}: analyzer_score={analyzer_score}, llm_score={llm_score}")
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (원본)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                correction_mode, analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold,
                                metric_key=key, config=api_config
                            )
                            log.debug(f"[점수 보정] {display}: corrected_score={corrected_score}")
                            orig_metric_opinions[i].score = corrected_score
                            orig_metric_opinions[i].grade = _grade_label(corrected_score)
                        else:
                            # LLM 점수가 없는 경우 원본 측정 점수 사용
                            log.debug(f"[점수 보정] {display}: LLM 점수 없음, 원본 측정 점수 사용")
                            orig_metric_opinions[i].score = orig_measurements_report.get(key, 0)
                            orig_metric_opinions[i].grade = _grade_label(orig_metric_opinions[i].score)
                        
                        # 복원 점수 보정
                        if key in ref_metric_scores:
                            analyzer_score = ref_measurements_report.get(key, 0)
                            llm_score = ref_metric_scores[key]
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (복원)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                correction_mode, analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold,
                                metric_key=key, config=api_config
                            )
                            ref_metric_opinions[i].score = corrected_score
                            ref_metric_opinions[i].grade = _grade_label(corrected_score)
                elif dynamic_weighting_enabled:
                    # score_correction 비활성화 시에도 동적 가중치 독립 작동
                    analyzer_weight = score_correction_config.get("analyzer_weight", 0.7)
                    llm_weight = score_correction_config.get("llm_weight", 0.3)
                    log.info(f"[동적 가중치] 듀얼 모드 독립 작동: score_difference_threshold={score_difference_threshold}, 기본 가중치=자체{analyzer_weight}:LLM{llm_weight}")
                    if anomaly_detection_enabled:
                        log.info(f"[오탐 방지] 활성화: diff_comparison_threshold={diff_comparison_threshold}")
                    
                    # 종합 점수 모니터링
                    _monitor_score_difference(orig_overall_score, llm_orig_overall_score, "종합 점수 (원본)")
                    _monitor_score_difference(ref_overall_score, llm_ref_overall_score, "종합 점수 (복원)")
                    
                    # 종합 점수 보정 (config 가중치 사용)
                    orig_overall_score = _apply_score_correction(
                        orig_overall_score, llm_orig_overall_score,
                        "hybrid", analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    ref_overall_score = _apply_score_correction(
                        ref_overall_score, llm_ref_overall_score,
                        "hybrid", analyzer_weight, llm_weight,
                        dynamic_weighting_enabled, score_difference_threshold
                    )
                    
                    # 개별 항목 점수 보정
                    for i, (key, display, category, _) in enumerate(_METRIC_META):
                        # 오탐 방지: 자체 분석기와 LLM의 원본-복원 차이 쌍 비교
                        if anomaly_detection_enabled and key in orig_measurements_report and key in ref_measurements_report and key in orig_metric_scores and key in ref_metric_scores:
                            orig_analyzer_score = orig_measurements_report.get(key, 0)
                            ref_analyzer_score = ref_measurements_report.get(key, 0)
                            orig_llm_score = orig_metric_scores[key]
                            ref_llm_score = ref_metric_scores[key]
                            
                            # 자체 분석기 원본-복원 차이
                            analyzer_diff = abs(orig_analyzer_score - ref_analyzer_score)
                            # LLM 원본-복원 차이
                            llm_diff = abs(orig_llm_score - ref_llm_score)
                            # 차이 비교: 자체 분석기 차이 - LLM 차이
                            diff_comparison = analyzer_diff - llm_diff
                            
                            if diff_comparison >= diff_comparison_threshold:
                                log.info(f"[오탐 방지] {display}: 자체 분석기 차이 {analyzer_diff:.1f} - LLM 차이 {llm_diff:.1f} = {diff_comparison:.1f} >= 임계값 {diff_comparison_threshold}, LLM 오탐으로 간주하여 자체 분석기 점수 사용")
                                orig_metric_opinions[i].score = orig_analyzer_score
                                orig_metric_opinions[i].grade = _grade_label(orig_analyzer_score)
                                ref_metric_opinions[i].score = ref_analyzer_score
                                ref_metric_opinions[i].grade = _grade_label(ref_analyzer_score)
                                continue
                            else:
                                log.debug(f"[오탐 방지] {display}: 자체 분석기 차이 {analyzer_diff:.1f} - LLM 차이 {llm_diff:.1f} = {diff_comparison:.1f} < 임계값 {diff_comparison_threshold}, LLM 정상 동작으로 간주하여 LLM 점수 사용")
                        
                        # 원본 점수 보정
                        if key in orig_metric_scores:
                            analyzer_score = orig_measurements_report.get(key, 0)
                            llm_score = orig_metric_scores[key]
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (원본)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                "hybrid", analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold,
                                metric_key=key, config=api_config
                            )
                            orig_metric_opinions[i].score = corrected_score
                            orig_metric_opinions[i].grade = _grade_label(corrected_score)
                        
                        # 복원 점수 보정
                        if key in ref_metric_scores:
                            analyzer_score = ref_measurements_report.get(key, 0)
                            llm_score = ref_metric_scores[key]
                            
                            # 개별 항목 점수 차이 모니터링
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (복원)")
                            
                            corrected_score = _apply_score_correction(
                                analyzer_score, llm_score,
                                "hybrid", analyzer_weight, llm_weight,
                                dynamic_weighting_enabled, score_difference_threshold,
                                metric_key=key, config=api_config
                            )
                            ref_metric_opinions[i].score = corrected_score
                            ref_metric_opinions[i].grade = _grade_label(corrected_score)
                else:
                    # 점수 보정 비활성화: 점수 차이만 모니터링
                    _monitor_score_difference(orig_overall_score, llm_orig_overall_score, "종합 점수 (원본)")
                    _monitor_score_difference(ref_overall_score, llm_ref_overall_score, "종합 점수 (복원)")
                    
                    if anomaly_detection_enabled:
                        log.info(f"[오탐 방지] 활성화: diff_comparison_threshold={diff_comparison_threshold}")
                    
                    # 개별 항목 점수 차이 모니터링 및 오탐 방지
                    for i, (key, display, category, _) in enumerate(_METRIC_META):
                        # 오탐 방지: 자체 분석기와 LLM의 원본-복원 차이 쌍 비교
                        if anomaly_detection_enabled and key in orig_measurements_report and key in ref_measurements_report and key in orig_metric_scores and key in ref_metric_scores:
                            orig_analyzer_score = orig_measurements_report.get(key, 0)
                            ref_analyzer_score = ref_measurements_report.get(key, 0)
                            orig_llm_score = orig_metric_scores[key]
                            ref_llm_score = ref_metric_scores[key]
                            
                            # 자체 분석기 원본-복원 차이
                            analyzer_diff = abs(orig_analyzer_score - ref_analyzer_score)
                            # LLM 원본-복원 차이
                            llm_diff = abs(orig_llm_score - ref_llm_score)
                            # 차이 비교: 자체 분석기 차이 - LLM 차이
                            diff_comparison = analyzer_diff - llm_diff
                            
                            if diff_comparison >= diff_comparison_threshold:
                                log.info(f"[오탐 방지] {display}: 자체 분석기 차이 {analyzer_diff:.1f} - LLM 차이 {llm_diff:.1f} = {diff_comparison:.1f} >= 임계값 {diff_comparison_threshold}, LLM 오탐으로 간주하여 자체 분석기 점수 사용")
                                orig_metric_opinions[i].score = orig_analyzer_score
                                orig_metric_opinions[i].grade = _grade_label(orig_analyzer_score)
                                ref_metric_opinions[i].score = ref_analyzer_score
                                ref_metric_opinions[i].grade = _grade_label(ref_analyzer_score)
                                continue
                            else:
                                log.debug(f"[오탐 방지] {display}: 자체 분석기 차이 {analyzer_diff:.1f} - LLM 차이 {llm_diff:.1f} = {diff_comparison:.1f} < 임계값 {diff_comparison_threshold}, LLM 정상 동작으로 간주하여 LLM 점수 사용")
                        
                        # 점수 차이 모니터링
                        if key in orig_metric_scores:
                            analyzer_score = orig_measurements_report.get(key, 0)
                            llm_score = orig_metric_scores[key]
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (원본)")
                        
                        if key in ref_metric_scores:
                            analyzer_score = ref_measurements_report.get(key, 0)
                            llm_score = ref_metric_scores[key]
                            _monitor_score_difference(analyzer_score, llm_score, f"{display} (복원)")
                    
                    # LLM 점수 사용
                    orig_overall_score = llm_orig_overall_score
                    ref_overall_score = llm_ref_overall_score
            except Exception as e:
                log.warning(f"[점수 보정] 적용 실패, LLM 점수 사용: {e}")
                orig_overall_score = llm_orig_overall_score
                ref_overall_score = llm_ref_overall_score
            
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

            ref_report = SkinLLMReport(
                overall_score=ref_overall_score,
                perceived_age=ref_perceived_age,
                metric_opinions=ref_metric_opinions,
                overall_opinion=ref_overall_opinion,
                recommendation=recommendation,
                raw_response=response_text,
                scores_adjusted=False,  # 듀얼 모드에서는 점수 조정 미사용
                matched_products=matched_products,  # DB 매칭 제품
            )
            
            return orig_report, ref_report
            
        except json.JSONDecodeError as e:
            log.error(f"[LLM] JSON 파싱 실패: {e}")
            raise ValueError(f"LLM 응답 JSON 파싱 실패: {e}")

