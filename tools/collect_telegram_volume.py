from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict


async def _collect_with_telethon(chan_usernames: Dict[str, str], minutes: int) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    try:
        from telethon import TelegramClient  # type: ignore
    except Exception:
        return out

    api_id = int(os.getenv('TELEGRAM_API_ID', '0') or 0)
    api_hash = os.getenv('TELEGRAM_API_HASH', '')
    session = os.getenv('TELEGRAM_SESSION', 'tg_session')
    if not api_id or not api_hash:
        return out
    client = TelegramClient(session, api_id, api_hash)
    await client.start()
    since = dt.datetime.utcnow() - dt.timedelta(minutes=minutes)
    for asset, uname in chan_usernames.items():
        try:
            count = 0
            async for msg in client.iter_messages(uname, offset_date=None):
                if msg.date is None:
                    continue
                if msg.date.replace(tzinfo=None) < since:
                    break
                count += 1
            out[asset] = {"value": float(count), "ts": float(dt.datetime.utcnow().timestamp())}
        except Exception:
            out[asset] = {"value": 0.0, "ts": float(dt.datetime.utcnow().timestamp())}
    await client.disconnect()
    return out


def main() -> int:
    p = argparse.ArgumentParser(description='Collect Telegram volume per asset via Telethon')
    p.add_argument('--assets', required=True, help='comma-separated assets e.g., BTC,ETH,SOL')
    p.add_argument('--channels', default=os.getenv('TELEGRAM_CHANNELS', ''), help='mapping like ETH=@channel1,SOL=@channel2')
    p.add_argument('--minutes', type=int, default=int(os.getenv('TELEGRAM_WINDOW_MIN', '60')))
    p.add_argument('--out', default=os.getenv('TELEGRAM_VOLUME_PATH', 'runtime/telegram_volume.json'))
    args = p.parse_args()

    chan_map: Dict[str, str] = {}
    for part in (args.channels or '').split(','):
        if '=' in part:
            a, ch = part.split('=', 1)
            chan_map[a.strip().upper()] = ch.strip()

    if not chan_map:
        Path(args.out).write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({"count": 0}))
        return 0

    try:
        out = asyncio.get_event_loop().run_until_complete(_collect_with_telethon(chan_map, args.minutes))
    except RuntimeError:
        out = asyncio.run(_collect_with_telethon(chan_map, args.minutes))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({"count": len(out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
