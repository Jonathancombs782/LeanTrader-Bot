"""Run MTF aggregator and publish promoted signals as premium notifications.

This script promotes MTF-aligned signals, generates branded charts, and sends
Telegram messages with inline action buttons (trade links). It also writes the
signals to the NDJSON queue via signals_publisher.publish_batch for audit.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ensure repo root on path so `import tools` works when executed as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pathlib import Path as _Path  # noqa: E402

from tools.mtf_aggregator import read_and_aggregate  # noqa: E402


def _log_pub(event: str, **kw) -> None:
    """Write a small JSON line to runtime/logs/publish_mtf.log for audit/debug."""
    try:
        logdir = _Path(os.getenv("RUNTIME_DIR", "runtime")) / "logs"
        logdir.mkdir(parents=True, exist_ok=True)
        debug_file = logdir / "publish_mtf.log"
        ent = {"ts": int(__import__("time").time()), "event": event}
        ent.update(kw)
        with open(debug_file, "a", encoding="utf-8") as df:
            df.write(json.dumps(ent, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _build_trade_buttons(sig: dict) -> list:
    """Return InlineKeyboardMarkup button rows.

    Uses TRADING_LINK_TEMPLATE env var. Example:
      https://example.com/trade?symbol={symbol}&side={side}&qty={qty}
    If unset, falls back to quick web links that search the symbol on Binance.
    """
    tpl = os.getenv("TRADING_LINK_TEMPLATE", "").strip()
    sym = sig.get("symbol", "").replace("/", "")
    if not tpl:
        buy_url = f"https://www.binance.com/en/trade/{sym}"
        flat_url = "https://www.binance.com/en/my/orders/open" if sym else "https://www.binance.com"
        bal_url = "https://www.binance.com/en/usercenter/settings/asset"
    else:
        # leave {qty} as placeholder for user to fill if template includes it
        buy_url = tpl.format(symbol=sym, side="buy", qty="<qty>")
        flat_url = tpl.format(symbol=sym, side="flat", qty="<qty>")
        bal_url = tpl.format(symbol=sym, side="balance", qty="<qty>")

    # Telegram expects reply_markup JSON; we return array of button rows
    return [
        [{"text": "Buy / Open", "url": buy_url}, {"text": "Flat / Close", "url": flat_url}],
        [{"text": "Balance", "url": bal_url}],
    ]


def main() -> int:
    from signals_publisher import publish_batch
    from tg_utils import send_photo_with_buttons

    try:
        from charting import plot_candlestick
    except Exception:
        plot_candlestick = None
    try:
        from tools.brand_chart import brand_chart
    except Exception:
        brand_chart = None

    promoted = read_and_aggregate(ROOT / "runtime")
    if not promoted:
        print("No multi-timeframe-aligned signals found")
        return 0

    # bump confidence slightly when fully aligned and publish
    for s in promoted:
        s["confidence"] = max(s.get("confidence", 0.0), 0.9)
        s.setdefault("context", [])
        s["context"].insert(0, "MTF: premium alignment across TFs")
        # assign stable id for callbacks
        if not s.get("id"):
            s["id"] = str(json.dumps({"sym": s.get("symbol"), "ts": int(s.get("ts", 0))}))

    # write to queue (audit) via signals_publisher
    res = publish_batch(promoted)
    print(json.dumps(res, indent=2))

    # For each promoted signal, generate a chart, brand it, and send with buttons
    for s in promoted:
        try:
            symbol = s.get("symbol", "")
            fname = f"{symbol.replace('/', '_')}_{int(s.get('ts', 0))}.png"
            charts_dir = ROOT / "runtime" / "charts"
            charts_dir.mkdir(parents=True, exist_ok=True)
            out_path = str((charts_dir / fname).resolve())
            # generate base candlestick (best-effort)
            if plot_candlestick:
                try:
                    plot_candlestick(
                        symbol,
                        s.get("ohlcv") or [],
                        entries=[{"ts": s.get("ts") * 1000, "price": s.get("entry"), "side": s.get("side")}],
                        tps=[s.get("tp1"), s.get("tp2"), s.get("tp3")],
                        sl=s.get("sl"),
                        out_path=out_path,
                    )
                except Exception:
                    pass

            final_path = out_path
            if brand_chart:
                try:
                    caption_title = f"🚀 {symbol} — {s.get('side', '').upper()} — {s.get('tf', '')}"
                    caption_lines = []
                    caption_lines.append(f"Entry: {s.get('entry')}")
                    caption_lines.append(f"SL: {s.get('sl')}")
                    for c in (s.get("context") or [])[:6]:
                        caption_lines.append(str(c))
                    final_path = brand_chart(out_path, caption_title, caption_lines)
                except Exception:
                    final_path = out_path

            # If final_path does not exist (chart generation failed), try to fall back
            # to the most recent existing chart for this symbol in the charts dir.
            try:
                if not os.path.exists(final_path):
                    pattern_prefix = symbol.replace("/", "_")
                    # find files like SYMBOL_*.png
                    candidates = sorted(
                        charts_dir.glob(f"{pattern_prefix}_*.png"), key=lambda p: p.stat().st_mtime, reverse=True
                    )
                    if candidates:
                        fallback = str(candidates[0].resolve())
                        _log_pub("fallback_chart", symbol=symbol, fallback=fallback)
                        final_path = fallback
            except Exception as _e:
                _log_pub("fallback_chart_error", symbol=symbol, error=str(_e))

            # If still missing, create a tiny placeholder image so Telegram upload has a real file
            try:
                if not os.path.exists(final_path):
                    try:
                        # standardize placeholder filename
                        prefix = symbol.replace("/", "_") or "unknown"
                        placeholder_path = charts_dir / f"{prefix}_placeholder.png"
                        from PIL import Image, ImageDraw, ImageFont

                        img = Image.new("RGB", (800, 400), color=(30, 30, 30))
                        d = ImageDraw.Draw(img)
                        try:
                            font = ImageFont.truetype("arial.ttf", 18)
                        except Exception:
                            font = ImageFont.load_default()
                        text = f"Chart unavailable for {symbol}"
                        w, h = d.textsize(text, font=font)
                        d.text(((800 - w) / 2, (400 - h) / 2), text, font=font, fill=(255, 255, 255))
                        img.save(str(placeholder_path))
                        final_path = str(placeholder_path.resolve())
                        _log_pub("created_placeholder", symbol=symbol, path=final_path)
                    except Exception as _e:
                        _log_pub("placeholder_create_failed", symbol=symbol, error=str(_e))
            except Exception as _e:
                _log_pub("placeholder_outer_error", symbol=symbol, error=str(_e))

            # build trade buttons and confirm buttons
            # Use compact, emoji-enhanced trade buttons for better presentation
            def _short_trade_buttons2(sig):
                sym = sig.get("symbol", "").replace("/", "")
                buy_url = f"https://www.binance.com/en/trade/{sym}"
                flat_url = "https://www.binance.com/en/my/orders/open"
                bal_url = "https://www.binance.com/en/usercenter/settings/asset"
                ascii_only = os.getenv("TELEGRAM_ASCII", "false").strip().lower() in ("1", "true", "yes")
                buy_lbl = "Buy" if ascii_only else "🟢 Buy"
                close_lbl = "Close" if ascii_only else "🔻 Close"
                bal_lbl = "Balances" if ascii_only else "💼 Balances"
                return [
                    [{"text": buy_lbl, "url": buy_url}, {"text": close_lbl, "url": flat_url}],
                    [{"text": bal_lbl, "url": bal_url}],
                ]

            def _short_trade_buttons(sig):
                sym = sig.get("symbol", "").replace("/", "")
                buy_url = f"https://www.binance.com/en/trade/{sym}"
                flat_url = "https://www.binance.com/en/my/orders/open"
                bal_url = "https://www.binance.com/en/usercenter/settings/asset"
                return [
                    [{"text": "💹 Buy", "url": buy_url}, {"text": "📉 Close", "url": flat_url}],
                    [{"text": "🏦 Balances", "url": bal_url}],
                ]

            buttons = _short_trade_buttons2(s)
            # build confirm callback buttons for webhook handling
            try:
                from tg_utils import build_confirm_buttons_clean as build_confirm_buttons
            except Exception:
                try:
                    from tg_utils import build_confirm_buttons  # fallback
                except Exception:
                    build_confirm_buttons = None

            # include_subscribe=True so non-premium users see a Subscribe/Link Broker button
            confirm_buttons = (
                build_confirm_buttons(s.get("id"), include_simulate=True, include_subscribe=True)
                if build_confirm_buttons
                else []
            )

            # Multi-line caption with key fields, using basic Markdown escapes
            box = f"Entry: {s.get('entry')} | SL: {s.get('sl')}"
            caption = f"*{symbol}*  \n_{s.get('side', '').upper()}_  TF:{s.get('tf')}  CONF:{s.get('confidence'):.2f}\n`{box}`\n"
            try:
                # send the chart with trade links first
                # Debug: log the exact file path and size before sending
                try:
                    exists = os.path.exists(final_path)
                    size = os.path.getsize(final_path) if exists else None
                except Exception:
                    exists = False
                    size = None
                _log_pub("about_to_send_photo", symbol=symbol, final_path=final_path, exists=exists, size=size)

                # Merge trade buttons and confirm callback buttons into one inline keyboard
                merged_buttons = list(buttons)
                # append confirm_buttons as an additional block if present
                if confirm_buttons:
                    merged_buttons.extend(confirm_buttons)

                # Use a richer send wrapper if available (handles retries/resizing/logging)
                try:
                    from tg_utils import send_photo_rich
                except Exception:
                    send_photo_rich = None

                if send_photo_rich:
                    ok = send_photo_rich(caption, final_path, merged_buttons)
                    _log_pub("send_photo_rich_result", symbol=symbol, ok=bool(ok))
                else:
                    ok = send_photo_with_buttons(caption, final_path, merged_buttons)
                    _log_pub("send_photo_basic_result", symbol=symbol, ok=bool(ok))

                print(f"Sent premium signal photo for {symbol}: {ok}")
            except Exception as e:
                print("Failed to send photo with buttons:", e)
        except Exception as e:
            print("Error processing promoted signal:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
