"""Données de marché Coinbase (endpoints publics, aucune clé nécessaire)."""
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.coinbase.com/api/v3/brokerage"

GRANULARITY_SECONDS = {
    "ONE_MINUTE": 60,
    "FIVE_MINUTE": 300,
    "FIFTEEN_MINUTE": 900,
    "THIRTY_MINUTE": 1800,
    "ONE_HOUR": 3600,
    "TWO_HOUR": 7200,
    "SIX_HOUR": 21600,
    "ONE_DAY": 86400,
}
MAX_CANDLES_PER_REQUEST = 350

_session = requests.Session()


def _get(path: str, params: dict | None = None, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            resp = _session.get(f"{BASE_URL}{path}", params=params, timeout=15)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt == retries - 1 or (status is not None and 400 <= status < 500 and status != 429):
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def get_price(product_id: str) -> float:
    return float(_get(f"/market/products/{product_id}")["price"])


def get_product(product_id: str) -> dict:
    return _get(f"/market/products/{product_id}")


def fetch_candles(product_id: str, granularity: str, start: int, end: int) -> pd.DataFrame:
    """Bougies entre ``start`` et ``end`` (timestamps UNIX, secondes)."""
    step = GRANULARITY_SECONDS[granularity]
    rows = []
    cursor = end
    while cursor > start:
        chunk_start = max(start, cursor - step * MAX_CANDLES_PER_REQUEST)
        data = _get(
            f"/market/products/{product_id}/candles",
            {"start": str(chunk_start), "end": str(cursor), "granularity": granularity},
        )
        rows.extend(data.get("candles", []))
        cursor = chunk_start
        time.sleep(0.15)  # rester sous les limites de débit
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["start"].astype(int), unit="s", utc=True)
    df = df.drop(columns="start").astype({c: float for c in ["open", "high", "low", "close", "volume"]})
    return df.drop_duplicates("time").sort_values("time").set_index("time")[["open", "high", "low", "close", "volume"]]


def recent_closed_candles(product_id: str, granularity: str, count: int) -> pd.DataFrame:
    """Les ``count`` dernières bougies CLÔTURÉES (la bougie en cours est retirée)."""
    step = GRANULARITY_SECONDS[granularity]
    now = int(time.time())
    df = fetch_candles(product_id, granularity, now - step * (count + 2), now)
    if not df.empty:
        last_start = int(df.index[-1].timestamp())
        if last_start + step > now:
            df = df.iloc[:-1]
    return df.tail(count)


def history(product_id: str, granularity: str, days: int, cache_dir: str | Path = "data/cache") -> pd.DataFrame:
    """Historique pour le backtest, mis en cache sur disque."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{product_id}_{granularity}_{days}d_{time.strftime('%Y%m%d')}.csv"
    if path.exists():
        return pd.read_csv(path, index_col="time", parse_dates=["time"])
    now = int(time.time())
    df = fetch_candles(product_id, granularity, now - days * 86400, now)
    df.to_csv(path)
    return df
