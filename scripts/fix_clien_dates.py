"""클리앙 5/5 잘못된 날짜 데이터 삭제 후 재수집"""
import sys, time, re, requests
from datetime import date, datetime
from bs4 import BeautifulSoup
sys.path.insert(0, 'scripts')
from db_config import DB_CONFIG
import psycopg2

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
CUTOFF = date(2025, 1, 1)

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# 1. 클리앙 5/5 데이터 삭제
cur.execute("SELECT id FROM communities WHERE name = '클리앙 투자'")
cid = cur.fetchone()[0]

cur.execute('SELECT COUNT(*) FROM posts WHERE community_id = %s AND post_date = %s', (cid, '2026-05-05'))
print(f"삭제 대상: {cur.fetchone()[0]}건")

cur.execute('DELETE FROM post_mentions WHERE post_id IN (SELECT id FROM posts WHERE community_id = %s AND post_date = %s)', (cid, '2026-05-05'))
print(f"post_mentions 삭제: {cur.rowcount}건")

cur.execute('DELETE FROM posts WHERE community_id = %s AND post_date = %s', (cid, '2026-05-05'))
print(f"posts 삭제: {cur.rowcount}건")
conn.commit()
print("삭제 완료!")

# 2. 클리앙 재수집 (올바른 날짜 파서 사용)
print("\n" + "="*60)
print("클리앙 백필 시작")
total_inserted = 0
consecutive_old = 0

for page in range(2000):
    url = f"https://www.clien.net/service/board/cm_stock?&po={page}" if page > 0 else "https://www.clien.net/service/board/cm_stock"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  페이지 {page+1} 실패: {e}")
        time.sleep(3)
        continue

    items = soup.select("div.list_item")
    if not items:
        print(f"  페이지 {page+1}: 항목 없음, 종료")
        break

    old_count = 0
    inserted = 0
    for item in items:
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
        author = re.sub(r"\s+", " ", author).strip()
        time_el = item.select_one("span.timestamp")
        date_text = time_el.get_text(strip=True) if time_el else ""

        # 날짜 파싱 (개선된 버전)
        post_date = None
        try:
            post_date = datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S").date()
        except ValueError:
            try:
                post_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                post_date = date.today()

        if post_date < CUTOFF:
            old_count += 1
            continue

        cur.execute(
            "INSERT INTO posts (community_id, title, author, post_date, source_url) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING",
            (cid, title, author, post_date, href),
        )
        if cur.rowcount > 0:
            inserted += 1

    conn.commit()
    total_inserted += inserted

    if page % 50 == 0 or inserted > 0:
        print(f"  페이지 {page+1}: +{inserted} 신규 / {len(items)} 수집 (과거: {old_count}건, 누적 {total_inserted}건)")

    if old_count == len(items):
        consecutive_old += 1
        if consecutive_old >= 3:
            print(f"  3연속 과거 → 종료 (총 {page+1}페이지)")
            break
    else:
        consecutive_old = 0

    time.sleep(1.0)

cur.close()
conn.close()
print(f"\n완료! 총 {total_inserted}건 신규 삽입")
