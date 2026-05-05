"""
커뮤니티 페이지 모듈 - 대중 의견 분석
"""

import streamlit as st
from datetime import timedelta
from lib.shared import run_query, navigate_to, paginated_dataframe, period_tabs, PERIOD_OPTIONS, PERIOD_SQL, PERIOD_DAYS, SCORE_WEIGHT_POSITIVE, SCORE_WEIGHT_NEGATIVE, SCORE_WEIGHT_NEUTRAL


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

    # 기간 선택
    period = period_tabs("comm_period")
    date_sel = PERIOD_SQL[period]["select"].format(date_col="p.post_date")
    date_grp = PERIOD_SQL[period]["group"].format(date_col="p.post_date")

    # 감성 변화 추이
    st.subheader("📈 감성 변화 추이")
    sentiment_trend = run_query(f"""
        SELECT {date_sel} as "날짜",
               COUNT(*) FILTER (WHERE pm.sentiment = 1) as "👍 긍정",
               COUNT(*) FILTER (WHERE pm.sentiment = 0) as "➖ 중립",
               COUNT(*) FILTER (WHERE pm.sentiment = -1) as "👎 부정"
        FROM post_mentions pm
        JOIN posts p ON p.id = pm.post_id
        WHERE p.post_date BETWEEN %s AND %s
        GROUP BY {date_grp} ORDER BY 1
    """, (start_date, end_date))
    if not sentiment_trend.empty:
        st.line_chart(sentiment_trend.set_index("날짜"))

    st.markdown("---")

    # TOP 10 언급 종목 (선택한 기간 기준)
    from datetime import date as _date
    top_end = end_date
    top_start = max(start_date, top_end - timedelta(days=PERIOD_DAYS[period]))
    st.subheader("🔥 TOP 10 언급 종목")
    top_tickers = run_query("""
        SELECT t.name as "종목", COUNT(*) as "언급 수"
        FROM post_mentions pm
        JOIN tickers t ON t.id = pm.ticker_id
        JOIN posts p ON p.id = pm.post_id
        WHERE p.post_date BETWEEN %s AND %s
          AND t.market NOT IN ('THEME', 'CRYPTO')
        GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
    """, (top_start, top_end))
    if not top_tickers.empty:
        import altair as alt
        chart = alt.Chart(top_tickers).mark_bar().encode(
            x=alt.X("언급 수:Q"),
            y=alt.Y("종목:N", sort="-x"),
        ).properties(height=350)
        st.altair_chart(chart, use_container_width=True)


def page_mention_ranking(start_date, end_date):
    """📊 언급량 랭킹"""
    st.title("📊 종목 언급량 랭킹")

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
    """, (SCORE_WEIGHT_POSITIVE, SCORE_WEIGHT_NEGATIVE, SCORE_WEIGHT_NEUTRAL,
          start_date, end_date))

    if not ranking.empty:
        paginated_dataframe(ranking, "pg_mention_ranking")
    else:
        st.info("데이터가 없습니다.")


def page_surge_ranking(start_date, end_date):
    """🚀 급상승 랭킹"""
    st.title("🚀 급상승 종목 랭킹")

    period = period_tabs("surge_period")
    days = PERIOD_DAYS[period]

    recent_end = end_date
    recent_start = end_date - timedelta(days=days - 1)
    prev_end = recent_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    st.caption(f"최근: {recent_start} ~ {recent_end}  vs  이전: {prev_start} ~ {prev_end}")

    surge = run_query("""
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
    """, (recent_start, recent_end, prev_start, prev_end))

    if not surge.empty:
        paginated_dataframe(surge, "pg_surge_ranking")
    else:
        st.info("비교할 데이터가 부족합니다.")


def page_author_ranking(start_date, end_date):
    """👤 작성자 랭킹"""
    st.title("👤 활발한 작성자 랭킹")

    authors = run_query("""
        SELECT author as "작성자", COUNT(*) as "게시글 수"
        FROM posts
        WHERE post_date BETWEEN %s AND %s
        GROUP BY author ORDER BY COUNT(*) DESC
    """, (start_date, end_date))
    paginated_dataframe(authors, "pg_author_ranking")


def page_post_list(start_date, end_date):
    """📋 게시글 목록"""
    st.title("📋 게시글 목록")

    PAGE_SIZE = 25

    # 랭킹에서 종목 필터로 넘어온 경우
    filter_symbol = st.session_state.nav_filter_symbol
    if filter_symbol:
        st.session_state.nav_filter_symbol = None

    # 페이지 상태 초기화
    if "posts_page" not in st.session_state:
        st.session_state.posts_page = 0

    default_keyword = st.session_state.nav_search_keyword or ""

    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔎 제목 검색", value=default_keyword, placeholder="검색어를 입력하세요")
    with col2:
        comms = run_query("""
            SELECT DISTINCT c.name FROM communities c
            JOIN posts p ON p.community_id = c.id
            WHERE p.post_date BETWEEN %s AND %s
            ORDER BY c.name
        """, (start_date, end_date))
        comm_list = ["전체"] + comms["name"].tolist()
        selected_comm = st.selectbox("📢 커뮤니티", comm_list, key="posts_comm")

    if st.session_state.nav_search_keyword:
        st.session_state.nav_search_keyword = None

    page = st.session_state.posts_page
    offset = page * PAGE_SIZE

    # 동적 쿼리 조건
    conditions = ["p.post_date BETWEEN %s AND %s"]
    params = [start_date, end_date]

    if filter_symbol:
        st.info(f"🎯 종목 필터: {filter_symbol}")
        conditions.append("t_filter.symbol = %s")
        params.append(filter_symbol)
    if search:
        conditions.append("p.title ILIKE %s")
        params.append(f"%{search}%")
    if selected_comm != "전체":
        conditions.append("c.name = %s")
        params.append(selected_comm)

    where = " AND ".join(conditions)

    # 총 건수
    if filter_symbol:
        count_df = run_query(f"""
            SELECT COUNT(DISTINCT p.id) as cnt
            FROM posts p
            JOIN communities c ON c.id = p.community_id
            JOIN post_mentions pm ON pm.post_id = p.id
            JOIN tickers t_filter ON t_filter.id = pm.ticker_id
            WHERE {where}
        """, params)
    else:
        count_df = run_query(f"""
            SELECT COUNT(*) as cnt
            FROM posts p
            JOIN communities c ON c.id = p.community_id
            WHERE {where}
        """, params)
    total = int(count_df["cnt"].iloc[0]) if len(count_df) > 0 else 0

    # 데이터 조회
    query_params = params + [PAGE_SIZE, offset]
    if filter_symbol:
        posts_df = run_query(f"""
            SELECT p.post_date as "날짜", c.name as "커뮤니티", p.title as "제목", p.author as "작성자",
                   STRING_AGG(DISTINCT t2.name, ', ') as "언급 종목",
                   p.source_url as "링크"
            FROM posts p
            JOIN communities c ON c.id = p.community_id
            JOIN post_mentions pm ON pm.post_id = p.id
            JOIN tickers t_filter ON t_filter.id = pm.ticker_id
            LEFT JOIN post_mentions pm2 ON pm2.post_id = p.id
            LEFT JOIN tickers t2 ON t2.id = pm2.ticker_id
            WHERE {where}
            GROUP BY p.id, p.post_date, c.name, p.title, p.author, p.source_url
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s OFFSET %s
        """, query_params)
    else:
        posts_df = run_query(f"""
            SELECT p.post_date as "날짜", c.name as "커뮤니티", p.title as "제목", p.author as "작성자",
                   STRING_AGG(t.name, ', ') as "언급 종목",
                   p.source_url as "링크"
            FROM posts p
            JOIN communities c ON c.id = p.community_id
            LEFT JOIN post_mentions pm ON pm.post_id = p.id
            LEFT JOIN tickers t ON t.id = pm.ticker_id
            WHERE {where}
            GROUP BY p.id, p.post_date, c.name, p.title, p.author, p.source_url
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s OFFSET %s
        """, query_params)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    st.dataframe(
        posts_df, use_container_width=True, hide_index=True, height=700,
        column_config={
            "날짜": st.column_config.DateColumn("날짜", width="small"),
            "커뮤니티": st.column_config.TextColumn("커뮤니티", width="small"),
            "제목": st.column_config.TextColumn("제목", width="large"),
            "작성자": st.column_config.TextColumn("작성자", width="small"),
            "언급 종목": st.column_config.TextColumn("언급 종목", width="medium"),
            "링크": st.column_config.LinkColumn("링크", display_text="🔗", width="small"),
        }
    )

    # 페이지 네비게이션
    _, col_prev, col_info, col_next, _ = st.columns([2, 1, 1, 1, 2])
    with col_prev:
        if st.button("⬅️ 이전", disabled=(page == 0), key="posts_prev", use_container_width=True):
            st.session_state.posts_page = page - 1
            st.rerun()
    with col_info:
        st.markdown(f"<div style='text-align:center;padding:0.4rem 0;color:#888;'>{page + 1} / {total_pages}</div>", unsafe_allow_html=True)
    with col_next:
        if st.button("다음 ➡️", disabled=(page >= total_pages - 1), key="posts_next", use_container_width=True):
            st.session_state.posts_page = page + 1
            st.rerun()

