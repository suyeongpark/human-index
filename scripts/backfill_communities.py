"""
Human Index - 과거 데이터 백필 스크립트
2025년 1월 1일부터 현재까지의 커뮤니티 게시글을 수집합니다.

사용법:
    python scripts/backfill_communities.py

주의:
    - 로컬에서 실행합니다 (GitHub Actions 아님)
    - 수천 페이지를 크롤링하므로 수 시간 소요될 수 있습니다
    - source_url 기준 중복 자동 방지 (ON CONFLICT DO NOTHING)
    - Ctrl+C로 중단해도 이미 저장된 데이터는 유지됩니다 (페이지 단위 커밋)
"""

import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import date, datetime
import re
import time
import logging
import os
import sys

# ─── 로깅 설정 ──────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f"backfill_{date.today().isoformat()}.log"),
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─── DB 설정 ────────────────────────────────────────────
from db_config import DB_CONFIG

# ─── 설정 ───────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

CUTOFF_DATE = date(2025, 1, 1)  # 이 날짜 이전 글은 수집하지 않음
REQUEST_DELAY = 1.0  # 서버 부담 최소화 (벌크이므로 넉넉하게)
MAX_PAGES = 2000  # 안전 상한

COMMUNITIES = [
    {
        "name": "MLBPark 불펜",
        "base_url": "https://mlbpark.donga.com/mp/b.php",
        "category": "주식",
        "crawl_url": (
            "https://mlbpark.donga.com/mp/b.php"
            "?search_select=sct&search_input=&select=spf"
            "&m=search&b=bullpen&query=%EC%A3%BC%EC%8B%9D"
        ),
        "posts_per_page": 30,
        "parser": "mlbpark",
    },
    {
        "name": "클리앙 투자",
        "base_url": "https://www.clien.net/service/board/cm_stock",
        "category": "주식",
        "crawl_url": "https://www.clien.net/service/board/cm_stock",
        "posts_per_page": 30,
        "parser": "clien",
    },
    {
        "name": "에펨코리아 주식",
        "base_url": "https://www.fmkorea.com/stock",
        "category": "주식",
        "crawl_url": "https://www.fmkorea.com/index.php?mid=stock",
        "posts_per_page": 20,
        "parser": "fmkorea",
    },
]


# ─── 파서 ───────────────────────────────────────────────

def parse_date(date_text: str) -> date:
    """날짜 문자열 파싱 (여러 커뮤니티 형식 대응)"""
    date_text = date_text.strip()
    if not date_text:
        return date.today()

    # "14:30" 같은 시간만 → 오늘
    if ":" in date_text and "-" not in date_text and "." not in date_text:
        return date.today()

    # "2026-05-04" (MLB Park)
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        pass

    # "2026-04-12 00:41:38" (클리앙)
    try:
        return datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        pass

    # "2026.05.04" 또는 "05.04"
    try:
        return datetime.strptime(date_text, "%Y.%m.%d").date()
    except ValueError:
        pass

    try:
        return datetime.strptime(f"{date.today().year}.{date_text}", "%Y.%m.%d").date()
    except ValueError:
        pass

    return date.today()


def crawl_mlbpark_page(url: str) -> list[dict]:
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
            "post_date": parse_date(date_text),
            "source_url": href,
        })
    return posts


def crawl_clien_page(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    posts = []
    for item in soup.select("div.list_item"):
        title_el = item.select_one("a.list_subject")
        if not title_el:
            continue
        title_spans = title_el.find_all("span")
        title = title_spans[-1].get_text(strip=True) if title_spans else title_el.get_text(strip=True)
        if not title:
            continue
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://www.clien.net{href}"
        author_el = item.select_one("span.nickname")
        author = author_el.get_text(strip=True) if author_el else ""
        time_el = item.select_one("span.timestamp")
        date_text = time_el.get_text(strip=True) if time_el else ""
        posts.append({
            "title": title,
            "author": re.sub(r"\s+", " ", author).strip(),
            "post_date": parse_date(date_text),
            "source_url": href,
        })
    return posts


def crawl_fmkorea_page(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    posts = []
    for row in soup.select("tr"):
        title_td = row.select_one("td.title")
        if not title_td:
            continue
        title_a = title_td.select_one("a")
        if not title_a:
            continue
        notice = row.select_one("td.notice")
        if notice:
            continue
        for reply_span in title_a.select("span.replyNum"):
            reply_span.decompose()
        title = title_a.get_text(strip=True)
        if not title:
            continue
        href = title_a.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://www.fmkorea.com{href}"
        author_el = row.select_one("td.author") or row.select_one("a.member_plate")
        author = author_el.get_text(strip=True) if author_el else ""
        time_el = row.select_one("td.time")
        date_text = time_el.get_text(strip=True) if time_el else ""
        posts.append({
            "title": title,
            "author": re.sub(r"\s+", " ", author).strip(),
            "post_date": parse_date(date_text),
            "source_url": href,
        })
    return posts


PARSERS = {
    "mlbpark": crawl_mlbpark_page,
    "clien": crawl_clien_page,
    "fmkorea": crawl_fmkorea_page,
}


def build_page_url(community: dict, page: int) -> str:
    parser = community["parser"]
    base = community["crawl_url"]
    if parser == "mlbpark":
        offset = page * community["posts_per_page"]
        return f"{base}&p={offset}"
    elif parser == "clien":
        return f"{base}?&po={page}" if page > 0 else base
    elif parser == "fmkorea":
        return f"{base}&page={page + 1}" if page > 0 else base
    return base


def ensure_community(cur, community: dict) -> int:
    cur.execute("SELECT id FROM communities WHERE name = %s", (community["name"],))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO communities (name, base_url, category) VALUES (%s, %s, %s) RETURNING id",
        (community["name"], community["base_url"], community["category"]),
    )
    return cur.fetchone()[0]


def backfill_community(conn, community: dict) -> int:
    """날짜 기반 백필: CUTOFF_DATE 이전 게시글이 나오면 종료"""
    cur = conn.cursor()
    community_id = ensure_community(cur, community)
    conn.commit()

    total_inserted = 0
    consecutive_old_pages = 0

    parser_name = community["parser"]
    parse_fn = PARSERS[parser_name]

    log.info(f"[{community['name']}] 백필 시작 (목표: {CUTOFF_DATE} 이후)")

    for page in range(MAX_PAGES):
        url = build_page_url(community, page)

        try:
            posts = parse_fn(url)
        except Exception as e:
            log.warning(f"  페이지 {page+1} 크롤링 실패: {e}")
            time.sleep(REQUEST_DELAY * 3)
            continue

        if not posts:
            log.info(f"  페이지 {page+1}: 게시글 없음, 종료")
            break

        # CUTOFF_DATE 이전 글 필터링
        old_count = sum(1 for p in posts if p["post_date"] < CUTOFF_DATE)
        fresh_posts = [p for p in posts if p["post_date"] >= CUTOFF_DATE]

        inserted = 0
        for post in fresh_posts:
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

        conn.commit()
        total_inserted += inserted

        if page % 10 == 0 or inserted > 0:
            log.info(f"  페이지 {page+1}: +{inserted} 신규 / {len(posts)} 수집 (이전 날짜: {old_count}건)")

        # 전체 게시글이 CUTOFF_DATE 이전이면 종료
        if old_count == len(posts):
            consecutive_old_pages += 1
            if consecutive_old_pages >= 3:
                log.info(f"  3연속 과거 페이지 → 종료 (총 {page+1}페이지)")
                break
        else:
            consecutive_old_pages = 0

        time.sleep(REQUEST_DELAY)

    log.info(f"[{community['name']}] 백필 완료: {total_inserted}건 신규 삽입")
    cur.close()
    return total_inserted


def main():
    log.info("=" * 60)
    log.info(f"과거 데이터 백필 시작 (목표: {CUTOFF_DATE} ~ 현재)")
    log.info("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    grand_total = 0

    for community in COMMUNITIES:
        try:
            inserted = backfill_community(conn, community)
            grand_total += inserted
        except KeyboardInterrupt:
            log.info("사용자 중단 (Ctrl+C)")
            break
        except Exception as e:
            log.error(f"[{community['name']}] 에러: {e}")
            continue

    conn.close()
    log.info("=" * 60)
    log.info(f"백필 완료! 총 {grand_total}건 신규 삽입")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
