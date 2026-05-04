"""
종합 페이지 모듈 - 교차 분석 및 종목 검색
"""

import streamlit as st
from lib.shared import run_query, paginated_dataframe


def page_dashboard(start_date, end_date):
    """🏠 종합 대시보드"""
    st.title("🏠 종합 대시보드")
    st.caption("대중 의견(커뮤니티) vs 전문가 의견(증권사 리포트) 교차 분석")

    # KPI
    kpi_all = run_query("""
        SELECT
            (SELECT COUNT(*) FROM posts WHERE post_date BETWEEN %s AND %s) as comm_posts,
            (SELECT COUNT(*) FROM expert_articles WHERE published_date BETWEEN %s AND %s) as expert_reports
    """, (start_date, end_date, start_date, end_date))

    c1, c2 = st.columns(2)
    c1.metric("📢 커뮤니티 게시글", f"{kpi_all['comm_posts'].iloc[0]:,}")
    c2.metric("🔬 전문가 리포트", f"{kpi_all['expert_reports'].iloc[0]:,}")

    # 종목별 교차 분석
    st.subheader("🔀 종목별 대중 vs 전문가 비교")
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
            WHERE ea.published_date BETWEEN %s AND %s
            GROUP BY eam.ticker_id
        )
        SELECT t.name as "종목",
               COALESCE(c.comm_cnt, 0) as "커뮤니티 언급",
               COALESCE(e.expert_cnt, 0) as "전문가 리포트",
               c.comm_sentiment as "대중 감성",
               e.expert_sentiment as "전문가 감성",
               CASE
                   WHEN c.comm_sentiment IS NOT NULL AND e.expert_sentiment IS NOT NULL
                   THEN ROUND((e.expert_sentiment - c.comm_sentiment)::numeric, 1)
                   ELSE NULL
               END as "감성 괴리"
        FROM comm_mentions c
        FULL OUTER JOIN expert_mentions e ON c.ticker_id = e.ticker_id
        JOIN tickers t ON t.id = COALESCE(c.ticker_id, e.ticker_id)
        WHERE t.market NOT IN ('THEME', 'CRYPTO')
        ORDER BY COALESCE(c.comm_cnt, 0) + COALESCE(e.expert_cnt, 0) DESC
        LIMIT 30
    """, (start_date, end_date, start_date, end_date))

    if not cross.empty:
        paginated_dataframe(cross, "pg_cross_analysis")

    st.markdown("---")

    # 전문가만 커버하고 커뮤니티에서 안 보이는 종목
    st.subheader("🔍 전문가 Only (커뮤니티 미언급)")
    expert_only = run_query("""
        SELECT t.name as "종목", COUNT(*) as "리포트 수",
               STRING_AGG(DISTINCT ea.securities_firm, ', ') as "커버 증권사"
        FROM expert_article_mentions eam
        JOIN tickers t ON t.id = eam.ticker_id
        JOIN expert_articles ea ON ea.id = eam.article_id
        WHERE ea.published_date BETWEEN %s AND %s
          AND eam.ticker_id NOT IN (
              SELECT DISTINCT pm.ticker_id FROM post_mentions pm
              JOIN posts p ON p.id = pm.post_id
              WHERE p.post_date BETWEEN %s AND %s
          )
        GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 15
    """, (start_date, end_date, start_date, end_date))

    if not expert_only.empty:
        paginated_dataframe(expert_only, "pg_expert_only")
    else:
        st.info("모든 전문가 종목이 커뮤니티에서도 언급되고 있습니다.")


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

    # 종목 목록 가져오기 (언급된 적 있는 것만)
    ticker_list = run_query("""
        SELECT DISTINCT t.id, t.symbol, t.name, t.market
        FROM tickers t
        JOIN post_mentions pm ON pm.ticker_id = t.id
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
    ticker_id = options[selected]

    # 종목 기본 정보
    ticker_info = run_query("""
        SELECT t.symbol, t.name, t.market,
               COUNT(*) as total_mentions,
               COUNT(*) FILTER (WHERE pm.sentiment = 1) as positive,
               COUNT(*) FILTER (WHERE pm.sentiment = -1) as negative,
               COUNT(*) FILTER (WHERE pm.sentiment = 0) as neutral,
               ROUND(100.0 * COUNT(*) FILTER (WHERE pm.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as positive_rate,
               ROUND(((AVG(pm.sentiment) + 1) * 50)::numeric, 1) as sentiment_score,
               ROUND(
                   2.0 * COUNT(*) FILTER (WHERE pm.sentiment = 1) +
                   0.5 * COUNT(*) FILTER (WHERE pm.sentiment = -1) +
                   1.0 * COUNT(*) FILTER (WHERE pm.sentiment = 0)
               , 1) as weighted_score
        FROM tickers t
        JOIN post_mentions pm ON pm.ticker_id = t.id
        JOIN posts p ON p.id = pm.post_id
        WHERE t.id = %s AND p.post_date BETWEEN %s AND %s
        GROUP BY t.symbol, t.name, t.market
    """, (int(ticker_id), start_date, end_date))

    if not ticker_info.empty:
        info = ticker_info.iloc[0]

    st.markdown("---")

    # ── 커뮤니티 ──
    st.subheader("📢 커뮤니티")

    # 일별 추이 차트
    daily = run_query("""
        SELECT p.post_date as "날짜",
               COUNT(*) as "전체",
               COUNT(*) FILTER (WHERE pm.sentiment = 1) as "긍정",
               COUNT(*) FILTER (WHERE pm.sentiment = -1) as "부정",
               COUNT(*) FILTER (WHERE pm.sentiment = 0) as "중립"
        FROM post_mentions pm
        JOIN posts p ON p.id = pm.post_id
        WHERE pm.ticker_id = %s AND p.post_date BETWEEN %s AND %s
        GROUP BY p.post_date ORDER BY p.post_date
    """, (int(ticker_id), start_date, end_date))

    if not daily.empty:
        st.line_chart(daily.set_index("날짜"))

    if not ticker_info.empty:
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        r1c1.metric("💬 총 언급", f"{info['total_mentions']}")
        r1c2.metric("👍 긍정", f"{info['positive']}")
        r1c3.metric("👎 부정", f"{info['negative']}")
        r1c4.metric("➖ 중립", f"{info['neutral']}")

        r2c1, r2c2, r2c3 = st.columns(3)
        r2c1.metric("📊 긍정률", f"{info['positive_rate'] or 0}%")
        r2c2.metric("🎯 감성 점수", f"{info['sentiment_score']}")
        r2c3.metric("⭐ 가중 점수", f"{info['weighted_score']}")

    st.markdown("---")

    # ── 전문가 ──
    st.subheader("🔬 전문가 리포트")
    ticker_symbol = ticker_info.iloc[0]['symbol'] if not ticker_info.empty else None
    if ticker_symbol:
        expert_stats = run_query("""
            SELECT COUNT(*) as report_cnt,
                   COUNT(DISTINCT ea.securities_firm) as firm_cnt,
                   COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%buy%%' OR eam.opinion = '매수') as buy,
                   COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%hold%%' OR eam.opinion = '중립') as hold,
                   COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%sell%%' OR eam.opinion = '매도') as sell,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE eam.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as positive_rate,
                   ROUND(((AVG(eam.sentiment) + 1) * 50)::numeric, 1) as sentiment_score,
                   ROUND(
                       2.0 * COUNT(*) FILTER (WHERE eam.sentiment = 1) +
                       0.5 * COUNT(*) FILTER (WHERE eam.sentiment = -1) +
                       1.0 * COUNT(*) FILTER (WHERE eam.sentiment = 0)
                   , 1) as weighted_score
            FROM expert_article_mentions eam
            JOIN tickers t ON t.id = eam.ticker_id
            JOIN expert_articles ea ON ea.id = eam.article_id
            WHERE t.symbol = %s AND ea.published_date BETWEEN %s AND %s
        """, (ticker_symbol, start_date, end_date))

        if not expert_stats.empty and expert_stats.iloc[0]['report_cnt'] > 0:
            es = expert_stats.iloc[0]
            r1c1, r1c2, r1c3, r1c4 = st.columns(4)
            r1c1.metric("📄 리포트 수", f"{es['report_cnt']}")
            r1c3.metric("📈 Buy", f"{es['buy']}")
            r1c2.metric("➖ Hold", f"{es['hold']}")
            r1c4.metric("📉 Sell", f"{es['sell']}")

            r2c1, r2c2, r2c3 = st.columns(3)
            r2c1.metric("📊 긍정률", f"{es['positive_rate'] or 0}%")
            r2c2.metric("🎯 감성 점수", f"{es['sentiment_score']}")
            r2c3.metric("⭐ 가중 점수", f"{es['weighted_score']}")
        else:
            st.info("해당 기간에 전문가 리포트가 없습니다.")

