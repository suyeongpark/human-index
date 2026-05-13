from datetime import date

import crawl_google_news


class FakeResponse:
    encoding = "utf-8"

    def __init__(self, text):
        self.text = text


def test_fetch_rss_articles_parses_titles_sources_dates_and_links(monkeypatch):
    rss = """
    <rss>
      <channel>
        <item>
          <title>삼성전자 실적 개선 - 한국경제</title>
          <source>한국경제</source>
          <pubDate>Mon, 04 May 2026 09:30:00 GMT</pubDate>
          <link>https://news.google.com/articles/1</link>
        </item>
        <item>
          <title>출처 없는 기사</title>
          <pubDate>bad date</pubDate>
          <link>https://news.google.com/articles/2</link>
        </item>
      </channel>
    </rss>
    """

    monkeypatch.setattr(crawl_google_news.requests, "get", lambda *args, **kwargs: FakeResponse(rss))

    articles = crawl_google_news.fetch_rss_articles("https://example.test/rss")

    assert articles[0] == {
        "title": "삼성전자 실적 개선",
        "source": "한국경제",
        "published_date": date(2026, 5, 4),
        "source_url": "https://news.google.com/articles/1",
    }
    assert articles[1]["title"] == "출처 없는 기사"
    assert articles[1]["source"] == ""
    assert articles[1]["published_date"] == date.today()


def test_fetch_rss_articles_returns_empty_when_channel_missing(monkeypatch):
    monkeypatch.setattr(crawl_google_news.requests, "get", lambda *args, **kwargs: FakeResponse("<rss />"))

    assert crawl_google_news.fetch_rss_articles("https://example.test/rss") == []
