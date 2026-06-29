"""CME futures contract specifications.

Point value (dollars per 1.0 price move) is what the orchestrator needs to
convert from a portfolio weight (% of equity) to an integer contract count.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    name: str
    point_value: float  # dollars per 1.0 move in the index/price
    tick_size: float
    yf_symbol: str  # yfinance ticker for historical data


# Full-size and micro variants. Micros are 1/10 size by point value.
CONTRACTS: dict[str, ContractSpec] = {
    # Equity index
    "ES": ContractSpec("ES", "E-mini S&P 500", 50.0, 0.25, "ES=F"),
    "MES": ContractSpec("MES", "Micro E-mini S&P 500", 5.0, 0.25, "ES=F"),
    "NQ": ContractSpec("NQ", "E-mini Nasdaq 100", 20.0, 0.25, "NQ=F"),
    "MNQ": ContractSpec("MNQ", "Micro E-mini Nasdaq 100", 2.0, 0.25, "NQ=F"),
    "M2K": ContractSpec("M2K", "Micro E-mini Russell 2000", 5.0, 0.10, "RTY=F"),
    # Treasuries (point value = $1000/pt for 10y/30y note)
    "ZN": ContractSpec("ZN", "10-yr T-Note", 1000.0, 1.0 / 64.0, "ZN=F"),
    "ZB": ContractSpec("ZB", "30-yr T-Bond", 1000.0, 1.0 / 32.0, "ZB=F"),
    # Metals
    "GC": ContractSpec("GC", "Gold", 100.0, 0.10, "GC=F"),
    "MGC": ContractSpec("MGC", "Micro Gold", 10.0, 0.10, "GC=F"),
    "SI": ContractSpec("SI", "Silver", 5000.0, 0.005, "SI=F"),
    "HG": ContractSpec("HG", "Copper", 25000.0, 0.0005, "HG=F"),
    # Energy
    "CL": ContractSpec("CL", "Crude Oil", 1000.0, 0.01, "CL=F"),
    "MCL": ContractSpec("MCL", "Micro Crude Oil", 100.0, 0.01, "CL=F"),
    # FX
    "6E": ContractSpec("6E", "Euro FX", 125000.0, 0.00005, "6E=F"),
    # Grains
    "ZC": ContractSpec("ZC", "Corn", 50.0, 0.25, "ZC=F"),
}


# The audited Sleeve B deployment basket (mapped to micro contracts where
# available, so a $25-50k account can size positions in integer increments).
DEPLOYMENT_BASKET: list[str] = [
    "MES",  # equity large-cap (use MES not ES for small accounts)
    "MNQ",  # equity tech
    "ZN",   # 10y rates (no micro available)
    "ZB",   # 30y rates (no micro available)
    "MGC",  # gold
    "SI",   # silver
    "HG",   # copper
    "MCL",  # crude
    "6E",   # FX
    "ZC",   # grains
]
