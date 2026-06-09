"""SkinLens 단일 분석 오케스트레이터 (표준 진입점).

[구조변경 #3] GUI/CLI/Engine/Server 가 제각기 분석 경로를 갖던 문제(특히 GUI 의
analyze_compare_triple 기반 자체 스코어링)를 없애기 위한 단일 진입점.

본 서비스는 검증된 `run_analysis_pipeline`(복원→다중뷰 분석 analyze_all_multi_v3→
안전장치→LLM→결과통합→DB기록)에 위임한다. 따라서:
  - CLI/Engine/Server: 이미 같은 함수를 쓰므로 동작 불변.
  - GUI: 이 서비스를 호출하도록 전환하면 '표준(canonical) 점수 경로'로 수렴
    (= analyze_compare_triple 기반 자체 경로 제거 → 점수 드리프트 해소).

구현 노트: 600여 LOC 본문을 즉시 이전하지 않고 '얇은 파사드'로 시작해 순환참조와
회귀 위험을 0으로 둔다. 추후 본문을 단계별로 서비스 내부 stage 로 이관 가능.
"""
from __future__ import annotations

import asyncio
import dataclasses
import functools
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# 주의: run_analysis_pipeline(_async) 는 메서드 내부에서 지연 import 한다.
# (cli 모듈이 본 서비스를 import 할 수 있으므로 모듈 로드 시 순환참조 방지)


@dataclass
class AnalysisRequest:
    """분석 요청 1건. run_analysis_pipeline 의 keyword 인자와 1:1 대응.

    GUI/CLI/Engine 가 제각기 인자를 풀어 넘기던 것을 한 객체로 수렴한다.
    """
    input_image: Path
    output_dir: Path
    do_restore: bool = True
    debug: bool = False
    include_base64: bool = False
    score_safety_net: bool = True
    llm_report: bool = True
    llm_api_key: Optional[str] = None
    llm_scores: bool = False
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_contact: Optional[str] = None
    customer_address: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    race: Optional[str] = None
    region: Optional[str] = None
    lateral_images: Optional[List[Dict[str, str]]] = None
    use_multi_view_analysis: bool = True
    input_json: Optional[Dict[str, Any]] = None
    # base_url 은 run_analysis_pipeline 의 기본값(SERVER_URL)을 그대로 쓰도록 미포함.
    base_url: Optional[str] = None

    def to_kwargs(self) -> Dict[str, Any]:
        """run_analysis_pipeline 호출용 kwargs (None 인 base_url 은 제외)."""
        d = dataclasses.asdict(self)
        if d.get("base_url") is None:
            d.pop("base_url", None)
        return d


class AnalysisService:
    """모든 모드가 공유하는 표준 분석 진입점.

    사용 예:
        svc = AnalysisService(llm_api_key=key)
        result = svc.run(image_path, out_dir, do_restore=True, llm_report=True)
        # 또는
        result = svc.run_request(AnalysisRequest(image_path, out_dir, ...))
        # 비동기(engine/server):
        result = await svc.run_async(image_path, out_dir, ...)
    """

    def __init__(self, *, llm_api_key: Optional[str] = None) -> None:
        # 생성자에서 키를 한 번만 주입하면 매 호출 시 반복 전달 불필요.
        self._llm_api_key = llm_api_key

    # ── 동기 ──────────────────────────────────────────────────────────────
    def run(self, input_image: Path, output_dir: Path, **kwargs: Any) -> Dict[str, Any]:
        """검증된 run_analysis_pipeline 에 위임."""
        from src.cli.skin_analysis_cli import run_analysis_pipeline
        if self._llm_api_key is not None:
            kwargs.setdefault("llm_api_key", self._llm_api_key)
        return run_analysis_pipeline(input_image, output_dir, **kwargs)

    def run_request(self, req: AnalysisRequest) -> Dict[str, Any]:
        kwargs = req.to_kwargs()
        input_image = kwargs.pop("input_image")
        output_dir = kwargs.pop("output_dir")
        return self.run(input_image, output_dir, **kwargs)

    # ── 비동기 (engine/server) ────────────────────────────────────────────
    async def run_async(
        self,
        input_image: Path,
        output_dir: Path,
        *,
        executor: Optional[ThreadPoolExecutor] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        from src.cli.skin_analysis_cli import run_analysis_pipeline_async
        if self._llm_api_key is not None:
            kwargs.setdefault("llm_api_key", self._llm_api_key)
        return await run_analysis_pipeline_async(
            input_image, output_dir, executor=executor, **kwargs
        )

    async def run_request_async(
        self,
        req: AnalysisRequest,
        *,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> Dict[str, Any]:
        kwargs = req.to_kwargs()
        input_image = kwargs.pop("input_image")
        output_dir = kwargs.pop("output_dir")
        return await self.run_async(input_image, output_dir, executor=executor, **kwargs)

    # ── GUI 호환 비교 분석 (옵션 B 어댑터) ─────────────────────────────────
    def run_compare(
        self,
        orig_image: Path,
        restored_image: Path,
        *,
        score_safety_net: bool = True,
    ):
        """GUI 의 '비교(compare_triple) 점수 경로'를 단일 진입점으로 캡슐화.

        GUI(skin_analysis_pipeline._cli_body)가 인라인으로 하던
        ``analyze_compare_triple(orig, restored, restored)`` + 선택적
        ``apply_score_safety_net`` 시퀀스를 **동일 함수·동일 순서·동일 폴백**으로
        재현한다. 따라서 GUI 가 이 메서드로 전환해도 점수가 바뀌지 않는다(중복만 제거).

        canonical 경로(run/run_async, analyze_all_multi_v3)와는 점수 의미가
        다르므로 별도 메서드로 분리한다. GUI 의 표시측 후처리(offset/filter)·LLM·
        파일 이동은 호출측(GUI)에 그대로 남긴다.

        Qt 비의존: src.skin.core.analyze_utils 의 analyze_compare_triple 사용
        (gui.analyzer_compare_gui 버전과 로직 동일) → engine/server 에서도 안전.

        Returns:
            (orig_result, restored_result, ref2_result) — GUI 의 (o, i1, i2) 와 동일 계약.
        """
        from src.skin.core.analyze_utils import analyze_compare_triple

        orig_path = Path(orig_image)
        restored_path = Path(restored_image)

        # GUI 와 동일: 기준1=기준2=복원 이미지
        o, i1_raw, i2 = analyze_compare_triple(orig_path, restored_path, restored_path)

        if score_safety_net:
            try:
                from src.utils.utils import apply_score_safety_net
                o, i1, i2 = apply_score_safety_net(
                    orig_path,
                    restored_path,
                    pre_analyzed_original=o,
                    pre_analyzed_restored=i1_raw,
                )
                return o, i1, i2
            except Exception as e:  # GUI 와 동일: 실패 시 raw 점수로 폴백
                import logging
                logging.getLogger(__name__).warning(f"[run_compare] 점수 안전장치 실패: {e}")
                return o, i1_raw, i2

        return o, i1_raw, i2


__all__ = ["AnalysisService", "AnalysisRequest"]
