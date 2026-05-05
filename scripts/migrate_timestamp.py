"""
posts.post_date: DATE → TIMESTAMP 마이그레이션 스크립트
1. 전체 DB 백업 (CSV)
2. 의존 테이블부터 순서대로 DROP
3. 새 스키마로 재생성
4. 데이터 복원
"""
import psycopg2
import csv
import os
from db_config import DB_CONFIG

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backup")
os.makedirs(BACKUP_DIR, exist_ok=True)

def backup_table(cur, table_name, columns):
    """테이블 데이터를 CSV로 백업"""
    path = os.path.join(BACKUP_DIR, f"{table_name}.csv")
    cur.execute(f"SELECT {', '.join(columns)} FROM {table_name} ORDER BY id")
    rows = cur.fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    print(f"  ✅ {table_name}: {len(rows)}건 → {path}")
    return len(rows)

def restore_table(cur, table_name, columns):
    """CSV에서 데이터 복원"""
    path = os.path.join(BACKUP_DIR, f"{table_name}.csv")
    if not os.path.exists(path):
        print(f"  ⚠️ {table_name}: 백업 파일 없음, 스킵")
        return 0
    
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header
        rows = list(reader)
    
    if not rows:
        print(f"  ⚠️ {table_name}: 데이터 없음")
        return 0
    
    placeholders = ", ".join(["%s"] * len(columns))
    col_names = ", ".join(columns)
    
    for row in rows:
        # 빈 문자열을 None으로 변환
        cleaned = [None if v == "" else v for v in row]
        try:
            cur.execute(
                f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})",
                cleaned,
            )
        except Exception as e:
            print(f"  ❌ {table_name} 삽입 오류: {e} | row: {cleaned[:3]}...")
            raise
    
    # 시퀀스 재설정
    cur.execute(f"SELECT MAX(id) FROM {table_name}")
    max_id = cur.fetchone()[0]
    if max_id:
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), %s)", (max_id,))
    
    print(f"  ✅ {table_name}: {len(rows)}건 복원")
    return len(rows)

# 테이블 정의 (백업/복원 순서 고려)
TABLES = [
    ("communities", ["id", "name", "base_url", "category", "is_active", "created_at"]),
    ("tickers", ["id", "symbol", "name", "market", "is_active", "created_at"]),
    ("posts", ["id", "community_id", "title", "author", "post_date", "collected_at", "source_url"]),
    ("post_mentions", ["id", "post_id", "ticker_id", "sentiment", "analyzed_at"]),
    ("mention_daily_stats", ["id", "ticker_id", "community_id", "stat_date", "mention_count", "positive_count", "negative_count", "neutral_count", "calculated_at"]),
    ("mention_trend_alerts", ["id", "ticker_id", "alert_date", "current_week_count", "previous_week_count", "change_rate", "is_read", "created_at"]),
    ("expert_sources", ["id", "name", "source_type", "base_url", "is_active", "created_at"]),
    ("expert_articles", ["id", "source_id", "title", "author", "securities_firm", "published_date", "collected_at", "source_url"]),
    ("expert_article_mentions", ["id", "article_id", "ticker_id", "sentiment", "target_price", "opinion", "analyzed_at"]),
]

# DROP 순서 (의존성 역순)
DROP_ORDER = [
    "expert_article_mentions",
    "expert_articles", 
    "expert_sources",
    "mention_trend_alerts",
    "mention_daily_stats",
    "post_mentions",
    "posts",
    "tickers",
    "communities",
]

# CREATE 순서 (init-db.sql 기반, post_date를 TIMESTAMP으로)
CREATE_SQL = """
CREATE TABLE communities (
    id          SERIAL          PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL UNIQUE,
    base_url    VARCHAR(500)    NOT NULL,
    category    VARCHAR(100),
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE tickers (
    id          SERIAL          PRIMARY KEY,
    symbol      VARCHAR(20)     NOT NULL UNIQUE,
    name        VARCHAR(200)    NOT NULL,
    market      VARCHAR(20)     NOT NULL DEFAULT 'KRX',
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_tickers_name ON tickers (name);

CREATE TABLE posts (
    id              BIGSERIAL       PRIMARY KEY,
    community_id    INTEGER         NOT NULL REFERENCES communities(id),
    title           TEXT            NOT NULL,
    author          VARCHAR(200),
    post_date       TIMESTAMP       NOT NULL,
    collected_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_url      VARCHAR(1000)
);
CREATE INDEX ix_posts_community_date ON posts (community_id, post_date);
CREATE INDEX ix_posts_post_date ON posts (post_date);
CREATE UNIQUE INDEX uq_posts_source_url ON posts (source_url) WHERE source_url IS NOT NULL;

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

CREATE TABLE expert_sources (
    id          SERIAL          PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL UNIQUE,
    source_type VARCHAR(20)     NOT NULL,
    base_url    VARCHAR(500)    NOT NULL,
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE expert_articles (
    id              BIGSERIAL       PRIMARY KEY,
    source_id       INTEGER         NOT NULL REFERENCES expert_sources(id),
    title           TEXT            NOT NULL,
    author          VARCHAR(200),
    securities_firm VARCHAR(100),
    published_date  DATE            NOT NULL,
    collected_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_url      VARCHAR(1000)
);
CREATE INDEX ix_expert_articles_published_date ON expert_articles (published_date);
CREATE INDEX ix_expert_articles_source_date ON expert_articles (source_id, published_date);
CREATE INDEX ix_expert_articles_securities_firm ON expert_articles (securities_firm) WHERE securities_firm IS NOT NULL;
CREATE UNIQUE INDEX uq_expert_articles_source_url ON expert_articles (source_url) WHERE source_url IS NOT NULL;

CREATE TABLE expert_article_mentions (
    id          BIGSERIAL       PRIMARY KEY,
    article_id  BIGINT          NOT NULL REFERENCES expert_articles(id) ON DELETE CASCADE,
    ticker_id   INTEGER         NOT NULL REFERENCES tickers(id),
    sentiment   SMALLINT        NOT NULL DEFAULT 0,
    target_price VARCHAR(50),
    opinion     VARCHAR(20),
    analyzed_at TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_expert_article_mentions UNIQUE (article_id, ticker_id)
);
CREATE INDEX ix_expert_article_mentions_article ON expert_article_mentions (article_id);
CREATE INDEX ix_expert_article_mentions_ticker ON expert_article_mentions (ticker_id);
"""

if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()
    
    # ── STEP 1: 백업 ──
    print("=" * 60)
    print("STEP 1: 데이터 백업")
    print("=" * 60)
    for table_name, columns in TABLES:
        try:
            backup_table(cur, table_name, columns)
        except Exception as e:
            print(f"  ⚠️ {table_name}: {e}")
    
    # ── STEP 2: 테이블 삭제 ──
    print("\n" + "=" * 60)
    print("STEP 2: 테이블 삭제")
    print("=" * 60)
    for table_name in DROP_ORDER:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
            print(f"  🗑️ {table_name} 삭제")
        except Exception as e:
            print(f"  ❌ {table_name} 삭제 실패: {e}")
    
    # ── STEP 3: 테이블 재생성 ──
    print("\n" + "=" * 60)
    print("STEP 3: 테이블 재생성 (post_date = TIMESTAMP)")
    print("=" * 60)
    for statement in CREATE_SQL.split(";"):
        statement = statement.strip()
        if statement:
            try:
                cur.execute(statement)
            except Exception as e:
                print(f"  ❌ SQL 오류: {e}")
                print(f"     {statement[:80]}...")
    print("  ✅ 테이블 생성 완료")
    
    # ── STEP 4: 데이터 복원 ──
    print("\n" + "=" * 60)
    print("STEP 4: 데이터 복원")
    print("=" * 60)
    for table_name, columns in TABLES:
        try:
            restore_table(cur, table_name, columns)
        except Exception as e:
            print(f"  ❌ {table_name} 복원 실패: {e}")
            break
    
    conn.close()
    print("\n" + "=" * 60)
    print("✅ 마이그레이션 완료!")
    print("=" * 60)
