"""Gestion du risque : taille des positions et garde-fous.

C'est la partie la plus importante du robot. Une stratégie moyenne avec une
bonne gestion du risque survit ; une bonne stratégie sans gestion du risque
finit par tout perdre.
"""
from dataclasses import dataclass


@dataclass
class RiskConfig:
    # Part du capital qu'on accepte de perdre si le stop-loss est touché.
    risk_per_trade_pct: float = 1.0
    # Taille maximale d'une position, en % du capital.
    max_position_pct: float = 50.0
    max_open_positions: int = 2
    # Plus de nouvelles entrées pour la journée (UTC) si la perte du jour dépasse ce seuil.
    daily_loss_limit_pct: float = 3.0
    # Coupe-circuit : tout est vendu et le robot s'arrête si le capital recule
    # de ce pourcentage depuis son plus haut. Réarmement manuel (commande `reset`).
    max_drawdown_pct: float = 15.0
    # Montant minimal d'un ordre (en devise de cotation). Coinbase refuse les
    # ordres trop petits ; et sous quelques euros les frais fixes dominent.
    min_order_quote: float = 5.0


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def position_size(self, equity: float, cash: float, price: float, stop_dist: float) -> float:
        """Montant à investir (devise de cotation), ou 0 si le trade est refusé.

        La taille est calculée pour que toucher le stop coûte environ
        ``risk_per_trade_pct`` du capital, plafonnée par ``max_position_pct``
        et par le cash disponible.
        """
        if equity <= 0 or price <= 0 or not stop_dist or stop_dist <= 0 or stop_dist != stop_dist:
            return 0.0
        risk_amount = equity * self.cfg.risk_per_trade_pct / 100
        stop_pct = stop_dist / price
        size = risk_amount / stop_pct
        size = min(size, equity * self.cfg.max_position_pct / 100, cash * 0.995)
        return size if size >= self.cfg.min_order_quote else 0.0

    def can_open(self, open_positions: int, equity: float, day_start_equity: float) -> tuple[bool, str]:
        if open_positions >= self.cfg.max_open_positions:
            return False, "nombre max de positions atteint"
        if day_start_equity > 0 and equity <= day_start_equity * (1 - self.cfg.daily_loss_limit_pct / 100):
            return False, "limite de perte journalière atteinte"
        return True, ""

    def drawdown_breached(self, equity: float, peak_equity: float) -> bool:
        return peak_equity > 0 and equity <= peak_equity * (1 - self.cfg.max_drawdown_pct / 100)
