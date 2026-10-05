# Changelog

All notable changes to the QTSurfer OpenAPI contract are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). While the API is
pre-1.0, its version follows the version in `openapi.yaml`.

## [Unreleased]

## [0.128.18] — 2026-10-05

### Added

- `warmFrom` on `POST /strategy/{strategyId}/live`: how many seconds before its start a run replays the market feed from, so its indicators and windows have history when the first live tick arrives. An integer from `0` to `3600`; `0` replays nothing, so the run delivers its first signal as soon as it is running, with indicators that start empty and a first bar that can be partial; omitted, the platform replays from the start of the current 15-minute block, between 0 and 900 seconds before the run's start, as before, so the first bar of a 15-minute window is complete. It can be set only when the run is started (it is not a parameter of `PUT /live/{runId}/params`), and any other value is `400`.
- A live run reports the `warmFrom` in effect: an integer, the one requested or, when none was, the one the platform chose (0 to 900), and `null` only for a run started before the field existed. It is returned in the start response, `GET /strategy/{strategyId}/live` and `GET /live/{runId}`.
- The "Live execution" guide has a section on it, "Warming up".

## [0.128.17] — 2026-10-03

### Added

- A live run carries `stats` when you read it (`GET /strategy/{strategyId}/live` and `GET /live/{runId}`): its latest counters, refreshed about once a minute while it is being executed — updates processed (`processed`), rate (`opsPerSecond`), instruments seen (`instrumentsSeen`), when they were written (`asOfMs`), the last time `processed` grew (`progressedAtMs`) and `stale`, which says only that the platform stopped updating them. A run whose `processed` is flat is not stale: a source that updates rarely, a funding rate for example, can stay flat for hours. Absent until the first snapshot exists; starting and stopping a run do not return it. A refresh of `stats` does not move `updatedAtMs`. New schema `LiveRunStats`; documented in the live execution guide.

## [0.128.16] — 2026-10-01

### Added

- A **stream URL** for a run: pass `stream: true` to `POST /strategy/{strategyId}/live` and the response carries `streamUrl`, a secret `wss://` address a simple client, or a service that passes your signals on to others, opens as an ordinary WebSocket to receive the run's signals as plain JSON text frames, from the `sandbox` stage on. It turns `relay` on, can only be asked for when the run is started, and is available on the plans that may broadcast (any other plan gets `429`). `GET /strategy/{strategyId}/live` returns the same `streamUrl` while the run is running and the plan allows it; stopping a run and `GET /live/{runId}` never carry it (they keep returning `LiveRun`; starting a run and `GET .../live` return the new `LiveRunWithStream`).
- `POST /live/{runId}/stream` (`rotateLiveStream`) gives the run a new address and retires the old one; `DELETE /live/{runId}/stream` (`revokeLiveStream`) revokes it for good. Owner only.
- The "Live execution" guide has a section on the stream: what a frame is, `?after=<signalId>` to resume, the limits (plan on 2 connections per URL and 10 per client address), why a connection closes (`1008`, `1013`, `4001`, `1001`, `1009`), and how to keep the URL secret. The sentences that said only you can read a sandbox run now say "except through a stream URL you create".

### Changed

- `POST /strategy/{strategyId}/live` answers `400`, not `500`, for a `relay` that is not `true` or `false`, and the same for `stream`; a `stream` where streams are not available yet is also `400` ("stream is not available").
- `429` on `POST /strategy/{strategyId}/live`: a refusal for your **plan** (no live runs, a limit reached, no stream) no longer says to retry: it carries no `Retry-After`, since retrying will not help until something changes. A refusal because the platform is at capacity keeps it.

## [0.128.15] — 2026-09-30

### Added

- `GET /live/{runId}` reads one of your runs by its own id (`getLiveRun`): the state `GET /strategy/{strategyId}/live` returns, plus `updatedAtMs`, when the run last changed. Until now a run could only be read as its strategy's most recent one, or from the `GET /live` listing, which omits most of its fields. A run that is not yours answers `404`. Documented in the live execution guide.

## [0.128.14] — 2026-09-30

### Documented 📝

- The account guide lists `maxExecute`, `maxRangeDays` and `maxImportRangeHours`, the three limits `GET /account` has returned since 0.128.12, in its example and its field table.

### Added

- `GET /account` returns `maxSweepCartesian`, the largest full grid a sweep may run with the `grid` sampler. A larger grid is refused with `400`, asking for the `random` or `lhs` sampler, which are not held to it. Documented in the account and sweep guides and on `executeSweep`.

## [0.128.13] — 2026-09-29

### Changed 🔧

- **`POST /strategy/{strategyId}/live` refuses a source `type` the strategy cannot consume** with a
  `400` that names both sides (a ticker strategy with a `kline` source, or the reverse), instead of
  answering `201` and leaving a run that ends `FAILED`. A QTScript strategy is a ticker strategy
  unless its header says `kline`.
- **`reason` says why a run `FAILED`**, on `GET /strategy/{strategyId}/live` and now on each entry of
  `GET /live` (until now it appeared only for a resource stop, and only on the first). It is one of a
  fixed set of sentences, never an internal message.

### Documented 📝

- A `FAILED` run is final, but usually stays `desired: RUNNING` and counts as active (`409` on a new
  start, and toward the live-run limit) until you stop it with `DELETE`. One that can never run
  because its strategy cannot consume its source type is stopped by the platform itself
  (`desired: STOPPED`, `state: FAILED`) and holds no place.

## [0.128.12] — 2026-09-29

### Added

- `GET /account` returns `maxExecute`, `maxRangeDays` and `maxImportRangeHours` next to the dataset and storage
  limits, so every limit your account is held to can be read from one place.

## [0.128.11] — 2026-09-28

### Added ✨

- **`GET /strategies` and `GET /datasets` take `includeDeleted=true`** to also list what you have
  deleted, each entry carrying a new `deletedAt`. Without it both listings are unchanged. Useful
  to keep your own copy of the list in sync: a deleted item shows up as deleted instead of simply
  disappearing.

## [0.128.10] — 2026-09-27

### Fixed 🩹

- **A command's `properties` land as top-level entries on the strategy's `CommandRequest`, not nested
  under their own `properties` key.** `docs/strategy_coding.md`'s "Receiving commands" example read
  `Map<String, Object> properties = request.get("properties"); properties.get("instrument")` — that
  was a real design error published earlier today (0.128.9), not just wording: the runner puts every
  property directly on the request's own map, so the correct read is `request.get("instrument")`.
  Corrected, along with a note that a value keeps its JSON type (so assigning a non-string one to a
  `String` throws `ClassCastException`). The command's own text is kept as its own field, separate
  from `properties` entirely, so no property name is off limits — `cmd` included.

## [0.128.9] — 2026-09-27

### Added ➕

- **[`docs/strategy_coding.md`](docs/strategy_coding.md) documents receiving a command, in Java.** A
  "Receiving commands" section replicates what [`docs/qtscript.md`](docs/qtscript.md#handling-a-command)
  already said for QTScript — `CommandRequestHandler`, `request.getCommand()`, a command's `properties`
  map, `getStateStore(...)` from inside `handle`, and that neither a `@StrategyProperty` field nor a
  `StateStore` written there survives a restart — so the API's own docs cover the Java side directly
  instead of pointing only at the external skill. `docs/live.md`'s `Commands` section and
  `docs/qtscript.md`'s own closing note now cross-reference it.

## [0.128.8] — 2026-09-27

### Added ➕

- **`POST /live/{runId}/commands` admits an optional `properties` object alongside `command`** — a map of
  your own choosing, forwarded unchanged to the strategy's own handler; `command` and `properties` are the
  only keys the body may carry, `400` for anything else or a `properties` that is not an object.
  [`docs/qtscript.md`](docs/qtscript.md#handling-a-command) documents QTScript's own way to read it,
  `$command.<key>` sugar for a value from the map, and `getStateStore(...)`, now reachable from `onCommand`
  by a symbol a command's own properties name.

## [0.128.7] — 2026-09-27

### Changed 🔄

- **`POST /live/{runId}/commands` is not Java-only.** `docs/live.md` said a command needs a strategy "whose
  Java implements the engine's `CommandRequestHandler`" — true when 0.128.6 shipped, no longer true now that a
  QTScript strategy can implement it too, through a new `onCommand { }` section. Reworded to name both routes,
  and [`docs/qtscript.md`](docs/qtscript.md#handling-a-command) documents `onCommand { }` and `$command`. No
  change to the endpoint itself — `CommandRequestHandler` was always the actual, language-neutral contract.

## [0.128.6] — 2026-09-27

### Added ✨

- **`POST /live/{runId}/commands` tells a running strategy something without restarting it**, for a strategy
  that implements the engine's `CommandRequestHandler`: `{"command": "<text>"}`, `202` with a `commandId` and
  the market position every execution applies it at. A command is transient, unlike a parameter — nothing
  about it is stored, so a replica that restarts and replays only recent market history never sees one from
  before that window. `409` for a run that is not running, a compiled strategy with no record of whether it
  handles commands (register it again), or one that does not implement the handler at all; `503`, nothing
  sent, when it could not be delivered; `413` at 2 KiB, same convention as every other body-reading route.

## [0.128.5] — 2026-09-26

### Changed 🔄

- **A signal's `data` is public on a public run, and one over 8 KiB is not pushed.** The Live execution guide, `LiveSignal.data` and the
  Java strategy guide say that whoever may read a run may read the `data` its strategy sets on a signal, so on a `public` run it is
  public. A signal whose `data` is over 8 KiB (8,192 bytes of its JSON) is not pushed on the WebSocket channel; `GET
  /live/{runId}/signals` returns it whole. Before, the size was not bounded, and a payload past the broker's message limit was
  lost to the channel without a word.

## [0.128.4] — 2026-09-26

### Changed 🔄

- **A `200` from `POST /strategy` is said to mean "parsed and compiled", not "will run".** The QTScript guide's "When something is wrong"
  now marks the line between what registering catches (a `400` with `Line N, Column M:`) and what only `validate` can, with the case
  to know, a window on an indicator that is not registered. The same sentence is in the Strategy guide and in the `POST /strategy`
  description.

## [0.128.3] — 2026-09-26

### Changed 🔄

- **A request body over its cap is refused with the API's JSON error, naming the cap.** It was a bare plain-text `413`, with no content
  type. The Strategy guide has a table of the caps by endpoint (a strategy's source is 32 KiB, the JSON bodies of the others 1 to
  8 KiB), and `POST /strategy` documents the `413`.
- **The dataset size limit is described as what it is: a limit on the stored size.** `maxDatasetBytes` (in the guide and in `GET
  /account`) is the `bytes` of a ready version, the converted file for a CSV upload; a new "Size limits" section in the Datasets guide
  says how to estimate it from rows, and that an upload over it ends `failed` after a `202`. The `413` of `finalize` is described as
  the early check for a file many times the limit.
- **The Backtests guide says where each job's status lives:** `status` for a prepare, `state.status` for an execute and a sweep, with
  the sweep's own top-level `status` marked as a different vocabulary.

## [0.128.2] — 2026-09-26

### Changed 🔄

- **The `Live execution` guide says how long the sandbox trial lasts and what to watch while it runs.** The trial is 24 hours and
  what it checks is now listed; `stage`, `state` and `gate` are described as what a caller can poll in the meantime, with `gate`
  documented as absent until the trial ends. `state` gains its vocabulary (`STARTING`, `RUNNING`, `LAGGING`, `HUNG`, `DEGRADED`,
  `FAILED`, `STOPPED`) in the guide and in `LiveRun.state`. A table says who can read a run and whether it is listed, by
  visibility and stage, and that `relay` never decides who may read.
- `GET /live/public` is described as listing runs that have been promoted to `live` and are running; a `public` run still in the
  sandbox is not listed.
- The `409` of `PUT /live/{runId}/params` (and of the `live.params` call) now says what to do: register the strategy again with
  `POST /strategy` and start a new run. AsyncAPI `0.2.1`.

## [0.128.1] — 2026-09-26

### Changed 🔄

- **A signal produced at the promotion from `sandbox` to `live` arrives once.** `0.128.0` said such a signal could reach a
  subscriber twice, once per stage, with the same `signalId`. The two stages now split a run's signals at one instant, so each
  arrives on one side of it. The quiet spell around the promotion is unchanged. Deduplicating on `signalId` is still the right
  thing after a reconnection.

## [0.128.0] — 2026-09-25

### Changed 🔄

- **A run's owner reads it privately from the start of the sandbox.** A run started with `relay: true`
  now pushes its signals over its WebSocket channel from its first signal, in the `sandbox` stage
  too, where only its owner can subscribe; the same subscription carries on after the promotion to
  `live`, with `LiveSignal.stage` flipping from `sandbox` to `live`. The channel can stay quiet for
  several minutes around the promotion; what the run produced meanwhile then arrives in order, and a signal
  produced right at the promotion can arrive twice, once per stage, with the same `signalId`.
  `LiveRun.relay` reports the requested value in either stage (it was `false` on a `sandbox` run).
- **`visibility: public` takes effect at the promotion.** While a run is a `sandbox` trial it is read
  by its owner only, whatever visibility it asked for: the channel subscription (`103` for anyone
  else), `GET /live/{runId}/signals`, `GET /live/{runId}/paper` and `GET /live/{runId}/paper/equity`
  answer as they do for a private run, and it is not listed in `GET /live/public`. Nothing needs
  repeating at the promotion. AsyncAPI `0.2.0`.

## [0.127.0] — 2026-09-24

### Added ✨

- **Paper trading on live runs.** `POST /strategy/{strategyId}/live` accepts an optional `paper`
  block (`LivePaperConfig`): the same economics as a backtest's `baseConfig`, plus `output`
  (`separate` or `mix`). The run's hints are then executed in simulation from its first tick, with
  one account per quote currency. The run echoes the block, normalised, as `LiveRun.paper`. An
  invalid block is a `400`. A strategy that overrides `getExecutionCallback()` cannot start without
  one, also a `400`.
- `GET /live/{runId}/paper`: each paper account's starting capital, latest equity, realised PnL,
  open positions and backtest KPIs (`LivePaper`, `LivePaperAccount`, `LivePaperPosition`,
  `LivePaperKpi`).
- `GET /live/{runId}/paper/equity`: the paper equity curve, paged, optionally for one currency
  (`LivePaperEquityPage`, `LivePaperEquityPoint`).
- `GET /live/{runId}/signals` takes a `type` filter (comma-separated), which combines with
  `instrument`.
- `LiveSignal.type` gains `paper`: items a `mix` run writes into its own signals, never pushed on
  the WebSocket channel. `LiveSignal.instrument` is `null` for a paper item about a whole account.
- `docs/live_paper.md`, a guide to paper trading on live runs: configuration and sizing, accounts per
  quote currency, reading an account, the equity curve with paging, `mix` output, gaps. `docs/live.md`
  links to it.
- `SweepBaseConfig.percentAmountToLock` has a description.

### Fixed 🐛

- `GET /live/{runId}/signals`: `_links.next` now carries the `instrument` (and `type`) filter, so
  following it no longer returns the next page unfiltered.

## [0.126.2] — 2026-09-23

### Added ✨

- `GET /live` — list your own live runs, any `stage`/`desired`/`visibility`, paged the same way
  as `GET /live/public` (`cursor`/`limit`, `_links.next.href`). Unlike `GET /live/public` it needs
  a Bearer token and does not filter by state, so a `sandbox` trial or an already-stopped run
  still shows up. New schemas `LiveListResponse`/`LiveRunSummary`.

## [0.126.1] — 2026-09-23

### Added ✨

- `asyncapi.yaml` — the Live Execution WebSocket as a machine-readable contract (AsyncAPI 3.1.0,
  its own version, starting at `0.1.0`), alongside this OpenAPI spec. It names the protocol — the
  [Centrifugo](https://centrifugal.dev) v6 client protocol, JSON — so clients can use an official
  Centrifugo library, and fixes what is QTSurfer's own: the URL, `connect` with the token from
  `POST /live/token`, `sig:<runId>` channels, the signal `push`, the `live.params` RPC, `refresh`,
  ping/pong, the server unsubscribe, and the error codes (`103`, `400`, `404`, `409`). The signal
  payload and the `live.params` result are `$ref`s into this spec's `LiveSignal` and
  `LiveParamsUpdateResult`, so REST and WebSocket share one definition.
- `scripts/live_ws_conformance.py` checks it: offline, every example against its schema; live, every
  frame the running service sends.

### Fixed 🐛

- `LiveSignal.kind`, `LiveSignalOrder` and its `price`/`amount`/`stopPrice`/`trailPct` were marked
  `nullable: true`, an OpenAPI 3.0 keyword that 3.1 (and JSON Schema) ignores, so a validator
  rejected the `null` values the service actually sends. They are now `type: ['string', 'null']`
  (`['object', 'null']` for `order`). Generated clients may change these fields' types to optional.
- `docs/live.md` gave the connect reply's `ping` as `25000`; the service answers in seconds (`25`).
  The guide now also covers what a client needs to stay connected: answering pings, refreshing the
  token on the same connection, the `push` frame around each signal, and being unsubscribed when a
  run turns private.

## [0.126.0] — 2026-09-23

### Added ✨

- `GET /live/{runId}/signals` — read the signals a run has already produced, page by page. The
  real-time channel only carries what happens while you are connected, and only for a run that
  asked for `relay`; signals are recorded either way, so this serves them whether or not `relay`
  was ever on, in both the `sandbox` and `live` stages.
  - Optional `instrument` filter: a pair (`BTC/USDT`), either half wildcarded (`*/USDT`, `BTC/*`),
    or a comma-separated list. Symbols match exactly, case included.
  - `sinceMs`, `cursor` and `limit` (default 20, max 100) for positioning and paging; entries come
    back in the same shape the signal channel pushes.
  - Every response carries `availableSinceMs`, the oldest moment still readable. The window moves
    as older signals are discarded, so a `sinceMs` earlier than that is served from
    `availableSinceMs` rather than rejected.
  - A cursor whose position has since been discarded answers `410` (with that `availableSinceMs`
    in the message) instead of silently returning a shortened page. On a busy run this is an
    ordinary outcome of paging, not a failure — see [`docs/live.md`](docs/live.md).

## [0.125.2] — 2026-09-22

### Fixed 🐛

- `LiveRun.relay` now reflects a promoted run's real state — it used to always report `false`, even
  once relay was genuinely active on a `live` run. `StartLiveRequest` was also missing its own
  `relay` field: the flag was already accepted by `POST /strategy/{strategyId}/live`, just absent
  from the spec. See [`docs/live.md`](docs/live.md) for the stage rule around it.

## [0.125.1] — 2026-09-22

### Changed 🔄

- The request/response bodies inline on `POST /strategy/{strategyId}/live`, `PATCH /live/{runId}`,
  `PUT /live/{runId}/params`, and `GET /live/public`'s pagination wrapper are now named schemas
  (`StartLiveRequest`, `UpdateLiveRequest`, `UpdateLiveParamsRequest`, `PublicLiveListResponse`)
  instead of anonymous inline objects — same shapes, only how they're named in the spec changes.

## [0.125.0] — 2026-09-22

### Added ✨

- **Live execution**, a new endpoint group: run a strategy continuously against a live market feed
  instead of a fixed historical window.
  - `POST`/`GET`/`DELETE` `/strategy/{strategyId}/live` — start, inspect, and stop a run. A new run
    starts in a `SANDBOX` trial and is promoted to `LIVE` automatically once it passes.
  - `GET /live/public` — browse other users' runs marked `public`, without revealing who owns them.
  - `PATCH /live/{runId}` — change a run's visibility, name, or description.
  - `PUT /live/{runId}/params` — change a running strategy's parameters without restarting it.
  - `POST /live/token` — mint a token for the WebSocket connection that streams a run's signals in
    real time and carries the `live.params` RPC (the WebSocket form of the `PUT` above). See
    [`docs/live.md`](docs/live.md) for the full protocol.

## [0.124.0] — 2026-09-21

### Added ✨

- `DataSourceType` is now `ticker`, `kline` or `funding` (it was `ticker`). `kline` can be prepared,
  executed and swept — walk-forward included — over bars of the `cadence` the data was prepared at.
  The bar width is the caller's choice at prepare time, not the strategy's, so one strategy can be
  run at several cadences. For `kline`, `PrepareRequest.cadence` accepts `1s` (the default), `1m`,
  `5m`, `15m`, `30m`, `1h`, `4h` and `1d`; any other label is `400` and the message lists them.
- `funding` can be prepared, but `execute` and `executeSweep` reject it with `400` before anything
  is queued (`funding data can be prepared but not executed yet`), naming the sources that can be
  run. Running funding-rate strategies is not available yet.

### Changed 🔄

- The strategy endpoints describe both languages a source can be written in: Java, and QTScript
  (beta), a compact language whose braced bodies are plain Java, told apart by starting with
  `strategy`. Descriptions only — no request or response changes. One statement changes with it:
  `strategyId` ignoring comments and re-indentation holds for Java, not for QTScript, where
  indentation is part of the grammar; the QTScript rules are spelled out on `POST /strategy`.

## [0.123.0] — 2026-09-17

### Added ✨

- `Dataset` gains `status` (`ready`/`failed`/`pending`, always present) plus `bytes`/`rows`/`gaps`/
  `largestGapSteps` (present when `status` is `ready`) and `error` (present when `status` is
  `failed`) — mirrors what `DatasetUploadState`/`DatasetVersion` already report for a specific
  upload/import, now also on `GET /datasets` and `GET /datasets/{datasetId}` without needing an
  `uploadId`/`importId`. Backward-compatible: purely additive fields, `currentVersionId`'s own
  semantics unchanged.

## [0.122.0] — 2026-09-16

### Added ✨

- Dataset uploads now accept a `lastra` file (our own native columnar format — the same one a
  dataset's `dataUrl` hands back by default) in addition to CSV and parquet. A `lastra` upload is
  stored as-is, same as parquet today, so downloading a dataset and handing that exact file to
  another user to upload works with no conversion in between.

### Changed

- `dataFormat` on `DatasetVersion`/`GetDatasetResult` clarified: `lastra` can now mean either a
  converted CSV upload or an unconverted lastra upload — the value alone no longer implies how the
  data was originally uploaded.

## [0.121.0] — 2026-09-12

### Added ✨

- `GET /account` — your identity, current tier, and that tier's limits (`maxDatasets`,
  `maxDatasetBytes`, `maxTotalStorageBytes`). No database call behind it, safe to fetch on every
  page load.
- `GET /account/usage` — your live storage usage against `maxTotalStorageBytes`: datasets,
  strategy-execution signals, and registered strategies all count against one shared pool, not a
  cap per resource type, since they compete for the same underlying storage.
- `429` on `POST /datasets/{datasetId}/uploads/{uploadId}/finalize` and `POST /datasets/imports`
  when the account's total storage limit is reached or would be exceeded — see
  [Account](docs/account.md) and [Datasets](docs/datasets.md).

## [0.120.0] — 2026-09-12

### Added ✨

- `Dataset` (and `DatasetWithLinks`) gains `timestampUnit`, mirroring `from`/`to`/`cadence` from
  the current version — a dataset viewer can now decode the `timestamp` column of `dataUrl`'s file
  without a second call to `GET .../uploads/{uploadId}`.

### Fixed 🐛

- `POST /datasets/imports`'s docs previously said an unsupported cadence/network combination fails
  asynchronously; it's actually silently ignored (the import falls back to native cadence).
  Corrected in [Datasets](docs/datasets.md); `dex.id`/`dex.version` are documented as required in
  that fallback case too.

## [0.119.0] — 2026-09-11

### Added ✨

- `executeBacktest` (`POST .../execute`) accepts `baseConfig`, the same `SweepBaseConfig` shape
  `executeSweep` already accepts (`initialFunding`, `feeRate`/`buyFeeRate`/`sellFeeRate`, `feeLeg`,
  `percentAmountToLock`) — a client can send the identical object to either endpoint. This endpoint
  has one effective fee rate rather than a sweep's independent buy/sell legs: a `baseConfig` that
  implies asymmetric buy/sell fees, or a non-default `feeLeg`, is rejected with `400`.

### Changed 🔄

- `SweepBaseConfig.initialFunding`'s default is `100` (was `10000`) — same default capital on both
  `executeBacktest` and `executeSweep`. The default fee rate is unchanged.

## [0.115.1] — 2026-09-07

### Changed 🔄

- `ScalarStrategyParamValue` names the scalar values accepted by `executeBacktest.params` and
  returned in `ResultMap.params`. The JSON contract is unchanged; generated clients now expose a
  stable component-derived type instead of a path-derived anonymous model.

## [0.115.0] — 2026-09-07

### Added ✨

- Dataset resources and completed upload versions can expose `dataUrl`, a presigned URL for the
  stored data, and `dataFormat`, which identifies that data as `lastra` or `parquet`.
- Dataset upload accepts a CSV or parquet file directly, or a gzip/zip containing exactly one of
  those files.

### Changed 🔄

- `DatasetVersion.bytes` now describes the stored data rather than the originally uploaded bytes.
  Read `dataFormat` before choosing a reader.
- `JobState.size` is an upfront estimate for single executions and plain sweeps; a value of `0`
  identifies contexts predating the estimate, or walk-forward sweeps where it is not calculated.
- `deflatedSharpe` is absent when it cannot be meaningfully computed, rather than a zero value.
