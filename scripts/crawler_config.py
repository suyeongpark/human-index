"""
크롤러 설정 - 커뮤니티 정의, 종목 별칭, 감성 키워드 등
daily_worker.py에서 import하여 사용
"""

import csv
import os

# ─── HTTP 요청 설정 ─────────────────────────────────────
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
# ─── 별칭 데이터 로드 (CSV) ──────────────────────────────
_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def _load_aliases() -> dict:
    """aliases.csv → {alias: symbol}"""
    path = os.path.join(_DATA_DIR, "aliases.csv")
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["alias"].strip()] = row["symbol"].strip()
    return result

def _load_multi_aliases() -> dict:
    """multi_aliases.csv → {alias: [symbol, ...]}"""
    path = os.path.join(_DATA_DIR, "multi_aliases.csv")
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            alias = row["alias"].strip()
            symbols = [s.strip() for s in row["symbols"].split(",")]
            result[alias] = symbols
    return result

EXTRA_ALIASES = _load_aliases()
MULTI_ALIASES = _load_multi_aliases()


# ─── 오매칭 방지 (CSV) ──────────────────────────────────
def _load_skip_names() -> set:
    """skip_names.csv → set"""
    path = os.path.join(_DATA_DIR, "skip_names.csv")
    result = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result.add(row["name"].strip())
    return result

SKIP_NAMES = _load_skip_names()


# ─── 감성 분석 키워드 (CSV) ──────────────────────────────
def _load_sentiment_words() -> tuple[list, list]:
    """sentiment_words.csv → (positive_list, negative_list)"""
    path = os.path.join(_DATA_DIR, "sentiment_words.csv")
    positive, negative = [], []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = row["word"].strip()
            if row["sentiment"].strip() == "positive":
                positive.append(word)
            elif row["sentiment"].strip() == "negative":
                negative.append(word)
    return positive, negative

POSITIVE_WORDS, NEGATIVE_WORDS = _load_sentiment_words()
