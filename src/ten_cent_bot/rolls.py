"""Futures contract calendar and roll rules for the deployment basket.

Which contract month is 'active' on a given date, and whether a held
contract is due to roll.  Rules are the common retail conventions
(roll a few days before first notice / expiry), encoded per root.
Symbols use the CME/Tradovate form ROOT + month code + 1-digit year
(e.g. MESZ6).  Expiry rules are approximations good to a day or two;
roll_days_before leaves a margin.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

MONTH_CODES = "FGHJKMNQUVXZ"
QUARTERLY = (3, 6, 9, 12)


@dataclass(frozen=True)
class RollRule:
    months: tuple[int, ...]
    kind: str          # 'third_friday' (equity idx), 'third_wed_minus2' (FX), 'month_before_20' (energy/grains/rates), 'prior_month_end' (metals)
    roll_days_before: int = 5


RULES: dict[str, RollRule] = {
    **{r: RollRule(QUARTERLY, "third_friday", 8) for r in ("ES", "MES", "NQ", "MNQ", "RTY", "M2K", "YM")},
    **{r: RollRule(QUARTERLY, "third_wed_minus2", 5) for r in ("6E", "6B", "6J", "6A", "6C", "6S")},
    **{r: RollRule(QUARTERLY, "month_before_20", 5) for r in ("ZN", "ZB", "ZF", "ZT", "UB")},
    **{r: RollRule((2, 4, 6, 8, 10, 12), "prior_month_end", 3) for r in ("GC", "MGC")},
    **{r: RollRule((3, 5, 7, 9, 12), "prior_month_end", 3) for r in ("SI", "HG")},
    **{r: RollRule(tuple(range(1, 13)), "month_before_20", 3) for r in ("CL", "MCL", "NG", "RB", "HO")},
    "ZC": RollRule((3, 5, 7, 9, 12), "prior_month_end", 3), "ZS": RollRule((1, 3, 5, 7, 8, 9, 11), "prior_month_end", 3), "ZW": RollRule((3, 5, 7, 9, 12), "prior_month_end", 3),
}


def _third(year: int, month: int, weekday: int) -> dt.date:
    d = dt.date(year, month, 1); d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=2)


def last_trade_date(root: str, year: int, month: int) -> dt.date:
    """Approximate last day a retail account should hold the contract (expiry
    or first-notice proxy)."""
    r = RULES[root]
    if r.kind == "third_friday":
        return _third(year, month, 4)
    if r.kind == "third_wed_minus2":
        return _third(year, month, 2) - dt.timedelta(days=2)
    if r.kind == "month_before_20":
        py, pm = (year, month - 1) if month > 1 else (year - 1, 12)
        return dt.date(py, pm, 20)
    if r.kind == "prior_month_end":
        return dt.date(year, month, 1) - dt.timedelta(days=1)
    raise ValueError(r.kind)


def roll_date(root: str, year: int, month: int) -> dt.date:
    return last_trade_date(root, year, month) - dt.timedelta(days=RULES[root].roll_days_before)


def active_contract(root: str, on: dt.date) -> tuple[int, int]:
    """(year, month) of the contract a new position should use on `on`:
    the nearest listed month whose roll date is still ahead."""
    y, m = on.year, on.month
    for _ in range(30):
        if m in RULES[root].months and roll_date(root, y, m) > on:
            return y, m
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    raise RuntimeError("no contract found")


def contract_symbol(root: str, year: int, month: int) -> str:
    return f"{root}{MONTH_CODES[month - 1]}{year % 10}"


def parse_symbol(sym: str, root: str, ref: dt.date) -> tuple[int, int]:
    code, yd = sym[len(root)], int(sym[len(root) + 1])
    month = MONTH_CODES.index(code) + 1
    year = (ref.year // 10) * 10 + yd
    if year < ref.year - 2:
        year += 10
    return year, month


def roll_due(root: str, held: str, on: dt.date) -> bool:
    y, m = parse_symbol(held, root, on)
    return on >= roll_date(root, y, m)
