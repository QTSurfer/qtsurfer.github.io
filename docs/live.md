# Live execution

Run a strategy continuously against a live market feed, watch its signals as they happen, and
change its parameters without restarting it.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/strategy/{strategyId}/live` | Start a strategy live |
| `GET` | `/strategy/{strategyId}/live` | Read this strategy's current (or last) run |
| `DELETE` | `/strategy/{strategyId}/live` | Stop it |
| `GET` | `/live` | List your own runs |
| `GET` | `/live/{runId}` | Read one of your runs by its id |
| `GET` | `/live/public` | Browse runs other users made public |
| `PATCH` | `/live/{runId}` | Change visibility, name, or description |
| `PUT` | `/live/{runId}/params` | Change parameters while it stays live |
| `POST` | `/live/{runId}/commands` | Tell it a command while it stays live |
| `GET` | `/live/{runId}/signals` | Read the signals it has already produced |
| `GET` | `/live/{runId}/paper` | Read its paper trading — see [Paper trading](live_paper.md) |
| `GET` | `/live/{runId}/paper/equity` | Page through its paper equity curve — see [Paper trading](live_paper.md) |
| `POST` | `/live/token` | Mint a WebSocket connection token |

## Lifecycle: sandbox, then live

Starting a run (`POST /strategy/{strategyId}/live`) never puts it in front of anyone but you. It
begins in the `sandbox` stage, a trial of **24 hours**. During it the platform runs an independent
second execution of your strategy beside the first and checks four things: that the run is
processing market data, that its memory use and per-tick time stay within the platform's allowance,
that it does not hang or fail repeatedly, and that the two executions produce the same signals.
Only you can read a sandbox run: over the WebSocket channel from its first signal if you asked for
`relay`, and through the read routes either way (see [Visibility](#visibility)) — and through a
[stream URL](#a-plain-websocket-stream-of-a-run) if you create one for it, which lets whoever you give it
to read the run's signals from the sandbox on.

A run that passes is promoted to `live` automatically when the 24 hours are up. There is no
separate "promote" call and nothing for you to do while you wait. A run that does not pass is not
promoted, and keeps running in the sandbox.

### Starting again does not repeat the trial

A strategy that has been through the trial once does not go through it again. When you stop a run
that was promoted and start the strategy again, the new run begins in `live` at once, with no
24-hour wait. That holds when an earlier run of yours of **the same compiled strategy** was
promoted, and none of that compilation's runs was stopped for using more resources than allowed.
The parameters, sources and instruments of the new run may differ from the earlier one. If you submit
the strategy again (`POST /strategy`) it is compiled anew, and the new compilation goes through the
sandbox like a first run.

What changes for such a run:

- `stage` is `LIVE` in the response to the start, and `gate` is there from the start: the verdict of
  the earlier run it relies on, with `inheritedFrom` naming that run.
- Nothing compares a second execution against it, because there is no trial. The platform stops a
  live run that uses more resources than allowed, as it does any other (see
  [State of a run](#state-of-a-run)).
- If it is `public`, it is in the catalogue and open to anyone from its first signal.
- It has no history on the connection: that is kept for the `sandbox` stage only (see
  [Reading earlier signals over the connection](#reading-earlier-signals-over-the-connection)). Its
  signals are still readable through `GET /live/{runId}/signals`.

To get the sandbox anyway — to debug a strategy, or to read its signals back over the connection —
start it with `"sandbox": true`. For a strategy that has not been through the trial the field changes
nothing: it always starts in the sandbox.

What you can watch while it waits, on `GET`/`PATCH` `.../live`:

- `stage` is `SANDBOX` until the promotion and `LIVE` after it (`LIVE` from the start for a strategy
  that has already been through the trial, see above).
- `state` is the run's health right now (see [State of a run](#state-of-a-run)).
- `gate` is **absent for the whole trial** and appears when it ends, holding the verdict. An
  absent `gate` therefore means "the trial has not finished", never "nobody is evaluating the
  run". Its `passed` field is the verdict; the rest is diagnostic detail whose shape may change.
  A run that started in `live` has it from the start (see above).

## State of a run

`state` says what the run is doing. It is a string that may gain values, so read an unknown one as
"running, with something to look at".

| `state` | What it means |
|---|---|
| `STARTING` | Accepted; no runner has reported on it yet. |
| `RUNNING` | Running normally. |
| `LAGGING` | Running, but behind the market data: usual while it catches up after starting or after a platform restart. It clears by itself. |
| `HUNG` | Your strategy is stuck inside one call for longer than the platform allows. It clears when that call returns. |
| `DEGRADED` | The run's independent executions produced different signals from the same market data. The run keeps publishing. In the sandbox this counts against the trial: the run is not promoted. |
| `FAILED` | The platform refused the run, could not start it, or the run failed while running. `reason` says why (see [Why a run failed or stopped](#why-a-run-failed-or-stopped)). |
| `STOPPED` | Stopped, by you or by the platform (`reason` says so when it was for exceeding its resource allowance). |

`LAGGING`, `HUNG` and `DEGRADED` are flags on a run that is otherwise running: they come and go, and
the run's signals keep flowing throughout. `desired` is what you last asked for (`RUNNING` or
`STOPPED`), and `state` can trail it briefly.

Only one run per strategy at a time. Starting again while one is `RUNNING` is `409` — stop it
first with `DELETE`.

A stop (`DELETE`) is a request, not an instant kill: `desired` flips to `STOPPED` immediately, but
`state` can stay `RUNNING` for a short window while the run winds down. Calling `DELETE` again on
an already-stopped run is not an error.

### A failed run is final, and still holds its place

`FAILED` is final for that run: it is not processing data and nothing restarts it. To try again,
fix what `reason` names and start a new run. Usually `desired` stays `RUNNING` until you stop the
run yourself, and a run counts as active by its `desired`, not its `state`: a `FAILED` run still
answers `409` to a new start of the same strategy and still counts toward your plan's live-run
limit. Call `DELETE` on it, then start again.

The exception is a run that can never run because of what it was started with: when its strategy
cannot consume its source type, the platform stops it itself (`desired` becomes `STOPPED`, `state`
stays `FAILED`, `reason` says why), so it does not hold a place.

### Why a run failed or stopped

`GET /strategy/{strategyId}/live`, and each entry of `GET /live`, carry a `reason` when there is
one to give. It is absent otherwise, and it is never a stack trace or an internal message: it is
one of a fixed set of sentences, so a client can match on it.

| `reason` | When |
|---|---|
| `resource: ...` | The platform stopped the run for exceeding its resource allowance; the text says which limit. |
| `The run could not start: its strategy cannot consume the source type it was started with.` | A ticker strategy started with a `kline` source, or the reverse. Start refuses this with a `400` (see [Sources](#sources)); it can only show up on a run created before that check existed. |
| `The run could not start: its definition was refused.` | The run's definition is not one the platform can run. |
| `The run could not start after several attempts.` | A start that kept failing for a reason that was not yours. Start again. |
| `The run stopped because its strategy failed while processing data.` | Your strategy's own code brought the run down. |
| `The run stopped because it lost its data feed.` | The run's market data stream broke and the run stalled. |
| `The run failed.` | Anything else. |

The set may grow. Read an unrecognised sentence as "the run failed", and do not parse it for
detail: the text is for people.

## What a run is doing: `stats`

While a run is being executed the platform keeps its latest counters and refreshes them about once a
minute. `GET /strategy/{strategyId}/live` and `GET /live/{runId}` return them as `stats`:

```json
"stats": {
  "processed": 18233,
  "opsPerSecond": 4.2,
  "instrumentsSeen": 12,
  "asOfMs": 1758330060000,
  "progressedAtMs": 1758330060000,
  "stale": false
}
```

| Field | What it means |
|---|---|
| `processed` | Updates of instruments the run has accepted since it started executing. It can start again from zero if the run is restarted. |
| `opsPerSecond` | Updates accepted per second over the last refresh. An average over about a minute, so it does not jump from one update to the next. `0` when none arrived. |
| `instrumentsSeen` | Distinct instruments the run has received an update for. |
| `asOfMs` | When these counters were last written. |
| `progressedAtMs` | The last refresh in which `processed` had grown. Absent until the run has processed anything. |
| `stale` | `true` when the run is meant to be running and its counters have not been refreshed for several refresh intervals. |

Three things to know:

- **`stats` is absent, not zero, when there is nothing yet**: a run that has just started has no
  snapshot. Starting (`POST`) and stopping (`DELETE`) a run do not return it; read it with one of the
  two `GET`s above.
- **`stale` only says the platform stopped updating the counters.** Check it against `state`. A run
  whose `processed` stays flat is *not* stale and is not broken: one fed by a source that updates rarely
  (a funding rate, for example) can stay flat for hours. `progressedAtMs` is how to tell such a run from
  one that has stopped.
- **A refresh of `stats` is not a change of the run.** It does not move `updatedAtMs`.

## Sources

`sources` takes exactly one entry (multi-source strategies are not supported yet):

```json
{
  "sources": [
    {"venueType": "cx", "exchange": "binance", "segment": "spot", "type": "ticker", "instruments": ["BTC/USDT"]}
  ]
}
```

`type` has to match the kind of strategy: a ticker strategy runs on a `ticker` source and a kline
strategy on a `kline` one, and a start with the other one is refused with `400`, naming both. A
QTScript strategy is a ticker strategy unless its header says otherwise (`strategy "Name" kline`);
a Java one is whichever base class it extends (`AbstractTickerStrategy` or `AbstractKlineStrategy`).

`type` is `ticker` or `kline`. Both connect to the lightest (fastest) cadence available for the
exchange — today that is 1 tick/second on every supported exchange; choosing among several
cadences is not offered yet.

`instruments` can be left out. A QTScript strategy can declare which instruments it accepts with an `instruments`
line in its source. When the compilation of the strategy records that selection as a list of pairs, a
start that leaves `instruments` out, or sends `["*"]`, takes that list; otherwise the run reads every
instrument the exchange/segment offers, subject to your plan's instrument-count limit:

```json
{
  "sources": [
    {"venueType": "cx", "exchange": "binance", "segment": "spot", "type": "ticker"}
  ]
}
```

A list of instruments is taken as sent, and `[]` and `null` are refused with `400`.

Write instruments as `BASE/QUOTE`. They are not case-sensitive and spaces around them are ignored, so
`btc/usdt`, `BTC/USDT` and `" btc / usdt "` are the same instrument. Either side can be `*` to mean any:
`*/USDT` is every pair quoted in USDT and `BTC/*` is BTC against every quote. An entry that is not of that
form (no `/`, an empty side, a `.` or a space inside a side, or a `*` mixed with other characters of a side)
makes the run fail when it starts. Against your plan's limit, a list with an entry that has a `*` on a side
counts like `["*"]`, and only plans that include the wildcard accept it; the other entries are counted one by one.

The instruments the run actually reads come back in the run's `sources`: a run started without `instruments`
shows the list it got, which can have entries like `*/USDT`.

## Warming up: `warmFrom`

A strategy that reads an average, a window or any other indicator needs some history before its values
mean anything: the average of the last 50 prices has nothing to average on its first tick. So a run is
started **warm**. Before its first live tick it replays the market feed from a moment shortly before the
run's start, and the strategy sees that stretch first, as if it had been running. While it catches up, the
run can show `LAGGING`, and its first signal reaches the channel and the stream only once it has caught up.
Signals about the replayed time describe events from before the run started, so they are not pushed.

`warmFrom` is how you choose how much to replay: the number of **seconds before the run's start** to
replay from. Set it in the body of `POST /strategy/{strategyId}/live`, next to `sources`:

```json
{
  "sources": [
    {"venueType": "cx", "exchange": "binance", "segment": "spot", "type": "ticker", "instruments": ["BTC/USDT"]}
  ],
  "warmFrom": 300
}
```

| `warmFrom` | What happens |
|---|---|
| omitted | The platform replays from the start of the current 15-minute block: between 0 and 900 seconds before the run's start, depending on when it starts (0 if it starts exactly on a quarter hour). The first bar of a 15-minute window is then complete. |
| `0` | No replay. The run starts at its start: it delivers its first signal as soon as it is running, with indicators that start empty and a first bar of a window that can be partial. |
| `1` to `3600` | The strategy sees that many seconds of the feed before the start, then carries on live. |

- It is an integer number of seconds from `0` to `3600` (one hour). Anything else (a negative number, one
  above `3600`, a fraction, text) is refused with `400`.
- Choose it for what the strategy needs. A strategy with long indicator periods should ask for at least the
  time its slowest indicator takes to fill: with `0`, its first values are computed on whatever has arrived
  since the start, and left out, the replay can be as short as `0` seconds (a run that starts exactly on a
  quarter hour) and never longer than `900`.
- It can be set **only when the run is started**. It is not one of the parameters `PUT /live/{runId}/params`
  accepts, and it cannot be added later: to change it, stop the run and start it again.
- The run reports the value in effect back as `warmFrom` when you read it (the start response,
  `GET /strategy/{strategyId}/live` and `GET /live/{runId}`; the response to stopping a run does not carry it): the one you asked for or, if you left it out, the
  one the platform chose. Send that number to get the same amount of warm-up in another run. A run started
  before this field existed has no `warmFrom` at all; it is never `null`.

## Listing your runs

`GET /live` (needs a Bearer token) returns every run you have started — any `stage`, any
`desired` state, any `visibility` — newest first, paged the same way as `GET /live/public`
(`cursor`/`limit`, `_links.next.href`). It does not filter by `state`: a `sandbox` trial or a
run you have already stopped still shows up, unlike `GET /live/public`, which needs no
`Authorization` header but only ever lists other runs — anyone's, yours included — that are
`public` and currently `RUNNING`.

## Reading one run

`GET /live/{runId}` (needs a Bearer token) returns one of your runs by its own id, whatever its
`stage`, `desired` state or `visibility` and however long ago you stopped it: the same state
`GET /strategy/{strategyId}/live` gives, plus `updatedAtMs`, when the run last changed. That value
only moves forward, so when you keep your own copy of a run, apply a read only if its `updatedAtMs`
is larger than the one you hold. A run that is not yours, or does not exist, answers `404`; a run
someone made public is found through `GET /live/public`, not here.

## Visibility

A run is `private` by default — only you can read its state or receive its signals. Setting
`visibility: public` (via `PATCH /live/{runId}`) does two things:

- it appears in `GET /live/public`'s catalogue, listed without revealing who owns it or which
  strategy runs it;
- its signal channel (see below) accepts a WebSocket subscription from anyone, not only you.

`public` is what you ask for, and it takes effect when the run is in the `live` stage: when it is promoted, or at once for a run that starts there. Until then —
while it is a `sandbox` trial — only you can read it, over the channel and through the read routes,
and it is not listed in the catalogue; nothing you did needs repeating at promotion.

Who can read what, by run:

| The run | Subscribe to its channel, and read `.../signals`, `.../paper` | Listed in `GET /live/public` |
|---|---|---|
| Any run of yours | You, always | — |
| `private` | Only you | No |
| `public`, still in the `sandbox` | Only you (`public` takes effect at the promotion) | No |
| `public`, promoted to `live` | Anyone | Yes, while it is running |

A [stream URL](#a-plain-websocket-stream-of-a-run) is separate from all of this: it is a secret you
create for one run, and whoever holds it can read that run's signals in either stage, whatever its
`visibility` says. You decide who holds it.

`relay` is separate: it only decides whether a run's signals are *pushed* over the WebSocket
channel (opt-in, in either stage) and never who may read them. `GET /live/{runId}/signals` serves
a run's signals whether or not you asked for `relay`.

Switching back to `private` also disconnects anyone else currently subscribed to that channel —
best-effort, and it does not undo the visibility change if the disconnect itself fails.

## Runtime parameters

`params` on `POST /strategy/{strategyId}/live` only sets the values a run **starts** with. To
change one while the run keeps running, call `PUT /live/{runId}/params` (or the equivalent
`live.params` WebSocket call below — both go through the same validation and land on the identical
value at the identical moment). Every key must be one your strategy declares; an undeclared key is
`400`.

A `409` means this run's compiled strategy has no record of the parameters it declares, so they
cannot be changed while it runs. A run keeps the compiled version it started with: register the
strategy again (`POST /strategy` with the same source, which compiles it afresh) and start a new
run.

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

## Commands

`POST /live/{runId}/commands` tells a running strategy something without restarting it, for a strategy that
implements the engine's `CommandRequestHandler` — a Java strategy directly (see [Coding Java
strategies](strategy_coding.md#receiving-commands)), or a QTScript strategy through `onCommand { }` (see
[QTScript](qtscript.md#handling-a-command)). It takes
`{"command": "<text>"}` — a plain string — and an optional `properties` object of your own choosing alongside
it, which travels unchanged to the strategy's own handler; `command` and `properties` are the only keys the
body may carry. It answers `202` with `commandId` and `effectiveAtMs`, the market position every execution
behind the run applies it at.

**A command is transient**, unlike a parameter: it is an event, not a stored value, and nothing about it is written
to the run. A replica that restarts replays only its recent market history, so a command from before that window
never reaches it — a peer that was already running when it arrived applies it, one that starts later does not.
Anything the strategy needs to remember across a restart belongs in a parameter (`PUT /live/{runId}/params`), which
does have a stored value.

A `409` means one of three things, each its own message: the run is not running; this run's compiled strategy has
no record of whether it handles commands (register the strategy again and start a new run, same as the `409` on
`params`); or the strategy does not implement `CommandRequestHandler` at all. A `503` means the command could not be
delivered right now and was **not** sent — there is no fallback path for an event the way there is for a parameter
row, so retry the request itself.

```
POST /live/6TzAPiPpsOWwBLdLBZCxwH/commands
{"command": "flatten", "properties": {"instrument": "BTC/USDT"}}

202
{"runId": "6TzAPiPpsOWwBLdLBZCxwH", "commandId": "0e3f2f1a-9c4b-4d3e-8a2f-6b7c5d4e3f21", "effectiveAtMs": 1758330015000}
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
default `false`). They reach it from the run's first signal, in the `sandbox` stage too, where only
you can subscribe to it; the same channel carries on unchanged once the run is promoted to `live`,
on the same subscription: `stage` flips from `sandbox` to `live` and nothing needs redoing. The run
takes a while to start in the `live` stage, so the channel can stay quiet for several minutes around
the promotion; what the run produced meanwhile then arrives in order, and each signal arrives once.
`GET`/`PATCH .../live` echo back what was requested as the run's own `relay` field.

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
   onto it if you own that run, or it is `public` **and** has reached the `live` stage — a foreign
   private run's channel, and a public run that is still in the `sandbox`, refuse the subscription
   with `{"id": 2, "error": {"code": 103, "message": "permission denied"}}`. Each
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

After a disconnect, the channel does not replay what you missed on its own: read it back with `history`
while the run is in the `sandbox` stage ([next section](#reading-earlier-signals-over-the-connection)), or
with `GET /live/{runId}/signals` (below) in either stage, deduplicating on `signalId`.

### Reading earlier signals over the connection

A client that connects late, or that was disconnected for a moment, can read the signals a run in the
`sandbox` stage has just produced from the same connection, without a REST call. Send `history` on a
channel you are subscribed to:
```json
{"id": 5, "history": {"channel": "sig:6TzAPiPpsOWwBLdLBZCxwH", "limit": 300}}
```
It answers with the signals, oldest first, each with the `offset` it was pushed with, and the `epoch` and
the newest `offset` the channel holds:
```json
{"id": 5, "history": {"publications": [{"data": {"v": 1, "signalId": "…", …}, "offset": 41}, {"data": {"v": 1, "signalId": "…", …}, "offset": 42}], "epoch": "SQRGfEAq", "offset": 42}}
```

- **What it holds.** The signals of the `sandbox` stage only: the 300 most recent, whatever their age,
  until 5 minutes after the run's last `sandbox` signal, when it empties. Nothing from the `live` stage is
  kept: once a run is promoted the history stops growing, and it empties 5 minutes after the last
  `sandbox` signal. To read further back, or any `live` signal, use `GET /live/{runId}/signals` (below).
  A run that starts in `live` (see [Starting again does not repeat the trial](#starting-again-does-not-repeat-the-trial))
  never has a history here; start it with `"sandbox": true` if you need one.
- **Nothing is replayed on its own.** Subscribing, and resubscribing after a disconnect, never delivers
  past signals; `history` is the only way to read them.
- **Who can read it.** A connection that is subscribed to the channel; while a run is in the `sandbox`
  stage that is its owner. A connection that is not subscribed gets error `103`.
- **How to use it.** Subscribe first, so that nothing is missed, then call `history` with `limit` `300`.
  The signals pushed meanwhile and the ones in the reply overlap: keep one copy per `signalId`.
- **After a disconnect.** Resubscribe, then call `history` with `since`: the `offset` of the last signal
  you have and the `epoch` of a previous `history` reply:
  ```json
  {"id": 6, "history": {"channel": "sig:6TzAPiPpsOWwBLdLBZCxwH", "limit": 300, "since": {"offset": 42, "epoch": "SQRGfEAq"}}}
  ```
  The reply holds only the signals after that position. A client that has not called `history` yet has
  no `epoch`: call it once without `since`.
- **When the history is lost.** If the platform loses the channel's history (for example when the
  real-time service restarts) its `epoch` changes, and a `since` with the old one answers
  `{"id": 6, "error": {"code": 112, "message": "unrecoverable position"}}`. Call `history` again without
  `since`; what was produced before the loss is only available from `GET /live/{runId}/signals`.
- `limit` `0` returns no signals, only the position (`epoch` and `offset`).

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
| `stage` | `sandbox` or `live`: the stage the run was in when it produced the signal. Only you receive a `sandbox` signal on this channel; everyone allowed onto the channel receives `live` ones. |
| `paramsVersion` | The parameter set in force when this signal was produced. |
| `type` | `hint`, `info`, `marker`, or `command` — plus `paper` when reading a `mix` run's history (see [Paper trading](live_paper.md#output-separate-or-mix); paper items are never pushed on this channel). |
| `kind` | `BUY`/`SELL` for a `hint`; the command name for a `command`; absent otherwise. |
| `eventTsMs` | Market time the signal was produced. |
| `emittedAtMs` | Time it was published — always ≥ `eventTsMs`. |
| `order` | Present only for a `hint`. |
| `data` | The signal's own free-form payload: what the strategy put there with `signal.set(...)`. Whoever may read the run may read it, so on a `public` run it is public. A signal whose `data` is over 8 KiB (8,192 bytes of its JSON) is not pushed on this channel; [the history route](#reading-signals-a-run-already-produced) returns it whole. |
| `regenerated` | `true` only for a signal republished to fill a gap in the historical record — always `false` for a signal you are seeing for the first time. |
| `digest` | Content hash, for verifying two independent deliveries of the same signal agree. |

Who owns the run, which strategy or compilation produced a signal, and the exact market-data
position behind it are never included on this channel, whether the run is public or private.

## A plain WebSocket stream of a run

The connection above is a protocol: a token, a subscription, frames of its own. A **stream URL** is the
simple alternative. It is one address that you open as an ordinary WebSocket — from a script, a command-line
tool such as [`websocat`](https://github.com/vi/websocat), or a service of your own that passes your signals on
to others — and each signal of the run arrives as **one JSON text frame**. There is no token to mint, nothing
to subscribe to and nothing to send.

It is meant for your own tests, for simple clients, and for services that pass your signals on to many
connections themselves: this address is limited in how many connections it accepts (see below), so a service
that serves many readers holds one connection and fans the signals out itself.

It is available from the `sandbox` stage on, so you can try it before the run is promoted, on the plans that
may broadcast (the Pro and Elite plans: your plan is the `tier` that [`GET /account`](account.md) returns).
Any other plan is refused with `429`, naming the plan.

### Getting one

Ask for it **when you start the run**, with `stream: true` in `POST /strategy/{strategyId}/live`. It turns
`relay` on, and it cannot be added to a run later. The response carries the address as `streamUrl`:

```json
{
  "runId": "5t5oAmQ4PD0lQRoCU58uE0",
  "stage": "SANDBOX",
  "relay": true,
  "streamUrl": "wss://…"
}
```

`GET /strategy/{strategyId}/live` returns the same `streamUrl` for as long as the run is running and your plan
allows it. It is in no other response: not when the run is stopped, not in `GET /live/{runId}`, and not in the
public catalogue. Use the address exactly as it is returned; it is opaque.

**Treat it like a password.** Anyone who holds it can read the run's signals, sandbox ones included. Do not put
it in a repository, a log, a screenshot or a shared chat. If it may have leaked, [rotate it](#rotating-and-revoking-it).
You are responsible for who you give it to and for what is done with the signals you pass on.

### What arrives

Each text frame is exactly one signal, the same object as the `pub.data` of a `sig:<runId>` channel push (see
[Signal shape](#signal-shape)), `stage` included, so a receiver can tell a sandbox trial from the real thing.
There is no connect message and no wrapper around it, and nothing to answer: your WebSocket library answers
the pings the service sends. A signal whose `data` is over 8 KiB is not sent, as on the channel.

```bash
websocat "$STREAM_URL"
```

Anything you send is ignored, and a frame from you over 1 KiB closes the connection.

### Reconnecting

Connections do end (a restart of the service, a network blip), so a client reconnects. To resume without
gaps, add the `signalId` of the last signal you received as a query parameter, `?after=<signalId>`: the service
sends the signals that came after that one, then carries on live, each signal once.

It keeps only the most recent signals of a run, **about the last few minutes** and fewer for a run whose
signals are large. If the signal you name is no longer held, the connection is closed with `4001` before any
frame is sent: read what you missed with [`GET /live/{runId}/signals`](#reading-signals-a-run-already-produced),
then connect again without `after`. Whatever you do, de-duplicate by `signalId`.

### Limits, and why a connection closes

- Plan on **2** connections open at once on one URL (the second covers the overlap while you reconnect), and
  **10** from one client address. They are the numbers to design for, not exact walls: the service counts connections
  in more than one place, so one past them is sometimes accepted. A connection that is refused is closed with `1013` once it is
  open, or turned away before it opens, when the handshake itself fails (with `429`, or with a gateway error such as `502`).
- A reader that does not keep up is disconnected; it never slows anyone else down.
- A client address that keeps presenting URLs that do not work is refused for a while (`429`).

An address that is not a valid stream URL, or one that has stopped working, answers `404` to the connection
attempt, never saying which; `503` means try again in a moment. Once open, a connection can be closed with:

| Code | Meaning | What to do |
|---|---|---|
| `1008` | The URL no longer works: it was rotated or revoked, the run stopped, or your plan no longer lets you broadcast. | Do not retry the same URL. Read `GET /strategy/{strategyId}/live` for the current one. |
| `1013` | Too many connections on this URL or from this address, the connection could not keep up, or the service could not confirm the URL for a moment. | Wait and reconnect, with `after`. |
| `4001` | The signal in `after` is no longer held. | Read the history, then connect without `after`. |
| `1001` | The service is restarting. | Reconnect right away, with `after`. |
| `1009` | You sent a frame over 1 KiB. | Do not send frames. |

If your plan stops letting you broadcast, the URL is no longer shown and open connections are closed with
`1008`, typically within a minute; if the plan lets you broadcast again, the same URL works again.

### Rotating and revoking it

- `POST /live/{runId}/stream` gives the run a **new** address and retires the old one: connections on the old
  address close with `1008` within about 15 seconds. Only for a running run that was started with a stream.
- `DELETE /live/{runId}/stream` revokes it **for good**: connections close and the address answers `404`. The
  run itself keeps running, and a stream cannot be added to it again: start the run again with `stream: true`
  for a new one. It is always allowed, whatever your plan, and repeating it is not an error.

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

Start a run with a `paper` block and its hints are executed in simulation from its first tick, as a
backtest would execute them — fills, closed trades, equity and the same KPIs a backtest reports:

```json
"paper": {"initialFunding": 1000, "feeRate": 0.001, "percentAmountToLock": 20}
```

Read it back with `GET /live/{runId}/paper` and `GET /live/{runId}/paper/equity`. Everything about it
— the configuration, one account per quote currency, the equity curve, `mix` output and gaps — is in
**[Paper trading on live runs](live_paper.md)**.
