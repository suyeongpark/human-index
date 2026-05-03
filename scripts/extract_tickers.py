"""
종목 추출 & 감성 분석 스크립트 (시나리오 2)
- posts 테이블의 제목에서 종목명을 매칭
- 간단한 키워드 기반 감성 분석 (1: 긍정, -1: 부정, 0: 중립)
- 결과를 post_mentions, mention_daily_stats 테이블에 저장
"""

import psycopg2
import re
import sys
from datetime import date

DB_CONFIG = {
    "dbname": "human_index",
    "host": "localhost",
    "port": 5432,
}

# ─── 종목 사전 ──────────────────────────────────────────
# (symbol, name, market, aliases)
# aliases: 제목에서 매칭할 키워드 목록 (정규식 패턴)
TICKER_DEFS = [
    # === 한국 대형주 ===
    ("005930", "삼성전자", "KRX", ["삼성전자", "삼전"]),
    ("000660", "SK하이닉스", "KRX", ["SK하이닉스", "하이닉스", "하닉"]),
    ("373220", "LG에너지솔루션", "KRX", ["LG에너지", "LG엔솔"]),
    ("005935", "삼성전자우", "KRX", ["삼성전자우", "삼전우"]),
    ("006400", "삼성SDI", "KRX", ["삼성SDI", "삼성sdi"]),
    ("051910", "LG화학", "KRX", ["LG화학"]),
    ("005490", "POSCO홀딩스", "KRX", ["포스코", "POSCO"]),
    ("035420", "NAVER", "KRX", ["네이버", "NAVER"]),
    ("035720", "카카오", "KRX", ["카카오"]),
    ("000270", "기아", "KRX", ["기아차", "기아"]),
    ("005380", "현대차", "KRX", ["현대차", "현대자동차"]),
    ("068270", "셀트리온", "KRX", ["셀트리온"]),
    ("012330", "현대모비스", "KRX", ["현대모비스"]),
    ("028260", "삼성물산", "KRX", ["삼성물산"]),
    ("009150", "삼성전기", "KRX", ["삼성전기"]),
    ("066570", "LG전자", "KRX", ["LG전자"]),
    ("003550", "LG", "KRX", ["LG는", "LG가", "LG의"]),
    ("034730", "SK", "KRX", ["SK는", "SK가"]),
    ("010130", "고려아연", "KRX", ["고려아연"]),
    ("003670", "포스코퓨처엠", "KRX", ["포스코퓨처엠"]),
    ("032830", "삼성생명", "KRX", ["삼성생명"]),
    ("105560", "KB금융", "KRX", ["KB금융"]),
    ("055550", "신한지주", "KRX", ["신한지주", "신한금융"]),
    ("086790", "하나금융지주", "KRX", ["하나금융"]),
    ("316140", "우리금융지주", "KRX", ["우리금융"]),
    ("009540", "한국조선해양", "KRX", ["한국조선해양"]),
    ("042700", "한미반도체", "KRX", ["한미반도체"]),
    ("012450", "한화에어로스페이스", "KRX", ["한화에어로", "한화에어"]),
    ("272210", "한화시스템", "KRX", ["한화시스템"]),
    ("000880", "한화", "KRX", ["한화"]),
    ("047050", "포스코인터내셔널", "KRX", ["포스코인터"]),
    ("018260", "삼성에스디에스", "KRX", ["삼성SDS"]),
    ("011200", "HMM", "KRX", ["HMM"]),
    ("352820", "하이브", "KRX", ["하이브"]),
    ("259960", "크래프톤", "KRX", ["크래프톤"]),
    ("247540", "에코프로비엠", "KRX", ["에코프로비엠", "에코프로"]),

    # === 미국 대형주 ===
    ("AAPL", "Apple", "NASDAQ", ["애플", "Apple", "AAPL"]),
    ("MSFT", "Microsoft", "NASDAQ", ["마이크로소프트", "마소", "Microsoft", "MSFT"]),
    ("GOOGL", "Alphabet", "NASDAQ", ["알파벳", "구글", "Google", "GOOGL"]),
    ("AMZN", "Amazon", "NASDAQ", ["아마존", "Amazon", "AMZN"]),
    ("NVDA", "NVIDIA", "NASDAQ", ["엔비디아", "NVIDIA", "NVDA"]),
    ("TSLA", "Tesla", "NASDAQ", ["테슬라", "Tesla", "TSLA"]),
    ("META", "Meta", "NASDAQ", ["메타", "페이스북", "META"]),
    ("NFLX", "Netflix", "NASDAQ", ["넷플릭스", "Netflix", "NFLX"]),
    ("MU", "Micron", "NASDAQ", ["마이크론", "Micron"]),
    ("INTC", "Intel", "NASDAQ", ["인텔", "Intel", "INTC"]),
    ("AMD", "AMD", "NASDAQ", ["AMD"]),
    ("TSM", "TSMC", "NYSE", ["TSMC"]),
    ("AVGO", "Broadcom", "NASDAQ", ["브로드컴", "Broadcom", "AVGO"]),
    ("ARM", "ARM Holdings", "NASDAQ", ["ARM"]),
    ("PLTR", "Palantir", "NYSE", ["팔란티어", "Palantir", "PLTR"]),
    ("ASML", "ASML", "NASDAQ", ["ASML"]),
    ("WDC", "Western Digital", "NASDAQ", ["샌디스크", "웨스턴디지털", "WDC"]),
    ("SOFI", "SoFi", "NASDAQ", ["소파이", "SoFi", "SOFI"]),
    ("COIN", "Coinbase", "NASDAQ", ["코인베이스", "Coinbase"]),

    # === ETF ===
    ("QQQ", "QQQ", "NASDAQ", ["QQQ"]),
    ("SPY", "SPY", "NYSE", ["SPY"]),
    ("TQQQ", "TQQQ", "NASDAQ", ["TQQQ"]),
    ("SOXL", "SOXL", "NYSE", ["SOXL"]),
    ("SCHD", "SCHD", "NYSE", ["SCHD"]),

    # === 섹터/테마 키워드 (가상 심볼) ===
    ("SECTOR_DEFENSE", "방산주", "THEME", ["방산"]),
    ("SECTOR_SHIPBUILD", "조선주", "THEME", ["조선"]),
    ("SECTOR_BIO", "바이오", "THEME", ["바이오"]),
    ("SECTOR_BANK", "은행주", "THEME", ["은행"]),
    ("SECTOR_SEMI", "반도체", "THEME", ["반도체"]),
    ("CRYPTO_BTC", "비트코인", "CRYPTO", ["비트코인", "비코"]),
]

# ─── 감성 분석 키워드 ──────────────────────────────────
POSITIVE_WORDS = [
    "상승", "급등", "폭등", "상한가", "최고", "신고가", "돌파", "오르",
    "올라", "올랐", "매수", "사야", "좋은", "호재", "기대", "수익",
    "흥해", "대박", "축하", "벌었", "성공", "반등", "회복", "날아",
    "갓", "ㄱㅇㅇ", "간다", "갑니다", "가즈아", "가자", "목표",
]

NEGATIVE_WORDS = [
    "하락", "급락", "폭락", "폭망", "하한가", "최저", "추락", "내려",
    "떨어", "빠지", "매도", "팔아", "위험", "악재", "하방", "손절",
    "망했", "물렸", "물타", "빠졌", "쫄리", "ㅈ망", "폭삭", "개잡",
    "파업", "소송", "리스크", "규제", "제재", "우려", "걱정",
]


def analyze_sentiment(title: str) -> int:
    """제목 기반 간단 감성 분석. 1: 긍정, -1: 부정, 0: 중립"""
    pos = sum(1 for w in POSITIVE_WORDS if w in title)
    neg = sum(1 for w in NEGATIVE_WORDS if w in title)
    if pos > neg:
        return 1
    elif neg > pos:
        return -1
    return 0


def main():
    print("=" * 60)
    print("종목 추출 & 감성 분석 (시나리오 2)")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        # 1. 종목 시딩
        print("\n📌 1단계: 종목 마스터 시딩...")
        ticker_map = {}  # name → id
        with conn:
            with conn.cursor() as cur:
                for symbol, name, market, aliases in TICKER_DEFS:
                    cur.execute(
                        """
                        INSERT INTO tickers (symbol, name, market)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name
                        RETURNING id
                        """,
                        (symbol, name, market),
                    )
                    ticker_id = cur.fetchone()[0]
                    for alias in aliases:
                        ticker_map[alias] = (ticker_id, symbol, name)

        print(f"  ✅ {len(TICKER_DEFS)}개 종목 등록, {len(ticker_map)}개 별칭 매핑")

        # 별칭을 길이 역순 정렬 (긴 매칭 우선: "삼성전자" > "삼성")
        sorted_aliases = sorted(ticker_map.keys(), key=len, reverse=True)

        # 2. 게시글 제목에서 종목 추출
        print("\n📌 2단계: 게시글 제목에서 종목 추출...")
        with conn.cursor() as cur:
            cur.execute("SELECT id, title FROM posts ORDER BY id")
            posts = cur.fetchall()

        print(f"  분석 대상: {len(posts)}건")

        mentions = []  # (post_id, ticker_id, sentiment)
        matched_posts = 0

        for i, (post_id, title) in enumerate(posts):
            found_tickers = set()
            remaining = title

            for alias in sorted_aliases:
                if alias in remaining:
                    ticker_id, symbol, name = ticker_map[alias]
                    if ticker_id not in found_tickers:
                        found_tickers.add(ticker_id)
                        sentiment = analyze_sentiment(title)
                        mentions.append((post_id, ticker_id, sentiment))
                    # 중복 매칭 방지: 이미 매칭된 키워드 제거
                    remaining = remaining.replace(alias, "", 1)

            if found_tickers:
                matched_posts += 1

            if (i + 1) % 5000 == 0:
                sys.stdout.write(f"\r  진행: {i+1}/{len(posts)} ({i*100//len(posts)}%)")
                sys.stdout.flush()

        print(f"\r  ✅ 분석 완료: {len(posts)}건 중 {matched_posts}건 종목 매칭 ({matched_posts*100//len(posts)}%)")
        print(f"  📊 총 언급 건수: {len(mentions)}건")

        # 3. post_mentions 저장
        print("\n📌 3단계: post_mentions 저장...")
        inserted = 0
        with conn:
            with conn.cursor() as cur:
                # 기존 데이터 삭제
                cur.execute("DELETE FROM post_mentions")
                for post_id, ticker_id, sentiment in mentions:
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
                            inserted += 1
                    except Exception as e:
                        pass

        print(f"  ✅ {inserted}건 저장 완료")

        # 4. mention_daily_stats 집계
        print("\n📌 4단계: 일별 통계 집계...")
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM mention_daily_stats")
                cur.execute("""
                    INSERT INTO mention_daily_stats
                        (ticker_id, community_id, stat_date, mention_count,
                         positive_count, negative_count, neutral_count)
                    SELECT
                        pm.ticker_id,
                        p.community_id,
                        p.post_date,
                        COUNT(*),
                        COUNT(*) FILTER (WHERE pm.sentiment = 1),
                        COUNT(*) FILTER (WHERE pm.sentiment = -1),
                        COUNT(*) FILTER (WHERE pm.sentiment = 0)
                    FROM post_mentions pm
                    JOIN posts p ON p.id = pm.post_id
                    GROUP BY pm.ticker_id, p.community_id, p.post_date
                """)
                stats_count = cur.rowcount
                print(f"  ✅ {stats_count}건 통계 집계 완료")

                # 전체 합산 통계도 생성
                cur.execute("""
                    INSERT INTO mention_daily_stats
                        (ticker_id, community_id, stat_date, mention_count,
                         positive_count, negative_count, neutral_count)
                    SELECT
                        pm.ticker_id,
                        NULL,
                        p.post_date,
                        COUNT(*),
                        COUNT(*) FILTER (WHERE pm.sentiment = 1),
                        COUNT(*) FILTER (WHERE pm.sentiment = -1),
                        COUNT(*) FILTER (WHERE pm.sentiment = 0)
                    FROM post_mentions pm
                    JOIN posts p ON p.id = pm.post_id
                    GROUP BY pm.ticker_id, p.post_date
                """)

        # 5. 결과 출력
        print("\n" + "=" * 60)
        print("📊 종목별 총 언급 수 (상위 20)")
        print("=" * 60)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.symbol, t.name, 
                       COUNT(*) as total,
                       COUNT(*) FILTER (WHERE pm.sentiment = 1) as pos,
                       COUNT(*) FILTER (WHERE pm.sentiment = -1) as neg,
                       COUNT(*) FILTER (WHERE pm.sentiment = 0) as neu
                FROM post_mentions pm
                JOIN tickers t ON t.id = pm.ticker_id
                GROUP BY t.symbol, t.name
                ORDER BY total DESC
                LIMIT 20
            """)
            rows = cur.fetchall()
            print(f"{'심볼':<10} {'종목명':<15} {'총계':>5} {'긍정':>5} {'부정':>5} {'중립':>5}")
            print("-" * 55)
            for row in rows:
                print(f"{row[0]:<10} {row[1]:<15} {row[2]:>5} {row[3]:>5} {row[4]:>5} {row[5]:>5}")

        print("\n📊 마이크론 일별 언급 추이")
        print("-" * 40)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT stat_date, mention_count, positive_count, negative_count, neutral_count
                FROM mention_daily_stats
                WHERE ticker_id = (SELECT id FROM tickers WHERE symbol = 'MU')
                  AND community_id IS NULL
                ORDER BY stat_date
            """)
            rows = cur.fetchall()
            for row in rows:
                bar = "█" * row[1]
                print(f"  {row[0]} | {row[1]:>3}건 (👍{row[2]} 👎{row[3]} ➖{row[4]}) {bar}")

    finally:
        conn.close()

    print("\n✅ 종목 추출 & 감성 분석 완료!")


if __name__ == "__main__":
    main()
