from juscraper_mcp.ratelimit import RateLimitMiddleware, _client_ip


def test_janela_de_rate_limit():
    mw = RateLimitMiddleware(app=None, max_requests=3, window_seconds=60)
    assert all(mw._permitido("1.2.3.4") for _ in range(3))
    assert mw._permitido("1.2.3.4") is False
    # outro IP não é afetado
    assert mw._permitido("5.6.7.8") is True


def test_client_ip_prefere_x_forwarded_for():
    scope = {"headers": [(b"x-forwarded-for", b"10.0.0.1, 10.0.0.2")], "client": ("127.0.0.1", 1234)}
    assert _client_ip(scope) == "10.0.0.1"
    assert _client_ip({"headers": [], "client": ("127.0.0.1", 1234)}) == "127.0.0.1"
