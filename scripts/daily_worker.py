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
import random

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
from db_config import DB_CONFIG
from crawler_config import HEADERS, COMMUNITIES, build_headers
from data_loader import (
    load_aliases, load_multi_aliases, load_skip_names,
    load_sentiment_words,
)


# ─── SQL 쿼리 ──────────────────────────────────────────

SQL_FIND_COMMUNITY = "SELECT id FROM communities WHERE name = %s"
SQL_INSERT_COMMUNITY = "INSERT INTO communities (name, base_url, category) VALUES (%s, %s, %s) RETURNING id"
SQL_KNOWN_URLS = "SELECT source_url FROM posts WHERE community_id = %s ORDER BY id DESC LIMIT %s"
SQL_INSERT_POST = """
    INSERT INTO posts (community_id, title, author, post_date, source_url)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
"""
SQL_LOAD_TICKERS = "SELECT id, symbol, name, market FROM tickers WHERE is_active = TRUE"
SQL_UNANALYZED_POSTS = """
    SELECT p.id, p.title
    FROM posts p
    LEFT JOIN post_mentions pm ON pm.post_id = p.id
    WHERE pm.id IS NULL
    ORDER BY p.id
    LIMIT %s
"""
SQL_INSERT_MENTION = """
    INSERT INTO post_mentions (post_id, ticker_id, sentiment)
    VALUES (%s, %s, %s)
    ON CONFLICT (post_id, ticker_id) DO NOTHING
"""
SQL_DELETE_DAILY_STATS = "DELETE FROM mention_daily_stats WHERE stat_date = %s"
SQL_INSERT_COMMUNITY_STATS = """
    INSERT INTO mention_daily_stats
        (ticker_id, community_id, stat_date, mention_count,
         positive_count, negative_count, neutral_count)
    SELECT
        pm.ticker_id, p.community_id, DATE(p.post_date),
        COUNT(*),
        COUNT(*) FILTER (WHERE pm.sentiment = 1),
        COUNT(*) FILTER (WHERE pm.sentiment = -1),
        COUNT(*) FILTER (WHERE pm.sentiment = 0)
    FROM post_mentions pm
    JOIN posts p ON p.id = pm.post_id
    WHERE DATE(p.post_date) = %s
    GROUP BY pm.ticker_id, p.community_id, DATE(p.post_date)
"""
SQL_INSERT_TOTAL_STATS = """
    INSERT INTO mention_daily_stats
        (ticker_id, community_id, stat_date, mention_count,
         positive_count, negative_count, neutral_count)
    SELECT
        pm.ticker_id, NULL, DATE(p.post_date),
        COUNT(*),
        COUNT(*) FILTER (WHERE pm.sentiment = 1),
        COUNT(*) FILTER (WHERE pm.sentiment = -1),
        COUNT(*) FILTER (WHERE pm.sentiment = 0)
    FROM post_mentions pm
    JOIN posts p ON p.id = pm.post_id
    WHERE DATE(p.post_date) = %s
    GROUP BY pm.ticker_id, DATE(p.post_date)
"""
SQL_COUNT_POSTS = "SELECT COUNT(*) FROM posts"
SQL_COUNT_MENTIONS = "SELECT COUNT(*) FROM post_mentions"
ANALYZE_BATCH_SIZE = int(os.environ.get("ANALYZE_BATCH_SIZE", "1000"))


# ═══════════════════════════════════════════════════════
# STEP 1: 크롤링
# ═══════════════════════════════════════════════════════

def fetch_page(url: str, parser: str = "default", session=None, referer: str | None = None):
    """페이지 요청. session을 넘기면 쿠키와 연결을 유지한다."""
    client = session or requests
    headers = build_headers(parser, referer=referer) if parser else HEADERS
    return client.get(url, headers=headers, timeout=15)


def ensure_community(cur, community: dict) -> int:
    """커뮤니티 존재 확인/생성"""
    cur.execute(SQL_FIND_COMMUNITY, (community["name"],))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        SQL_INSERT_COMMUNITY,
        (community["name"], community["base_url"], community["category"]),
    )
    return cur.fetchone()[0]


def known_url_limit(community: dict) -> int:
    """중복 판정용 최근 URL 로드량. 얕은 수집은 적게, 깊은 수집은 넉넉히."""
    crawl_depth = community.get("max_pages", 1) * community.get("posts_per_page", 30)
    return min(1000, max(100, crawl_depth * 3))


def parse_post_date(date_text: str) -> datetime:
    """게시글 날짜/시간 파싱 (여러 커뮤니티 형식 대응) → datetime 반환"""
    date_text = date_text.strip()
    if not date_text:
        return datetime.now()

    # "13:02:26" 또는 "14:30" 같은 시간만 → 오늘 + 해당 시간 (미래면 어제)
    if ":" in date_text and "-" not in date_text and "." not in date_text:
        from datetime import timedelta as _td
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(date_text, fmt)
                result = datetime.combine(date.today(), t.time())
                # 크롤링 시점보다 미래이면 전날 글로 판단
                if result > datetime.now():
                    result -= _td(days=1)
                return result
            except ValueError:
                continue
        return datetime.now()

    # "2026-05-04" (MLB Park)
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        pass

    # "2026-04-12 00:41:38" (클리앙)
    try:
        return datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    # "2026.05.04" (일부 커뮤니티)
    try:
        return datetime.strptime(date_text, "%Y.%m.%d")
    except ValueError:
        pass

    # "05.04" (에펨코리아 올해)
    try:
        return datetime.strptime(f"{date.today().year}.{date_text}", "%Y.%m.%d")
    except ValueError:
        pass

    return datetime.now()



def crawl_mlbpark_page(url: str, session=None, referer: str | None = None) -> list[dict]:
    """MLB Park 한 페이지 크롤링"""
    resp = fetch_page(url, "mlbpark", session=session, referer=referer)
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
        # URL 정규화: p= 파라미터가 다르면 같은 글이 중복 저장되므로 id 기반 URL로 통일
        id_match = re.search(r"id=(\d+)", href)
        if id_match:
            href = f"https://mlbpark.donga.com/mp/b.php?id={id_match.group(1)}&b=bullpen"

        author = cols[2].get_text(strip=True)
        date_text = cols[3].get_text(strip=True)

        posts.append({
            "title": title,
            "author": re.sub(r"\s+", " ", author).strip(),
            "post_date": parse_post_date(date_text),
            "source_url": href,
        })

    return posts


def crawl_clien_page(url: str, session=None, referer: str | None = None) -> list[dict]:
    """클리앙 투자게시판 한 페이지 크롤링"""
    resp = fetch_page(url, "clien", session=session, referer=referer)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    posts = []
    for item in soup.select("div.list_item"):
        title_el = item.select_one("a.list_subject")
        if not title_el:
            continue

        # 제목: 카테고리 span 제외한 텍스트
        title_spans = title_el.find_all("span")
        title = title_spans[-1].get_text(strip=True) if title_spans else title_el.get_text(strip=True)
        if not title:
            continue

        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://www.clien.net{href}"

        # 작성자
        author_el = item.select_one("span.nickname")
        author = author_el.get_text(strip=True) if author_el else ""

        # 날짜
        time_el = item.select_one("span.timestamp")
        date_text = time_el.get_text(strip=True) if time_el else ""

        posts.append({
            "title": title,
            "author": re.sub(r"\s+", " ", author).strip(),
            "post_date": parse_post_date(date_text),
            "source_url": href,
        })

    return posts


def crawl_fmkorea_page(url: str, session=None, referer: str | None = None) -> list[dict]:
    """에펨코리아 주식 게시판 한 페이지 크롤링"""
    resp = fetch_page(url, "fmkorea", session=session, referer=referer)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    # 디버그: 응답 상태 기록
    all_trs = soup.select("tbody tr")
    cate_trs = [r for r in all_trs if r.select_one("td.cate")]
    normal_trs = [r for r in cate_trs if "공지" not in r.select_one("td.cate").get_text()]
    log.info(f"  [FM디버그] status={resp.status_code} len={len(resp.text)} "
             f"tr={len(all_trs)} cate={len(cate_trs)} normal={len(normal_trs)}")

    posts = []
    for row in soup.select("tr"):
        # 카테고리 확인 (공지 제외)
        cate_el = row.select_one("td.cate")
        if not cate_el:
            continue
        cate_text = cate_el.get_text(strip=True)
        if "공지" in cate_text:
            continue

        # 제목: td.title 안의 글 링크 (a.hx 또는 /숫자 또는 document_srl=숫자)
        title_td = row.select_one("td[class*='title']")
        if not title_td:
            continue
        title_a = title_td.select_one("a.hx")
        if not title_a:
            for a in title_td.select("a"):
                href = a.get("href", "")
                if re.match(r"^/\d+$", href) or "document_srl=" in href:
                    title_a = a
                    break
        if not title_a:
            continue

        # 제목 (댓글 수 span 제거)
        for reply_span in title_a.select("span"):
            reply_span.decompose()
        title = title_a.get_text(strip=True)
        if not title:
            continue

        href = title_a.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://www.fmkorea.com{href}"

        # 작성자
        author_el = row.select_one("td.author") or row.select_one("a.member_plate")
        author = author_el.get_text(strip=True) if author_el else ""

        # 날짜
        time_el = row.select_one("td.time")
        date_text = time_el.get_text(strip=True) if time_el else ""

        posts.append({
            "title": title,
            "author": re.sub(r"\s+", " ", author).strip(),
            "post_date": parse_post_date(date_text),
            "source_url": href,
        })

    return posts


# 파서 매핑
PARSERS = {
    "mlbpark": crawl_mlbpark_page,
    "clien": crawl_clien_page,
    "fmkorea": crawl_fmkorea_page,
}


def _build_page_url(community: dict, page: int) -> str:
    """사이트별 페이지네이션 URL 생성"""
    parser = community.get("parser", "mlbpark")
    base = community["crawl_url"]

    if parser == "mlbpark":
        if page == 0:
            return base
        # MLBPark 검색은 1-indexed offset: p=31(2페이지), p=61(3페이지)...
        offset = page * community["posts_per_page"] + 1
        return f"{base}&p={offset}"
    elif parser == "clien":
        return f"{base}?&po={page}" if page > 0 else base
    elif parser == "fmkorea":
        return f"{base}{page + 1}"
    return base


def crawl_community(cur, community: dict) -> int:
    """커뮤니티 크롤링 + DB 저장. 기존 URL 기반 중복 감지로 자동 종료."""
    community_id = ensure_community(cur, community)
    total_inserted = 0
    consecutive_dup_pages = 0

    parser_name = community.get("parser", "mlbpark")
    parse_fn = PARSERS.get(parser_name)
    if not parse_fn:
        log.error(f"  알 수 없는 파서: {parser_name}")
        return 0

    # 최근 수집된 URL을 미리 로드하여 정확한 중복 판정
    cur.execute(SQL_KNOWN_URLS, (community_id, known_url_limit(community)))
    known_urls = {row[0] for row in cur.fetchall() if row[0]}

    session = requests.Session()
    referer = community.get("base_url")

    for page in range(community["max_pages"]):
        url = _build_page_url(community, page)

        try:
            posts = parse_fn(url, session=session, referer=referer)
        except Exception as e:
            log.warning(f"  페이지 {page+1} 크롤링 실패: {e}")
            continue

        if not posts:
            # 첫 페이지 빈 결과 → 봇 차단 가능성, 1회 재시도
            if page == 0:
                log.info(f"  페이지 1: 빈 결과, 3초 후 재시도...")
                time.sleep(3)
                try:
                    posts = parse_fn(url, session=session, referer=referer)
                except Exception:
                    pass
            if not posts:
                log.info(f"  페이지 {page+1}: 게시글 없음, 종료")
                break

        # 새 글만 필터링하여 INSERT
        new_posts = [p for p in posts if p.get("source_url") not in known_urls]
        inserted = 0
        for post in new_posts:
            cur.execute(
                SQL_INSERT_POST,
                (community_id, post["title"], post["author"],
                 post["post_date"], post["source_url"]),
            )
            if cur.rowcount > 0:
                inserted += 1
                known_urls.add(post["source_url"])

        total_inserted += inserted
        log.info(f"  페이지 {page+1}: +{inserted} 신규 / {len(posts)} 수집")

        # 페이지 전체가 이미 수집된 글이면 중복 페이지
        if inserted == 0:
            consecutive_dup_pages += 1
            if consecutive_dup_pages >= 2:
                log.info(f"  2연속 중복 페이지 → 크롤링 종료 (총 {page+1}페이지)")
                break
        else:
            consecutive_dup_pages = 0

        referer = url
        if parser_name == "fmkorea":
            time.sleep(random.uniform(3.0, 6.0))
        else:
            time.sleep(1)  # 크롤링 딜레이 (초)

    return total_inserted


# ═══════════════════════════════════════════════════════
# STEP 2: 종목 추출 + 감성 분석
# ═══════════════════════════════════════════════════════

_POSITIVE_WORDS, _NEGATIVE_WORDS = load_sentiment_words()

def analyze_sentiment(title: str) -> int:
    """제목 기반 감성 분석"""
    pos = sum(1 for w in _POSITIVE_WORDS if w in title)
    neg = sum(1 for w in _NEGATIVE_WORDS if w in title)
    if pos > neg:
        return 1
    elif neg > pos:
        return -1
    return 0


def build_ticker_map(cur) -> dict:
    """DB의 tickers 테이블 전체 + 수동 별칭으로 매칭 맵 구성
    모든 키는 upper()로 저장하여 대소문자 무시 매칭 (한글은 영향 없음)
    Returns: {keyword_upper: [(ticker_id, symbol), ...]} - 긴 키워드 우선
    """
    extra_aliases = load_aliases()
    multi_aliases = load_multi_aliases()
    skip_names = load_skip_names()

    ticker_map = {}  # keyword_upper → [(ticker_id, symbol), ...]

    # 1) DB에서 모든 종목 로드
    cur.execute(SQL_LOAD_TICKERS)
    all_tickers = cur.fetchall()
    symbol_to_id = {}  # symbol → ticker_id

    for ticker_id, symbol, name, market in all_tickers:
        symbol_to_id[symbol] = ticker_id

        # KRX 종목: name으로 매칭
        if market in ("KOSPI", "KOSDAQ"):
            if name and len(name) >= 2 and name.upper() not in skip_names:
                ticker_map[name.upper()] = [(ticker_id, symbol)]

        # US 종목: 3글자 이상 심볼만
        elif market in ("US", "NASDAQ", "NYSE"):
            if len(symbol) >= 3 and symbol not in skip_names:
                ticker_map[symbol.upper()] = [(ticker_id, symbol)]

    # 2) 수동 한글 별칭 추가 (1:1)
    for alias, symbol in extra_aliases.items():
        if symbol in symbol_to_id and alias.upper() not in skip_names:
            ticker_map[alias.upper()] = [(symbol_to_id[symbol], symbol)]

    # 3) 복수 종목 별칭 추가 (1:N)
    for alias, symbols in multi_aliases.items():
        pairs = [(symbol_to_id[s], s) for s in symbols if s in symbol_to_id]
        if pairs:
            ticker_map[alias.upper()] = pairs

    log.info(f"  종목 매칭 맵: {len(ticker_map)}개 키워드 로드")
    return ticker_map


def extract_tickers_for_new_posts(cur) -> int:
    """미분석 게시글에서 종목 추출 + 감성 분석"""
    ticker_map = build_ticker_map(cur)
    if not ticker_map:
        log.warning("  종목 매핑이 비어있습니다")
        return 0

    # 길이 역순 정렬 (긴 매칭 우선 → "삼성전자" > "삼성")
    sorted_keywords = sorted(ticker_map.keys(), key=len, reverse=True)

    # 아직 분석하지 않은 게시글 조회
    cur.execute(SQL_UNANALYZED_POSTS, (ANALYZE_BATCH_SIZE,))
    unanalyzed = cur.fetchall()

    if not unanalyzed:
        log.info("  분석할 새 게시글 없음")
        return 0

    total_mentions = 0
    for post_id, title in unanalyzed:
        found_tickers = set()
        remaining = title.upper()  # 대소문자 무시 매칭

        for keyword in sorted_keywords:
            if keyword in remaining:
                for ticker_id, symbol in ticker_map[keyword]:
                    if ticker_id not in found_tickers:
                        found_tickers.add(ticker_id)
                        sentiment = analyze_sentiment(title)
                        try:
                            cur.execute(
                                SQL_INSERT_MENTION,
                                (post_id, ticker_id, sentiment),
                            )
                            if cur.rowcount > 0:
                                total_mentions += 1
                        except Exception:
                            pass
                remaining = remaining.replace(keyword, "", 1)

    return total_mentions


# ═══════════════════════════════════════════════════════
# STEP 3: 일별 통계 갱신
# ═══════════════════════════════════════════════════════

def update_daily_stats(cur, target_date: date = None) -> int:
    """특정 날짜의 mention_daily_stats를 갱신"""
    if target_date is None:
        target_date = date.today()

    # 해당 날짜 기존 통계 삭제
    cur.execute(SQL_DELETE_DAILY_STATS, (target_date,))

    # 커뮤니티별 통계
    cur.execute(SQL_INSERT_COMMUNITY_STATS, (target_date,))
    community_stats = cur.rowcount

    # 전체 합산 통계 (community_id = NULL)
    cur.execute(SQL_INSERT_TOTAL_STATS, (target_date,))

    return community_stats + cur.rowcount


# ═══════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════

def run_pipeline(community_filter=None, run_crawl=True, run_analyze=True, run_stats=True):
    """파이프라인 실행.

    community_filter: 파서명(mlbpark/clien/fmkorea)으로 크롤링 대상 필터링.
    run_crawl/run_analyze/run_stats로 수집, 분석, 통계 단계를 분리 실행할 수 있다.
    """
    start_time = datetime.now()
    log.info("=" * 60)
    log.info(f"Human Index Daily Worker 시작 - {start_time.isoformat()}")
    if community_filter:
        log.info(f"  필터: {community_filter}")
    log.info(
        f"  단계: crawl={run_crawl}, analyze={run_analyze}, stats={run_stats}"
    )
    log.info("=" * 60)

    targets = COMMUNITIES
    if run_crawl and community_filter:
        targets = [c for c in COMMUNITIES if c["parser"] == community_filter]
        if not targets:
            log.error(f"  알 수 없는 커뮤니티: {community_filter}")
            return

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        total_new = 0
        mentions = 0

        # STEP 1: 크롤링
        if run_crawl:
            log.info("\n📡 STEP 1: 크롤링")
            for community in targets:
                log.info(f"  [{community['name']}] 크롤링 시작...")
                with conn:
                    with conn.cursor() as cur:
                        new_posts = crawl_community(cur, community)
                        total_new += new_posts
                        log.info(f"  [{community['name']}] 완료: {new_posts}건 신규")
        else:
            log.info("\n📡 STEP 1: 크롤링 건너뜀")

        # STEP 2: 종목 추출
        if run_analyze:
            log.info("\n🔍 STEP 2: 종목 추출 + 감성 분석")
            with conn:
                with conn.cursor() as cur:
                    mentions = extract_tickers_for_new_posts(cur)
                    log.info(f"  {mentions}건 종목 언급 추출")
        else:
            log.info("\n🔍 STEP 2: 종목 추출 + 감성 분석 건너뜀")

        # STEP 3: 통계 갱신 (오늘 + 어제)
        if run_stats:
            log.info("\n📊 STEP 3: 일별 통계 갱신")
            with conn:
                with conn.cursor() as cur:
                    today = date.today()
                    yesterday = today - timedelta(days=1)

                    stats_today = update_daily_stats(cur, today)
                    stats_yesterday = update_daily_stats(cur, yesterday)
                    log.info(f"  오늘({today}): {stats_today}건")
                    log.info(f"  어제({yesterday}): {stats_yesterday}건")
        else:
            log.info("\n📊 STEP 3: 일별 통계 갱신 건너뜀")

        # 결과 요약
        elapsed = (datetime.now() - start_time).total_seconds()
        with conn.cursor() as cur:
            cur.execute(SQL_COUNT_POSTS)
            total_posts = cur.fetchone()[0]
            cur.execute(SQL_COUNT_MENTIONS)
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
    import argparse
    parser = argparse.ArgumentParser(description="Human Index 크롤링 파이프라인")
    parser.add_argument(
        "--community",
        choices=["mlbpark", "clien", "fmkorea"],
        help="특정 커뮤니티만 크롤링 (미지정 시 전체)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--crawl-only", action="store_true", help="크롤링만 실행")
    mode.add_argument("--analyze-only", action="store_true", help="미분석 게시글 종목 추출만 실행")
    mode.add_argument("--stats-only", action="store_true", help="오늘/어제 일별 통계 갱신만 실행")
    mode.add_argument("--postprocess-only", action="store_true", help="종목 추출과 통계 갱신만 실행")
    args = parser.parse_args()

    if args.crawl_only:
        run_pipeline(community_filter=args.community, run_crawl=True, run_analyze=False, run_stats=False)
    elif args.analyze_only:
        run_pipeline(community_filter=None, run_crawl=False, run_analyze=True, run_stats=False)
    elif args.stats_only:
        run_pipeline(community_filter=None, run_crawl=False, run_analyze=False, run_stats=True)
    elif args.postprocess_only:
        run_pipeline(community_filter=None, run_crawl=False, run_analyze=True, run_stats=True)
    else:
        run_pipeline(community_filter=args.community)
