"""
피부 분석 결과를 저장하는 SQLite 데이터베이스 모듈.

변경 이력
----------
- 2026-05-15: Supabase 동기화 통합
    save_analysis() 에서 로컬 SQLite 저장 성공 후
    SupabaseSync.sync() 를 자동 호출하여 동일 데이터를 Supabase 에도 저장.
    Supabase 연동 실패는 경고 로그만 남기고 로컬 저장에 영향 없음.
- 2026-05-15: WAL 모드 및 연결 재사용 추가
    PRAGMA journal_mode=WAL, synchronous=NORMAL 적용.
    인스턴스 레벨 연결 재사용으로 성능 향상.
"""
import logging
import sqlite3
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

log = logging.getLogger(__name__)

from src.utils.config import load_config as _load_config


class SkinAnalysisDB:
    """피부 분석 결과를 관리하는 SQLite DB 클래스"""

    def __init__(
        self,
        db_path: str = "skin_analysis.db",
        supabase_sync: Optional[bool] = None,
    ):
        """
        DB 초기화.

        Parameters
        ----------
        db_path:
            DB 파일 경로 (기본값: skin_analysis.db).
        supabase_sync:
            Supabase 동기화 여부. None이면 config.json의 supabase.enabled를 사용.
            기본값은 config.json의 supabase.enabled (기본 true).
        """
        # config.json에서 Supabase 설정 로드
        config = _load_config()
        database_config = config.get("database", {})
        supabase_config = database_config.get("supabase", {})
        
        # supabase_sync 인자가 None이면 config.json에서 읽기
        if supabase_sync is None:
            supabase_sync = supabase_config.get("enabled", True)
        
        self.db_path = db_path
        self._supabase_sync_enabled = supabase_sync
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_db()

        # Supabase syncer — 지연 초기화 (최초 save_analysis 호출 시)
        self._syncer = None

    # ── DB 초기화 ─────────────────────────────────────────────────────────────

    def _init_db(self):
        """DB 테이블 생성 및 인덱스 설정"""
        cursor = self._conn.cursor()

        # 스키마 버전 테이블 생성 (마이그레이션 관리용)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 현재 스키마 버전 확인
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0

        # analyses 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT,
                original_image_path TEXT NOT NULL,
                restored_image_path TEXT NOT NULL,
                json_result TEXT NOT NULL,
                input_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                original_filename TEXT,
                overall_score_original REAL,
                overall_score_restored REAL
            )
        """)

        # 마이그레이션: input_json 컬럼 추가 (버전 1)
        if current_version < 1:
            if not self._column_exists(cursor, "analyses", "input_json"):
                cursor.execute("ALTER TABLE analyses ADD COLUMN input_json TEXT")
                cursor.execute("INSERT INTO schema_version (version) VALUES (1)")
                self._conn.commit()

        # 마이그레이션: 피부 타입 감지 컬럼 추가 (버전 2)
        if current_version < 2:
            if not self._column_exists(cursor, "analyses", "detected_skin_types"):
                cursor.execute("ALTER TABLE analyses ADD COLUMN detected_skin_types TEXT")
                cursor.execute("ALTER TABLE analyses ADD COLUMN skin_type_confidence REAL")
                cursor.execute("ALTER TABLE analyses ADD COLUMN skin_type_features TEXT")
                cursor.execute("ALTER TABLE analyses ADD COLUMN skin_type_source TEXT DEFAULT 'auto'")
                cursor.execute("INSERT INTO schema_version (version) VALUES (2)")
                self._conn.commit()

        # 마이그레이션: 장애 자동 복구 테이블 추가 (버전 3)
        if current_version < 3:
            # 장애 이벤트 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incident_events (
                    id TEXT PRIMARY KEY,
                    incident_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    status TEXT DEFAULT 'detected',
                    description TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_incident_events_type
                ON incident_events(incident_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_incident_events_severity
                ON incident_events(severity)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_incident_events_detected
                ON incident_events(detected_at)
            """)

            # 복구 작업 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recovery_actions (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_status TEXT DEFAULT 'pending',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    rollback_at TIMESTAMP,
                    error_message TEXT,
                    FOREIGN KEY (incident_id) REFERENCES incident_events(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recovery_actions_incident
                ON recovery_actions(incident_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recovery_actions_status
                ON recovery_actions(action_status)
            """)

            # 복구 로그 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recovery_logs (
                    id TEXT PRIMARY KEY,
                    recovery_action_id TEXT NOT NULL,
                    log_level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (recovery_action_id) REFERENCES recovery_actions(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recovery_logs_action
                ON recovery_logs(recovery_action_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recovery_logs_created
                ON recovery_logs(created_at)
            """)

            cursor.execute("INSERT INTO schema_version (version) VALUES (3)")
            self._conn.commit()
            log.info("[DB] 장애 자동 복구 테이블 생성 완료 (버전 3)")

        # 마이그레이션: 사용자 설정 테이블 추가 (버전 4)
        if current_version < 4:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT UNIQUE NOT NULL,
                    language TEXT DEFAULT 'ko',
                    timezone TEXT DEFAULT 'Asia/Seoul',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_preferences_customer
                ON user_preferences(customer_id)
            """)
            cursor.execute("INSERT INTO schema_version (version) VALUES (4)")
            self._conn.commit()
            log.info("[DB] 사용자 설정 테이블 생성 완료 (버전 4)")

        # 피부 타입 검증 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skin_type_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id INTEGER NOT NULL,
                survey_skin_types TEXT,
                detected_skin_types TEXT,
                user_confirmed_skin_types TEXT,
                is_correct INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id)
            )
        """)

        # 인덱스 추가
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stv_analysis_id
            ON skin_type_validations(analysis_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stv_created
            ON skin_type_validations(created_at)
        """)

        # ProductTable 생성 (맞춤형 화장품 성분 정보)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                key_ingredients TEXT NOT NULL,
                efficacy TEXT NOT NULL,
                target_skin_types TEXT,
                target_concerns TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 샘플 제품 데이터 로드 (테이블이 비어있는 경우만)
        cursor.execute("SELECT COUNT(*) FROM products")
        product_count = cursor.fetchone()[0]
        if product_count == 0:
            self._load_sample_products(cursor)
            self._conn.commit()

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_customer
            ON analyses(customer_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created
            ON analyses(created_at)
        """)

    def _column_exists(self, cursor, table_name: str, column_name: str) -> bool:
        """테이블에 컬럼이 존재하는지 확인합니다.
        
        [FIX 2026-05-24] PRAGMA table_info를 사용하여 안전한 컬럼 존재 확인.
        """
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        return column_name in columns

    def close(self) -> None:
        """연결 종료."""
        with self._lock:
            self._conn.close()

    def __enter__(self):
        """Context manager 진입."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료 시 연결 종료."""
        self.close()
        return False

    # ── 저장 ─────────────────────────────────────────────────────────────────

    def save_analysis(
        self,
        original_path: str,
        restored_path: str,
        json_result: Dict[str, Any],
        customer_id: Optional[str] = None,
        input_json: Optional[Dict[str, Any]] = None,
        supabase_async: bool = True,
    ) -> int:
        """
        분석 결과를 로컬 SQLite 에 저장하고, Supabase 에도 동기화.

        Parameters
        ----------
        original_path:
            원본 이미지 경로.
        restored_path:
            복원 이미지 경로.
        json_result:
            분석 결과 JSON 딕셔너리.
        customer_id:
            고객 식별자 (선택사항).
        input_json:
            스마트폰에서 보내온 입력 JSON (survey + client_meta).
        supabase_async:
            True(기본)이면 Supabase 업로드를 백그라운드 스레드로 실행.
            False 이면 현재 스레드에서 완료까지 대기 (테스트·배치 용).

        Returns
        -------
        int
            로컬 SQLite 에 저장된 레코드 ID.
        """
        # ── 1. 로컬 SQLite 저장 ───────────────────────────────────────────
        with self._lock:
            cursor = self._conn.cursor()

            original_filename = Path(original_path).stem if original_path else ""

            # 점수 추출: analysis_result 키에서 추출
            # [REFACTOR P0-8] 중복 로직을 result_parser.py로 통합
            from src.db.result_parser import extract_overall_scores
            overall_orig, overall_rest = extract_overall_scores(json_result)

            cursor.execute("""
                INSERT INTO analyses (
                    customer_id,
                    original_image_path,
                    restored_image_path,
                    json_result,
                    input_json,
                    original_filename,
                    overall_score_original,
                    overall_score_restored,
                    detected_skin_types,
                    skin_type_confidence,
                    skin_type_features,
                    skin_type_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                customer_id,
                str(original_path),
                str(restored_path),
                json.dumps(json_result, ensure_ascii=False, indent=2),
                json.dumps(input_json, ensure_ascii=False, indent=2) if input_json else None,
                original_filename,
                float(overall_orig),
                float(overall_rest),
                json.dumps(json_result.get("skin_type_detection", {}).get("skin_types"), ensure_ascii=False) if json_result.get("skin_type_detection") else None,
                json_result.get("skin_type_detection", {}).get("confidence") if json_result.get("skin_type_detection") else None,
                json.dumps(json_result.get("skin_type_detection", {}).get("features"), ensure_ascii=False) if json_result.get("skin_type_detection") else None,
                "auto" if json_result.get("skin_type_detection") else None,
            ))

            analysis_id = cursor.lastrowid
            self._conn.commit()

            log.info("[DB] 분석 결과 저장 완료: ID=%d, 파일명=%s", analysis_id, original_filename)

        # ── 2. Supabase 동기화 ────────────────────────────────────────────
        if self._supabase_sync_enabled:
            self._sync_to_supabase(
                local_id      = analysis_id,
                original_path = original_path,
                restored_path = restored_path,
                json_result   = json_result,
                customer_id   = customer_id,
                async_mode    = supabase_async,
                input_json    = input_json,
            )

        return analysis_id

    def _sync_to_supabase(
        self,
        local_id:      int,
        original_path: str,
        restored_path: str,
        json_result:   Dict[str, Any],
        customer_id:   Optional[str],
        async_mode:    bool,
        input_json:    Optional[Dict[str, Any]] = None,
    ) -> None:
        """Supabase 동기화 내부 호출. 실패는 경고 로그만 남기고 무시."""
        try:
            from src.db.supabase_sync import get_syncer
            syncer = get_syncer()
            if not syncer.is_available():
                log.debug("[Supabase] 연결 비가용 — 동기화 건너뜀")
                return
            syncer.sync(
                local_id      = local_id,
                original_path = original_path,
                restored_path = restored_path,
                json_result   = json_result,
                customer_id   = customer_id,
                input_json    = input_json,
                sync_mode     = not async_mode,
            )
        except Exception as e:
            log.warning("[Supabase] 동기화 호출 실패: %s", e)

    # ── 조회 / 검색 / 삭제 (기존 메서드 — 변경 없음) ────────────────────────

    def get_analysis(self, analysis_id: int) -> Optional[Dict[str, Any]]:
        """ID로 분석 결과 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT json_result FROM analyses WHERE id = ?
            """, (analysis_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

    def get_customer_analyses(self, customer_id: str) -> List[Dict[str, Any]]:
        """고객의 전체 분석 기록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                WHERE customer_id = ?
                ORDER BY created_at DESC
            """, (customer_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "original_filename": row[1],
                    "created_at": row[2],
                    "overall_score_original": row[3],
                    "overall_score_restored": row[4],
                }
                for row in rows
            ]

    def get_recent_analyses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """최근 분석 기록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                "id": row[0],
                "customer_id": row[1],
                "original_filename": row[2],
                "created_at": row[3],
                "overall_score_original": row[4],
                "overall_score_restored": row[5],
            }
            for row in rows
        ]

    def search_by_filename(self, filename: str) -> List[Dict[str, Any]]:
        """파일명으로 분석 기록 검색 (부분 일치)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                WHERE original_filename LIKE ?
                ORDER BY created_at DESC
            """, (f"%{filename}%",))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "customer_id": row[1],
                    "original_filename": row[2],
                    "created_at": row[3],
                    "overall_score_original": row[4],
                    "overall_score_restored": row[5],
                }
                for row in rows
            ]

    def delete_analysis(self, analysis_id: int) -> bool:
        """분석 기록 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM analyses WHERE id = ?
            """, (analysis_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 분석 기록 삭제 완료: ID=%d", analysis_id)
            return deleted

    def get_stats(self) -> Dict[str, Any]:
        """DB 통계 정보 조회"""
        with self._lock:
            cursor = self._conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM analyses")
            total_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT customer_id) FROM analyses WHERE customer_id IS NOT NULL")
            customer_count = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(created_at) FROM analyses")
            last_analysis = cursor.fetchone()[0]

            return {
                "total_analyses":   total_count,
                "total_customers": customer_count,
                "last_analysis":    last_analysis,
            }

    def _load_sample_products(self, cursor) -> None:
        """샘플 제품 데이터 로드"""
        sample_products = [
            {
                "product_id": "P001",
                "product_name": "CÔTELEAF 트러블 케어 세럼",
                "category": "트러블 케어",
                "key_ingredients": ["나이아신아마이드", "살리실산", "티트리 오일"],
                "efficacy": "여드름 억제, 모공 관리, 피부 진정",
                "target_skin_types": ["oily", "combination", "acne_prone"],
                "target_concerns": ["여드름", "모공", "트러블"],
            },
            {
                "product_id": "P002",
                "product_name": "CÔTELEAF 레드니스 케어 크림",
                "category": "홍조 케어",
                "key_ingredients": ["병풀 추출물", "판테놀", "알로에 베라"],
                "efficacy": "홍조 완화, 피부 진정, 장벽 강화",
                "target_skin_types": ["sensitive", "combination", "dry"],
                "target_concerns": ["홍조", "민감성", "붉은기"],
            },
            {
                "product_id": "P003",
                "product_name": "CÔTELEAF 브라이트닝 앰플",
                "category": "색소 케어",
                "key_ingredients": ["비타민 C", "글루타치온", "나이아신아마이드"],
                "efficacy": "색소 침착 개선, 피부 톤 밝기",
                "target_skin_types": ["all", "combination", "dry"],
                "target_concerns": ["색소침착", "기미", "주근깨", "칙칙함"],
            },
            {
                "product_id": "P004",
                "product_name": "CÔTELEAF 안티에이징 크림",
                "category": "주름 케어",
                "key_ingredients": ["레티놀", "펩타이드", "히알루론산"],
                "efficacy": "주름 개선, 탄력 증진, 보습",
                "target_skin_types": ["mature", "dry", "combination"],
                "target_concerns": ["주름", "탄력", "건조"],
            },
            {
                "product_id": "P005",
                "product_name": "CÔTELEAF 모공 토너",
                "category": "모공 케어",
                "key_ingredients": ["BHA", "AHA", "하이드로진산"],
                "efficacy": "모공 축소, 각질 제거, 피부결 개선",
                "target_skin_types": ["oily", "combination"],
                "target_concerns": ["모공", "거칠기", "블랙헤드"],
            },
        ]
        
        for product_data in sample_products:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO products
                    (product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_data["product_id"],
                    product_data["product_name"],
                    product_data["category"],
                    json.dumps(product_data["key_ingredients"], ensure_ascii=False),
                    product_data["efficacy"],
                    json.dumps(product_data["target_skin_types"], ensure_ascii=False),
                    json.dumps(product_data["target_concerns"], ensure_ascii=False),
                ))
                log.info(f"샘플 제품 로드 완료: {product_data['product_name']}")
            except Exception as e:
                log.warning(f"샘플 제품 로드 실패: {product_data['product_name']} - {e}")

    # ── 장애 자동 복구 관련 메서드 ───────────────────────────────────────────────

    def create_incident(
        self,
        incident_type: str,
        severity: str,
        resource_type: str,
        resource_id: str,
        description: Optional[str] = None,
    ) -> str:
        """장애 이벤트 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            incident_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO incident_events (
                    id, incident_type, severity, resource_type, resource_id, description
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (incident_id, incident_type, severity, resource_type, resource_id, description))
            self._conn.commit()
            log.info("[DB] 장애 이벤트 생성: ID=%s, Type=%s, Severity=%s", incident_id, incident_type, severity)
            return incident_id

    def update_incident_status(self, incident_id: str, status: str) -> bool:
        """장애 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            if status == "resolved":
                cursor.execute("""
                    UPDATE incident_events
                    SET status = ?, resolved_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, incident_id))
            else:
                cursor.execute("""
                    UPDATE incident_events
                    SET status = ?
                    WHERE id = ?
                """, (status, incident_id))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 장애 상태 업데이트: ID=%s, Status=%s", incident_id, status)
            return updated

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """장애 이벤트 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, incident_type, severity, resource_type, resource_id,
                       detected_at, resolved_at, status, description
                FROM incident_events
                WHERE id = ?
            """, (incident_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "incident_type": row[1],
                    "severity": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "detected_at": row[5],
                    "resolved_at": row[6],
                    "status": row[7],
                    "description": row[8],
                }
            return None

    def get_incidents(
        self,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """장애 이벤트 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, incident_type, severity, resource_type, resource_id,
                       detected_at, resolved_at, status, description
                FROM incident_events
                WHERE 1=1
            """
            params = []
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY detected_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "incident_type": row[1],
                    "severity": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "detected_at": row[5],
                    "resolved_at": row[6],
                    "status": row[7],
                    "description": row[8],
                }
                for row in rows
            ]

    def create_recovery_action(
        self,
        incident_id: str,
        action_type: str,
    ) -> str:
        """복구 작업 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            action_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO recovery_actions (id, incident_id, action_type)
                VALUES (?, ?, ?)
            """, (action_id, incident_id, action_type))
            self._conn.commit()
            log.info("[DB] 복구 작업 생성: ID=%s, IncidentID=%s, Type=%s", action_id, incident_id, action_type)
            return action_id

    def update_recovery_action_status(
        self,
        action_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """복구 작업 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            if status == "in_progress":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, action_id))
            elif status == "completed":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, action_id))
            elif status == "failed":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, error_message = ?
                    WHERE id = ?
                """, (status, error_message, action_id))
            elif status == "rolled_back":
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?, rollback_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, action_id))
            else:
                cursor.execute("""
                    UPDATE recovery_actions
                    SET action_status = ?
                    WHERE id = ?
                """, (status, action_id))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 복구 작업 상태 업데이트: ID=%s, Status=%s", action_id, status)
            return updated

    def get_recovery_actions(self, incident_id: str) -> List[Dict[str, Any]]:
        """복구 작업 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, incident_id, action_type, action_status,
                       started_at, completed_at, rollback_at, error_message
                FROM recovery_actions
                WHERE incident_id = ?
                ORDER BY started_at DESC
            """, (incident_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "incident_id": row[1],
                    "action_type": row[2],
                    "action_status": row[3],
                    "started_at": row[4],
                    "completed_at": row[5],
                    "rollback_at": row[6],
                    "error_message": row[7],
                }
                for row in rows
            ]

    def add_recovery_log(
        self,
        recovery_action_id: str,
        log_level: str,
        message: str,
    ) -> str:
        """복구 로그 추가"""
        with self._lock:
            cursor = self._conn.cursor()
            log_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO recovery_logs (id, recovery_action_id, log_level, message)
                VALUES (?, ?, ?, ?)
            """, (log_id, recovery_action_id, log_level, message))
            self._conn.commit()
            return log_id

    def get_recovery_logs(self, recovery_action_id: str) -> List[Dict[str, Any]]:
        """복구 로그 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, recovery_action_id, log_level, message, created_at
                FROM recovery_logs
                WHERE recovery_action_id = ?
                ORDER BY created_at ASC
            """, (recovery_action_id,))
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "recovery_action_id": row[1],
                    "log_level": row[2],
                    "message": row[3],
                    "created_at": row[4],
                }
                for row in rows
            ]

    # ── 사용자 설정 관련 메서드 ───────────────────────────────────────────────

    def set_user_language(self, customer_id: str, language: str) -> bool:
        """사용자 언어 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_preferences (customer_id, language)
                VALUES (?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET language = ?, updated_at = CURRENT_TIMESTAMP
            """, (customer_id, language, language))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 사용자 언어 설정: customer_id=%s, language=%s", customer_id, language)
            return updated

    def get_user_language(self, customer_id: str) -> str:
        """사용자 언어 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT language FROM user_preferences WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            return row[0] if row else "ko"

    def set_user_timezone(self, customer_id: str, timezone: str) -> bool:
        """사용자 시간대 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_preferences (customer_id, timezone)
                VALUES (?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET timezone = ?, updated_at = CURRENT_TIMESTAMP
            """, (customer_id, timezone, timezone))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 사용자 시간대 설정: customer_id=%s, timezone=%s", customer_id, timezone)
            return updated

    def get_user_timezone(self, customer_id: str) -> str:
        """사용자 시간대 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT timezone FROM user_preferences WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            return row[0] if row else "Asia/Seoul"

    def get_user_preferences(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """사용자 설정 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT customer_id, language, timezone, created_at, updated_at
                FROM user_preferences WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": row[0],
                    "language": row[1],
                    "timezone": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                }
            return None
