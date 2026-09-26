# Changelog

All notable changes to the QTSurfer OpenAPI contract are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). While the API is
pre-1.0, its version follows the version in `openapi.yaml`.

## [Unreleased]

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
