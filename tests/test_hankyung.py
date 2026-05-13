from datetime import date

import crawl_hankyung


class FakeResponse:
    encoding = "utf-8"

    def __init__(self, text):
        self.text = text


def test_build_url_contains_date_range_page_and_page_size():
    url = crawl_hankyung.build_url(date(2026, 5, 1), date(2026, 5, 4), page=3)

    assert "skinType=business" in url
    assert "sdate=2026-05-01" in url
    assert "edate=2026-05-04" in url
    assert "now_page=3" in url
    assert f"pagenum={crawl_hankyung.PAGENUM}" in url


def test_report_field_parsers_normalize_empty_values():
    assert crawl_hankyung.parse_target_price("123,000") == "123000"
    assert crawl_hankyung.parse_target_price("0") is None
    assert crawl_hankyung.parse_target_price("-") is None

    assert crawl_hankyung.parse_opinion("Buy") == "Buy"
    assert crawl_hankyung.parse_opinion("투자의견없음") is None
    assert crawl_hankyung.parse_opinion("-") is None

    assert crawl_hankyung.extract_ticker_from_title("삼성전자(005930) 실적 개선") == "005930"
    assert crawl_hankyung.extract_ticker_from_title("종목코드 없는 리포트") is None


def test_map_opinion_to_sentiment_uses_loaded_grade_mapping(monkeypatch):
    monkeypatch.setattr(
        crawl_hankyung,
        "_OPINION_GRADES",
        {"strong buy": 1, "buy": 1, "reduce": -1, "hold": 0},
    )

    assert crawl_hankyung.map_opinion_to_sentiment("Strong Buy 유지") == 1
    assert crawl_hankyung.map_opinion_to_sentiment("Reduce") == -1
    assert crawl_hankyung.map_opinion_to_sentiment("Hold") == 0
    assert crawl_hankyung.map_opinion_to_sentiment(None) == 0
    assert crawl_hankyung.map_opinion_to_sentiment("Not Rated") == 0


def test_crawl_page_parses_business_report_table(monkeypatch):
    html = """
    <html>
      <body>
        <div class="table_style01">
          <table>
            <tbody>
              <tr>
                <td>2026-05-04</td>
                <td><a href="/analysis/downpdf?report_idx=1">삼성전자(005930) 실적 개선</a></td>
                <td>123,000</td>
                <td>Buy</td>
                <td>홍길동</td>
                <td>테스트증권</td>
              </tr>
              <tr>
                <td>bad-date</td>
                <td><a>무시되는 행</a></td>
                <td>-</td>
                <td>-</td>
                <td></td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(crawl_hankyung.requests, "get", lambda *args, **kwargs: FakeResponse(html))

    articles = crawl_hankyung.crawl_page("https://example.test")

    assert articles == [
        {
            "title": "삼성전자(005930) 실적 개선",
            "author": "홍길동",
            "securities_firm": "테스트증권",
            "published_date": date(2026, 5, 4),
            "source_url": "https://consensus.hankyung.com/analysis/downpdf?report_idx=1",
            "target_price": "123000",
            "opinion": "Buy",
            "ticker_symbol": "005930",
        }
    ]


def test_get_total_pages_reads_links_and_current_page(monkeypatch):
    html = """
    <div class="paging">
      <a href="?now_page=2">2</a>
      <a href="?now_page=7">7</a>
      <strong>3</strong>
    </div>
    """
    monkeypatch.setattr(crawl_hankyung.requests, "get", lambda *args, **kwargs: FakeResponse(html))

    assert crawl_hankyung.get_total_pages("https://example.test") == 7
