"""
Human Index Dashboard
수집된 커뮤니티 데이터의 종목 언급량 통계 대시보드
"""

import streamlit as st
import psycopg2
import pandas as pd
from datetime import date, timedelta

# ─── 페이지 설정 ─────────────────────────────────────
st.set_page_config(
    page_title="Human Index",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── 스타일 ──────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        border: 1px solid #2a2a4a;
    }
    [data-testid="stMetricLabel"] p {
        color: #a0a0cc !important;
        font-size: 0.9rem !important;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 1.8rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ─── DB 연결 ─────────────────────────────────────────
DB_CONFIG = {
    "dbname": "human_index",
    "host": "localhost",
    "port": 5432,
}


@st.cache_resource
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def run_query(query, params=None):
    """쿼리 실행 후 DataFrame 반환"""
    conn = get_connection()
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception:
        # 연결 끊겼을 때 재연결
        st.cache_resource.clear()
        conn = get_connection()
        return pd.read_sql_query(query, conn, params=params)


# ─── 사이드바 ────────────────────────────────────────
st.sidebar.title("📊 Human Index")
st.sidebar.markdown("---")

# 날짜 범위
date_range = run_query("SELECT MIN(post_date) as min_d, MAX(post_date) as max_d FROM posts")
min_date = date_range["min_d"].iloc[0]
max_date = date_range["max_d"].iloc[0]

selected_range = st.sidebar.date_input(
    "📅 날짜 범위",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

if len(selected_range) == 2:
    start_date, end_date = selected_range
else:
    start_date, end_date = min_date, max_date

page = st.sidebar.radio(
    "메뉴",
    ["📈 개요", "🔍 종목 검색", "🏆 랭킹", "📋 게시글 목록"],
)

st.sidebar.markdown("---")
st.sidebar.caption(f"데이터 범위: {min_date} ~ {max_date}")

# ═══════════════════════════════════════════════════════
# 📈 개요 페이지
# ═══════════════════════════════════════════════════════
if page == "📈 개요":
    st.title("📈 Human Index Dashboard")
    st.caption("커뮤니티 주식 언급량 분석")

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
            st.bar_chart(daily_posts.set_index("날짜"))

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
            st.bar_chart(daily_mentions.set_index("날짜"))

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


# ═══════════════════════════════════════════════════════
# 🔍 종목 검색 페이지
# ═══════════════════════════════════════════════════════
elif page == "🔍 종목 검색":
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
    else:
        # 검색어 입력
        search_term = st.text_input("🔎 종목명/별칭 검색", placeholder="예: 삼성전자, 마이크론, 샌디스크...")

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
        else:
            selected = st.selectbox("종목 선택", list(options.keys()))
            ticker_id = options[selected]

            # 종목 기본 정보
            ticker_info = run_query("""
                SELECT t.symbol, t.name, t.market,
                       COUNT(*) as total_mentions,
                       COUNT(*) FILTER (WHERE pm.sentiment = 1) as positive,
                       COUNT(*) FILTER (WHERE pm.sentiment = -1) as negative,
                       COUNT(*) FILTER (WHERE pm.sentiment = 0) as neutral
                FROM tickers t
                JOIN post_mentions pm ON pm.ticker_id = t.id
                JOIN posts p ON p.id = pm.post_id
                WHERE t.id = %s AND p.post_date BETWEEN %s AND %s
                GROUP BY t.symbol, t.name, t.market
            """, (int(ticker_id), start_date, end_date))

            if not ticker_info.empty:
                info = ticker_info.iloc[0]
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("총 언급", f"{info['total_mentions']}")
                col2.metric("👍 긍정", f"{info['positive']}")
                col3.metric("👎 부정", f"{info['negative']}")
                col4.metric("➖ 중립", f"{info['neutral']}")

            st.markdown("---")

            # 일별 추이 차트
            st.subheader("📈 일별 언급 추이")
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

            # 관련 게시글
            st.subheader("📋 관련 게시글")
            posts = run_query("""
                SELECT p.post_date as "날짜", p.title as "제목", p.author as "작성자",
                       CASE pm.sentiment WHEN 1 THEN '👍' WHEN -1 THEN '👎' ELSE '➖' END as "감성"
                FROM post_mentions pm
                JOIN posts p ON p.id = pm.post_id
                WHERE pm.ticker_id = %s AND p.post_date BETWEEN %s AND %s
                ORDER BY p.post_date DESC, p.id DESC
                LIMIT 50
            """, (int(ticker_id), start_date, end_date))

            if not posts.empty:
                st.dataframe(posts, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════
# 🏆 랭킹 페이지
# ═══════════════════════════════════════════════════════
elif page == "🏆 랭킹":
    st.title("🏆 종목 언급 랭킹")

    tab1, tab2, tab3 = st.tabs(["📊 언급량 순위", "📈 급상승 종목", "👤 활발한 작성자"])

    with tab1:
        st.subheader("종목별 총 언급 수")
        ranking = run_query("""
            SELECT t.symbol as "심볼", t.name as "종목명", t.market as "시장",
                   COUNT(*) as "총 언급",
                   COUNT(*) FILTER (WHERE pm.sentiment = 1) as "👍 긍정",
                   COUNT(*) FILTER (WHERE pm.sentiment = -1) as "👎 부정",
                   COUNT(*) FILTER (WHERE pm.sentiment = 0) as "➖ 중립",
                   ROUND(100.0 * COUNT(*) FILTER (WHERE pm.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as "긍정률(%%)"
            FROM post_mentions pm
            JOIN tickers t ON t.id = pm.ticker_id
            JOIN posts p ON p.id = pm.post_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY t.symbol, t.name, t.market
            ORDER BY COUNT(*) DESC
        """, (start_date, end_date))
        st.dataframe(ranking, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("최근 3일 vs 이전 3일 언급량 비교")
        recent_end = end_date
        recent_start = end_date - timedelta(days=2)
        prev_end = recent_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=2)

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
                   COALESCE(r.cnt, 0) as "최근 3일",
                   COALESCE(p.cnt, 0) as "이전 3일",
                   COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) as "변화량",
                   CASE WHEN COALESCE(p.cnt, 0) > 0
                        THEN ROUND(100.0 * (COALESCE(r.cnt,0) - p.cnt) / p.cnt, 1)
                        ELSE NULL END as "변화율(%%)"
            FROM recent r
            FULL OUTER JOIN prev p ON r.ticker_id = p.ticker_id
            JOIN tickers t ON t.id = COALESCE(r.ticker_id, p.ticker_id)
            WHERE t.market NOT IN ('THEME', 'CRYPTO')
            ORDER BY COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) DESC
            LIMIT 20
        """, (recent_start, recent_end, prev_start, prev_end))

        if not surge.empty:
            st.dataframe(surge, use_container_width=True, hide_index=True)
        else:
            st.info("비교할 데이터가 부족합니다.")

    with tab3:
        st.subheader("게시글 많은 작성자 TOP 20")
        authors = run_query("""
            SELECT author as "작성자", COUNT(*) as "게시글 수"
            FROM posts
            WHERE post_date BETWEEN %s AND %s
            GROUP BY author ORDER BY COUNT(*) DESC LIMIT 20
        """, (start_date, end_date))
        st.dataframe(authors, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════
# 📋 게시글 목록 페이지
# ═══════════════════════════════════════════════════════
elif page == "📋 게시글 목록":
    st.title("📋 게시글 목록")

    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔎 제목 검색", placeholder="검색어를 입력하세요")
    with col2:
        limit = st.selectbox("표시 건수", [50, 100, 200, 500], index=0)

    if search:
        posts_df = run_query("""
            SELECT p.post_date as "날짜", p.title as "제목", p.author as "작성자",
                   STRING_AGG(t.name, ', ') as "언급 종목"
            FROM posts p
            LEFT JOIN post_mentions pm ON pm.post_id = p.id
            LEFT JOIN tickers t ON t.id = pm.ticker_id
            WHERE p.post_date BETWEEN %s AND %s
              AND p.title ILIKE %s
            GROUP BY p.id, p.post_date, p.title, p.author
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s
        """, (start_date, end_date, f"%{search}%", limit))
    else:
        posts_df = run_query("""
            SELECT p.post_date as "날짜", p.title as "제목", p.author as "작성자",
                   STRING_AGG(t.name, ', ') as "언급 종목"
            FROM posts p
            LEFT JOIN post_mentions pm ON pm.post_id = p.id
            LEFT JOIN tickers t ON t.id = pm.ticker_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY p.id, p.post_date, p.title, p.author
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s
        """, (start_date, end_date, limit))

    st.caption(f"총 {len(posts_df)}건 표시")
    st.dataframe(posts_df, use_container_width=True, hide_index=True)
