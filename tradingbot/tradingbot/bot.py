"""Boucle de trading (paper ou live).

Le robot tient son propre registre (cash alloué + positions ouvertes) dans un
fichier JSON. Ainsi :
- il ne dépense jamais plus que ``capital`` ;
- il ne vend que ce qu'il a lui-même acheté (tes avoirs existants sont ignorés) ;
- un redémarrage reprend exactement là où il s'était arrêté.

Limite à connaître : les stops sont surveillés par le robot (toutes les
``poll_seconds``). S'il est arrêté, les stops ne sont plus surveillés.
"""
import csv
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import data
from .brokers.base import Broker, Fill
from .config import Config
from .risk import RiskManager
from .strategies import build_strategy

log = logging.getLogger("tradingbot")


@dataclass
class Position:
    product: str
    qty: float
    entry_price: float
    cost: float
    stop: float
    take_profit: float
    opened_at: str


@dataclass
class State:
    cash: float
    peak_equity: float
    day: str = ""
    day_start_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    positions: dict[str, Position] = field(default_factory=dict)
    last_signal_candle: dict[str, str] = field(default_factory=dict)
    realized_pnl: float = 0.0

    @classmethod
    def load(cls, path: Path, capital: float) -> "State":
        if path.exists():
            raw = json.loads(path.read_text())
            raw["positions"] = {k: Position(**v) for k, v in raw.get("positions", {}).items()}
            return cls(**raw)
        return cls(cash=capital, peak_equity=capital)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        tmp.replace(path)  # écriture atomique


class TradingBot:
    def __init__(self, cfg: Config, broker: Broker):
        self.cfg = cfg
        self.broker = broker
        self.strategy = build_strategy(cfg.strategy, cfg.strategy_params)
        self.risk = RiskManager(cfg.risk)
        self.state_path = Path(cfg.state_file)
        self.journal_path = Path(cfg.journal_file)
        self.state = State.load(self.state_path, cfg.capital)
        self.history = self.strategy.warmup() + 50

    # --- Comptabilité ------------------------------------------------------
    def equity(self, prices: dict[str, float]) -> float:
        return self.state.cash + sum(p.qty * prices.get(p.product, p.entry_price) for p in self.state.positions.values())

    def _journal(self, fill: Fill, reason: str, pnl: float | None = None) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.journal_path.exists()
        with self.journal_path.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "mode", "product", "side", "price", "qty", "quote", "fee", "pnl", "reason", "order_id"])
            w.writerow([
                datetime.now(timezone.utc).isoformat(timespec="seconds"), self.cfg.mode, fill.product, fill.side,
                f"{fill.price:.8g}", f"{fill.base_qty:.8g}", f"{fill.quote_amount:.2f}", f"{fill.fee:.4f}",
                "" if pnl is None else f"{pnl:.2f}", reason, fill.order_id,
            ])

    # --- Ordres --------------------------------------------------------------
    def _open(self, product: str, price: float, stop_dist: float, tp_dist: float, equity: float) -> None:
        cash = min(self.state.cash, self.broker.available_quote(self.cfg.quote_currency))
        amount = self.risk.position_size(equity, cash, price, stop_dist)
        if amount <= 0:
            log.info("%s : signal d'achat ignoré (taille trop petite ou cash insuffisant)", product)
            return
        fill = self.broker.market_buy(product, amount)
        cost = fill.quote_amount + fill.fee
        self.state.cash -= cost
        self.state.positions[product] = Position(
            product, fill.base_qty, fill.price, cost,
            stop=fill.price - stop_dist, take_profit=fill.price + tp_dist,
            opened_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.state.save(self.state_path)
        self._journal(fill, "entrée")
        log.info("ACHAT %s : %.8g @ %.2f (coût %.2f, stop %.2f, objectif %.2f)",
                 product, fill.base_qty, fill.price, cost, fill.price - stop_dist, fill.price + tp_dist)

    def _close(self, product: str, reason: str) -> None:
        pos = self.state.positions[product]
        fill = self.broker.market_sell(product, pos.qty)
        proceeds = fill.quote_amount - fill.fee
        pnl = proceeds - pos.cost
        self.state.cash += proceeds
        self.state.realized_pnl += pnl
        del self.state.positions[product]
        self.state.save(self.state_path)
        self._journal(fill, reason, pnl)
        log.info("VENTE %s (%s) : %.8g @ %.2f -> P&L %+.2f", product, reason, fill.base_qty, fill.price, pnl)

    # --- Cycle ---------------------------------------------------------------
    def step(self) -> None:
        st = self.state
        prices = {p: self.broker.get_price(p) for p in self.cfg.products}
        equity = self.equity(prices)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if st.day != today:
            st.day, st.day_start_equity = today, equity
        st.peak_equity = max(st.peak_equity, equity)

        if st.halted:
            log.warning("Robot en pause : %s. Lance `python -m tradingbot reset` après analyse.", st.halt_reason)
            return

        if self.risk.drawdown_breached(equity, st.peak_equity):
            log.error("COUPE-CIRCUIT : capital %.2f < plus haut %.2f - %.0f %%", equity, st.peak_equity, self.cfg.risk.max_drawdown_pct)
            for product in list(st.positions):
                self._close(product, "coupe-circuit")
            st.halted, st.halt_reason = True, f"drawdown > {self.cfg.risk.max_drawdown_pct} %"
            st.save(self.state_path)
            return

        for product in self.cfg.products:
            price = prices[product]
            pos = st.positions.get(product)

            # Stops vérifiés à chaque cycle, sans attendre la clôture de bougie
            if pos is not None:
                if price <= pos.stop:
                    self._close(product, "stop")
                    continue
                if price >= pos.take_profit:
                    self._close(product, "take-profit")
                    continue

            candles = data.recent_closed_candles(product, self.cfg.granularity, self.history)
            if len(candles) < self.strategy.warmup():
                log.warning("%s : historique insuffisant (%d bougies)", product, len(candles))
                continue
            last = self.strategy.generate(candles).iloc[-1]
            candle_id = candles.index[-1].isoformat()
            if st.last_signal_candle.get(product) == candle_id:
                continue  # cette bougie a déjà été traitée
            st.last_signal_candle[product] = candle_id

            if pos is not None and last["exit"]:
                self._close(product, "signal de sortie")
            elif pos is None and last["entry"]:
                ok, why = self.risk.can_open(len(st.positions), self.equity(prices), st.day_start_equity)
                if ok:
                    self._open(product, price, float(last["stop_dist"]), float(last["tp_dist"]), self.equity(prices))
                else:
                    log.info("%s : signal d'achat ignoré (%s)", product, why)

        st.save(self.state_path)
        log.info("Capital %.2f %s | cash %.2f | positions %s | P&L réalisé %+.2f",
                 self.equity(prices), self.cfg.quote_currency, st.cash, list(st.positions) or "-", st.realized_pnl)

    def run(self) -> None:
        log.info("Démarrage en mode %s | %s | %s | stratégie %s | budget %.2f %s",
                 self.cfg.mode.upper(), ",".join(self.cfg.products), self.cfg.granularity,
                 self.strategy.name, self.cfg.capital, self.cfg.quote_currency)
        while True:
            try:
                self.step()
            except KeyboardInterrupt:
                raise
            except Exception:
                log.exception("Erreur pendant le cycle (nouvel essai au prochain cycle)")
            time.sleep(self.cfg.poll_seconds)
