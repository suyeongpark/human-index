# Human Index - Database Schema

> PostgreSQL 기반 주식 언급량 분석 시스템의 데이터베이스 스키마 설계 문서
> - **대중 의견**: 커뮤니티 게시글 기반 (communities → posts → post_mentions)
> - **전문가 의견**: 증권사 리포트·뉴스 기사 기반 (expert_sources → expert_articles → expert_article_mentions)

---

## ER Diagram

```mermaid
erDiagram
    communities ||--o{ posts : "has"
    posts ||--o{ post_mentions : "contains"
    tickers ||--o{ post_mentions : "referenced_in"
    tickers ||--o{ mention_daily_stats : "aggregated"
    communities ||--o{ mention_daily_stats : "source"
    tickers ||--o{ mention_trend_alerts : "triggers"

    expert_sources ||--o{ expert_articles : "publishes"
    expert_articles ||--o{ expert_article_mentions : "contains"
    tickers ||--o{ expert_article_mentions : "referenced_in"

    communities {
        int id PK
        varchar name
        varchar base_url
        varchar category
        boolean is_active
        timestamptz created_at
    }

    posts {
        bigint id PK
        int community_id FK
        varchar title
        varchar author
        timestamp post_date
        timestamptz collected_at
        varchar source_url
    }

    tickers {
        int id PK
        varchar symbol
        varchar name
        varchar market
        boolean is_active
        timestamptz created_at
    }

    post_mentions {
        bigint id PK
        bigint post_id FK
        int ticker_id FK
        smallint sentiment
        timestamptz analyzed_at
    }

    mention_daily_stats {
        bigint id PK
        int ticker_id FK
        int community_id FK
        date stat_date
        int mention_count
        int positive_count
        int negative_count
        int neutral_count
        timestamptz calculated_at
    }

    mention_trend_alerts {
        bigint id PK
        int ticker_id FK
        date alert_date
        int current_week_count
        int previous_week_count
        numeric change_rate
        boolean is_read
        timestamptz created_at
    }

    crawler_health_alerts {
        bigint id PK
        varchar alert_key UK
        varchar source
        varchar status
        varchar severity
        text title
        text message
        timestamptz first_detected_at
        timestamptz last_detected_at
        timestamptz last_notified_at
        timestamptz resolved_at
    }

    expert_sources {
        int id PK
        varchar name
        varchar source_type
        varchar base_url
        boolean is_active
        timestamptz created_at
    }

    expert_articles {
        bigint id PK
        int source_id FK
        varchar title
        varchar author
        varchar securities_firm
        date published_date
        timestamptz collected_at
        varchar source_url
    }

    expert_article_mentions {
        bigint id PK
        bigint article_id FK
        int ticker_id FK
        smallint sentiment
        varchar target_price
        varchar opinion
        timestamptz analyzed_at
    }
```

---

## Tables

### 📢 대중 의견 (Public Opinion)

### 1. `communities` — 크롤링 대상 커뮤니티

크롤링 대상이 되는 커뮤니티 사이트 정보를 관리한다.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `SERIAL` | `PK` | 커뮤니티 고유 ID |
| `name` | `VARCHAR(100)` | `NOT NULL, UNIQUE` | 커뮤니티 이름 (예: 디시인사이드, 네이버 카페 등) |
| `base_url` | `VARCHAR(500)` | `NOT NULL` | 크롤링 대상 기본 URL |
| `category` | `VARCHAR(100)` | | 크롤링 대상 카테고리 (예: 주식, 해외주식) |
| `is_active` | `BOOLEAN` | `NOT NULL DEFAULT TRUE` | 크롤링 활성 여부 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 등록 일시 |

---

### 2. `posts` — 크롤링된 게시글 제목

> **시나리오 1** — 매일 정해진 시간에 커뮤니티에서 제목만 추출하여 저장

커뮤니티에서 수집된 게시글의 메타 정보(제목, 작성자, 날짜)를 저장한다. 본문은 저장하지 않는다.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `BIGSERIAL` | `PK` | 게시글 고유 ID |
| `community_id` | `INTEGER` | `NOT NULL, FK → communities.id` | 출처 커뮤니티 |
| `title` | `TEXT` | `NOT NULL` | 게시글 제목 (full text) |
| `author` | `VARCHAR(200)` | | 작성자 |
| `post_date` | `TIMESTAMP` | `NOT NULL` | 게시글 작성일시 |
| `collected_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 수집 일시 |
| `source_url` | `VARCHAR(1000)` | | 원본 게시글 URL (중복 수집 방지용) |

**Indexes:**
- `ix_posts_community_date` — `(community_id, post_date)` : 커뮤니티별 일자 조회
- `ix_posts_post_date` — `(post_date)` : 날짜 기반 조회
- `uq_posts_source_url` — `UNIQUE(source_url)` : 중복 수집 방지

---

### 3. `tickers` — 종목 마스터

> **시나리오 2** — ticker를 별도로 DB화

분석 대상 종목(ticker) 정보를 관리한다.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `SERIAL` | `PK` | 종목 고유 ID |
| `symbol` | `VARCHAR(20)` | `NOT NULL, UNIQUE` | 종목 코드 (예: 005930, AAPL) |
| `name` | `VARCHAR(200)` | `NOT NULL` | 종목명 (예: 삼성전자, Apple Inc.) |
| `market` | `VARCHAR(20)` | `NOT NULL DEFAULT 'KRX'` | 시장 구분 (KRX, NASDAQ, NYSE 등) |
| `is_active` | `BOOLEAN` | `NOT NULL DEFAULT TRUE` | 활성 여부 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 등록 일시 |

**Indexes:**
- `ix_tickers_name` — `(name)` : 종목명 검색용

> [!TIP]
> 종목 매칭 시 `symbol`뿐 아니라 `name` 기반으로도 매칭해야 하므로, 별칭(alias) 테이블을 추후 추가하는 것을 고려할 수 있다. (예: "삼전" → "삼성전자")

---

### 4. `post_mentions` — 게시글별 종목 언급 & 감성 분석

> **시나리오 2** — 제목에서 종목을 추출하고 긍정/부정/중립을 판별

게시글 제목에서 추출된 종목 언급과 해당 감성(sentiment) 분석 결과를 저장한다.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `BIGSERIAL` | `PK` | 고유 ID |
| `post_id` | `BIGINT` | `NOT NULL, FK → posts.id` | 게시글 참조 |
| `ticker_id` | `INTEGER` | `NOT NULL, FK → tickers.id` | 언급된 종목 |
| `sentiment` | `SMALLINT` | `NOT NULL DEFAULT 0` | 감성 분석 결과: `1` 긍정 / `-1` 부정 / `0` 중립 |
| `analyzed_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 분석 일시 |

**Indexes:**
- `ix_post_mentions_ticker` — `(ticker_id)` : 종목별 언급 조회
- `ix_post_mentions_post` — `(post_id)` : 게시글별 언급 조회
- `uq_post_mentions_post_ticker` — `UNIQUE(post_id, ticker_id)` : 동일 게시글-종목 중복 방지

---

### 📊 공통 집계 (Aggregation)

### 5. `mention_daily_stats` — 일별 종목 언급 통계

일별/커뮤니티별 종목 언급 수와 감성 분포를 집계한 테이블. 트렌드 분석의 기반 데이터.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `BIGSERIAL` | `PK` | 고유 ID |
| `ticker_id` | `INTEGER` | `NOT NULL, FK → tickers.id` | 종목 |
| `community_id` | `INTEGER` | `FK → communities.id` | 커뮤니티 (NULL이면 전체 합산) |
| `stat_date` | `DATE` | `NOT NULL` | 집계 날짜 |
| `mention_count` | `INTEGER` | `NOT NULL DEFAULT 0` | 총 언급 수 |
| `positive_count` | `INTEGER` | `NOT NULL DEFAULT 0` | 긍정 언급 수 |
| `negative_count` | `INTEGER` | `NOT NULL DEFAULT 0` | 부정 언급 수 |
| `neutral_count` | `INTEGER` | `NOT NULL DEFAULT 0` | 중립 언급 수 |
| `calculated_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 집계 일시 |

**Indexes:**
- `uq_mention_daily_stats` — `UNIQUE(ticker_id, community_id, stat_date)` : 중복 집계 방지
- `ix_mention_daily_stats_date` — `(stat_date)` : 날짜 기반 조회

---

### 6. `mention_trend_alerts` — 트렌드 알림

> **시나리오 3** — 전주 대비 언급량 증가 종목 알림

주간 언급량 변화를 감지하여 생성된 알림 정보를 저장한다.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `BIGSERIAL` | `PK` | 고유 ID |
| `ticker_id` | `INTEGER` | `NOT NULL, FK → tickers.id` | 종목 |
| `alert_date` | `DATE` | `NOT NULL` | 알림 발생일 |
| `current_week_count` | `INTEGER` | `NOT NULL` | 금주 언급 수 |
| `previous_week_count` | `INTEGER` | `NOT NULL` | 전주 언급 수 |
| `change_rate` | `NUMERIC(10,4)` | `NOT NULL` | 변화율 (예: 1.5 = 150% 증가) |
| `is_read` | `BOOLEAN` | `NOT NULL DEFAULT FALSE` | 읽음 여부 (UI 알림 표시용) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 알림 생성 일시 |

**Indexes:**
- `ix_trend_alerts_ticker_date` — `(ticker_id, alert_date)` : 종목별 알림 조회
- `ix_trend_alerts_unread` — `(is_read) WHERE is_read = FALSE` : 미읽은 알림 조회 (partial index)

---

### 🛠 운영 알림 (Operational Alerts)

### 7. `crawler_health_alerts` — 크롤러 상태 알림

크롤러 쿠키 만료, 차단 응답 등 운영자가 확인해야 하는 상태 알림을 저장한다.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `BIGSERIAL` | `PK` | 고유 ID |
| `alert_key` | `VARCHAR(100)` | `NOT NULL, UNIQUE` | 알림 종류별 고정 키 (예: `fmkorea_cookie_430`) |
| `source` | `VARCHAR(50)` | `NOT NULL` | 알림 출처 (예: `fmkorea`) |
| `status` | `VARCHAR(20)` | `NOT NULL DEFAULT 'open'` | `open` / `resolved` |
| `severity` | `VARCHAR(20)` | `NOT NULL DEFAULT 'warning'` | 심각도 |
| `title` | `TEXT` | `NOT NULL` | 알림 제목 |
| `message` | `TEXT` | `NOT NULL` | 알림 메시지 |
| `first_detected_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 최초 감지 시각 |
| `last_detected_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 마지막 감지 시각 |
| `last_notified_at` | `TIMESTAMPTZ` | | 마지막 macOS 알림 발송 시각 |
| `resolved_at` | `TIMESTAMPTZ` | | 처리 완료 시각 |
| `resolution_note` | `TEXT` | | 처리 메모 |
| `details` | `JSONB` | `NOT NULL DEFAULT '{}'` | 감지 상세 정보 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 생성 일시 |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 수정 일시 |

**Indexes:**
- `ix_crawler_health_alerts_status` — `(status, source)` : 열린 운영 알림 조회

---

### 🔬 전문가 의견 (Expert Opinion)

### 8. `expert_sources` — 전문가 소스

증권사 리포트, 뉴스 기사 등 전문가 의견의 출처를 관리한다.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `SERIAL` | `PK` | 소스 고유 ID |
| `name` | `VARCHAR(100)` | `NOT NULL, UNIQUE` | 소스 이름 (예: 한경 컨센서스, 네이버 증권 리서치) |
| `source_type` | `VARCHAR(20)` | `NOT NULL` | 소스 유형: `report` (증권사 리포트) / `article` (뉴스 기사) |
| `base_url` | `VARCHAR(500)` | `NOT NULL` | 수집 대상 기본 URL |
| `is_active` | `BOOLEAN` | `NOT NULL DEFAULT TRUE` | 수집 활성 여부 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 등록 일시 |

---

### 9. `expert_articles` — 전문가 리포트·기사

증권사 리포트 및 뉴스 기사의 메타 정보(제목, 작성자, 증권사, 날짜)를 저장한다. 커뮤니티 `posts`의 전문가 버전.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `BIGSERIAL` | `PK` | 고유 ID |
| `source_id` | `INTEGER` | `NOT NULL, FK → expert_sources.id` | 출처 소스 |
| `title` | `TEXT` | `NOT NULL` | 리포트/기사 제목 |
| `author` | `VARCHAR(200)` | | 작성자 (애널리스트명, 기자명) |
| `securities_firm` | `VARCHAR(100)` | | 증권사명 (리포트인 경우. 예: 미래에셋, 삼성증권) |
| `published_date` | `DATE` | `NOT NULL` | 발행일 |
| `collected_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 수집 일시 |
| `source_url` | `VARCHAR(1000)` | | 원본 URL (중복 수집 방지용) |

**Indexes:**
- `ix_expert_articles_source_date` — `(source_id, published_date)` : 소스별 일자 조회
- `ix_expert_articles_published_date` — `(published_date)` : 날짜 기반 조회
- `ix_expert_articles_securities_firm` — `(securities_firm)` : 증권사별 조회
- `uq_expert_articles_source_url` — `UNIQUE(source_url)` : 중복 수집 방지

---

### 10. `expert_article_mentions` — 리포트·기사별 종목 언급 & 감성 분석

리포트/기사 제목에서 추출된 종목 언급과 감성 분석 결과를 저장한다. 커뮤니티 `post_mentions`의 전문가 버전.

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | `BIGSERIAL` | `PK` | 고유 ID |
| `article_id` | `BIGINT` | `NOT NULL, FK → expert_articles.id` | 리포트/기사 참조 |
| `ticker_id` | `INTEGER` | `NOT NULL, FK → tickers.id` | 언급된 종목 |
| `sentiment` | `SMALLINT` | `NOT NULL DEFAULT 0` | 감성: `1` 긍정 / `-1` 부정 / `0` 중립 |
| `target_price` | `VARCHAR(50)` | | 목표가 (리포트에 명시된 경우) |
| `opinion` | `VARCHAR(20)` | | 투자의견 (매수/중립/매도 등) |
| `analyzed_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` | 분석 일시 |

**Indexes:**
- `ix_expert_article_mentions_ticker` — `(ticker_id)` : 종목별 언급 조회
- `ix_expert_article_mentions_article` — `(article_id)` : 기사별 언급 조회
- `uq_expert_article_mentions` — `UNIQUE(article_id, ticker_id)` : 동일 기사-종목 중복 방지

---

## Data Flow

```mermaid
flowchart TD
    subgraph public["📢 대중 의견"]
        A["⏰ Scheduled Crawler"] -->|"매일 크롤링"| B["communities"]
        A -->|"제목 저장"| C["posts"]
        C -->|"종목 추출 & 감성 분석"| D["post_mentions"]
    end

    subgraph expert["🔬 전문가 의견"]
        A2["⏰ Report Crawler"] -->|"리포트/기사 수집"| B2["expert_sources"]
        A2 -->|"제목 저장"| C2["expert_articles"]
        C2 -->|"종목 추출 & 감성 분석"| D2["expert_article_mentions"]
    end

    E["tickers<br/>(종목 마스터)"] -->|"매칭"| D
    E -->|"매칭"| D2
    D -->|"일별 집계"| F["mention_daily_stats"]
    D2 -->|"일별 집계"| F
    F -->|"주간 비교 분석"| G["mention_trend_alerts"]
    G -->|"알림 표시"| H["🖥️ Blazor WASM UI"]
    F -->|"차트/대시보드<br/>(대중 vs 전문가)"| H
```

---

## DDL

```sql
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
    post_date       TIMESTAMP       NOT NULL,
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

-- =============================================
-- 운영 알림 (Operational Alerts)
-- =============================================

-- 7. crawler_health_alerts
CREATE TABLE crawler_health_alerts (
    id                  BIGSERIAL       PRIMARY KEY,
    alert_key           VARCHAR(100)    NOT NULL UNIQUE,
    source              VARCHAR(50)     NOT NULL,
    status              VARCHAR(20)     NOT NULL DEFAULT 'open',
    severity            VARCHAR(20)     NOT NULL DEFAULT 'warning',
    title               TEXT            NOT NULL,
    message             TEXT            NOT NULL,
    first_detected_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_detected_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_notified_at    TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    resolution_note     TEXT,
    details             JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_crawler_health_alerts_status CHECK (status IN ('open', 'resolved'))
);

CREATE INDEX ix_crawler_health_alerts_status ON crawler_health_alerts (status, source);

-- =============================================
-- 전문가 의견 (Expert Opinion)
-- =============================================

-- 8. expert_sources
CREATE TABLE expert_sources (
    id          SERIAL          PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL UNIQUE,
    source_type VARCHAR(20)     NOT NULL,
    base_url    VARCHAR(500)    NOT NULL,
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN expert_sources.source_type IS 'report: 증권사 리포트, article: 뉴스 기사';

-- 9. expert_articles
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

CREATE INDEX ix_expert_articles_source_date ON expert_articles (source_id, published_date);
CREATE INDEX ix_expert_articles_published_date ON expert_articles (published_date);
CREATE INDEX ix_expert_articles_securities_firm ON expert_articles (securities_firm) WHERE securities_firm IS NOT NULL;
CREATE UNIQUE INDEX uq_expert_articles_source_url ON expert_articles (source_url) WHERE source_url IS NOT NULL;

-- 10. expert_article_mentions
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

CREATE INDEX ix_expert_article_mentions_ticker ON expert_article_mentions (ticker_id);
CREATE INDEX ix_expert_article_mentions_article ON expert_article_mentions (article_id);

COMMENT ON COLUMN expert_article_mentions.sentiment IS '1: 긍정, -1: 부정, 0: 중립';
COMMENT ON COLUMN expert_article_mentions.opinion IS '매수, 중립, 매도, Trading Buy 등';
```

---

## Design Decisions

> [!NOTE]
> ### 왜 본문(content)을 저장하지 않는가?
> 프로젝트 운영 원칙상 언급량 분석이 목적이므로 본문은 수집하지 않는다.
> 제목만으로 종목 추출 및 감성 분석을 수행하여 스토리지 비용을 최소화한다.

> [!NOTE]
> ### sentiment를 SMALLINT로 관리하는 이유
> ENUM 대신 `SMALLINT(-1, 0, 1)`를 사용하면 집계 시 `SUM()`으로 전체 감성 점수를 산출할 수 있고,
> 추후 감성 강도(예: -2 ~ +2)로 확장하기도 용이하다.

> [!NOTE]
> ### mention_daily_stats의 community_id가 nullable인 이유
> `community_id = NULL`인 행은 전체 커뮤니티 합산 통계를 나타낸다.
> 커뮤니티별 통계와 전체 통계를 하나의 테이블에서 관리하여 쿼리를 단순화한다.

> [!NOTE]
> ### 대중 의견 vs 전문가 의견 분리 이유
> 커뮤니티 게시글(대중)과 증권사 리포트·뉴스(전문가)는 데이터 특성이 다르므로 별도 테이블로 관리한다.
> - **대중 의견**: 대량, 노이즈 多, 감성 분석 중심, 버즈량 추적 목적
> - **전문가 의견**: 소량, 구조화, 목표가·투자의견 포함, 시장 컨센서스 추적 목적
> - `mention_daily_stats`에서 양쪽을 합산하여 교차 분석 가능

> [!NOTE]
> ### expert_articles에 securities_firm을 별도 컬럼으로 둔 이유
> 하나의 소스(예: 한경 컨센서스)에서 여러 증권사의 리포트가 수집되므로,
> 증권사를 기사 레벨에서 관리해야 "어떤 증권사가 어떤 종목을 커버하는지" 분석이 가능하다.

> [!IMPORTANT]
> ### 향후 확장 고려 사항
> - **ticker_aliases 테이블**: "삼전" → "삼성전자" 같은 별칭 매핑 지원
> - **crawl_logs 테이블**: 크롤링 실행 이력 및 에러 로그 관리
> - **price_data 테이블**: 주가 데이터 연동 시 언급량-주가 상관관계 분석 지원
> - **expert_daily_stats 테이블**: 전문가 의견 전용 일별 집계 (필요 시 mention_daily_stats에서 분리)
