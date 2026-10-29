from dataclasses import dataclass


@dataclass
class Fill:
    product: str
    side: str  # "BUY" ou "SELL"
    price: float  # prix moyen d'exécution
    base_qty: float  # quantité de l'actif (ex. BTC)
    quote_amount: float  # montant en devise de cotation, hors frais
    fee: float
    order_id: str = ""


class Broker:
    """Interface commune : le robot ne parle qu'à cette interface.

    Pour ajouter un courtier actions/ETF (Interactive Brokers, Alpaca...), il
    suffit d'implémenter ces méthodes.
    """

    name = "base"

    def get_price(self, product: str) -> float:
        raise NotImplementedError

    def available_quote(self, currency: str) -> float:
        """Solde disponible dans la devise de cotation (EUR, USD, USDC...)."""
        raise NotImplementedError

    def market_buy(self, product: str, quote_amount: float) -> Fill:
        """Achète pour ``quote_amount`` (frais inclus côté Coinbase)."""
        raise NotImplementedError

    def market_sell(self, product: str, base_qty: float) -> Fill:
        raise NotImplementedError
