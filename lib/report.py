"""
전문가 페이지 모듈 - 증권사 리포트 분석 (리포트만, 뉴스 기사 제외)
"""

import streamlit as st
from lib.shared import run_query, paginated_dataframe, period_tabs, render_top10_chart, render_surge_page, render_colored_line_chart, PERIOD_OPTIONS, PERIOD_SQL, PERIOD_DAYS


def page_overview(start_date, end_date):
    """📈 리포트 개요"""
    st.title("🔬 리포트 대시보드")
    st.caption("증권사 리포트 분석")

    kpi_ex = run_query("""
        SELECT
            (SELECT COUNT(*) FROM expert_articles ea
             JOIN expert_sources es ON es.id = ea.source_id
             WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report') as total_reports,
            (SELECT COUNT(DISTINCT eam.ticker_id) FROM expert_article_mentions eam
             JOIN expert_articles ea ON ea.id = eam.article_id
             JOIN expert_sources es ON es.id = ea.source_id
             WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report') as unique_tickers,
            (SELECT COUNT(DISTINCT ea.securities_firm) FROM expert_articles ea
             JOIN expert_sources es ON es.id = ea.source_id
             WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report' AND ea.securities_firm IS NOT NULL) as firms,
            (SELECT COUNT(*) FROM expert_article_mentions eam
             JOIN expert_articles ea ON ea.id = eam.article_id
             JOIN expert_sources es ON es.id = ea.source_id
             WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report' AND eam.sentiment = 1) as buy_cnt,
            (SELECT COUNT(*) FROM expert_article_mentions eam
             JOIN expert_articles ea ON ea.id = eam.article_id
             JOIN expert_sources es ON es.id = ea.source_id
             WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report' AND eam.sentiment <= 0) as other_cnt
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

    # 기간 선택
    period = period_tabs("expert_period")
    date_sel = PERIOD_SQL[period]["select"].format(date_col="ea.published_date")
    date_grp = PERIOD_SQL[period]["group"].format(date_col="ea.published_date")

    # 투자의견 변화 추이
    st.subheader("📈 투자의견 변화 추이")
    expert_trend = run_query(f"""
        SELECT {date_sel} as "날짜",
               COUNT(*) FILTER (WHERE eam.sentiment = 1) as "📈 Buy",
               COUNT(*) FILTER (WHERE eam.sentiment = 0) as "➖ Hold",
               COUNT(*) FILTER (WHERE eam.sentiment = -1) as "📉 Sell"
        FROM expert_article_mentions eam
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
        GROUP BY {date_grp} ORDER BY 1
    """, (start_date, end_date))
    if not expert_trend.empty:
        render_colored_line_chart(expert_trend)

    st.markdown("---")

    # TOP 10 커버 종목
    from datetime import timedelta
    top_end = end_date
    top_start = max(start_date, top_end - timedelta(days=PERIOD_DAYS[period]))
    st.subheader("🔥 TOP 10 커버 종목")
    top_cover = run_query("""
        SELECT t.name as "종목", COUNT(*) as "리포트 수"
        FROM expert_article_mentions eam
        JOIN tickers t ON t.id = eam.ticker_id
        JOIN expert_articles ea ON ea.id = eam.article_id
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
        GROUP BY t.name ORDER BY COUNT(*) DESC LIMIT 10
    """, (top_start, top_end))
    render_top10_chart(top_cover, x_label="리포트 수")


def page_surge_ranking(start_date, end_date):
    """🚀 급상승 랭킹"""
    render_surge_page(
        title="🚀 리포트 급상승 종목",
        query_template="""
            WITH recent AS (
                SELECT eam.ticker_id, COUNT(*) as cnt
                FROM expert_article_mentions eam
                JOIN expert_articles ea ON ea.id = eam.article_id
                JOIN expert_sources es ON es.id = ea.source_id
                WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
                GROUP BY eam.ticker_id
            ),
            prev AS (
                SELECT eam.ticker_id, COUNT(*) as cnt
                FROM expert_article_mentions eam
                JOIN expert_articles ea ON ea.id = eam.article_id
                JOIN expert_sources es ON es.id = ea.source_id
                WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
                GROUP BY eam.ticker_id
            )
            SELECT t.name as "종목",
                   COALESCE(r.cnt, 0) as "최근",
                   COALESCE(p.cnt, 0) as "이전",
                   COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) as "변화량",
                   CASE WHEN COALESCE(p.cnt, 0) > 0
                        THEN ROUND(100.0 * (COALESCE(r.cnt,0) - p.cnt) / p.cnt, 1)
                        ELSE NULL END as "변화율(%%)"
            FROM recent r
            FULL OUTER JOIN prev p ON r.ticker_id = p.ticker_id
            JOIN tickers t ON t.id = COALESCE(r.ticker_id, p.ticker_id)
            WHERE t.market NOT IN ('THEME', 'CRYPTO')
            ORDER BY COALESCE(r.cnt, 0) - COALESCE(p.cnt, 0) DESC
        """,
        period_key="expert_surge_period",
        end_date=end_date,
        start_date=start_date,
        page_key="pg_expert_surge",
    )


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
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE ea.published_date BETWEEN %s AND %s AND es.source_type = 'report'
        GROUP BY t.symbol, t.name
        ORDER BY "⭐ 가중 점수" DESC
    """, (start_date, end_date))

    if not rpt_ranking.empty:
        paginated_dataframe(rpt_ranking, "pg_rpt_ranking")
    else:
        st.info("데이터가 없습니다.")


def page_report_list(start_date, end_date):
    """📋 리포트 목록"""
    st.title("📋 리포트 목록")

    PAGE_SIZE = 25

    if "rpt_page" not in st.session_state:
        st.session_state.rpt_page = 0

    col1, col2 = st.columns([3, 1])
    with col1:
        rpt_search = st.text_input("🔎 제목 검색", placeholder="종목명 또는 키워드", key="rpt_search")
    with col2:
        firms = run_query("""
            SELECT DISTINCT ea.securities_firm FROM expert_articles ea
            JOIN expert_sources es ON es.id = ea.source_id
            WHERE ea.securities_firm IS NOT NULL AND ea.published_date BETWEEN %s AND %s
              AND es.source_type = 'report'
            ORDER BY ea.securities_firm
        """, (start_date, end_date))
        firm_list = ["전체"] + firms["securities_firm"].tolist()
        selected_firm = st.selectbox("🏢 증권사", firm_list, key="rpt_firm")

    # 쿼리 조건
    conditions = ["ea.published_date BETWEEN %s AND %s", "es.source_type = 'report'"]
    params = [start_date, end_date]

    if rpt_search:
        conditions.append("ea.title ILIKE %s")
        params.append(f"%{rpt_search}%")
    if selected_firm != "전체":
        conditions.append("ea.securities_firm = %s")
        params.append(selected_firm)

    where = " AND ".join(conditions)

    count_df = run_query(f"""
        SELECT COUNT(*) as cnt FROM expert_articles ea
        JOIN expert_sources es ON es.id = ea.source_id
        WHERE {where}
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
        JOIN expert_sources es ON es.id = ea.source_id
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
