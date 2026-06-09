"""공유 커넥션·락·스키마·암복호화/동기화 헬퍼 베이스."""
import logging
import sqlite3
import json
import threading
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone  # [FIX] timezone 추가(원본 누락)
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.utils.config import load_config as _load_config

log = logging.getLogger(__name__)


class _BaseRepository:
    """공유 SQLite 커넥션(check_same_thread=False)+Lock+WAL, 스키마, 내부 헬퍼."""

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
                    name TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    address TEXT NOT NULL,
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

        # 버전 20: 주문 테이블
        if current_version < 20:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending_payment',
                    total_amount REAL NOT NULL,
                    payment_method TEXT,
                    payment_status TEXT DEFAULT 'pending',
                    shipping_status TEXT DEFAULT 'pending',
                    shipping_address TEXT,
                    barcode_number TEXT,
                    recommendation_source TEXT,
                    analysis_job_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customer_profiles(customer_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    product_name TEXT,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    subtotal REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_customer
                ON orders(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status
                ON orders(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_order_items_order
                ON order_items(order_id)
            """)
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (20)")
            self._conn.commit()
            log.info("[DB] 주문 테이블 생성 완료 (버전 20)")

        # 버전 21: A/B 테스트 관리 테이블
        if current_version < 21:
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
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (21)")
            self._conn.commit()
            log.info("[DB] A/B 테스트 테이블 생성 완료 (버전 21)")

        # 버전 22: A/B 테스트 사용자 분배 테이블
        if current_version < 22:
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
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (22)")
            self._conn.commit()
            log.info("[DB] A/B 테스트 분배 테이블 생성 완료 (버전 22)")

        # 버전 23: A/B 테스트 결과 테이블
        if current_version < 23:
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
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (23)")
            self._conn.commit()
            log.info("[DB] A/B 테스트 결과 테이블 생성 완료 (버전 23)")

        # 버전 24: 모니터링 메트릭 테이블
        if current_version < 24:
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
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (24)")
            self._conn.commit()
            log.info("[DB] 모니터링 메트릭 테이블 생성 완료 (버전 24)")

        # 버전 25: 분석 추이 테이블
        if current_version < 25:
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
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (25)")
            self._conn.commit()
            log.info("[DB] 분석 추이 테이블 생성 완료 (버전 25)")

        # 제품 피드백 테이블 생성 (버전 26)
        if current_version < 26:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (26)")
            self._conn.commit()
            log.info("[DB] 제품 피드백 테이블 생성 완료 (버전 26)")

        # 피부 일기 테이블 생성 (버전 27)
        if current_version < 27:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (27)")
            self._conn.commit()
            log.info("[DB] 피부 일기 테이블 생성 완료 (버전 27)")

        # 고객 목표 테이블 생성 (버전 28)
        if current_version < 28:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (28)")
            self._conn.commit()
            log.info("[DB] 고객 목표 테이블 생성 완료 (버전 28)")

        # 업적 테이블 생성 (버전 29)
        if current_version < 29:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (29)")
            self._conn.commit()
            log.info("[DB] 업적 테이블 생성 완료 (버전 29)")

        # 고객 업적 테이블 생성 (버전 30)
        if current_version < 30:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (30)")
            self._conn.commit()
            log.info("[DB] 고객 업적 테이블 생성 완료 (버전 30)")

        # 제품 구독 테이블 생성 (버전 31)
        if current_version < 31:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (31)")
            self._conn.commit()
            log.info("[DB] 제품 구독 테이블 생성 완료 (버전 31)")

        # 챌린지 테이블 생성 (버전 32)
        if current_version < 32:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (32)")
            self._conn.commit()
            log.info("[DB] 챌린지 테이블 생성 완료 (버전 32)")

        # 고객 챌린지 참여 테이블 생성 (버전 33)
        if current_version < 33:
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
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (33)")
            self._conn.commit()
            log.info("[DB] 고객 챌린지 참여 테이블 생성 완료 (버전 33)")

        # [FIX P1] 사용자 테이블 생성 (버전 34)
        if current_version < 34:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'customer',
                    customer_id TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_username
                ON users(username)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_customer_id
                ON users(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_role
                ON users(role)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (34)")
            self._conn.commit()
            log.info("[DB] 사용자 테이블 생성 완료 (버전 34)")

        # [FIX] 리프레시 토큰 테이블 생성 (버전 35)
        if current_version < 35:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_revoked INTEGER DEFAULT 0,
                    FOREIGN KEY (customer_id) REFERENCES users(customer_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token
                ON refresh_tokens(token)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_customer_id
                ON refresh_tokens(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at
                ON refresh_tokens(expires_at)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (35)")
            self._conn.commit()
            log.info("[DB] 리프레시 토큰 테이블 생성 완료 (버전 35)")

        # [FIX] 장치 관리 테이블 생성 (버전 36)
        if current_version < 36:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    device_token TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    device_name TEXT,
                    os_version TEXT,
                    app_version TEXT,
                    is_active INTEGER DEFAULT 1,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES users(customer_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_customer_id
                ON devices(customer_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_devices_token
                ON devices(device_token)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (36)")
            self._conn.commit()
            log.info("[DB] 장치 관리 테이블 생성 완료 (버전 36)")

        # [FIX] 설문 데이터 테이블 생성 (버전 37)
        if current_version < 37:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS surveys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    survey_id TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    survey_data TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES users(customer_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_surveys_survey_id
                ON surveys(survey_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_surveys_customer_id
                ON surveys(customer_id)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (37)")
            self._conn.commit()
            log.info("[DB] 설문 데이터 테이블 생성 완료 (버전 37)")

        # [FIX] 비밀번호 리셋 토큰 테이블 생성 (버전 38)
        if current_version < 38:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_used INTEGER DEFAULT 0,
                    FOREIGN KEY (customer_id) REFERENCES users(customer_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token
                ON password_reset_tokens(token)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_customer_id
                ON password_reset_tokens(customer_id)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (38)")
            self._conn.commit()
            log.info("[DB] 비밀번호 리셋 토큰 테이블 생성 완료 (버전 38)")

        # PCR 검사 테이블 생성 (버전 39)
        if current_version < 39:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pcr_test_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    test_type TEXT NOT NULL,
                    requested_at TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'pending',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES users(customer_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pcr_test_requests_request_id
                ON pcr_test_requests(request_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pcr_test_requests_customer_id
                ON pcr_test_requests(customer_id)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pcr_test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    result_id TEXT UNIQUE NOT NULL,
                    request_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    test_data TEXT,
                    interpretation TEXT,
                    completed_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (request_id) REFERENCES pcr_test_requests(request_id),
                    FOREIGN KEY (customer_id) REFERENCES users(customer_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pcr_test_results_result_id
                ON pcr_test_results(result_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pcr_test_results_customer_id
                ON pcr_test_results(customer_id)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pcr_consultations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    consultation_id TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    scheduled_at TIMESTAMP NOT NULL,
                    notes TEXT,
                    status TEXT DEFAULT 'scheduled',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES users(customer_id),
                    FOREIGN KEY (request_id) REFERENCES pcr_test_requests(request_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pcr_consultations_consultation_id
                ON pcr_consultations(consultation_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pcr_consultations_customer_id
                ON pcr_consultations(customer_id)
            """)
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (38)")
            self._conn.commit()
            log.info("[DB] PCR 검사 테이블 생성 완료 (버전 38)")

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

        # ProductTable 생성 (맞춤형 화장품 성분 정보) - 버전 39 이전에 생성
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

        # 버전 39: 제품 재고 관리 테이블 추가
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0
        if current_version < 39:
            # products 테이블에 재고 관련 컬럼 추가
            if not self._column_exists(cursor, "products", "stock_quantity"):
                cursor.execute("ALTER TABLE products ADD COLUMN stock_quantity INTEGER DEFAULT 0")
            if not self._column_exists(cursor, "products", "price"):
                cursor.execute("ALTER TABLE products ADD COLUMN price REAL DEFAULT 0.0")
            if not self._column_exists(cursor, "products", "is_active"):
                cursor.execute("ALTER TABLE products ADD COLUMN is_active INTEGER DEFAULT 1")
            if not self._column_exists(cursor, "products", "target_prescription_items"):
                cursor.execute("ALTER TABLE products ADD COLUMN target_prescription_items TEXT")
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (39)")
            self._conn.commit()
            log.info("[DB] 제품 재고 관리 컬럼 추가 완료 (버전 39)")

        # 기성품 여부 컬럼 추가 (버전 40)
        if current_version < 40:
            if not self._column_exists(cursor, "products", "is_ready_made"):
                cursor.execute("ALTER TABLE products ADD COLUMN is_ready_made INTEGER DEFAULT 0")
            if not self._column_exists(cursor, "products", "target_prescription_items"):
                cursor.execute("ALTER TABLE products ADD COLUMN target_prescription_items TEXT")
            if not self._column_exists(cursor, "products", "description"):
                cursor.execute("ALTER TABLE products ADD COLUMN description TEXT")
            
            cursor.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (40)")
            self._conn.commit()
            log.info("[DB] 기성품 여부 컬럼 추가 완료 (버전 40)")

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


    def _encrypt_data(self, data: str) -> str:
        """데이터 암호화 (SHA-256 해싱)"""
        if not data:
            return ""
        return hashlib.sha256(data.encode()).hexdigest()


    def _encrypt_address(self, address: Dict[str, str]) -> str:
        """배송 주소 암호화"""
        if not address:
            return ""
        # 민감 정보 해싱
        address_str = json.dumps(address, sort_keys=True)
        return self._encrypt_data(address_str)

