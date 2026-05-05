"""
Human Index Dashboard
수집된 커뮤니티 데이터의 종목 언급량 통계 대시보드
"""

import streamlit as st

from lib.shared import run_query
from lib import community, expert, combined

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
</style>
""", unsafe_allow_html=True)

# ─── 세션 상태 초기화 ────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "📈 커뮤니티 개요"
if "nav_ticker_symbol" not in st.session_state:
    st.session_state.nav_ticker_symbol = None
if "nav_search_keyword" not in st.session_state:
    st.session_state.nav_search_keyword = None
if "nav_filter_symbol" not in st.session_state:
    st.session_state.nav_filter_symbol = None

# ─── 사이드바 ────────────────────────────────────────
st.sidebar.title("📊 Human Index")
st.sidebar.markdown("---")

# 날짜 범위 (커뮤니티 + 전문가 통합)
date_range = run_query("""
    SELECT LEAST(
        (SELECT MIN(post_date) FROM posts),
        (SELECT MIN(published_date) FROM expert_articles)
    ) as min_d,
    GREATEST(
        (SELECT MAX(post_date) FROM posts),
        (SELECT MAX(published_date) FROM expert_articles)
    ) as max_d
""")
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

# ─── 메뉴 섹션 정의 ──────────────────────────────────
COMMUNITY_PAGES = ["📈 커뮤니티 개요", "📊 언급량 랭킹", "🚀 급상승 랭킹", "📋 게시글 목록"]
EXPERT_PAGES = ["📈 전문가 개요", "📊 리포트 랭킹", "📊 기사 언급량 랭킹", "📋 리포트, 기사 목록"]
COMBINED_PAGES = ["🏠 종합 대시보드", "🔍 종목 검색"]

# navigate_to → rerun 후, radio 생성 전에 위젯 키 동기화
if st.session_state.get("_pending_nav"):
    p = st.session_state.page
    if p in COMMUNITY_PAGES:
        st.session_state._radio_community = p
    elif p in EXPERT_PAGES:
        st.session_state._radio_expert = p
    elif p in COMBINED_PAGES:
        st.session_state._radio_combined = p
    st.session_state._pending_nav = False


def _make_handler(radio_key, other_keys):
    def handler():
        st.session_state.page = st.session_state[radio_key]
        for k in other_keys:
            if k in st.session_state:
                st.session_state[k] = None
        st.session_state.nav_ticker_symbol = None
        st.session_state.nav_search_keyword = None
    return handler


# 현재 페이지가 어느 섹션인지 판별
current = st.session_state.page
comm_idx = COMMUNITY_PAGES.index(current) if current in COMMUNITY_PAGES else None
expert_idx = EXPERT_PAGES.index(current) if current in EXPERT_PAGES else None
combined_idx = COMBINED_PAGES.index(current) if current in COMBINED_PAGES else None

st.sidebar.markdown("#### 📢 커뮤니티")
st.sidebar.radio(
    "커뮤니티", COMMUNITY_PAGES, key="_radio_community",
    index=comm_idx if comm_idx is not None else 0,
    on_change=_make_handler("_radio_community", ["_radio_expert", "_radio_combined"]),
    label_visibility="collapsed",
)

st.sidebar.markdown("#### 🔬 전문가")
st.sidebar.radio(
    "전문가", EXPERT_PAGES, key="_radio_expert",
    index=expert_idx if expert_idx is not None else None,
    on_change=_make_handler("_radio_expert", ["_radio_community", "_radio_combined"]),
    label_visibility="collapsed",
)

st.sidebar.markdown("#### 📊 종합")
st.sidebar.radio(
    "종합", COMBINED_PAGES, key="_radio_combined",
    index=combined_idx if combined_idx is not None else None,
    on_change=_make_handler("_radio_combined", ["_radio_community", "_radio_expert"]),
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption(f"데이터 범위: {min_date} ~ {max_date}")

# ─── 페이지 라우팅 ───────────────────────────────────
PAGE_MAP = {
    # 커뮤니티
    "📈 커뮤니티 개요": community.page_overview,
    "📊 언급량 랭킹": community.page_mention_ranking,
    "🚀 급상승 랭킹": community.page_surge_ranking,

    "📋 게시글 목록": community.page_post_list,
    # 전문가
    "📈 전문가 개요": expert.page_overview,
    "📊 리포트 랭킹": expert.page_report_ranking,
    "📊 기사 언급량 랭킹": expert.page_mention_ranking,
    "📋 리포트, 기사 목록": expert.page_report_list,
    # 종합
    "🏠 종합 대시보드": combined.page_dashboard,
    "🔍 종목 검색": combined.page_ticker_search,
}

page = st.session_state.page
if page in PAGE_MAP:
    PAGE_MAP[page](start_date, end_date)
