"""
MLB Park 불펜 - 주식 카테고리 전체 크롤러
태그 필터(spf) 방식으로 가능한 모든 데이터를 수집하여 human_index DB에 저장
"""

import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import date, datetime
import re
import time
import sys

# ─── 설정 ──────────────────────────────────────────────
from db_config import DB_CONFIG

COMMUNITY_NAME = "MLBPark 불펜"
BASE_URL = "https://mlbpark.donga.com/mp/b.php"
CATEGORY = "주식"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 태그 필터 방식 URL (검색이 아닌 게시판 직접 접근)
TAG_FILTER_URL = (
    "https://mlbpark.donga.com/mp/b.php"
    "?b=bullpen&select=spf&query=%EC%A3%BC%EC%8B%9D"
)

POSTS_PER_PAGE = 30
REQUEST_DELAY = 0.5  # 요청 간 딜레이 (초) - 서버 부하 방지


def ensure_community(cur) -> int:
    """communities 테이블에 MLBPark 불펜이 없으면 추가하고 id를 반환"""
    cur.execute("SELECT id FROM communities WHERE name = %s", (COMMUNITY_NAME,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """
        INSERT INTO communities (name, base_url, category, is_active)
        VALUES (%s, %s, %s, TRUE)
        RETURNING id
        """,
        (COMMUNITY_NAME, BASE_URL, CATEGORY),
    )
    return cur.fetchone()[0]


def parse_post_date(date_text: str) -> date:
    """MLB Park 날짜 형식 파싱"""
    date_text = date_text.strip()
    if ":" in date_text and "-" not in date_text:
        return date.today()
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def crawl_page(url: str) -> list[dict]:
    """한 페이지의 게시글 목록을 크롤링"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    posts = []
    table = soup.select_one("table.tbl_type01")
    if not table:
        return posts

    rows = table.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        title_el = cols[1].select_one("a.txt")
        if not title_el:
            title_el = row.select_one("a.txt")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")

        if href and not href.startswith("http"):
            source_url = f"https://mlbpark.donga.com{href}"
        else:
            source_url = href

        author = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        author = re.sub(r'\s+', ' ', author).strip()

        date_text = cols[3].get_text(strip=True) if len(cols) > 3 else ""
        post_date = parse_post_date(date_text)

        posts.append({
            "title": title,
            "author": author,
            "post_date": post_date,
            "source_url": source_url,
        })

    return posts


def main():
    print("=" * 60)
    print("MLB Park 불펜 - 주식 전체 크롤러")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                community_id = ensure_community(cur)
                print(f"커뮤니티: {COMMUNITY_NAME} (ID: {community_id})")

        total_inserted = 0
        total_skipped = 0
        empty_count = 0
        page_num = 0

        while True:
            offset = page_num * POSTS_PER_PAGE
            url = f"{TAG_FILTER_URL}&p={offset}"

            posts = crawl_page(url)

            if not posts or len(posts) < 10:
                empty_count += 1
                if empty_count >= 3:
                    print(f"\n⛔ 연속 {empty_count}회 빈 페이지 → 크롤링 종료")
                    break
                page_num += 1
                continue

            empty_count = 0

            # 날짜 범위 표시
            dates = [p["post_date"] for p in posts]
            min_date = min(dates)
            max_date = max(dates)

            # DB 삽입
            with conn:
                with conn.cursor() as cur:
                    inserted = 0
                    for post in posts:
                        cur.execute(
                            """
                            INSERT INTO posts (community_id, title, author, post_date, source_url)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (source_url) WHERE source_url IS NOT NULL
                            DO NOTHING
                            """,
                            (community_id, post["title"], post["author"],
                             post["post_date"], post["source_url"]),
                        )
                        if cur.rowcount > 0:
                            inserted += 1

            skipped = len(posts) - inserted
            total_inserted += inserted
            total_skipped += skipped

            # 진행 상황
            sys.stdout.write(
                f"\r  페이지 {page_num+1:>4} (p={offset:>5}) | "
                f"{min_date} ~ {max_date} | "
                f"+{inserted:>2} 신규, {skipped:>2} 스킵 | "
                f"누적: {total_inserted:>5}건"
            )
            sys.stdout.flush()

            page_num += 1
            time.sleep(REQUEST_DELAY)

        print(f"\n\n{'=' * 60}")
        print(f"📊 수집 결과")
        print(f"  총 페이지: {page_num}")
        print(f"  신규 삽입: {total_inserted}건")
        print(f"  중복 스킵: {total_skipped}건")

        # 최종 통계
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), MIN(post_date), MAX(post_date) FROM posts WHERE community_id = %s",
                (community_id,),
            )
            total, min_d, max_d = cur.fetchone()
            print(f"\n📊 DB 현황:")
            print(f"  총 게시글: {total}건")
            print(f"  날짜 범위: {min_d} ~ {max_d}")

            # 일별 분포
            cur.execute(
                """
                SELECT post_date, COUNT(*) as cnt
                FROM posts WHERE community_id = %s
                GROUP BY post_date ORDER BY post_date DESC LIMIT 10
                """,
                (community_id,),
            )
            rows = cur.fetchall()
            print(f"\n📅 일별 수집 현황 (최근 10일):")
            for row in rows:
                bar = "█" * min(row[1] // 2, 40)
                print(f"  {row[0]} | {row[1]:>4}건 {bar}")

    finally:
        conn.close()

    print(f"\n✅ 완료!")


if __name__ == "__main__":
    main()
