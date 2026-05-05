"""
종합 페이지 모듈 - 교차 분석 및 종목 검색
"""

import streamlit as st
from lib.shared import run_query, paginated_dataframe, period_tabs, render_top10_chart, render_colored_line_chart, PERIOD_DAYS


def page_dashboard(start_date, end_date):
    """🏠 종합 대시보드"""
    st.title("🏠 종합 대시보드")
    st.caption("커뮤니티 · 전문가 · 뉴스 교차 분석")

    from datetime import timedelta

    period = period_tabs("combined_period")
    days = PERIOD_DAYS[period]
    period_start = max(start_date, end_date - timedelta(days=days))

    # KPI
    kpi_all = run_query("""
        SELECT
            (SELECT COUNT(*) FROM posts WHERE post_date BETWEEN %s AND %s) as comm_posts,
            (SELECT COUNT(*) FROM expert_articles ea
             JOIN expert_sources es ON es.id = ea.source_id
             WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report') as expert_reports,
            (SELECT COUNT(*) FROM expert_articles ea
             JOIN expert_sources es ON es.id = ea.source_id
             WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article') as news_articles
    """, (period_start, end_date, period_start, end_date, period_start, end_date))

    c1, c2, c3 = st.columns(3)
    c1.metric("📢 커뮤니티 게시글", f"{kpi_all['comm_posts'].iloc[0]:,}")
    c2.metric("🔬 전문가 리포트", f"{kpi_all['expert_reports'].iloc[0]:,}")
    c3.metric("📰 뉴스 기사", f"{kpi_all['news_articles'].iloc[0]:,}")

    st.markdown("---")

    # 종목별 교차 분석
    st.subheader("🔀 종목별 비교")
    cross = run_query("""
        WITH comm_mentions AS (
            SELECT pm.ticker_id, COUNT(*) as comm_cnt,
                   ROUND(((AVG(pm.sentiment) + 1) * 50)::numeric, 1) as comm_sentiment
            FROM post_mentions pm JOIN posts p ON p.id = pm.post_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY pm.ticker_id
        ),
        expert_mentions AS (
            SELECT eam.ticker_id, COUNT(*) as expert_cnt,
                   ROUND(((AVG(eam.sentiment) + 1) * 50)::numeric, 1) as expert_sentiment
            FROM expert_article_mentions eam
            JOIN expert_articles ea ON ea.id = eam.article_id
            JOIN expert_sources es ON es.id = ea.source_id
            WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
            GROUP BY eam.ticker_id
        ),
        news_mentions AS (
            SELECT eam.ticker_id, COUNT(*) as news_cnt,
                   ROUND(((AVG(eam.sentiment) + 1) * 50)::numeric, 1) as news_sentiment
            FROM expert_article_mentions eam
            JOIN expert_articles ea ON ea.id = eam.article_id
            JOIN expert_sources es ON es.id = ea.source_id
            WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
            GROUP BY eam.ticker_id
        )
        SELECT t.name as "종목",
               COALESCE(c.comm_cnt, 0) as "커뮤니티 언급",
               COALESCE(e.expert_cnt, 0) as "전문가 리포트",
               COALESCE(n.news_cnt, 0) as "뉴스",
               c.comm_sentiment as "대중 감성",
               e.expert_sentiment as "전문가 감성",
               n.news_sentiment as "뉴스 감성"
        FROM comm_mentions c
        FULL OUTER JOIN expert_mentions e ON c.ticker_id = e.ticker_id
        FULL OUTER JOIN news_mentions n ON COALESCE(c.ticker_id, e.ticker_id) = n.ticker_id
        JOIN tickers t ON t.id = COALESCE(c.ticker_id, e.ticker_id, n.ticker_id)
        WHERE t.market NOT IN ('THEME', 'CRYPTO')
        ORDER BY COALESCE(c.comm_cnt, 0) + COALESCE(e.expert_cnt, 0) + COALESCE(n.news_cnt, 0) DESC
        LIMIT 30
    """, (period_start, end_date, period_start, end_date, period_start, end_date))

    if not cross.empty:
        paginated_dataframe(cross, "pg_cross_analysis")

    st.markdown("---")

    # TOP 10 차트 3개 (세로 배치)
    st.subheader("🔥 채널별 TOP 10 종목")

    st.markdown("**📢 커뮤니티**")
    comm_top = run_query("""
        SELECT t.name as "종목", COUNT(*) as "언급 수"
        FROM post_mentions pm
        JOIN tickers t ON t.id = pm.ticker_id
        JOIN posts p ON p.id = pm.post_id
        WHERE p.post_date BETWEEN %s AND %s AND t.market NOT IN ('THEME', 'CRYPTO')
        GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
    """, (period_start, end_date))
    render_top10_chart(comm_top, height=300)

    st.markdown("**🔬 리포트**")
    expert_top = run_query("""
        SELECT t.name as "종목", COUNT(*) as "언급 수"
        FROM expert_article_mentions eam
        JOIN tickers t ON t.id = eam.ticker_id
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
        GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
    """, (period_start, end_date))
    render_top10_chart(expert_top, height=300)

    st.markdown("**📰 뉴스**")
    news_top = run_query("""
        SELECT t.name as "종목", COUNT(*) as "언급 수"
        FROM expert_article_mentions eam
        JOIN tickers t ON t.id = eam.ticker_id
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
        GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
    """, (period_start, end_date))
    render_top10_chart(news_top, height=300)


def page_ticker_search(start_date, end_date):
    """🔍 종목 검색"""
    st.title("🔍 종목 검색")

    # 한글 별칭 매핑 (검색용)
    ALIAS_MAP = {
        "삼성전자": "005930", "삼전": "005930",
        "SK하이닉스": "000660", "하이닉스": "000660", "하닉": "000660",
        "네이버": "035420", "카카오": "035720",
        "현대차": "005380", "기아": "000270",
        "한화": "000880", "셀트리온": "068270",
        "애플": "AAPL", "구글": "GOOGL", "아마존": "AMZN",
        "테슬라": "TSLA", "엔비디아": "NVDA", "마이크론": "MU",
        "인텔": "INTC", "넷플릭스": "NFLX", "메타": "META",
        "샌디스크": "SNDK", "시게이트": "STX",
        "브로드컴": "AVGO", "팔란티어": "PLTR", "소파이": "SOFI",
        "디즈니": "DIS", "보잉": "BA", "코스트코": "COST",
    }

    # 종목 목록 가져오기 (3채널 중 하나라도 언급된 것)
    ticker_list = run_query("""
        SELECT DISTINCT t.id, t.symbol, t.name, t.market
        FROM tickers t
        WHERE t.id IN (
            SELECT pm.ticker_id FROM post_mentions pm
            UNION
            SELECT eam.ticker_id FROM expert_article_mentions eam
        )
        ORDER BY t.name
    """)

    if ticker_list.empty:
        st.warning("아직 언급된 종목이 없습니다.")
        return

    # 검색어 입력 (랭킹에서 이동 시 자동 채움)
    default_search = st.session_state.nav_ticker_symbol or ""
    search_term = st.text_input("🔎 종목명/별칭 검색", value=default_search, placeholder="예: 삼성전자, 마이크론, 샌디스크...")
    if st.session_state.nav_ticker_symbol:
        st.session_state.nav_ticker_symbol = None  # 사용 후 초기화

    # 별칭으로 심볼 찾기
    matched_symbol = ALIAS_MAP.get(search_term.strip())

    # 필터링
    if search_term:
        if matched_symbol:
            filtered = ticker_list[ticker_list['symbol'] == matched_symbol]
        else:
            mask = (
                ticker_list['name'].str.contains(search_term, case=False, na=False) |
                ticker_list['symbol'].str.contains(search_term, case=False, na=False)
            )
            filtered = ticker_list[mask]
    else:
        filtered = ticker_list

    options = {f"{row['name']} ({row['symbol']})": row['id']
               for _, row in filtered.iterrows()}

    if not options:
        st.warning(f"'{search_term}'에 해당하는 종목이 없습니다.")
        return

    selected = st.selectbox("종목 선택", list(options.keys()))
    ticker_id = int(options[selected])

    # 기간 선택 (집계 단위: 일별/주별/월별/연별)
    from lib.shared import PERIOD_SQL
    period = period_tabs("ticker_search_period")
    date_sel_comm = PERIOD_SQL[period]["select"].format(date_col="p.post_date")
    date_grp_comm = PERIOD_SQL[period]["group"].format(date_col="p.post_date")
    date_sel_expert = PERIOD_SQL[period]["select"].format(date_col="ea.published_date")
    date_grp_expert = PERIOD_SQL[period]["group"].format(date_col="ea.published_date")

    st.markdown("---")

    # ── 채널별 수치 테이블 ──
    st.subheader("📊 채널별 수치 비교")
    stats = run_query("""
        SELECT '커뮤니티' as "채널",
               COUNT(*) as "총 언급",
               COUNT(*) FILTER (WHERE pm.sentiment = 1) as "👍 긍정",
               COUNT(*) FILTER (WHERE pm.sentiment = -1) as "👎 부정",
               COUNT(*) FILTER (WHERE pm.sentiment = 0) as "➖ 중립",
               ROUND(100.0 * COUNT(*) FILTER (WHERE pm.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as "긍정률(%%)",
               ROUND(((AVG(pm.sentiment) + 1) * 50)::numeric, 1) as "감성 점수"
        FROM post_mentions pm
        JOIN posts p ON p.id = pm.post_id
        WHERE pm.ticker_id = %s AND p.post_date BETWEEN %s AND %s

        UNION ALL

        SELECT '리포트',
               COUNT(*),
               COUNT(*) FILTER (WHERE eam.sentiment = 1),
               COUNT(*) FILTER (WHERE eam.sentiment = -1),
               COUNT(*) FILTER (WHERE eam.sentiment = 0),
               ROUND(100.0 * COUNT(*) FILTER (WHERE eam.sentiment = 1) / NULLIF(COUNT(*), 0), 1),
               ROUND(((AVG(eam.sentiment) + 1) * 50)::numeric, 1)
        FROM expert_article_mentions eam
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE eam.ticker_id = %s AND ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'

        UNION ALL

        SELECT '뉴스',
               COUNT(*),
               COUNT(*) FILTER (WHERE eam.sentiment = 1),
               COUNT(*) FILTER (WHERE eam.sentiment = -1),
               COUNT(*) FILTER (WHERE eam.sentiment = 0),
               ROUND(100.0 * COUNT(*) FILTER (WHERE eam.sentiment = 1) / NULLIF(COUNT(*), 0), 1),
               ROUND(((AVG(eam.sentiment) + 1) * 50)::numeric, 1)
        FROM expert_article_mentions eam
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE eam.ticker_id = %s AND ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
    """, (ticker_id, start_date, end_date,
          ticker_id, start_date, end_date,
          ticker_id, start_date, end_date))

    if not stats.empty:
        st.dataframe(stats, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 커뮤니티 언급량 ──
    st.subheader("📢 커뮤니티 언급량")
    comm_trend = run_query(f"""
        SELECT {date_sel_comm} as "날짜",
               COUNT(*) as "전체",
               COUNT(*) FILTER (WHERE pm.sentiment = 1) as "긍정",
               COUNT(*) FILTER (WHERE pm.sentiment = -1) as "부정",
               COUNT(*) FILTER (WHERE pm.sentiment = 0) as "중립"
        FROM post_mentions pm
        JOIN posts p ON p.id = pm.post_id
        WHERE pm.ticker_id = %s AND p.post_date BETWEEN %s AND %s
        GROUP BY {date_grp_comm} ORDER BY 1
    """, (ticker_id, start_date, end_date))
    if not comm_trend.empty:
        render_colored_line_chart(comm_trend)
    else:
        st.info("커뮤니티 언급 데이터가 없습니다.")

    st.markdown("---")

    # ── 리포트 언급량 ──
    st.subheader("🔬 리포트 언급량")
    rpt_trend = run_query(f"""
        SELECT {date_sel_expert} as "날짜",
               COUNT(*) as "전체",
               COUNT(*) FILTER (WHERE eam.sentiment = 1) as "긍정",
               COUNT(*) FILTER (WHERE eam.sentiment = -1) as "부정",
               COUNT(*) FILTER (WHERE eam.sentiment = 0) as "중립"
        FROM expert_article_mentions eam
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE eam.ticker_id = %s AND ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
        GROUP BY {date_grp_expert} ORDER BY 1
    """, (ticker_id, start_date, end_date))
    if not rpt_trend.empty:
        render_colored_line_chart(rpt_trend)
    else:
        st.info("리포트 데이터가 없습니다.")

    st.markdown("---")

    # ── 뉴스 언급량 ──
    st.subheader("📰 뉴스 언급량")
    news_trend = run_query(f"""
        SELECT {date_sel_expert} as "날짜",
               COUNT(*) as "전체",
               COUNT(*) FILTER (WHERE eam.sentiment = 1) as "긍정",
               COUNT(*) FILTER (WHERE eam.sentiment = -1) as "부정",
               COUNT(*) FILTER (WHERE eam.sentiment = 0) as "중립"
        FROM expert_article_mentions eam
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE eam.ticker_id = %s AND ea.published_date BETWEEN %s AND %s AND es.source_type = 'article'
        GROUP BY {date_grp_expert} ORDER BY 1
    """, (ticker_id, start_date, end_date))
    if not news_trend.empty:
        render_colored_line_chart(news_trend)
    else:
        st.info("뉴스 데이터가 없습니다.")

