"""
Google News 기사 백필 - 기존 기사에 대한 종목 추출 + 감성 분석
daily_worker.py의 build_ticker_map / analyze_sentiment 로직 재사용
"""

import psycopg2
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from db_config import DB_CONFIG
from daily_worker import build_ticker_map, analyze_sentiment

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def backfill_news_mentions():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # 종목 매핑 로드
        ticker_map = build_ticker_map(cur)
        sorted_keywords = sorted(ticker_map.keys(), key=len, reverse=True)

        # 아직 분석 안 된 뉴스 기사 조회
        cur.execute("""
            SELECT ea.id, ea.title
            FROM expert_articles ea
            JOIN expert_sources es ON es.id = ea.source_id
            LEFT JOIN expert_article_mentions eam ON eam.article_id = ea.id
            WHERE es.source_type = 'article' AND eam.id IS NULL
            ORDER BY ea.id
        """)
        unanalyzed = cur.fetchall()
        log.info(f"분석 대상 뉴스 기사: {len(unanalyzed)}건")

        if not unanalyzed:
            log.info("분석할 기사 없음")
            return

        total_mentions = 0
        articles_with_mentions = 0

        for article_id, title in unanalyzed:
            found_tickers = set()
            remaining = title

            for keyword in sorted_keywords:
                if keyword in remaining:
                    ticker_id, symbol = ticker_map[keyword]
                    if ticker_id not in found_tickers:
                        found_tickers.add(ticker_id)
                        sentiment = analyze_sentiment(title)
                        try:
                            cur.execute("""
                                INSERT INTO expert_article_mentions
                                    (article_id, ticker_id, sentiment)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (article_id, ticker_id) DO NOTHING
                            """, (article_id, ticker_id, sentiment))
                            if cur.rowcount > 0:
                                total_mentions += 1
                        except Exception as e:
                            log.warning(f"삽입 실패: {title[:30]}... → {e}")
                    remaining = remaining.replace(keyword, "", 1)

            if found_tickers:
                articles_with_mentions += 1

        conn.commit()
        log.info(f"✅ 완료: {articles_with_mentions}건 기사에서 {total_mentions}건 종목 언급 추출")

    except Exception as e:
        conn.rollback()
        log.error(f"❌ 오류: {e}", exc_info=True)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    backfill_news_mentions()
