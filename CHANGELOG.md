# Changelog

All notable changes to the QTSurfer OpenAPI contract are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). While the API is
pre-1.0, its version follows the version in `openapi.yaml`.

## [Unreleased]

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
