# ingest_calendar.py
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
OUT_CSV = DATA_DIR / "calendar.csv"

FF_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]


def fetch_forexfactory() -> pd.DataFrame:
    rows = []
    for url in FF_URLS:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            js = r.json()
            for it in js:
                # Fields: "timestamp","country","title","impact","actual","forecast","previous"
                ts = int(it.get("timestamp", 0))
                if ts <= 0:
                    continue
                dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
                impact = (it.get("impact") or "").strip().title()
                rows.append(
                    {
                        "timestamp": dt_utc.isoformat().replace("+00:00", "Z"),
                        "currency": it.get("country", ""),
                        "event": it.get("title", ""),
                        "impact": impact if impact else "Low",
                        "actual": it.get("actual", ""),
                        "forecast": it.get("forecast", ""),
                        "previous": it.get("previous", ""),
                    }
                )
        except Exception as e:
            print("FF fetch error:", e)
    return pd.DataFrame(rows)


def fetch_tradingeconomics(d1: str, d2: str, apikey: str) -> pd.DataFrame:
    # Free guest key also works: guest:guest (limited)
    url = f"https://api.tradingeconomics.com/calendar?d1={d1}&d2={d2}&c=all&format=json&client={apikey}"
    try:
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        js = r.json()
        rows = []
        for it in js:
            # TE fields vary; unify
            dt_utc = pd.to_datetime(it.get("Date"), utc=True)
            impact = (it.get("Importance", "") or "").strip().title()
            rows.append(
                {
                    "timestamp": dt_utc.isoformat().replace("+00:00", "Z"),
                    "currency": it.get("Country", ""),
                    "event": it.get("Event", ""),
                    "impact": impact if impact else "Low",
                    "actual": it.get("Actual", ""),
                    "forecast": it.get("Forecast", ""),
                    "previous": it.get("Previous", ""),
                }
            )
        return pd.DataFrame(rows)
    except Exception as e:
        print("TE fetch error:", e)
        return pd.DataFrame(
            columns=[
                "timestamp",
                "currency",
                "event",
                "impact",
                "actual",
                "forecast",
                "previous",
            ]
        )


def main():
    load_dotenv()
    te_key = os.getenv("TRADING_ECONOMICS_KEY", "guest:guest")

    # ForexFactory this & next week
    df_ff = fetch_forexfactory()

    # TradingEconomics next 14 days (optional, merged)
    today = datetime.utcnow().date()
    d1 = today.isoformat()
    d2 = (today + timedelta(days=14)).isoformat()
    df_te = fetch_tradingeconomics(d1, d2, te_key)

    # Merge & clean
    df = pd.concat([df_ff, df_te], ignore_index=True)
    if df.empty:
        print("No events fetched; writing empty calendar.csv.")
        df = pd.DataFrame(
            columns=[
                "timestamp",
                "currency",
                "event",
                "impact",
                "actual",
                "forecast",
                "previous",
            ]
        )

    # Normalize
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["impact"] = df["impact"].str.title().replace({"Medium": "Medium", "High": "High"}).fillna("Low")
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp", "event", "currency"])

    # Save high-impact only (what your filters expect)
    df_high = df[df["impact"] == "High"].copy()
    df_high.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(df_high)} high-impact rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
