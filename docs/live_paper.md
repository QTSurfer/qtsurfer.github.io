# Paper trading on live runs

Start a [live run](live.md) with a `paper` block and its hints are executed in simulation from its
first tick, exactly as a backtest would execute them: orders fill, positions open and close, and the
run accumulates equity and the same KPIs a backtest reports. Nothing is sent to an exchange. Without
the block, the run has no paper trading.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/strategy/{strategyId}/live` | Start a run — with a `paper` block to paper-trade it |
| `GET` | `/live/{runId}/paper` | Each paper account: equity, open positions, KPIs |
| `GET` | `/live/{runId}/paper/equity` | Page through the equity curve |
| `GET` | `/live/{runId}/signals?type=paper` | Paper items interleaved in the run's signals (`output: mix` only) |

Both paper routes follow the same access rule as a run's signals: the run's owner, or anyone if the
run is `public`. A run started without a `paper` block answers `404` on both.

## Starting a run with paper trading

```
POST /v1/strategy/6bsh31ikwkuivhtgcoa6s4/live
{
  "sources": [{"venueType": "cx", "exchange": "binance", "segment": "spot", "type": "ticker",
               "instruments": ["BTC/USDT", "ETH/USDT"]}],
  "paper": {"initialFunding": 1000, "feeRate": 0.001, "percentAmountToLock": 20}
}

201
{
  "strategyId": "6bsh31ikwkuivhtgcoa6s4",
  "runId": "6TzAPiPpsOWwBLdLBZCxwH",
  "stage": "SANDBOX",
  "state": "STARTING",
  …
  "paper": {"initialFunding": 1000.0, "buyFeeRate": 0.001, "sellFeeRate": 0.001, "feeLeg": "RECEIVED",
            "percentAmountToLock": 20.0, "output": "separate"}
}
```

The block takes the same economics as a backtest's `baseConfig`, with the same defaults and limits,
so one object moves between a backtest and a live run unchanged:

| field | default | meaning |
|---|---|---|
| `initialFunding` | `100` | Starting capital of each account, in that account's quote currency. At most 1,000,000,000. |
| `feeRate` | `0.001` | Fee rate for both sides (0.001 = 0.1%). |
| `buyFeeRate` / `sellFeeRate` | `feeRate` | Per-side rates; override `feeRate`. |
| `feeLeg` | `RECEIVED` | Which asset fees are charged in: `RECEIVED`, `QUOTE` or `BASE`. |
| `percentAmountToLock` | see below | Share of the account's free balance each entry locks, in percent (0–100]. |
| `output` | `separate` | `separate`, or `mix` to also write paper items into the run's signals (see [below](#output-separate-or-mix)). |

The run's own `GET /strategy/{strategyId}/live` returns the block as accepted: `feeRate` resolved
into `buyFeeRate`/`sellFeeRate`, defaults filled in, `feeLeg` upper-cased.

**Sizing.** Without `percentAmountToLock`, each entry locks 10% of the account's free balance, unless
the strategy sets its own. A backtest defaults to all-in instead, but a live run trades several pairs
at once, and all-in would let the first one hold the whole account. With `20`, as above, the first
entry locks 200 of the 1000, and a second entry opened while the first is still open locks 20% of the
800 left: 160.

### What is refused

Anything invalid is a `400`, never silently adjusted:

```json
{"code": 400, "message": "paper.slippage is not a known field (known: [initialFunding, feeRate, buyFeeRate, sellFeeRate, feeLeg, percentAmountToLock, output])"}
{"code": 400, "message": "paper.initialFunding must be > 0"}
{"code": 400, "message": "paper.output must be one of [separate, mix]"}
```

**Strategies that listen to their own execution.** A strategy that overrides
`getExecutionCallback()` reacts to its fills and stops, and paper trading is the only place a live run
executes. Starting one without a `paper` block is refused (`"paper": {}` is enough):

```json
{"code": 400, "message": "this strategy listens to execution events (it overrides getExecutionCallback()), and paper trading is where its orders are executed: a paper block is required, e.g. \"paper\": {}"}
```

## Accounts: one per quote currency

Every quote currency the run trades gets its own simulated account, opened with `initialFunding` in
**its own currency** the first time one of its pairs is traded. Accounts are never added together:
there is no conversion between currencies.

| `instruments` | accounts |
|---|---|
| `["BTC/USDT", "ETH/USDT"]` | one: `USDT` (1000 USDT), shared by both pairs |
| `["BTC/USDT", "ETH/BTC"]` | two: `USDT` (1000 USDT) and `BTC` (1000 BTC) |

Pairs that share an account share its balance: sizing is always a share of what that account still
has free.

## Reading an account

`GET /live/{runId}/paper` returns each account as last recorded. For the run above, a little after
01:02 UTC (BTC/USDT bought at 01:00:10 and sold at 01:01:18 for −0.41; ETH/USDT bought at 01:00:25 and
still open):

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper

200
{
  "runId": "6TzAPiPpsOWwBLdLBZCxwH",
  "stage": "SANDBOX",
  "accounts": [{
    "currency": "USDT",
    "initialFunding": 1000.0,
    "equity": 1000.44,
    "equityAtMs": 1758330120000,
    "equityKind": "mark",
    "realisedPnl": -0.41,
    "trades": 1,
    "gaps": 0,
    "openPositions": [{"instrument": "ETH/USDT", "base": 0.05948, "cost": 160.0}],
    "kpi": {
      "totalTrades": 1, "winCount": 0, "lossCount": 1, "winRate": 0.0,
      "pnlTotal": -0.41, "pnlTotalPercent": -0.041,
      "sharpeRatio": null, "sortinoRatio": null, "cagr": -0.00041,
      "maxDrawdown": 0.41, "maxDrawdownPercent": 0.041
    }
  }]
}
```

| field | meaning |
|---|---|
| `equity` | The latest recorded value: at the last closed trade (`equityKind: equity`, capital plus realised PnL), or at the last mark-to-market (`equityKind: mark`, which also values the open positions at market price). Until either exists, the starting capital. |
| `realisedPnl` | Sum of the PnL of the closed trades. |
| `trades` | Closed trades. |
| `gaps` | Times open positions were lost because the run was restarted with them open (see [Gaps](#gaps)). |
| `openPositions` | What is held now: `base` in the base asset, `cost` in the account's currency. |
| `kpi` | The same KPIs a backtest reports, over the trades closed so far; absent until the first one. |

The KPIs use the backtest's units: `winRate` and `cagr` are ratios (`0.15` = 15%);
`pnlTotalPercent` and `maxDrawdownPercent` are percentages (0–100 scale); `sharpeRatio` and
`sortinoRatio` are per trade, not annualised, and `null` until there are enough trades to compute
them.

## The equity curve

`GET /live/{runId}/paper/equity` pages through an account's whole curve, oldest first. It is kept for
the life of the run, so unlike signals there is no moving window. The curve is per **account**, not
per pair: BTC/USDT and ETH/USDT share one. Each point is one of:

| `kind` | when | `equity` |
|---|---|---|
| `equity` | after every closed trade, of any pair | capital plus realised PnL |
| `mark` | once a minute of market time, while any position is open | capital plus realised PnL plus the open positions at market price |
| `gap` | open positions lost at a restart | absent |

For the run above, from its start:

| time | event | point |
|---|---|---|
| 01:00:10 | BTC/USDT bought (200 USDT) | — |
| 01:00:25 | ETH/USDT bought (160 USDT) | — |
| 01:01:00 | a minute with both open, −0.38 unrealised | `mark` 999.62 |
| 01:01:18 | BTC/USDT sold, −0.41 | `equity` 999.59 |
| 01:02:00 | a minute with ETH/USDT open, +0.85 unrealised | `mark` 1000.44 |
| 01:02:31 | ETH/USDT sold, +0.72 | `equity` 1000.31 |
| 01:03:00 | nothing open | — |
| 01:03:40 | BTC/USDT bought again (200.06 USDT) | — |
| 01:04:00 | a minute with BTC/USDT open, −0.12 unrealised | `mark` 1000.19 |

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?limit=3

200
{
  "points": [
    {"currency": "USDT", "kind": "mark",   "eventTsMs": 1758330060000, "equity": 999.62},
    {"currency": "USDT", "kind": "equity", "eventTsMs": 1758330078000, "equity": 999.59},
    {"currency": "USDT", "kind": "mark",   "eventTsMs": 1758330120000, "equity": 1000.44}
  ],
  "_links": {"next": {"href": "/v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?cursor=eyJ0cyI6MTc1ODMzMDEyMDAwMCwiaWQiOiI…&limit=3"}}
}
```

Following `_links.next`:

```
200
{
  "points": [
    {"currency": "USDT", "kind": "equity", "eventTsMs": 1758330151000, "equity": 1000.31},
    {"currency": "USDT", "kind": "mark",   "eventTsMs": 1758330240000, "equity": 1000.19}
  ]
}
```

No `_links.next`: that was the last page. The cursor is opaque — use the `href` as given.
`sinceMs` starts from a given market time instead of the beginning; `limit` defaults to 100 and caps
at 1000.

**Several accounts.** Without `currency`, every account's points come interleaved by time, each
carrying its currency. For a run on BTC/USDT and ETH/BTC, `?currency=BTC` narrows to the BTC account:

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?currency=BTC

200
{
  "points": [
    {"currency": "BTC", "kind": "mark",   "eventTsMs": 1758330060000, "equity": 999.9981},
    {"currency": "BTC", "kind": "equity", "eventTsMs": 1758330097000, "equity": 1000.0012}
  ]
}
```

## Output: `separate` or `mix`

With `output: separate` (the default), paper trading stays out of the run's signals: read it with
the routes above. With `output: mix`, each paper item is also written into the run's own signals, as
`type: paper`, right after the signal that caused it. Filter them with `type`:

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/signals?type=paper&limit=4

200
{
  "signals": [
    {"type": "paper", "kind": "fill",   "eventTsMs": 1758330010000,
     "instrument": {"exchange": "binance", "segment": "spot", "symbol": "BTC/USDT"},
     "data": {"side": "buy", "orderKind": "market", "price": 84389.41, "amount": 0.00237,
              "counterAmount": 200.0, "feeBase": 0.00000237, "feeQuote": 0.0}, …},
    {"type": "paper", "kind": "trade",  "eventTsMs": 1758330078000,
     "instrument": {"exchange": "binance", "segment": "spot", "symbol": "BTC/USDT"},
     "data": {"side": "long", "entryTsMs": 1758330010000, "enterAmount": 200.0,
              "exitAmount": 199.59, "pnl": -0.41}, …},
    {"type": "paper", "kind": "equity", "eventTsMs": 1758330078000, "instrument": null,
     "data": {"currency": "USDT", "equity": 999.59}, …},
    {"type": "paper", "kind": "kpi",    "eventTsMs": 1758330078000, "instrument": null,
     "data": {"currency": "USDT", "totalTrades": 1, "winRate": 0.0, "pnlTotal": -0.41, …}, …}
  ],
  "availableSinceMs": 1757725212000,
  "_links": {"next": {"href": "/v1/live/6TzAPiPpsOWwBLdLBZCxwH/signals?cursor=…&limit=4&type=paper"}}
}
```

Each entry has the full signal shape described in [Live execution](live.md#signal-shape) (`v`,
`signalId`, `runId`, `stage`, `paramsVersion`, `emittedAtMs`, `order: null`, `regenerated`, `digest`),
shortened here to `…`. `kind` says what the item is:

| `kind` | when | `instrument` | `data` |
|---|---|---|---|
| `fill` | an order filled | the pair | `side` (`buy`/`sell`), `orderKind` (`market`, `limit`, `stop`, `stopTrailing`), `price`, `amount`, `counterAmount`, `feeBase`, `feeQuote` |
| `trade` | a position closed | the pair | `side` (`long`/`short`), `entryTsMs`, `enterAmount`, `exitAmount`, `pnl` |
| `equity` | after each closed trade | `null` | `currency`, `equity` |
| `kpi` | after each closed trade | `null` | `currency` and the KPIs of [Reading an account](#reading-an-account) |
| `mark` | once a minute of market time while positions are open | `null` | `currency`, `equity`, `realisedPnl`, `unrealisedPnl`, `openPositions` (how many) |
| `gap` | open positions lost at a restart | the pair | `currency`, `base`, `cost` |

`equity`, `kpi` and `mark` are about a whole account, so their `instrument` is `null` and
`data.currency` names the account. `type` combines with `instrument`:
`?type=paper&instrument=ETH/USDT` returns the fills, trades and gaps of that pair only.

Paper items are kept with the run's signals, under the same moving window, but they are **never
pushed over the WebSocket channel**, whatever `relay` says. For the complete, permanent record use
the paper routes.

## Gaps

A run can be restarted by the platform, for instance when a new version is deployed. Its paper trading carries
on from its record: closed trades, realised PnL, equity curve and KPIs are all kept, and nothing is
counted twice. Positions that were **open** at the restart, and any pending orders, cannot be carried
over: each open position is reported as a `gap`, with what it held, and is no longer counted.

```json
{"currency": "USDT", "kind": "gap", "eventTsMs": 1758333600000}
```

In the curve a gap has no `equity`, and the account's `gaps` counts them. In a `mix` run the
matching signal names the pair and what was held:

```json
{"type": "paper", "kind": "gap", "instrument": {"exchange": "binance", "segment": "spot", "symbol": "ETH/USDT"},
 "data": {"currency": "USDT", "base": 0.05948, "cost": 160.0}, …}
```
