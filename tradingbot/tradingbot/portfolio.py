"""Stratégies de portefeuille (plusieurs actifs) et leur backtest.

Ces stratégies travaillent sur des bougies journalières et décident chaque
jour (ou chaque semaine) d'une RÉPARTITION cible : quelle part du capital mettre
dans chaque actif, le reste en euros. Elles tradent peu, donc les frais pèsent
beaucoup moins que dans le trading intraday.

Backtest : la répartition décidée à la clôture du jour J s'applique aux
rendements du jour J+1 (pas d'information future). Les frais sont payés sur
chaque changement de répartition (turnover).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import data


def load_closes(products: list[str], days: int, cache_dir="data/cache") -> pd.DataFrame:
    """Matrice des clôtures journalières (une colonne par produit)."""
    frames = {}
    for p in products:
        df = data.history(p, "ONE_DAY", days, cache_dir=cache_dir)
        if not df.empty:
            frames[p] = df["close"]
    closes = pd.DataFrame(frames).sort_index()
    return closes[~closes.index.duplicated()]


# --- Stratégies : renvoient un DataFrame de poids (somme <= 1) ---------------
def buy_and_hold(closes: pd.DataFrame) -> pd.DataFrame:
    """Répartition égale entre les actifs disponibles, jamais vendus."""
    avail = closes.notna().astype(float)
    return avail.div(avail.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)


def trend_filter(closes: pd.DataFrame, sma: int = 100) -> pd.DataFrame:
    """Suivi de tendance : chaque actif est détenu quand son prix est au-dessus
    de sa moyenne mobile ``sma`` jours, sinon on est en euros.
    Poids égaux entre les actifs du panier."""
    above = (closes > closes.rolling(sma, min_periods=sma).mean()).astype(float)
    n = closes.notna().sum(axis=1).replace(0, np.nan)
    return above.div(n, axis=0).fillna(0)


def momentum_rotation(
    closes: pd.DataFrame,
    lookback: int = 30,
    top: int = 2,
    regime_asset: str | None = "BTC-EUR",
    regime_sma: int = 100,
    rebalance_days: int = 7,
    vol_target: float | None = None,
) -> pd.DataFrame:
    """Rotation momentum : on détient les ``top`` actifs ayant le plus monté sur
    ``lookback`` jours (à condition que leur performance soit positive).
    Filtre de régime : si BTC est sous sa moyenne ``regime_sma``, tout en euros.
    Rééquilibrage tous les ``rebalance_days`` jours.
    ``vol_target`` (ex. 0.6 = 60 %/an) réduit l'exposition quand le marché est agité.
    """
    mom = closes.pct_change(lookback, fill_method=None)
    rank = mom.rank(axis=1, ascending=False)
    picks = ((rank <= top) & (mom > 0)).astype(float)
    weights = picks / top
    if vol_target:
        asset_vol = closes.pct_change(fill_method=None).rolling(30).std() * np.sqrt(365)
        scale = (vol_target / asset_vol.where(weights > 0).mean(axis=1)).clip(upper=1).fillna(0)
        weights = weights.mul(scale, axis=0)
    # Ne rééquilibrer qu'à intervalle régulier : on garde les poids entre deux dates
    mask = pd.Series(np.arange(len(weights)) % rebalance_days == 0, index=weights.index)
    weights = weights.where(mask, np.nan).ffill().fillna(0)
    # Le filtre de régime, lui, s'applique tous les jours : on sort dès que BTC casse sa tendance
    if regime_asset and regime_asset in closes:
        r = closes[regime_asset]
        risk_on = r > r.rolling(regime_sma, min_periods=regime_sma).mean()
        weights = weights.mul(risk_on.astype(float), axis=0)
    return weights


PORTFOLIO_STRATEGIES = {
    "buy_and_hold": buy_and_hold,
    "trend_filter": trend_filter,
    "momentum_rotation": momentum_rotation,
}


# --- Backtest ------------------------------------------------------------------
@dataclass
class PortfolioResult:
    equity: pd.Series
    weights: pd.DataFrame
    turnover: float
    fees_paid_pct: float

    def stats(self, start=None, end=None) -> dict:
        eq = self.equity.loc[start:end]
        if len(eq) < 2:
            return {}
        rets = eq.pct_change().dropna()
        years = (eq.index[-1] - eq.index[0]).days / 365.25
        total = eq.iloc[-1] / eq.iloc[0] - 1
        cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else float("nan")
        dd = (eq / eq.cummax() - 1).min()
        vol = rets.std() * np.sqrt(365)
        sharpe = rets.mean() / rets.std() * np.sqrt(365) if rets.std() > 0 else 0.0
        w = self.weights.loc[start:end]
        return {
            "rendement_total_pct": total * 100,
            "rendement_annuel_pct": cagr * 100,
            "drawdown_max_pct": dd * 100,
            "volatilite_pct": vol * 100,
            "sharpe": sharpe,
            "calmar": (cagr / abs(dd)) if dd < 0 else float("nan"),
            "exposition_pct": w.sum(axis=1).mean() * 100,
        }


def backtest_weights(closes: pd.DataFrame, weights: pd.DataFrame, fee_pct: float = 1.2,
                     slippage_pct: float = 0.05, initial: float = 100.0) -> PortfolioResult:
    rets = closes.pct_change(fill_method=None).fillna(0)
    w = weights.reindex(closes.index).fillna(0)
    held = w.shift(1).fillna(0)  # décision à J, appliquée sur le rendement de J+1
    gross = (held * rets).sum(axis=1)
    # Les poids dérivent avec les prix entre deux rééquilibrages ; on approxime
    # le turnover par la variation des poids cibles (prudent, légèrement surestimé).
    # Les ordres sont passés à la clôture de J : les frais sont payés ce jour-là.
    turnover = (w - w.shift(1).fillna(0)).abs().sum(axis=1)
    cost = turnover * (fee_pct + slippage_pct) / 100
    net = gross - cost
    equity = initial * (1 + net).cumprod()
    return PortfolioResult(equity, w, float(turnover.sum()), float(cost.sum() * 100))


def trend_states(closes: pd.DataFrame, smas=(50, 100, 200), buffer_pct: float = 2.0) -> dict:
    """Pour chaque moyenne : (état 1 = au-dessus / 0 = en dessous, moyenne mobile).

    Avec la zone tampon, l'état ne bascule que si le prix franchit la moyenne
    de plus de ``buffer_pct`` %, sinon il garde son état précédent.
    """
    out = {}
    for n in smas:
        ma = closes.rolling(n, min_periods=n).mean()
        up, down = closes > ma * (1 + buffer_pct / 100), closes < ma * (1 - buffer_pct / 100)
        state = pd.DataFrame(np.where(up, 1.0, np.where(down, 0.0, np.nan)), index=closes.index, columns=closes.columns)
        out[n] = (state.ffill().fillna(0), ma)
    return out


def trend_ensemble(
    closes: pd.DataFrame,
    smas: tuple[int, ...] = (50, 100, 200),
    buffer_pct: float = 2.0,
    vol_target: float | None = None,
    check_days: int = 1,
) -> pd.DataFrame:
    """Suivi de tendance « ensemble » : pour chaque actif, la part investie est
    la proportion de moyennes mobiles sous le prix (0, 1/3, 2/3 ou 1 avec 3 moyennes).
    Plus robuste qu'une seule moyenne : on entre et on sort progressivement.

    - ``buffer_pct`` : zone tampon autour de chaque moyenne (évite les allers-retours) ;
    - ``vol_target`` : volatilité annuelle visée (ex. 0.5), l'exposition baisse quand ça s'agite ;
    - ``check_days`` : fréquence de décision (7 = une fois par semaine).
    Poids égaux entre les actifs du panier.
    """
    states = trend_states(closes, smas, buffer_pct)
    score = sum(st for st, _ in states.values()) / len(smas)
    if vol_target:
        vol = closes.pct_change(fill_method=None).rolling(30).std() * np.sqrt(365)
        score = score * (vol_target / vol).clip(upper=1).fillna(0)
    mask = pd.Series(np.arange(len(score)) % check_days == 0, index=score.index)
    score = score.where(mask, np.nan).ffill().fillna(0)
    # Arrondi au quart pour ne pas trader pour des variations minimes
    score = (score * 4).round() / 4
    n = closes.notna().sum(axis=1).replace(0, np.nan)
    return score.div(n, axis=0).fillna(0)


PORTFOLIO_STRATEGIES["trend_ensemble"] = trend_ensemble
