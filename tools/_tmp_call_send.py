from tg_utils import send_photo_with_buttons

photo = r"runtime/charts/BTC_USDT_1757060104.png"
buttons = [
    [
        {"text": "Buy / Open", "url": "https://www.binance.com/en/trade/BTCUSDT"},
        {"text": "Flat / Close", "url": "https://www.binance.com/en/my/orders/open"},
    ],
    [{"text": "Balance", "url": "https://www.binance.com/en/usercenter/settings/asset"}],
]
print("calling send_photo_with_buttons...")
ok = send_photo_with_buttons("TEST CAPTION", photo, buttons)
print("result:", ok)
