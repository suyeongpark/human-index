"""
전문가 페이지 모듈 - 증권사 리포트 분석
"""

import streamlit as st
from lib.shared import run_query, paginated_dataframe


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
        paginated_dataframe(top_cover, "pg_top_cover", height=400)

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

    rpt_ranking = run_query("""
        SELECT t.symbol as "심볼", t.name as "종목명",
               COUNT(*) as "리포트 수",
               COUNT(DISTINCT ea.securities_firm) as "증권사 수",
               COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%buy%%' OR eam.opinion = '매수') as "📈 Buy",
               COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%hold%%' OR eam.opinion = '중립') as "➖ Hold",
               COUNT(*) FILTER (WHERE eam.opinion ILIKE '%%sell%%' OR eam.opinion = '매도') as "📉 Sell",
               ROUND(100.0 * COUNT(*) FILTER (WHERE eam.sentiment = 1) / NULLIF(COUNT(*), 0), 1) as "📊 긍정률(%%)",
               ROUND(((AVG(eam.sentiment) + 1) * 50)::numeric, 1) as "🎯 감성 점수",
               ROUND(
                   2.0 * COUNT(*) FILTER (WHERE eam.sentiment = 1) +
                   0.5 * COUNT(*) FILTER (WHERE eam.sentiment = -1) +
                   1.0 * COUNT(*) FILTER (WHERE eam.sentiment = 0)
               , 1) as "⭐ 가중 점수"
        FROM expert_article_mentions eam
        JOIN tickers t ON t.id = eam.ticker_id
        JOIN expert_articles ea ON ea.id = eam.article_id
        WHERE ea.published_date BETWEEN %s AND %s
        GROUP BY t.symbol, t.name
        ORDER BY "⭐ 가중 점수" DESC
    """, (start_date, end_date))

    if not rpt_ranking.empty:
        paginated_dataframe(rpt_ranking, "pg_rpt_ranking")
    else:
        st.info("데이터가 없습니다.")


def page_report_list(start_date, end_date):
    """📋 리포트 목록"""
    st.title("📋 증권사 리포트 목록")

    PAGE_SIZE = 25

    # 페이지 상태 초기화
    if "rpt_page" not in st.session_state:
        st.session_state.rpt_page = 0

    col1, col2 = st.columns([3, 1])
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

    # 쿼리 조건
    conditions = ["ea.published_date BETWEEN %s AND %s"]
    params = [start_date, end_date]

    if rpt_search:
        conditions.append("ea.title ILIKE %s")
        params.append(f"%{rpt_search}%")
    if selected_firm != "전체":
        conditions.append("ea.securities_firm = %s")
        params.append(selected_firm)

    where = " AND ".join(conditions)

    # 총 건수 조회
    count_df = run_query(f"""
        SELECT COUNT(*) as cnt FROM expert_articles ea WHERE {where}
    """, params)
    total = int(count_df["cnt"].iloc[0]) if len(count_df) > 0 else 0

    page = st.session_state.rpt_page
    offset = page * PAGE_SIZE
    query_params = params + [PAGE_SIZE, offset]

    rpt_df = run_query(f"""
        SELECT ea.published_date as "날짜", ea.title as "제목",
               ea.securities_firm as "증권사", ea.author as "작성자",
               TO_CHAR(eam.target_price::numeric, 'FM999,999,999') as "목표가", eam.opinion as "투자의견",
               t.name as "종목",
               ea.source_url as "링크"
        FROM expert_articles ea
        LEFT JOIN expert_article_mentions eam ON eam.article_id = ea.id
        LEFT JOIN tickers t ON t.id = eam.ticker_id
        WHERE {where}
        ORDER BY ea.published_date DESC, ea.id DESC
        LIMIT %s OFFSET %s
    """, query_params)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    st.dataframe(
        rpt_df, use_container_width=True, hide_index=True, height=700,
        column_config={
            "날짜": st.column_config.DateColumn("날짜", width="small"),
            "제목": st.column_config.TextColumn("제목", width="large"),
            "증권사": st.column_config.TextColumn("증권사", width="small"),
            "작성자": st.column_config.TextColumn("작성자", width="small"),
            "목표가": st.column_config.TextColumn("목표가", width="small"),
            "투자의견": st.column_config.TextColumn("투자의견", width="small"),
            "종목": st.column_config.TextColumn("종목", width="small"),
            "링크": st.column_config.LinkColumn("링크", display_text="🔗", width="small"),
        }
    )

    # 페이지 네비게이션
    _, col_prev, col_info, col_next, _ = st.columns([2, 1, 1, 1, 2])
    with col_prev:
        if st.button("⬅️ 이전", disabled=(page == 0), key="rpt_prev", use_container_width=True):
            st.session_state.rpt_page = page - 1
            st.rerun()
    with col_info:
        st.markdown(f"<div style='text-align:center;padding:0.4rem 0;color:#888;'>{page + 1} / {total_pages}</div>", unsafe_allow_html=True)
    with col_next:
        if st.button("다음 ➡️", disabled=(page >= total_pages - 1), key="rpt_next", use_container_width=True):
            st.session_state.rpt_page = page + 1
            st.rerun()

