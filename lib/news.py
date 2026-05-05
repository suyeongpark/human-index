"""
뉴스 페이지 모듈 - Google News 기사 분석
expert_sources.source_type = 'article' 데이터만 표시
"""

import streamlit as st
from lib.shared import (
    run_query, paginated_dataframe, period_tabs,
    render_top10_chart, render_surge_page, render_colored_line_chart,
    page_header, pagination_bar,
    PERIOD_OPTIONS, PERIOD_SQL, PERIOD_DAYS,
    SCORE_WEIGHT_POSITIVE, SCORE_WEIGHT_NEGATIVE, SCORE_WEIGHT_NEUTRAL,
)

# ─── SQL 쿼리 ──────────────────────────────────────────

SQL_KPI = """
    SELECT
        (SELECT COUNT(*) FROM expert_articles ea
         JOIN expert_sources es ON es.id = ea.source_id
         WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article') as total_articles,
        (SELECT COUNT(DISTINCT eam.ticker_id) FROM expert_article_mentions eam
         JOIN expert_articles ea ON ea.id = eam.article_id
         JOIN expert_sources es ON es.id = ea.source_id
         WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article') as unique_tickers,
        (SELECT COUNT(*) FROM expert_article_mentions eam
         JOIN expert_articles ea ON ea.id = eam.article_id
         JOIN expert_sources es ON es.id = ea.source_id
         WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article' AND eam.sentiment = 1) as pos_cnt,
        (SELECT COUNT(*) FROM expert_article_mentions eam
         JOIN expert_articles ea ON ea.id = eam.article_id
         JOIN expert_sources es ON es.id = ea.source_id
         WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article' AND eam.sentiment <= 0) as other_cnt
"""

SQL_SENTIMENT_TREND = """
    SELECT {{date_sel}} as "날짜",
           COUNT(*) FILTER (WHERE eam.sentiment = 1) as "👍 긍정",
           COUNT(*) FILTER (WHERE eam.sentiment = 0) as "➖ 중립",
           COUNT(*) FILTER (WHERE eam.sentiment = -1) as "👎 부정"
    FROM expert_article_mentions eam
    JOIN expert_articles ea ON ea.id = eam.article_id
    JOIN expert_sources es ON es.id = ea.source_id
    WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
    GROUP BY {{date_grp}} ORDER BY 1
"""

SQL_TOP10 = """
    SELECT t.name as "종목", COUNT(*) as "언급 수"
    FROM expert_article_mentions eam
    JOIN tickers t ON t.id = eam.ticker_id
    JOIN expert_articles ea ON ea.id = eam.article_id
    JOIN expert_sources es ON es.id = ea.source_id
    WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
    GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
"""

SQL_SURGE = """
    WITH recent AS (
        SELECT eam.ticker_id, COUNT(*) as cnt
        FROM expert_article_mentions eam
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
        GROUP BY eam.ticker_id
    ),
    prev AS (
        SELECT eam.ticker_id, COUNT(*) as cnt
        FROM expert_article_mentions eam
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
        GROUP BY eam.ticker_id
    )
    SELECT t.name as "종목",
           COALESCE(r.cnt, 0) as "최근",
           COALESCE(p.cnt, 0) as "이전",
           COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) as "변화량",
           CASE WHEN COALESCE(p.cnt, 0) > 0
                THEN ROUND(100.0 * (COALESCE(r.cnt,0) - p.cnt) / p.cnt, 1)
                ELSE NULL END as "변화율(%%)"
    FROM recent r
    FULL OUTER JOIN prev p ON r.ticker_id = p.ticker_id
    JOIN tickers t ON t.id = COALESCE(r.ticker_id, p.ticker_id)
    WHERE t.market NOT IN ('THEME', 'CRYPTO')
    ORDER BY COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) DESC
"""

SQL_MENTION_RANKING = """
    SELECT t.symbol as "심볼", t.name as "종목명", t.market as "시장",
           COUNT(*) as "총 언급",
           COUNT(*) FILTER (WHERE eam.sentiment = 1) as "👍 긍정",
           COUNT(*) FILTER (WHERE eam.sentiment = -1) as "👎 부정",
           COUNT(*) FILTER (WHERE eam.sentiment = 0) as "➖ 중립",
           ROUND(100.0 * COUNT(*) FILTER (WHERE eam.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as "📊 긍정률(%%)",
           ROUND(((AVG(eam.sentiment) + 1) * 50)::numeric, 1) as "🎯 감성 점수",
           ROUND(
               %s * COUNT(*) FILTER (WHERE eam.sentiment = 1) +
               %s * COUNT(*) FILTER (WHERE eam.sentiment = -1) +
               %s * COUNT(*) FILTER (WHERE eam.sentiment = 0)
           , 1) as "⭐ 가중 점수"
    FROM expert_article_mentions eam
    JOIN tickers t ON t.id = eam.ticker_id
    JOIN expert_articles ea ON ea.id = eam.article_id
    JOIN expert_sources es ON es.id = ea.source_id
    WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
    GROUP BY t.symbol, t.name, t.market
    ORDER BY "⭐ 가중 점수" DESC
"""

SQL_SOURCE_LIST = """
    SELECT DISTINCT ea.securities_firm FROM expert_articles ea
    JOIN expert_sources es ON es.id = ea.source_id
    WHERE ea.securities_firm IS NOT NULL AND ea.published_date BETWEEN %s AND %s
      AND es.source_type = 'article'
    ORDER BY ea.securities_firm
"""

SQL_ARTICLE_COUNT = """
    SELECT COUNT(*) as cnt FROM expert_articles ea
    JOIN expert_sources es ON es.id = ea.source_id
    WHERE {where}
"""

SQL_ARTICLE_LIST = """
    SELECT ea.published_date as "날짜", ea.title as "제목",
           ea.securities_firm as "언론사",
           t.name as "종목",
           ea.source_url as "링크"
    FROM expert_articles ea
    JOIN expert_sources es ON es.id = ea.source_id
    LEFT JOIN expert_article_mentions eam ON eam.article_id = ea.id
    LEFT JOIN tickers t ON t.id = eam.ticker_id
    WHERE {where}
    ORDER BY ea.published_date DESC, ea.id DESC
    LIMIT %s OFFSET %s
"""


# ─── 페이지 함수 ───────────────────────────────────────

def page_overview(start_date, end_date):
    """📈 뉴스 개요"""
    page_header("📰 뉴스 대시보드", "Google News 기사 감성 분석")

    # 기간 선택
    from datetime import timedelta
    period = period_tabs("news_period")
    days = PERIOD_DAYS[period]
    period_start = max(start_date, end_date - timedelta(days=days))
    date_sel = PERIOD_SQL[period]["select"].format(date_col="ea.published_date")
    date_grp = PERIOD_SQL[period]["group"].format(date_col="ea.published_date")

    kpi = run_query(SQL_KPI, (period_start, end_date) * 4)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📰 총 기사", f"{kpi['total_articles'].iloc[0]:,}")
    c2.metric("📌 종목 수", f"{kpi['unique_tickers'].iloc[0]}")
    pos = kpi['pos_cnt'].iloc[0]
    total_op = pos + kpi['other_cnt'].iloc[0]
    pos_pct = round(100 * pos / total_op, 1) if total_op > 0 else 0
    c3.metric("👍 긍정률", f"{pos_pct}%")
    c4.metric("💬 총 언급", f"{(pos + kpi['other_cnt'].iloc[0]):,}")

    # 감성 변화 추이
    st.subheader("📈 감성 변화 추이")
    query = SQL_SENTIMENT_TREND.replace("{{date_sel}}", date_sel).replace("{{date_grp}}", date_grp)
    trend = run_query(query, (start_date, end_date))
    if not trend.empty:
        render_colored_line_chart(trend)

    # TOP 10 언급 종목
    from datetime import timedelta
    top_end = end_date
    top_start = max(start_date, top_end - timedelta(days=PERIOD_DAYS[period]))
    st.subheader("🔥 TOP 10 언급 종목")
    top = run_query(SQL_TOP10, (top_start, top_end))
    render_top10_chart(top)


def page_surge_ranking(start_date, end_date):
    """🚀 급상승 랭킹"""
    render_surge_page(
        title="🚀 뉴스 급상승 종목",
        query_template=SQL_SURGE,
        period_key="news_surge_period",
        end_date=end_date,
        start_date=start_date,
        page_key="pg_news_surge",
    )


def page_mention_ranking(start_date, end_date):
    """📊 뉴스 언급량 랭킹"""
    page_header("📊 뉴스 언급량 랭킹", "기간별 뉴스 종목 언급 빈도 및 감성 점수 랭킹")

    from datetime import timedelta
    period = period_tabs("news_ranking_period", include_daily=True)
    days = PERIOD_DAYS[period]
    period_start = max(start_date, end_date - timedelta(days=days))

    ranking = run_query(SQL_MENTION_RANKING, (
        SCORE_WEIGHT_POSITIVE, SCORE_WEIGHT_NEGATIVE, SCORE_WEIGHT_NEUTRAL,
        period_start, end_date,
    ))

    if not ranking.empty:
        paginated_dataframe(ranking, "pg_news_mention_ranking")
    else:
        st.info("데이터가 없습니다.")


def page_article_list(start_date, end_date):
    """📋 뉴스 목록"""
    page_header("📋 뉴스 목록", "수집된 뉴스 기사 원문 목록")

    PAGE_SIZE = 25

    if "news_page" not in st.session_state:
        st.session_state.news_page = 0

    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔎 제목 검색", placeholder="종목명 또는 키워드", key="news_search")
    with col2:
        sources = run_query(SQL_SOURCE_LIST, (start_date, end_date))
        source_list = ["전체"] + sources["securities_firm"].tolist()
        selected_source = st.selectbox("📰 언론사", source_list, key="news_source")

    # 쿼리 조건
    conditions = ["ea.published_date BETWEEN %s AND %s", "es.source_type = 'article'"]
    params = [start_date, end_date]

    if search:
        conditions.append("ea.title ILIKE %s")
        params.append(f"%{search}%")
    if selected_source != "전체":
        conditions.append("ea.securities_firm = %s")
        params.append(selected_source)

    where = " AND ".join(conditions)

    count_df = run_query(SQL_ARTICLE_COUNT.format(where=where), params)
    total = int(count_df["cnt"].iloc[0]) if len(count_df) > 0 else 0

    page = st.session_state.news_page
    offset = page * PAGE_SIZE
    query_params = params + [PAGE_SIZE, offset]

    df = run_query(SQL_ARTICLE_LIST.format(where=where), query_params)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    st.dataframe(
        df, use_container_width=True, hide_index=True, height=700,
        column_config={
            "날짜": st.column_config.DateColumn("날짜", width="small"),
            "제목": st.column_config.TextColumn("제목", width="large"),
            "언론사": st.column_config.TextColumn("언론사", width="small"),
            "종목": st.column_config.TextColumn("종목", width="small"),
            "링크": st.column_config.LinkColumn("링크", display_text="🔗", width="small"),
        }
    )

    pagination_bar(page, total_pages, "news_page", "news")
