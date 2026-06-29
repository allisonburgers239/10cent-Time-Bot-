"""Tradovate REST client.

Implements just what the orchestrator needs:
  - OAuth-style authentication (POST /auth/accesstokenrequest)
  - Account / position / cash-balance queries
  - Order placement (with built-in dry-run safeguard)

Hosts:
  Live: https://live.tradovateapi.com/v1
  Demo: https://demo.tradovateapi.com/v1

Credentials needed (request from Tradovate support):
  - username + password (your normal Tradovate login)
  - app_id, cid, sec (issued when API access is enabled on your account)

Set via environment variables to keep them out of source control:
  TRADOVATE_NAME, TRADOVATE_PASSWORD, TRADOVATE_APP_ID,
  TRADOVATE_CID, TRADOVATE_SEC, TRADOVATE_DEVICE_ID

Until credentials are issued, use orchestrator.FilePositionStore + dry-run mode.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


LIVE_HOST = "https://live.tradovateapi.com/v1"
DEMO_HOST = "https://demo.tradovateapi.com/v1"


@dataclass
class TradovateConfig:
    base_url: str
    name: str
    password: str
    app_id: str = "10cent-bot"
    app_version: str = "0.1.0"
    cid: int = 0
    sec: str = ""
    device_id: str = "10cent-bot-1"

    @classmethod
    def from_env(cls, paper: bool = True) -> TradovateConfig:
        base = DEMO_HOST if paper else LIVE_HOST
        required = ["TRADOVATE_NAME", "TRADOVATE_PASSWORD", "TRADOVATE_CID", "TRADOVATE_SEC"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"Missing required env vars: {missing}. "
                "Request API access from Tradovate support, then export TRADOVATE_NAME, "
                "TRADOVATE_PASSWORD, TRADOVATE_APP_ID, TRADOVATE_CID, TRADOVATE_SEC."
            )
        return cls(
            base_url=base,
            name=os.environ["TRADOVATE_NAME"],
            password=os.environ["TRADOVATE_PASSWORD"],
            app_id=os.environ.get("TRADOVATE_APP_ID", "10cent-bot"),
            cid=int(os.environ["TRADOVATE_CID"]),
            sec=os.environ["TRADOVATE_SEC"],
            device_id=os.environ.get("TRADOVATE_DEVICE_ID", "10cent-bot-1"),
        )


class TradovateError(RuntimeError):
    pass


@dataclass
class TradovateClient:
    config: TradovateConfig
    access_token: str | None = field(default=None, repr=False)
    token_expiry: datetime | None = field(default=None, repr=False)
    account_id: int | None = None

    def _request(self, method: str, path: str, body: dict | None = None, authed: bool = True) -> dict | list:
        url = self.config.base_url + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if authed:
            if self._token_expired():
                self.authenticate()
            headers["Authorization"] = f"Bearer {self.access_token}"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read())
            except Exception:
                payload = {}
            raise TradovateError(f"{method} {path} -> HTTP {e.code}: {payload}") from e

    def _token_expired(self) -> bool:
        if not self.access_token or not self.token_expiry:
            return True
        return datetime.now(tz=timezone.utc) >= (self.token_expiry - timedelta(minutes=2))

    # -- Auth ----------------------------------------------------------

    def authenticate(self) -> None:
        body = {
            "name": self.config.name,
            "password": self.config.password,
            "appId": self.config.app_id,
            "appVersion": self.config.app_version,
            "deviceId": self.config.device_id,
            "cid": self.config.cid,
            "sec": self.config.sec,
        }
        resp = self._request("POST", "/auth/accesstokenrequest", body=body, authed=False)
        if not isinstance(resp, dict) or "accessToken" not in resp:
            raise TradovateError(f"Auth response missing accessToken: {resp}")
        self.access_token = resp["accessToken"]
        expires_iso = resp.get("expirationTime")
        self.token_expiry = (
            datetime.fromisoformat(expires_iso.replace("Z", "+00:00"))
            if expires_iso
            else datetime.now(tz=timezone.utc) + timedelta(minutes=75)
        )

    # -- Queries -------------------------------------------------------

    def list_accounts(self) -> list[dict]:
        return self._request("GET", "/account/list")  # type: ignore[return-value]

    def resolve_account(self) -> int:
        if self.account_id is not None:
            return self.account_id
        accounts = self.list_accounts()
        if not accounts:
            raise TradovateError("No Tradovate accounts visible to this login")
        self.account_id = accounts[0]["id"]
        return self.account_id

    def list_positions(self) -> list[dict]:
        return self._request("GET", "/position/list")  # type: ignore[return-value]

    def list_cash_balances(self) -> list[dict]:
        return self._request("GET", "/cashBalance/list")  # type: ignore[return-value]

    def get_account_equity(self) -> float:
        balances = self.list_cash_balances()
        account_id = self.resolve_account()
        for b in balances:
            if b.get("accountId") == account_id:
                return float(b.get("amount", 0.0)) + float(b.get("realizedPnL", 0.0))
        if balances:
            return float(balances[0].get("amount", 0.0))
        raise TradovateError("Could not determine account equity")

    def positions_by_symbol(self) -> dict[str, int]:
        """Aggregate positions to {symbol_root: net_contracts}."""
        result: dict[str, int] = {}
        for p in self.list_positions():
            sym = p.get("symbol") or p.get("contractName") or ""
            root = _symbol_root(sym)
            qty = int(p.get("netPos", 0))
            if qty != 0:
                result[root] = result.get(root, 0) + qty
        return result

    # -- Order placement ----------------------------------------------

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "Market",
        dry_run: bool = True,
    ) -> dict:
        if qty <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        if side not in ("Buy", "Sell"):
            raise ValueError(f"side must be 'Buy' or 'Sell', got {side!r}")

        body = {
            "accountId": self.resolve_account(),
            "action": side,
            "symbol": symbol,
            "orderQty": qty,
            "orderType": order_type,
            "isAutomated": True,
        }

        if dry_run:
            return {"dry_run": True, "would_send": body}

        return self._request("POST", "/order/placeOrder", body=body)  # type: ignore[return-value]


def _symbol_root(symbol: str) -> str:
    """Normalize 'MESH6' / 'MES H6' / 'MES' -> 'MES'."""
    s = (symbol or "").strip()
    for sep in (" ", "."):
        if sep in s:
            s = s.split(sep)[0]
    while s and s[-1].isdigit():
        s = s[:-1]
    if s.endswith(("F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z")) and len(s) > 2:
        # CME month codes -- strip if it's clearly a month code (preceded by underscores etc.)
        # Conservative: only strip if length > 3 (e.g. MESM6 -> MES)
        # This heuristic is imperfect; consumers should pass clean roots when possible.
        if len(s) >= 4:
            s = s[:-1]
    return s
