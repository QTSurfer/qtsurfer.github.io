# Changelog

All notable changes to the QTSurfer OpenAPI contract are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). While the API is
pre-1.0, its version follows the version in `openapi.yaml`.

## [Unreleased]

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
