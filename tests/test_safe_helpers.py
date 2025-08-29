import os
from paper_broker import PaperBroker
from order_utils import safe_create_order


def test_safe_create_order_market():
    ex = PaperBroker(1000.0)
    res = safe_create_order(ex, 'market', 'BTC/USDT', 'buy', 0.001)
    assert isinstance(res, dict)
    # PaperBroker returns an object with id/symbol/side
    assert res.get('symbol') == 'BTC/USDT'
    assert res.get('side') == 'buy'
    assert 'id' in res


def test_exchange_router_paper_mode_fetch_and_order():
    # exercise the ExchangeRouter in paper mode: fetch_ohlcv fallback and create_order
    from router import ExchangeRouter
    # ensure we use paper backend
    os.environ['EXCHANGE_ID'] = 'paper'
    ex = ExchangeRouter()
    # fetch ohlcv (PaperBroker returns synthetic or empty but should not raise)
    bars = ex.safe_fetch_ohlcv('BTC/USDT', '1m', limit=5)
    assert isinstance(bars, list)
    # create a paper market order (router.safe_place_order signature: symbol, side, amount, price=None, params=None)
    res = ex.safe_place_order('BTC/USDT', 'buy', 0.001)
    assert isinstance(res, dict)
    assert res.get('symbol') == 'BTC/USDT'


def test_tg_notifier_mocked(monkeypatch):
    # ensure notifier will call Telegram endpoints; mock requests.post to avoid network
    import notifier
    called = {}

    def fake_post(url, *args, **kwargs):
        called['url'] = url
        class R:
            status_code = 200
            def json(self):
                return {'ok': True, 'result': {'message_id': 1}}
        return R()

    import requests
    # ensure notifier instance thinks it's enabled
    import os
    os.environ['TELEGRAM_ENABLED'] = 'true'
    os.environ['TELEGRAM_BOT_TOKEN'] = 'fake-token'
    os.environ['TELEGRAM_CHAT_ID'] = '1'
    monkeypatch.setattr(requests, 'post', fake_post)
    tn = notifier.TelegramNotifier()
    # call the internal _send which uses requests.post under the hood
    tn._send('test message')
    assert called.get('url') is not None


def test_fetch_ohlcv_synthetic_fallback():
    # force the router into 'malformed' mode to exercise the synthetic fallback
    import os
    from router import ExchangeRouter
    os.environ['EXCHANGE_ID'] = 'paper'
    ex = ExchangeRouter()
    ex._exchange_malformed = True
    bars = ex.safe_fetch_ohlcv('BTC/USDT', '1m', limit=3)
    assert isinstance(bars, list)
    assert len(bars) == 3
    for r in bars:
        assert isinstance(r, list)
        assert len(r) >= 6


def test_place_oco_with_paper_broker():
    from paper_broker import PaperBroker
    from order_utils import place_oco_ccxt
    ex = PaperBroker(10000.0)
    res = place_oco_ccxt(ex, 'BTC/USDT', 'buy', 0.001, entry_px=100.0, stop_px=90.0, take_px=110.0)
    assert isinstance(res, dict)
    assert 'entry' in res and 'tp' in res and 'sl' in res
    assert isinstance(res['entry'], dict)
