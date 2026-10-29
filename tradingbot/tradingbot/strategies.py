"""Stratégies de trading.

Chaque stratégie prend un DataFrame de bougies CLÔTURÉES (colonnes open, high,
low, close, volume) et renvoie le même DataFrame enrichi de :

- ``entry``     : bool, signal d'achat à la clôture de cette bougie
- ``exit``      : bool, signal de sortie à la clôture de cette bougie
- ``stop_dist`` : distance (en prix) entre l'entrée et le stop-loss
- ``tp_dist``   : distance (en prix) entre l'entrée et le take-profit

Le même code sert au backtest (toutes les lignes) et au live (dernière ligne),
ce qui garantit que ce qui est testé est ce qui est tradé.

Toutes les stratégies sont « long only » : on achète puis on revend, pas de
vente à découvert (impossible en spot sur Coinbase).
"""
from dataclasses import dataclass

import pandas as pd

from . import indicators as ind


class Strategy:
    name = "base"

    def warmup(self) -> int:
        """Nombre minimal de bougies nécessaires avant un premier signal."""
        raise NotImplementedError

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError


@dataclass
class EmaCross(Strategy):
    """Suivi de tendance court terme.

    Achat quand l'EMA rapide croise au-dessus de l'EMA lente, uniquement si le
    prix est au-dessus de l'EMA de tendance (on ne trade que dans le sens du
    marché) et si le RSI n'est pas en zone de surachat.
    Sortie sur croisement inverse, stop-loss ou take-profit (basés sur l'ATR).
    """

    fast: int = 9
    slow: int = 21
    trend: int = 200
    rsi_period: int = 14
    rsi_max: float = 70.0
    atr_period: int = 14
    atr_stop_mult: float = 2.0
    reward_risk: float = 2.0

    name = "ema_cross"

    def warmup(self) -> int:
        return max(self.trend, self.slow, self.rsi_period, self.atr_period) + 5

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        close = out["close"]
        f, s, t = ind.ema(close, self.fast), ind.ema(close, self.slow), ind.ema(close, self.trend)
        r = ind.rsi(close, self.rsi_period)
        a = ind.atr(out, self.atr_period)
        cross_up = (f > s) & (f.shift(1) <= s.shift(1))
        cross_down = (f < s) & (f.shift(1) >= s.shift(1))
        out["entry"] = (cross_up & (close > t) & (r < self.rsi_max)).fillna(False)
        out["exit"] = cross_down.fillna(False)
        out["stop_dist"] = a * self.atr_stop_mult
        out["tp_dist"] = out["stop_dist"] * self.reward_risk
        return out


@dataclass
class MeanReversion(Strategy):
    """Achat de repli dans une tendance haussière.

    Achat quand le prix clôture sous la bande de Bollinger basse avec un RSI
    survendu, tant que le prix reste au-dessus de l'EMA de tendance.
    Sortie quand le prix revient sur la moyenne (bande médiane).
    """

    bb_period: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    rsi_min: float = 30.0
    trend: int = 200
    atr_period: int = 14
    atr_stop_mult: float = 2.0
    reward_risk: float = 3.0

    name = "mean_reversion"

    def warmup(self) -> int:
        return max(self.trend, self.bb_period, self.rsi_period, self.atr_period) + 5

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        close = out["close"]
        lower, mid, _ = ind.bollinger(close, self.bb_period, self.bb_std)
        r = ind.rsi(close, self.rsi_period)
        t = ind.ema(close, self.trend)
        a = ind.atr(out, self.atr_period)
        out["entry"] = ((close < lower) & (r < self.rsi_min) & (close > t)).fillna(False)
        out["exit"] = (close > mid).fillna(False)
        out["stop_dist"] = a * self.atr_stop_mult
        out["tp_dist"] = out["stop_dist"] * self.reward_risk
        return out


STRATEGIES = {cls.name: cls for cls in (EmaCross, MeanReversion)}


def build_strategy(name: str, params: dict | None = None) -> Strategy:
    if name not in STRATEGIES:
        raise ValueError(f"Stratégie inconnue '{name}'. Choix : {', '.join(STRATEGIES)}")
    return STRATEGIES[name](**(params or {}))
