"""
종목 마스터 임포트 스크립트
- KRX: data.krx.co.kr API로 KOSPI/KOSDAQ 전 종목 임포트
- US: 주요 미국 종목 + 한글 별칭 임포트
- 외부 라이브러리 의존 없이 requests만 사용
"""

import psycopg2
import requests
import sys
from bs4 import BeautifulSoup

from db_config import DB_CONFIG


# ─── 미국 주요 종목 + 한글 별칭 ────────────────────────
US_TICKERS = {
    # Mega Cap
    "AAPL": ("Apple", ["애플"]),
    "MSFT": ("Microsoft", ["마이크로소프트", "마소"]),
    "GOOGL": ("Alphabet", ["알파벳", "구글"]),
    "AMZN": ("Amazon", ["아마존"]),
    "NVDA": ("NVIDIA", ["엔비디아"]),
    "TSLA": ("Tesla", ["테슬라"]),
    "META": ("Meta Platforms", ["메타", "페이스북"]),
    "BRK.B": ("Berkshire Hathaway", ["버크셔"]),
    # Tech
    "NFLX": ("Netflix", ["넷플릭스"]),
    "CRM": ("Salesforce", ["세일즈포스"]),
    "ORCL": ("Oracle", ["오라클"]),
    "ADBE": ("Adobe", ["어도비"]),
    "UBER": ("Uber", ["우버"]),
    "PLTR": ("Palantir", ["팔란티어"]),
    "COIN": ("Coinbase", ["코인베이스"]),
    "SOFI": ("SoFi Technologies", ["소파이"]),
    # Semis
    "MU": ("Micron", ["마이크론"]),
    "INTC": ("Intel", ["인텔"]),
    "AMD": ("AMD", []),
    "TSM": ("TSMC", []),
    "AVGO": ("Broadcom", ["브로드컴"]),
    "QCOM": ("Qualcomm", ["퀄컴"]),
    "ARM": ("ARM Holdings", []),
    "ASML": ("ASML", []),
    "MRVL": ("Marvell", ["마벨"]),
    "LRCX": ("Lam Research", ["램리서치"]),
    "AMAT": ("Applied Materials", ["어플라이드"]),
    "WDC": ("Western Digital", ["웨스턴디지털", "샌디스크"]),
    "STX": ("Seagate", ["시게이트"]),
    "ON": ("ON Semiconductor", ["온세미"]),
    # EV
    "RIVN": ("Rivian", ["리비안"]),
    "NIO": ("NIO", ["니오"]),
    "LI": ("Li Auto", ["리오토"]),
    # Pharma
    "LLY": ("Eli Lilly", ["일라이릴리", "릴리"]),
    "NVO": ("Novo Nordisk", ["노보노디스크", "노보"]),
    "PFE": ("Pfizer", ["화이자"]),
    "MRNA": ("Moderna", ["모더나"]),
    # Finance
    "JPM": ("JPMorgan", ["JP모건"]),
    "V": ("Visa", ["비자"]),
    "MA": ("Mastercard", ["마스터카드"]),
    "GS": ("Goldman Sachs", ["골드만삭스"]),
    # Consumer
    "COST": ("Costco", ["코스트코"]),
    "WMT": ("Walmart", ["월마트"]),
    "NKE": ("Nike", ["나이키"]),
    "DIS": ("Disney", ["디즈니"]),
    # Defense
    "LMT": ("Lockheed Martin", ["록히드마틴", "록히드"]),
    "RTX": ("RTX Corp", ["레이시온"]),
    "NOC": ("Northrop Grumman", ["노스롭"]),
    "BA": ("Boeing", ["보잉"]),
    # Energy
    "XOM": ("ExxonMobil", ["엑슨모빌"]),
    "CVX": ("Chevron", ["셰브론"]),
    # ETF
    "SPY": ("SPDR S&P 500 ETF", []),
    "QQQ": ("Invesco QQQ", []),
    "TQQQ": ("ProShares UltraPro QQQ", []),
    "SQQQ": ("ProShares Short QQQ", []),
    "SOXL": ("Direxion Semis Bull 3X", []),
    "SOXS": ("Direxion Semis Bear 3X", []),
    "SCHD": ("Schwab US Dividend Equity", []),
    "VOO": ("Vanguard S&P 500", []),
    "ARKK": ("ARK Innovation ETF", []),
    "JEPI": ("JPMorgan Equity Premium Income", []),
    "JEPQ": ("JPMorgan Nasdaq Equity Premium", []),
}


def fetch_krx_tickers(market_type: str) -> list[dict]:
    """kind.krx.co.kr에서 상장법인 목록 HTML 다운로드 후 파싱
    market_type: stockMkt=KOSPI, kosdaqMkt=KOSDAQ
    """
    url = f"https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType={market_type}"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.encoding = "euc-kr"

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tr")

    results = []
    for row in rows[1:]:  # 헤더 스킵
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        name = cols[0].get_text(strip=True)     # 회사명
        symbol = cols[2].get_text(strip=True)    # 종목코드
        if name and symbol:
            results.append({"symbol": symbol, "name": name})

    return results


def import_krx(cur):
    """KRX 전 종목 임포트"""
    print("\n📌 KRX 종목 임포트...")
    inserted = 0
    updated = 0

    for market_name, market_type in [("KOSPI", "stockMkt"), ("KOSDAQ", "kosdaqMkt")]:
        print(f"  {market_name} 종목 가져오는 중...")
        try:
            tickers = fetch_krx_tickers(market_type)
        except Exception as e:
            print(f"  ❌ {market_name} 조회 실패: {e}")
            continue

        for t in tickers:
            if not t["symbol"]:
                continue
            try:
                cur.execute(
                    """
                    INSERT INTO tickers (symbol, name, market, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (symbol) DO UPDATE
                        SET name = EXCLUDED.name, market = EXCLUDED.market
                    RETURNING (xmax = 0) as is_new
                    """,
                    (t["symbol"], t["name"], market_name),
                )
                is_new = cur.fetchone()[0]
                if is_new:
                    inserted += 1
                else:
                    updated += 1
            except Exception:
                pass

        print(f"  ✅ {market_name}: {len(tickers)}개 처리")

    return inserted, updated


def fetch_krx_etf() -> list[dict]:
    """네이버 금융에서 KRX ETF 전체 목록 조회 (페이지네이션)"""
    results = []
    page = 1
    while True:
        url = f"https://finance.naver.com/api/sise/etfItemList.nhn?etfType=0&targetColumn=market_sum&sortOrder=desc&page={page}&pageSize=100"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        items = data.get("result", {}).get("etfItemList", [])
        if not items:
            break
        for item in items:
            symbol = item.get("itemcode", "").strip()
            name = item.get("itemname", "").strip()
            if symbol and name:
                results.append({"symbol": symbol, "name": name})
        total_pages = data.get("result", {}).get("totalPages", 1)
        if page >= total_pages:
            break
        page += 1
    return results


def import_krx_etf(cur):
    """KRX ETF 전체 임포트"""
    print("\n📌 KRX ETF 임포트...")
    inserted = 0
    updated = 0

    try:
        etfs = fetch_krx_etf()
    except Exception as e:
        print(f"  ❌ ETF 조회 실패: {e}")
        return 0, 0

    for t in etfs:
        try:
            cur.execute(
                """
                INSERT INTO tickers (symbol, name, market, is_active)
                VALUES (%s, %s, 'ETF', TRUE)
                ON CONFLICT (symbol) DO UPDATE
                    SET name = EXCLUDED.name, market = 'ETF'
                RETURNING (xmax = 0) as is_new
                """,
                (t["symbol"], t["name"]),
            )
            is_new = cur.fetchone()[0]
            if is_new:
                inserted += 1
            else:
                updated += 1
        except Exception:
            pass

    print(f"  ✅ ETF: {len(etfs)}개 처리")
    return inserted, updated


def import_us_from_sec(cur):
    """SEC EDGAR에서 미국 전체 상장 종목 임포트"""
    print("\n📌 미국 종목 임포트 (SEC EDGAR)...")

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": "HumanIndex admin@humanindex.local"}
    resp = requests.get(url, headers=headers, timeout=30)
    data = resp.json()

    inserted = 0
    updated = 0
    skipped = 0

    for item in data.values():
        symbol = item.get("ticker", "").strip()
        name = item.get("title", "").strip()

        if not symbol or not name:
            continue

        # 이미 KRX에 있는 심볼 스킵 (숫자 6자리는 한국 종목)
        if symbol.isdigit() and len(symbol) == 6:
            skipped += 1
            continue

        # 심볼에 특수문자가 있으면 정리 (예: BRK/B → BRK.B)
        symbol = symbol.replace("/", ".")

        # 이름 정리 (SEC는 대문자)
        name = name.title()

        try:
            cur.execute(
                """
                INSERT INTO tickers (symbol, name, market, is_active)
                VALUES (%s, %s, 'US', TRUE)
                ON CONFLICT (symbol) DO UPDATE
                    SET name = CASE
                        WHEN tickers.market = 'US' THEN EXCLUDED.name
                        ELSE tickers.name
                    END
                RETURNING (xmax = 0) as is_new
                """,
                (symbol, name),
            )
            is_new = cur.fetchone()[0]
            if is_new:
                inserted += 1
            else:
                updated += 1
        except Exception:
            pass

    print(f"  ✅ SEC EDGAR: {len(data)}개 처리 (신규: {inserted}, 업데이트: {updated}, 스킵: {skipped})")
    return inserted, updated


def main():
    print("=" * 60)
    print("종목 마스터 임포트 (KRX + US)")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM tickers")
                before = cur.fetchone()[0]
                print(f"기존 종목 수: {before}개")

                krx_ins, krx_upd = import_krx(cur)
                print(f"  → 신규: {krx_ins}, 업데이트: {krx_upd}")

                etf_ins, etf_upd = import_krx_etf(cur)
                print(f"  → 신규: {etf_ins}, 업데이트: {etf_upd}")

                us_ins, us_upd = import_us_from_sec(cur)
                print(f"  → 신규: {us_ins}, 업데이트: {us_upd}")

                # 최종 통계
                cur.execute("SELECT market, COUNT(*) FROM tickers GROUP BY market ORDER BY COUNT(*) DESC")
                rows = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM tickers")
                after = cur.fetchone()[0]

        print(f"\n{'=' * 60}")
        print(f"📊 결과: {before}개 → {after}개 (+{after - before})")
        print(f"\n  시장별:")
        for market, cnt in rows:
            print(f"    {market:<10} {cnt:>6}개")

        # 샘플
        with conn.cursor() as cur:
            print(f"\n📋 KRX 샘플 (10개):")
            cur.execute("SELECT symbol, name, market FROM tickers WHERE market IN ('KOSPI','KOSDAQ') ORDER BY random() LIMIT 10")
            for r in cur.fetchall():
                print(f"  {r[0]} {r[1]} ({r[2]})")

            print(f"\n📋 US 샘플 (10개):")
            cur.execute("SELECT symbol, name FROM tickers WHERE market = 'US' ORDER BY random() LIMIT 10")
            for r in cur.fetchall():
                print(f"  {r[0]} {r[1]}")

    finally:
        conn.close()

    print(f"\n✅ 완료!")


if __name__ == "__main__":
    main()
