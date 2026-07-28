-- =============================================================================
-- CIBIL Credit Coach — Supabase schema
--
-- Run this entire file in the Supabase SQL Editor:
--   https://app.supabase.com/project/_/sql
--
-- Creates 11 tables + indexes + RLS policies. Mirrors the SQLite schema in
-- app/models.py so the FastAPI pipeline can read either backend through the
-- same SQLAlchemy ORM (via app/database.py branching on DATABASE_URL).
--
-- Order matters for FKs. Customer tables come first; KB tables after.
-- =============================================================================


-- =============================================================================
-- 1. CUSTOMERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS customers (
    pan_card              VARCHAR(10)  PRIMARY KEY,
    customer_id           VARCHAR(50)  UNIQUE NOT NULL,
    first_name            VARCHAR(255) NOT NULL,
    dob_year              INTEGER      NOT NULL,
    income_bracket        VARCHAR(50)  NOT NULL,
    income_monthly_paise  BIGINT       NOT NULL,
    region                VARCHAR(10)  NOT NULL,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- 2. SCORES (1-to-1 with customers)
-- =============================================================================
CREATE TABLE IF NOT EXISTS scores (
    score_id              INTEGER      PRIMARY KEY,
    pan_card              VARCHAR(10)  UNIQUE NOT NULL REFERENCES customers(pan_card) ON DELETE CASCADE,
    score                 INTEGER      NOT NULL,
    band                  VARCHAR(50)  NOT NULL,
    score_as_of_date      DATE         NOT NULL,
    previous_score_1mo    INTEGER,
    previous_score_3mo    INTEGER,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_scores_pan_card ON scores (pan_card);


-- =============================================================================
-- 3. ACCOUNTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS accounts (
    account_id            VARCHAR(50)  PRIMARY KEY,
    pan_card              VARCHAR(10)  NOT NULL REFERENCES customers(pan_card) ON DELETE CASCADE,
    display_name          VARCHAR(255) NOT NULL,
    account_type          VARCHAR(50)  NOT NULL,
    status                VARCHAR(50)  NOT NULL,
    balance_paise         BIGINT       NOT NULL,
    credit_limit_paise    BIGINT,
    monthly_payment_paise BIGINT       NOT NULL,
    opened_date           DATE         NOT NULL,
    is_revolving          BOOLEAN      NOT NULL,
    payment_history       JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_accounts_pan_card ON accounts (pan_card);


-- =============================================================================
-- 4. INQUIRIES
-- =============================================================================
CREATE TABLE IF NOT EXISTS inquiries (
    inquiry_id     VARCHAR(50)  PRIMARY KEY,
    pan_card       VARCHAR(10)  NOT NULL REFERENCES customers(pan_card) ON DELETE CASCADE,
    creditor_name  VARCHAR(255) NOT NULL,
    inquiry_date   DATE         NOT NULL,
    inquiry_type   VARCHAR(50)  NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_inquiries_pan_card ON inquiries (pan_card);


-- =============================================================================
-- 5. COLLECTIONS
-- =============================================================================
CREATE TABLE IF NOT EXISTS collections (
    collection_id      VARCHAR(50)  PRIMARY KEY,
    pan_card           VARCHAR(10)  NOT NULL REFERENCES customers(pan_card) ON DELETE CASCADE,
    original_creditor  VARCHAR(255) NOT NULL,
    collection_agency  VARCHAR(255),
    balance_paise      BIGINT       NOT NULL,
    opened_date        DATE         NOT NULL,
    status             VARCHAR(50)  NOT NULL,
    is_past_sol        BOOLEAN      NOT NULL DEFAULT FALSE,
    is_disputable      BOOLEAN      NOT NULL DEFAULT FALSE,
    is_medical         BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_collections_pan_card ON collections (pan_card);


-- =============================================================================
-- 6. PUBLIC RECORDS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public_records (
    record_id     VARCHAR(50)  PRIMARY KEY,
    pan_card      VARCHAR(10)  NOT NULL REFERENCES customers(pan_card) ON DELETE CASCADE,
    record_type   VARCHAR(50)  NOT NULL,
    status        VARCHAR(50)  NOT NULL,
    amount_paise  BIGINT,
    jurisdiction  VARCHAR(255),
    filed_date    DATE         NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_public_records_pan_card ON public_records (pan_card);


-- =============================================================================
-- 7. KB_LABELS — 32 coaching labels
-- =============================================================================
CREATE TABLE IF NOT EXISTS kb_labels (
    label_id                          VARCHAR(100) PRIMARY KEY,
    display_name                      VARCHAR(255) NOT NULL,
    category                          VARCHAR(50)  NOT NULL,
    severity                          VARCHAR(50)  NOT NULL,
    priority_rank                     INTEGER      NOT NULL,
    fact_id                           VARCHAR(100) NOT NULL,
    condition                         TEXT         NOT NULL,
    condition_human                   TEXT         NOT NULL,
    what_it_means_cibil               TEXT         NOT NULL,
    why_it_matters                    TEXT         NOT NULL,
    personalized_response_template    TEXT         NOT NULL,
    created_at                        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_kb_labels_category     ON kb_labels (category);
CREATE INDEX IF NOT EXISTS ix_kb_labels_severity     ON kb_labels (severity);
CREATE INDEX IF NOT EXISTS ix_kb_labels_priority     ON kb_labels (priority_rank);


-- =============================================================================
-- 8. KB_MITIGATION_STEPS — ordered remediation per label
-- =============================================================================
CREATE TABLE IF NOT EXISTS kb_mitigation_steps (
    id         INTEGER       PRIMARY KEY,
    label_id   VARCHAR(100)  NOT NULL REFERENCES kb_labels(label_id) ON DELETE CASCADE,
    step_order INTEGER       NOT NULL,
    step_text  TEXT          NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kb_mitigation_steps_label_id ON kb_mitigation_steps (label_id);


-- =============================================================================
-- 9. KB_FACTS_TO_CITE — fact names to surface per label
-- =============================================================================
CREATE TABLE IF NOT EXISTS kb_facts_to_cite (
    id        INTEGER       PRIMARY KEY,
    label_id  VARCHAR(100)  NOT NULL REFERENCES kb_labels(label_id) ON DELETE CASCADE,
    fact_name VARCHAR(100)  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kb_facts_to_cite_label_id ON kb_facts_to_cite (label_id);


-- =============================================================================
-- 10. KB_REASON_CODES — CIBIL reason codes per label
-- =============================================================================
CREATE TABLE IF NOT EXISTS kb_reason_codes (
    id          INTEGER       PRIMARY KEY,
    label_id    VARCHAR(100)  NOT NULL REFERENCES kb_labels(label_id) ON DELETE CASCADE,
    reason_code VARCHAR(20)   NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kb_reason_codes_label_id ON kb_reason_codes (label_id);


-- =============================================================================
-- 11. KB_SOURCES — citation (title, URL) per label
-- =============================================================================
CREATE TABLE IF NOT EXISTS kb_sources (
    id        INTEGER       PRIMARY KEY,
    label_id  VARCHAR(100)  NOT NULL REFERENCES kb_labels(label_id) ON DELETE CASCADE,
    title     VARCHAR(500)  NOT NULL,
    url       VARCHAR(1000) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kb_sources_label_id ON kb_sources (label_id);


-- =============================================================================
-- 12. KB_META — top-level KB conventions (band ranges, etc.)
-- =============================================================================
CREATE TABLE IF NOT EXISTS kb_meta (
    key        VARCHAR(100) PRIMARY KEY,
    value      JSONB        NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- 13. REQUESTS — request audit + cost log
-- =============================================================================
CREATE TABLE IF NOT EXISTS requests (
    request_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    pan_card             VARCHAR(10)  REFERENCES customers(pan_card),
    request_type         VARCHAR(30)  NOT NULL,
    status               VARCHAR(20)  NOT NULL DEFAULT 'pending',
    input_payload        JSONB,
    output_payload       JSONB,
    error_message        TEXT,
    ip_address           INET,
    user_agent           TEXT,
    turnstile_verified   BOOLEAN      DEFAULT FALSE,
    cost_cents           INTEGER,
    latency_ms           INTEGER,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests (status, created_at);
CREATE INDEX IF NOT EXISTS idx_requests_pan    ON requests (pan_card, created_at DESC);


-- =============================================================================
-- ROW LEVEL SECURITY
--
-- Pattern: anon key can READ customer + KB data but cannot write to it.
-- Backend uses service_role key which bypasses RLS for INSERTs to `requests`.
-- =============================================================================

ALTER TABLE customers       ENABLE ROW LEVEL SECURITY;
ALTER TABLE scores          ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE inquiries       ENABLE ROW LEVEL SECURITY;
ALTER TABLE collections     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public_records  ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_labels       ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_mitigation_steps  ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_facts_to_cite     ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_reason_codes      ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_sources          ENABLE ROW LEVEL SECURITY;
ALTER TABLE kb_meta             ENABLE ROW LEVEL SECURITY;
ALTER TABLE requests            ENABLE ROW LEVEL SECURITY;


-- READ policies for anon (frontend may SELECT customer/KB data via the API
-- proxy; the frontend never queries Supabase directly for this read path).
CREATE POLICY "anon_read_customers"       ON customers       FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_scores"          ON scores          FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_accounts"        ON accounts        FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_inquiries"       ON inquiries       FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_collections"     ON collections     FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_public_records"  ON public_records  FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_kb_labels"       ON kb_labels       FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_kb_mitigation"   ON kb_mitigation_steps FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_kb_facts"        ON kb_facts_to_cite    FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_kb_reasons"      ON kb_reason_codes     FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_kb_sources"      ON kb_sources         FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_kb_meta"         ON kb_meta            FOR SELECT TO anon USING (true);


-- WRITE policies: anon cannot INSERT/UPDATE/DELETE anything except `requests`.
-- (Even `requests` writes are blocked at anon; backend uses service_role.)

CREATE POLICY "anon_deny_insert_customers"       ON customers       FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_customers"       ON customers       FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_customers"       ON customers       FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_scores"          ON scores          FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_scores"          ON scores          FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_scores"          ON scores          FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_accounts"        ON accounts        FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_accounts"        ON accounts        FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_accounts"        ON accounts        FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_inquiries"       ON inquiries       FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_inquiries"       ON inquiries       FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_inquiries"       ON inquiries       FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_collections"     ON collections     FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_collections"     ON collections     FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_collections"     ON collections     FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_public_records"  ON public_records  FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_public_records"  ON public_records  FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_public_records"  ON public_records  FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_kb_labels"       ON kb_labels       FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_kb_labels"       ON kb_labels       FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_kb_labels"       ON kb_labels       FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_kb_mitigation"   ON kb_mitigation_steps FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_kb_mitigation"   ON kb_mitigation_steps FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_kb_mitigation"   ON kb_mitigation_steps FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_kb_facts"        ON kb_facts_to_cite    FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_kb_facts"        ON kb_facts_to_cite    FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_kb_facts"        ON kb_facts_to_cite    FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_kb_reasons"      ON kb_reason_codes     FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_kb_reasons"      ON kb_reason_codes     FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_kb_reasons"      ON kb_reason_codes     FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_kb_sources"      ON kb_sources         FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_kb_sources"      ON kb_sources         FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_kb_sources"      ON kb_sources         FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_kb_meta"         ON kb_meta            FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_kb_meta"         ON kb_meta            FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_kb_meta"         ON kb_meta            FOR DELETE TO anon USING (false);

CREATE POLICY "anon_deny_insert_requests"        ON requests           FOR INSERT TO anon WITH CHECK (false);
CREATE POLICY "anon_deny_update_requests"        ON requests           FOR UPDATE TO anon USING (false);
CREATE POLICY "anon_deny_delete_requests"        ON requests           FOR DELETE TO anon USING (false);