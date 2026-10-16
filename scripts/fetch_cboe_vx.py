"""Download every CBOE VIX futures (VX) per-contract daily file from CBOE's
free public archive into data/cboe_vx/raw/.

Two URL patterns cover the full history (verified 2026-10-15):

  legacy  https://cdn.cboe.com/resources/futures/archive/volume-and-price/CFE_{M}{YY}_VX.csv
          contract months 2004-05 (first VX listing) through ~2019; 403 after.
  current https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{expiry}.csv
          expiries 2013-06-19 onward; 403 before.

Both are tried for every month; whichever answers is kept (current wins on
overlap). Expiry rule: the Wednesday 30 days before the third Friday of the
following month; +/-1 day fallbacks cover holiday shifts.

Idempotent: existing non-empty files are skipped.  Usage:
  python scripts/fetch_cboe_vx.py
"""
from __future__ import annotations

import datetime as dt
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "cboe_vx" / "raw"
LEGACY = "https://cdn.cboe.com/resources/futures/archive/volume-and-price/CFE_{code}{yy}_VX.csv"
CURRENT = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{d}.csv"
MONTH_CODES = "FGHJKMNQUVXZ"
UA = {"User-Agent": "Mozilla/5.0 (ten-cent-bot research)"}


def third_friday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 15)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d


def vx_expiry(year: int, month: int) -> dt.date:
    """Monthly VX expiry for contract month (year, month)."""
    ny, nm = (year, month + 1) if month < 12 else (year + 1, 1)
    return third_friday(ny, nm) - dt.timedelta(days=30)


def get(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    first = (2004, 5)
    last = (today.year + 1, 12)
    months = []
    y, m = first
    while (y, m) <= last:
        months.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)

    got = skipped = missed = 0
    for y, m in months:
        code = MONTH_CODES[m - 1]
        yy = f"{y % 100:02d}"
        exp = vx_expiry(y, m)
        out = RAW / f"VX_{y}-{m:02d}_exp{exp.isoformat()}.csv"
        if out.exists() and out.stat().st_size > 200:
            skipped += 1
            continue
        data = None
        src = None
        for delta in (0, -1, 1, -2, 2):
            d = exp + dt.timedelta(days=delta)
            data = get(CURRENT.format(d=d.isoformat()))
            if data:
                src = f"current {d}"
                if delta:
                    out = RAW / f"VX_{y}-{m:02d}_exp{d.isoformat()}.csv"
                break
        if not data:
            data = get(LEGACY.format(code=code, yy=yy))
            src = "legacy" if data else None
        if data and b"Trade Date" in data:
            out.write_bytes(data)
            got += 1
            print(f"  {y}-{m:02d}  {src:<20} {len(data):>7} bytes")
        else:
            missed += 1
            if y <= today.year:
                print(f"  {y}-{m:02d}  MISSING")
        time.sleep(0.05)
    print(f"\ndownloaded {got}, skipped {skipped}, missing {missed}")


if __name__ == "__main__":
    sys.exit(main())
