"""
Human Index Dashboard
수집된 커뮤니티 데이터의 종목 언급량 통계 대시보드
"""

import streamlit as st
import streamlit.components.v1 as components

from lib.shared import run_query
from lib import community, report, news, overview

# ─── 페이지 설정 ─────────────────────────────────────
st.set_page_config(
    page_title="Human Index",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Google Analytics (GA4) ───────────────────────────
components.html("""
<script async src="https://www.googletagmanager.com/gtag/js?id=G-WW9WTSV3C0"></script>
<script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'G-WW9WTSV3C0');
</script>
""", height=0)

# ─── 스타일 ──────────────────────────────────────────
from pathlib import Path
_css = (Path(__file__).parent / "static" / "style.css").read_text()
st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)

# ─── 세션 상태 초기화 ────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "🏠 종합 대시보드"
if "nav_ticker_symbol" not in st.session_state:
    st.session_state.nav_ticker_symbol = None
if "nav_search_keyword" not in st.session_state:
    st.session_state.nav_search_keyword = None
if "nav_filter_symbol" not in st.session_state:
    st.session_state.nav_filter_symbol = None

# ─── 사이드바 ────────────────────────────────────────
st.sidebar.markdown("""
<div class="sidebar-logo">
    <div class="logo-icon">
        <span class="accent">📊</span> Human Index
    </div>
    <div class="logo-sub">COMMUNITY SENTIMENT ANALYTICS</div>
</div>
""", unsafe_allow_html=True)

# 날짜 범위 (커뮤니티 + 전문가 통합)
SQL_DATE_RANGE = """
    SELECT LEAST(
        (SELECT MIN(post_date) FROM posts),
        (SELECT MIN(published_date) FROM expert_articles)
    ) as min_d,
    GREATEST(
        (SELECT MAX(post_date) FROM posts),
        (SELECT MAX(published_date) FROM expert_articles)
    ) as max_d
"""
date_range = run_query(SQL_DATE_RANGE)
min_date = date_range["min_d"].iloc[0]
max_date = date_range["max_d"].iloc[0]
start_date, end_date = min_date, max_date

# ─── 메뉴 섹션 정의 ──────────────────────────────────
COMMUNITY_PAGES = ["📈 커뮤니티 개요", "📊 언급량 랭킹", "🚀 급상승 랭킹", "📋 게시글 목록"]
EXPERT_PAGES = ["📈 리포트 개요", "📊 리포트 랭킹", "🚀 리포트 급상승", "📋 리포트 목록"]
NEWS_PAGES = ["📈 뉴스 개요", "📊 뉴스 언급량 랭킹", "🚀 뉴스 급상승", "📋 뉴스 목록"]
COMBINED_PAGES = ["🏠 종합 대시보드", "🔍 종목 검색"]

# navigate_to → rerun 후, radio 생성 전에 위젯 키 동기화
if st.session_state.get("_pending_nav"):
    p = st.session_state.page
    if p in COMMUNITY_PAGES:
        st.session_state._radio_community = p
    elif p in EXPERT_PAGES:
        st.session_state._radio_expert = p
    elif p in NEWS_PAGES:
        st.session_state._radio_news = p
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
news_idx = NEWS_PAGES.index(current) if current in NEWS_PAGES else None
combined_idx = COMBINED_PAGES.index(current) if current in COMBINED_PAGES else None

st.sidebar.markdown('<div class="nav-section-header">📊 종합</div>', unsafe_allow_html=True)
st.sidebar.radio(
    "종합", COMBINED_PAGES, key="_radio_combined",
    index=combined_idx if combined_idx is not None else 0,
    on_change=_make_handler("_radio_combined", ["_radio_community", "_radio_expert", "_radio_news"]),
    label_visibility="collapsed",
)

st.sidebar.markdown('<div class="nav-section-header">📢 커뮤니티</div>', unsafe_allow_html=True)
st.sidebar.radio(
    "커뮤니티", COMMUNITY_PAGES, key="_radio_community",
    index=comm_idx if comm_idx is not None else None,
    on_change=_make_handler("_radio_community", ["_radio_expert", "_radio_news", "_radio_combined"]),
    label_visibility="collapsed",
)

st.sidebar.markdown('<div class="nav-section-header">🔬 리포트</div>', unsafe_allow_html=True)
st.sidebar.radio(
    "리포트", EXPERT_PAGES, key="_radio_expert",
    index=expert_idx if expert_idx is not None else None,
    on_change=_make_handler("_radio_expert", ["_radio_community", "_radio_news", "_radio_combined"]),
    label_visibility="collapsed",
)

st.sidebar.markdown('<div class="nav-section-header">📰 뉴스</div>', unsafe_allow_html=True)
st.sidebar.radio(
    "뉴스", NEWS_PAGES, key="_radio_news",
    index=news_idx if news_idx is not None else None,
    on_change=_make_handler("_radio_news", ["_radio_community", "_radio_expert", "_radio_combined"]),
    label_visibility="collapsed",
)

# 사이드바 하단 푸터
st.sidebar.markdown('<div class="sidebar-footer">© 2026 Human Index · v1.0</div>', unsafe_allow_html=True)

# ─── 페이지 라우팅 ───────────────────────────────────
PAGE_MAP = {
    # 커뮤니티
    "📈 커뮤니티 개요": community.page_overview,
    "📊 언급량 랭킹": community.page_mention_ranking,
    "🚀 급상승 랭킹": community.page_surge_ranking,
    "📋 게시글 목록": community.page_post_list,
    # 리포트
    "📈 리포트 개요": report.page_overview,
    "📊 리포트 랭킹": report.page_report_ranking,
    "🚀 리포트 급상승": report.page_surge_ranking,
    "📋 리포트 목록": report.page_report_list,
    # 뉴스
    "📈 뉴스 개요": news.page_overview,
    "📊 뉴스 언급량 랭킹": news.page_mention_ranking,
    "🚀 뉴스 급상승": news.page_surge_ranking,
    "📋 뉴스 목록": news.page_article_list,
    # 종합
    "🏠 종합 대시보드": overview.page_dashboard,
    "🔍 종목 검색": overview.page_ticker_search,
}

page = st.session_state.page
if page in PAGE_MAP:
    PAGE_MAP[page](start_date, end_date)
