"""
크롤러 설정 - 커뮤니티 정의, 종목 별칭, 감성 키워드 등
daily_worker.py에서 import하여 사용
"""

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
    "스퀘어": "402340",  # SK스퀘어
    # KRX 영문명/혼합명 종목의 한글 별칭 (DB에 한글명 없는 것만)
    "네이버": "035420",                        # DB: NAVER
    "포스코": "005490", "포스코홀딩스": "005490", # DB: POSCO홀딩스
    "LS일렉트릭": "010120",                     # DB: 엘에스일렉트릭
    "KT&G": "033780",                          # DB: 케이티앤지
    "HD한국조선해양": "009540",                  # DB: 한국조선해양
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


# ─── 오매칭 방지 ────────────────────────────────────────
# 너무 일반적이거나 짧은 단어는 종목 매칭에서 제외
SKIP_NAMES = {
    "한국", "대한", "제일", "동양", "삼성", "대우", "현대", "한화",
    "서울", "부산", "동아", "세계", "우리", "신한", "아시아",
    "IT", "AI", "OK", "SK", "LG", "LS", "GS", "KT",
    # US에서 너무 짧은 심볼
    "A", "B", "C", "D", "E", "F", "G", "K", "L", "M",
    "O", "R", "T", "U", "V", "W", "X", "Y", "Z",
}


# ─── 감성 분석 키워드 ───────────────────────────────────
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
