"""Build VIX-futures curve series from CBOE per-contract files
(see scripts/fetch_cboe_vx.py).

Outputs, all indexed by trade date:
  settle_panel : DataFrame[date x contract]  daily settlement per contract
  curve        : DataFrame with VX1, VX2, VX3 settles, their expiries,
                 calendar days to VX1/VX2 expiry, and CM30 (constant
                 30-day blend, SPVXSP-style weights)
  cm30_return  : daily return of holding the constant-maturity position
                 (roll-weighted P&L on the SAME contracts across t-1 -> t,
                 so expiry days are handled correctly)

Quirks handled:
  - Legacy files quote prices x10 before 2007-03-26 (CFE rescaled VX by
    1/10 that day).  Divided through.
  - Legacy files carry a disclaimer line above the header; some rows have
    Settle 0 before a contract starts trading.  Dropped.
  - Dates come as mm/dd/yyyy or yyyy-mm-dd.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pandas as pd

RESCALE_DATE = pd.Timestamp("2007-03-26")
_EXP_RE = re.compile(r"_exp(\d{4}-\d{2}-\d{2})\.csv$")


def _read_one(path: Path) -> pd.DataFrame:
    lines = path.read_text(errors="replace").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("Trade Date"))
    except StopIteration:
        return pd.DataFrame()
    from io import StringIO

    df = pd.read_csv(StringIO("\n".join(lines[start:])), engine="python", on_bad_lines="skip", index_col=False)
    df.columns = [c.strip() for c in df.columns]
    df["date"] = pd.to_datetime(df["Trade Date"], format="mixed")
    df["settle"] = pd.to_numeric(df["Settle"], errors="coerce")
    df["volume"] = pd.to_numeric(df.get("Total Volume"), errors="coerce")
    df["oi"] = pd.to_numeric(df.get("Open Interest"), errors="coerce")
    df = df[df["settle"] > 0].copy()
    pre = df["date"] < RESCALE_DATE
    df.loc[pre, "settle"] = df.loc[pre, "settle"] / 10.0
    m = _EXP_RE.search(path.name)
    df["expiry"] = pd.Timestamp(m.group(1)) if m else pd.NaT
    df["contract"] = path.stem.split("_exp")[0].replace("VX_", "")
    return df[["date", "contract", "expiry", "settle", "volume", "oi"]]


def load_raw(raw_dir: Path) -> pd.DataFrame:
    frames = [_read_one(p) for p in sorted(raw_dir.glob("VX_*.csv"))]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    # Only keep trade dates strictly before expiry (final settlement is the
    # Wednesday AM SOQ; the last trade date is the Tuesday).
    df = df[df["date"] < df["expiry"]]
    return df.sort_values(["date", "expiry"]).reset_index(drop=True)


def build_curve(raw: pd.DataFrame, min_days: int = 1) -> dict:
    settle = raw.pivot_table(index="date", columns="contract", values="settle")
    expiry = raw.groupby("contract")["expiry"].first()
    contracts_by_exp = expiry.sort_values().index.tolist()
    settle = settle.reindex(columns=contracts_by_exp)

    rows = []
    for date, row in settle.iterrows():
        live = row.dropna()
        live = live[[expiry[c] - date >= pd.Timedelta(days=min_days) for c in live.index]]
        if len(live) < 2:
            continue
        c1, c2 = live.index[0], live.index[1]
        c3 = live.index[2] if len(live) > 2 else None
        e1, e2 = expiry[c1], expiry[c2]
        dr = (e1 - date).days
        dtot = (e2 - e1).days
        w1 = dr / dtot if dtot > 0 else 1.0
        w1 = float(np.clip(w1, 0.0, 1.0))
        rows.append(
            {
                "date": date,
                "c1": c1, "c2": c2, "c3": c3,
                "VX1": live[c1], "VX2": live[c2],
                "VX3": live[c3] if c3 else np.nan,
                "exp1": e1, "exp2": e2,
                "days1": dr, "days2": (e2 - date).days,
                "w1": w1,
                "CM30": w1 * live[c1] + (1 - w1) * live[c2],
            }
        )
    curve = pd.DataFrame(rows).set_index("date")

    # Constant-maturity position return: weights from t-1, prices of the
    # SAME contracts at t-1 and t.
    prev = curve.shift(1)
    p1_t = _lookup(settle, curve.index, prev["c1"])
    p2_t = _lookup(settle, curve.index, prev["c2"])
    pnl = prev["w1"] * (p1_t - prev["VX1"]) + (1 - prev["w1"]) * (p2_t - prev["VX2"])
    cm30_ret = pd.Series(pnl.values / prev["CM30"].values, index=curve.index, name="cm30_return")
    return {"settle_panel": settle, "expiry": expiry, "curve": curve, "cm30_return": cm30_ret}


def _lookup(panel: pd.DataFrame, dates, contracts) -> np.ndarray:
    out = np.full(len(dates), np.nan)
    col_idx = {c: i for i, c in enumerate(panel.columns)}
    row_idx = {d: i for i, d in enumerate(panel.index)}
    vals = panel.values
    for k, (d, c) in enumerate(zip(dates, contracts)):
        if isinstance(c, str) and c in col_idx and d in row_idx:
            out[k] = vals[row_idx[d], col_idx[c]]
    return out
