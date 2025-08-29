# tg_test.py
# Sends a single test Telegram message using your configured env vars.
from dotenv import load_dotenv
import os
from notifier import TelegramNotifier
import time

load_dotenv()

if __name__ == '__main__':
    n = TelegramNotifier()
    print('Notifier enabled:', n.enabled)
    print('Token present:', bool(n.token))
    print('Chat id present:', bool(n.chat_id))
    if not n.enabled:
        print('\nTelegram is disabled. To enable set TELEGRAM_ENABLED=true in your .env or environment.')
    else:
        print('\nAttempting to send test message...')
        r = n._send('Test message from LeanTrader smoke test at ' + time.strftime('%Y-%m-%d %H:%M:%S'))
        if os.getenv('TELEGRAM_DEBUG','false').lower() == 'true':
            print('tg send response:', r)
        else:
            print('Sent (fire-and-forget). If you do not receive a message, check token/chat id and bot permissions.')
