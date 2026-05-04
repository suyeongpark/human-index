"""
전문가 페이지 모듈 - 증권사 리포트 분석
"""

import streamlit as st
from lib.shared import run_query


def page_overview(start_date, end_date):
    """📈 전문가 개요"""
    st.title("🔬 전문가 대시보드")
    st.caption("증권사 리포트 분석 (전문가 의견)")

    kpi_ex = run_query("""
        SELECT
            (SELECT COUNT(*) FROM expert_articles WHERE published_date BETWEEN %s AND %s) as total_reports,
            (SELECT COUNT(DISTINCT eam.ticker_id) FROM expert_article_mentions eam
             JOIN expert_articles ea ON ea.id = eam.article_id
             WHERE ea.published_date BETWEEN %s AND %s) as unique_tickers,
            (SELECT COUNT(DISTINCT securities_firm) FROM expert_articles
             WHERE published_date BETWEEN %s AND %s AND securities_firm IS NOT NULL) as firms,
            (SELECT COUNT(*) FROM expert_article_mentions eam
             JOIN expert_articles ea ON ea.id = eam.article_id
             WHERE ea.published_date BETWEEN %s AND %s AND eam.sentiment = 1) as buy_cnt,
            (SELECT COUNT(*) FROM expert_article_mentions eam
             JOIN expert_articles ea ON ea.id = eam.article_id
             WHERE ea.published_date BETWEEN %s AND %s AND eam.sentiment <= 0) as other_cnt
    """, (start_date, end_date) * 5)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📄 총 리포트", f"{kpi_ex['total_reports'].iloc[0]:,}")
    c2.metric("📌 종목 수", f"{kpi_ex['unique_tickers'].iloc[0]}")
    c3.metric("🏢 증권사 수", f"{kpi_ex['firms'].iloc[0]}")
    buy = kpi_ex['buy_cnt'].iloc[0]
    total_op = buy + kpi_ex['other_cnt'].iloc[0]
    buy_pct = round(100 * buy / total_op, 1) if total_op > 0 else 0
    c4.metric("📈 Buy 비율", f"{buy_pct}%")

    st.markdown("---")

    st.subheader("🔥 TOP 10 커버 종목")
    top_cover = run_query("""
        SELECT t.name as "종목", COUNT(*) as "리포트 수",
               COUNT(DISTINCT ea.securities_firm) as "증권사 수",
               STRING_AGG(DISTINCT ea.securities_firm, ', ') as "커버 증권사"
        FROM expert_article_mentions eam
        JOIN tickers t ON t.id = eam.ticker_id
        JOIN expert_articles ea ON ea.id = eam.article_id
        WHERE ea.published_date BETWEEN %s AND %s
        GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
    """, (start_date, end_date))
    if not top_cover.empty:
        st.dataframe(top_cover, use_container_width=True, hide_index=True, height=400)

    st.markdown("---")

    st.subheader("🏢 증권사별 리포트 수")
    by_firm = run_query("""
        SELECT securities_firm as "증권사", COUNT(*) as "리포트 수"
        FROM expert_articles
        WHERE published_date BETWEEN %s AND %s AND securities_firm IS NOT NULL
        GROUP BY securities_firm ORDER BY COUNT(*) DESC LIMIT 15
    """, (start_date, end_date))
    if not by_firm.empty:
        st.bar_chart(by_firm.set_index("증권사"))


def page_report_ranking(start_date, end_date):
    """📊 리포트 랭킹"""
    st.title("📊 종목별 리포트 랭킹")

    rpt_limit_opts = {"30건": 30, "50건": 50, "100건": 100, "전체": 9999}
    rpt_limit_label = st.selectbox("표시 건수", list(rpt_limit_opts.keys()), key="rpt_limit")
    rpt_limit = rpt_limit_opts[rpt_limit_label]

    rpt_ranking = run_query("""
        SELECT t.symbol as "심볼", t.name as "종목명",
               COUNT(*) as "리포트 수",
               COUNT(DISTINCT ea.securities_firm) as "증권사 수",
               COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%buy%%' OR eam.opinion = '매수') as "Buy",
               COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%hold%%' OR eam.opinion = '중립') as "Hold",
               COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%sell%%' OR eam.opinion = '매도') as "Sell"
        FROM expert_article_mentions eam
        JOIN tickers t ON t.id = eam.ticker_id
        JOIN expert_articles ea ON ea.id = eam.article_id
        WHERE ea.published_date BETWEEN %s AND %s
        GROUP BY t.symbol, t.name
        ORDER BY COUNT(*) DESC
        LIMIT %s
    """, (start_date, end_date, rpt_limit))

    if not rpt_ranking.empty:
        st.dataframe(rpt_ranking, use_container_width=True, hide_index=True, height=800)
    else:
        st.info("데이터가 없습니다.")


def page_report_list(start_date, end_date):
    """📋 리포트 목록"""
    st.title("📋 증권사 리포트 목록")

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        rpt_search = st.text_input("🔎 제목 검색", placeholder="종목명 또는 키워드", key="rpt_search")
    with col2:
        firms = run_query("""
            SELECT DISTINCT securities_firm FROM expert_articles
            WHERE securities_firm IS NOT NULL AND published_date BETWEEN %s AND %s
            ORDER BY securities_firm
        """, (start_date, end_date))
        firm_list = ["전체"] + firms["securities_firm"].tolist()
        selected_firm = st.selectbox("🏢 증권사", firm_list, key="rpt_firm")
    with col3:
        rpt_lim = st.selectbox("표시 건수", [50, 100, 200, 500], key="rpt_list_limit")

    # 쿼리 조건
    conditions = ["ea.published_date BETWEEN %s AND %s"]
    params = [start_date, end_date]

    if rpt_search:
        conditions.append("ea.title ILIKE %s")
        params.append(f"%{rpt_search}%")
    if selected_firm != "전체":
        conditions.append("ea.securities_firm = %s")
        params.append(selected_firm)

    params.append(rpt_lim)
    where = " AND ".join(conditions)

    rpt_df = run_query(f"""
        SELECT ea.published_date as "날짜", ea.title as "제목",
               ea.securities_firm as "증권사", ea.author as "작성자",
               eam.target_price as "목표가", eam.opinion as "투자의견",
               t.name as "종목"
        FROM expert_articles ea
        LEFT JOIN expert_article_mentions eam ON eam.article_id = ea.id
        LEFT JOIN tickers t ON t.id = eam.ticker_id
        WHERE {where}
        ORDER BY ea.published_date DESC, ea.id DESC
        LIMIT %s
    """, params)

    st.caption(f"총 {len(rpt_df)}건 표시")
    st.dataframe(rpt_df, use_container_width=True, hide_index=True, height=800)
