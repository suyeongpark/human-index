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
from db_config import DB_CONFIG

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
            "?search_select=sct&search_input=&select=spf"
            "&m=search&b=bullpen&query=%EC%A3%BC%EC%8B%9D"
        ),
        "posts_per_page": 30,
        "max_pages": 50,
        "parser": "mlbpark",
    },
    {
        "name": "클리앙 투자",
        "base_url": "https://www.clien.net/service/board/cm_stock",
        "category": "주식",
        "crawl_url": "https://www.clien.net/service/board/cm_stock",
        "posts_per_page": 30,
        "max_pages": 50,
        "parser": "clien",
    },
    {
        "name": "에펨코리아 국내주식",
        "base_url": "https://www.fmkorea.com/stock",
        "category": "주식",
        "crawl_url": "https://www.fmkorea.com/index.php?mid=stock&category=2997203870",
        "posts_per_page": 20,
        "max_pages": 50,
        "parser": "fmkorea",
    },
    {
        "name": "에펨코리아 해외주식",
        "base_url": "https://www.fmkorea.com/stock",
        "category": "주식",
        "crawl_url": "https://www.fmkorea.com/index.php?mid=stock&category=2997204381",
        "posts_per_page": 20,
        "max_pages": 50,
        "parser": "fmkorea",
    },
]

# ─── 수동 한글 별칭 (DB name과 다른 약칭들) ──────────
# DB의 종목명은 공식 명칭이라 커뮤니티 약칭과 다른 경우가 있음
EXTRA_ALIASES = {
    # KRX 약칭 / 커뮤니티 약칭
    "삼전": "005930", "삼전우": "005935",
    "하닉": "000660", "하이닉스": "000660", "닉스": "000660",
    "LG엔솔": "373220",
    "한화에어": "012450",
    "에코프로": "247540",
    "현대차": "005380",
    "기아차": "000270",
    "두에빌": "034020", "두산에너빌리티": "034020",
    # KRX 영문명 종목의 한글 별칭
    "네이버": "035420",
    "카카오": "035720", "카카오뱅크": "323410", "카뱅": "323410",
    "카카오페이": "377300",
    "포스코": "005490", "포스코홀딩스": "005490",
    "포스코퓨처엠": "003670",
    "셀트리온": "068270",
    "크래프톤": "259960",
    "HD현대": "267250", "HD현대중공업": "329180",
    "HD한국조선해양": "009540",
    "HLB": "028300",
    "LS일렉트릭": "010120",
    "CJ제일제당": "097950", "CJ": "001040",
    "BGF리테일": "282330",
    "OCI홀딩스": "010060",
    "DL이앤씨": "375500",
    "KT&G": "033780",
    # 미국 한글 별칭
    "애플": "AAPL", "구글": "GOOGL", "아마존": "AMZN",
    "엔비디아": "NVDA", "테슬라": "TSLA",
    "메타": "META", "페이스북": "META",
    "넷플릭스": "NFLX", "마이크론": "MU",
    "인텔": "INTC", "마소": "MSFT", "마이크로소프트": "MSFT",
    "브로드컴": "AVGO", "퀄컴": "QCOM",
    "샌디스크": "SNDK", "웨스턴디지털": "WDC", "시게이트": "STX",
    "팔란티어": "PLTR", "소파이": "SOFI",
    "코인베이스": "COIN", "화이자": "PFE", "모더나": "MRNA",
    "록히드마틴": "LMT", "록히드": "LMT",
    "보잉": "BA", "코스트코": "COST", "디즈니": "DIS",
    "노보노디스크": "NVO", "노보": "NVO",
    "일라이릴리": "LLY", "릴리": "LLY",
    "골드만삭스": "GS", "JP모건": "JPM",
    "월마트": "WMT", "나이키": "NKE",
    "엑슨모빌": "XOM", "셰브론": "CVX",
    "알파벳": "GOOGL", "버크셔": "BRK.B",
    "우버": "UBER", "오라클": "ORCL", "어도비": "ADBE",
    "니오": "NIO", "리비안": "RIVN", "리오토": "LI",
    "온세미": "ON", "마벨": "MRVL", "램리서치": "LRCX",
    "노스롭": "NOC", "레이시온": "RTX",
}

# 하나의 키워드 → 여러 종목 매핑 (커뮤니티 합성어)
MULTI_ALIASES = {
    "삼닉": ["005930", "000660"],  # 삼성전자 + SK하이닉스
    "삼하": ["005930", "000660"],  # 삼성전자 + SK하이닉스
}

# 오매칭 방지: 너무 일반적이거나 짧은 단어는 제외
SKIP_NAMES = {
    "한국", "대한", "제일", "동양", "삼성", "대우", "현대", "한화",
    "서울", "부산", "동아", "세계", "우리", "신한", "아시아",
    "IT", "AI", "OK", "SK", "LG", "LS", "GS", "KT",
    # US에서 너무 짧은 심볼
    "A", "B", "C", "D", "E", "F", "G", "K", "L", "M",
    "O", "R", "T", "U", "V", "W", "X", "Y", "Z",
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


def parse_post_date(date_text: str) -> datetime:
    """게시글 날짜/시간 파싱 (여러 커뮤니티 형식 대응) → datetime 반환"""
    date_text = date_text.strip()
    if not date_text:
        return datetime.now()

    # "14:30" 같은 시간만 → 오늘 + 해당 시간
    if ":" in date_text and "-" not in date_text and "." not in date_text:
        try:
            t = datetime.strptime(date_text, "%H:%M")
            return datetime.combine(date.today(), t.time())
        except ValueError:
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


def crawl_clien_page(url: str) -> list[dict]:
    """클리앙 투자게시판 한 페이지 크롤링"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
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


def crawl_fmkorea_page(url: str) -> list[dict]:
    """에펨코리아 주식 게시판 한 페이지 크롤링"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    posts = []
    for row in soup.select("tr"):
        # 제목 링크 (에펨코리아 Sketchbook5 스킨: a.hx)
        title_a = row.select_one("a.hx")
        if not title_a:
            continue

        # 공지 제외: 첫 번째 링크 텍스트에 '공지' 포함 시 스킵
        first_a = row.select_one("a")
        if first_a and "공지" in first_a.get_text():
            continue

        # 제목 (댓글 수 제외)
        for reply_span in title_a.select("span.replyNum"):
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
        return f"{base}&page={page + 1}" if page > 0 else base
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
    cur.execute(
        "SELECT source_url FROM posts WHERE community_id = %s ORDER BY id DESC LIMIT 1000",
        (community_id,),
    )
    known_urls = {row[0] for row in cur.fetchall() if row[0]}

    for page in range(community["max_pages"]):
        url = _build_page_url(community, page)

        try:
            posts = parse_fn(url)
        except Exception as e:
            log.warning(f"  페이지 {page+1} 크롤링 실패: {e}")
            continue

        if not posts:
            log.info(f"  페이지 {page+1}: 게시글 없음, 종료")
            break

        # 새 글만 필터링하여 INSERT
        new_posts = [p for p in posts if p.get("source_url") not in known_urls]
        inserted = 0
        for post in new_posts:
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
    """DB의 tickers 테이블 전체 + 수동 별칭으로 매칭 맵 구성
    Returns: {keyword: [(ticker_id, symbol), ...]} - 긴 키워드 우선
    """
    ticker_map = {}  # keyword → [(ticker_id, symbol), ...]

    # 1) DB에서 모든 종목 로드
    cur.execute("SELECT id, symbol, name, market FROM tickers WHERE is_active = TRUE")
    all_tickers = cur.fetchall()
    symbol_to_id = {}  # symbol → ticker_id

    for ticker_id, symbol, name, market in all_tickers:
        symbol_to_id[symbol] = ticker_id

        # KRX 종목: name으로 매칭 (예: "미래에셋증권", "삼성전자")
        if market in ("KOSPI", "KOSDAQ"):
            if name and len(name) >= 2 and name not in SKIP_NAMES:
                ticker_map[name] = [(ticker_id, symbol)]

        # US 종목: 3글자 이상 심볼만 (1~2글자는 오매칭 위험)
        elif market in ("US", "NASDAQ", "NYSE"):
            if len(symbol) >= 3 and symbol not in SKIP_NAMES:
                ticker_map[symbol] = [(ticker_id, symbol)]

    # 2) 수동 한글 별칭 추가 (1:1)
    for alias, symbol in EXTRA_ALIASES.items():
        if symbol in symbol_to_id and alias not in SKIP_NAMES:
            ticker_map[alias] = [(symbol_to_id[symbol], symbol)]

    # 3) 복수 종목 별칭 추가 (1:N)
    for alias, symbols in MULTI_ALIASES.items():
        pairs = [(symbol_to_id[s], s) for s in symbols if s in symbol_to_id]
        if pairs:
            ticker_map[alias] = pairs

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

        for keyword in sorted_keywords:
            if keyword in remaining:
                for ticker_id, symbol in ticker_map[keyword]:
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
    cur.execute("DELETE FROM mention_daily_stats WHERE stat_date = %s", (target_date,))

    # 커뮤니티별 통계
    cur.execute("""
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
    """, (target_date,))
    community_stats = cur.rowcount

    # 전체 합산 통계 (community_id = NULL)
    cur.execute("""
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
    """, (target_date,))

    return community_stats + cur.rowcount


# ═══════════════════════════════════════════════════════
# 메인 파이프라인
# ═══════════════════════════════════════════════════════

def run_pipeline(community_filter=None):
    """일일 파이프라인 실행. community_filter: 파서명(mlbpark/clien/fmkorea)으로 필터링"""
    start_time = datetime.now()
    log.info("=" * 60)
    log.info(f"Human Index Daily Worker 시작 - {start_time.isoformat()}")
    if community_filter:
        log.info(f"  필터: {community_filter}")
    log.info("=" * 60)

    targets = COMMUNITIES
    if community_filter:
        targets = [c for c in COMMUNITIES if c["parser"] == community_filter]
        if not targets:
            log.error(f"  알 수 없는 커뮤니티: {community_filter}")
            return

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        # STEP 1: 크롤링
        log.info("\n📡 STEP 1: 크롤링")
        total_new = 0
        for community in targets:
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
    import argparse
    parser = argparse.ArgumentParser(description="Human Index 크롤링 파이프라인")
    parser.add_argument(
        "--community",
        choices=["mlbpark", "clien", "fmkorea"],
        help="특정 커뮤니티만 크롤링 (미지정 시 전체)",
    )
    args = parser.parse_args()
    run_pipeline(community_filter=args.community)

