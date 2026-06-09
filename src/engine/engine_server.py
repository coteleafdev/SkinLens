#!/usr/bin/env python3
"""
Engine Server - 피부 분석 전용 서버

웹서버로부터 분석 요청을 받아 처리하고 결과를 반환합니다.
GPU 리소스를 독립적으로 사용하며, 웹서버와 분리됩니다.

엔드포인트:
- POST /v1/engine/analysis/jobs - 분석 작업 생성
- GET  /v1/engine/analysis/jobs/{job_id} - 작업 상태 조회
- GET  /v1/engine/health - 헬스 체크
"""

import asyncio
import hashlib
import hmac
import logging
import os
import shutil
import sqlite3
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Depends, File, Form, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.utils.config import load_config
from src.utils.utils import setup_logging

# 중앙 집중식 로깅 설정 (import 전에 호출하여 올바른 로그 파일명 설정)
setup_logging(mode="engine")
log = logging.getLogger(__name__)

from src.pipeline.analysis_service import AnalysisService

# ── 내부 유틸 ─────────────────────────────────────────────────────────────

def _get_secret_key() -> str:
    """시크릿 키 가져오기.

    [구조변경] 공유 secrets 모듈로 위임 → server(deps.get_secret_key) 와 동일
    소스/정책 사용. JWT_SECRET_KEY 미설정 시: 프로덕션은 fail-fast, 개발은 경고+기본값.
    (이전: server 기본값 'your-...' vs engine 기본값 'default-...' 불일치로 401)
    """
    from src.common.secrets import get_hmac_secret
    return get_hmac_secret("JWT_SECRET_KEY")

def _utc_now_iso() -> str:
    """현재 UTC 시간을 ISO 형식으로 반환."""
    return datetime.now(timezone.utc).isoformat()

def _safe_filename(filename: str) -> str:
    """안전한 파일명 생성."""
    import re
    # 확장자 유지, 파일명에서 위험한 문자 제거
    name = re.sub(r'[^\w\-.]', '_', filename)
    return name

def validate_path_within_directory(path: Path, allowed_root: Path) -> None:
    """경로가 허용된 디렉토리 내에 있는지 검증."""
    try:
        path.resolve().relative_to(allowed_root.resolve())
    except ValueError:
        raise ValueError(f"Path {path} is not within allowed root {allowed_root}")

def job_dir(job_id: str) -> Path:
    """Job 디렉토리 경로 반환."""
    jobs_root = Path("jobs")
    jobs_root.mkdir(parents=True, exist_ok=True)
    return jobs_root / job_id

def write_job_meta(job_id: str, meta: Dict[str, Any]) -> None:
    """Job 메타데이터 저장."""
    import json
    meta_path = job_dir(job_id) / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def read_job_meta(job_id: str) -> Dict[str, Any]:
    """Job 메타데이터 읽기."""
    import json
    meta_path = job_dir(job_id) / "meta.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)

# ── 동시성 제어 (GPU 보호) ────────────────────────────────────────────────
# [구조변경] GPU 를 실제로 사용하는 계층은 engine 이므로, 동시 실행 한도는
# 여기(engine)에 둔다. (이전: 위임만 하는 server 에만 JOB_SEMAPHORE 존재,
# engine 은 asyncio.create_task 로 무제한 → 동시 요청 시 GPU OOM 위험)
ENGINE_MAX_CONCURRENCY = max(1, int(os.environ.get("ENGINE_MAX_CONCURRENCY", "2")))
_engine_job_sem: Optional[asyncio.Semaphore] = None

def _get_engine_semaphore() -> asyncio.Semaphore:
    """실행 중인 이벤트 루프에 바인딩된 세마포어를 lazy 생성/반환."""
    global _engine_job_sem
    if _engine_job_sem is None:
        _engine_job_sem = asyncio.Semaphore(ENGINE_MAX_CONCURRENCY)
    return _engine_job_sem

# FastAPI 앱 생성
app = FastAPI(
    title="SkinLens Engine Server",
    description="피부 분석 전용 엔진 서버",
    version="1.0.0",
)

# CORS 미들웨어
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    """분석 요청 모델"""
    customer_id: Optional[str] = None
    customer_name: str
    customer_contact: str
    customer_address: str
    gender: Optional[str] = None
    age: Optional[int] = None
    race: Optional[str] = None
    region: Optional[str] = None
    do_restore: bool = True
    include_base64: bool = False
    score_safety_net: bool = True
    llm_report: bool = True
    use_multi_view_analysis: bool = True
    debug: bool = False
    survey: Optional[str] = None
    client_meta: Optional[str] = None
    lateral_images: Optional[list] = None
    input_json: Optional[Dict[str, Any]] = None

class JobStatusResponse(BaseModel):
    """작업 상태 응답 모델"""
    job_id: str
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

# ── 내부 유틸 ─────────────────────────────────────────────────────────────

def _canonicalize_artifacts(job_id: str, image_stem: str, result: Dict[str, Any]) -> Dict[str, str]:
    """결과 파일들을 artifacts/ 로 정규화하고 URL 경로 맵 반환."""
    art_dir = job_dir(job_id) / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, str] = {}

    # 결과 JSON
    import json
    result_path = art_dir / "results.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    out["results.json"] = f"/v1/engine/analysis/jobs/{job_id}/artifacts/results.json"

    # 복원·입력 이미지
    for key in ("restored_image", "input_image"):
        val = result.get(key)
        if val:
            src = Path(val)
            if src.exists():
                dst = art_dir / src.name
                shutil.copyfile(src, dst)
                out[key] = f"/v1/engine/analysis/jobs/{job_id}/artifacts/{src.name}"

    out["image_stem"] = image_stem
    return out

async def _run_job(job_id: str) -> None:
    """파이프라인 비동기 실행.

    [구조변경] GPU 동시 실행 한도를 세마포어로 제한한다. 세마포어 대기 동안에는
    상태를 'queued' 로 유지하고, 슬롯 획득 후에야 'running' 으로 전환한다.
    """
    sem = _get_engine_semaphore()
    if sem.locked():
        log.info(f"[Engine] Job {job_id} 대기 중 (동시 실행 한도 {ENGINE_MAX_CONCURRENCY} 도달)")
    async with sem:
        try:
            meta = read_job_meta(job_id)
            meta["status"] = "running"
            meta["started_at"] = _utc_now_iso()
            write_job_meta(job_id, meta)

            log.info(f"[Engine] Job {job_id} started")

            # 환경변수에서 API 키 로드
            llm_api_key_from_env = os.environ.get("GEMINI_API_KEY")

            # 분석 파이프라인 실행
            # [구조변경 #3] 단일 진입점 AnalysisService 경유 (내부적으로 동일 함수에 위임 → 동작 불변)
            result = await AnalysisService().run_async(
                input_image=Path(meta["input_image_path"]),
                output_dir=Path(meta["output_dir"]),
                do_restore=meta.get("do_restore", True),
                debug=meta.get("debug", False),
                include_base64=meta.get("include_base64", False),
                base_url=meta.get("base_url", "http://localhost:8000"),
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
                executor=None,  # 엔진 서버는 기본 executor 사용
                input_json=meta.get("input_json"),
            )

            log.info(f"[Engine] Job {job_id} analysis completed")

            # 결과 처리
            if "input_image" in result:
                result["input_image_url"] = (
                    f"/v1/engine/analysis/jobs/{job_id}/artifacts/{Path(result['input_image']).name}"
                )
            if "restored_image" in result:
                result["restored_image_url"] = (
                    f"/v1/engine/analysis/jobs/{job_id}/artifacts/{Path(result['restored_image']).name}"
                )

            artifacts = _canonicalize_artifacts(job_id, Path(meta["input_image_path"]).stem, result)

            meta["status"] = "succeeded" if "error" not in result else "failed"
            meta["finished_at"] = _utc_now_iso()
            meta["error"] = result.get("error")
            meta["artifacts"] = artifacts
            meta["artifacts_local"] = artifacts
            meta["result"] = result
            write_job_meta(job_id, meta)

            log.info(f"[Engine] Job {job_id} finished with status: {meta['status']}")

        except Exception as e:
            log.error(f"[Engine] Job {job_id} failed: {e}", exc_info=True)
            meta = read_job_meta(job_id)
            meta["status"] = "failed"
            meta["finished_at"] = _utc_now_iso()
            meta["error"] = str(e)
            meta["traceback"] = traceback.format_exc()
            write_job_meta(job_id, meta)

# ── 엔드포인트 ────────────────────────────────────────────────────────────

@app.post("/v1/engine/analysis/jobs", status_code=202)
async def create_job(
    request: Request,
    analysis_request: str = Form(...),  # JSON string
    signature: str = Form(...),  # HMAC signature
    # [구조변경] 다중 이미지 multipart 수신 (권장)
    images: List[UploadFile] = File(default=[]),
    angles: List[str] = Form(default=[]),
    # 레거시 단일 이미지 (하위 호환)
    image: Optional[UploadFile] = File(None),
):
    """분석 작업 생성.

    웹서버로부터 분석 요청을 받아 처리합니다.
    HMAC 서명을 검증하여 요청의 무결성을 확인합니다.

    이미지 입력:
    - 다중(권장): ``images[]`` 1~3장 + ``angles[]`` (front/left45/right45)
    - 단일(레거시): ``image``
    [구조변경] 측면 이미지를 **실제 multipart 전송**으로 받아 engine 로컬에 저장한다.
    (이전: server 로컬 경로를 JSON 으로만 전달 → 호스트 분리 시 다중뷰 무력화)
    """
    # HMAC 서명 검증
    payload_str = analysis_request
    expected_signature = hmac.new(
        _get_secret_key().encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, f"sha256={expected_signature}"):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # 요청 파싱
    import json
    try:
        req_data = json.loads(analysis_request)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in analysis_request")
    
    # Pydantic 모델로 검증
    try:
        analysis_req = AnalysisRequest(**req_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")
    
    # Job 생성
    job_id = str(uuid.uuid4())
    jdir = job_dir(job_id)
    jdir.mkdir(parents=True, exist_ok=True)
    output_dir = jdir / "output"

    max_upload_bytes = 50 * 1024 * 1024  # 50MB

    async def _save_upload(upload: UploadFile, fallback_name: str) -> Path:
        fname = _safe_filename(upload.filename or fallback_name)
        save_path = jdir / fname
        validate_path_within_directory(save_path, jdir)
        blob = await upload.read()
        if len(blob) > max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"File too large: {fname}")
        save_path.write_bytes(blob)
        return save_path

    # ── 이미지 저장 + engine 로컬 경로로 lateral_images 재구성 ──────────────
    _VALID_ANGLES = {"front", "left45", "right45"}
    _DEFAULT_ANGLES = ["front", "left45", "right45"]
    lateral_images: List[Dict[str, str]] = []
    front_path: Optional[Path] = None

    if images:
        # angles[] 가 부족하면 기본 순서로 보충
        resolved_angles = [
            angles[i] if i < len(angles) else (_DEFAULT_ANGLES[i] if i < 3 else f"extra_{i}")
            for i in range(len(images))
        ]
        bad = [a for a in resolved_angles if a not in _VALID_ANGLES]
        if bad:
            raise HTTPException(
                status_code=400,
                detail=f"유효하지 않은 angles[] 값: {bad}. 허용값: front, left45, right45",
            )
        for upload, angle in zip(images, resolved_angles):
            saved = await _save_upload(upload, f"{angle}.jpg")
            lateral_images.append({"angle": angle, "path": str(saved)})
            if angle == "front" and front_path is None:
                front_path = saved
        if front_path is None and lateral_images:
            front_path = Path(lateral_images[0]["path"])
    elif image is not None:
        saved = await _save_upload(image, "upload.jpg")
        front_path = saved
        lateral_images = [{"angle": "front", "path": str(saved)}]
    else:
        raise HTTPException(
            status_code=400,
            detail="images[] 또는 image 중 하나를 반드시 제공해야 합니다.",
        )

    input_path = front_path
    filename = input_path.name

    # Job 메타 저장
    meta: Dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "do_restore": analysis_req.do_restore,
        "include_base64": analysis_req.include_base64,
        "base_url": "http://localhost:8000",  # 엔진 서버 기본 URL
        "score_safety_net": analysis_req.score_safety_net,
        "llm_report": analysis_req.llm_report,
        "use_multi_view_analysis": analysis_req.use_multi_view_analysis,
        "customer_id": analysis_req.customer_id,
        "customer_name": analysis_req.customer_name,
        "customer_contact": analysis_req.customer_contact,
        "customer_address": analysis_req.customer_address,
        "gender": analysis_req.gender,
        "age": analysis_req.age,
        "race": analysis_req.race,
        "region": analysis_req.region,
        "debug": analysis_req.debug,
        "input_image_name": filename,
        "input_image_path": str(input_path),
        # [구조변경] JSON 경로가 아니라 engine 로컬에 저장된 경로 사용
        "lateral_images": lateral_images,
        "output_dir": str(output_dir),
        "input_json": analysis_req.input_json,
        "error": None,
        "artifacts": {},
        "result": None,
    }
    write_job_meta(job_id, meta)
    
    # 비동기 작업 실행
    asyncio.create_task(_run_job(job_id))
    
    return {
        "job_id": job_id,
        "status": meta["status"],
        "created_at": meta["created_at"],
    }

@app.get("/v1/engine/analysis/jobs/{job_id}")
async def get_job(job_id: str):
    """작업 상태 조회."""
    try:
        meta = read_job_meta(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": meta.get("job_id"),
        "status": meta.get("status"),
        "created_at": meta.get("created_at"),
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "error": meta.get("error"),
        "result": meta.get("result"),
        "artifacts": meta.get("artifacts") or {},
    }

@app.get("/v1/engine/health")
async def health_check():
    """헬스 체크."""
    sem = _get_engine_semaphore()
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": _utc_now_iso(),
        "max_concurrency": ENGINE_MAX_CONCURRENCY,
        "available_slots": getattr(sem, "_value", None),
    }

# ── 메인 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    
    config = load_config()
    engine_config = config.get("engine_server", {})
    
    host = engine_config.get("host", "0.0.0.0")
    port = engine_config.get("port", 8001)
    
    log.info(f"Starting Engine Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
