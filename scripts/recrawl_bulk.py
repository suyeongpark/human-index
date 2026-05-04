"""
MLB Park 주식 태그 게시글 벌크 수집 (검색 모드)
새 URL로 전체 재수집용 일회성 스크립트
"""

import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import date, datetime
import re
import time

from db_config import DB_CONFIG
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

BASE_URL = (
    "https://mlbpark.donga.com/mp/b.php"
    "?search_select=sct&search_input=&select=spf"
    "&m=search&b=bullpen&query=%EC%A3%BC%EC%8B%9D"
)

DELAY = 0.5  # 서버 부하 방지


def parse_date(text: str) -> date:
    text = text.strip()
    if ":" in text and "-" not in text:
        return date.today()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def crawl_page(offset: int) -> list[dict]:
    url = f"{BASE_URL}&p={offset}"
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
        a = cols[1].select_one("a.txt")
        if not a:
            continue

        title = a.get_text(strip=True)
        href = a.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://mlbpark.donga.com{href}"

        author = re.sub(r"\s+", " ", cols[2].get_text(strip=True)).strip()
        post_date = parse_date(cols[3].get_text(strip=True))

        posts.append({
            "title": title,
            "author": author,
            "post_date": post_date,
            "source_url": href,
        })

    return posts


def main():
    print("=" * 60)
    print("MLB Park 주식 태그 벌크 수집 시작")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)

    # 커뮤니티 확인/생성
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM communities WHERE name = %s", ("MLBPark 불펜",))
            row = cur.fetchone()
            if row:
                community_id = row[0]
            else:
                cur.execute(
                    "INSERT INTO communities (name, base_url, category) VALUES (%s, %s, %s) RETURNING id",
                    ("MLBPark 불펜", "https://mlbpark.donga.com/mp/b.php", "주식"),
                )
                community_id = cur.fetchone()[0]

    total = 0
    empty_streak = 0
    max_pages = 120  # 30 * 120 = 3600건 커버

    for page in range(max_pages):
        offset = page * 30
        try:
            posts = crawl_page(offset)
        except Exception as e:
            print(f"  ⚠ p={offset} 실패: {e}")
            time.sleep(2)
            continue

        if not posts:
            empty_streak += 1
            if empty_streak >= 3:
                print(f"  3회 연속 빈 페이지, 수집 종료")
                break
            continue

        empty_streak = 0
        inserted = 0

        with conn:
            with conn.cursor() as cur:
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

        total += inserted
        oldest = posts[-1]["post_date"] if posts else "?"
        print(f"  p={offset:>4}: +{inserted}/{len(posts)}  (누적: {total}, 최구: {oldest})")
        time.sleep(DELAY)

    conn.close()
    print(f"\n{'=' * 60}")
    print(f"✅ 수집 완료: {total}건")
    print("=" * 60)


if __name__ == "__main__":
    main()
