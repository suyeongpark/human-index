"""
크롤러 설정 - 커뮤니티 정의, HTTP 헤더 등 정적 설정
CSV 기반 데이터(별칭, 감성 키워드 등)는 data_loader.py에서 로드
"""

import os
import random

# ─── HTTP 요청 설정 ─────────────────────────────────────
USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    "Connection": "keep-alive",
}

HEADERS = {
    **BASE_HEADERS,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def build_headers(parser: str | None = None, referer: str | None = None) -> dict:
    """요청별 HTTP 헤더 생성. FM코리아는 선택적으로 쿠키/UA 환경변수를 반영한다."""
    user_agent = os.environ.get("FMKOREA_USER_AGENT") if parser == "fmkorea" else None
    headers = {
        **BASE_HEADERS,
        "User-Agent": user_agent or random.choice(USER_AGENTS),
    }
    if referer:
        headers["Referer"] = referer

    if parser == "fmkorea":
        headers.update({
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Upgrade-Insecure-Requests": "1",
        })
        cookie = os.environ.get("FMKOREA_COOKIE")
        if cookie:
            headers["Cookie"] = cookie

    return headers


# ─── 커뮤니티 소스 설정 ─────────────────────────────────
COMMUNITIES = [
    {
        "name": "MLB Park 불펜",
        "base_url": "https://mlbpark.donga.com/mp/b.php?b=bullpen",
        "category": "주식",
        "crawl_url": "https://mlbpark.donga.com/mp/b.php?select=sct&m=search&b=bullpen&select=spf&query=%EC%A3%BC%EC%8B%9D&p=",
        "posts_per_page": 30,
        "max_pages": 1,
        "parser": "mlbpark",
    },
    {
        "name": "클리앙 투자",
        "base_url": "https://www.clien.net/service/board/cm_stock",
        "category": "주식",
        "crawl_url": "https://www.clien.net/service/board/cm_stock?po=",
        "posts_per_page": 30,
        "max_pages": 100,
        "parser": "clien",
    },
    {
        "name": "에펨코리아 국내주식",
        "base_url": "https://www.fmkorea.com/stock",
        "category": "주식",
        "crawl_url": "https://www.fmkorea.com/index.php?mid=stock&category=2997203870&page=",
        "posts_per_page": 20,
        "max_pages": 1,
        "parser": "fmkorea",
    },
    {
        "name": "에펨코리아 해외주식",
        "base_url": "https://www.fmkorea.com/stock",
        "category": "주식",
        "crawl_url": "https://www.fmkorea.com/index.php?mid=stock&category=2997204381&page=",
        "posts_per_page": 20,
        "max_pages": 1,
        "parser": "fmkorea",
    },
]

# ─── CSV 데이터 경로 ────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
