-- =============================================
-- Human Index - Database Schema DDL
-- PostgreSQL 15+
-- =============================================

-- 1. communities
CREATE TABLE communities (
    id          SERIAL          PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL UNIQUE,
    base_url    VARCHAR(500)    NOT NULL,
    category    VARCHAR(100),
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- 2. posts
CREATE TABLE posts (
    id              BIGSERIAL       PRIMARY KEY,
    community_id    INTEGER         NOT NULL REFERENCES communities(id),
    title           TEXT            NOT NULL,
    author          VARCHAR(200),
    post_date       DATE            NOT NULL,
    collected_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_url      VARCHAR(1000)
);

CREATE INDEX ix_posts_community_date ON posts (community_id, post_date);
CREATE INDEX ix_posts_post_date ON posts (post_date);
CREATE UNIQUE INDEX uq_posts_source_url ON posts (source_url) WHERE source_url IS NOT NULL;

-- 3. tickers
CREATE TABLE tickers (
    id          SERIAL          PRIMARY KEY,
    symbol      VARCHAR(20)     NOT NULL UNIQUE,
    name        VARCHAR(200)    NOT NULL,
    market      VARCHAR(20)     NOT NULL DEFAULT 'KRX',
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_tickers_name ON tickers (name);

-- 4. post_mentions
CREATE TABLE post_mentions (
    id          BIGSERIAL       PRIMARY KEY,
    post_id     BIGINT          NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    ticker_id   INTEGER         NOT NULL REFERENCES tickers(id),
    sentiment   SMALLINT        NOT NULL DEFAULT 0,
    analyzed_at TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_post_mentions_post_ticker UNIQUE (post_id, ticker_id)
);

CREATE INDEX ix_post_mentions_ticker ON post_mentions (ticker_id);
CREATE INDEX ix_post_mentions_post ON post_mentions (post_id);

COMMENT ON COLUMN post_mentions.sentiment IS '1: 긍정, -1: 부정, 0: 중립';

-- 5. mention_daily_stats
CREATE TABLE mention_daily_stats (
    id              BIGSERIAL       PRIMARY KEY,
    ticker_id       INTEGER         NOT NULL REFERENCES tickers(id),
    community_id    INTEGER         REFERENCES communities(id),
    stat_date       DATE            NOT NULL,
    mention_count   INTEGER         NOT NULL DEFAULT 0,
    positive_count  INTEGER         NOT NULL DEFAULT 0,
    negative_count  INTEGER         NOT NULL DEFAULT 0,
    neutral_count   INTEGER         NOT NULL DEFAULT 0,
    calculated_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_mention_daily_stats
    ON mention_daily_stats (ticker_id, COALESCE(community_id, 0), stat_date);
CREATE INDEX ix_mention_daily_stats_date ON mention_daily_stats (stat_date);

-- 6. mention_trend_alerts
CREATE TABLE mention_trend_alerts (
    id                  BIGSERIAL       PRIMARY KEY,
    ticker_id           INTEGER         NOT NULL REFERENCES tickers(id),
    alert_date          DATE            NOT NULL,
    current_week_count  INTEGER         NOT NULL,
    previous_week_count INTEGER         NOT NULL,
    change_rate         NUMERIC(10,4)   NOT NULL,
    is_read             BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_trend_alerts_ticker_date ON mention_trend_alerts (ticker_id, alert_date);
CREATE INDEX ix_trend_alerts_unread ON mention_trend_alerts (is_read) WHERE is_read = FALSE;
