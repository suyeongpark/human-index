"""
Human Index Dashboard
수집된 커뮤니티 데이터의 종목 언급량 통계 대시보드
"""

import streamlit as st
import psycopg2
import pandas as pd
from datetime import date, timedelta

# ─── 점수 가중치 설정 ─────────────────────────────────
SCORE_WEIGHT_POSITIVE = 2.0   # 긍정 가중치
SCORE_WEIGHT_NEGATIVE = 0.5   # 부정 가중치
SCORE_WEIGHT_NEUTRAL  = 1.0   # 중립 가중치

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
    /* 랭킹 테이블 컴팩트 */
    [data-testid="stHorizontalBlock"] {
        gap: 0.2rem !important;
    }
    [data-testid="stHorizontalBlock"] [data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }
    [data-testid="stHorizontalBlock"] p {
        margin-bottom: 0 !important;
        padding: 0.15rem 0 !important;
        font-size: 0.85rem !important;
        line-height: 1.3 !important;
    }
    [data-testid="stHorizontalBlock"] button {
        padding: 0.15rem 0.5rem !important;
        font-size: 0.75rem !important;
        min-height: 0 !important;
        line-height: 1 !important;
    }
    /* dataframe을 화면 높이에 맞춤 */
    [data-testid="stDataFrame"] > div {
        height: calc(100vh - 250px) !important;
        max-height: calc(100vh - 250px) !important;
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


# ─── 세션 상태 초기화 ────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "📈 개요"
if "nav_ticker_symbol" not in st.session_state:
    st.session_state.nav_ticker_symbol = None
if "nav_search_keyword" not in st.session_state:
    st.session_state.nav_search_keyword = None
if "nav_filter_symbol" not in st.session_state:
    st.session_state.nav_filter_symbol = None


def navigate_to(target_page, ticker_symbol=None, search_keyword=None, filter_symbol=None):
    """다른 페이지로 이동"""
    st.session_state.page = target_page
    st.session_state.nav_ticker_symbol = ticker_symbol
    st.session_state.nav_search_keyword = search_keyword
    st.session_state.nav_filter_symbol = filter_symbol
    st.session_state._pending_nav = True  # radio 동기화 플래그


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

MENU_ITEMS = ["📈 개요", "📊 언급량 랭킹", "🚀 급상승 랭킹", "👤 작성자 랭킹", "🔍 종목 검색", "📋 게시글 목록"]

# navigate_to → rerun 후, radio 생성 전에 위젯 키 동기화
if st.session_state.get("_pending_nav"):
    st.session_state._page_radio = st.session_state.page
    st.session_state._pending_nav = False

def _on_page_change():
    st.session_state.page = st.session_state._page_radio
    st.session_state.nav_ticker_symbol = None
    st.session_state.nav_search_keyword = None

st.sidebar.radio(
    "메뉴", MENU_ITEMS, key="_page_radio",
    on_change=_on_page_change,
)
page = st.session_state.page

st.sidebar.markdown("---")
st.sidebar.caption(f"데이터 범위: {min_date} ~ {max_date}")

# ═══════════════════════════════════════════════════════
# 📈 개요 페이지
# ═══════════════════════════════════════════════════════
if st.session_state.page == "📈 개요":
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
elif st.session_state.page == "🔍 종목 검색":
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
# 📊 언급량 랭킹 페이지
# ═══════════════════════════════════════════════════════
elif st.session_state.page == "📊 언급량 랭킹":
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
               ROUND(100.0 * COUNT(*) FILTER (WHERE pm.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as "긍정률(%%)",
               ROUND(
                   %s * COUNT(*) FILTER (WHERE pm.sentiment = 1) +
                   %s * COUNT(*) FILTER (WHERE pm.sentiment = -1) +
                   %s * COUNT(*) FILTER (WHERE pm.sentiment = 0)
               , 1) as "⭐ 점수"
        FROM post_mentions pm
        JOIN tickers t ON t.id = pm.ticker_id
        JOIN posts p ON p.id = pm.post_id
        WHERE p.post_date BETWEEN %s AND %s
        GROUP BY t.symbol, t.name, t.market
        ORDER BY "⭐ 점수" DESC
        LIMIT %s
    """, (SCORE_WEIGHT_POSITIVE, SCORE_WEIGHT_NEGATIVE, SCORE_WEIGHT_NEUTRAL,
          start_date, end_date, rank_limit))

    if not ranking.empty:
        # 헤더
        hdr = st.columns([0.5, 1.2, 1.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.7, 0.8, 0.5, 0.5])
        headers = ["#", "심볼", "종목명", "시장", "총언급", "👍", "👎", "➖", "긍정률", "⭐점수", "", ""]
        for h, label in zip(hdr, headers):
            h.markdown(f"**{label}**")
        st.markdown("<hr style='margin:0.2rem 0'>", unsafe_allow_html=True)

        # 행
        for idx, row in ranking.iterrows():
            cols = st.columns([0.5, 1.2, 1.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.7, 0.8, 0.5, 0.5])
            cols[0].write(f"{idx + 1}")
            cols[1].write(row["심볼"])
            cols[2].write(row["종목명"])
            cols[3].write(row["시장"])
            cols[4].write(str(row["총 언급"]))
            cols[5].write(str(row["👍 긍정"]))
            cols[6].write(str(row["👎 부정"]))
            cols[7].write(str(row["➖ 중립"]))
            cols[8].write(f"{row['긍정률(%)'] or 0}%")
            cols[9].write(f"**{row['⭐ 점수']}**")
            if cols[10].button("🔍", key=f"tk_{idx}", help="종목 검색"):
                navigate_to("🔍 종목 검색", ticker_symbol=row["심볼"])
                st.rerun()
            if cols[11].button("📋", key=f"ps_{idx}", help="게시글 검색"):
                navigate_to("📋 게시글 목록", filter_symbol=row["심볼"])
                st.rerun()
    else:
        st.info("데이터가 없습니다.")


# ═══════════════════════════════════════════════════════
# 🚀 급상승 랭킹 페이지
# ═══════════════════════════════════════════════════════
elif st.session_state.page == "🚀 급상승 랭킹":
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
        st.dataframe(surge, use_container_width=True, hide_index=True)
    else:
        st.info("비교할 데이터가 부족합니다.")


# ═══════════════════════════════════════════════════════
# 👤 작성자 랭킹 페이지
# ═══════════════════════════════════════════════════════
elif st.session_state.page == "👤 작성자 랭킹":
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
    st.dataframe(authors, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════
# 📋 게시글 목록 페이지
# ═══════════════════════════════════════════════════════
elif st.session_state.page == "📋 게시글 목록":
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
            SELECT p.post_date as "날짜", p.title as "제목", p.author as "작성자",
                   STRING_AGG(DISTINCT t2.name, ', ') as "언급 종목"
            FROM posts p
            JOIN post_mentions pm ON pm.post_id = p.id
            JOIN tickers t ON t.id = pm.ticker_id AND t.symbol = %s
            LEFT JOIN post_mentions pm2 ON pm2.post_id = p.id
            LEFT JOIN tickers t2 ON t2.id = pm2.ticker_id
            WHERE p.post_date BETWEEN %s AND %s
            GROUP BY p.id, p.post_date, p.title, p.author
            ORDER BY p.post_date DESC, p.id DESC
            LIMIT %s
        """, (filter_symbol, start_date, end_date, limit))
    elif search:
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
