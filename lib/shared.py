"""
공통 모듈 - DB 연결, 쿼리 실행, 상수, 네비게이션
"""

import streamlit as st
import psycopg2
import pandas as pd
import os

# ─── 점수 가중치 설정 ─────────────────────────────────
SCORE_WEIGHT_POSITIVE = 2.0   # 긍정 가중치
SCORE_WEIGHT_NEGATIVE = 0.5   # 부정 가중치
SCORE_WEIGHT_NEUTRAL  = 1.0   # 중립 가중치

# ─── DB 연결 ─────────────────────────────────────────
# 우선순위: Streamlit secrets → 환경변수 → 로컬 기본값
def _get_config(key, default=""):
    """Streamlit secrets 또는 환경변수에서 설정값 읽기"""
    try:
        return st.secrets["database"][key]
    except Exception:
        return os.environ.get(key, default)

DB_CONFIG = {
    "dbname": _get_config("DB_NAME", "human_index"),
    "host": _get_config("DB_HOST", "localhost"),
    "port": int(_get_config("DB_PORT", "5432")),
    "user": _get_config("DB_USER", ""),
    "password": _get_config("DB_PASSWORD", ""),
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


def navigate_to(target_page, ticker_symbol=None, search_keyword=None, filter_symbol=None):
    """다른 페이지로 이동"""
    st.session_state.page = target_page
    st.session_state.nav_ticker_symbol = ticker_symbol
    st.session_state.nav_search_keyword = search_keyword
    st.session_state.nav_filter_symbol = filter_symbol
    st.session_state._pending_nav = True  # radio 동기화 플래그


PAGE_SIZE = 25


def paginated_dataframe(df, key, height=700, column_config=None):
    """DataFrame을 25건 단위로 페이지네이션하여 표시"""
    if key not in st.session_state:
        st.session_state[key] = 0

    total = len(df)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    page = st.session_state[key]
    page = min(page, total_pages - 1)
    st.session_state[key] = page

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_df = df.iloc[start:end]

    kwargs = dict(use_container_width=True, hide_index=True, height=height)
    if column_config:
        kwargs["column_config"] = column_config
    st.dataframe(page_df, **kwargs)

    # 테이블 아래 가운데 정렬: [이전] [페이지 X/Y] [다음]
    _, col_prev, col_info, col_next, _ = st.columns([2, 1, 1, 1, 2])
    with col_prev:
        if st.button("⬅️ 이전", disabled=(page == 0), key=f"{key}_prev", use_container_width=True):
            st.session_state[key] = page - 1
            st.rerun()
    with col_info:
        st.markdown(f"<div style='text-align:center;padding:0.4rem 0;color:#888;'>{page + 1} / {total_pages}</div>", unsafe_allow_html=True)
    with col_next:
        if st.button("다음 ➡️", disabled=(page >= total_pages - 1), key=f"{key}_next", use_container_width=True):
            st.session_state[key] = page + 1
            st.rerun()


# ─── 기간별 집계 헬퍼 ──────────────────────────────────
PERIOD_OPTIONS = ["일간", "주간", "월간", "연간"]

PERIOD_SQL = {
    "일간": {"select": "{date_col}", "group": "{date_col}"},
    "주간": {"select": "DATE_TRUNC('week', {date_col})::date", "group": "DATE_TRUNC('week', {date_col})"},
    "월간": {"select": "DATE_TRUNC('month', {date_col})::date", "group": "DATE_TRUNC('month', {date_col})"},
    "연간": {"select": "DATE_TRUNC('year', {date_col})::date", "group": "DATE_TRUNC('year', {date_col})"},
}

# TOP 10 등 집계에 사용할 최근 기간 (일 수)
PERIOD_DAYS = {"일간": 1, "주간": 7, "월간": 30, "연간": 365}
