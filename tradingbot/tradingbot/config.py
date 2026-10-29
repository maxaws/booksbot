import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .data import GRANULARITY_SECONDS
from .risk import RiskConfig


@dataclass
class Config:
    mode: str = "paper"  # "paper" ou "live"
    products: list[str] = field(default_factory=lambda: ["BTC-EUR", "ETH-EUR"])
    granularity: str = "FIFTEEN_MINUTE"
    strategy: str = "ema_cross"
    strategy_params: dict = field(default_factory=dict)
    # Budget alloué au robot. En live, le robot n'utilisera JAMAIS plus que ce
    # montant, même si le compte contient davantage, et ne touchera pas aux
    # cryptos que tu possèdes déjà.
    capital: float = 100.0
    risk: RiskConfig = field(default_factory=RiskConfig)
    fee_pct: float = 1.2
    slippage_pct: float = 0.05
    # Stratégies de portefeuille : on ne rééquilibre que si l'écart dépasse ce % du capital
    rebalance_threshold_pct: float = 5.0
    poll_seconds: int = 30
    state_file: str = "data/state.json"
    journal_file: str = "data/trades.csv"

    @property
    def quote_currency(self) -> str:
        return self.products[0].split("-")[1]

    def validate(self) -> None:
        if self.mode not in ("paper", "live"):
            raise ValueError("mode doit valoir 'paper' ou 'live'")
        if self.granularity not in GRANULARITY_SECONDS:
            raise ValueError(f"granularity invalide. Choix : {', '.join(GRANULARITY_SECONDS)}")
        quotes = {p.split("-")[1] for p in self.products}
        if len(quotes) != 1:
            raise ValueError(f"Tous les produits doivent avoir la même devise de cotation (trouvé {quotes})")
        from .portfolio import PORTFOLIO_STRATEGIES
        from .strategies import STRATEGIES

        if self.strategy not in STRATEGIES and self.strategy not in PORTFOLIO_STRATEGIES:
            raise ValueError(f"Stratégie inconnue '{self.strategy}'. Choix : {', '.join([*STRATEGIES, *PORTFOLIO_STRATEGIES])}")
        if self.capital <= 0:
            raise ValueError("capital doit être > 0")


def load_dotenv(path: str | Path = ".env") -> None:
    """Chargeur .env minimal (n'écrase pas les variables déjà définies)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def load_config(path: str | Path = "config.yaml") -> Config:
    p = Path(path)
    raw = (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}
    risk = RiskConfig(**(raw.pop("risk", None) or {}))
    cfg = Config(risk=risk, **raw)
    cfg.validate()
    return cfg
