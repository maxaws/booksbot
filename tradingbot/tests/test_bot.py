import base64

import jwt
import numpy as np
import pandas as pd
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from tradingbot import bot as bot_mod
from tradingbot import indicators as ind
from tradingbot.backtest import run_backtest
from tradingbot.brokers.base import Broker, Fill
from tradingbot.brokers.coinbase import CoinbaseBroker, _round_down
from tradingbot.config import Config
from tradingbot.risk import RiskConfig, RiskManager
from tradingbot.strategies import EmaCross, Strategy


def candles(closes, spread=0.5):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": closes, "high": closes + spread, "low": closes - spread, "close": closes, "volume": 1.0}, index=idx
    )


# --- Indicateurs -------------------------------------------------------------
def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert ind.rsi(up).iloc[-1] == 100
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert ind.rsi(down).iloc[-1] < 1
    noisy = pd.Series(np.random.default_rng(0).normal(100, 1, 300))
    r = ind.rsi(noisy).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_atr_constant_range():
    df = candles([100] * 50, spread=1)
    assert ind.atr(df, 14).iloc[-1] == pytest.approx(2.0)


# --- Risque ------------------------------------------------------------------
def test_position_size_respects_risk_and_caps():
    rm = RiskManager(RiskConfig(risk_per_trade_pct=1, max_position_pct=50, min_order_quote=5))
    # stop à 5 % -> 1 % de risque = 20 % du capital
    assert rm.position_size(1000, 1000, 100, 5) == pytest.approx(200)
    # stop très serré -> plafonné à 50 %
    assert rm.position_size(1000, 1000, 100, 0.1) == pytest.approx(500)
    # plafonné par le cash
    assert rm.position_size(1000, 100, 100, 0.1) == pytest.approx(99.5)
    # trop petit -> refusé
    assert rm.position_size(10, 10, 100, 5) == 0
    assert rm.position_size(1000, 1000, 100, float("nan")) == 0


def test_daily_limit_and_drawdown():
    rm = RiskManager(RiskConfig(daily_loss_limit_pct=3, max_drawdown_pct=15, max_open_positions=1))
    assert rm.can_open(0, 98, 100)[0]
    assert not rm.can_open(0, 96.9, 100)[0]
    assert not rm.can_open(1, 100, 100)[0]
    assert rm.drawdown_breached(84, 100)
    assert not rm.drawdown_breached(86, 100)


# --- Backtest ----------------------------------------------------------------
class SignalAt(Strategy):
    """Achat à la bougie `buy`, sortie à la bougie `sell`."""

    name = "test"

    def __init__(self, buy, sell, stop_dist=50.0, tp_dist=1e9):
        self.buy, self.sell, self.stop_dist, self.tp_dist = buy, sell, stop_dist, tp_dist

    def warmup(self):
        return 0

    def generate(self, df):
        out = df.copy()
        out["entry"] = False
        out["exit"] = False
        out.iloc[self.buy, out.columns.get_loc("entry")] = True
        out.iloc[self.sell, out.columns.get_loc("exit")] = True
        out["stop_dist"], out["tp_dist"] = self.stop_dist, self.tp_dist
        return out


def test_backtest_fills_next_bar_and_charges_fees():
    df = candles([100, 100, 110, 120, 130, 130], spread=0)
    risk = RiskManager(RiskConfig(risk_per_trade_pct=100, max_position_pct=100, max_drawdown_pct=100))
    res = run_backtest(df, SignalAt(buy=1, sell=3), risk, initial_capital=100, fee_pct=1.0, slippage_pct=0)
    t = res.trades[0]
    assert t.entry_price == 110  # signal bougie 1 -> exécution ouverture bougie 2
    assert t.exit_price == 130  # signal bougie 3 -> exécution ouverture bougie 4
    expected = 99.5 * 0.99 / 110 * 130 * 0.99
    assert res.stats["final_equity"] == pytest.approx(expected + 0.5)


def test_backtest_stop_loss_intrabar():
    df = candles([100, 100, 100, 80, 80], spread=0)
    df.loc[df.index[3], "open"] = 100
    df.loc[df.index[3], "low"] = 80
    risk = RiskManager(RiskConfig(risk_per_trade_pct=100, max_position_pct=100, max_drawdown_pct=100))
    res = run_backtest(df, SignalAt(buy=1, sell=4, stop_dist=10), risk, initial_capital=100, fee_pct=0, slippage_pct=0)
    t = res.trades[0]
    assert t.reason == "stop" and t.exit_price == pytest.approx(90)


def test_ema_strategy_runs_on_random_walk():
    rng = np.random.default_rng(1)
    df = candles(1000 + np.cumsum(rng.normal(0, 5, 1500)))
    res = run_backtest(df, EmaCross(), RiskManager(RiskConfig()), initial_capital=100)
    assert res.stats["n_trades"] > 0
    assert len(res.equity) == len(df)


# --- Boucle du robot ---------------------------------------------------------
class FakeBroker(Broker):
    def __init__(self, price):
        self.price = price
        self.orders = []

    def get_price(self, product):
        return self.price

    def available_quote(self, currency):
        return 1e9

    def market_buy(self, product, quote_amount):
        fee = quote_amount * 0.01
        self.orders.append(("BUY", quote_amount))
        return Fill(product, "BUY", self.price, (quote_amount - fee) / self.price, quote_amount - fee, fee)

    def market_sell(self, product, base_qty):
        gross = base_qty * self.price
        self.orders.append(("SELL", base_qty))
        return Fill(product, "SELL", self.price, base_qty, gross, gross * 0.01)


@pytest.fixture
def trading_bot(tmp_path, monkeypatch):
    cfg = Config(products=["BTC-EUR"], capital=100, state_file=str(tmp_path / "s.json"),
                 journal_file=str(tmp_path / "t.csv"),
                 risk=RiskConfig(risk_per_trade_pct=1, max_position_pct=50))
    broker = FakeBroker(100.0)
    b = bot_mod.TradingBot(cfg, broker)
    b.strategy = SignalAt(buy=-1, sell=0, stop_dist=2, tp_dist=4)
    monkeypatch.setattr(bot_mod.data, "recent_closed_candles", lambda *a: candles([100] * 10))
    return b, broker


def test_bot_buys_then_stops_out_and_persists(trading_bot):
    b, broker = trading_bot
    b.step()
    pos = b.state.positions["BTC-EUR"]
    assert broker.orders[0] == ("BUY", 50.0)
    assert pos.stop == 98 and pos.take_profit == 104
    assert b.state.cash == pytest.approx(50)

    b.step()  # même bougie : pas de second achat
    assert len(broker.orders) == 1

    broker.price = 97.0
    b.step()
    assert "BTC-EUR" not in b.state.positions
    assert broker.orders[-1][0] == "SELL"
    assert b.state.realized_pnl < 0

    reloaded = bot_mod.State.load(b.state_path, 100)
    assert reloaded.cash == pytest.approx(b.state.cash) and not reloaded.positions
    assert b.journal_path.read_text().count("\n") == 3  # en-tête + achat + vente


def test_bot_kill_switch(trading_bot):
    b, broker = trading_bot
    b.step()
    broker.price = 60.0
    b.state.positions["BTC-EUR"].stop = 0  # neutralise le stop pour tester le coupe-circuit
    b.step()
    assert b.state.halted and not b.state.positions
    n = len(broker.orders)
    b.step()
    assert len(broker.orders) == n  # plus aucun ordre une fois arrêté


# --- Coinbase ----------------------------------------------------------------
def test_round_down():
    assert _round_down(12.3456, "0.01") == "12.34"
    assert _round_down(0.123456789, "0.00000001") == "0.12345678"


def test_jwt_es256_and_ed25519():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                            serialization.NoEncryption()).decode()
    broker = CoinbaseBroker("organizations/o/apiKeys/k", pem.replace("\n", "\\n"))
    token = broker._jwt("GET", "/api/v3/brokerage/accounts")
    claims = jwt.decode(token, key.public_key(), algorithms=["ES256"])
    assert claims["uri"] == "GET api.coinbase.com/api/v3/brokerage/accounts"
    assert jwt.get_unverified_header(token)["kid"] == "organizations/o/apiKeys/k"

    ed = ed25519.Ed25519PrivateKey.generate()
    raw = ed.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = ed.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    broker = CoinbaseBroker("key-id", base64.b64encode(raw + pub).decode())
    token = broker._jwt("POST", "/api/v3/brokerage/orders")
    assert jwt.decode(token, ed.public_key(), algorithms=["EdDSA"])["sub"] == "key-id"


# --- Portefeuille --------------------------------------------------------------
from tradingbot.portfolio import backtest_weights, momentum_rotation, trend_ensemble  # noqa: E402


def daily(**series):
    n = len(next(iter(series.values())))
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({k: np.asarray(v, float) for k, v in series.items()}, index=idx)


def test_trend_ensemble_weights():
    up = np.linspace(100, 300, 300)
    down = np.linspace(300, 100, 300)
    w = trend_ensemble(daily(**{"A-EUR": up, "B-EUR": down}), smas=(20, 50, 100))
    assert w["A-EUR"].iloc[-1] == pytest.approx(0.5)  # 100 % de sa moitié
    assert w["B-EUR"].iloc[-1] == 0
    assert w.iloc[:99].sum().sum() == 0 or w["A-EUR"].iloc[:19].sum() == 0  # pas de poids avant la chauffe
    assert (w.sum(axis=1) <= 1 + 1e-9).all()


def test_backtest_weights_no_lookahead_and_fees():
    closes = daily(**{"A-EUR": [100, 100, 200, 200]})
    w = pd.DataFrame({"A-EUR": [0, 1, 1, 1]}, index=closes.index, dtype=float)
    res = backtest_weights(closes, w, fee_pct=1.0, slippage_pct=0, initial=100)
    # décidé à J1, investi à partir de J2 : le doublement de J2 est capturé, moins 1 % de frais
    assert res.equity.iloc[-1] == pytest.approx(100 * 2 * 0.99)
    # Un poids décidé le jour même du saut ne doit PAS capter ce saut
    w2 = pd.DataFrame({"A-EUR": [0, 0, 1, 1]}, index=closes.index, dtype=float)
    assert backtest_weights(closes, w2, fee_pct=0, slippage_pct=0).equity.iloc[-1] == pytest.approx(100)


def test_momentum_rotation_picks_strongest_and_respects_regime():
    n = 250
    closes = daily(**{
        "BTC-EUR": np.linspace(100, 200, n),
        "ETH-EUR": np.linspace(100, 400, n),
        "XRP-EUR": np.linspace(100, 50, n),
    })
    w = momentum_rotation(closes, lookback=30, top=1, regime_sma=100, rebalance_days=1)
    assert w.iloc[-1].to_dict() == {"BTC-EUR": 0, "ETH-EUR": 1, "XRP-EUR": 0}
    closes["BTC-EUR"] = np.linspace(200, 100, n)  # BTC en baisse -> tout en cash
    w = momentum_rotation(closes, lookback=30, top=1, regime_sma=100, rebalance_days=1)
    assert w.iloc[-1].sum() == 0


def test_portfolio_bot_rebalances(tmp_path, monkeypatch):
    cfg = Config(products=["BTC-EUR", "ETH-EUR"], capital=100, strategy="trend_ensemble",
                 strategy_params={"smas": [5]}, state_file=str(tmp_path / "s.json"),
                 journal_file=str(tmp_path / "t.csv"), risk=RiskConfig(min_order_quote=5))
    broker = FakeBroker(100.0)
    b = bot_mod.make_bot(cfg, broker)
    assert isinstance(b, bot_mod.PortfolioBot)

    targets = iter([({"BTC-EUR": 0.5, "ETH-EUR": 0.5}, "d1"), ({"BTC-EUR": 0.5, "ETH-EUR": 0.5}, "d1"),
                    ({"BTC-EUR": 0.25, "ETH-EUR": 0.0}, "d2")])
    monkeypatch.setattr(b, "target_weights", lambda: next(targets))
    b.step()
    assert [o[0] for o in broker.orders] == ["BUY", "BUY"]
    assert b.state.cash == pytest.approx(0.25, abs=0.01)  # marge de sécurité sur le dernier achat
    b.step()  # même journée : rien
    assert len(broker.orders) == 2
    b.step()  # ETH vendu entièrement, BTC réduit de moitié
    assert "ETH-EUR" not in b.state.positions
    btc = b.state.positions["BTC-EUR"]
    assert btc.qty * 100 == pytest.approx(b.equity({"BTC-EUR": 100, "ETH-EUR": 100}) * 0.25, rel=0.05)


# --- Rapport -------------------------------------------------------------------
def test_report_metrics_and_summary():
    from tradingbot.report import asset_comment, asset_metrics, market_summary

    up = candles(np.linspace(100, 300, 400))
    down = candles(np.linspace(300, 100, 400))
    mu, md = asset_metrics("BTC-EUR", up), asset_metrics("ETH-EUR", down)
    assert mu["trend"] == 3 and md["trend"] == 0
    assert mu["p30"] > 0 > md["p30"]
    assert md["drawdown"] == pytest.approx(-64.6, abs=0.5)  # plus haut des 365 derniers jours
    assert "baissière" in asset_comment(md)
    s = market_summary([mu, md])
    assert s["breadth"] == 1 and s["verdict"]
