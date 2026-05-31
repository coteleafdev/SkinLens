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
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

log = logging.getLogger(__name__)

from src.utils.config import load_config as _load_config


class SkinAnalysisDB:
    """피부 분석 결과를 관리하는 SQLite DB 클래스"""

    def __init__(
        self,
        db_path: str = "results/skin_analysis.db",
        supabase_sync: Optional[bool] = None,
    ):
        """
        DB 초기화.

        Parameters
        ----------
        db_path:
            DB 파일 경로 (기본값: results/skin_analysis.db).
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
                cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")
                self._conn.commit()

        # 마이그레이션: 피부 타입 감지 컬럼 추가 (버전 2)
        if current_version < 2:
            if not self._column_exists(cursor, "analyses", "detected_skin_types"):
                cursor.execute("ALTER TABLE analyses ADD COLUMN detected_skin_types TEXT")
                cursor.execute("ALTER TABLE analyses ADD COLUMN skin_type_confidence REAL")
                cursor.execute("ALTER TABLE analyses ADD COLUMN skin_type_features TEXT")
                cursor.execute("ALTER TABLE analyses ADD COLUMN skin_type_source TEXT DEFAULT 'auto'")
                cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (2)")
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

            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (3)")
            self._conn.commit()
            log.info("[DB] 장애 자동 복구 테이블 생성 완료 (버전 3)")

        # 마이그레이션: API 키 관리 테이블 추가 (버전 4)
        if current_version < 4:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT,
                    owner_id TEXT,
                    scopes TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    expires_at TIMESTAMP,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TIMESTAMP,
                    revoke_reason TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_owner
                ON api_keys(owner_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_active
                ON api_keys(is_active, expires_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_hash
                ON api_keys(key_hash)
            """)

            # API 키 사용 로그 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_key_usage_logs (
                    id TEXT PRIMARY KEY,
                    api_key_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    success BOOLEAN DEFAULT 1,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (api_key_id) REFERENCES api_keys(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_key_logs_key
                ON api_key_usage_logs(api_key_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_key_logs_created
                ON api_key_usage_logs(created_at)
            """)

            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (4)")
            self._conn.commit()
            log.info("[DB] API 키 관리 테이블 생성 완료 (버전 4)")

        # 마이그레이션: 사용자 설정 테이블 추가 (버전 5)
        if current_version < 5:
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
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (5)")
            self._conn.commit()
            log.info("[DB] 사용자 설정 테이블 생성 완료 (버전 5)")

        # 마이그레이션: 북마크 테이블 추가 (버전 6)
        if current_version < 6:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    analysis_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bookmarks_customer
                ON analysis_bookmarks(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bookmarks_analysis
                ON analysis_bookmarks(analysis_id)
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_customer_analysis
                ON analysis_bookmarks(customer_id, analysis_id)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (6)")
            self._conn.commit()
            log.info("[DB] 북마크 테이블 생성 완료 (버전 6)")

        # 마이그레이션: 알림 설정 테이블 추가 (버전 7)
        if current_version < 7:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT UNIQUE NOT NULL,
                    analysis_complete BOOLEAN DEFAULT 1,
                    score_improvement BOOLEAN DEFAULT 1,
                    care_reminder BOOLEAN DEFAULT 0,
                    marketing BOOLEAN DEFAULT 0,
                    reminder_hours INTEGER DEFAULT 168,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_settings_customer
                ON notification_settings(customer_id)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (7)")
            self._conn.commit()
            log.info("[DB] 알림 설정 테이블 생성 완료 (버전 7)")

        # 마이그레이션: 제품 추천 테이블 추가 (버전 8)
        if current_version < 8:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    analysis_id INTEGER NOT NULL,
                    product_id TEXT NOT NULL,
                    match_score REAL,
                    recommendation_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recommendations_customer
                ON product_recommendations(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recommendations_analysis
                ON product_recommendations(analysis_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recommendations_product
                ON product_recommendations(product_id)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (8)")
            self._conn.commit()
            log.info("[DB] 제품 추천 테이블 생성 완료 (버전 8)")

        # 마이그레이션: 고객 관리 테이블 추가 (버전 9)
        if current_version < 9:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customer_profiles (
                    customer_id TEXT PRIMARY KEY,
                    email TEXT,
                    name TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login_at TIMESTAMP,
                    total_analyses INTEGER DEFAULT 0,
                    FOREIGN KEY (customer_id) REFERENCES analyses(customer_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_customer_profiles_status
                ON customer_profiles(status)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (9)")
            self._conn.commit()
            log.info("[DB] 고객 프로필 테이블 생성 완료 (버전 9)")

        # 마이그레이션: 사용자 세션 테이블 추가 (버전 10)
        if current_version < 10:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_customer
                ON user_sessions(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_active
                ON user_sessions(is_active)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (10)")
            self._conn.commit()
            log.info("[DB] 사용자 세션 테이블 생성 완료 (버전 10)")

        # 마이그레이션: 이상 활동 테이블 추가 (버전 11)
        if current_version < 11:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_anomalies (
                    id TEXT PRIMARY KEY,
                    anomaly_type TEXT NOT NULL,
                    customer_id TEXT,
                    ip_address TEXT,
                    description TEXT,
                    severity TEXT DEFAULT 'medium',
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    status TEXT DEFAULT 'detected'
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_anomalies_type
                ON security_anomalies(anomaly_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_anomalies_status
                ON security_anomalies(status)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (11)")
            self._conn.commit()
            log.info("[DB] 이상 활동 테이블 생성 완료 (버전 11)")

        # 마이그레이션: 역할 테이블 추가 (버전 12)
        if current_version < 12:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_roles (
                    customer_id TEXT PRIMARY KEY,
                    role TEXT DEFAULT 'customer',
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    granted_by TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_roles_role
                ON user_roles(role)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (12)")
            self._conn.commit()
            log.info("[DB] 사용자 역할 테이블 생성 완료 (버전 12)")

        # 마이그레이션: 차단된 IP 테이블 추가 (버전 13)
        if current_version < 13:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blocked_ips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT UNIQUE NOT NULL,
                    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    blocked_by TEXT,
                    reason TEXT,
                    expires_at TIMESTAMP,
                    is_permanent BOOLEAN DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_blocked_ips_address
                ON blocked_ips(ip_address)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (13)")
            self._conn.commit()
            log.info("[DB] 차단된 IP 테이블 생성 완료 (버전 13)")

        # 마이그레이션: 일일 통계 테이블 추가 (버전 14)
        if current_version < 14:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    total_analyses INTEGER DEFAULT 0,
                    unique_customers INTEGER DEFAULT 0,
                    successful_analyses INTEGER DEFAULT 0,
                    failed_analyses INTEGER DEFAULT 0,
                    avg_score REAL,
                    total_revenue REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (14)")
            self._conn.commit()
            log.info("[DB] 일일 통계 테이블 생성 완료 (버전 14)")

        # 마이그레이션: 웹훅 테이블 추가 (버전 15)
        if current_version < 15:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    events TEXT NOT NULL,
                    secret_key TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES analyses(customer_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhooks_customer
                ON webhooks(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhooks_active
                ON webhooks(is_active)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (15)")
            self._conn.commit()
            log.info("[DB] 웹훅 테이블 생성 완료 (버전 15)")

        # 마이그레이션: 외부 동기화 로그 테이블 추가 (버전 16)
        if current_version < 16:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS external_sync_logs (
                    id TEXT PRIMARY KEY,
                    sync_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    source_system TEXT,
                    target_system TEXT,
                    records_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_logs_type
                ON external_sync_logs(sync_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_logs_status
                ON external_sync_logs(status)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (16)")
            self._conn.commit()
            log.info("[DB] 외부 동기화 로그 테이블 생성 완료 (버전 16)")

        # 마이그레이션: OAuth 제공자 테이블 추가 (버전 17)
        if current_version < 17:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oauth_providers (
                    id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    client_secret TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    scopes TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_oauth_provider_name
                ON oauth_providers(provider_name)
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES analyses(customer_id),
                    FOREIGN KEY (provider_id) REFERENCES oauth_providers(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_oauth_tokens_customer
                ON oauth_tokens(customer_id)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (17)")
            self._conn.commit()
            log.info("[DB] OAuth 제공자 테이블 생성 완료 (버전 17)")

        # 버전 18: 이미지 업로드 관리 테이블
        if current_version < 18:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS image_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    upload_id TEXT UNIQUE NOT NULL,
                    original_filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    width INTEGER,
                    height INTEGER,
                    rotation_angle INTEGER DEFAULT 0,
                    upload_status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_image_uploads_customer
                ON image_uploads(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_image_uploads_status
                ON image_uploads(upload_status)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (18)")
            self._conn.commit()
            log.info("[DB] 이미지 업로드 테이블 생성 완료 (버전 18)")

        # 버전 19: 푸시 알림 선호도 테이블
        if current_version < 19:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS push_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT UNIQUE NOT NULL,
                    push_enabled INTEGER DEFAULT 1,
                    analysis_complete_enabled INTEGER DEFAULT 1,
                    promotion_enabled INTEGER DEFAULT 0,
                    quiet_hours_start TEXT,
                    quiet_hours_end TEXT,
                    device_token TEXT,
                    platform TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_push_preferences_customer
                ON push_preferences(customer_id)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (19)")
            self._conn.commit()
            log.info("[DB] 푸시 알림 선호도 테이블 생성 완료 (버전 19)")

        # 버전 20: A/B 테스트 관리 테이블
        if current_version < 20:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    variant_a_name TEXT NOT NULL,
                    variant_b_name TEXT NOT NULL,
                    traffic_split REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'active',
                    start_date TIMESTAMP,
                    end_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ab_tests_status
                ON ab_tests(status)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (20)")
            self._conn.commit()
            log.info("[DB] A/B 테스트 테이블 생성 완료 (버전 20)")

        # 버전 21: A/B 테스트 사용자 분배 테이블
        if current_version < 21:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    customer_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (test_id) REFERENCES ab_tests(id),
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
                    UNIQUE(test_id, customer_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ab_assignments_test
                ON ab_test_assignments(test_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ab_assignments_customer
                ON ab_test_assignments(customer_id)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (21)")
            self._conn.commit()
            log.info("[DB] A/B 테스트 분배 테이블 생성 완료 (버전 21)")

        # 버전 22: A/B 테스트 결과 테이블
        if current_version < 22:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ab_test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    variant TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL,
                    event_count INTEGER DEFAULT 0,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (test_id) REFERENCES ab_tests(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ab_results_test
                ON ab_test_results(test_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ab_results_variant
                ON ab_test_results(variant)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (22)")
            self._conn.commit()
            log.info("[DB] A/B 테스트 결과 테이블 생성 완료 (버전 22)")

        # 버전 23: 모니터링 메트릭 테이블
        if current_version < 23:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitoring_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL,
                    metric_unit TEXT,
                    tags TEXT,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_monitoring_name
                ON monitoring_metrics(metric_name)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_monitoring_recorded
                ON monitoring_metrics(recorded_at)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (23)")
            self._conn.commit()
            log.info("[DB] 모니터링 메트릭 테이블 생성 완료 (버전 23)")

        # 버전 24: 분석 추이 테이블
        if current_version < 24:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_trends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    analysis_id INTEGER NOT NULL,
                    overall_score_original REAL,
                    overall_score_restored REAL,
                    measurement_scores TEXT,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trends_customer
                ON analysis_trends(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trends_recorded
                ON analysis_trends(recorded_at)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (24)")
            self._conn.commit()
            log.info("[DB] 분석 추이 테이블 생성 완료 (버전 24)")

        # 제품 피드백 테이블 생성 (버전 25)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 25:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id TEXT UNIQUE NOT NULL,
                    order_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    would_repurchase INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pf_order_id
                ON product_feedback(order_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pf_product_id
                ON product_feedback(product_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pf_customer_id
                ON product_feedback(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pf_created
                ON product_feedback(created_at)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (25)")
            self._conn.commit()
            log.info("[DB] 제품 피드백 테이블 생성 완료 (버전 25)")

        # 피부 일기 테이블 생성 (버전 26)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 26:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skin_diary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    analysis_id INTEGER,
                    image_url TEXT,
                    overall_score REAL,
                    measurement_scores TEXT,
                    notes TEXT,
                    mood TEXT,
                    weather TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sd_customer_id
                ON skin_diary(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sd_analysis_id
                ON skin_diary(analysis_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sd_created
                ON skin_diary(created_at)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (26)")
            self._conn.commit()
            log.info("[DB] 피부 일기 테이블 생성 완료 (버전 26)")

        # 고객 목표 테이블 생성 (버전 27)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 27:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customer_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    goal_type TEXT NOT NULL,
                    target_value REAL,
                    current_value REAL,
                    start_date DATE,
                    end_date DATE,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cg_customer_id
                ON customer_goals(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cg_status
                ON customer_goals(status)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (27)")
            self._conn.commit()
            log.info("[DB] 고객 목표 테이블 생성 완료 (버전 27)")

        # 업적 테이블 생성 (버전 28)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 28:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    achievement_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    icon TEXT,
                    requirement_type TEXT,
                    requirement_value REAL,
                    reward_points INTEGER DEFAULT 0
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ach_id
                ON achievements(achievement_id)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (28)")
            self._conn.commit()
            log.info("[DB] 업적 테이블 생성 완료 (버전 28)")

        # 고객 업적 테이블 생성 (버전 29)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 29:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customer_achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    achievement_id TEXT NOT NULL,
                    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (achievement_id) REFERENCES achievements(achievement_id)
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ca_customer_id
                ON customer_achievements(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ca_achievement_id
                ON customer_achievements(achievement_id)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (29)")
            self._conn.commit()
            log.info("[DB] 고객 업적 테이블 생성 완료 (버전 29)")

        # 제품 구독 테이블 생성 (버전 30)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 30:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    next_delivery_date DATE,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ps_customer_id
                ON product_subscriptions(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ps_product_id
                ON product_subscriptions(product_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ps_status
                ON product_subscriptions(status)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (30)")
            self._conn.commit()
            log.info("[DB] 제품 구독 테이블 생성 완료 (버전 30)")

        # 챌린지 테이블 생성 (버전 31)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 31:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS challenges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    challenge_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    duration_days INTEGER,
                    start_date DATE,
                    end_date DATE,
                    reward_points INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active'
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ch_id
                ON challenges(challenge_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ch_status
                ON challenges(status)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (31)")
            self._conn.commit()
            log.info("[DB] 챌린지 테이블 생성 완료 (버전 31)")

        # 고객 챌린지 참여 테이블 생성 (버전 32)
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 32:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customer_challenges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    challenge_id TEXT NOT NULL,
                    start_date DATE,
                    end_date DATE,
                    progress REAL DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (challenge_id) REFERENCES challenges(challenge_id)
                )
            """)
            
            # 인덱스 추가
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cc_customer_id
                ON customer_challenges(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cc_challenge_id
                ON customer_challenges(challenge_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cc_status
                ON customer_challenges(status)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (32)")
            self._conn.commit()
            log.info("[DB] 고객 챌린지 참여 테이블 생성 완료 (버전 32)")

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

    def get_customer_analysis_detail(self, customer_id: str, analysis_id: int) -> Optional[Dict[str, Any]]:
        """고객의 특정 분석 상세 정보 조회 (이미지 경로 포함)"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, original_image_path, restored_image_path,
                       json_result, input_json, original_filename, created_at,
                       overall_score_original, overall_score_restored
                FROM analyses
                WHERE customer_id = ? AND id = ?
            """, (customer_id, analysis_id))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "customer_id": row[1],
                    "original_image_path": row[2],
                    "restored_image_path": row[3],
                    "json_result": json.loads(row[4]) if row[4] else None,
                    "input_json": json.loads(row[5]) if row[5] else None,
                    "original_filename": row[6],
                    "created_at": row[7],
                    "overall_score_original": row[8],
                    "overall_score_restored": row[9],
                }
            return None

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
                "efficacy": "트러블 억제, 모공 관리, 피부 진정",
                "target_skin_types": ["oily", "combination", "acne_prone"],
                "target_concerns": ["트러블", "모공"],
            },
            {
                "product_id": "P002",
                "product_name": "CÔTELEAF 레드니스 케어 크림",
                "category": "홍조 케어",
                "key_ingredients": ["병풀 추출물", "판테놀", "알로에 베라"],
                "efficacy": "홍조 완화, 피부 진정, 장벽 강화",
                "target_skin_types": ["sensitive", "combination", "dry"],
                "target_concerns": ["홍조", "민감성", "붉은기"],
                "target_prescription_items": ["M06"],  # 홍조
            },
            {
                "product_id": "P003",
                "product_name": "CÔTELEAF 브라이트닝 앰플",
                "category": "색소 케어",
                "key_ingredients": ["비타민 C", "글루타치온", "나이아신아마이드"],
                "efficacy": "색소 침착 개선, 피부 톤 밝기",
                "target_skin_types": ["all", "combination", "dry"],
                "target_concerns": ["색소침착", "기미", "주근깨", "칙칙함"],
                "target_prescription_items": ["M01", "M05"],  # 광채, 색소침착
            },
            {
                "product_id": "P004",
                "product_name": "CÔTELEAF 안티에이징 크림",
                "category": "주름 케어",
                "key_ingredients": ["레티놀", "펩타이드", "히알루론산"],
                "efficacy": "주름 개선, 탄력 증진, 보습",
                "target_skin_types": ["mature", "dry", "combination"],
                "target_concerns": ["주름", "탄력", "건조"],
                "target_prescription_items": ["M02"],  # 주름
            },
            {
                "product_id": "P005",
                "product_name": "CÔTELEAF 모공 토너",
                "category": "모공 케어",
                "key_ingredients": ["BHA", "AHA", "하이드로진산"],
                "efficacy": "모공 축소, 각질 제거, 피부결 개선",
                "target_skin_types": ["oily", "combination"],
                "target_concerns": ["모공", "거칠기", "블랙헤드"],
                "target_prescription_items": ["M07", "M08"],  # 모공, 피부결
            },
        ]
        
        for product_data in sample_products:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO products
                    (product_id, product_name, category, key_ingredients, efficacy, target_skin_types, target_concerns, target_prescription_items)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_data["product_id"],
                    product_data["product_name"],
                    product_data["category"],
                    json.dumps(product_data["key_ingredients"], ensure_ascii=False),
                    product_data["efficacy"],
                    json.dumps(product_data["target_skin_types"], ensure_ascii=False),
                    json.dumps(product_data["target_concerns"], ensure_ascii=False),
                    json.dumps(product_data.get("target_prescription_items", []), ensure_ascii=False),
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

    # ── API 키 관리 ─────────────────────────────────────────────────────────────

    def create_api_key(
        self,
        name: str,
        owner_id: str,
        description: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """API 키 생성.

        Args:
            name: API 키 이름
            owner_id: 소유자 ID
            description: 설명
            scopes: 권한 범위 (예: ["read", "write"])
            expires_in_days: 만료일수 (None이면 만료 없음)

        Returns:
            생성된 API 키 정보 (실제 키는 한 번만 반환됨)
        """
        import hashlib

        # 실제 API 키 생성 (32 bytes = 64 hex chars)
        api_key = secrets.token_hex(32)

        # 키 해시 생성 (SHA-256)
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # 만료일 계산
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now() + timedelta(days=expires_in_days)

        # JSON으로 scopes 저장
        scopes_json = json.dumps(scopes) if scopes else None

        with self._lock:
            cursor = self._conn.cursor()
            key_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO api_keys (id, key_hash, name, description, owner_id, scopes, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (key_id, key_hash, name, description, owner_id, scopes_json, expires_at))
            self._conn.commit()

        return {
            "id": key_id,
            "api_key": api_key,  # 실제 키는 한 번만 반환
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "scopes": scopes,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "created_at": datetime.now().isoformat(),
        }

    def validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """API 키 검증.

        Args:
            api_key: 검증할 API 키

        Returns:
            유효한 키 정보, 유효하지 않으면 None
        """
        import hashlib

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, name, description, owner_id, scopes, is_active, expires_at
                FROM api_keys
                WHERE key_hash = ? AND is_active = 1
            """, (key_hash,))
            row = cursor.fetchone()

            if not row:
                return None

            # 만료 체크
            expires_at = row[6]
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at)
                if datetime.now() > expires_dt:
                    return None

            # 마지막 사용 시간 업데이트
            cursor.execute("""
                UPDATE api_keys
                SET last_used_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (row[0],))
            self._conn.commit()

            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "owner_id": row[3],
                "scopes": json.loads(row[4]) if row[4] else [],
                "expires_at": row[5],
            }

    def revoke_api_key(self, key_id: str, reason: Optional[str] = None) -> bool:
        """API 키 폐지.

        Args:
            key_id: 폐지할 API 키 ID
            reason: 폐지 사유

        Returns:
            성공 여부
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE api_keys
                SET is_active = 0, revoked_at = CURRENT_TIMESTAMP, revoke_reason = ?
                WHERE id = ?
            """, (reason, key_id))
            self._conn.commit()
            return cursor.rowcount > 0

    def list_api_keys(
        self,
        owner_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """API 키 목록 조회.

        Args:
            owner_id: 소유자 ID 필터
            is_active: 활성 상태 필터
            limit: 최대 반환 수

        Returns:
            API 키 목록
        """
        with self._lock:
            cursor = self._conn.cursor()

            query = """
                SELECT id, name, description, owner_id, scopes, is_active,
                       expires_at, last_used_at, created_at, revoked_at
                FROM api_keys
                WHERE 1=1
            """
            params = []

            if owner_id:
                query += " AND owner_id = ?"
                params.append(owner_id)

            if is_active is not None:
                query += " AND is_active = ?"
                params.append(1 if is_active else 0)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "owner_id": row[3],
                    "scopes": json.loads(row[4]) if row[4] else [],
                    "is_active": bool(row[5]),
                    "expires_at": row[6],
                    "last_used_at": row[7],
                    "created_at": row[8],
                    "revoked_at": row[9],
                }
                for row in rows
            ]

    def log_api_key_usage(
        self,
        api_key_id: str,
        endpoint: str,
        method: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> str:
        """API 키 사용 로그 기록.

        Args:
            api_key_id: API 키 ID
            endpoint: 엔드포인트
            method: HTTP 메서드
            ip_address: IP 주소
            user_agent: User-Agent
            success: 성공 여부
            error_message: 에러 메시지

        Returns:
            로그 ID
        """
        with self._lock:
            cursor = self._conn.cursor()
            log_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO api_key_usage_logs
                (id, api_key_id, endpoint, method, ip_address, user_agent, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, api_key_id, endpoint, method, ip_address, user_agent, success, error_message))
            self._conn.commit()
            return log_id

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

    # ── 북마크 관련 메서드 ─────────────────────────────────────────────────────

    def add_bookmark(self, customer_id: str, analysis_id: int, notes: Optional[str] = None) -> bool:
        """분석 결과 북마크 추가"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO analysis_bookmarks (customer_id, analysis_id, notes)
                    VALUES (?, ?, ?)
                """, (customer_id, analysis_id, notes))
                self._conn.commit()
                log.info("[DB] 북마크 추가: customer_id=%s, analysis_id=%d", customer_id, analysis_id)
                return True
            except sqlite3.IntegrityError:
                # 이미 북마크된 경우
                return False

    def remove_bookmark(self, customer_id: str, analysis_id: int) -> bool:
        """분석 결과 북마크 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM analysis_bookmarks
                WHERE customer_id = ? AND analysis_id = ?
            """, (customer_id, analysis_id))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 북마크 삭제: customer_id=%s, analysis_id=%d", customer_id, analysis_id)
            return deleted

    def get_bookmarks(self, customer_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """고객의 북마크 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT b.id, b.analysis_id, b.notes, b.created_at,
                       a.original_filename, a.created_at as analysis_date,
                       a.overall_score_original, a.overall_score_restored
                FROM analysis_bookmarks b
                JOIN analyses a ON b.analysis_id = a.id
                WHERE b.customer_id = ?
                ORDER BY b.created_at DESC
                LIMIT ? OFFSET ?
            """, (customer_id, limit, offset))
            rows = cursor.fetchall()
            return [
                {
                    "bookmark_id": row[0],
                    "analysis_id": row[1],
                    "notes": row[2],
                    "bookmarked_at": row[3],
                    "original_filename": row[4],
                    "analysis_date": row[5],
                    "overall_score_original": row[6],
                    "overall_score_restored": row[7],
                }
                for row in rows
            ]

    def is_bookmarked(self, customer_id: str, analysis_id: int) -> bool:
        """분석 결과 북마크 여부 확인"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM analysis_bookmarks
                WHERE customer_id = ? AND analysis_id = ?
            """, (customer_id, analysis_id))
            return cursor.fetchone()[0] > 0

    # ── 알림 설정 관련 메서드 ─────────────────────────────────────────────────

    def get_notification_settings(self, customer_id: str) -> Dict[str, Any]:
        """알림 설정 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT analysis_complete, score_improvement, care_reminder,
                       marketing, reminder_hours, created_at, updated_at
                FROM notification_settings WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": customer_id,
                    "analysis_complete": bool(row[0]),
                    "score_improvement": bool(row[1]),
                    "care_reminder": bool(row[2]),
                    "marketing": bool(row[3]),
                    "reminder_hours": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                }
            # 기본 설정 반환
            return {
                "customer_id": customer_id,
                "analysis_complete": True,
                "score_improvement": True,
                "care_reminder": False,
                "marketing": False,
                "reminder_hours": 168,
            }

    def update_notification_settings(
        self,
        customer_id: str,
        analysis_complete: Optional[bool] = None,
        score_improvement: Optional[bool] = None,
        care_reminder: Optional[bool] = None,
        marketing: Optional[bool] = None,
        reminder_hours: Optional[int] = None,
    ) -> bool:
        """알림 설정 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            
            # 업데이트할 필드만 동적으로 구성
            updates = []
            params = []
            
            if analysis_complete is not None:
                updates.append("analysis_complete = ?")
                params.append(1 if analysis_complete else 0)
            if score_improvement is not None:
                updates.append("score_improvement = ?")
                params.append(1 if score_improvement else 0)
            if care_reminder is not None:
                updates.append("care_reminder = ?")
                params.append(1 if care_reminder else 0)
            if marketing is not None:
                updates.append("marketing = ?")
                params.append(1 if marketing else 0)
            if reminder_hours is not None:
                updates.append("reminder_hours = ?")
                params.append(reminder_hours)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(customer_id)
            
            query = f"""
                INSERT INTO notification_settings (customer_id)
                VALUES (?)
                ON CONFLICT(customer_id) DO UPDATE SET {', '.join(updates)}
            """
            
            cursor.execute(query, params)
            self._conn.commit()
            log.info("[DB] 알림 설정 업데이트: customer_id=%s", customer_id)
            return True

    # ── 제품 추천 관련 메서드 ─────────────────────────────────────────────────

    def save_product_recommendation(
        self,
        customer_id: str,
        analysis_id: int,
        product_id: str,
        match_score: float,
        recommendation_reason: str,
    ) -> bool:
        """제품 추천 저장"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO product_recommendations
                (customer_id, analysis_id, product_id, match_score, recommendation_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (customer_id, analysis_id, product_id, match_score, recommendation_reason))
            self._conn.commit()
            log.info("[DB] 제품 추천 저장: customer_id=%s, product_id=%s", customer_id, product_id)
            return True

    def get_product_recommendations(
        self,
        customer_id: str,
        analysis_id: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """고객의 제품 추천 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            
            if analysis_id:
                cursor.execute("""
                    SELECT pr.id, pr.analysis_id, pr.product_id, pr.match_score,
                           pr.recommendation_reason, pr.created_at,
                           p.product_name, p.category, p.key_ingredients, p.efficacy
                    FROM product_recommendations pr
                    JOIN products p ON pr.product_id = p.product_id
                    WHERE pr.customer_id = ? AND pr.analysis_id = ?
                    ORDER BY pr.match_score DESC
                    LIMIT ?
                """, (customer_id, analysis_id, limit))
            else:
                cursor.execute("""
                    SELECT pr.id, pr.analysis_id, pr.product_id, pr.match_score,
                           pr.recommendation_reason, pr.created_at,
                           p.product_name, p.category, p.key_ingredients, p.efficacy
                    FROM product_recommendations pr
                    JOIN products p ON pr.product_id = p.product_id
                    WHERE pr.customer_id = ?
                    ORDER BY pr.created_at DESC
                    LIMIT ?
                """, (customer_id, limit))
            
            rows = cursor.fetchall()
            return [
                {
                    "recommendation_id": row[0],
                    "analysis_id": row[1],
                    "product_id": row[2],
                    "match_score": row[3],
                    "recommendation_reason": row[4],
                    "recommended_at": row[5],
                    "product_name": row[6],
                    "category": row[7],
                    "key_ingredients": json.loads(row[8]) if row[8] else [],
                    "efficacy": row[9],
                }
                for row in rows
            ]

    def get_latest_recommendations(self, customer_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """최근 분석 기반 제품 추천 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT pr.id, pr.analysis_id, pr.product_id, pr.match_score,
                       pr.recommendation_reason, pr.created_at,
                       p.product_name, p.category, p.key_ingredients, p.efficacy,
                       a.overall_score_restored
                FROM product_recommendations pr
                JOIN products p ON pr.product_id = p.product_id
                JOIN analyses a ON pr.analysis_id = a.id
                WHERE pr.customer_id = ?
                ORDER BY pr.created_at DESC
                LIMIT ?
            """, (customer_id, limit))
            
            rows = cursor.fetchall()
            return [
                {
                    "recommendation_id": row[0],
                    "analysis_id": row[1],
                    "product_id": row[2],
                    "match_score": row[3],
                    "recommendation_reason": row[4],
                    "recommended_at": row[5],
                    "product_name": row[6],
                    "category": row[7],
                    "key_ingredients": json.loads(row[8]) if row[8] else [],
                    "efficacy": row[9],
                    "latest_score": row[10],
                }
                for row in rows
            ]

    # ── 고객 관리 관련 메서드 ─────────────────────────────────────────────────

    def create_customer_profile(
        self,
        customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
    ) -> bool:
        """고객 프로필 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO customer_profiles (customer_id, email, name)
                    VALUES (?, ?, ?)
                """, (customer_id, email, name))
                self._conn.commit()
                log.info("[DB] 고객 프로필 생성: customer_id=%s", customer_id)
                return True
            except sqlite3.IntegrityError:
                return False

    def get_customer_profile(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """고객 프로필 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT customer_id, email, name, status, created_at, updated_at,
                       last_login_at, total_analyses
                FROM customer_profiles WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": row[0],
                    "email": row[1],
                    "name": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                    "last_login_at": row[6],
                    "total_analyses": row[7],
                }
            return None

    def update_customer_status(self, customer_id: str, status: str) -> bool:
        """고객 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE customer_profiles
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE customer_id = ?
            """, (status, customer_id))
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 고객 상태 업데이트: customer_id=%s, status=%s", customer_id, status)
            return updated

    def list_customers(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """고객 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT customer_id, email, name, status, created_at, updated_at,
                       last_login_at, total_analyses
                FROM customer_profiles
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "customer_id": row[0],
                    "email": row[1],
                    "name": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                    "last_login_at": row[6],
                    "total_analyses": row[7],
                }
                for row in rows
            ]

    def delete_customer_profile(self, customer_id: str) -> bool:
        """고객 프로필 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM customer_profiles WHERE customer_id = ?
            """, (customer_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 고객 프로필 삭제: customer_id=%s", customer_id)
            return deleted

    # ── 제품 관리 관련 메서드 ─────────────────────────────────────────────────

    def create_product(
        self,
        product_id: str,
        product_name: str,
        category: str,
        key_ingredients: List[str],
        efficacy: str,
        target_skin_types: Optional[List[str]] = None,
        target_concerns: Optional[List[str]] = None,
    ) -> bool:
        """제품 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO products
                    (product_id, product_name, category, key_ingredients, efficacy,
                     target_skin_types, target_concerns)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_id,
                    product_name,
                    category,
                    json.dumps(key_ingredients, ensure_ascii=False),
                    efficacy,
                    json.dumps(target_skin_types, ensure_ascii=False) if target_skin_types else None,
                    json.dumps(target_concerns, ensure_ascii=False) if target_concerns else None,
                ))
                self._conn.commit()
                log.info("[DB] 제품 생성: product_id=%s", product_id)
                return True
            except sqlite3.IntegrityError:
                return False

    def update_product(
        self,
        product_id: str,
        product_name: Optional[str] = None,
        category: Optional[str] = None,
        key_ingredients: Optional[List[str]] = None,
        efficacy: Optional[str] = None,
    ) -> bool:
        """제품 정보 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            updates = []
            params = []
            
            if product_name:
                updates.append("product_name = ?")
                params.append(product_name)
            if category:
                updates.append("category = ?")
                params.append(category)
            if key_ingredients:
                updates.append("key_ingredients = ?")
                params.append(json.dumps(key_ingredients, ensure_ascii=False))
            if efficacy:
                updates.append("efficacy = ?")
                params.append(efficacy)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(product_id)
            
            query = f"UPDATE products SET {', '.join(updates)} WHERE product_id = ?"
            cursor.execute(query, params)
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 제품 업데이트: product_id=%s", product_id)
            return updated

    def delete_product(self, product_id: str) -> bool:
        """제품 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM products WHERE product_id = ?
            """, (product_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 제품 삭제: product_id=%s", product_id)
            return deleted

    def list_products(
        self,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """제품 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT product_id, product_name, category, key_ingredients, efficacy,
                       target_skin_types, target_concerns, created_at, updated_at
                FROM products
                WHERE 1=1
            """
            params = []
            if category:
                query += " AND category = ?"
                params.append(category)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "product_id": row[0],
                    "product_name": row[1],
                    "category": row[2],
                    "key_ingredients": json.loads(row[3]) if row[3] else [],
                    "efficacy": row[4],
                    "target_skin_types": json.loads(row[5]) if row[5] else [],
                    "target_concerns": json.loads(row[6]) if row[6] else [],
                    "created_at": row[7],
                    "updated_at": row[8],
                }
                for row in rows
            ]

    # ── 사용자 세션 관련 메서드 ─────────────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        customer_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """사용자 세션 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_sessions (id, customer_id, ip_address, user_agent)
                VALUES (?, ?, ?, ?)
            """, (session_id, customer_id, ip_address, user_agent))
            self._conn.commit()
            return True

    def update_session_activity(self, session_id: str) -> bool:
        """세션 활동 시간 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE user_sessions
                SET last_activity_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (session_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def end_session(self, session_id: str) -> bool:
        """세션 종료"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE user_sessions
                SET is_active = 0
                WHERE id = ?
            """, (session_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def get_active_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """활성 세션 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, ip_address, user_agent, started_at, last_activity_at
                FROM user_sessions
                WHERE is_active = 1
                ORDER BY last_activity_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "session_id": row[0],
                    "customer_id": row[1],
                    "ip_address": row[2],
                    "user_agent": row[3],
                    "started_at": row[4],
                    "last_activity_at": row[5],
                }
                for row in rows
            ]

    # ── 이상 활동 관련 메서드 ─────────────────────────────────────────────────

    def create_anomaly(
        self,
        anomaly_type: str,
        customer_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        description: Optional[str] = None,
        severity: str = "medium",
    ) -> str:
        """이상 활동 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            import uuid
            anomaly_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO security_anomalies
                (id, anomaly_type, customer_id, ip_address, description, severity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (anomaly_id, anomaly_type, customer_id, ip_address, description, severity))
            self._conn.commit()
            log.warning("[DB] 이상 활동 탐지: type=%s, customer_id=%s, ip=%s", 
                      anomaly_type, customer_id, ip_address)
            return anomaly_id

    def get_anomalies(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """이상 활동 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, anomaly_type, customer_id, ip_address, description,
                       severity, detected_at, resolved_at, status
                FROM security_anomalies
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            query += " ORDER BY detected_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "anomaly_type": row[1],
                    "customer_id": row[2],
                    "ip_address": row[3],
                    "description": row[4],
                    "severity": row[5],
                    "detected_at": row[6],
                    "resolved_at": row[7],
                    "status": row[8],
                }
                for row in rows
            ]

    def resolve_anomaly(self, anomaly_id: str) -> bool:
        """이상 활동 해결"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE security_anomalies
                SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (anomaly_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    # ── 사용자 역할 관련 메서드 ─────────────────────────────────────────────

    def set_user_role(
        self,
        customer_id: str,
        role: str,
        granted_by: Optional[str] = None,
    ) -> bool:
        """사용자 역할 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO user_roles (customer_id, role, granted_by)
                VALUES (?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    role = ?, granted_by = ?, granted_at = CURRENT_TIMESTAMP
            """, (customer_id, role, granted_by, role, granted_by))
            self._conn.commit()
            log.info("[DB] 사용자 역할 설정: customer_id=%s, role=%s", customer_id, role)
            return True

    def get_user_role(self, customer_id: str) -> Optional[str]:
        """사용자 역할 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT role FROM user_roles WHERE customer_id = ?
            """, (customer_id,))
            row = cursor.fetchone()
            return row[0] if row else "customer"

    def list_users_by_role(self, role: str, limit: int = 100) -> List[Dict[str, Any]]:
        """역할별 사용자 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT customer_id, role, granted_at, granted_by
                FROM user_roles
                WHERE role = ?
                ORDER BY granted_at DESC
                LIMIT ?
            """, (role, limit))
            rows = cursor.fetchall()
            return [
                {
                    "customer_id": row[0],
                    "role": row[1],
                    "granted_at": row[2],
                    "granted_by": row[3],
                }
                for row in rows
            ]

    # ── 차단된 IP 관련 메서드 ───────────────────────────────────────────────

    def block_ip(
        self,
        ip_address: str,
        reason: Optional[str] = None,
        blocked_by: Optional[str] = None,
        expires_in_hours: Optional[int] = None,
        is_permanent: bool = False,
    ) -> bool:
        """IP 차단"""
        with self._lock:
            cursor = self._conn.cursor()
            expires_at = None
            if expires_in_hours and not is_permanent:
                expires_at = (datetime.now() + timedelta(hours=expires_in_hours)).isoformat()
            
            cursor.execute("""
                INSERT INTO blocked_ips (ip_address, reason, blocked_by, expires_at, is_permanent)
                VALUES (?, ?, ?, ?, ?)
            """, (ip_address, reason, blocked_by, expires_at, 1 if is_permanent else 0))
            self._conn.commit()
            log.warning("[DB] IP 차단: ip=%s, reason=%s", ip_address, reason)
            return True

    def unblock_ip(self, ip_address: str) -> bool:
        """IP 차단 해제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM blocked_ips WHERE ip_address = ?
            """, (ip_address,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] IP 차단 해제: ip=%s", ip_address)
            return deleted

    def is_ip_blocked(self, ip_address: str) -> bool:
        """IP 차단 여부 확인"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM blocked_ips
                WHERE ip_address = ? AND (is_permanent = 1 OR expires_at > CURRENT_TIMESTAMP)
            """, (ip_address,))
            return cursor.fetchone()[0] > 0

    def get_blocked_ips(self, limit: int = 100) -> List[Dict[str, Any]]:
        """차단된 IP 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT ip_address, blocked_at, blocked_by, reason, expires_at, is_permanent
                FROM blocked_ips
                WHERE is_permanent = 1 OR expires_at > CURRENT_TIMESTAMP
                ORDER BY blocked_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "ip_address": row[0],
                    "blocked_at": row[1],
                    "blocked_by": row[2],
                    "reason": row[3],
                    "expires_at": row[4],
                    "is_permanent": bool(row[5]),
                }
                for row in rows
            ]

    # ── 일일 통계 관련 메서드 ───────────────────────────────────────────────

    def record_daily_stats(
        self,
        date: str,
        total_analyses: int,
        unique_customers: int,
        successful_analyses: int,
        failed_analyses: int,
        avg_score: Optional[float] = None,
        total_revenue: float = 0.0,
    ) -> bool:
        """일일 통계 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO daily_stats
                (date, total_analyses, unique_customers, successful_analyses,
                 failed_analyses, avg_score, total_revenue)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_analyses = ?, unique_customers = ?,
                    successful_analyses = ?, failed_analyses = ?,
                    avg_score = ?, total_revenue = ?
            """, (
                date, total_analyses, unique_customers, successful_analyses,
                failed_analyses, avg_score, total_revenue,
                total_analyses, unique_customers, successful_analyses,
                failed_analyses, avg_score, total_revenue,
            ))
            self._conn.commit()
            return True

    def get_daily_stats(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """일일 통계 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT date, total_analyses, unique_customers, successful_analyses,
                       failed_analyses, avg_score, total_revenue
                FROM daily_stats
                WHERE 1=1
            """
            params = []
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            query += " ORDER BY date DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "date": row[0],
                    "total_analyses": row[1],
                    "unique_customers": row[2],
                    "successful_analyses": row[3],
                    "failed_analyses": row[4],
                    "avg_score": row[5],
                    "total_revenue": row[6],
                }
                for row in rows
            ]

    # ── 제품 피드백 ───────────────────────────────────────────────────────────

    def create_product_feedback(
        self,
        feedback_id: str,
        order_id: str,
        customer_id: str,
        product_id: str,
        rating: int,
        comment: Optional[str] = None,
        would_repurchase: Optional[bool] = None,
    ) -> bool:
        """제품 피드백 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO product_feedback 
                (feedback_id, order_id, customer_id, product_id, rating, comment, would_repurchase)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, order_id, customer_id, product_id, rating, comment, 1 if would_repurchase else 0 if would_repurchase is not None else None),
            )
            self._conn.commit()
            log.info("[DB] 제품 피드백 생성: feedback_id=%s, product_id=%s, rating=%s", feedback_id, product_id, rating)
            return True

    def get_product_feedback(self, product_id: str, limit: int = 20) -> List[Dict]:
        """제품별 피드백 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT feedback_id, order_id, customer_id, product_id, rating, comment, would_repurchase, created_at
                FROM product_feedback
                WHERE product_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (product_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    def get_customer_feedback(self, customer_id: str, limit: int = 20) -> List[Dict]:
        """고객별 피드백 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT feedback_id, order_id, customer_id, product_id, rating, comment, would_repurchase, created_at
                FROM product_feedback
                WHERE customer_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    def get_product_average_rating(self, product_id: str) -> float:
        """제품 평균 평점 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT AVG(rating) as avg_rating
                FROM product_feedback
                WHERE product_id = ?
                """,
                (product_id,),
            )
            row = cursor.fetchone()
            return round(row[0], 1) if row and row[0] else 0.0

    # ── 피부 일기 ─────────────────────────────────────────────────────────────

    def create_skin_diary_entry(
        self,
        entry_id: str,
        customer_id: str,
        analysis_id: Optional[int] = None,
        image_url: Optional[str] = None,
        overall_score: Optional[float] = None,
        measurement_scores: Optional[Dict] = None,
        notes: Optional[str] = None,
        mood: Optional[str] = None,
        weather: Optional[str] = None,
    ) -> bool:
        """피부 일기 엔트리 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO skin_diary 
                (entry_id, customer_id, analysis_id, image_url, overall_score, measurement_scores, notes, mood, weather)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entry_id, customer_id, analysis_id, image_url, overall_score, json.dumps(measurement_scores) if measurement_scores else None, notes, mood, weather),
            )
            self._conn.commit()
            log.info("[DB] 피부 일기 엔트리 생성: entry_id=%s, customer_id=%s", entry_id, customer_id)
            return True

    def get_skin_diary_entries(self, customer_id: str, limit: int = 30) -> List[Dict]:
        """고객 피부 일기 엔트리 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT entry_id, customer_id, analysis_id, image_url, overall_score, measurement_scores, notes, mood, weather, created_at
                FROM skin_diary
                WHERE customer_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 고객 목표 ─────────────────────────────────────────────────────────────

    def create_customer_goal(
        self,
        goal_id: str,
        customer_id: str,
        goal_type: str,
        target_value: float,
        start_date: str,
        end_date: str,
    ) -> bool:
        """고객 목표 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_goals 
                (goal_id, customer_id, goal_type, target_value, current_value, start_date, end_date)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (goal_id, customer_id, goal_type, target_value, start_date, end_date),
            )
            self._conn.commit()
            log.info("[DB] 고객 목표 생성: goal_id=%s, customer_id=%s, type=%s", goal_id, customer_id, goal_type)
            return True

    def update_customer_goal_progress(self, goal_id: str, current_value: float) -> bool:
        """고객 목표 진행률 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE customer_goals
                SET current_value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE goal_id = ?
                """,
                (current_value, goal_id),
            )
            self._conn.commit()
            log.info("[DB] 고객 목표 진행률 업데이트: goal_id=%s, value=%s", goal_id, current_value)
            return True

    def get_customer_goals(self, customer_id: str) -> List[Dict]:
        """고객 목표 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT goal_id, customer_id, goal_type, target_value, current_value, start_date, end_date, status, created_at
                FROM customer_goals
                WHERE customer_id = ?
                ORDER BY created_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 업적 ─────────────────────────────────────────────────────────────────

    def create_achievement(
        self,
        achievement_id: str,
        name: str,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        requirement_type: Optional[str] = None,
        requirement_value: Optional[float] = None,
        reward_points: int = 0,
    ) -> bool:
        """업적 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO achievements 
                (achievement_id, name, description, icon, requirement_type, requirement_value, reward_points)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (achievement_id, name, description, icon, requirement_type, requirement_value, reward_points),
            )
            self._conn.commit()
            log.info("[DB] 업적 생성: achievement_id=%s, name=%s", achievement_id, name)
            return True

    def earn_achievement(self, customer_id: str, achievement_id: str) -> bool:
        """고객 업적 획득"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_achievements (customer_id, achievement_id)
                VALUES (?, ?)
                """,
                (customer_id, achievement_id),
            )
            self._conn.commit()
            log.info("[DB] 고객 업적 획득: customer_id=%s, achievement_id=%s", customer_id, achievement_id)
            return True

    def get_customer_achievements(self, customer_id: str) -> List[Dict]:
        """고객 업적 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT ca.customer_id, ca.achievement_id, ca.earned_at, a.name, a.description, a.icon, a.reward_points
                FROM customer_achievements ca
                JOIN achievements a ON ca.achievement_id = a.achievement_id
                WHERE ca.customer_id = ?
                ORDER BY ca.earned_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 제품 구독 ─────────────────────────────────────────────────────────────

    def create_product_subscription(
        self,
        subscription_id: str,
        customer_id: str,
        product_id: str,
        frequency: str,
        next_delivery_date: str,
    ) -> bool:
        """제품 구독 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO product_subscriptions 
                (subscription_id, customer_id, product_id, frequency, next_delivery_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (subscription_id, customer_id, product_id, frequency, next_delivery_date),
            )
            self._conn.commit()
            log.info("[DB] 제품 구독 생성: subscription_id=%s, customer_id=%s, product_id=%s", subscription_id, customer_id, product_id)
            return True

    def get_customer_subscriptions(self, customer_id: str) -> List[Dict]:
        """고객 구독 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT subscription_id, customer_id, product_id, frequency, next_delivery_date, status, created_at
                FROM product_subscriptions
                WHERE customer_id = ? AND status = 'active'
                ORDER BY created_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 챌린지 ───────────────────────────────────────────────────────────────

    def create_challenge(
        self,
        challenge_id: str,
        name: str,
        description: Optional[str] = None,
        duration_days: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        reward_points: int = 0,
    ) -> bool:
        """챌린지 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO challenges 
                (challenge_id, name, description, duration_days, start_date, end_date, reward_points)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (challenge_id, name, description, duration_days, start_date, end_date, reward_points),
            )
            self._conn.commit()
            log.info("[DB] 챌린지 생성: challenge_id=%s, name=%s", challenge_id, name)
            return True

    def join_challenge(self, customer_id: str, challenge_id: str, start_date: str, end_date: str) -> bool:
        """챌린지 참여"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO customer_challenges (customer_id, challenge_id, start_date, end_date)
                VALUES (?, ?, ?, ?)
                """,
                (customer_id, challenge_id, start_date, end_date),
            )
            self._conn.commit()
            log.info("[DB] 챌린지 참여: customer_id=%s, challenge_id=%s", customer_id, challenge_id)
            return True

    def update_challenge_progress(self, customer_id: str, challenge_id: str, progress: float) -> bool:
        """챌린지 진행률 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE customer_challenges
                SET progress = ?
                WHERE customer_id = ? AND challenge_id = ?
                """,
                (progress, customer_id, challenge_id),
            )
            self._conn.commit()
            log.info("[DB] 챌린지 진행률 업데이트: customer_id=%s, challenge_id=%s, progress=%s", customer_id, challenge_id, progress)
            return True

    def get_customer_challenges(self, customer_id: str) -> List[Dict]:
        """고객 챌린지 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT cc.customer_id, cc.challenge_id, cc.start_date, cc.end_date, cc.progress, cc.status, cc.created_at,
                       c.name, c.description, c.reward_points
                FROM customer_challenges cc
                JOIN challenges c ON cc.challenge_id = c.challenge_id
                WHERE cc.customer_id = ?
                ORDER BY cc.created_at DESC
                """,
                (customer_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 웹훅 관련 메서드 ───────────────────────────────────────────────────────

    def create_webhook(
        self,
        webhook_id: str,
        customer_id: str,
        url: str,
        events: List[str],
        secret_key: Optional[str] = None,
    ) -> bool:
        """웹훅 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO webhooks (id, customer_id, url, events, secret_key)
                    VALUES (?, ?, ?, ?, ?)
                """, (webhook_id, customer_id, url, json.dumps(events, ensure_ascii=False), secret_key))
                self._conn.commit()
                log.info("[DB] 웹훅 생성: webhook_id=%s, customer_id=%s", webhook_id, customer_id)
                return True
            except sqlite3.IntegrityError:
                return False

    def get_webhooks(self, customer_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """웹훅 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, customer_id, url, events, secret_key, is_active, created_at, updated_at
                FROM webhooks
                WHERE customer_id = ?
            """
            params = [customer_id]
            if active_only:
                query += " AND is_active = 1"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "customer_id": row[1],
                    "url": row[2],
                    "events": json.loads(row[3]) if row[3] else [],
                    "secret_key": row[4],
                    "is_active": bool(row[5]),
                    "created_at": row[6],
                    "updated_at": row[7],
                }
                for row in rows
            ]

    def update_webhook(
        self,
        webhook_id: str,
        url: Optional[str] = None,
        events: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """웹훅 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            updates = []
            params = []
            
            if url:
                updates.append("url = ?")
                params.append(url)
            if events:
                updates.append("events = ?")
                params.append(json.dumps(events, ensure_ascii=False))
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(1 if is_active else 0)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(webhook_id)
            
            query = f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 웹훅 업데이트: webhook_id=%s", webhook_id)
            return updated

    # ── 이미지 업로드 관리 ───────────────────────────────────────────────────────

    def create_image_upload(
        self,
        customer_id: str,
        upload_id: str,
        original_filename: str,
        file_path: str,
        file_size: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        rotation_angle: int = 0,
    ) -> bool:
        """이미지 업로드 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO image_uploads 
                    (customer_id, upload_id, original_filename, file_path, file_size, width, height, rotation_angle)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (customer_id, upload_id, original_filename, file_path, file_size, width, height, rotation_angle),
                )
                self._conn.commit()
                log.info("[DB] 이미지 업로드 생성: upload_id=%s", upload_id)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] 이미지 업로드 중복: upload_id=%s", upload_id)
                return False

    def update_image_upload_status(
        self,
        upload_id: str,
        upload_status: str,
        processed_at: Optional[datetime] = None,
    ) -> bool:
        """이미지 업로드 상태 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE image_uploads 
                SET upload_status = ?, processed_at = COALESCE(?, processed_at)
                WHERE upload_id = ?
                """,
                (upload_status, processed_at, upload_id),
            )
            self._conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                log.info("[DB] 이미지 업로드 상태 업데이트: upload_id=%s, status=%s", upload_id, upload_status)
            return updated

    def get_image_uploads(
        self,
        customer_id: Optional[str] = None,
        upload_status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """이미지 업로드 목록 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = "SELECT * FROM image_uploads WHERE 1=1"
            params = []
            
            if customer_id:
                query += " AND customer_id = ?"
                params.append(customer_id)
            if upload_status:
                query += " AND upload_status = ?"
                params.append(upload_status)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 푸시 알림 선호도 ───────────────────────────────────────────────────────

    def set_push_preferences(
        self,
        customer_id: str,
        push_enabled: bool = True,
        analysis_complete_enabled: bool = True,
        promotion_enabled: bool = False,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
        device_token: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> bool:
        """푸시 알림 선호도 설정"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO push_preferences 
                    (customer_id, push_enabled, analysis_complete_enabled, promotion_enabled, quiet_hours_start, quiet_hours_end, device_token, platform)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(customer_id) DO UPDATE SET
                        push_enabled = excluded.push_enabled,
                        analysis_complete_enabled = excluded.analysis_complete_enabled,
                        promotion_enabled = excluded.promotion_enabled,
                        quiet_hours_start = excluded.quiet_hours_start,
                        quiet_hours_end = excluded.quiet_hours_end,
                        device_token = excluded.device_token,
                        platform = excluded.platform,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (customer_id, push_enabled, analysis_complete_enabled, promotion_enabled, quiet_hours_start, quiet_hours_end, device_token, platform),
                )
                self._conn.commit()
                log.info("[DB] 푸시 알림 선호도 설정: customer_id=%s", customer_id)
                return True
            except Exception as e:
                log.error("[DB] 푸시 알림 선호도 설정 실패: %s", e)
                return False

    def get_push_preferences(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """푸시 알림 선호도 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM push_preferences WHERE customer_id = ?",
                (customer_id,),
            )
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

    # ── A/B 테스트 관리 ───────────────────────────────────────────────────────

    def create_ab_test(
        self,
        test_name: str,
        variant_a_name: str,
        variant_b_name: str,
        description: Optional[str] = None,
        traffic_split: float = 0.5,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> bool:
        """A/B 테스트 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO ab_tests 
                    (test_name, description, variant_a_name, variant_b_name, traffic_split, start_date, end_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (test_name, description, variant_a_name, variant_b_name, traffic_split, start_date, end_date),
                )
                self._conn.commit()
                log.info("[DB] A/B 테스트 생성: test_name=%s", test_name)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] A/B 테스트 중복: test_name=%s", test_name)
                return False

    def assign_user_to_variant(
        self,
        test_id: int,
        customer_id: str,
        variant: str,
    ) -> bool:
        """사용자를 A/B 테스트 변형에 할당"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO ab_test_assignments (test_id, customer_id, variant)
                    VALUES (?, ?, ?)
                    """,
                    (test_id, customer_id, variant),
                )
                self._conn.commit()
                log.info("[DB] A/B 테스트 할당: test_id=%s, customer_id=%s, variant=%s", test_id, customer_id, variant)
                return True
            except sqlite3.IntegrityError:
                log.warning("[DB] A/B 테스트 할당 중복: test_id=%s, customer_id=%s", test_id, customer_id)
                return False

    def get_user_variant(self, test_id: int, customer_id: str) -> Optional[str]:
        """사용자의 A/B 테스트 변형 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT variant FROM ab_test_assignments WHERE test_id = ? AND customer_id = ?",
                (test_id, customer_id),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def record_ab_test_result(
        self,
        test_id: int,
        variant: str,
        metric_name: str,
        metric_value: Optional[float] = None,
        event_count: int = 1,
    ) -> bool:
        """A/B 테스트 결과 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO ab_test_results (test_id, variant, metric_name, metric_value, event_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (test_id, variant, metric_name, metric_value, event_count),
            )
            self._conn.commit()
            log.info("[DB] A/B 테스트 결과 기록: test_id=%s, variant=%s, metric=%s", test_id, variant, metric_name)
            return True

    def get_ab_test_results(self, test_id: int) -> List[Dict[str, Any]]:
        """A/B 테스트 결과 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT variant, metric_name, AVG(metric_value) as avg_value, SUM(event_count) as total_events
                FROM ab_test_results
                WHERE test_id = ?
                GROUP BY variant, metric_name
                """,
                (test_id,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 모니터링 메트릭 ───────────────────────────────────────────────────────

    def record_metric(
        self,
        metric_name: str,
        metric_value: float,
        metric_unit: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        """모니터링 메트릭 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO monitoring_metrics (metric_name, metric_value, metric_unit, tags)
                VALUES (?, ?, ?, ?)
                """,
                (metric_name, metric_value, metric_unit, json.dumps(tags) if tags else None),
            )
            self._conn.commit()
            return True

    def get_metrics(
        self,
        metric_name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """모니터링 메트릭 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = "SELECT * FROM monitoring_metrics WHERE 1=1"
            params = []
            
            if metric_name:
                query += " AND metric_name = ?"
                params.append(metric_name)
            if since:
                query += " AND recorded_at >= ?"
                params.append(since)
            
            query += " ORDER BY recorded_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    # ── 분석 추이 ───────────────────────────────────────────────────────────

    def record_analysis_trend(
        self,
        customer_id: str,
        analysis_id: int,
        overall_score_original: float,
        overall_score_restored: float,
        measurement_scores: Dict[str, float],
    ) -> bool:
        """분석 추이 기록"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO analysis_trends 
                (customer_id, analysis_id, overall_score_original, overall_score_restored, measurement_scores)
                VALUES (?, ?, ?, ?, ?)
                """,
                (customer_id, analysis_id, overall_score_original, overall_score_restored, json.dumps(measurement_scores)),
            )
            self._conn.commit()
            log.info("[DB] 분석 추이 기록: customer_id=%s, analysis_id=%s", customer_id, analysis_id)
            return True

    def get_analysis_trends(
        self,
        customer_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """분석 추이 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT * FROM analysis_trends
                WHERE customer_id = ?
                ORDER BY recorded_at ASC
                LIMIT ?
                """,
                (customer_id, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    def delete_webhook(self, webhook_id: str) -> bool:
        """웹훅 삭제"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                DELETE FROM webhooks WHERE id = ?
            """, (webhook_id,))
            deleted = cursor.rowcount > 0
            self._conn.commit()
            if deleted:
                log.info("[DB] 웹훅 삭제: webhook_id=%s", webhook_id)
            return deleted

    # ── 외부 동기화 로그 관련 메서드 ───────────────────────────────────────────

    def create_sync_log(
        self,
        sync_type: str,
        direction: str,
        source_system: Optional[str] = None,
        target_system: Optional[str] = None,
    ) -> str:
        """동기화 로그 생성"""
        with self._lock:
            cursor = self._conn.cursor()
            import uuid
            log_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO external_sync_logs (id, sync_type, direction, source_system, target_system)
                VALUES (?, ?, ?, ?, ?)
            """, (log_id, sync_type, direction, source_system, target_system))
            self._conn.commit()
            log.info("[DB] 동기화 로그 생성: log_id=%s, type=%s", log_id, sync_type)
            return log_id

    def update_sync_log(
        self,
        log_id: str,
        status: str,
        records_count: int = 0,
        error_message: Optional[str] = None,
    ) -> bool:
        """동기화 로그 업데이트"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE external_sync_logs
                SET status = ?, records_count = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, records_count, error_message, log_id))
            self._conn.commit()
            return cursor.rowcount > 0

    def get_sync_logs(
        self,
        sync_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """동기화 로그 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            query = """
                SELECT id, sync_type, direction, status, source_system, target_system,
                       records_count, error_message, started_at, completed_at
                FROM external_sync_logs
                WHERE 1=1
            """
            params = []
            if sync_type:
                query += " AND sync_type = ?"
                params.append(sync_type)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "sync_type": row[1],
                    "direction": row[2],
                    "status": row[3],
                    "source_system": row[4],
                    "target_system": row[5],
                    "records_count": row[6],
                    "error_message": row[7],
                    "started_at": row[8],
                    "completed_at": row[9],
                }
                for row in rows
            ]

    # ── OAuth 관련 메서드 ─────────────────────────────────────────────────────

    def create_oauth_provider(
        self,
        provider_id: str,
        provider_name: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: Optional[List[str]] = None,
    ) -> bool:
        """OAuth 제공자 등록"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO oauth_providers (id, provider_name, client_id, client_secret, redirect_uri, scopes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    provider_id,
                    provider_name,
                    client_id,
                    client_secret,
                    redirect_uri,
                    json.dumps(scopes, ensure_ascii=False) if scopes else None,
                ))
                self._conn.commit()
                log.info("[DB] OAuth 제공자 등록: provider_name=%s", provider_name)
                return True
            except sqlite3.IntegrityError:
                return False

    def get_oauth_provider(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """OAuth 제공자 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, provider_name, client_id, client_secret, redirect_uri, scopes, is_active, created_at
                FROM oauth_providers
                WHERE provider_name = ? AND is_active = 1
            """, (provider_name,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "provider_name": row[1],
                    "client_id": row[2],
                    "client_secret": row[3],
                    "redirect_uri": row[4],
                    "scopes": json.loads(row[5]) if row[5] else [],
                    "is_active": bool(row[6]),
                    "created_at": row[7],
                }
            return None

    def save_oauth_token(
        self,
        token_id: str,
        customer_id: str,
        provider_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> bool:
        """OAuth 토큰 저장"""
        with self._lock:
            cursor = self._conn.cursor()
            expires_at = None
            if expires_in:
                from datetime import datetime, timedelta
                expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            
            cursor.execute("""
                INSERT INTO oauth_tokens (id, customer_id, provider_id, access_token, refresh_token, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (token_id, customer_id, provider_id, access_token, refresh_token, expires_at))
            self._conn.commit()
            log.info("[DB] OAuth 토큰 저장: customer_id=%s, provider_id=%s", customer_id, provider_id)
            return True

    def get_oauth_token(self, customer_id: str, provider_id: str) -> Optional[Dict[str, Any]]:
        """OAuth 토큰 조회"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT id, customer_id, provider_id, access_token, refresh_token, expires_at, created_at
                FROM oauth_tokens
                WHERE customer_id = ? AND provider_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (customer_id, provider_id))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "customer_id": row[1],
                    "provider_id": row[2],
                    "access_token": row[3],
                    "refresh_token": row[4],
                    "expires_at": row[5],
                    "created_at": row[6],
                }
            return None
