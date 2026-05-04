"""
커뮤니티 페이지 모듈 - 대중 의견 분석
"""

import streamlit as st
from datetime import timedelta
from lib.shared import run_query, SCORE_WEIGHT_POSITIVE, SCORE_WEIGHT_NEGATIVE, SCORE_WEIGHT_NEUTRAL


def page_overview(start_date, end_date):
    """📈 커뮤니티 개요"""
    st.title("📢 커뮤니티 대시보드")
    st.caption("커뮤니티 주식 언급량 분석 (대중 의견)")

    # KPI 카드
    kpi = run_query("""
        SELECT
            (SELECT COUNT(*) FROM posts WHERE post_date BETWEEN %s AND %s) as total_posts,
            (SELECT COUNT(*) FROM post_mentions pm JOIN posts p ON p.id = pm.post_id
             WHERE p.post_date BETWEEN %s AND %s) as total_mentions,
            (SELECT COUNT(DISTINCT pm.ticker_id) FROM post_mentions pm JOIN posts p ON p.id = pm.post_id
             WHERE p.post_date BETWEEN %s AND %s) as unique_tickers,
            (SELECT COUNT(DISTINCT p.author) FROM posts p
             WHERE p.post_date BETWEEN %s AND %s) as unique_authors
    """, (start_date, end_date, start_date, end_date, start_date, end_date, start_date, end_date))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📝 총 게시글", f"{kpi['total_posts'].iloc[0]:,}")
    col2.metric("💬 종목 언급", f"{kpi['total_mentions'].iloc[0]:,}")
    col3.metric("📌 언급 종목 수", f"{kpi['unique_tickers'].iloc[0]}")
    col4.metric("👤 작성자 수", f"{kpi['unique_authors'].iloc[0]:,}")

    st.markdown("---")

    # 일별 게시글 수 + 종목 언급 수 차트
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📊 일별 게시글 수")
        daily_posts = run_query("""
            SELECT post_date as "날짜", COUNT(*) as "게시글 수"
            FROM posts
            WHERE post_date BETWEEN %s AND %s
            GROUP BY post_date ORDER BY post_date
        """, (start_date, end_date))
        if not daily_posts.empty:
            st.line_chart(daily_posts.set_index("날짜"))

    with col_right:
        st.subheader("💬 일별 종목 언급 수")
        daily_mentions = run_query("""
            SELECT p.post_date as "날짜", COUNT(*) as "언급 수"
            FROM post_mentions pm
            JOIN posts p ON p.id = pm.post_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY p.post_date ORDER BY p.post_date
        """, (start_date, end_date))
        if not daily_mentions.empty:
            st.line_chart(daily_mentions.set_index("날짜"))

    st.markdown("---")

    # 감성 분포
    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.subheader("😊 전체 감성 분포")
        sentiment = run_query("""
            SELECT
                CASE pm.sentiment
                    WHEN 1 THEN '👍 긍정'
                    WHEN -1 THEN '👎 부정'
                    ELSE '➖ 중립'
                END as "감성",
                COUNT(*) as "건수"
            FROM post_mentions pm
            JOIN posts p ON p.id = pm.post_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY pm.sentiment ORDER BY pm.sentiment DESC
        """, (start_date, end_date))
        if not sentiment.empty:
            st.bar_chart(sentiment.set_index("감성"))

    with col_right2:
        st.subheader("🔥 TOP 10 언급 종목")
        top_tickers = run_query("""
            SELECT t.name as "종목", COUNT(*) as "언급 수"
            FROM post_mentions pm
            JOIN tickers t ON t.id = pm.ticker_id
            JOIN posts p ON p.id = pm.post_id
            WHERE p.post_date BETWEEN %s AND %s
              AND t.market NOT IN ('THEME', 'CRYPTO')
            GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
        """, (start_date, end_date))
        if not top_tickers.empty:
            st.bar_chart(top_tickers.set_index("종목"))


def page_mention_ranking(start_date, end_date):
    """📊 언급량 랭킹"""
    st.title("📊 종목 언급량 랭킹")

    rank_limit_options = {"30건": 30, "50건": 50, "100건": 100, "전체": 9999}
    rank_limit_label = st.selectbox("표시 건수", list(rank_limit_options.keys()))
    rank_limit = rank_limit_options[rank_limit_label]

    ranking = run_query("""
        SELECT t.symbol as "심볼", t.name as "종목명", t.market as "시장",
               COUNT(*) as "총 언급",
               COUNT(*) FILTER (WHERE pm.sentiment = 1) as "👍 긍정",
               COUNT(*) FILTER (WHERE pm.sentiment = -1) as "👎 부정",
               COUNT(*) FILTER (WHERE pm.sentiment = 0) as "➖ 중립",
               ROUND(100.0 * COUNT(*) FILTER (WHERE pm.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as "📊 긍정률(%%)",
               ROUND(((AVG(pm.sentiment) + 1) * 50)::numeric, 1) as "🎯 감성 점수",
               ROUND(
                   %s * COUNT(*) FILTER (WHERE pm.sentiment = 1) +
                   %s * COUNT(*) FILTER (WHERE pm.sentiment = -1) +
                   %s * COUNT(*) FILTER (WHERE pm.sentiment = 0)
               , 1) as "⭐ 가중 점수"
        FROM post_mentions pm
        JOIN tickers t ON t.id = pm.ticker_id
        JOIN posts p ON p.id = pm.post_id
        WHERE p.post_date BETWEEN %s AND %s
        GROUP BY t.symbol, t.name, t.market
        ORDER BY "⭐ 가중 점수" DESC
        LIMIT %s
    """, (SCORE_WEIGHT_POSITIVE, SCORE_WEIGHT_NEGATIVE, SCORE_WEIGHT_NEUTRAL,
          start_date, end_date, rank_limit))

    if not ranking.empty:
        st.dataframe(ranking, use_container_width=True, hide_index=True, height=800)
    else:
        st.info("데이터가 없습니다.")


def page_surge_ranking(start_date, end_date):
    """🚀 급상승 랭킹"""
    st.title("🚀 급상승 종목 랭킹")

    col1, col2 = st.columns(2)
    with col1:
        PERIOD_OPTIONS = {"3일간": 3, "주간 (7일)": 7, "월간 (30일)": 30}
        period_label = st.selectbox("📅 비교 기간", list(PERIOD_OPTIONS.keys()))
        days = PERIOD_OPTIONS[period_label]
    with col2:
        surge_limit_opts = {"20건": 20, "50건": 50, "100건": 100, "전체": 9999}
        surge_limit_label = st.selectbox("표시 건수", list(surge_limit_opts.keys()), key="surge_limit")
        surge_limit = surge_limit_opts[surge_limit_label]

    recent_end = end_date
    recent_start = end_date - timedelta(days=days - 1)
    prev_end = recent_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    st.caption(f"최근: {recent_start} ~ {recent_end}  vs  이전: {prev_start} ~ {prev_end}")

    recent_label = f"최근 {days}일"
    prev_label = f"이전 {days}일"

    surge = run_query(f"""
        WITH recent AS (
            SELECT pm.ticker_id, COUNT(*) as cnt
            FROM post_mentions pm JOIN posts p ON p.id = pm.post_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY pm.ticker_id
        ),
        prev AS (
            SELECT pm.ticker_id, COUNT(*) as cnt
            FROM post_mentions pm JOIN posts p ON p.id = pm.post_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY pm.ticker_id
        )
        SELECT t.name as "종목",
               COALESCE(r.cnt, 0) as "{recent_label}",
               COALESCE(p.cnt, 0) as "{prev_label}",
               COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) as "변화량",
               CASE WHEN COALESCE(p.cnt, 0) > 0
                    THEN ROUND(100.0 * (COALESCE(r.cnt,0) - p.cnt) / p.cnt, 1)
                    ELSE NULL END as "변화율(%%)"
        FROM recent r
        FULL OUTER JOIN prev p ON r.ticker_id = p.ticker_id
        JOIN tickers t ON t.id = COALESCE(r.ticker_id, p.ticker_id)
        WHERE t.market NOT IN ('THEME', 'CRYPTO')
        ORDER BY COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) DESC
        LIMIT %s
    """, (recent_start, recent_end, prev_start, prev_end, surge_limit))

    if not surge.empty:
        st.dataframe(surge, use_container_width=True, hide_index=True, height=800)
    else:
        st.info("비교할 데이터가 부족합니다.")


def page_author_ranking(start_date, end_date):
    """👤 작성자 랭킹"""
    st.title("👤 활발한 작성자 랭킹")

    author_limit_opts = {"20건": 20, "50건": 50, "100건": 100, "전체": 9999}
    author_limit_label = st.selectbox("표시 건수", list(author_limit_opts.keys()), key="author_limit")
    author_limit = author_limit_opts[author_limit_label]

    authors = run_query("""
        SELECT author as "작성자", COUNT(*) as "게시글 수"
        FROM posts
        WHERE post_date BETWEEN %s AND %s
        GROUP BY author ORDER BY COUNT(*) DESC LIMIT %s
    """, (start_date, end_date, author_limit))
    st.dataframe(authors, use_container_width=True, hide_index=True, height=800)


def page_post_list(start_date, end_date):
    """📋 게시글 목록"""
    st.title("📋 게시글 목록")

    # 랭킹에서 종목 필터로 넘어온 경우
    filter_symbol = st.session_state.nav_filter_symbol
    if filter_symbol:
        st.session_state.nav_filter_symbol = None

    col1, col2 = st.columns([3, 1])
    with col1:
        default_keyword = st.session_state.nav_search_keyword or ""
        search = st.text_input("🔎 제목 검색", value=default_keyword, placeholder="검색어를 입력하세요")
        if st.session_state.nav_search_keyword:
            st.session_state.nav_search_keyword = None
    with col2:
        limit = st.selectbox("표시 건수", [50, 100, 200, 500], index=0)

    if filter_symbol:
        # 종목 심볼로 post_mentions 조인 필터
        st.info(f"🎯 종목 필터: {filter_symbol}")
        posts_df = run_query("""
            SELECT p.post_date as "날짜", c.name as "커뮤니티", p.title as "제목", p.author as "작성자",
                   STRING_AGG(DISTINCT t2.name, ', ') as "언급 종목",
                   p.source_url as "링크"
            FROM posts p
            JOIN communities c ON c.id = p.community_id
            JOIN post_mentions pm ON pm.post_id = p.id
            JOIN tickers t ON t.id = pm.ticker_id AND t.symbol = %s
            LEFT JOIN post_mentions pm2 ON pm2.post_id = p.id
            LEFT JOIN tickers t2 ON t2.id = pm2.ticker_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY p.id, p.post_date, c.name, p.title, p.author, p.source_url
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s
        """, (filter_symbol, start_date, end_date, limit))
    elif search:
        posts_df = run_query("""
            SELECT p.post_date as "날짜", c.name as "커뮤니티", p.title as "제목", p.author as "작성자",
                   STRING_AGG(t.name, ', ') as "언급 종목",
                   p.source_url as "링크"
            FROM posts p
            JOIN communities c ON c.id = p.community_id
            LEFT JOIN post_mentions pm ON pm.post_id = p.id
            LEFT JOIN tickers t ON t.id = pm.ticker_id
            WHERE p.post_date BETWEEN %s AND %s
              AND p.title ILIKE %s
            GROUP BY p.id, p.post_date, c.name, p.title, p.author, p.source_url
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s
        """, (start_date, end_date, f"%{search}%", limit))
    else:
        posts_df = run_query("""
            SELECT p.post_date as "날짜", c.name as "커뮤니티", p.title as "제목", p.author as "작성자",
                   STRING_AGG(t.name, ', ') as "언급 종목",
                   p.source_url as "링크"
            FROM posts p
            JOIN communities c ON c.id = p.community_id
            LEFT JOIN post_mentions pm ON pm.post_id = p.id
            LEFT JOIN tickers t ON t.id = pm.ticker_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY p.id, p.post_date, c.name, p.title, p.author, p.source_url
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s
        """, (start_date, end_date, limit))

    st.caption(f"총 {len(posts_df)}건 표시")
    st.dataframe(
        posts_df, use_container_width=True, hide_index=True, height=800,
        column_config={
            "날짜": st.column_config.DateColumn("날짜", width="small"),
            "커뮤니티": st.column_config.TextColumn("커뮤니티", width="small"),
            "제목": st.column_config.TextColumn("제목", width="large"),
            "작성자": st.column_config.TextColumn("작성자", width="small"),
            "언급 종목": st.column_config.TextColumn("언급 종목", width="medium"),
            "링크": st.column_config.LinkColumn("링크", display_text="🔗", width="small"),
        }
    )

