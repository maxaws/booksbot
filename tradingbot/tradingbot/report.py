"""Rapport de marché en HTML : données Coinbase à jour, expliquées simplement.

    python -m tradingbot report        ->  data/rapport.html

Le rapport contient :
- un résumé du marché en une phrase (tendance, ampleur, agitation) ;
- un tableau par crypto (performances, tendance, RSI, volatilité, chute depuis le
  plus haut) avec une lecture en français ;
- la répartition que la stratégie du robot viserait aujourd'hui ;
- le backtest de cette stratégie comparé à « acheter et garder », sur une
  période d'apprentissage et une période de test jamais vue ;
- un lexique.
"""
import html
import json
import string
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from . import indicators as ind
from .config import Config
from .portfolio import PORTFOLIO_STRATEGIES, backtest_weights, buy_and_hold

UNIVERSE = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "XRP-EUR", "ADA-EUR", "DOGE-EUR",
            "LINK-EUR", "AVAX-EUR", "LTC-EUR", "DOT-EUR", "BCH-EUR"]
NAMES = {"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP", "ADA": "Cardano",
         "DOGE": "Dogecoin", "LINK": "Chainlink", "AVAX": "Avalanche", "LTC": "Litecoin",
         "DOT": "Polkadot", "BCH": "Bitcoin Cash"}
SMAS = (50, 100, 200)
TEST_START = "2024-01-01"


# --- Données -------------------------------------------------------------------
def fresh_daily(product: str, days: int) -> pd.DataFrame:
    """Bougies journalières sans cache ; la dernière est la journée en cours."""
    now = int(time.time())
    return data.fetch_candles(product, "ONE_DAY", now - days * 86400, now)


def asset_metrics(product: str, df: pd.DataFrame) -> dict:
    close = df["close"]
    price = float(close.iloc[-1])

    def perf(days):
        if len(close) <= days:
            return None
        return (price / float(close.iloc[-1 - days]) - 1) * 100

    smas = {n: float(ind.sma(close, n).iloc[-1]) if len(close) >= n else None for n in SMAS}
    above = sum(1 for v in smas.values() if v and price > v)
    rsi = float(ind.rsi(close, 14).iloc[-1])
    daily_vol = float(close.pct_change().tail(30).std() * 100)
    year = close.tail(365)
    drawdown = (price / float(year.max()) - 1) * 100
    base = product.split("-")[0]
    return {
        "product": product, "symbol": base, "name": NAMES.get(base, base), "price": price,
        "p1": perf(1), "p7": perf(7), "p30": perf(30), "p90": perf(90), "p365": perf(365),
        "sma": smas, "trend": above, "rsi": rsi, "vol_day": daily_vol,
        "vol_year": daily_vol * np.sqrt(365), "drawdown": drawdown,
        "dist200": (price / smas[200] - 1) * 100 if smas[200] else None,
    }


def trend_label(score: int) -> tuple[str, str]:
    return {3: ("Haussière", "good"), 2: ("Plutôt haussière", "good"),
            1: ("Plutôt baissière", "serious"), 0: ("Baissière", "critical")}[score]


def rsi_label(rsi: float) -> str:
    if rsi >= 70:
        return "surchauffe"
    if rsi <= 30:
        return "survendu"
    return "neutre"


def asset_comment(m: dict) -> str:
    """Une phrase de lecture, en français courant."""
    parts = []
    t = m["trend"]
    if t == 3:
        parts.append("Au-dessus de ses trois moyennes : la tendance de fond monte")
    elif t == 2:
        parts.append("Au-dessus de deux moyennes sur trois : tendance en amélioration ou en début d'essoufflement")
    elif t == 1:
        parts.append("Sous deux de ses moyennes : la tendance s'est dégradée")
    else:
        parts.append("Sous ses trois moyennes : tendance baissière installée")
    if m["rsi"] >= 70:
        parts.append(f"RSI {m['rsi']:.0f}, forte hausse récente : risque de pause ou de repli")
    elif m["rsi"] <= 30:
        parts.append(f"RSI {m['rsi']:.0f}, forte baisse récente : un rebond est possible mais pas garanti")
    if m["drawdown"] <= -50:
        parts.append(f"encore {abs(m['drawdown']):.0f} % sous son plus haut sur un an")
    return ". ".join(parts) + "."


def market_summary(metrics: list[dict]) -> dict:
    btc = next(m for m in metrics if m["symbol"] == "BTC")
    breadth = sum(1 for m in metrics if m["dist200"] is not None and m["dist200"] > 0)
    n = len(metrics)
    avg30 = float(np.mean([m["p30"] for m in metrics if m["p30"] is not None]))
    if btc["trend"] >= 2 and avg30 < -5:
        verdict, tone = "Tendance de fond positive, mois en repli", "warning"
    elif btc["trend"] == 3 and breadth >= n * 0.6:
        verdict, tone = "Marché haussier", "good"
    elif btc["trend"] >= 2:
        verdict, tone = "Marché plutôt haussier", "good"
    elif btc["trend"] == 1:
        verdict, tone = "Marché hésitant", "serious"
    else:
        verdict, tone = "Marché baissier", "critical"
    btc_pos = "au-dessus" if btc["dist200"] >= 0 else "en dessous"
    text = (
        f"Le bitcoin dépasse {btc['trend']} de ses 3 moyennes mobiles et se situe {abs(btc['dist200']):.0f} % "
        f"{btc_pos} de sa moyenne 200 jours. {breadth} cryptos sur {n} sont au-dessus de leur moyenne 200 jours "
        f"(tendance de fond). Sur le dernier mois, elles ont {'gagné' if avg30 >= 0 else 'perdu'} "
        f"{abs(avg30):.0f} % en moyenne. Le bitcoin bouge en ce moment d'environ ±{_num(btc['vol_day'], 1)} % par jour."
    )
    return {"verdict": verdict, "tone": tone, "text": text, "breadth": breadth, "n": n}


# --- Stratégie -----------------------------------------------------------------
def strategy_section(cfg: Config, closes: pd.DataFrame) -> dict:
    name = cfg.strategy if cfg.strategy in PORTFOLIO_STRATEGIES else "trend_ensemble"
    params = cfg.strategy_params if cfg.strategy in PORTFOLIO_STRATEGIES else {}
    fn = PORTFOLIO_STRATEGIES[name]
    closed = closes.iloc[:-1]  # le robot ne décide que sur des journées clôturées
    weights = fn(closed, **params)
    today = weights.iloc[-1].to_dict()
    res = backtest_weights(closed, weights, cfg.fee_pct, cfg.slippage_pct)
    hold = backtest_weights(closed, buy_and_hold(closed), cfg.fee_pct, cfg.slippage_pct)
    warm = closed.index[min(max(params.get("smas", SMAS)), len(closed) - 2)]
    periods = {
        "Apprentissage": (warm, pd.Timestamp(TEST_START, tz="UTC") - pd.Timedelta(days=1)),
        "Test (jamais vu)": (pd.Timestamp(TEST_START, tz="UTC"), None),
        "Total": (warm, None),
    }
    table = []
    for label, (a, b) in periods.items():
        s, h = res.stats(a, b), hold.stats(a, b)
        if s:
            table.append({"period": label, "from": f"{res.equity.loc[a:b].index[0]:%m/%Y}",
                          "to": f"{res.equity.loc[a:b].index[-1]:%m/%Y}", "strat": s, "hold": h})
    eq_s = res.equity.loc[warm:] / res.equity.loc[warm:].iloc[0] * 100
    eq_h = hold.equity.loc[warm:] / hold.equity.loc[warm:].iloc[0] * 100
    expo = weights.loc[warm:].sum(axis=1) * 100
    return {
        "name": name, "products": list(closed.columns), "today": today,
        "cash_pct": max(0.0, 1 - sum(today.values())) * 100, "table": table,
        "decided_on": f"{closed.index[-1]:%d/%m/%Y}",
        "series": {
            "dates": [d.strftime("%Y-%m-%d") for d in eq_s.index],
            "strat": [round(v, 2) for v in eq_s], "hold": [round(v, 2) for v in eq_h],
            "dd_strat": [round(v, 2) for v in (eq_s / eq_s.cummax() - 1) * 100],
            "dd_hold": [round(v, 2) for v in (eq_h / eq_h.cummax() - 1) * 100],
            "expo": [round(v, 1) for v in expo],
        },
        "fee": cfg.fee_pct,
    }


# --- Construction --------------------------------------------------------------
STANDALONE_HEAD = (
    '<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    "<style>body{margin:0}</style>\n</head>\n<body>\n"
)


def build_report(cfg: Config, out: str | Path = "data/rapport.html", standalone: bool = True) -> Path:
    generated = datetime.now(timezone.utc)
    universe = list(dict.fromkeys([*cfg.products, *UNIVERSE]))
    frames = {p: fresh_daily(p, 600) for p in universe}
    metrics = [asset_metrics(p, df) for p, df in frames.items() if len(df) > 30]
    metrics.sort(key=lambda m: -(m["p30"] or -1e9))
    summary = market_summary(metrics)

    strat_products = cfg.products if all(p.endswith("-EUR") for p in cfg.products) else ["BTC-EUR", "ETH-EUR"]
    long = pd.DataFrame({p: fresh_daily(p, 2400)["close"] for p in strat_products}).sort_index()
    strategy = strategy_section(cfg, long)

    btc = frames["BTC-EUR"].tail(365 + 200)
    c = btc["close"]
    chart_btc = {
        "dates": [d.strftime("%Y-%m-%d") for d in c.index[-365:]],
        "price": [round(v, 0) for v in c.tail(365)],
        **{f"sma{n}": [None if pd.isna(v) else round(v, 0) for v in ind.sma(c, n).tail(365)] for n in SMAS},
    }
    payload = {"btc": chart_btc, "strategy": strategy["series"]}
    page = render(generated, metrics, summary, strategy, payload)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    if standalone:
        page = STANDALONE_HEAD + page + "\n</body>\n</html>\n"
    path.write_text(page, encoding="utf-8")
    return path


# --- Rendu HTML ----------------------------------------------------------------
def _fmt_pct(v, digits=1, signed=True):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '<span class="na">—</span>'
    cls = "up" if v > 0 else "down" if v < 0 else ""
    sign = "+" if signed and v > 0 else ""
    return f'<span class="{cls}">{sign}{v:.{digits}f} %</span>'.replace(".", ",")


def _fmt_price(v):
    if v >= 1000:
        s = f"{v:,.0f}".replace(",", " ")
    elif v >= 1:
        s = f"{v:,.2f}".replace(".", ",")
    else:
        s = f"{v:.4f}".replace(".", ",")
    return f"{s} €"


def _num(v, d=2):
    return f"{v:.{d}f}".replace(".", ",")


def render(generated, metrics, summary, strategy, payload) -> str:
    e = html.escape
    rows = []
    for m in metrics:
        label, tone = trend_label(m["trend"])
        dots = "".join(f'<i class="{"on" if m["sma"][n] and m["price"] > m["sma"][n] else ""}" title="Moyenne {n} jours"></i>' for n in SMAS)
        rsi_tone = {"surchauffe": "warning", "survendu": "serious", "neutre": "neutral"}[rsi_label(m["rsi"])]
        rows.append(f"""
        <tr>
          <th scope="row"><span class="sym">{e(m['symbol'])}</span><span class="nm">{e(m['name'])}</span></th>
          <td class="num">{_fmt_price(m['price'])}</td>
          <td class="num">{_fmt_pct(m['p1'])}</td>
          <td class="num">{_fmt_pct(m['p7'])}</td>
          <td class="num">{_fmt_pct(m['p30'])}</td>
          <td class="num">{_fmt_pct(m['p365'], 0)}</td>
          <td class="trend-cell"><span class="pill {tone}"><b></b>{label}</span><span class="dots" aria-label="{m['trend']} moyennes sur 3 sous le prix">{dots}</span></td>
          <td class="num"><span class="pill sm {rsi_tone}"><b></b>{m['rsi']:.0f} · {rsi_label(m['rsi'])}</span></td>
          <td class="num">±{_num(m['vol_day'], 1)} %/j</td>
          <td class="num">{_fmt_pct(m['drawdown'], 0)}</td>
        </tr>
        <tr class="comment"><td colspan="10">{e(asset_comment(m))}</td></tr>""")

    alloc = []
    for p, w in strategy["today"].items():
        alloc.append((p.split("-")[0], w * 100))
    alloc.append(("Euros", strategy["cash_pct"]))
    alloc_bar = "".join(
        f'<span class="seg s{i + 1 if label != "Euros" else 0}" style="flex-grow:{max(v, 0.0001):.2f}" title="{e(label)} {v:.0f} %"></span>'
        for i, (label, v) in enumerate(alloc) if v > 0.5
    )
    alloc_legend = "".join(
        f'<li><i class="s{i + 1 if label != "Euros" else 0}"></i>{e(label)} <strong>{v:.0f} %</strong></li>'
        for i, (label, v) in enumerate(alloc)
    )

    bt_rows = []
    for r in strategy["table"]:
        s, h = r["strat"], r["hold"]
        better = s["sharpe"] > h["sharpe"]
        bt_rows.append(f"""
        <tr>
          <th scope="row">{e(r['period'])}<span class="nm">{r['from']} → {r['to']}</span></th>
          <td class="num">{_fmt_pct(s['rendement_annuel_pct'])}</td><td class="num">{_fmt_pct(h['rendement_annuel_pct'])}</td>
          <td class="num">{_fmt_pct(s['drawdown_max_pct'], 0)}</td><td class="num">{_fmt_pct(h['drawdown_max_pct'], 0)}</td>
          <td class="num">{_num(s['sharpe'])}</td><td class="num">{_num(h['sharpe'])}</td>
          <td><span class="pill {'good' if better else 'serious'}"><b></b>{'Meilleur rapport gain/risque' if better else 'Moins bon'}</span></td>
        </tr>""")

    test = next((r for r in strategy["table"] if r["period"].startswith("Test")), None)
    if test:
        headline = (f"Sur la période de test, la stratégie a fait {test['strat']['rendement_annuel_pct']:+.0f} % par an "
                    f"avec une pire chute de {test['strat']['drawdown_max_pct']:.0f} %, contre "
                    f"{test['hold']['rendement_annuel_pct']:+.0f} % par an et {test['hold']['drawdown_max_pct']:.0f} % "
                    f"pour « acheter et garder ».")
    else:
        headline = ""

    top = metrics[0]
    worst = metrics[-1]
    generated_txt = generated.strftime("%d/%m/%Y à %H:%M UTC")
    data_json = json.dumps(payload, separators=(",", ":"))
    products_txt = " + ".join(p.split("-")[0] for p in strategy["products"])

    here = Path(__file__).parent
    template = string.Template((here / "report_template.html").read_text(encoding="utf-8"))
    script = (here / "report_charts.js").read_text(encoding="utf-8")
    return template.substitute(
        generated=generated_txt,
        verdict=e(summary["verdict"]), tone=summary["tone"], summary=e(summary["text"]),
        breadth=summary["breadth"], n=summary["n"],
        btc_price=_fmt_price(next(m for m in metrics if m["symbol"] == "BTC")["price"]),
        btc_p30=_fmt_pct(next(m for m in metrics if m["symbol"] == "BTC")["p30"]),
        top_label="Meilleure sur 30 jours" if (top["p30"] or 0) > 0 else "La moins en baisse sur 30 jours",
        top_sym=e(top["symbol"]), top_p30=_fmt_pct(top["p30"]),
        worst_sym=e(worst["symbol"]), worst_p30=_fmt_pct(worst["p30"]),
        rows="".join(rows), alloc_bar=alloc_bar, alloc_legend=alloc_legend,
        decided_on=strategy["decided_on"], products=e(products_txt),
        bt_rows="".join(bt_rows), headline=e(headline), fee=_num(strategy["fee"], 1),
        data=data_json, script=script,
    )

