from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict


async def _collect(token: str, chan_map: Dict[str, int], minutes: int) -> Dict[str, Dict[str, float]]:
    try:
        import discord  # type: ignore
    except Exception:
        return {}

    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    client = discord.Client(intents=intents)
    out: Dict[str, Dict[str, float]] = {}

    ready = asyncio.Event()

    @client.event
    async def on_ready():  # type: ignore
        try:
            since = dt.datetime.utcnow() - dt.timedelta(minutes=minutes)
            for asset, chan_id in chan_map.items():
                try:
                    chan = await client.fetch_channel(int(chan_id))
                    count = 0
                    async for msg in chan.history(after=since, limit=None):
                        count += 1
                    out[asset] = {"value": float(count), "ts": float(dt.datetime.utcnow().timestamp())}
                except Exception:
                    out[asset] = {"value": 0.0, "ts": float(dt.datetime.utcnow().timestamp())}
        finally:
            ready.set()
            await client.close()

    await client.start(token)
    await ready.wait()
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Collect Discord volume per asset from channels")
    p.add_argument("--assets", required=True, help="comma-separated assets e.g., BTC,ETH,SOL")
    p.add_argument("--channels", default=os.getenv("DISCORD_CHANNELS", ""), help="mapping like ETH=123,SOL=456")
    p.add_argument("--minutes", type=int, default=int(os.getenv("DISCORD_WINDOW_MIN", "60")))
    p.add_argument("--out", default=os.getenv("DISCORD_VOLUME_PATH", "runtime/discord_volume.json"))
    args = p.parse_args()

    token = os.getenv("DISCORD_TOKEN", "").strip()
    chan_map: Dict[str, int] = {}
    for part in (args.channels or '').split(','):
        if '=' in part:
            a, cid = part.split('=', 1)
            try:
                chan_map[a.strip().upper()] = int(cid.strip())
            except Exception:
                continue

    assets = [s.strip().upper() for s in args.assets.split(',') if s.strip()]
    # Ensure each requested asset has some mapping (may be absent -> 0)
    for a in assets:
        chan_map.setdefault(a, 0)

    if not token or not chan_map:
        Path(args.out).write_text(json.dumps({}, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({"count": 0}))
        return 0

    try:
        out = asyncio.get_event_loop().run_until_complete(_collect(token, chan_map, args.minutes))
    except RuntimeError:
        out = asyncio.run(_collect(token, chan_map, args.minutes))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({"count": len(out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
