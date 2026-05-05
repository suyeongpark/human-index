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


# ─── UI 컴포넌트 헬퍼 ─────────────────────────────────

def page_header(title, caption=None):
    """페이지 타이틀 + 캡션 + 구분선을 통일된 스타일로 렌더링"""
    st.title(title)
    parts = []
    if caption:
        parts.append(f'<p class="page-caption">{caption}</p>')
    parts.append('<hr class="page-divider">')
    st.markdown("".join(parts), unsafe_allow_html=True)


def pagination_bar(page, total_pages, session_key, prefix):
    """통일된 페이지네이션 바 (⏮ ◀ 1/N ▶ ⏭)"""
    _, col_first, col_prev, col_info, col_next, col_last, _ = st.columns([8, 1, 1, 3, 1, 1, 8])
    with col_first:
        if st.button("⏮", disabled=(page == 0), key=f"{prefix}_first"):
            st.session_state[session_key] = 0
            st.rerun()
    with col_prev:
        if st.button("◀", disabled=(page == 0), key=f"{prefix}_prev"):
            st.session_state[session_key] = page - 1
            st.rerun()
    with col_info:
        st.markdown(
            f'<div class="pagination-info">'
            f'<strong>{page + 1}</strong> / {total_pages}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("▶", disabled=(page >= total_pages - 1), key=f"{prefix}_next"):
            st.session_state[session_key] = page + 1
            st.rerun()
    with col_last:
        if st.button("⏭", disabled=(page >= total_pages - 1), key=f"{prefix}_last"):
            st.session_state[session_key] = total_pages - 1
            st.rerun()


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

    pagination_bar(page, total_pages, key, key)


# ─── 기간별 집계 헬퍼 ──────────────────────────────────
PERIOD_OPTIONS = ["주간", "월간", "연간"]            # 급상승 (비교 분석)
PERIOD_OPTIONS_WITH_DAILY = ["일간", "주간", "월간", "연간"]  # 랭킹/언급량

PERIOD_SQL = {
    "일간": {"select": "{date_col}", "group": "{date_col}"},
    "주간": {"select": "DATE_TRUNC('week', {date_col})::date", "group": "DATE_TRUNC('week', {date_col})"},
    "월간": {"select": "DATE_TRUNC('month', {date_col})::date", "group": "DATE_TRUNC('month', {date_col})"},
    "연간": {"select": "DATE_TRUNC('year', {date_col})::date", "group": "DATE_TRUNC('year', {date_col})"},
}

# TOP 10 등 집계에 사용할 최근 기간 (일 수)
PERIOD_DAYS = {"일간": 1, "주간": 7, "월간": 30, "연간": 365}

def period_tabs(key: str, include_daily: bool = False) -> str:
    """집계 기간을 탭 스타일(horizontal radio) UI로 선택. 선택된 기간 문자열 반환."""
    options = PERIOD_OPTIONS_WITH_DAILY if include_daily else PERIOD_OPTIONS
    return st.radio("📅 집계 기간", options, key=key, horizontal=True, label_visibility="collapsed")


# ─── 공통 UI 컴포넌트 ──────────────────────────────────

# 감성/투자의견 색상 매핑 (긍정=파랑, 부정=빨강, 중립=회색)
COLOR_POSITIVE = "#4A90D9"  # 파란색 (긍정/Buy)
COLOR_NEGATIVE = "#E74C3C"  # 빨간색 (부정/Sell)
COLOR_NEUTRAL  = "#95A5A6"  # 회색   (중립/Hold)

SENTIMENT_COLORS = {
    "👍 긍정": COLOR_POSITIVE, "긍정": COLOR_POSITIVE,
    "👎 부정": COLOR_NEGATIVE, "부정": COLOR_NEGATIVE,
    "➖ 중립": COLOR_NEUTRAL,  "중립": COLOR_NEUTRAL,
    "📈 Buy": COLOR_POSITIVE,
    "📉 Sell": COLOR_NEGATIVE,
    "➖ Hold": COLOR_NEUTRAL,
    "전체": "#2C3E50",
}


def render_colored_line_chart(df, date_col=None):
    """감성 색상이 적용된 라인 차트. df의 컬럼명으로 색상을 자동 매핑."""
    if df.empty:
        return
    import altair as alt

    idx = date_col or df.columns[0]
    value_cols = [c for c in df.columns if c != idx]
    colors = [SENTIMENT_COLORS.get(c, "#2C3E50") for c in value_cols]

    melted = df.melt(id_vars=[idx], value_vars=value_cols, var_name="구분", value_name="건수")
    chart = alt.Chart(melted).mark_line(strokeWidth=2).encode(
        x=alt.X(f"{idx}:T", title=None),
        y=alt.Y("건수:Q"),
        color=alt.Color("구분:N", scale=alt.Scale(domain=value_cols, range=colors), legend=alt.Legend(title=None)),
    ).properties(height=300)
    st.altair_chart(chart, use_container_width=True)


def render_top10_chart(df, x_label="언급 수", height=350):
    """TOP 10 수평 바 차트 렌더링. df는 '종목', x_label 컬럼 필요."""
    if df.empty:
        return
    import altair as alt
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X(f"{x_label}:Q"),
        y=alt.Y("종목:N", sort="-x", title=None),
    ).properties(height=height)
    st.altair_chart(chart, use_container_width=True)


def render_trend_chart(query, params):
    """트렌드 라인 차트. 쿼리 결과의 첫 번째 컬럼을 인덱스로 사용."""
    df = run_query(query, params)
    if not df.empty:
        render_colored_line_chart(df)
    return df


def render_surge_page(title, query_template, period_key, end_date, start_date, page_key):
    """급상승 랭킹 페이지 공통 로직.
    query_template: recent/prev CTE용 쿼리. %s 4개 (recent_start, recent_end, prev_start, prev_end).
    """
    from datetime import timedelta

    page_header(title, "전주 대비 언급량 급상승 종목 감지")
    period = period_tabs(period_key)
    days = PERIOD_DAYS[period]

    recent_end = end_date
    recent_start = end_date - timedelta(days=days - 1)
    prev_end = recent_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)



    surge = run_query(query_template, (recent_start, recent_end, prev_start, prev_end))

    if not surge.empty:
        paginated_dataframe(surge, page_key)
    else:
        st.info("비교할 데이터가 부족합니다.")
