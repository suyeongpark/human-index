from datetime import datetime

import daily_worker
from crawler_config import COMMUNITIES


def test_parse_post_date_supports_known_formats():
    assert daily_worker.parse_post_date("2026-05-04") == datetime(2026, 5, 4)
    assert daily_worker.parse_post_date("2026-04-12 00:41:38") == datetime(2026, 4, 12, 0, 41, 38)
    assert daily_worker.parse_post_date("2026.05.04") == datetime(2026, 5, 4)


def test_analyze_sentiment_counts_positive_and_negative_words():
    assert daily_worker.analyze_sentiment("삼성전자 급등 호재 기대") == 1
    assert daily_worker.analyze_sentiment("삼성전자 급락 악재 우려") == -1
    assert daily_worker.analyze_sentiment("삼성전자 급등 급락") == 0


def test_build_page_url_for_each_community_type():
    assert daily_worker._build_page_url(
        {"parser": "mlbpark", "crawl_url": "https://example.test/list?p=", "posts_per_page": 30},
        1,
    ) == "https://example.test/list?p=&p=31"

    assert daily_worker._build_page_url(
        {"parser": "clien", "crawl_url": "https://example.test/board"},
        2,
    ) == "https://example.test/board?&po=2"

    assert daily_worker._build_page_url(
        {"parser": "fmkorea", "crawl_url": "https://example.test/page="},
        0,
    ) == "https://example.test/page=1"


def test_fmkorea_crawl_depth_is_capped():
    fmkorea_sources = [c for c in COMMUNITIES if c["parser"] == "fmkorea"]

    assert fmkorea_sources
    assert all(c["max_pages"] == 1 for c in fmkorea_sources)


def test_mlbpark_crawl_depth_is_capped():
    mlbpark_sources = [c for c in COMMUNITIES if c["parser"] == "mlbpark"]

    assert mlbpark_sources
    assert all(c["max_pages"] == 1 for c in mlbpark_sources)


def test_known_url_limit_scales_with_crawl_depth():
    assert daily_worker.known_url_limit({"max_pages": 1, "posts_per_page": 20}) == 100
    assert daily_worker.known_url_limit({"max_pages": 10, "posts_per_page": 20}) == 600
    assert daily_worker.known_url_limit({"max_pages": 100, "posts_per_page": 30}) == 1000


class FakeTickerCursor:
    def execute(self, query):
        self.query = query

    def fetchall(self):
        return [
            (1, "005930", "삼성전자", "KOSPI"),
            (2, "000660", "SK하이닉스", "KOSPI"),
            (3, "AAPL", "Apple Inc.", "NASDAQ"),
            (4, "T", "AT&T", "NYSE"),
        ]


def test_build_ticker_map_uses_names_symbols_aliases_and_skip_list(monkeypatch):
    monkeypatch.setattr(daily_worker, "load_aliases", lambda: {"삼전": "005930"})
    monkeypatch.setattr(daily_worker, "load_multi_aliases", lambda: {"삼닉": ["005930", "000660"]})
    monkeypatch.setattr(daily_worker, "load_skip_names", lambda: {"APPLE INC."})

    ticker_map = daily_worker.build_ticker_map(FakeTickerCursor())

    assert ticker_map["삼성전자"] == [(1, "005930")]
    assert ticker_map["삼전"] == [(1, "005930")]
    assert ticker_map["삼닉"] == [(1, "005930"), (2, "000660")]
    assert "APPLE INC." not in ticker_map
    assert "AAPL" in ticker_map
    assert "T" not in ticker_map


class FakeExtractCursor:
    def __init__(self):
        self.rowcount = 0
        self.inserted = []
        self.marked_analyzed = []
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query
        if params and query == daily_worker.SQL_INSERT_MENTION:
            self.inserted.append(params)
            self.rowcount = 1
        elif params and query == daily_worker.SQL_MARK_POST_ANALYZED:
            self.marked_analyzed.append(params[0])
            self.rowcount = 1

    def fetchall(self):
        return [
            (101, "삼전이랑 삼닉 급등"),
            (102, "AAPL 악재 우려"),
        ]


def test_extract_tickers_for_new_posts_inserts_unique_mentions(monkeypatch):
    monkeypatch.setattr(
        daily_worker,
        "build_ticker_map",
        lambda cur: {
            "삼전": [(1, "005930")],
            "삼닉": [(1, "005930"), (2, "000660")],
            "AAPL": [(3, "AAPL")],
        },
    )

    cur = FakeExtractCursor()

    assert daily_worker.extract_tickers_for_new_posts(cur) == 3
    assert (101, 1, 1) in cur.inserted
    assert (101, 2, 1) in cur.inserted
    assert (102, 3, -1) in cur.inserted
    assert len(cur.inserted) == 3
    assert cur.marked_analyzed == [101, 102]
