"""Courtier simulé : vrais prix Coinbase, ordres fictifs."""
import uuid

from .. import data
from .base import Broker, Fill


class PaperBroker(Broker):
    name = "paper"

    def __init__(self, fee_pct: float = 1.2, slippage_pct: float = 0.05):
        self.fee = fee_pct / 100
        self.slip = slippage_pct / 100

    def get_price(self, product: str) -> float:
        return data.get_price(product)

    def available_quote(self, currency: str) -> float:
        return float("inf")  # le budget est géré par le registre du robot

    def market_buy(self, product: str, quote_amount: float) -> Fill:
        price = self.get_price(product) * (1 + self.slip)
        fee = quote_amount * self.fee
        qty = (quote_amount - fee) / price
        return Fill(product, "BUY", price, qty, quote_amount - fee, fee, f"paper-{uuid.uuid4().hex[:8]}")

    def market_sell(self, product: str, base_qty: float) -> Fill:
        price = self.get_price(product) * (1 - self.slip)
        gross = base_qty * price
        return Fill(product, "SELL", price, base_qty, gross, gross * self.fee, f"paper-{uuid.uuid4().hex[:8]}")
