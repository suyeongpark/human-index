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
