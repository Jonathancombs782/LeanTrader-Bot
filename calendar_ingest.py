# calendar_ingest.py
"""
Download or scrape upcoming economic calendar events and save to data/calendar.csv
Supports: Investing.com (unofficial), FRED, or dummy fallback.
"""

import os, csv, requests
from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
OUT_FILE = DATA_DIR / "calendar.csv"

def fetch_investing_calendar():
    """
    Minimal example – you can replace with a paid API or premium feed for reliability.
    """
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"  # free feed from ForexFactory mirror
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    events = r.json()
    rows = []
    for e in events:
        rows.append({
            "time": e.get("date", ""),
            "currency": e.get("country", ""),
            "impact": e.get("impact", ""),
            "event": e.get("title", ""),
            "forecast": e.get("forecast", ""),
            "previous": e.get("previous", ""),
        })
    return pd.DataFrame(rows)

def main():
    try:
        df = fetch_investing_calendar()
        df.to_csv(OUT_FILE, index=False)
        print(f"[calendar] Saved {len(df)} events to {OUT_FILE}")
    except Exception as e:
        print("[calendar] failed:", e)
        # fallback dummy
        with open(OUT_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time","currency","impact","event","forecast","previous"])
            w.writerow(["2099-01-01","USD","HIGH","Dummy Event","N/A","N/A"])
        print(f"[calendar] wrote fallback to {OUT_FILE}")

if __name__ == "__main__":
    main()
