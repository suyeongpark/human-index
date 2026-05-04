"""
Google News RSS - 증권/종목 뉴스 기사 크롤러
Google News RSS 피드에서 한국 주식 관련 뉴스 기사 제목, 언론사, 날짜를 수집하여
expert_articles 테이블에 source_type='article'로 저장

하루 2회 실행 권장 (장 시작 전 + 장 마감 후)
"""

import xml.etree.ElementTree as ET
import requests
import psycopg2
from datetime import date, datetime
from email.utils import parsedate_to_datetime
import re
import logging
import sys

# ─── 로깅 설정 ──────────────────────────────────────────
LOG_DIR = "/Users/suyeongpark/Dev/Suyeongpark/human-index/logs"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/crawl_google_news.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─── 설정 ──────────────────────────────────────────────
from db_config import DB_CONFIG

# Google News RSS 검색 쿼리 (종목 관련 기사 수집)
RSS_FEEDS = [
    {
        "name": "Google News 종목분석",
        "url": "https://news.google.com/rss/search?q=%EC%A3%BC%EC%8B%9D+%EC%A2%85%EB%AA%A9+%EB%B6%84%EC%84%9D&hl=ko&gl=KR&ceid=KR:ko",
    },
    {
        "name": "Google News 실적",
        "url": "https://news.google.com/rss/search?q=%EC%8B%A4%EC%A0%81+%EB%A7%A4%EC%88%98+%EB%AA%A9%ED%91%9C%EA%B0%80&hl=ko&gl=KR&ceid=KR:ko",
    },
    {
        "name": "Google News 반도체주식",
        "url": "https://news.google.com/rss/search?q=%EB%B0%98%EB%8F%84%EC%B2%B4+%EC%A3%BC%EA%B0%80+%EC%A0%84%EB%A7%9D&hl=ko&gl=KR&ceid=KR:ko",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ═══════════════════════════════════════════════════════
# RSS 파싱
# ═══════════════════════════════════════════════════════

def fetch_rss_articles(url: str) -> list[dict]:
    """Google News RSS에서 기사 목록 파싱"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"

    root = ET.fromstring(resp.text)
    channel = root.find("channel")
    if channel is None:
        return []

    articles = []
    for item in channel.findall("item"):
        raw_title = item.findtext("title", "").strip()
        if not raw_title:
            continue

        # 제목에서 언론사 분리: "기사 제목 - 언론사"
        source_el = item.find("source")
        source_name = source_el.text.strip() if source_el is not None and source_el.text else ""

        # 제목에서 " - 언론사" 접미사 제거
        title = raw_title
        if source_name and raw_title.endswith(f" - {source_name}"):
            title = raw_title[: -(len(source_name) + 3)].strip()

        # 날짜 파싱
        pub_date_str = item.findtext("pubDate", "")
        try:
            pub_dt = parsedate_to_datetime(pub_date_str)
            pub_date = pub_dt.date()
        except Exception:
            pub_date = date.today()

        # 링크 (Google redirect URL)
        link = item.findtext("link", "")

        articles.append({
            "title": title,
            "source": source_name,
            "published_date": pub_date,
            "source_url": link,
        })

    return articles


# ═══════════════════════════════════════════════════════
# DB 저장
# ═══════════════════════════════════════════════════════

def ensure_source(cur, name: str) -> int:
    """expert_sources에 Google News 소스 등록 (없으면 생성)"""
    cur.execute("SELECT id FROM expert_sources WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """
        INSERT INTO expert_sources (name, source_type, base_url)
        VALUES (%s, 'article', 'https://news.google.com')
        RETURNING id
        """,
        (name,),
    )
    return cur.fetchone()[0]


def save_articles(cur, source_id: int, articles: list[dict]) -> int:
    """기사 저장, 중복 무시. 신규 삽입 건수 반환."""
    inserted = 0
    for art in articles:
        cur.execute(
            """
            INSERT INTO expert_articles (source_id, title, author, securities_firm, published_date, source_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
            """,
            (
                source_id,
                art["title"],
                None,  # author: 뉴스 기사는 작성자 미수집
                art["source"],  # securities_firm 컬럼을 언론사로 활용
                art["published_date"],
                art["source_url"],
            ),
        )
        if cur.rowcount > 0:
            inserted += 1
    return inserted


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("Google News 증권 기사 크롤러 시작")
    log.info("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    total_inserted = 0

    try:
        for feed in RSS_FEEDS:
            log.info(f"\n📰 [{feed['name']}] 수집 중...")

            source_id = ensure_source(cur, feed["name"])

            articles = fetch_rss_articles(feed["url"])
            log.info(f"  RSS 기사 수: {len(articles)}건")

            if not articles:
                continue

            inserted = save_articles(cur, source_id, articles)
            total_inserted += inserted
            log.info(f"  신규 저장: {inserted}건")

            conn.commit()

        log.info(f"\n✅ 완료: 총 {total_inserted}건 신규 저장")

    except Exception as e:
        conn.rollback()
        log.error(f"❌ 오류 발생: {e}", exc_info=True)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
