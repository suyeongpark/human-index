"""
MLB Park 불펜 - 주식 카테고리 게시글 제목 크롤러 (테스트용)
커뮤니티 게시글 제목, 작성자, 날짜를 수집하여 human_index DB에 저장
"""

import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import date, datetime
import re

# ─── 설정 ──────────────────────────────────────────────
DB_CONFIG = {
    "dbname": "human_index",
    "host": "localhost",
    "port": 5432,
}

COMMUNITY_NAME = "MLBPark 불펜"
BASE_URL = "https://mlbpark.donga.com/mp/b.php"
SEARCH_URL = (
    "https://mlbpark.donga.com/mp/b.php"
    "?select=sct&m=search&b=bullpen&select=spf&query=%EC%A3%BC%EC%8B%9D"
)
CATEGORY = "주식"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def ensure_community(cur) -> int:
    """communities 테이블에 MLBPark 불펜이 없으면 추가하고 id를 반환"""
    cur.execute(
        "SELECT id FROM communities WHERE name = %s",
        (COMMUNITY_NAME,),
    )
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
    """
    MLB Park 날짜 형식 파싱
    - 오늘 글: '19:56:12' 형식 → 오늘 날짜 사용
    - 이전 글: '2026-05-02' 형식
    """
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

    # table.tbl_type01 내의 모든 tr (첫 번째는 헤더이므로 skip)
    table = soup.select_one("table.tbl_type01")
    if not table:
        print("  ⚠ table.tbl_type01을 찾을 수 없습니다.")
        # fallback: 모든 a.txt 링크를 수집
        for link in soup.select("a.txt"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://mlbpark.donga.com{href}"
            posts.append({
                "title": title,
                "author": "",
                "post_date": date.today(),
                "source_url": href,
            })
        return posts

    rows = table.find_all("tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        # 제목: 2번째 td (index 1) 안의 a.txt
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

        # 작성자: 3번째 td (index 2)
        author = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        author = re.sub(r'\s+', ' ', author).strip()

        # 날짜: 4번째 td (index 3)
        date_text = cols[3].get_text(strip=True) if len(cols) > 3 else ""
        post_date = parse_post_date(date_text)

        posts.append({
            "title": title,
            "author": author,
            "post_date": post_date,
            "source_url": source_url,
        })

    return posts


def insert_posts(cur, community_id: int, posts: list[dict]) -> tuple[int, int]:
    """게시글들을 DB에 삽입. (inserted, skipped) 반환"""
    inserted = 0
    skipped = 0

    for post in posts:
        try:
            cur.execute(
                """
                INSERT INTO posts (community_id, title, author, post_date, source_url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_url) WHERE source_url IS NOT NULL
                DO NOTHING
                """,
                (
                    community_id,
                    post["title"],
                    post["author"],
                    post["post_date"],
                    post["source_url"],
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ⚠ 삽입 실패: {post['title'][:30]}... → {e}")
            skipped += 1

    return inserted, skipped


def main():
    print("=" * 60)
    print("MLB Park 불펜 - 주식 게시글 크롤러")
    print("=" * 60)

    # 1. 크롤링
    print(f"\n📡 크롤링 중: {SEARCH_URL[:80]}...")
    posts = crawl_page(SEARCH_URL)
    print(f"✅ {len(posts)}개 게시글 수집 완료")

    if not posts:
        print("❌ 수집된 게시글이 없습니다. 페이지 구조가 변경되었을 수 있습니다.")
        # 디버깅용 HTML 저장
        resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        debug_path = "/Users/suyeongpark/Dev/Suyeongpark/human-index/scripts/debug_page.html"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"  디버깅용 HTML 저장: {debug_path}")
        return

    # 미리보기
    print("\n📋 수집된 게시글 미리보기:")
    print("-" * 60)
    for i, p in enumerate(posts[:5], 1):
        print(f"  {i}. [{p['post_date']}] {p['title'][:50]}")
        print(f"     작성자: {p['author']}")
    if len(posts) > 5:
        print(f"  ... 외 {len(posts) - 5}개")

    # 2. DB 저장
    print(f"\n💾 DB 저장 중... (human_index)")
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                community_id = ensure_community(cur)
                print(f"  커뮤니티 ID: {community_id} ({COMMUNITY_NAME})")

                inserted, skipped = insert_posts(cur, community_id, posts)
                print(f"  ✅ 신규 삽입: {inserted}건")
                print(f"  ⏭ 중복 스킵: {skipped}건")

        # 검증 쿼리
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM posts WHERE community_id = %s", (community_id,))
            total = cur.fetchone()[0]
            print(f"\n📊 DB 현황: posts 테이블 내 '{COMMUNITY_NAME}' 게시글 총 {total}건")

            cur.execute(
                """
                SELECT post_date, title, author
                FROM posts
                WHERE community_id = %s
                ORDER BY id DESC
                LIMIT 5
                """,
                (community_id,),
            )
            rows = cur.fetchall()
            if rows:
                print("\n📋 최근 저장된 게시글:")
                print("-" * 60)
                for row in rows:
                    print(f"  [{row[0]}] {row[1][:50]} (by {row[2]})")

    finally:
        conn.close()

    print("\n✅ 완료!")


if __name__ == "__main__":
    main()
