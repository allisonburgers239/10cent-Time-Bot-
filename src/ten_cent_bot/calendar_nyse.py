"""NYSE trading calendar, rule-based (no external dependency).

Holidays: New Year's Day, MLK Day, Presidents Day, Good Friday, Memorial
Day, Juneteenth (2022+), Independence Day, Labor Day, Thanksgiving,
Christmas; Saturday holidays observed Friday, Sunday holidays observed
Monday (New Year's falling on Saturday is NOT observed on Dec 31, per NYSE
rule 7.2).  Early closes (13:00 ET): day after Thanksgiving, Christmas Eve
and July 3 when they fall on a weekday (and the market is open).
Ad-hoc closures (e.g. national days of mourning) are listed explicitly.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

AD_HOC_CLOSURES = {dt.date(2025, 1, 9)}  # Carter day of mourning


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    d = dt.date(year + (month == 12), (month % 12) + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> dt.date:
    a = year % 19; b = year // 100; c = year % 100; d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30; i = c // 4; k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31; day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _observed(d: dt.date, new_years: bool = False) -> dt.date | None:
    if d.weekday() == 5:
        return None if new_years else d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def holidays(year: int) -> frozenset[dt.date]:
    h = set()
    for d, ny in [(dt.date(year, 1, 1), True), (dt.date(year, 7, 4), False), (dt.date(year, 12, 25), False)]:
        o = _observed(d, ny)
        if o: h.add(o)
    if year >= 2022:
        o = _observed(dt.date(year, 6, 19))
        if o: h.add(o)
    h.add(_nth_weekday(year, 1, 0, 3))      # MLK
    h.add(_nth_weekday(year, 2, 0, 3))      # Presidents
    h.add(_easter(year) - dt.timedelta(days=2))  # Good Friday
    h.add(_last_weekday(year, 5, 0))        # Memorial
    h.add(_nth_weekday(year, 9, 0, 1))      # Labor
    h.add(_nth_weekday(year, 11, 3, 4))     # Thanksgiving
    h |= {d for d in AD_HOC_CLOSURES if d.year == year}
    return frozenset(h)


def is_trading_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def is_early_close(d: dt.date) -> bool:
    if not is_trading_day(d):
        return False
    thanks = _nth_weekday(d.year, 11, 3, 4)
    if d == thanks + dt.timedelta(days=1):
        return True
    if d == dt.date(d.year, 12, 24) or (d == dt.date(d.year, 7, 3)):
        return True
    return False


def next_trading_day(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    while not is_trading_day(d):
        d += dt.timedelta(days=1)
    return d


def session_close(d: dt.date) -> dt.time:
    return dt.time(13, 0) if is_early_close(d) else dt.time(16, 0)
