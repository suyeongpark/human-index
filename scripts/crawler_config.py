"""
크롤러 설정 - 커뮤니티 정의, HTTP 헤더 등 정적 설정
CSV 기반 데이터(별칭, 감성 키워드 등)는 data_loader.py에서 로드
"""

import os

# ─── HTTP 요청 설정 ─────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─── 커뮤니티 소스 설정 ─────────────────────────────────
COMMUNITIES = [
    {
        "name": "MLB Park 불펜",
        "base_url": "https://mlbpark.donga.com/mp/b.php?b=bullpen",
        "category": "주식",
        "crawl_url": "https://mlbpark.donga.com/mp/b.php?select=sct&m=search&b=bullpen&select=spf&query=%EC%A3%BC%EC%8B%9D&p=",
        "posts_per_page": 30,
        "max_pages": 100,
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
        "max_pages": 50,
        "parser": "fmkorea",
    },
    {
        "name": "에펨코리아 해외주식",
        "base_url": "https://www.fmkorea.com/stock",
        "category": "주식",
        "crawl_url": "https://www.fmkorea.com/index.php?mid=stock&category=2997204381&page=",
        "posts_per_page": 20,
        "max_pages": 50,
        "parser": "fmkorea",
    },
]

# ─── CSV 데이터 경로 ────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
