# Live execution

Run a strategy continuously against a live market feed, watch its signals as they happen, and
change its parameters without restarting it.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/strategy/{strategyId}/live` | Start a strategy live |
| `GET` | `/strategy/{strategyId}/live` | Read this strategy's current (or last) run |
| `DELETE` | `/strategy/{strategyId}/live` | Stop it |
| `GET` | `/live` | List your own runs |
| `GET` | `/live/public` | Browse runs other users made public |
| `PATCH` | `/live/{runId}` | Change visibility, name, or description |
| `PUT` | `/live/{runId}/params` | Change parameters while it stays live |
| `GET` | `/live/{runId}/signals` | Read the signals it has already produced |
| `GET` | `/live/{runId}/paper` | Read its paper trading: accounts, equity, positions, KPIs |
| `GET` | `/live/{runId}/paper/equity` | Page through its paper equity curve |
| `POST` | `/live/token` | Mint a WebSocket connection token |

## Lifecycle: sandbox, then live

Starting a run (`POST /strategy/{strategyId}/live`) never puts it in front of anything that reads
its signals immediately. It begins in the `sandbox` stage — a short trial, comparing an
independent second execution against the first for agreement — and is promoted to `live`
automatically once it passes. Poll `stage` on `GET`/`PATCH` `.../live` to watch it move from
`SANDBOX` to `LIVE`; there is no separate "promote" call.

Only one run per strategy at a time. Starting again while one is `RUNNING` is `409` — stop it
first with `DELETE`.

A stop (`DELETE`) is a request, not an instant kill: `desired` flips to `STOPPED` immediately, but
`state` can stay `RUNNING` for a short window while the run winds down. Calling `DELETE` again on
an already-stopped run is not an error.

## Sources

`sources` takes exactly one entry (multi-source strategies are not supported yet):

```json
{
  "sources": [
    {"venueType": "cx", "exchange": "binance", "segment": "spot", "type": "ticker", "instruments": ["BTC/USDT"]}
  ]
}
```

`type` is `ticker` or `kline`. Both connect to the lightest (fastest) cadence available for the
exchange — today that is 1 tick/second on every supported exchange; choosing among several
cadences is not offered yet. `instruments`
can be `["*"]` for every instrument the exchange/segment offers, subject to your plan's
instrument-count limit.

## Listing your runs

`GET /live` (needs a Bearer token) returns every run you have started — any `stage`, any
`desired` state, any `visibility` — newest first, paged the same way as `GET /live/public`
(`cursor`/`limit`, `_links.next.href`). It does not filter by `state`: a `sandbox` trial or a
run you have already stopped still shows up, unlike `GET /live/public`, which needs no
`Authorization` header but only ever lists other runs — anyone's, yours included — that are
`public` and currently `RUNNING`.

## Visibility

A run is `private` by default — only you can read its state or receive its signals. Setting
`visibility: public` (via `PATCH /live/{runId}`) does two things:

- it appears in `GET /live/public`'s catalogue, listed without revealing who owns it or which
  strategy runs it;
- its signal channel (see below) accepts a WebSocket subscription from anyone, not only you.

Switching back to `private` also disconnects anyone else currently subscribed to that channel —
best-effort, and it does not undo the visibility change if the disconnect itself fails.

## Runtime parameters

`params` on `POST /strategy/{strategyId}/live` only sets the values a run **starts** with. To
change one while the run keeps running, call `PUT /live/{runId}/params` (or the equivalent
`live.params` WebSocket call below — both go through the same validation and land on the identical
value at the identical moment). Every key must be one your strategy declares; an undeclared key is
`400`.

The response's `effectiveAtMs` is not "now" — it is a few seconds out, the earliest moment the new
value is guaranteed to be applied. This margin exists so that if a run has more than one execution
worker behind it, they all pick up the change at the same point rather than one applying it a few
events before the other.

```
PUT /live/6TzAPiPpsOWwBLdLBZCxwH/params
{"params": {"emaFastPeriod": "12"}}

200
{"runId": "6TzAPiPpsOWwBLdLBZCxwH", "paramsVersion": 2, "effectiveAtMs": 1758330015000}
```

## Receiving signals and updating parameters live: the WebSocket connection

Polling `GET .../live` tells you the run's *state*; it does not stream its output. To receive a
run's signals as they happen, or to send a parameter update over the same connection instead of a
separate REST call, open a WebSocket connection.

The connection speaks the [Centrifugo](https://centrifugal.dev) v6 client protocol (JSON). Its
machine-readable contract is [`asyncapi.yaml`](../asyncapi.yaml), next to the OpenAPI spec: the
URL, every frame, the channel names, the `live.params` call and the error codes, with the signal
payload shared with the REST schema `LiveSignal`.

The QTSurfer SDKs already wrap this connection — see
[Clients and SDKs](https://www.qtsurfer.com/docs/developers/clients-and-sdks) — so you may not need
to speak the protocol directly at all. Going direct, the easiest client is an official Centrifugo
library — [`centrifuge`](https://github.com/centrifugal/centrifuge-js) (JavaScript/TypeScript),
[`centrifuge-java`](https://github.com/centrifugal/centrifuge-java),
[`centrifuge-python`](https://github.com/centrifugal/centrifuge-python) and
[others](https://centrifugal.dev/docs/transports/client_sdk) — since it already does the pings,
token refresh and reconnection described below. With one, you only supply the URL, a function
that mints a token, the channel name and the RPC method.

Signals only reach this channel for a run started with `relay: true` (`POST .../live`'s own field,
default `false`) — and only once it reaches the `live` stage; a run still in `sandbox` never
relays, whatever was requested at start. `GET`/`PATCH .../live` echo back what was requested as the
run's own `relay` field, already folded with that stage rule — `true` there means signals are
reaching the channel right now, not merely that `relay: true` was once passed.

1. **Mint a token.** `POST /live/token` (JWT bearer, same as any other endpoint) returns a
   short-lived `token` and its `expiresAtMs`.
2. **Connect.** Open a WebSocket to `wss://rt.qtsurfer.net/connection/websocket` and send, as your
   first message:
   ```json
   {"id": 1, "connect": {"token": "<the token from step 1>"}}
   ```
   A successful connect replies with your own `client` id, and how long the token has left:
   ```json
   {"id": 1, "connect": {"client": "<client-id>", "expires": true, "ttl": 600, "ping": 25, "pong": true}}
   ```
   `ttl` and `ping` are in seconds. A token that is not accepted closes the socket with close code
   `3500` (`invalid token`).
3. **Subscribe to the run's signal channel**, named `sig:<runId>` — for example `sig:6TzAPiPpsOWwBLdLBZCxwH`:
   ```json
   {"id": 2, "subscribe": {"channel": "sig:6TzAPiPpsOWwBLdLBZCxwH"}}
   ```
   You may subscribe to any run's channel this way, but the connection is only actually allowed
   onto it if you own that run or it is `public` — a foreign private run's channel refuses the
   subscription with `{"id": 2, "error": {"code": 103, "message": "permission denied"}}`. Each
   signal then arrives as a `push` frame, with no `id`; the signal itself is its `pub.data`, in the
   shape below:
   ```json
   {"push": {"channel": "sig:6TzAPiPpsOWwBLdLBZCxwH", "pub": {"data": {"v": 1, "signalId": "…", …}, "offset": 42}}}
   ```
   If the run is made private while you are subscribed and it is not yours, the server removes you
   with `{"push": {"channel": "sig:…", "unsubscribe": {"code": 2000, "reason": "server unsubscribe"}}}`,
   and you are not resubscribed.
4. **Call `live.params`** (the WebSocket form of `PUT /live/{runId}/params`, owner-only):
   ```json
   {"id": 3, "rpc": {"method": "live.params", "data": {"runId": "6TzAPiPpsOWwBLdLBZCxwH", "params": {"emaFastPeriod": "12"}}}}
   ```
   Success:
   ```json
   {"id": 3, "rpc": {"data": {"runId": "6TzAPiPpsOWwBLdLBZCxwH", "paramsVersion": 2, "effectiveAtMs": 1758330015000}}}
   ```
   Failure (mirrors the REST endpoint's own 400/404/409):
   ```json
   {"id": 3, "error": {"code": 404, "message": "no such run"}}
   ```
5. **Keep the connection alive.** The server sends an empty frame `{}` as a ping; answer each one
   with `{}` (that is what `"pong": true` in the connect reply asks for). If nothing arrives for
   well over `ping` seconds, treat the connection as dead and reconnect.
6. **Refresh the token before `ttl` runs out**, on the same connection — mint a new one with
   `POST /live/token` and send it:
   ```json
   {"id": 4, "refresh": {"token": "<a new token>"}}
   ```
   which answers `{"id": 4, "refresh": {"expires": true, "ttl": 600}}`. Your subscriptions are
   untouched. A connection whose token is not refreshed in time is closed with close code `3005`
   (`connection expired`); reconnect with a new token.

Some protocol details to know if you write the client yourself: every reply carries the `id` of the
command it answers, frames the server sends on its own (pushes, pings) carry none, and one
WebSocket frame may hold several replies, one JSON object per line. A browser page served from
another site's origin is refused at the WebSocket upgrade (`403`); a client that sends no `Origin`
header, such as a server-side program or an SDK, is not affected.

After a disconnect, the channel does not replay what you missed: read it back with
`GET /live/{runId}/signals` (below), deduplicating on `signalId`.

### Signal shape

Each signal pushed on a `sig:<runId>` channel (the `pub.data` of the `push` frame):

```json
{
  "v": 1,
  "signalId": "…",
  "runId": "6TzAPiPpsOWwBLdLBZCxwH",
  "stage": "live",
  "paramsVersion": 2,
  "type": "hint",
  "kind": "BUY",
  "eventTsMs": 1758330012000,
  "emittedAtMs": 1758330012040,
  "instrument": {"exchange": "binance", "segment": "spot", "symbol": "BTC/USDT"},
  "order": {"orderKind": "MARKET", "price": null, "amount": null, "stopPrice": null, "trailPct": null},
  "data": {},
  "regenerated": false,
  "digest": "…"
}
```

| field | meaning |
|---|---|
| `signalId` | Stable id for this exact signal — dedupe on it if your connection ever reconnects mid-stream. |
| `stage` | Always `live` on this channel — a run only relays once `relay` is in effect, which never happens in `sandbox` (see above). |
| `paramsVersion` | The parameter set in force when this signal was produced. |
| `type` | `hint`, `info`, `marker`, or `command` — plus `paper` when reading a `mix` run's history (see "Paper trading"; paper items are never pushed on this channel). |
| `kind` | `BUY`/`SELL` for a `hint`; the command name for a `command`; absent otherwise. |
| `eventTsMs` | Market time the signal was produced. |
| `emittedAtMs` | Time it was published — always ≥ `eventTsMs`. |
| `order` | Present only for a `hint`. |
| `data` | The signal's own free-form payload. |
| `regenerated` | `true` only for a signal republished to fill a gap in the historical record — always `false` for a signal you are seeing for the first time. |
| `digest` | Content hash, for verifying two independent deliveries of the same signal agree. |

Who owns the run, which strategy or compilation produced a signal, and the exact market-data
position behind it are never included on this channel, whether the run is public or private.

## Reading signals a run already produced

The channel above is live only: it carries what happens while you are connected, and only for a run
that asked for `relay`. `GET /live/{runId}/signals` serves the record instead — a run's signals are
kept either way, so this works whether or not `relay` was ever on, and in both stages. Use it to
catch up after a disconnect, to read a run you never relayed, or simply to page back over what has
already happened.

```
GET /v1/live/6TzAPiPpsOWwBLdLBZCxwH/signals?sinceMs=1758330000000&limit=20

200
{
  "signals": [ { "signalId": "…", "eventTsMs": 1758330012000, … } ],
  "availableSinceMs": 1757725212000,
  "_links": {"next": {"href": "/v1/live/6TzAPiPpsOWwBLdLBZCxwH/signals?cursor=eyJzZXEiOjQyfQ&limit=20"}}
}
```

Each entry is the same shape the channel pushes — the table above applies unchanged, except that
`stage` here is whichever stage the run was in when the signal was produced, so a sandbox run's
signals read back as `sandbox`. Page with `_links.next` while it is present; `limit` defaults to 20
and caps at 100. Readable by the run's owner, and by anyone if the run is `public` — the same rule
the channel applies to a subscription.

### Filtering by instrument

`instrument` is optional and narrows the page without changing anything else:

| `instrument` | returns |
|---|---|
| omitted, or `*` | every instrument the run covers |
| `BTC/USDT` | just that pair |
| `*/USDT` | any base against that quote |
| `BTC/*` | that base against any quote |
| `BTC/USDT,ETH/EUR` | each pair in the list |

Symbols match exactly, case included — pass them as this API reports them (as they appear in the
run's own `sources`, or in a signal's `instrument.symbol`).

### Filtering by type

`type` narrows to one or more signal types, comma-separated: `hint`, `info`, `marker`, `command`,
`paper`. It combines with `instrument` — `?type=hint&instrument=*/USDT` is every hint on a USDT pair.
Both filters are carried over into `_links.next`, so following it keeps the same selection.

### The window moves, and cursors expire

Signals are kept for a limited span, and the oldest are discarded continuously as new ones arrive.
How far back you can read is therefore not a fixed number of hours: a run producing a lot of signals
consumes that span faster, and so do other runs sharing it. Two consequences worth designing for:

- **`availableSinceMs`** in every response is the oldest moment still answerable. Asking for a
  `sinceMs` older than that is not an error: you are served from `availableSinceMs` onwards, and
  the field tells you that is what happened.
- **A cursor can expire**, and on a busy run it can expire within minutes. When the position it
  points at has already been discarded, the next page answers `410` rather than quietly serving a
  shortened page that looks complete:

  ```json
  {"code": 410, "message": "the cursor's position is no longer retained by the signal stream (it now starts at availableSinceMs=1757725212000)"}
  ```

  Treat it as an ordinary outcome of paging a live system, not as a failure: read the
  `availableSinceMs` it names and start again from there. If you are paging to display a long
  history, fetch the pages you need in one pass rather than holding a cursor across a user's
  think-time.

## Paper trading

Start a run with a `paper` block and its hints are executed in simulation from its first tick,
exactly as a backtest would execute them: fills, closed trades, equity and the same KPIs a backtest
reports. Without the block the run has no paper trading.

```json
POST /v1/strategy/6bsh31ikwkuivhtgcoa6s4/live
{
  "sources": [{"venueType": "cx", "exchange": "binance", "segment": "spot", "type": "ticker", "instruments": ["BTC/USDT", "ETH/USDT"]}],
  "paper": {"initialFunding": 1000, "feeRate": 0.001, "percentAmountToLock": 20, "output": "separate"}
}
```

The block takes the same economics as a backtest's `baseConfig` — `initialFunding`, `feeRate`
(or `buyFeeRate`/`sellFeeRate`), `feeLeg`, `percentAmountToLock` — with the same defaults and limits,
so one object moves between a backtest and a live run unchanged. Two differences:

- `initialFunding` is capped at 1,000,000,000.
- Without `percentAmountToLock`, each entry locks 10% of the account's free balance (unless the
  strategy sets its own), rather than a backtest's all-in: a live run trades several pairs at once,
  and all-in would let the first one hold the whole account.

Anything invalid — an unknown field, a wrong type, a value out of range — is a `400`. The run's own
`GET /strategy/{strategyId}/live` returns the block as accepted, with `feeRate` resolved into the two
sides and the defaults filled in.

**One account per quote currency.** A run over `BTC/USDT` and `ETH/BTC` has a `USDT` account and a
`BTC` account, each opened with `initialFunding` in its own currency. They are never added together.

**Strategies that listen to their own execution.** A strategy that overrides
`getExecutionCallback()` reacts to fills and stops, and paper trading is the only place a live run
executes. Starting one without a `paper` block is a `400`.

### Reading it

`GET /live/{runId}/paper` returns each account as last recorded:

```json
{
  "runId": "6TzAPiPpsOWwBLdLBZCxwH",
  "stage": "SANDBOX",
  "accounts": [{
    "currency": "USDT",
    "initialFunding": 1000,
    "equity": 996.4, "equityAtMs": 1758330060000, "equityKind": "mark",
    "realisedPnl": -2.1, "trades": 14, "gaps": 0,
    "openPositions": [{"instrument": "BTC/USDT", "base": 0.0023, "cost": 194.2}],
    "kpi": {"totalTrades": 14, "winRate": 0.4286, "pnlTotal": -2.1, "pnlTotalPercent": -0.21, "sharpeRatio": -0.08, "…": "…"}
  }]
}
```

`equity` is the latest value: at the last closed trade (`equityKind: equity`), or the last
mark-to-market while positions are open (`mark`, once a minute of market time). `GET
/live/{runId}/paper/equity` pages through the whole curve, oldest first; it is kept for the life of
the run, so there is no moving window as with signals. Add `currency=USDT` for one account. A
`gap` point marks a restart with positions open: those positions are not carried over, and the
curve has no value there.

Both routes follow the same access rule as the signals: the run's owner, or anyone if the run is
`public`. A run without paper trading answers `404`.

### Output: `separate` or `mix`

With `output: separate` (the default), paper trading stays out of the run's signals: read it with
the two routes above. With `output: mix`, each paper item is also written into the run's own
signals, as `type: paper`, right after the signal that caused it — `GET /live/{runId}/signals?type=paper`
reads them back. `kind` says what the item is:

| `kind` | when | `data` |
|---|---|---|
| `fill` | an order filled | `side`, `orderKind`, `price`, `amount`, `counterAmount`, `feeBase`, `feeQuote` |
| `trade` | a position closed | `side`, `entryTsMs`, `enterAmount`, `exitAmount`, `pnl` |
| `equity` | after each closed trade | `currency`, `equity` |
| `kpi` | after each closed trade | `currency` and the KPIs above |
| `mark` | once a minute of market time while positions are open | `currency`, `equity`, `realisedPnl`, `unrealisedPnl`, `openPositions` |
| `gap` | open positions lost at a restart | `currency`, `base`, `cost` |

`equity`, `kpi` and `mark` are about a whole account, so their `instrument` is `null` and
`data.currency` names the account. Paper items are recorded with the run's signals but are **not**
pushed over the WebSocket channel, whatever `relay` says.
