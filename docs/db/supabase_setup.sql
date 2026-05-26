-- ============================================================
-- COTELEAF AI Skin v3 — Supabase 초기화 SQL
-- Supabase 프로젝트 > SQL Editor 에서 실행
-- ============================================================

-- 1. Storage 버킷 생성
-- (Supabase Dashboard > Storage > New bucket 에서 직접 생성하거나 아래 SQL 사용)
INSERT INTO storage.buckets (id, name, public)
VALUES ('skin-images', 'skin-images', false)
ON CONFLICT (id) DO NOTHING;

-- 2. 분석 결과 테이블
CREATE TABLE IF NOT EXISTS skin_analyses (
    id                      BIGSERIAL PRIMARY KEY,
    local_id                INTEGER,                   -- 로컬 SQLite analyses.id
    customer_id             TEXT,
    original_filename       TEXT,
    storage_original        TEXT,                      -- Storage 내 경로
    storage_restored        TEXT,                      -- Storage 내 경로
    overall_score_original  FLOAT,
    overall_score_restored  FLOAT,
    json_result             JSONB NOT NULL,
    input_json              JSONB,                     -- 스마트폰에서 보내온 입력 JSON (survey + client_meta)
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- 기존 테이블에 input_json 컬럼 추가 (마이그레이션)
ALTER TABLE skin_analyses ADD COLUMN IF NOT EXISTS input_json JSONB;

-- 피부 타입 감지 관련 컬럼 추가 (마이그레이션)
ALTER TABLE skin_analyses ADD COLUMN IF NOT EXISTS detected_skin_types JSONB;
ALTER TABLE skin_analyses ADD COLUMN IF NOT EXISTS skin_type_confidence FLOAT;
ALTER TABLE skin_analyses ADD COLUMN IF NOT EXISTS skin_type_features JSONB;
ALTER TABLE skin_analyses ADD COLUMN IF NOT EXISTS skin_type_source TEXT DEFAULT 'auto';

-- 피부 타입 검증 테이블
CREATE TABLE IF NOT EXISTS skin_type_validations (
    id                      BIGSERIAL PRIMARY KEY,
    analysis_id             INTEGER NOT NULL,
    survey_skin_types       JSONB,
    detected_skin_types     JSONB,
    user_confirmed_skin_types JSONB,
    is_correct              BOOLEAN,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_sa_customer  ON skin_analyses(customer_id);
CREATE INDEX IF NOT EXISTS idx_sa_created   ON skin_analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sa_local_id  ON skin_analyses(local_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sa_local_unique ON skin_analyses(local_id);
CREATE INDEX IF NOT EXISTS idx_stv_analysis_id ON skin_type_validations(analysis_id);
CREATE INDEX IF NOT EXISTS idx_stv_created ON skin_type_validations(created_at DESC);

-- 사용자 설정 테이블 (다국어 지원)
CREATE TABLE IF NOT EXISTS user_preferences (
    id                      BIGSERIAL PRIMARY KEY,
    customer_id             TEXT UNIQUE NOT NULL,
    language                TEXT DEFAULT 'ko',
    timezone                TEXT DEFAULT 'Asia/Seoul',
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_up_customer ON user_preferences(customer_id);

-- 4. Storage 접근 정책 (service_role 키 사용 시 불필요, anon 키 사용 시 필요)
-- 아래는 인증된 사용자만 업로드/읽기 허용하는 예시:

CREATE POLICY "authenticated upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'skin-images');

CREATE POLICY "authenticated read" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'skin-images');

-- service_role 키는 정책 우회이므로 서버 측에서는 위 정책 불필요.

-- 5. 이미지 서명 URL 생성 예시 (Python 서버에서 사용)
-- supabase_client.storage.from_("skin-images").create_signed_url(path, expires_in=3600)
