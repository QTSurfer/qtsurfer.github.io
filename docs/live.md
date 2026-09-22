# Live execution

Run a strategy continuously against a live market feed, watch its signals as they happen, and
change its parameters without restarting it.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/strategy/{strategyId}/live` | Start a strategy live |
| `GET` | `/strategy/{strategyId}/live` | Read this strategy's current (or last) run |
| `DELETE` | `/strategy/{strategyId}/live` | Stop it |
| `GET` | `/live/public` | Browse runs other users made public |
| `PATCH` | `/live/{runId}` | Change visibility, name, or description |
| `PUT` | `/live/{runId}/params` | Change parameters while it stays live |
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
separate REST call, open a WebSocket connection:

1. **Mint a token.** `POST /live/token` (JWT bearer, same as any other endpoint) returns a
   short-lived `token` and its `expiresAtMs`. Mint a fresh one before the current one expires or on
   a connection failure that looks auth-related.
2. **Connect.** Open a WebSocket to `wss://rt.qtsurfer.net/connection/websocket` and send, as your
   first message:
   ```json
   {"id": 1, "connect": {"token": "<the token from step 1>"}}
   ```
   A successful connect replies with your own `client` id:
   ```json
   {"id": 1, "connect": {"client": "<client-id>", "ping": 25000, "pong": true}}
   ```
3. **Subscribe to the run's signal channel**, named `sig:<runId>` — for example `sig:6TzAPiPpsOWwBLdLBZCxwH`:
   ```json
   {"id": 2, "subscribe": {"channel": "sig:6TzAPiPpsOWwBLdLBZCxwH"}}
   ```
   You may subscribe to any run's channel this way, but the connection is only actually allowed
   onto it if you own that run or it is `public` — a foreign private run's channel refuses the
   subscription. Each signal then arrives as a `push` on the channel, its `data` in the shape
   below.
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

### Signal shape

Each `push` payload on a `sig:<runId>` channel:

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
| `stage` | `sandbox` or `live` — mirrors `GET .../live`'s `stage`. |
| `paramsVersion` | The parameter set in force when this signal was produced. |
| `type` | `hint`, `info`, `marker`, or `command`. |
| `kind` | `BUY`/`SELL` for a `hint`; the command name for a `command`; absent otherwise. |
| `eventTsMs` | Market time the signal was produced. |
| `emittedAtMs` | Time it was published — always ≥ `eventTsMs`. |
| `order` | Present only for a `hint`. |
| `data` | The signal's own free-form payload. |
| `regenerated` | `true` only for a signal republished to fill a gap in the historical record — always `false` for a signal you are seeing for the first time. |
| `digest` | Content hash, for verifying two independent deliveries of the same signal agree. |

Who owns the run, which strategy or compilation produced a signal, and the exact market-data
position behind it are never included on this channel, whether the run is public or private.
