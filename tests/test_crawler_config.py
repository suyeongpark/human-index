import crawler_config


def test_build_headers_uses_fmkorea_cookie_and_user_agent(monkeypatch):
    monkeypatch.setenv("FMKOREA_COOKIE", "a=b; c=d")
    monkeypatch.setenv("FMKOREA_USER_AGENT", "Custom Browser")

    headers = crawler_config.build_headers("fmkorea", referer="https://www.fmkorea.com/stock")

    assert headers["Cookie"] == "a=b; c=d"
    assert headers["User-Agent"] == "Custom Browser"
    assert headers["Referer"] == "https://www.fmkorea.com/stock"
    assert headers["Sec-Fetch-Site"] == "same-origin"


def test_build_headers_omits_cookie_when_not_configured(monkeypatch):
    monkeypatch.delenv("FMKOREA_COOKIE", raising=False)

    headers = crawler_config.build_headers("fmkorea")

    assert "Cookie" not in headers
    assert headers["Sec-Fetch-Site"] == "none"
