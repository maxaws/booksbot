# Robot de trading court terme (Coinbase)

Robot de trading automatique pour la crypto sur **Coinbase Advanced Trade**, avec :

- **backtest réaliste** (frais, slippage, exécution à la bougie suivante, stops intra-bougie) ;
- **mode simulé (paper)** : vrais prix Coinbase, argent fictif ;
- **mode réel (live)** protégé par une triple confirmation ;
- **gestion du risque** : taille de position selon le risque, stop-loss / take-profit
  ATR, limite de perte journalière, coupe-circuit sur drawdown ;
- **budget plafonné** : le robot n'utilise jamais plus que `capital` et ne vend
  que ce qu'il a lui-même acheté (tes avoirs existants ne sont pas touchés) ;
- journal CSV de tous les trades et état persistant (reprise après redémarrage).

> ⚠️ **À lire avant tout** : voir la section [Résultats et avertissements](#résultats-et-avertissements).
> Les stratégies intraday (minutes, heures) perdent de l'argent en backtest à cause des frais.
> La stratégie recommandée, `trend_ensemble`, décide une fois par jour. Sur la période de test,
> elle a gagné autant ou plus que garder ses cryptos, avec des chutes environ moitié moins fortes.
> Elle ne rend pas riche rapidement, et elle a quand même connu des baisses de 30 à 50 %.

## Installation

```bash
cd tradingbot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

## Utilisation, étape par étape

### 0. Rapport de marché (aucune clé nécessaire)

```bash
python -m tradingbot report         # -> data/rapport.html, à ouvrir dans le navigateur
```

Données Coinbase à jour, expliquées en français :
- l'état du marché ;
- chaque crypto : performances, tendance, RSI, agitation, chute depuis le plus haut ;
- la répartition que viserait le robot aujourd'hui ;
- la preuve par backtest, avec graphiques et lexique.

Relance-le quand tu veux pour l'actualiser.

### 1. Backtester (aucune clé nécessaire)

```bash
python -m tradingbot backtest --days 2400                    # stratégie de config.yaml
python -m tradingbot backtest --product BTC-EUR --days 2400
```

Compare toujours le rendement à la ligne **buy&hold** (acheter et garder) : une
stratégie qui fait moins bien que ça n'a pas d'intérêt.

### 2. Mode simulé (plusieurs semaines)

```bash
python -m tradingbot run            # tourne en continu (Ctrl+C pour arrêter)
python -m tradingbot status         # état : cash, positions, P&L
```

Les trades fictifs sont enregistrés dans `data/trades.csv`, les logs dans `data/bot.log`.

### 3. Mode réel (petites sommes)

1. Crée une clé API sur <https://portal.cdp.coinbase.com/> :
   - permissions **View** et **Trade** uniquement, **jamais Transfer** ;
   - restreinte à ton adresse IP si possible.
2. `cp .env.example .env` et colle la clé (le fichier `.env` n'est jamais commité).
3. `python -m tradingbot check-keys` pour vérifier la connexion.
4. Dans `config.yaml` : `mode: live` et un `capital` que tu acceptes de perdre.
5. Efface l'état du mode simulé : `python -m tradingbot reset --all`.
6. `python -m tradingbot run --live` puis tape `OUI`.

Le robot doit tourner en continu pour surveiller les stops (un petit serveur
ou un Raspberry Pi suffit). **S'il est arrêté, les stops ne sont plus surveillés.**

### Coupe-circuit

Si le capital recule de `max_drawdown_pct` depuis son plus haut, le robot vend
tout et s'arrête. Analyse ce qui s'est passé, puis `python -m tradingbot reset`.

## Configuration

Tout se règle dans `config.yaml` (commenté). Les points clés :

| Paramètre | Rôle |
|---|---|
| `products` | paires Coinbase, même devise (ex. `BTC-EUR`, `ETH-EUR`) |
| `granularity` | taille des bougies (`FIFTEEN_MINUTE`, `ONE_HOUR`, `SIX_HOUR`...) |
| `strategy` | `trend_ensemble` (recommandée), `trend_filter`, `momentum_rotation`, `ema_cross`, `mean_reversion` |
| `capital` | budget max utilisé par le robot |
| `risk.risk_per_trade_pct` | perte si le stop est touché, en % du capital |
| `fee_pct` | frais taker de **ton** palier Coinbase (à vérifier dans ton compte) |

## Structure

```
tradingbot/
  indicators.py     EMA, RSI, ATR, Bollinger
  strategies.py     stratégies (mêmes signaux en backtest et en live)
  risk.py           taille de position, limites, coupe-circuit
  backtest.py       simulateur (stratégies intraday)
  portfolio.py      stratégies journalières de portefeuille + leur backtest
  report.py         rapport de marché HTML (+ report_template.html, report_charts.js)
  bot.py            boucle de trading + registre persistant
  data.py           données de marché Coinbase (publiques)
  brokers/          paper (simulé), coinbase (réel)
tests/              tests automatiques (pytest)
```

Pour ajouter une stratégie : une classe dans `strategies.py` qui renvoie les
colonnes `entry`, `exit`, `stop_dist`, `tp_dist`, puis l'ajouter à `STRATEGIES`.

## Résultats et avertissements

### Stratégie recommandée : `trend_ensemble`

La stratégie suit la tendance de façon progressive. Pour chaque crypto, la part investie dépend
du nombre de moyennes mobiles (50, 100 et 200 jours) que le prix dépasse : 0, un tiers, deux tiers
ou la totalité. Une marge de 2 % évite les allers-retours inutiles. Le robot décide une fois par
jour, après la clôture de minuit UTC.

Méthode : les réglages ont été choisis sur la période 2020-2023, puis vérifiés sur 2024-2026,
une période que la stratégie n'avait jamais vue. Frais de 1,2 % par ordre inclus.

| BTC + ETH | Gain / an | Pire chute | Sharpe |
|---|---|---|---|
| Stratégie, période de test (2024-2026) | +19 % | −33 % | 0,70 |
| Acheter et garder, même période | +13 % | −59 % | 0,50 |
| Stratégie, 2020-2026 | +43 % | −49 % | 1,07 |
| Acheter et garder, 2020-2026 | +40 % | −73 % | 0,86 |

Ce qui n'a **pas** tenu : la rotation vers les cryptos qui ont le plus monté (`momentum_rotation`).
Elle était excellente sur 2021-2023, puis a perdu de 20 à 70 % sur 2024-2026. C'est le signe d'un
réglage trop ajusté au passé.

### Stratégies intraday

Backtests réalisés le 29/10/2026 sur données Coinbase réelles, 100 € de capital,
rendement total sur la période selon le niveau de frais par ordre :

| Paire / bougies | Stratégie | Frais 1,2 % | Frais 0,6 % | Frais 0,25 % | Sans frais | Buy & hold |
|---|---|---|---|---|---|---|
| BTC-EUR 15 min (120 j) | ema_cross | −87 % | −66 % | −40 % | −10 % | +29 % |
| BTC-EUR 1 h (365 j) | ema_cross | −65 % | −40 % | −18 % | +3 % | −18 % |
| BTC-EUR 1 h (365 j) | mean_reversion | −8 % | −4 % | −1 % | 0 % | −18 % |
| ETH-EUR 1 h (365 j) | ema_cross | −66 % | −42 % | −20 % | 0 % | −27 % |
| ETH-EUR 6 h (365 j) | ema lente, stop 4×ATR | 0 % | +2 % | +2 % | +3 % | −20 % |

Ce qu'il faut en retenir :

1. **Les frais sont le problème n°1.** Sur les petits volumes, Coinbase Advanced
   facture de l'ordre de 0,6 % (maker) à 1,2 % (taker) par ordre : un aller-retour
   coûte jusqu'à 2,4 %. Le trading très court terme (minutes) y est perdant presque
   par construction. Vérifie ton palier réel dans Coinbase.
2. **Ces stratégies classiques n'ont pas d'avantage** : même sans frais, elles
   tournent autour de 0 %. Elles servent de point de départ pour expérimenter.
3. **Méfie-toi de l'optimisation** : en essayant beaucoup de réglages, on finit
   toujours par trouver un réglage gagnant sur le passé, par pur hasard. Valide
   sur une période différente, puis en paper trading.
4. **Faire grossir un petit capital par le trading court terme est très
   difficile** ; la grande majorité des traders particuliers perdent de l'argent.
   N'engage que des sommes que tu peux perdre entièrement.

Pistes pour améliorer les chances :
- trader moins souvent, sur des bougies plus longues (≥ 4 h) ;
- utiliser des ordres limite « post-only » (frais maker, environ deux fois moins
  chers) : non implémenté pour l'instant ;
- choisir une plateforme aux frais plus bas pour le court terme.

### Actions et ETF

Coinbase ne propose pas d'actions en France. Le robot est conçu pour accueillir
d'autres courtiers (`brokers/base.py`) ; pour un résident français, Interactive
Brokers (API complète, frais faibles) est l'option la plus courante. À noter :
le PEA, fiscalement avantageux, n'est en général pas accessible par API.

### Fiscalité (France, à vérifier)

Les plus-values sur crypto sont imposables lors de la conversion en euros
(prélèvement forfaitaire de 30 % pour un particulier) et un compte détenu sur
une plateforme étrangère se déclare (formulaire 3916-bis). Le journal
`data/trades.csv` facilite la déclaration. Renseigne-toi sur impots.gouv.fr
ou auprès d'un conseiller.

*Ce logiciel est fourni à titre éducatif. Ce n'est pas un conseil en investissement.*
