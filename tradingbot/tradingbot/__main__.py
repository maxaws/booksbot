"""Point d'entrée : python -m tradingbot <commande>"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import data
from .backtest import run_backtest
from .config import load_config, load_dotenv
from .risk import RiskManager
from .strategies import build_strategy


def cmd_backtest(cfg, args):
    strategy = build_strategy(cfg.strategy, cfg.strategy_params)
    products = [args.product] if args.product else cfg.products
    for product in products:
        df = data.history(product, cfg.granularity, args.days)
        res = run_backtest(df, strategy, RiskManager(cfg.risk), product, cfg.capital, cfg.fee_pct, cfg.slippage_pct)
        print(res.summary())
        if args.trades:
            for t in res.trades:
                print(f"  {t.entry_time:%m-%d %H:%M} -> {t.exit_time:%m-%d %H:%M}  "
                      f"{t.entry_price:>10.2f} -> {t.exit_price:>10.2f}  {t.pnl:+7.2f}  {t.reason}")
        print()


def make_broker(cfg, live: bool):
    if cfg.mode == "live" or live:
        if not (cfg.mode == "live" and live):
            sys.exit("Le trading réel exige À LA FOIS `mode: live` dans config.yaml ET l'option --live.")
        from .brokers.coinbase import CoinbaseBroker
        return CoinbaseBroker(os.environ.get("COINBASE_API_KEY", ""), os.environ.get("COINBASE_API_SECRET", ""))
    from .brokers.paper import PaperBroker
    return PaperBroker(cfg.fee_pct, cfg.slippage_pct)


def cmd_run(cfg, args):
    from .bot import TradingBot
    broker = make_broker(cfg, args.live)
    if cfg.mode == "live":
        available = broker.available_quote(cfg.quote_currency)
        print(f"\n*** MODE RÉEL *** Solde {cfg.quote_currency} disponible : {available:.2f}. "
              f"Budget du robot : {cfg.capital:.2f}.")
        if input("Tape OUI pour lancer le trading avec de l'argent réel : ").strip() != "OUI":
            sys.exit("Annulé.")
    bot = TradingBot(cfg, broker)
    if args.once:
        bot.step()
    else:
        bot.run()


def cmd_status(cfg, args):
    path = Path(cfg.state_file)
    if not path.exists():
        print("Aucun état enregistré (le robot n'a pas encore tourné).")
        return
    print(json.dumps(json.loads(path.read_text()), indent=2, ensure_ascii=False))


def cmd_reset(cfg, args):
    path = Path(cfg.state_file)
    if not path.exists():
        print("Rien à réinitialiser.")
        return
    state = json.loads(path.read_text())
    if args.all:
        if state.get("positions"):
            sys.exit("Des positions sont encore ouvertes : impossible de tout effacer.")
        path.unlink()
        print("État effacé : le robot repartira avec le capital de config.yaml.")
        return
    state.update(halted=False, halt_reason="")
    # Le plus haut repart du capital actuel, sinon le coupe-circuit se redéclencherait aussitôt
    state["peak_equity"] = state["cash"] + sum(p["cost"] for p in state.get("positions", {}).values())
    path.write_text(json.dumps(state, indent=2))
    print("Coupe-circuit réarmé.")


def cmd_check_keys(cfg, args):
    from .brokers.coinbase import CoinbaseBroker
    broker = CoinbaseBroker(os.environ.get("COINBASE_API_KEY", ""), os.environ.get("COINBASE_API_SECRET", ""))
    accounts = [a for a in broker.accounts() if float(a["available_balance"]["value"]) > 0]
    print("Connexion OK. Soldes non nuls :")
    for a in accounts:
        print(f"  {a['currency']:>6} : {a['available_balance']['value']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="tradingbot", description="Robot de trading court terme (Coinbase)")
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", help="tester la stratégie sur l'historique")
    b.add_argument("--product")
    b.add_argument("--days", type=int, default=90)
    b.add_argument("--trades", action="store_true", help="afficher le détail des trades")
    b.set_defaults(func=cmd_backtest)

    r = sub.add_parser("run", help="lancer le robot (paper par défaut)")
    r.add_argument("--live", action="store_true", help="trading réel (exige aussi mode: live)")
    r.add_argument("--once", action="store_true", help="un seul cycle puis arrêt")
    r.set_defaults(func=cmd_run)

    sub.add_parser("status", help="afficher l'état du robot").set_defaults(func=cmd_status)
    rs = sub.add_parser("reset", help="réarmer le coupe-circuit")
    rs.add_argument("--all", action="store_true", help="effacer tout l'état (repartir de zéro)")
    rs.set_defaults(func=cmd_reset)
    sub.add_parser("check-keys", help="vérifier les clés API Coinbase").set_defaults(func=cmd_check_keys)

    args = p.parse_args(argv)
    Path("data").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler("data/bot.log")])
    load_dotenv()
    cfg = load_config(args.config)
    args.func(cfg, args)


if __name__ == "__main__":
    main()
