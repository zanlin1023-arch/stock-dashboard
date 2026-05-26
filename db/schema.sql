-- ═══════════════════════════════════════════════════════════════
-- Stock Dashboard 스키마 (Supabase PostgreSQL)
-- ═══════════════════════════════════════════════════════════════

-- 1. 보유 종목 (holdings)
CREATE TABLE IF NOT EXISTS holdings (
    id BIGSERIAL PRIMARY KEY,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    avg_price NUMERIC(18, 2) NOT NULL CHECK (avg_price > 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    purchase_date DATE NOT NULL DEFAULT CURRENT_DATE,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_holdings_code ON holdings(stock_code);
CREATE INDEX IF NOT EXISTS idx_holdings_date ON holdings(purchase_date DESC);

-- 2. 관심 종목 (watchlist)
CREATE TABLE IF NOT EXISTS watchlist (
    id BIGSERIAL PRIMARY KEY,
    stock_code TEXT NOT NULL UNIQUE,
    stock_name TEXT NOT NULL,
    note TEXT,
    tags TEXT[],  -- 태그 배열 (예: ['반도체', 'AI'])
    added_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_code ON watchlist(stock_code);

-- 3. 분석 히스토리 (analysis_history)
CREATE TABLE IF NOT EXISTS analysis_history (
    id BIGSERIAL PRIMARY KEY,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    -- 핵심 지표
    price NUMERIC(18, 2),
    rsi_14 NUMERIC(6, 2),
    macd NUMERIC(18, 4),
    -- 일목균형표
    tenkan NUMERIC(18, 2),
    kijun NUMERIC(18, 2),
    senkou_a NUMERIC(18, 2),
    senkou_b NUMERIC(18, 2),
    cloud_position TEXT,  -- 'above' / 'inside' / 'below'
    -- 의사결정
    decision_stance TEXT,  -- 'STRONG_BUY' / 'BUY' / 'NEUTRAL' / 'SELL' / 'STRONG_SELL'
    decision_action TEXT,
    -- 목표가
    target_v NUMERIC(18, 2),
    target_n NUMERIC(18, 2),
    target_e NUMERIC(18, 2),
    stop_loss NUMERIC(18, 2),
    -- 전체 결과 (확장성)
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_history_code ON analysis_history(stock_code);
CREATE INDEX IF NOT EXISTS idx_history_date ON analysis_history(analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_code_date ON analysis_history(stock_code, analyzed_at DESC);

-- updated_at 자동 갱신 트리거 (holdings용)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_holdings_updated_at ON holdings;
CREATE TRIGGER update_holdings_updated_at
    BEFORE UPDATE ON holdings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
