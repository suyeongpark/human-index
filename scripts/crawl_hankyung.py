"""
한경 컨센서스 - 증권사 리포트 일일 크롤러
consensus.hankyung.com에서 기업 분석 리포트 제목, 작성자, 증권사, 목표가, 투자의견을 수집하여 DB에 저장
매일 장 마감 후 실행하여 당일 발행된 리포트를 수집
"""

import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import date, datetime, timedelta
import re
import time
import logging
import sys

# ─── 로깅 설정 ──────────────────────────────────────────
LOG_DIR = "/Users/suyeongpark/Dev/Suyeongpark/human-index/logs"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/crawl_hankyung.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─── 설정 ──────────────────────────────────────────────
from db_config import DB_CONFIG

SOURCE_NAME = "한경 컨센서스"
SOURCE_TYPE = "report"  # 증권사 리포트
BASE_URL = "https://consensus.hankyung.com/analysis/list"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://consensus.hankyung.com/",
}

DELAY = 1.0  # 서버 부하 방지 (robots.txt Disallow: / 이므로 보수적으로)
PAGENUM = 80  # 한 페이지당 표시 건수 (20, 50, 80 지원)


def ensure_source(cur) -> int:
    """expert_sources 테이블에 한경 컨센서스가 없으면 추가하고 id를 반환"""
    cur.execute(
        "SELECT id FROM expert_sources WHERE name = %s",
        (SOURCE_NAME,),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """
        INSERT INTO expert_sources (name, source_type, base_url, is_active)
        VALUES (%s, %s, %s, TRUE)
        RETURNING id
        """,
        (SOURCE_NAME, SOURCE_TYPE, BASE_URL),
    )
    return cur.fetchone()[0]


def build_url(sdate: date, edate: date, page: int = 1) -> str:
    """기업(business) 탭 리포트 목록 URL 생성"""
    return (
        f"{BASE_URL}?skinType=business"
        f"&sdate={sdate.isoformat()}"
        f"&edate={edate.isoformat()}"
        f"&now_page={page}"
        f"&pagenum={PAGENUM}"
    )


def parse_target_price(text: str) -> str | None:
    """목표가 텍스트를 정리. '0'이나 빈 값은 None"""
    text = text.strip().replace(",", "")
    if not text or text == "0" or text == "-":
        return None
    return text


def parse_opinion(text: str) -> str | None:
    """투자의견 텍스트 정리"""
    text = text.strip()
    if not text or text == "-" or text == "투자의견없음":
        return None
    return text


def extract_ticker_from_title(title: str) -> str | None:
    """제목에서 종목코드 추출. 예: '하이브(352820) ...' → '352820'"""
    match = re.search(r'\((\d{6})\)', title)
    return match.group(1) if match else None


def crawl_page(url: str) -> list[dict]:
    """한 페이지의 리포트 목록을 크롤링"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []

    # 기업 탭: div.table_style01 > table (table 자체에 class 없음)
    table_div = soup.select_one("div.table_style01")
    if not table_div:
        print("  ⚠ div.table_style01을 찾을 수 없습니다.")
        return articles

    table = table_div.select_one("table")
    if not table:
        print("  ⚠ div.table_style01 내 table을 찾을 수 없습니다.")
        return articles

    tbody = table.select_one("tbody")
    if not tbody:
        tbody = table

    rows = tbody.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        # 기업 탭: 9개 td (날짜, 제목, 적정가격, 투자의견, 작성자, 제공출처, 기업정보, 차트, 첨부)
        if len(cols) < 6:
            continue

        # [0] 작성일
        date_text = cols[0].get_text(strip=True)
        try:
            published_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue

        # [1] 제목 (text_l 클래스, a 태그에 제목 텍스트)
        title_el = cols[1].select_one("a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            source_url = f"https://consensus.hankyung.com{href}"
        else:
            source_url = href or None

        # [2] 적정가격
        target_price = parse_target_price(cols[2].get_text(strip=True))

        # [3] 투자의견
        opinion = parse_opinion(cols[3].get_text(strip=True))

        # [4] 작성자
        author = cols[4].get_text(strip=True)
        author = re.sub(r'\s+', ' ', author).strip() or None

        # [5] 제공출처/증권사
        securities_firm = cols[5].get_text(strip=True) or None

        # 제목에서 종목코드 추출
        ticker_symbol = extract_ticker_from_title(title)

        articles.append({
            "title": title,
            "author": author,
            "securities_firm": securities_firm,
            "published_date": published_date,
            "source_url": source_url,
            "target_price": target_price,
            "opinion": opinion,
            "ticker_symbol": ticker_symbol,
        })

    return articles


def get_total_pages(url: str) -> int:
    """페이지네이션에서 마지막 페이지 번호를 추출"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    paging = soup.select_one(".paging")
    if not paging:
        return 1

    max_page = 1
    for a in paging.find_all("a"):
        href = a.get("href", "")
        match = re.search(r'now_page=(\d+)', href)
        if match:
            page_num = int(match.group(1))
            max_page = max(max_page, page_num)

    # strong 태그 (현재 페이지)도 확인
    strong = paging.find("strong")
    if strong:
        try:
            max_page = max(max_page, int(strong.get_text(strip=True)))
        except ValueError:
            pass

    return max_page


def insert_articles(cur, source_id: int, articles: list[dict]) -> tuple[int, int]:
    """리포트를 expert_articles에 삽입. (inserted, skipped) 반환"""
    inserted = 0
    skipped = 0

    for art in articles:
        try:
            cur.execute(
                """
                INSERT INTO expert_articles
                    (source_id, title, author, securities_firm, published_date, source_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_url) WHERE source_url IS NOT NULL
                DO NOTHING
                RETURNING id
                """,
                (
                    source_id,
                    art["title"],
                    art["author"],
                    art["securities_firm"],
                    art["published_date"],
                    art["source_url"],
                ),
            )
            row = cur.fetchone()
            if row:
                article_id = row[0]
                inserted += 1

                # 종목코드가 있으면 expert_article_mentions에도 삽입
                if art["ticker_symbol"]:
                    cur.execute(
                        "SELECT id FROM tickers WHERE symbol = %s",
                        (art["ticker_symbol"],),
                    )
                    ticker_row = cur.fetchone()
                    if ticker_row:
                        # sentiment: 투자의견 기반으로 간단 매핑
                        sentiment = map_opinion_to_sentiment(art["opinion"])
                        cur.execute(
                            """
                            INSERT INTO expert_article_mentions
                                (article_id, ticker_id, sentiment, target_price, opinion)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (article_id, ticker_id) DO NOTHING
                            """,
                            (
                                article_id,
                                ticker_row[0],
                                sentiment,
                                art["target_price"],
                                art["opinion"],
                            ),
                        )
            else:
                skipped += 1
        except Exception as e:
            print(f"  ⚠ 삽입 실패: {art['title'][:30]}... → {e}")
            skipped += 1

    return inserted, skipped


def map_opinion_to_sentiment(opinion: str | None) -> int:
    """투자의견을 sentiment 값으로 매핑"""
    if not opinion:
        return 0

    opinion_lower = opinion.lower().strip()

    # 긍정 (매수 계열)
    positive = ["buy", "매수", "strong buy", "outperform", "overweight", "trading buy", "top pick"]
    # 부정 (매도 계열)
    negative = ["sell", "매도", "strong sell", "underperform", "underweight", "reduce"]
    # 중립
    neutral = ["hold", "neutral", "중립", "marketperform", "market perform", "equal-weight"]

    for kw in positive:
        if kw in opinion_lower:
            return 1
    for kw in negative:
        if kw in opinion_lower:
            return -1
    for kw in neutral:
        if kw in opinion_lower:
            return 0

    return 0


def main():
    log.info("=" * 60)
    log.info("한경 컨센서스 - 증권사 리포트 일일 크롤러")
    log.info("=" * 60)

    # 수집 기간: 최근 3일 (주말/공휴일 대비)
    edate = date.today()
    sdate = edate - timedelta(days=3)
    log.info(f"📅 수집 기간: {sdate} ~ {edate}")

    # 1. 첫 페이지로 총 페이지 수 확인
    first_url = build_url(sdate, edate, page=1)
    log.info(f"📡 URL: {first_url}")

    try:
        total_pages = get_total_pages(first_url)
    except Exception as e:
        log.error(f"❌ 페이지 수 확인 실패: {e}")
        return

    log.info(f"📄 총 페이지: {total_pages}")

    # 2. 전체 페이지 크롤링
    all_articles = []
    for page in range(1, total_pages + 1):
        url = build_url(sdate, edate, page=page)
        log.info(f"  📡 페이지 {page}/{total_pages} 크롤링 중...")

        try:
            articles = crawl_page(url)
            all_articles.extend(articles)
            log.info(f"  ✅ {len(articles)}건 수집")
        except Exception as e:
            log.error(f"  ⚠ 페이지 {page} 실패: {e}")

        if page < total_pages:
            time.sleep(DELAY)

    log.info(f"📊 총 {len(all_articles)}건 수집 완료")

    if not all_articles:
        log.warning("❌ 수집된 리포트가 없습니다. 휴일이거나 페이지 구조가 변경되었을 수 있습니다.")
        return

    # 3. DB 저장
    log.info("💾 DB 저장 중...")
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                source_id = ensure_source(cur)
                inserted, skipped = insert_articles(cur, source_id, all_articles)
                log.info(f"  ✅ 신규 삽입: {inserted}건 / ⏭ 중복 스킵: {skipped}건")

        # 검증 쿼리
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM expert_articles WHERE source_id = %s",
                (source_id,),
            )
            total = cur.fetchone()[0]
            log.info(f"📊 DB 현황: '{SOURCE_NAME}' 리포트 총 {total}건")

            cur.execute(
                """
                SELECT COUNT(DISTINCT eam.ticker_id)
                FROM expert_article_mentions eam
                JOIN expert_articles ea ON ea.id = eam.article_id
                WHERE ea.source_id = %s
                """,
                (source_id,),
            )
            matched = cur.fetchone()[0]
            log.info(f"🎯 종목 매칭: {matched}개 종목")

    except Exception as e:
        log.error(f"❌ DB 저장 실패: {e}")
    finally:
        conn.close()

    log.info("✅ 완료!")


if __name__ == "__main__":
    main()
