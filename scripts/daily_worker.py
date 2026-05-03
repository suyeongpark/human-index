"""
Human Index - Daily Worker Service
매일 정해진 시간에 실행되는 데이터 수집 파이프라인

파이프라인:
  1. 크롤링: 지정된 커뮤니티에서 새 게시글 수집
  2. 종목 추출: 미분석 게시글에서 종목 매칭 + 감성 분석
  3. 통계 집계: 당일 mention_daily_stats 갱신
"""

import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import date, datetime, timedelta
import re
import time
import logging
import os
import sys

# ─── 로깅 설정 ────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f"worker_{date.today().isoformat()}.log"),
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("worker")

# ─── 설정 ──────────────────────────────────────────────
DB_CONFIG = {
    "dbname": "human_index",
    "host": "localhost",
    "port": 5432,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_DELAY = 0.5  # 페이지 간 딜레이 (초)

# ─── 크롤링 대상 커뮤니티 정의 ──────────────────────────
COMMUNITIES = [
    {
        "name": "MLBPark 불펜",
        "base_url": "https://mlbpark.donga.com/mp/b.php",
        "category": "주식",
        "crawl_url": (
            "https://mlbpark.donga.com/mp/b.php"
            "?b=bullpen&select=spf&query=%EC%A3%BC%EC%8B%9D"
        ),
        "posts_per_page": 30,
        "max_pages": 5,  # 일일 크롤링 시 최근 5페이지만 (150건)
    },
    # 추후 다른 커뮤니티 추가 가능
    # {
    #     "name": "디시인사이드 주식갤러리",
    #     "base_url": "https://gall.dcinside.com/board/lists/?id=stock",
    #     ...
    # },
]

# ─── 종목 사전 (한글 별칭 → ticker 매핑) ─────────────
# DB에 등록된 종목과 별칭의 매핑
TICKER_ALIASES = {
    # KRX 주요 종목 별칭
    "삼성전자": "005930", "삼전": "005930",
    "SK하이닉스": "000660", "하이닉스": "000660", "하닉": "000660",
    "LG에너지": "373220", "LG엔솔": "373220",
    "삼성전자우": "005935", "삼전우": "005935",
    "삼성SDI": "006400", "삼성sdi": "006400",
    "LG화학": "051910",
    "포스코": "005490", "POSCO": "005490",
    "네이버": "035420", "NAVER": "035420",
    "카카오": "035720",
    "기아차": "000270", "기아": "000270",
    "현대차": "005380", "현대자동차": "005380",
    "셀트리온": "068270",
    "현대모비스": "012330",
    "삼성물산": "028260",
    "삼성전기": "009150",
    "LG전자": "066570",
    "한화에어로": "012450", "한화에어": "012450",
    "한화시스템": "272210",
    "한화": "000880",
    "한미반도체": "042700",
    "에코프로비엠": "247540", "에코프로": "247540",
    "크래프톤": "259960",
    "하이브": "352820",
    "HMM": "011200",
    "삼성SDS": "018260",
    "고려아연": "010130",
    "KB금융": "105560",
    "신한지주": "055550", "신한금융": "055550",
    "삼성생명": "032830",
    # 미국 주요 종목 한글 별칭
    "애플": "AAPL", "Apple": "AAPL", "AAPL": "AAPL",
    "마이크로소프트": "MSFT", "마소": "MSFT",
    "알파벳": "GOOGL", "구글": "GOOGL", "Google": "GOOGL",
    "아마존": "AMZN", "Amazon": "AMZN",
    "엔비디아": "NVDA", "NVIDIA": "NVDA",
    "테슬라": "TSLA", "Tesla": "TSLA",
    "메타": "META", "페이스북": "META",
    "넷플릭스": "NFLX", "Netflix": "NFLX",
    "마이크론": "MU", "Micron": "MU",
    "인텔": "INTC", "Intel": "INTC",
    "AMD": "AMD",
    "TSMC": "TSM",
    "브로드컴": "AVGO", "Broadcom": "AVGO",
    "ARM": "ARM",
    "ASML": "ASML",
    "샌디스크": "SNDK", "웨스턴디지털": "WDC",
    "시게이트": "STX",
    "팔란티어": "PLTR", "Palantir": "PLTR",
    "소파이": "SOFI",
    "퀄컴": "QCOM",
    "코인베이스": "COIN",
    "화이자": "PFE",
    "모더나": "MRNA",
    "록히드마틴": "LMT", "록히드": "LMT",
    "보잉": "BA",
    "코스트코": "COST",
    "디즈니": "DIS",
    # ETF
    "QQQ": "QQQ", "TQQQ": "TQQQ", "SOXL": "SOXL",
    "SCHD": "SCHD", "SPY": "SPY",
}

# 감성 분석 키워드
POSITIVE_WORDS = [
    "상승", "급등", "폭등", "상한가", "신고가", "돌파", "오르",
    "올라", "올랐", "매수", "사야", "호재", "기대", "수익",
    "대박", "반등", "회복", "날아", "간다", "갑니다", "가즈아",
]

NEGATIVE_WORDS = [
    "하락", "급락", "폭락", "폭망", "하한가", "추락", "내려",
    "떨어", "빠지", "매도", "팔아", "악재", "하방", "손절",
    "망했", "물렸", "파업", "리스크", "규제", "제재", "우려",
]


# ═══════════════════════════════════════════════════════
# STEP 1: 크롤링
# ═══════════════════════════════════════════════════════

def ensure_community(cur, community: dict) -> int:
    """커뮤니티 존재 확인/생성"""
    cur.execute("SELECT id FROM communities WHERE name = %s", (community["name"],))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO communities (name, base_url, category) VALUES (%s, %s, %s) RETURNING id",
        (community["name"], community["base_url"], community["category"]),
    )
    return cur.fetchone()[0]


def parse_post_date(date_text: str) -> date:
    """MLB Park 날짜 파싱"""
    date_text = date_text.strip()
    if ":" in date_text and "-" not in date_text:
        return date.today()
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def crawl_mlbpark_page(url: str) -> list[dict]:
    """MLB Park 한 페이지 크롤링"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    posts = []
    table = soup.select_one("table.tbl_type01")
    if not table:
        return posts

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        title_el = cols[1].select_one("a.txt")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://mlbpark.donga.com{href}"

        author = cols[2].get_text(strip=True)
        date_text = cols[3].get_text(strip=True)

        posts.append({
            "title": title,
            "author": re.sub(r"\s+", " ", author).strip(),
            "post_date": parse_post_date(date_text),
            "source_url": href,
        })

    return posts


def crawl_community(cur, community: dict) -> int:
    """커뮤니티 크롤링 + DB 저장. 신규 삽입 건수 반환."""
    community_id = ensure_community(cur, community)
    total_inserted = 0
    consecutive_zero = 0

    for page in range(community["max_pages"]):
        offset = page * community["posts_per_page"]
        url = f"{community['crawl_url']}&p={offset}"

        try:
            posts = crawl_mlbpark_page(url)
        except Exception as e:
            log.warning(f"  페이지 {page+1} 크롤링 실패: {e}")
            continue

        if not posts:
            consecutive_zero += 1
            if consecutive_zero >= 2:
                break
            continue

        consecutive_zero = 0
        inserted = 0

        for post in posts:
            cur.execute(
                """
                INSERT INTO posts (community_id, title, author, post_date, source_url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
                """,
                (community_id, post["title"], post["author"],
                 post["post_date"], post["source_url"]),
            )
            if cur.rowcount > 0:
                inserted += 1

        total_inserted += inserted
        log.info(f"  페이지 {page+1}: +{inserted} 신규 / {len(posts)} 수집")
        time.sleep(REQUEST_DELAY)

    return total_inserted


# ═══════════════════════════════════════════════════════
# STEP 2: 종목 추출 + 감성 분석
# ═══════════════════════════════════════════════════════

def analyze_sentiment(title: str) -> int:
    """제목 기반 감성 분석"""
    pos = sum(1 for w in POSITIVE_WORDS if w in title)
    neg = sum(1 for w in NEGATIVE_WORDS if w in title)
    if pos > neg:
        return 1
    elif neg > pos:
        return -1
    return 0


def build_ticker_map(cur) -> dict:
    """DB의 tickers 테이블 기반으로 alias → ticker_id 매핑 구성"""
    ticker_map = {}  # alias → (ticker_id, symbol)

    # TICKER_ALIASES의 각 alias에 대해 DB에서 ticker_id 조회
    cur.execute("SELECT id, symbol, name FROM tickers")
    db_tickers = {row[1]: (row[0], row[2]) for row in cur.fetchall()}

    for alias, symbol in TICKER_ALIASES.items():
        if symbol in db_tickers:
            ticker_id, name = db_tickers[symbol]
            ticker_map[alias] = (ticker_id, symbol)

    return ticker_map


def extract_tickers_for_new_posts(cur) -> int:
    """미분석 게시글에서 종목 추출 + 감성 분석"""
    ticker_map = build_ticker_map(cur)
    if not ticker_map:
        log.warning("  종목 매핑이 비어있습니다")
        return 0

    # 길이 역순 정렬 (긴 매칭 우선)
    sorted_aliases = sorted(ticker_map.keys(), key=len, reverse=True)

    # 아직 분석하지 않은 게시글 조회
    cur.execute("""
        SELECT p.id, p.title
        FROM posts p
        LEFT JOIN post_mentions pm ON pm.post_id = p.id
        WHERE pm.id IS NULL
        ORDER BY p.id
    """)
    unanalyzed = cur.fetchall()

    if not unanalyzed:
        log.info("  분석할 새 게시글 없음")
        return 0

    total_mentions = 0
    for post_id, title in unanalyzed:
        found_tickers = set()
        remaining = title

        for alias in sorted_aliases:
            if alias in remaining:
                ticker_id, symbol = ticker_map[alias]
                if ticker_id not in found_tickers:
                    found_tickers.add(ticker_id)
                    sentiment = analyze_sentiment(title)
                    try:
                        cur.execute(
                            """
                            INSERT INTO post_mentions (post_id, ticker_id, sentiment)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (post_id, ticker_id) DO NOTHING
                            """,
                            (post_id, ticker_id, sentiment),
                        )
                        if cur.rowcount > 0:
                            total_mentions += 1
                    except Exception:
                        pass
                remaining = remaining.replace(alias, "", 1)

    return total_mentions


# ═══════════════════════════════════════════════════════
# STEP 3: 일별 통계 갱신
# ═══════════════════════════════════════════════════════

def update_daily_stats(cur, target_date: date = None) -> int:
    """특정 날짜의 mention_daily_stats를 갱신"""
    if target_date is None:
        target_date = date.today()

    # 해당 날짜 기존 통계 삭제
    cur.execute("DELETE FROM mention_daily_stats WHERE stat_date = %s", (target_date,))

    # 커뮤니티별 통계
    cur.execute("""
        INSERT INTO mention_daily_stats
            (ticker_id, community_id, stat_date, mention_count,
             positive_count, negative_count, neutral_count)
        SELECT
            pm.ticker_id, p.community_id, p.post_date,
            COUNT(*),
            COUNT(*) FILTER (WHERE pm.sentiment = 1),
            COUNT(*) FILTER (WHERE pm.sentiment = -1),
            COUNT(*) FILTER (WHERE pm.sentiment = 0)
        FROM post_mentions pm
        JOIN posts p ON p.id = pm.post_id
        WHERE p.post_date = %s
        GROUP BY pm.ticker_id, p.community_id, p.post_date
    """, (target_date,))
    community_stats = cur.rowcount

    # 전체 합산 통계 (community_id = NULL)
    cur.execute("""
        INSERT INTO mention_daily_stats
            (ticker_id, community_id, stat_date, mention_count,
             positive_count, negative_count, neutral_count)
        SELECT
            pm.ticker_id, NULL, p.post_date,
            COUNT(*),
            COUNT(*) FILTER (WHERE pm.sentiment = 1),
            COUNT(*) FILTER (WHERE pm.sentiment = -1),
            COUNT(*) FILTER (WHERE pm.sentiment = 0)
        FROM post_mentions pm
        JOIN posts p ON p.id = pm.post_id
        WHERE p.post_date = %s
        GROUP BY pm.ticker_id, p.post_date
    """, (target_date,))

    return community_stats + cur.rowcount


# ═══════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════

def run_pipeline():
    """일일 파이프라인 실행"""
    start_time = datetime.now()
    log.info("=" * 60)
    log.info(f"Human Index Daily Worker 시작 - {start_time.isoformat()}")
    log.info("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        # STEP 1: 크롤링
        log.info("\n📡 STEP 1: 크롤링")
        total_new = 0
        for community in COMMUNITIES:
            log.info(f"  [{community['name']}] 크롤링 시작...")
            with conn:
                with conn.cursor() as cur:
                    new_posts = crawl_community(cur, community)
                    total_new += new_posts
                    log.info(f"  [{community['name']}] 완료: {new_posts}건 신규")

        # STEP 2: 종목 추출
        log.info("\n🔍 STEP 2: 종목 추출 + 감성 분석")
        with conn:
            with conn.cursor() as cur:
                mentions = extract_tickers_for_new_posts(cur)
                log.info(f"  {mentions}건 종목 언급 추출")

        # STEP 3: 통계 갱신 (오늘 + 어제)
        log.info("\n📊 STEP 3: 일별 통계 갱신")
        with conn:
            with conn.cursor() as cur:
                today = date.today()
                yesterday = today - timedelta(days=1)

                stats_today = update_daily_stats(cur, today)
                stats_yesterday = update_daily_stats(cur, yesterday)
                log.info(f"  오늘({today}): {stats_today}건")
                log.info(f"  어제({yesterday}): {stats_yesterday}건")

        # 결과 요약
        elapsed = (datetime.now() - start_time).total_seconds()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM posts")
            total_posts = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM post_mentions")
            total_mentions = cur.fetchone()[0]

        log.info(f"\n{'=' * 60}")
        log.info(f"✅ 완료 ({elapsed:.1f}초)")
        log.info(f"  신규 게시글: {total_new}건")
        log.info(f"  신규 종목 언급: {mentions}건")
        log.info(f"  DB 현황: posts={total_posts}, mentions={total_mentions}")
        log.info("=" * 60)

    except Exception as e:
        log.error(f"❌ 파이프라인 오류: {e}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_pipeline()
