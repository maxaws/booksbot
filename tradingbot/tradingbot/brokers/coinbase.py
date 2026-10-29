"""Courtier réel : API Coinbase Advanced Trade.

Authentification par clé API CDP (Coinbase Developer Platform) :
https://docs.cdp.coinbase.com/advanced-trade/docs/getting-started

Crée une clé avec UNIQUEMENT les permissions « View » et « Trade »
(JAMAIS « Transfer »/retrait), et restreins-la à ton adresse IP si possible.

Deux formats de clé sont supportés :
- ECDSA : secret au format PEM « -----BEGIN EC PRIVATE KEY----- ... »
- Ed25519 : secret en base64
"""
import base64
import math
import secrets
import time
import uuid
from decimal import Decimal, ROUND_DOWN

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .. import data
from .base import Broker, Fill

HOST = "api.coinbase.com"
API_PREFIX = "/api/v3/brokerage"


class CoinbaseError(RuntimeError):
    pass


def _round_down(value: float, increment: str) -> str:
    inc = Decimal(increment)
    return str((Decimal(str(value)) / inc).to_integral_value(rounding=ROUND_DOWN) * inc)


class CoinbaseBroker(Broker):
    name = "coinbase"

    def __init__(self, api_key: str, api_secret: str):
        if not api_key or not api_secret:
            raise CoinbaseError("COINBASE_API_KEY / COINBASE_API_SECRET manquants (voir .env.example)")
        self.api_key = api_key
        secret = api_secret.replace("\\n", "\n").strip()
        if secret.startswith("-----BEGIN"):
            self._alg, self._signing_key = "ES256", secret
        else:
            raw = base64.b64decode(secret)
            self._alg, self._signing_key = "EdDSA", Ed25519PrivateKey.from_private_bytes(raw[:32])
        self._session = requests.Session()
        self._products: dict[str, dict] = {}

    # --- HTTP authentifié -------------------------------------------------
    def _jwt(self, method: str, path: str) -> str:
        now = int(time.time())
        payload = {"sub": self.api_key, "iss": "cdp", "nbf": now, "exp": now + 120, "uri": f"{method} {HOST}{path}"}
        headers = {"kid": self.api_key, "nonce": secrets.token_hex()}
        return jwt.encode(payload, self._signing_key, algorithm=self._alg, headers=headers)

    def _request(self, method: str, endpoint: str, params=None, body=None) -> dict:
        path = API_PREFIX + endpoint
        for attempt in range(4):
            headers = {"Authorization": f"Bearer {self._jwt(method, path)}", "Content-Type": "application/json"}
            try:
                resp = self._session.request(method, f"https://{HOST}{path}", params=params, json=body, headers=headers, timeout=15)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == 3:
                    break
                time.sleep(2**attempt)
                continue
            if not resp.ok:
                raise CoinbaseError(f"{method} {endpoint} -> HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        raise CoinbaseError(f"{method} {endpoint} -> HTTP {resp.status_code}: {resp.text[:300]}")

    # --- Infos -------------------------------------------------------------
    def accounts(self) -> list[dict]:
        out, cursor = [], None
        while True:
            params = {"limit": 250, **({"cursor": cursor} if cursor else {})}
            res = self._request("GET", "/accounts", params=params)
            out.extend(res.get("accounts", []))
            if not res.get("has_next"):
                return out
            cursor = res.get("cursor")

    def available_quote(self, currency: str) -> float:
        for acc in self.accounts():
            if acc.get("currency") == currency:
                return float(acc["available_balance"]["value"])
        return 0.0

    def product(self, product: str) -> dict:
        if product not in self._products:
            self._products[product] = self._request("GET", f"/products/{product}")
        return self._products[product]

    def get_price(self, product: str) -> float:
        return data.get_price(product)

    # --- Ordres ------------------------------------------------------------
    def _place_market(self, product: str, side: str, size_key: str, size: str) -> Fill:
        body = {
            "client_order_id": str(uuid.uuid4()),
            "product_id": product,
            "side": side,
            "order_configuration": {"market_market_ioc": {size_key: size}},
        }
        res = self._request("POST", "/orders", body=body)
        if not res.get("success"):
            raise CoinbaseError(f"Ordre refusé : {res.get('error_response') or res}")
        order_id = res["success_response"]["order_id"]
        return self._wait_fill(order_id, product, side)

    def _wait_fill(self, order_id: str, product: str, side: str, timeout: float = 30) -> Fill:
        deadline = time.time() + timeout
        while True:
            order = self._request("GET", f"/orders/historical/{order_id}")["order"]
            status = order.get("status")
            if status in ("FILLED", "CANCELLED", "EXPIRED", "FAILED") or time.time() > deadline:
                filled = float(order.get("filled_size") or 0)
                if filled <= 0:
                    raise CoinbaseError(f"Ordre {order_id} non exécuté (statut {status})")
                return Fill(
                    product=product,
                    side=side,
                    price=float(order.get("average_filled_price") or 0),
                    base_qty=filled,
                    quote_amount=float(order.get("filled_value") or 0),
                    fee=float(order.get("total_fees") or 0),
                    order_id=order_id,
                )
            time.sleep(1)

    def market_buy(self, product: str, quote_amount: float) -> Fill:
        info = self.product(product)
        size = _round_down(quote_amount, info["quote_increment"])
        if float(size) < float(info.get("quote_min_size") or 0):
            raise CoinbaseError(f"Montant {size} inférieur au minimum {info['quote_min_size']} pour {product}")
        return self._place_market(product, "BUY", "quote_size", size)

    def market_sell(self, product: str, base_qty: float) -> Fill:
        info = self.product(product)
        size = _round_down(base_qty, info["base_increment"])
        if float(size) <= 0 or math.isclose(float(size), 0.0):
            raise CoinbaseError(f"Quantité {base_qty} trop petite pour {product}")
        return self._place_market(product, "SELL", "base_size", size)
