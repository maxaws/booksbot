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


def fresh_hourly(product: str, hours: int = 48) -> pd.DataFrame:
    now = int(time.time())
    return data.fetch_candles(product, "ONE_HOUR", now - hours * 3600, now)


def recent_crosses(close: pd.Series, days: int = 10) -> list[dict]:
    """Franchissements de moyennes mobiles (en clôture) sur les ``days`` derniers jours clôturés."""
    out = []
    closed = close.iloc[:-1]  # la dernière bougie est la journée en cours
    for n in SMAS:
        if len(closed) < n + days:
            continue
        above = closed > ind.sma(closed, n)
        change = above.ne(above.shift(1)) & above.shift(1).notna()
        recent = change.tail(days)
        if recent.any():
            when = recent[recent].index[-1]
            out.append({"sma": n, "up": bool(above.loc[when]), "date": when})
    return out


def asset_metrics(product: str, df: pd.DataFrame, hourly: pd.DataFrame | None = None) -> dict:
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
    vol = df["volume"]
    vol_ratio = float(vol.iloc[-2] / vol.iloc[-32:-2].mean()) if len(vol) > 32 else None
    h24 = h48 = range24 = None
    if hourly is not None and len(hourly) >= 25:
        hc = hourly["close"]
        h24 = (price / float(hc.iloc[-25]) - 1) * 100
        h48 = (price / float(hc.iloc[0]) - 1) * 100
        last = hourly.tail(24)
        range24 = (float(last["high"].max()) / float(last["low"].min()) - 1) * 100
    return {
        "p24h": h24, "p48h": h48, "range24": range24, "vol_ratio": vol_ratio,
        "crosses": recent_crosses(close),
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


def market_events(metrics: list[dict]) -> list[dict]:
    """Ce qui se passe en ce moment, du plus important au moins important.

    Chaque événement : {"tone": good|warning|serious|critical|neutral, "title", "text", "rank"}.
    """
    ev = []
    n = len(metrics)
    fr = lambda v, d=1: f"{v:+.{d}f}".replace(".", ",")  # noqa: E731

    # 1) Mouvement d'ensemble sur 48 h et 7 jours
    m48 = [m["p48h"] for m in metrics if m["p48h"] is not None]
    if m48:
        down48 = sum(1 for v in m48 if v < -2)
        up48 = sum(1 for v in m48 if v > 2)
        avg48 = float(np.mean(m48))
        if down48 >= 0.7 * len(m48):
            ev.append({"tone": "critical" if avg48 < -5 else "serious", "rank": 0,
                       "title": f"Baisse généralisée : {fr(avg48)} % en 48 h",
                       "text": f"{down48} cryptos sur {len(m48)} ont perdu plus de 2 % en 48 heures. "
                               "Quand tout baisse en même temps, c'est le marché entier qui recule, pas un actif en particulier."})
        elif up48 >= 0.7 * len(m48):
            ev.append({"tone": "good", "rank": 0, "title": f"Hausse généralisée : {fr(avg48)} % en 48 h",
                       "text": f"{up48} cryptos sur {len(m48)} ont gagné plus de 2 % en 48 heures."})
    m30 = [m["p30"] for m in metrics if m["p30"] is not None]
    down30 = sum(1 for v in m30 if v < 0)
    if m30 and down30 == len(m30):
        worst = min(metrics, key=lambda m: m["p30"] or 0)
        ev.append({"tone": "serious", "rank": 1, "title": "Toutes les cryptos en baisse sur un mois",
                   "text": f"Moyenne {fr(float(np.mean(m30)), 0)} % sur 30 jours ; la plus touchée est "
                           f"{worst['name']} ({fr(worst['p30'], 0)} %). Les petites cryptos baissent plus que le bitcoin, "
                           "c'est typique des phases de prudence : l'argent se replie sur les actifs les plus solides."})

    # 2) Volumes inhabituels : un mouvement avec du volume est plus « sérieux »
    spikes = sorted((m for m in metrics if m["vol_ratio"] and m["vol_ratio"] >= 1.8), key=lambda m: -m["vol_ratio"])
    if spikes:
        names = ", ".join(f"{m['symbol']} ({m['vol_ratio']:.1f}×)".replace(".", ",") for m in spikes[:5])
        ev.append({"tone": "warning", "rank": 2, "title": "Volumes d'échange élevés hier",
                   "text": f"{names} la normale du mois. Beaucoup d'échanges pendant une baisse signifie que des "
                           "vendeurs sont réellement actifs : le mouvement a plus de poids qu'une baisse dans le calme."})

    # 3) Agitation dans la journée
    wild = [m for m in metrics if m["range24"] and m["vol_day"] and m["range24"] > 2.5 * m["vol_day"]]
    if len(wild) >= 3:
        btc = next((m for m in metrics if m["symbol"] == "BTC"), None)
        extra = ""
        if btc and btc["range24"]:
            extra = f" Le bitcoin a oscillé de {btc['range24']:.1f} % entre son plus haut et son plus bas.".replace(".", ",", 1)
        ev.append({"tone": "warning", "rank": 3, "title": "Journée très agitée",
                   "text": f"{len(wild)} cryptos ont eu un écart plus haut / plus bas sur 24 h bien supérieur à leur "
                           f"variation habituelle.{extra}"})

    # 4) Franchissements récents de moyennes (changements de tendance), regroupés
    groups: dict[tuple[bool, int], list[str]] = {}
    for m in metrics:
        for c in m["crosses"]:
            groups.setdefault((c["up"], c["sma"]), []).append(m["symbol"])
    for up in (False, True):
        lines = [f"{'Au-dessus' if up else 'Sous'} la moyenne {n} jours : {', '.join(syms)}."
                 for (u, n), syms in sorted(groups.items(), key=lambda kv: -kv[0][1]) if u == up]
        if not lines:
            continue
        count = sum(len(v) for (u, _), v in groups.items() if u == up)
        ev.append({
            "tone": "good" if up else "serious", "rank": 4,
            "title": f"{count} {'franchissements à la hausse' if up else 'cassures de tendance'} sur 10 jours",
            "text": " ".join(lines) + (
                " Repasser au-dessus d'une moyenne signale une amélioration." if up else
                " Passer sous la moyenne 200 jours, c'est perdre la tendance de fond ; sous la 50 jours, "
                "c'est une alerte de court terme."),
        })

    # 5) RSI proche des extrêmes
    low = [m for m in metrics if m["rsi"] <= 35]
    if low:
        names = ", ".join(f"{m['symbol']} ({m['rsi']:.0f})" for m in sorted(low, key=lambda m: m["rsi"]))
        ev.append({"tone": "neutral", "rank": 6, "title": "Proches de la zone de survente",
                   "text": f"RSI de {names}. Sous 30, la baisse est jugée excessive à court terme : un rebond technique "
                           "devient plus probable, mais une baisse peut durer longtemps en survente."})
    high = [m for m in metrics if m["rsi"] >= 65]
    if high:
        names = ", ".join(f"{m['symbol']} ({m['rsi']:.0f})" for m in sorted(high, key=lambda m: -m["rsi"]))
        ev.append({"tone": "neutral", "rank": 6, "title": "Proches de la surchauffe",
                   "text": f"RSI de {names}. Au-dessus de 70, la hausse est jugée excessive à court terme."})

    if not ev:
        ev.append({"tone": "neutral", "rank": 9, "title": "Marché calme",
                   "text": "Pas de mouvement d'ensemble, pas de volume inhabituel ni de changement de tendance récent."})
    return sorted(ev, key=lambda e: e["rank"])


def robot_events(strategy: dict, levels: list[dict]) -> list[dict]:
    """Ce que le robot vient de faire, et ce qu'il fera ce soir si les prix restent là."""
    ev = []
    moves = []
    for p, w in strategy["today"].items():
        before = strategy["yesterday"].get(p, 0.0)
        if abs(w - before) > 1e-6:
            moves.append(f"{p.split('-')[0]} {before:.0%} → {w:.0%}".replace("%", " %"))
    if moves:
        ev.append({"tone": "warning", "rank": -1, "title": "Le robot a changé sa répartition",
                   "text": f"À la clôture du {strategy['decided_on']} : {', '.join(moves)}. "
                           "Il a réduit son exposition parce que les prix sont passés sous une de leurs moyennes."
                   if sum(strategy["today"].values()) < sum(strategy["yesterday"].values()) else
                   f"À la clôture du {strategy['decided_on']} : {', '.join(moves)}."})
    for lv in levels:
        if lv["sell"] and lv["sell"]["dist"] > 0:
            ev.append({"tone": "critical", "rank": -1,
                       "title": f"{lv['symbol']} est sous son seuil de vente",
                       "text": f"Prix actuel {_fmt_price(lv['price'])}, seuil {_fmt_price(lv['sell']['level'])}. "
                               f"Si la clôture de ce soir (minuit UTC) reste en dessous, le robot réduira "
                               f"{lv['symbol']} de {lv['now_pct']:.0f} % à {lv['after_sell_pct']:.0f} % du capital."})
        if lv["buy"] and lv["buy"]["dist"] < 0:
            ev.append({"tone": "good", "rank": -1,
                       "title": f"{lv['symbol']} est au-dessus de son seuil d'achat",
                       "text": f"Prix actuel {_fmt_price(lv['price'])}, seuil {_fmt_price(lv['buy']['level'])}. "
                               f"Si la clôture de ce soir reste au-dessus, le robot augmentera {lv['symbol']} "
                               f"de {lv['now_pct']:.0f} % à {lv['after_buy_pct']:.0f} % du capital."})
    return ev


def robot_levels(cfg: Config, closes: pd.DataFrame) -> list[dict]:
    """Prix de clôture qui feraient changer d'avis la stratégie trend_ensemble.

    Approximatif : les moyennes bougent un peu chaque jour.
    """
    if cfg.strategy != "trend_ensemble":
        return []
    from .portfolio import trend_states

    smas = tuple(cfg.strategy_params.get("smas", SMAS))
    buf = float(cfg.strategy_params.get("buffer_pct", 2.0))
    closed = closes.iloc[:-1]
    states = trend_states(closed, smas, buf)
    out = []
    for p in closes.columns:
        price = float(closes[p].iloc[-1])
        below, above = [], []
        for n, (state, ma) in states.items():
            m = float(ma[p].iloc[-1])
            if np.isnan(m):
                continue
            if state[p].iloc[-1] == 1:
                below.append((m * (1 - buf / 100), n))
            else:
                above.append((m * (1 + buf / 100), n))
        sell = max(below) if below else None
        buy = min(above) if above else None
        out.append({
            "symbol": p.split("-")[0], "price": price,
            "sell": None if sell is None else {"level": sell[0], "sma": sell[1], "dist": (sell[0] / price - 1) * 100},
            "buy": None if buy is None else {"level": buy[0], "sma": buy[1], "dist": (buy[0] / price - 1) * 100},
        })
        k, total = sum(float(state[p].iloc[-1]) for state, _ in states.values()), len(states)
        share = lambda x: round(x / total * 4) / 4 / len(closes.columns) * 100  # noqa: E731  (même arrondi que la stratégie)
        out[-1].update(now_pct=share(k), after_sell_pct=share(max(k - 1, 0)), after_buy_pct=share(min(k + 1, total)))
    return out


# --- Stratégie -----------------------------------------------------------------
def strategy_section(cfg: Config, closes: pd.DataFrame) -> dict:
    name = cfg.strategy if cfg.strategy in PORTFOLIO_STRATEGIES else "trend_ensemble"
    params = cfg.strategy_params if cfg.strategy in PORTFOLIO_STRATEGIES else {}
    fn = PORTFOLIO_STRATEGIES[name]
    closed = closes.iloc[:-1]  # le robot ne décide que sur des journées clôturées
    weights = fn(closed, **params)
    today = weights.iloc[-1].to_dict()
    yesterday = weights.iloc[-2].to_dict() if len(weights) > 1 else today
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
        "name": name, "products": list(closed.columns), "today": today, "yesterday": yesterday,
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
    hourly = {p: fresh_hourly(p, 48) for p in universe}
    metrics = [asset_metrics(p, df, hourly[p]) for p, df in frames.items() if len(df) > 30]
    events = market_events(metrics)
    metrics.sort(key=lambda m: -(m["p30"] or -1e9))
    summary = market_summary(metrics)

    strat_products = cfg.products if all(p.endswith("-EUR") for p in cfg.products) else ["BTC-EUR", "ETH-EUR"]
    long = pd.DataFrame({p: fresh_daily(p, 2400)["close"] for p in strat_products}).sort_index()
    strategy = strategy_section(cfg, long)
    levels = robot_levels(cfg, long)
    events = robot_events(strategy, levels) + events

    btc = frames["BTC-EUR"].tail(365 + 200)
    c = btc["close"]
    chart_btc = {
        "dates": [d.strftime("%Y-%m-%d") for d in c.index[-365:]],
        "price": [round(v, 0) for v in c.tail(365)],
        **{f"sma{n}": [None if pd.isna(v) else round(v, 0) for v in ind.sma(c, n).tail(365)] for n in SMAS},
    }
    payload = {"btc": chart_btc, "strategy": strategy["series"]}
    page = render(generated, metrics, summary, strategy, payload, events, levels)
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


def render(generated, metrics, summary, strategy, payload, events=(), levels=()) -> str:
    e = html.escape
    event_items = "".join(
        f'<li class="ev {ev["tone"]}"><span class="pill {ev["tone"]}"><b></b>{e(ev["title"])}</span>'
        f'<p>{e(ev["text"])}</p></li>' for ev in events
    )
    level_rows = []
    for lv in levels:
        def cell(x, verb, crossed):
            if x is None:
                return '<td class="na">—</td>'
            flag = ' <span class="pill sm critical"><b></b>prix déjà au-delà</span>' if crossed else ""
            return (f'<td><span class="num">{_fmt_price(x["level"])}</span> <span class="muted">'
                    f'({_fmt_pct(x["dist"])} · moyenne {x["sma"]} j)</span>{flag}<br><span class="muted">{verb}</span></td>')
        level_rows.append(
            f'<tr><th scope="row">{e(lv["symbol"])}<span class="nm">{_fmt_price(lv["price"])}</span></th>'
            + cell(lv["sell"], f"clôture en dessous : {lv['now_pct']:.0f} % → {lv['after_sell_pct']:.0f} % du capital",
                   bool(lv["sell"] and lv["sell"]["dist"] > 0))
            + cell(lv["buy"], f"clôture au-dessus : {lv['now_pct']:.0f} % → {lv['after_buy_pct']:.0f} % du capital",
                   bool(lv["buy"] and lv["buy"]["dist"] < 0))
            + "</tr>")
    levels_html = "" if not level_rows else (
        '<h3>Niveaux à surveiller</h3><div class="table-scroll"><table class="bt"><thead><tr>'
        '<th scope="col">Crypto</th><th scope="col">Prochain seuil de vente</th><th scope="col">Prochain seuil d\'achat</th>'
        "</tr></thead><tbody>" + "".join(level_rows) + "</tbody></table></div>"
        '<p class="muted">Seuils approximatifs, en clôture journalière (minuit UTC) : les moyennes bougent un peu chaque jour. '
        "Tant que le prix reste entre les deux, le robot ne fait rien, même si le marché s'agite.</p>")
    rows = []
    for m in metrics:
        label, tone = trend_label(m["trend"])
        dots = "".join(f'<i class="{"on" if m["sma"][n] and m["price"] > m["sma"][n] else ""}" title="Moyenne {n} jours"></i>' for n in SMAS)
        rsi_tone = {"surchauffe": "warning", "survendu": "serious", "neutre": "neutral"}[rsi_label(m["rsi"])]
        rows.append(f"""
        <tr>
          <th scope="row"><span class="sym">{e(m['symbol'])}</span><span class="nm">{e(m['name'])}</span></th>
          <td class="num">{_fmt_price(m['price'])}</td>
          <td class="num">{_fmt_pct(m['p24h'] if m['p24h'] is not None else m['p1'])}</td>
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
        events=event_items, levels=levels_html,
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

