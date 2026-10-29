"""Backtest réaliste : frais, slippage, exécution à la bougie suivante.

Règles de simulation (volontairement prudentes) :
- un signal à la clôture de la bougie i est exécuté à l'ouverture de i+1
  (pas de « triche » avec une information future) ;
- stop-loss et take-profit sont vérifiés sur le plus bas / plus haut de chaque
  bougie ; si les deux sont touchés dans la même bougie, on suppose le stop ;
- si l'ouverture saute au-delà du stop (gap), on sort au prix d'ouverture ;
- des frais et du slippage sont appliqués à chaque achat et chaque vente.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .risk import RiskManager
from .strategies import Strategy


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    qty: float
    cost: float  # montant investi, frais inclus
    stop: float
    take_profit: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    proceeds: float | None = None  # montant récupéré, frais déduits
    reason: str = ""

    @property
    def pnl(self) -> float:
        return (self.proceeds or 0.0) - self.cost


@dataclass
class BacktestResult:
    product: str
    trades: list[Trade]
    equity: pd.Series
    initial_capital: float
    fees_paid: float
    buy_hold_return_pct: float
    stats: dict = field(default_factory=dict)

    def summary(self) -> str:
        s = self.stats
        return "\n".join(
            [
                f"=== Backtest {self.product} ===",
                f"Période             : {self.equity.index[0]:%Y-%m-%d %H:%M} -> {self.equity.index[-1]:%Y-%m-%d %H:%M}",
                f"Capital initial     : {self.initial_capital:,.2f}",
                f"Capital final       : {s['final_equity']:,.2f}",
                f"Rendement stratégie : {s['return_pct']:+.2f} %",
                f"Rendement buy&hold  : {self.buy_hold_return_pct:+.2f} %",
                f"Nombre de trades    : {s['n_trades']}",
                f"Taux de réussite    : {s['win_rate_pct']:.1f} %",
                f"Profit factor       : {s['profit_factor']:.2f}",
                f"Drawdown max        : {s['max_drawdown_pct']:.2f} %",
                f"Frais payés         : {self.fees_paid:,.2f} ({s['fees_pct_of_capital']:.1f} % du capital)",
                f"Exposition          : {s['exposure_pct']:.1f} % du temps en position",
            ]
        )


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    risk: RiskManager,
    product: str = "",
    initial_capital: float = 100.0,
    fee_pct: float = 1.2,
    slippage_pct: float = 0.05,
) -> BacktestResult:
    sig = strategy.generate(df)
    fee = fee_pct / 100
    slip = slippage_pct / 100

    cash = initial_capital
    peak = initial_capital
    pos: Trade | None = None
    trades: list[Trade] = []
    equity_curve = []
    fees_paid = 0.0
    in_market_bars = 0
    pending_entry: pd.Series | None = None
    pending_exit = False
    halted = False

    def close_position(t, raw_price, reason):
        nonlocal cash, pos, fees_paid
        price = raw_price * (1 - slip)
        gross = pos.qty * price
        fees_paid += gross * fee
        pos.exit_time, pos.exit_price, pos.proceeds, pos.reason = t, price, gross * (1 - fee), reason
        cash += pos.proceeds
        trades.append(pos)
        pos = None

    rows = sig.itertuples()
    for i, row in enumerate(rows):
        t = row.Index

        # 1) Exécution à l'ouverture des ordres décidés à la clôture précédente
        if pos is not None and pending_exit:
            close_position(t, row.open, "signal")
        elif pos is None and pending_entry is not None and not halted:
            price = row.open * (1 + slip)
            equity = cash
            amount = risk.position_size(equity, cash, price, pending_entry.stop_dist)
            if amount > 0:
                fees_paid += amount * fee
                qty = amount * (1 - fee) / price
                cash -= amount
                pos = Trade(
                    t, price, qty, amount,
                    stop=price - pending_entry.stop_dist,
                    take_profit=price + pending_entry.tp_dist,
                )
        pending_entry, pending_exit = None, False

        # 2) Stop-loss / take-profit pendant la bougie
        if pos is not None:
            if row.open <= pos.stop:
                close_position(t, row.open, "stop (gap)")
            elif row.low <= pos.stop:
                close_position(t, pos.stop, "stop")
            elif row.high >= pos.take_profit:
                close_position(t, pos.take_profit, "take-profit")

        # 3) Valorisation et coupe-circuit
        equity = cash + (pos.qty * row.close if pos else 0.0)
        peak = max(peak, equity)
        if not halted and risk.drawdown_breached(equity, peak):
            halted = True
            if pos is not None:
                close_position(t, row.close, "coupe-circuit")
                equity = cash
        equity_curve.append((t, equity))
        if pos is not None:
            in_market_bars += 1

        # 4) Signaux à la clôture -> exécutés à la bougie suivante
        if pos is not None and row.exit:
            pending_exit = True
        elif pos is None and row.entry:
            pending_entry = row

    # Clôture de la position restante en fin de période
    if pos is not None:
        close_position(sig.index[-1], sig["close"].iloc[-1], "fin du backtest")
        equity_curve[-1] = (sig.index[-1], cash)

    equity = pd.Series(dict(equity_curve))
    pnls = np.array([tr.pnl for tr in trades])
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    dd = (equity / equity.cummax() - 1).min() * 100 if len(equity) else 0.0
    stats = {
        "final_equity": float(equity.iloc[-1]) if len(equity) else initial_capital,
        "return_pct": (float(equity.iloc[-1]) / initial_capital - 1) * 100 if len(equity) else 0.0,
        "n_trades": len(trades),
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "profit_factor": (wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf") if len(wins) else 0.0,
        "max_drawdown_pct": abs(float(dd)),
        "fees_pct_of_capital": fees_paid / initial_capital * 100,
        "exposure_pct": in_market_bars / len(sig) * 100 if len(sig) else 0.0,
    }
    bh = (df["close"].iloc[-1] / df["close"].iloc[strategy.warmup()] - 1) * 100 if len(df) > strategy.warmup() else 0.0
    return BacktestResult(product, trades, equity, initial_capital, fees_paid, float(bh), stats)
