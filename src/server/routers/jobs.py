"""
routers/jobs.py — 분석 Job 생성·조회·아티팩트 다운로드

POST   /v1/analysis/jobs
GET    /v1/analysis/jobs/{job_id}
GET    /v1/analysis/jobs/{job_id}/result
GET    /v1/analysis/jobs/{job_id}/artifacts/{name}
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import shutil
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from src.server.deps import (
    MAX_UPLOAD_BYTES,
    ALLOWED_EXT,
    SERVER_URL,
    JOB_SEMAPHORE,
    JOB_SEMAPHORE_TIMEOUT_SEC,
    get_shared_executor,
    log,
    get_current_customer,
    require_current_customer,
    download_image_to,
    _safe_filename,
    job_dir,
    jobs_root,
    read_job_meta,
    write_job_meta,
    _utc_now_iso,
    increment_active_jobs,
    decrement_active_jobs,
    limiter,
    validate_customer_id_match,
    validate_path_within_directory,
    get_main_loop,
    is_ssrf_blocked_host,
    get_secret_key,
)
from src.cli.execution_history import ExecutionHistoryDB
from src.utils.config import get_db_path_from_env

router = APIRouter(prefix="/v1/analysis", tags=["jobs"])


# ── 내부 유틸 ─────────────────────────────────────────────────────────────

def _canonicalize_artifacts(job_id: str, image_stem: str, result: Dict[str, Any]) -> Dict[str, str]:
    """결과 파일들을 artifacts/ 로 정규화하고 URL 경로 맵 반환."""
    art_dir = job_dir(job_id) / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, str] = {}

    # 결과 JSON
    result_path = art_dir / "results.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    out["results.json"] = f"/v1/analysis/jobs/{job_id}/artifacts/results.json"

    # 복원·입력 이미지
    for key in ("restored_image", "input_image"):
        val = result.get(key)
        if val:
            src = Path(val)
            if src.exists():
                dst = art_dir / src.name
                shutil.copyfile(src, dst)
                out[key] = f"/v1/analysis/jobs/{job_id}/artifacts/{src.name}"

    out["image_stem"] = image_stem
    return out


async def _run_job(job_id: str) -> None:
    """파이프라인 순수 비동기 실행 — Semaphore 없음 (호출자 _run_job_sync 에서 획득)."""
    # Lazy import to avoid torch dependency at module import time
    from src.cli.skin_analysis_cli import run_analysis_pipeline_async
    from src.server.routers.websocket import report_progress

    try:
        increment_active_jobs()
        meta = read_job_meta(job_id)
        meta["status"] = "running"
        meta["started_at"] = _utc_now_iso()
        write_job_meta(job_id, meta)

        # 진행률 보고: 작업 시작
        await report_progress(job_id, "init", 0, "작업 시작 중...")

        base_url = meta.get("base_url") or SERVER_URL
        executor = get_shared_executor()
        
        # 보안: llm_api_key는 환경변수에서만 로드, 클라이언트 입력은 무시
        llm_api_key_from_env = os.environ.get("GEMINI_API_KEY")
        
        # 진행률 보고: 복원 단계 시작
        if meta.get("do_restore", True):
            await report_progress(job_id, "restore", 10, "이미지 복원 중...")
        
        await report_progress(job_id, "analysis", 30, "피부 분석 중...")
        
        result = await run_analysis_pipeline_async(
            input_image=Path(meta["input_image_path"]),
            output_dir=Path(meta["output_dir"]),
            do_restore=meta.get("do_restore", True),
            debug=meta.get("debug", False),
            include_base64=meta.get("include_base64", False),
            base_url=base_url,
            score_safety_net=meta.get("score_safety_net", True),
            llm_report=meta.get("llm_report", False),
            llm_api_key=llm_api_key_from_env,
            customer_id=meta.get("customer_id"),
            gender=meta.get("gender"),
            age=meta.get("age"),
            race=meta.get("race"),
            region=meta.get("region"),
            lateral_images=meta.get("lateral_images"),
            use_multi_view_analysis=meta.get("use_multi_view_analysis", True),
            executor=executor,
            input_json=meta.get("input_json"),
        )

        # 진행률 보고: 결과 처리
        await report_progress(job_id, "processing", 80, "결과 처리 중...")

        if "input_image" in result:
            result["input_image_url"] = (
                f"/analysis/jobs/{job_id}/artifacts/{Path(result['input_image']).name}"
            )
        if "restored_image" in result:
            result["restored_image_url"] = (
                f"/analysis/jobs/{job_id}/artifacts/{Path(result['restored_image']).name}"
            )

        artifacts = _canonicalize_artifacts(job_id, Path(meta["input_image_path"]).stem, result)

        if "error" not in result:
            try:
                from src.db.skin_analysis_db import SkinAnalysisDB
                _db = SkinAnalysisDB(db_path=str(Path(meta["output_dir"]) / "skin_analysis.db"))
                _db.save_analysis(
                    original_path=meta.get("input_image_path", ""),
                    restored_path=result.get("restored_image", ""),
                    json_result=result,
                    customer_id=meta.get("customer_id"),
                    input_json=meta.get("input_json"),
                )
                
                # 분석 추이 기록
                customer_id = meta.get("customer_id")
                if customer_id:
                    overall_score_original = result.get("overall_score_original")
                    overall_score_restored = result.get("overall_score_restored")
                    measurement_scores = result.get("skin_types", {})
                    
                    # 분석 ID 조회 (가장 최근 분석)
                    analyses = _db.get_analyses(customer_id=customer_id, limit=1)
                    if analyses:
                        analysis_id = analyses[0]["id"]
                        _db.record_analysis_trend(
                            customer_id=customer_id,
                            analysis_id=analysis_id,
                            overall_score_original=overall_score_original or 0,
                            overall_score_restored=overall_score_restored or 0,
                            measurement_scores=measurement_scores,
                        )
            except Exception as db_err:
                log.warning("DB 저장 실패: %s", db_err)

        meta["status"]         = "succeeded" if "error" not in result else "failed"
        meta["finished_at"]    = _utc_now_iso()
        meta["error"]          = result.get("error")
        meta["artifacts"]      = artifacts
        meta["artifacts_local"] = artifacts
        write_job_meta(job_id, meta)

        # 진행률 보고: 완료
        await report_progress(job_id, "complete", 100, "작업 완료")

        # 콜백 URL 호출 (연동 기능)
        callback_url = meta.get("callback_url")
        if callback_url and meta["status"] == "succeeded":
            try:
                # [FIX P1] SSRF 검증
                parsed = urlparse(callback_url)
                if is_ssrf_blocked_host(parsed.hostname):
                    log.warning("콜백 URL 차단 (SSRF): %s", callback_url)
                    raise ValueError("Blocked callback URL")
                
                import httpx
                callback_payload = {
                    "job_id": job_id,
                    "status": meta["status"],
                    "external_reference_id": meta.get("external_reference_id"),
                    "result": {
                        "overall_score_original": result.get("overall_score_original"),
                        "overall_score_restored": result.get("overall_score_restored"),
                        "skin_types": result.get("skin_types"),
                    },
                    "finished_at": meta["finished_at"],
                }
                
                # [FIX P1] HMAC 서명 추가
                payload_str = json.dumps(callback_payload, sort_keys=True)
                signature = hmac.new(
                    get_secret_key().encode(),
                    payload_str.encode(),
                    hashlib.sha256
                ).hexdigest()
                
                headers = {"X-Webhook-Signature": f"sha256={signature}"}
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(callback_url, json=callback_payload, headers=headers)
                log.info("콜백 URL 호출 성공: %s", callback_url)
            except Exception as callback_err:
                log.warning("콜백 URL 호출 실패: %s", callback_err)

    except Exception as e:
        meta = meta if isinstance(meta, dict) else {}
        meta["status"]      = "failed"
        meta["finished_at"] = _utc_now_iso()
        meta["error"]       = str(e)
        meta["traceback"]   = traceback.format_exc()
        write_job_meta(job_id, meta)
        
        # 진행률 보고: 에러
        from src.server.routers.websocket import manager
        await manager.send_error(job_id, str(e))
    finally:
        decrement_active_jobs()


def _run_job_sync(job_id: str) -> None:
    """threading.Semaphore 획득 후 _run_job 실행.

    ThreadPoolExecutor 워커 스레드에서 호출된다.
    Semaphore.acquire(timeout=JOB_SEMAPHORE_TIMEOUT_SEC) — 타임아웃 시 job failed 처리.
    
    [FIX 2026-05-24] asyncio.run() 대신 asyncio.run_coroutine_threadsafe() 사용하여
    메인 이벤트 루프의 WebSocket 연결에 접근 가능하도록 수정.
    """
    acquired = JOB_SEMAPHORE.acquire(timeout=JOB_SEMAPHORE_TIMEOUT_SEC)
    if not acquired:
        log.error("[Job %s] Semaphore 획득 타임아웃 (%d초): 서버 부하 초과", job_id, JOB_SEMAPHORE_TIMEOUT_SEC)
        try:
            meta = read_job_meta(job_id)
            meta["status"]      = "failed"
            meta["error"]       = "대기 타임아웃: 서버 동시 처리 한계 초과 (5분 대기 후 실패)"
            meta["finished_at"] = _utc_now_iso()
            write_job_meta(job_id, meta)
        except Exception as e:
            log.warning(f"Failed to write job meta: {e}", exc_info=True)
        return
    try:
        # 메인 이벤트 루프 가져오기 (deps.py에서 관리)
        main_loop = get_main_loop()
        if main_loop is None:
            log.error("[Job %s] 메인 이벤트 루프가 설정되지 않았습니다.", job_id)
            meta = read_job_meta(job_id)
            meta["status"]      = "failed"
            meta["error"]       = "서버 초기화 오류: 이벤트 루프 미설정"
            meta["finished_at"] = _utc_now_iso()
            write_job_meta(job_id, meta)
            return
        
        # asyncio.run() 대신 run_coroutine_threadsafe 사용
        future = asyncio.run_coroutine_threadsafe(_run_job(job_id), main_loop)
        # 완료 대기 (타임아웃 없음 - job 자체가 타임아웃 처리)
        future.result()
    finally:
        JOB_SEMAPHORE.release()


# ── 엔드포인트 ────────────────────────────────────────────────────────────

@router.post("/jobs", status_code=202, response_model=None)
@limiter.limit("3/minute")
async def create_job(
    request: Request,
    # ── 이미지 입력 ─────────────────────────────────────────────────────
    images:    List[UploadFile]      = File(default=[]),
    angles:    List[str]             = Form(default=[]),
    image:     Optional[UploadFile]  = File(None),
    image_url: Optional[str]         = Form(None),
    # ── 파이프라인 옵션 ──────────────────────────────────────────────────
    do_restore:      bool            = Form(True),
    include_base64:  bool            = Form(False),
    base_url:        str             = Form(SERVER_URL),
    score_safety_net: bool           = Form(True),
    llm_report:      bool            = Form(True),
    use_multi_view_analysis: bool    = Form(True),
    # llm_api_key: 보안상 클라이언트 입력을 받지 않음, 환경변수 GEMINI_API_KEY 사용
    # llm_api_key:     Optional[str]   = Form(None),
    customer_id:     Optional[str]   = Form(None),
    gender:          Optional[str]   = Form(None),
    age:             Optional[int]   = Form(None),
    race:            Optional[str]   = Form(None),
    region:          Optional[str]   = Form(None),
    debug:           bool            = Form(False),
    # ── 설문·메타 ────────────────────────────────────────────────────────
    survey:      Optional[str]       = Form(None),
    client_meta: Optional[str]       = Form(None),
    # ── 연동 옵션 ────────────────────────────────────────────────────────
    callback_url: Optional[str]      = Form(None),
    external_reference_id: Optional[str] = Form(None),
    # ── 인증 (P0: 미인증 GPU 남용 방지) ─────────────────────────────────
    # [FIX 2026-05-24] Optional 제거 - 인증 필수화
    current_customer: Dict[str, Any] = Depends(require_current_customer),
) -> Dict[str, Any]:
    """분석 Job 생성.

    이미지 입력 규칙:
    - 다중(권장): ``images[]`` 1~3장 + ``angles[]`` 동일 수
      유효 각도: ``front`` / ``left45`` / ``right45``
    - 단일(레거시): ``image`` 파일 또는 ``image_url``
    두 방식 동시 사용 불가.
    """
    job_id  = str(uuid.uuid4())
    jdir    = job_dir(job_id)
    jdir.mkdir(parents=True, exist_ok=True)
    output_dir = jdir / "output"

    # ── 입력 방식 결정 ────────────────────────────────────────────────
    has_multi  = len(images) > 0
    has_single = image is not None
    has_url    = bool(image_url)

    if not (has_multi or has_single or has_url):
        raise HTTPException(
            status_code=400,
            detail="images[], image, image_url 중 하나를 반드시 제공해야 합니다.",
        )
    if sum([has_multi, has_single, has_url]) > 1:
        raise HTTPException(
            status_code=400,
            detail="images[], image, image_url 은 동시에 사용할 수 없습니다.",
        )

    # ── 다중 이미지 ──────────────────────────────────────────────────
    lateral_image_paths: List[Dict[str, str]] = []
    front_path: Optional[Path] = None

    if has_multi:
        _default_angles = ["front", "left45", "right45"]
        resolved_angles = [
            angles[i] if i < len(angles) else (_default_angles[i] if i < 3 else f"extra_{i}")
            for i, _ in enumerate(images)
        ]
        bad = [a for a in resolved_angles if a not in {"front", "left45", "right45"}]
        if bad:
            raise HTTPException(
                status_code=400,
                detail=f"유효하지 않은 angles[] 값: {bad}. 허용값: front, left45, right45",
            )
        for upload_file, angle in zip(images, resolved_angles):
            original_fname = upload_file.filename or f"{angle}.jpg"
            # 파일 확장자 검증 (원본 파일명 확인)
            file_ext = Path(original_fname).suffix.lower()
            if file_ext not in ALLOWED_EXT:
                raise HTTPException(
                    status_code=400,
                    detail=f"허용되지 않은 파일 확장자: {file_ext}. 허용 확장자: {', '.join(ALLOWED_EXT)}",
                )
            fname     = _safe_filename(original_fname)
            save_path = jdir / fname
            # 경로 검증 (2026-05-24): Path.is_relative_to() 사용
            validate_path_within_directory(save_path, jdir)
            data      = await upload_file.read()
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"파일 크기 초과: {upload_file.filename} ({len(data)//1024//1024}MB > {MAX_UPLOAD_BYTES//1024//1024}MB)",
                )
            save_path.write_bytes(data)
            lateral_image_paths.append({"angle": angle, "path": str(save_path)})
            if angle == "front" and front_path is None:
                front_path = save_path
        if front_path is None and lateral_image_paths:
            front_path = Path(lateral_image_paths[0]["path"])
        input_path = front_path  # type: ignore[assignment]
        filename   = input_path.name  # type: ignore[union-attr]

    # ── 단일 이미지 (레거시) ─────────────────────────────────────────
    elif has_single:
        original_fname = image.filename or "upload.jpg"  # type: ignore[union-attr]
        # 파일 확장자 검증 (원본 파일명 확인)
        file_ext = Path(original_fname).suffix.lower()
        if file_ext not in ALLOWED_EXT:
            raise HTTPException(
                status_code=400,
                detail=f"허용되지 않은 파일 확장자: {file_ext}. 허용 확장자: {', '.join(ALLOWED_EXT)}",
            )
        filename   = _safe_filename(original_fname)
        input_path = jdir / filename
        # 경로 검증 (2026-05-24): Path.is_relative_to() 사용
        validate_path_within_directory(input_path, jdir)
        data       = await image.read()  # type: ignore[union-attr]
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"파일 크기 초과: {image.filename} ({len(data)//1024//1024}MB > {MAX_UPLOAD_BYTES//1024//1024}MB)",  # type: ignore[union-attr]
            )
        input_path.write_bytes(data)
        lateral_image_paths = [{"angle": "front", "path": str(input_path)}]

    # ── URL (레거시) ─────────────────────────────────────────────────
    else:
        parsed   = urlparse(str(image_url))
        url_name = os.path.basename(parsed.path) if parsed.path else ""
        filename   = _safe_filename(url_name or "download.jpg")
        input_path = jdir / filename
        # 경로 검증 (2026-05-24): Path.is_relative_to() 사용
        validate_path_within_directory(input_path, jdir)
        try:
            download_image_to(str(image_url), input_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to download image_url: {e}")
        lateral_image_paths = [{"angle": "front", "path": str(input_path)}]

    # ── 설문·메타 파싱 ────────────────────────────────────────────────
    input_json: Dict[str, Any] = {}
    if survey:
        try:
            input_json["survey"] = json.loads(survey)
        except json.JSONDecodeError:
            pass
    if client_meta:
        try:
            input_json["client_meta"] = json.loads(client_meta)
        except json.JSONDecodeError:
            pass

    # ── customer_id 검증 (보안: JWT의 customer_id와 일치 확인) ─────────
    if customer_id and current_customer:
        validate_customer_id_match(current_customer, str(customer_id))

    # ── Job 메타 저장 ─────────────────────────────────────────────────
    meta: Dict[str, Any] = {
        "job_id":           job_id,
        "status":           "queued",
        "created_at":       _utc_now_iso(),
        "started_at":       None,
        "finished_at":      None,
        "do_restore":       bool(do_restore),
        "include_base64":   bool(include_base64),
        "base_url":         str(base_url),
        "score_safety_net": bool(score_safety_net),
        "llm_report":       bool(llm_report),
        "use_multi_view_analysis": bool(use_multi_view_analysis),
        "llm_api_key":      None,  # 보안: 환경변수에서만 로드, 저장하지 않음
        "customer_id":      str(customer_id) if customer_id else None,
        "gender":           str(gender) if gender else None,
        "age":              int(age) if age else None,
        "race":             str(race) if race else None,
        "region":           str(region) if region else None,
        "debug":            bool(debug),
        "input_image_name": filename,
        "input_image_path": str(input_path),
        "input_image_url":  str(image_url) if image_url else None,
        "lateral_images":   lateral_image_paths,
        "output_dir":       str(output_dir),
        "input_json":       input_json or None,
        "error":            None,
        "artifacts":        {},
        "callback_url":     callback_url,
        "external_reference_id": external_reference_id,
    }
    write_job_meta(job_id, meta)

    # [FIX P0] _executor.submit → ThreadPoolExecutor 워커 풀 내에서 실행
    get_shared_executor().submit(_run_job_sync, job_id)

    return {"job_id": job_id, "status": meta["status"], "created_at": meta["created_at"]}


@router.get("/jobs/{job_id}", response_model=None)
def get_job(job_id: str, current_customer: Dict[str, Any] = Depends(get_current_customer)) -> Dict[str, Any]:
    """Job 상태 조회."""
    try:
        meta = read_job_meta(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    
    # [FIX P0] 소유권 검증
    validate_customer_id_match(current_customer, meta.get("customer_id"))
    
    return {
        "job_id":      meta.get("job_id"),
        "status":      meta.get("status"),
        "created_at":  meta.get("created_at"),
        "started_at":  meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "error":       meta.get("error"),
        "artifacts":   meta.get("artifacts") or {},
    }


@router.get("/jobs/{job_id}/result", response_model=None)
def get_job_result(job_id: str, current_customer: Dict[str, Any] = Depends(get_current_customer)) -> Dict[str, Any]:
    """완료된 Job 의 분석 결과 반환."""
    try:
        meta = read_job_meta(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    
    # [FIX P0] 소유권 검증
    validate_customer_id_match(current_customer, meta.get("customer_id"))

    if meta.get("status") not in ("succeeded", "failed"):
        raise HTTPException(status_code=409, detail="job not finished")

    artifacts_local = meta.get("artifacts_local") or {}
    results_local   = artifacts_local.get("results.json")
    analysis_payload: Dict[str, Any] = {}
    if isinstance(results_local, str) and results_local:
        p = Path(results_local)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    analysis_payload = json.load(f)
            except Exception as e:
                log.warning(f"Failed to load results.json: {e}", exc_info=True)

    return {
        "job_id":    meta.get("job_id"),
        "status":    meta.get("status"),
        "timestamp": meta.get("finished_at") or meta.get("started_at") or meta.get("created_at"),
        "analysis":  analysis_payload,
        "artifacts": meta.get("artifacts") or {},
        "error":     meta.get("error"),
    }


@router.get("/jobs/{job_id}/artifacts/{name}")
def download_artifact(job_id: str, name: str, current_customer: Dict[str, Any] = Depends(get_current_customer)):
    """아티팩트 파일 다운로드."""
    try:
        meta = read_job_meta(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    
    # [FIX P0] 소유권 검증
    validate_customer_id_match(current_customer, meta.get("customer_id"))

    artifacts_local = meta.get("artifacts_local") or {}
    local_path      = artifacts_local.get(name)
    if not isinstance(local_path, str) or not local_path:
        raise HTTPException(status_code=404, detail="artifact not found")

    p = Path(local_path).resolve()
    allowed_root = job_dir(job_id).resolve()

    # path traversal 방지 (2026-05-24): Path.is_relative_to() 사용
    validate_path_within_directory(p, allowed_root)

    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")

    media_type = None
    if name.lower().endswith(".json"):
        media_type = "application/json"
    elif name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        media_type = "image/*"

    return FileResponse(path=str(p), media_type=media_type, filename=name)


# ── 피부 타입 감지 관련 엔드포인트 ─────────────────────────────────────────────

@router.post("/jobs/{job_id}/confirm-skin-type", response_model=None)
async def confirm_skin_type(
    job_id: str,
    skin_types: List[str] = Form(...),
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """피부 타입 사용자 확인"""
    try:
        meta = read_job_meta(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    
    # [FIX P1] 고객 권한 확인 (인자 순서 교정)
    validate_customer_id_match(current_customer, meta.get("customer_id"))
    
    # 분석 결과 로드
    result_path = Path(job_dir(job_id)) / "artifacts" / "results.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="analysis result not found")
    
    with open(result_path, "r", encoding="utf-8") as f:
        analysis_result = json.load(f)
    
    # 피부 타입 검증 데이터 저장 (DB에 저장)
    try:
        from src.utils.config import get_db_path_from_env
        db = ExecutionHistoryDB(get_db_path_from_env())
        
        # 감사 로그 기록
        customer_id = current_customer.get("sub") if current_customer else None
        db.record_audit_log(
            actor_customer_id=customer_id,
            target_customer_id=customer_id,
            endpoint=f"/v1/analysis/jobs/{job_id}/confirm-skin-type",
            method="POST",
            user_role=current_customer.get("role", "unknown") if current_customer else "unknown",
            success=True,
        )
        
        # 피부 타입 검증 데이터를 분석 통계에 기록
        # 기존 score 정보가 있으면 업데이트
        original_score = analysis_result.get("original_overall_score")
        restored_score = analysis_result.get("restored_overall_score")
        
        if original_score is not None or restored_score is not None:
            db.record_analysis_stat(
                customer_id=customer_id,
                success=True,
                score_original=original_score,
                score_restored=restored_score,
                execution_time_sec=0.0,  # 피부 타입 확인은 실행 시간 없음
            )
        
        log.info(f"[피부 타입 확인] job_id={job_id}, customer_id={customer_id}, skin_types={skin_types}")
    except Exception as e:
        log.warning(f"[피부 타입 확인] DB 저장 실패: {e}")
        # DB 저장 실패해도 분석 결과 업데이트는 계속 진행
    
    # 분석 결과 업데이트
    if "skin_type_detection" in analysis_result:
        analysis_result["skin_type_detection"]["skin_types"] = skin_types
        analysis_result["skin_type_detection"]["skin_type_source"] = "manual"
    
    # 결과 파일 업데이트
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    return {
        "job_id": job_id,
        "confirmed_skin_types": skin_types,
        "previous_detected_types": analysis_result.get("skin_type_detection", {}).get("skin_types"),
        "skin_type_source": "manual"
    }


@router.post("/jobs/{job_id}/reclassify-skin-type", response_model=None)
async def reclassify_skin_type(
    job_id: str,
    force_reclassification: bool = Form(True),
    current_customer: Optional[Dict[str, Any]] = Depends(get_current_customer),
):
    """피부 타입 재감지"""
    try:
        meta = read_job_meta(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    
    # [FIX P1] 고객 권한 확인 (인자 순서 교정)
    validate_customer_id_match(current_customer, meta.get("customer_id"))
    
    # 분석 결과 로드
    result_path = Path(job_dir(job_id)) / "artifacts" / "results.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="analysis result not found")
    
    with open(result_path, "r", encoding="utf-8") as f:
        analysis_result = json.load(f)
    
    # 피부 타입 재감지
    from src.scoring.skin_scoring import detect_skin_type
    new_detection = detect_skin_type(analysis_result)
    
    # 분석 결과 업데이트
    analysis_result["skin_type_detection"] = {
        "skin_types": new_detection.skin_types,
        "primary_type": new_detection.primary_type,
        "secondary_type": new_detection.secondary_type,
        "confidence": new_detection.confidence,
        "all_scores": new_detection.all_scores,
        "features": new_detection.features,
        "zone_analysis": new_detection.zone_analysis
    }
    
    # 결과 파일 업데이트
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    return {
        "job_id": job_id,
        "new_skin_types": new_detection.skin_types,
        "previous_skin_types": analysis_result.get("skin_type_detection", {}).get("skin_types"),
        "confidence": new_detection.confidence
    }
