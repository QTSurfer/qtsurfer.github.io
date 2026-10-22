# Paper trading on live runs

Start a [live run](live.md) with a `paper` block and its hints are executed in simulation from its
first tick, exactly as a backtest would execute them: orders fill, positions open and close, and the
run accumulates equity and the same KPIs a backtest reports. Nothing is sent to an exchange. Without
the block, the run has no paper trading.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/strategy/{strategyId}/live` | Start a run — with a `paper` block to paper-trade it |
| `GET` | `/live/{runId}/paper` | Each paper account: equity, open positions, KPIs |
| `GET` | `/live/{runId}/paper/equity` | One account's equity curve, in the shape of every [equity curve](equity_curves.md) |
| `GET` | `/live/{runId}/signals?type=paper` | Paper items interleaved in the run's signals (`output: mix` only) |

Both paper routes follow the same access rule as a run's signals: the run's owner, or anyone if the
run is `public`. A run started without a `paper` block answers `404` on both.

## Starting a run with paper trading

```
POST /v1/strategy/6bsh31ikwkuivhtgcoa6s4/live
{
  "sources": [{"venueType": "cex", "exchange": "binance", "segment": "spot", "type": "ticker",
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
| `initialFunding` | `100` | Starting capital of each account, in that account's quote currency. At most 1,000,000,000. With `accounts: instrument` it is the capital of EACH instrument's account, never the run's total. |
| `feeRate` | `0.001` | Fee rate for both sides (0.001 = 0.1%). |
| `buyFeeRate` / `sellFeeRate` | `feeRate` | Per-side rates; override `feeRate`. |
| `feeLeg` | `RECEIVED` | Which asset fees are charged in: `RECEIVED`, `QUOTE` or `BASE`. |
| `percentAmountToLock` | see below | Share of the account's free balance each entry locks, in percent (0–100]. |
| `output` | `separate` | `separate`, or `mix` to also write paper items into the run's signals (see [below](#output-separate-or-mix)). |
| `accounts` | `currency` | `currency`: one shared account per quote currency. `instrument`: one isolated account per instrument, each with its own `initialFunding` (see [One account per instrument](#one-account-per-instrument)). |

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
{"code": 400, "message": "paper.slippage is not a known field (known: [initialFunding, feeRate, buyFeeRate, sellFeeRate, feeLeg, percentAmountToLock, output, accounts])"}
{"code": 400, "message": "paper.initialFunding must be > 0"}
{"code": 400, "message": "paper.output must be one of [separate, mix]"}
{"code": 400, "message": "paper.accounts must be one of [currency, instrument]"}
{"code": 400, "message": "paper.accounts = instrument needs the instruments named, not a wildcard ('*'): it opens one account for each"}
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

### One account per instrument

With `"accounts": "instrument"` in the `paper` block, each instrument gets an account of its own
instead, opened with `initialFunding` in the instrument's quote currency the first time it is traded.
Each is a simulation of that instrument alone, exactly what a backtest of it would do with the same
economics: it never draws on another instrument's balance, so it is the way to compare a live run with
a backtest of each instrument.

| `instruments` | `accounts: currency` (the default) | `accounts: instrument` |
|---|---|---|
| `["BTC/USDT", "ETH/USDT"]` | one: `USDT` (1000 USDT), shared | two: `BTC/USDT` (1000 USDT) and `ETH/USDT` (1000 USDT) |
| `["BTC/USDT", "ETH/BTC"]` | two: `USDT` and `BTC` | two: `BTC/USDT` (1000 USDT) and `ETH/BTC` (1000 BTC) |

Three things to know:

- **`initialFunding` is the capital of each account, never the run's total.** Two instruments with
  `"initialFunding": 1000` are two accounts of 1000, not 1000 split between them. The accounts are
  never added together, in the same currency or not, and nothing here reports a total.
- **It is less realistic than the shared account.** A venue holds one wallet per asset, not one per
  pair: with a shared account, a `*/USDT` run at 25% per entry can hold four instruments from one USDT
  wallet, and what it sells comes back as USDT. Use the isolated mode to ask "how would this strategy
  have done on this instrument alone"; use the shared one to ask how the run behaves with one wallet.
- **Without `percentAmountToLock`, an entry locks the whole free balance**, as a backtest does, because
  nothing is shared. The shared account keeps its 10% default. A value you give wins in both.

The instruments have to be named: `"instruments": ["*"]`, or a pair with a `*` on one side, is refused
whatever the plan, since it would open an account, each with the whole `initialFunding`, for every
instrument of the exchange. The split is fixed when the run starts and is returned with the block.

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
    "unrealisedPnl": 0.85,
    "totalPnl": 0.44,
    "trades": 1,
    "gaps": 0,
    "openPositions": [{
      "instrument": "ETH/USDT", "base": 0.05948, "cost": 160.0,
      "markPrice": 2704.25, "markedAtMs": 1758330120000, "unrealisedPnl": 0.85
    }],
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
| `unrealisedPnl` | What its open positions are worth over their cost as of the last mark, in the account's currency: the sum of `unrealisedPnl` over `openPositions`. `0` when it holds nothing. Absent while any of its positions has no current mark. |
| `totalPnl` | `realisedPnl` plus `unrealisedPnl`; absent when `unrealisedPnl` is. When `equityKind` is `mark` and it is present, it is `equity` minus `initialFunding`. |
| `trades` | Closed trades. |
| `gaps` | Times open positions were lost because the run was restarted with them open (see [Gaps](#gaps)). |
| `openPositions` | What is held now: `base` in the base asset, `cost` in the account's currency. When the last mark valued the position as it stands now it also says `markPrice` (the price it was valued at), `markedAtMs` (when) and `unrealisedPnl` (`base` times `markPrice`, minus `cost`). A position opened or changed since the last mark, at most about a minute ago, has none of those three yet. |
| `kpi` | The same KPIs a backtest reports, over the trades closed so far; absent until the first one. |

The KPIs use the backtest's units: `winRate` and `cagr` are ratios (`0.15` = 15%);
`pnlTotalPercent` and `maxDrawdownPercent` are percentages (0–100 scale); `sharpeRatio` and
`sortinoRatio` are per trade, not annualised, and `null` until there are enough trades to compute
them.

### Per instrument

An account is shared by every instrument of its quote currency, so each account also says what it
realised **per instrument**: `instruments`, one entry for every instrument that has closed a trade or
holds a position now, in instrument order. For a run with BTC/USDT and ETH/USDT on one 1000 USDT
account:

```
"instruments": [
  {
    "instrument": "BTC/USDT", "trades": 3, "wins": 2, "losses": 1,
    "realisedPnl": 12.0, "contributionPct": 1.2,
    "unrealisedPnl": 0.0, "totalPnl": 12.0,
    "kpi": {
      "totalTrades": 3, "winCount": 2, "lossCount": 1, "winRate": 0.6667,
      "pnlTotal": 12.0, "pnlTotalPercent": 1.2,
      "sharpeRatio": 0.6794, "sortinoRatio": 1.7321, "cagr": 0.012,
      "maxDrawdown": 4.0, "maxDrawdownPercent": 0.396
    }
  },
  {
    "instrument": "ETH/USDT", "trades": 2, "wins": 0, "losses": 2,
    "realisedPnl": -3.0, "contributionPct": -0.3,
    "unrealisedPnl": 0.85, "totalPnl": -2.15,
    "openPosition": {
      "base": 0.05948, "cost": 160.0,
      "markPrice": 2704.25, "markedAtMs": 1758330120000, "unrealisedPnl": 0.85
    },
    "kpi": {
      "totalTrades": 2, "winCount": 0, "lossCount": 2, "winRate": 0.0,
      "pnlTotal": -3.0, "pnlTotalPercent": -0.3,
      "sharpeRatio": -1.0, "sortinoRatio": -0.7071, "cagr": -0.003,
      "maxDrawdown": 3.0, "maxDrawdownPercent": 0.3
    }
  }
]
```

| field | meaning |
|---|---|
| `instrument` | The pair. |
| `trades`, `wins`, `losses` | Its closed trades. A trade wins if its PnL is above zero, so a trade with a PnL of exactly zero is a loss. |
| `realisedPnl` | Sum of the PnL of its closed trades, in the account's currency. The `realisedPnl` of the instruments add up to the account's. |
| `contributionPct` | `realisedPnl` as a percent of the account's `initialFunding` (0–100 scale), so the contributions of the instruments add up to the account's realised return. |
| `openPosition` | What it holds now (`base` in the base asset, `cost` in the account's currency); absent when it holds nothing. With the same `markPrice`, `markedAtMs` and `unrealisedPnl` as an entry of the account's `openPositions`, when the last mark is of the position as it stands. An instrument that holds a position but has not closed a trade yet is listed, without a `kpi`. |
| `unrealisedPnl` | What its open position is worth over its cost, as of the last mark; `0` when it holds nothing. Absent while its position has no current mark. Added over the instruments it is the account's `unrealisedPnl`, the part of `equity` (at a mark) that is not capital or realised. |
| `totalPnl` | `realisedPnl` plus `unrealisedPnl`; absent when `unrealisedPnl` is. |
| `kpi` | The KPIs of that instrument's closed trades alone, with the account's `initialFunding` as the capital, so its `pnlTotalPercent` equals its `contributionPct`. Same units as the account's; absent until its first closed trade. |

**What the breakdown is, and what it is not.** It is exact for what was realised. It is not how the
instrument would have done on its own: its entries depended on what the others had already locked from
the same account (with `percentAmountToLock: 20`, a second entry locks 20 % of what the first left
free), so a different mix of instruments would have sized it differently. It answers which instrument
adds to the account and which one takes away.

### An account per instrument

For a run started with `"accounts": "instrument"` each entry of `accounts` is one instrument and says
so with `instrument`; `currency` is its quote, and two accounts can share it. There is no `instruments`
to break down, since the account already is one instrument.

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper

200
{
  "runId": "6TzAPiPpsOWwBLdLBZCxwH",
  "stage": "SANDBOX",
  "accounts": [
    {
      "currency": "USDT", "instrument": "BTC/USDT",
      "initialFunding": 1000.0, "equity": 1001.2, "equityAtMs": 1758330120000, "equityKind": "mark",
      "realisedPnl": 1.2, "unrealisedPnl": 0.0, "totalPnl": 1.2, "trades": 3, "gaps": 0, "openPositions": [],
      "kpi": {"totalTrades": 3, "winCount": 2, "lossCount": 1, "winRate": 0.6667, "pnlTotal": 1.2, "pnlTotalPercent": 0.12}
    },
    {
      "currency": "USDT", "instrument": "ETH/USDT",
      "initialFunding": 1000.0, "equity": 997.35, "equityAtMs": 1758330120000, "equityKind": "mark",
      "realisedPnl": -3.5, "unrealisedPnl": 0.85, "totalPnl": -2.65, "trades": 2, "gaps": 0,
      "openPositions": [{
        "instrument": "ETH/USDT", "base": 0.05948, "cost": 160.0,
        "markPrice": 2704.25, "markedAtMs": 1758330120000, "unrealisedPnl": 0.85
      }],
      "kpi": {"totalTrades": 2, "winCount": 0, "lossCount": 2, "winRate": 0.0, "pnlTotal": -3.5, "pnlTotalPercent": -0.35}
    }
  ]
}
```

Each account has its own `initialFunding` and its own KPIs, computed over its trades alone. Its
`unrealisedPnl` and `totalPnl` are those of any account (above): what its position is worth, and that
with what it realised, so here they are the instrument's own. Read
`GET /live/{runId}/paper/equity?instrument=ETH/USDT` for the curve of one of them (see [The equity
curve](#the-equity-curve)).

## The equity curve

`GET /v1/live/{runId}/paper/equity` returns an account's whole curve, oldest first, in the same shape
as every other [equity curve](equity_curves.md) of the API: `{points, meta}` or, with
`outMode=SHORT`, `{timestamps, equities, meta}`, shaped by the same `outMode`, `resample` and
`differential` query parameters and described by the same `meta`. Beside it come the account's
`currency` and its `gaps`. The curve is kept for the life of the run, so unlike signals there is no
moving window. It is per **account**, not per pair: BTC/USDT and ETH/USDT share one.

It is one series of running equity, made of two kinds of point:

| point | when | `equity` |
|---|---|---|
| closed trade | after every closed trade, of any pair | capital plus realised PnL |
| mark | once a minute of market time, while any position is open | capital plus realised PnL plus the open positions at market price |

Where the run was restarted with positions open, those positions are lost (see [Gaps](#gaps)) and the
curve has no value there: that moment is listed in `gaps`, beside the curve, and is not a point of it.

For the run above, from its start:

| time | event | point |
|---|---|---|
| 01:00:10 | BTC/USDT bought (200 USDT) | — |
| 01:00:25 | ETH/USDT bought (160 USDT) | — |
| 01:01:00 | a minute with both open, −0.38 unrealised | mark 999.62 |
| 01:01:18 | BTC/USDT sold, −0.41 | closed trade 999.59 |
| 01:02:00 | a minute with ETH/USDT open, +0.85 unrealised | mark 1000.44 |
| 01:02:31 | ETH/USDT sold, +0.72 | closed trade 1000.31 |
| 01:03:00 | nothing open | — |
| 01:03:40 | BTC/USDT bought again (200.06 USDT) | — |
| 01:04:00 | a minute with BTC/USDT open, −0.12 unrealised | mark 1000.19 |

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity

200
{
  "currency": "USDT",
  "measure": "equity",
  "points": [
    {"timestamp": 1758330060000, "equity": 999.62},
    {"timestamp": 1758330078000, "equity": 999.59},
    {"timestamp": 1758330120000, "equity": 1000.44},
    {"timestamp": 1758330151000, "equity": 1000.31},
    {"timestamp": 1758330240000, "equity": 1000.19}
  ],
  "gaps": [],
  "meta": {"inputPointCount": 5, "outputPointCount": 5, "resampled": false, "differential": false, "outMode": "ARRAY"}
}
```

The compact forms are the ones every curve has. The same curve, delta-encoded in parallel arrays (the
first value stays absolute, see [decoding differential data](equity_curves.md#decoding-differential-data)):

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?outMode=SHORT&differential=true

200
{
  "currency": "USDT",
  "measure": "equity",
  "timestamps": [1758330060000, 18000, 42000, 31000, 89000],
  "equities": [999.62, -0.03, 0.85, -0.13, -0.12],
  "gaps": [],
  "meta": {"inputPointCount": 5, "outputPointCount": 5, "resampled": false, "differential": true, "outMode": "SHORT"}
}
```

A long run has a long curve. `resample` caps it (`?resample=500` is at most 500 points, keeping the
first, the last and the extremes), and above a server-side size the shape is compacted whatever was
asked, as for any curve: read `meta.outMode`. `sinceMs` starts from a given market time, inclusive, so
a client that already holds a curve reads only what is new. A curve too long to be read in one request
answers `400`; narrow it with `sinceMs`, or page it.

**Reading the raw curve in pages.** The server compacts a long curve and, past a larger size,
resamples it, so the whole-curve answer is not the way to take every point. To take them all, ask for
pages: give `limit` (up to 1000, default 100) and the answer is one page of the raw curve, oldest
first, with `_links.next` while there is more.

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?limit=3

200
{
  "currency": "USDT",
  "measure": "equity",
  "points": [
    {"timestamp": 1758330060000, "equity": 999.62},
    {"timestamp": 1758330078000, "equity": 999.59},
    {"timestamp": 1758330120000, "equity": 1000.44}
  ],
  "gaps": [],
  "meta": {"inputPointCount": 3, "outputPointCount": 3, "resampled": false, "differential": false, "outMode": "ARRAY"},
  "_links": {"next": {"href": "/v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?cursor=eyJ0cyI6MTc1ODMzMDEyMDAwMCwiaWQiOiI…&limit=3&currency=USDT"}}
}
```

Follow `_links.next` as given (the cursor is opaque); a page without `_links` is the last one:

```
200
{
  "currency": "USDT",
  "measure": "equity",
  "points": [
    {"timestamp": 1758330151000, "equity": 1000.31},
    {"timestamp": 1758330240000, "equity": 1000.19}
  ],
  "gaps": [],
  "meta": {"inputPointCount": 2, "outputPointCount": 2, "resampled": false, "differential": false, "outMode": "ARRAY"}
}
```

A page has the same shape as the whole curve, so `outMode` and `differential` apply to it and the next
link keeps them; each page is decoded on its own, with its own absolute first value. A page holds at
most `limit` entries and a [gap](#gaps) counts as one, so a page with a gap has one point fewer, and
the gap's time is in that page's `gaps`. `resample` cannot be combined with paging (`400`): a
resampled curve is one answer, a paged one is the raw curve. A cursor never loses or repeats an
entry, even between two entries of the same millisecond.

**Several accounts.** Each account has its own curve, never added to another. `currency` chooses it,
and it may be left out only when the run has a single account (or none yet, which gives an empty
curve). With several accounts and no `currency` the request is a `400` that lists them. For a run on
BTC/USDT and ETH/BTC, `?currency=BTC` is the BTC account:

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?currency=BTC

200
{
  "currency": "BTC",
  "measure": "equity",
  "points": [
    {"timestamp": 1758330060000, "equity": 999.9981},
    {"timestamp": 1758330097000, "equity": 1000.0012}
  ],
  "gaps": [],
  "meta": {"inputPointCount": 2, "outputPointCount": 2, "resampled": false, "differential": false, "outMode": "ARRAY"}
}
```

**One instrument's curve.** For the breakdown above (see [Per instrument](#per-instrument)),
`?instrument=BTC/USDT` answers that instrument's **cumulative realised PnL**, from 0: a point at each
of its closed trades. It is the same curve shape, with the same options and paging, and the answer
says what its values are in `measure`: `equity` on an account's curve, `realisedPnl` on an
instrument's (the shape names its values `equity` either way). An instrument belongs to the account
of its quote currency, so `currency` need not be given, and a different one is a `400`. The last
values of the curves of all the instruments of an account add up to the account's `realisedPnl`. In
between they follow the realised part of the account's own curve only up to the order the trades were
processed in: the account's curve is recorded in that order and this one is served by event time, and
two instruments that close almost together can be stamped slightly out of it, so at those points the
two differ by one trade. The account's gaps are not attributed to an instrument, so `gaps` is empty
here.

**With an account per instrument**, `?instrument=ETH/USDT` does not ask for a part of a shared account:
it SELECTS the account that instrument is, and the answer is that account's own curve, its `equity` (it
already includes its marks), with the `instrument` beside the `currency` and the account's own `gaps`.
`currency` may be given instead only while it names a single account, `measure` does not apply (a
`400`), and with several accounts one of them has to be named.

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?instrument=ETH/USDT

200
{
  "currency": "USDT",
  "instrument": "ETH/USDT",
  "measure": "equity",
  "points": [
    {"timestamp": 1758330060000, "equity": 999.1},
    {"timestamp": 1758330120000, "equity": 996.5}
  ],
  "gaps": [],
  "meta": {"inputPointCount": 2, "outputPointCount": 2, "resampled": false, "differential": false, "outMode": "ARRAY"}
}
```

**With what it holds and has not sold.** `?instrument=ETH/USDT&measure=totalPnl` adds to each point the
unrealised value of the instrument's open position: a point at each closed trade (nothing is held then,
so it is the cumulative realised PnL) and at each mark while a position is open (what was realised up to
then, plus what the position is worth at that mark). The answer says `"measure": "totalPnl"`. The
default is `measure=realisedPnl`; `measure` without `instrument` is a `400`, since an account's curve is
`equity` and already includes its marks.

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?instrument=ETH/USDT&measure=totalPnl

200
{
  "currency": "USDT",
  "instrument": "ETH/USDT",
  "measure": "totalPnl",
  "points": [
    {"timestamp": 1758329950000, "equity": -1.0},
    {"timestamp": 1758330010000, "equity": -3.0},
    {"timestamp": 1758330060000, "equity": -3.4},
    {"timestamp": 1758330120000, "equity": -2.15}
  ],
  "gaps": [],
  "meta": {"inputPointCount": 4, "outputPointCount": 4, "resampled": false, "differential": false, "outMode": "ARRAY"}
}
```

The first two points are closed trades (−1.0, then −2.0 more); the position opened at 01:00:25 is worth
−0.4 at the 01:01:00 mark (−3.0 − 0.4) and +0.85 at the 01:02:00 mark (−3.0 + 0.85).

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/paper/equity?instrument=BTC/USDT

200
{
  "currency": "USDT",
  "instrument": "BTC/USDT",
  "measure": "realisedPnl",
  "points": [
    {"timestamp": 1758330078000, "equity": 10.0},
    {"timestamp": 1758330190000, "equity": 6.0},
    {"timestamp": 1758330310000, "equity": 12.0}
  ],
  "gaps": [],
  "meta": {"inputPointCount": 3, "outputPointCount": 3, "resampled": false, "differential": false, "outMode": "ARRAY"}
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
| `mark` | once a minute of market time while positions are open | `null` | `currency`, `equity`, `realisedPnl`, `unrealisedPnl`, `openPositions` (how many) and `positions`, one entry per open position: `instrument`, `base`, `cost`, `markPrice`, `unrealisedPnl` (their `unrealisedPnl` add up to the mark's) |
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
"gaps": [1758333600000]
```

A gap is not a point of the curve: the curve lists its time in `gaps`, and the account's `gaps`
counts them. In a `mix` run the matching signal names the pair and what was held:

```json
{"type": "paper", "kind": "gap", "instrument": {"exchange": "binance", "segment": "spot", "symbol": "ETH/USDT"},
 "data": {"currency": "USDT", "base": 0.05948, "cost": 160.0}, …}
```
