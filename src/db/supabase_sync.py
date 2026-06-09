"""
Supabase 동기화 모듈
====================
로컬 SQLite 저장과 동시에 Supabase Storage(이미지) 및
Supabase Database(분석 결과 JSON)에 동기화합니다.

설계 원칙
----------
- 로컬 저장이 항상 선행: Supabase 연동 실패가 로컬 저장을 막지 않음
- 비동기 옵션: sync_mode=False 이면 백그라운드 스레드로 업로드
- 멱등성: storage_path 를 기준으로 upsert → 재업로드 시 중복 방지
- 설정 주입: SupabaseConfig 또는 환경 변수(SUPABASE_URL / SUPABASE_KEY) 사용

Supabase 준비 사항
-------------------
1. Storage 버킷 생성:
       이름: skin-images   (Public 또는 Private 모두 가능)
       폴더 구조: skin-images/<customer_id 또는 "anonymous">/<job_id>/
           original.png
           restored.png

2. Database 테이블 생성 (SQL Editor에서 실행):

    CREATE TABLE IF NOT EXISTS skin_analyses (
        id              BIGSERIAL PRIMARY KEY,
        local_id        INTEGER,            -- 로컬 SQLite ID
        customer_id     TEXT,
        original_filename TEXT,
        storage_original  TEXT,             -- Storage 경로
        storage_restored  TEXT,             -- Storage 경로
        overall_score_original  FLOAT,
        overall_score_restored  FLOAT,
        json_result     JSONB NOT NULL,
        input_json      JSONB,              -- 스마트폰에서 보내온 입력 JSON (survey + client_meta)
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_sa_customer  ON skin_analyses(customer_id);
    CREATE INDEX IF NOT EXISTS idx_sa_created   ON skin_analyses(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_sa_local_id  ON skin_analyses(local_id);

3. 환경 변수 또는 config.secrets.json 에 추가:
       SUPABASE_URL=https://<project>.supabase.co
       SUPABASE_KEY=<service_role 또는 anon key>

사용 예시
----------
    from src.db.supabase_sync import SupabaseSync, SupabaseConfig

    cfg   = SupabaseConfig.from_env()          # 환경 변수로 자동 로드
    syncer = SupabaseSync(cfg)

    syncer.sync(
        local_id        = sqlite_id,
        original_path   = "/path/to/original.png",
        restored_path   = "/path/to/restored.png",
        json_result     = result_dict,
        customer_id     = "C001",
        sync_mode       = False,               # 비동기 (백그라운드)
    )
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ── Supabase SDK import (선택적) ─────────────────────────────────────────────
try:
    from supabase import create_client, Client as SupabaseClient
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False
    SupabaseClient = Any  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SupabaseConfig:
    """Supabase 연결 설정.

    Parameters
    ----------
    url:
        Supabase 프로젝트 URL.
        예) https://abcdefgh.supabase.co
    key:
        service_role 키 또는 anon 키.
        이미지 업로드를 위해 service_role 키 권장.
    bucket:
        Storage 버킷 이름. 기본값 ``"skin-images"``.
    table:
        Database 테이블 이름. 기본값 ``"skin_analyses"``.
    enabled:
        False 이면 sync() 호출 자체를 무시 (환경별 on/off 용).
    timeout_sec:
        단일 업로드 작업의 최대 대기 시간(초). 기본값 30.
    """
    url:         str  = ""
    key:         str  = ""
    bucket:      str  = "skin-images"
    table:       str  = "skin_analyses"
    enabled:     bool = True
    timeout_sec: int  = 30

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        """환경 변수에서 설정을 읽어 인스턴스 생성.

        읽는 환경 변수:
            SUPABASE_URL   - 필수
            SUPABASE_KEY   - 필수
            SUPABASE_BUCKET - 선택 (기본: skin-images)
            SUPABASE_TABLE  - 선택 (기본: skin_analyses)
            SUPABASE_ENABLED - 선택 (기본: true)
        """
        return cls(
            url     = os.getenv("SUPABASE_URL", ""),
            key     = os.getenv("SUPABASE_KEY", ""),
            bucket  = os.getenv("SUPABASE_BUCKET", "skin-images"),
            table   = os.getenv("SUPABASE_TABLE", "skin_analyses"),
            enabled = os.getenv("SUPABASE_ENABLED", "true").lower() != "false",
        )
    
    @classmethod
    def from_config(cls, config_path: str = "config/config.json") -> "SupabaseConfig":
        """config.json에서 설정을 읽어 인스턴스 생성.

        환경 변수가 있으면 환경 변수를 우선 사용합니다.

        Parameters
        ----------
        config_path:
            config.json 파일 경로.
        """
        import json
        from pathlib import Path
        
        # 환경 변수 우선
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        
        # config.json에서 읽기
        cfg_file = Path(config_path)
        if cfg_file.exists() and not url:
            with open(cfg_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                database_cfg = config.get("database", {})
                supabase_cfg = database_cfg.get("supabase", {})
                url = supabase_cfg.get("url") or url
                key = supabase_cfg.get("key") or key
                bucket = supabase_cfg.get("bucket", "skin-images")
                enabled = supabase_cfg.get("enabled", True)
        else:
            bucket = "skin-images"
            enabled = True
        
        return cls(
            url     = url,
            key     = key,
            bucket  = bucket,
            table   = "skin_analyses",
            enabled = enabled,
        )

    @classmethod
    def from_secrets_json(cls, path: str = "config.secrets.json") -> "SupabaseConfig":
        """config.secrets.json 의 ``supabase`` 섹션에서 설정을 읽어 인스턴스 생성.

        JSON 구조 예시::

            {
                "supabase": {
                    "url": "https://xxxx.supabase.co",
                    "key": "service_role_key_here",
                    "bucket": "skin-images",
                    "table": "skin_analyses",
                    "enabled": true
                }
            }
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            sec = data.get("supabase", {})
            return cls(
                url     = sec.get("url", ""),
                key     = sec.get("key", ""),
                bucket  = sec.get("bucket", "skin-images"),
                table   = sec.get("table", "skin_analyses"),
                enabled = bool(sec.get("enabled", True)),
            )
        except FileNotFoundError:
            log.debug("[Supabase] config.secrets.json 없음 - 환경 변수로 폴백")
            return cls.from_env()
        except Exception as e:
            log.warning("[Supabase] config.secrets.json 읽기 실패: %s", e)
            return cls.from_env()

    def is_valid(self) -> bool:
        """URL과 KEY 가 모두 설정돼 있으면 True."""
        return bool(self.url and self.key)


# ─────────────────────────────────────────────────────────────────────────────
# 동기화 클래스
# ─────────────────────────────────────────────────────────────────────────────

class SupabaseSync:
    """로컬 분석 결과를 Supabase 에 동기화하는 클래스.

    Parameters
    ----------
    config:
        SupabaseConfig 인스턴스. None 이면 config.json → config.secrets.json → 환경 변수 순으로 자동 로드.
    """

    def __init__(self, config: Optional[SupabaseConfig] = None) -> None:
        if config is None:
            # config.json → config.secrets.json → 환경 변수 순으로 로드
            config = SupabaseConfig.from_config()
            if not config.is_valid():
                config = SupabaseConfig.from_secrets_json()
        self._cfg = config
        self._client: Optional[SupabaseClient] = None
        self._lock   = threading.Lock()
        self._init_client()

    # ── 공개 API ────────────────────────────────────────────────────────────

    def sync(
        self,
        local_id:      int,
        original_path: str,
        restored_path: str,
        json_result:   Dict[str, Any],
        customer_id:   Optional[str] = None,
        sync_mode:     bool          = False,
        input_json:    Optional[Dict[str, Any]] = None,
    ) -> None:
        """Supabase 에 이미지 및 JSON 을 저장.

        Parameters
        ----------
        local_id:
            로컬 SQLite 에서 발급받은 analyses.id.
        original_path:
            원본 이미지 파일 경로.
        restored_path:
            복원 이미지 파일 경로.
        json_result:
            분석 결과 딕셔너리.
        customer_id:
            고객 식별자 (선택).
        sync_mode:
            True  → 현재 스레드에서 동기 실행 (완료 대기).
            False → 백그라운드 daemon 스레드로 비동기 실행 (기본).
        input_json:
            스마트폰에서 보내온 입력 JSON (survey + client_meta).
        """
        if not self._cfg.enabled:
            return
        if not self._cfg.is_valid():
            log.warning("[Supabase] URL/KEY 미설정 - Supabase 동기화 건너뜀")
            return
        if self._client is None:
            log.warning("[Supabase] 클라이언트 미초기화 - Supabase 동기화 건너뜀")
            return

        if sync_mode:
            self._do_sync(local_id, original_path, restored_path, json_result, customer_id, input_json)
        else:
            t = threading.Thread(
                target=self._do_sync,
                args=(local_id, original_path, restored_path, json_result, customer_id, input_json),
                daemon=True,
                name=f"supabase-sync-{local_id}",
            )
            t.start()
            log.debug("[Supabase] 백그라운드 동기화 시작: local_id=%d", local_id)

    def is_available(self) -> bool:
        """Supabase 연결이 가용 상태인지 반환."""
        return self._client is not None and self._cfg.is_valid()

    # ── 내부 구현 ────────────────────────────────────────────────────────────

    def _init_client(self) -> None:
        """Supabase 클라이언트 초기화."""
        if not _SUPABASE_OK:
            log.warning(
                "[Supabase] supabase-py 패키지 없음. "
                "설치: pip install supabase"
            )
            return
        if not self._cfg.is_valid():
            return
        try:
            self._client = create_client(self._cfg.url, self._cfg.key)
            log.info("[Supabase] 클라이언트 초기화 완료: %s", self._cfg.url)
        except Exception as e:
            log.error("[Supabase] 클라이언트 초기화 실패: %s", e)
            self._client = None

    def _do_sync(
        self,
        local_id:      int,
        original_path: str,
        restored_path: str,
        json_result:   Dict[str, Any],
        customer_id:   Optional[str],
        input_json:    Optional[Dict[str, Any]] = None,
    ) -> None:
        """실제 업로드 작업 (Storage + Database)."""
        try:
            folder = self._make_folder(customer_id, local_id)

            # ── 1. 이미지 업로드 ─────────────────────────────────────────
            path_orig = self._upload_image(original_path, f"{folder}/original.png")
            path_rest = self._upload_image(restored_path, f"{folder}/restored.png")

            # ── 2. 분석 점수 추출 ────────────────────────────────────────
            score_orig, score_rest = self._extract_scores(json_result)
            original_filename = Path(original_path).stem if original_path else ""

            # ── 3. DB upsert ─────────────────────────────────────────────
            self._upsert_row(
                local_id          = local_id,
                customer_id       = customer_id,
                original_filename = original_filename,
                storage_original  = path_orig,
                storage_restored  = path_rest,
                score_orig        = score_orig,
                score_rest        = score_rest,
                json_result       = json_result,
                input_json        = input_json,
            )

            log.info(
                "[Supabase] 동기화 완료: local_id=%d, folder=%s",
                local_id, folder,
            )

        except Exception as e:
            log.error("[Supabase] 동기화 실패: local_id=%d, error=%s", local_id, e, exc_info=True)

    def _make_folder(self, customer_id: Optional[str], local_id: int) -> str:
        """Storage 저장 폴더 경로 생성.

        구조: <customer_id 또는 "anonymous">/<날짜>_<local_id>
        예)   C001/20260515_42
        """
        owner     = (customer_id or "anonymous").replace("/", "_")
        date_str  = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{owner}/{date_str}_{local_id}"

    def _upload_image(self, local_path: str, storage_path: str, max_retry: int = 3) -> str:
        """이미지를 Supabase Storage 에 업로드 (재시도 포함).

        Parameters
        ----------
        local_path:
            업로드할 파일의 로컬 경로.
        storage_path:
            버킷 내 저장 경로 (예: C001/20260515_42/original.png).
        max_retry:
            최대 재시도 횟수 (기본 3회).

        Returns
        -------
        str
            업로드된 Storage 경로 (성공) 또는 "" (실패/파일 없음).
        """
        if not local_path:
            return ""

        p = Path(local_path)
        if not p.exists():
            log.warning("[Supabase] 이미지 파일 없음: %s", local_path)
            return ""

        for attempt in range(1, max_retry + 1):
            try:
                with open(p, "rb") as f:
                    data = f.read()

                suffix  = p.suffix.lower()
                content = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

                # upsert=True: 동일 경로 재업로드 시 덮어쓰기
                self._client.storage.from_(self._cfg.bucket).upload(
                    path       = storage_path,
                    file       = data,
                    file_options = {"content-type": content, "upsert": "true"},
                )
                log.debug("[Supabase] 이미지 업로드: %s → %s", local_path, storage_path)
                return storage_path

            except Exception as e:
                wait = 2 ** attempt
                if attempt < max_retry:
                    log.warning("[Supabase] 업로드 실패 (시도 %d/%d): %s - %ds 후 재시도", attempt, max_retry, e, wait)
                    import time
                    time.sleep(wait)
                else:
                    log.error("[Supabase] 이미지 업로드 최종 실패: %s - %s", storage_path, e)
                    self._record_failed_upload(local_path, storage_path)
                    return ""

    def _record_failed_upload(self, local_path: str, storage_path: str) -> None:
        """재기동 시 재시도를 위한 실패 큐 로컬 파일 기록."""
        queue_file = Path("supabase_upload_queue.jsonl")
        import json
        from datetime import datetime, timezone
        with open(queue_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "local": local_path,
                "storage": storage_path,
                "ts": datetime.now(timezone.utc).isoformat()
            }) + "\n")

    def _upsert_row(
        self,
        local_id:          int,
        customer_id:       Optional[str],
        original_filename: str,
        storage_original:  str,
        storage_restored:  str,
        score_orig:        float,
        score_rest:        float,
        json_result:       Dict[str, Any],
        input_json:        Optional[Dict[str, Any]] = None,
    ) -> None:
        """skin_analyses 테이블에 행을 upsert.

        local_id 기준으로 중복 방지 (on_conflict=local_id).
        """
        row = {
            "local_id":               local_id,
            "customer_id":            customer_id,
            "original_filename":      original_filename,
            "storage_original":       storage_original,
            "storage_restored":       storage_restored,
            "overall_score_original": score_orig,
            "overall_score_restored": score_rest,
            "json_result":            json_result,
            "input_json":             input_json,
            "created_at":             datetime.now(timezone.utc).isoformat(),
        }

        (
            self._client.table(self._cfg.table)
            .upsert(row, on_conflict="local_id")
            .execute()
        )
        log.debug("[Supabase] DB upsert 완료: local_id=%d", local_id)

    @staticmethod
    def _extract_scores(json_result: Dict[str, Any]) -> tuple[float, float]:
        """분석 결과에서 종합 점수 추출.

        [REFACTOR P0-9] 중복 로직을 result_parser.py로 통합
        """
        from src.db.result_parser import extract_overall_scores
        return extract_overall_scores(json_result)


# ─────────────────────────────────────────────────────────────────────────────
# 싱글턴 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

_default_syncer: Optional[SupabaseSync] = None
_syncer_lock    = threading.Lock()


def get_syncer(config: Optional[SupabaseConfig] = None) -> SupabaseSync:
    """프로세스 전역 싱글턴 SupabaseSync 반환.

    Parameters
    ----------
    config:
        최초 호출 시에만 적용. 이후 호출은 캐시된 인스턴스 반환.
    """
    global _default_syncer
    with _syncer_lock:
        if _default_syncer is None:
            _default_syncer = SupabaseSync(config)
        return _default_syncer
