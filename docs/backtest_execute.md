# Backtests

Prepare historical data, run a compiled strategy against it once, poll the result, and plot the
equity curve. For running the *same* strategy across a parameter grid instead, see
[`docs/backtest_sweep.md`](backtest_sweep.md).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/backtest/{exchangeId}/{type}/prepare` | Prepare a dataset |
| `GET` | `/backtest/{exchangeId}/{type}/prepare/{jobId}` | Poll prepare status |
| `POST` | `/backtest/{exchangeId}/{type}/execute` | Run a strategy against a prepared dataset |
| `GET` | `/backtest/{exchangeId}/{type}/execute/{jobId}` | Poll the execution result |
| `DELETE` | `/backtest/{exchangeId}/{type}/execute/{jobId}` | Cancel a running execution |

`{type}` is the [`DataSourceType`](../openapi.yaml) — `ticker` today.

## Preparing data

`POST .../prepare`

Enqueues a prepare task over a date range and returns a `jobId` immediately; poll the `GET`
below for completion. Same params → same `jobId` (idempotent) — repeated calls reuse the
existing job instead of enqueueing duplicate work.

### Request body — `PrepareRequest`

Two shapes, chosen by the `exchangeId` path segment:

| Field | Type | Notes |
|---|---|---|
| `from`, `to` | string | required. ISO-8601, ISO date, or basic ISO date (`2024-12-14T23:59:59Z`, `2024-12-14`, `20241214`) |
| `instrument` | string | required **unless** `exchangeId` is the reserved value `user` |
| `datasetId` | string | **only** for `exchangeId: user` — a dataset from `POST /datasets`, in place of `instrument` |
| `datasetVersionId` | string | **only** for `exchangeId: user`, optional — pins a past version instead of the dataset's current one |
| `cadence` | enum | `1s`, `5s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `8h`, `12h`, `1d`, `1w`, `1q` — default `1s`. Coarser-than-source values must be exact multiples of the source cadence |

`exchangeId: user` is reserved for your own uploaded data — see
[`docs/datasets.md`](datasets.md).

### Example

```bash
curl -X POST https://api.qtsurfer.net/v1/backtest/binance/ticker/prepare \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instrument":"BTC/USDT","from":"2026-03-14","to":"2026-03-15"}'
# → 202 {"jobId": "5ikYAMIO..."}
```

Errors: `400` invalid request, `from` older than the lookback window, `to` in the future, or (for
`exchangeId: user`) the dataset's upload hasn't finished ingesting / `cadence` finer than the
dataset's discovered cadence / range exceeds your tier's limit · `404` exchange/type not found, or
(for `exchangeId: user`) `datasetId`/`datasetVersionId` doesn't exist or isn't yours · `429` global
queue at capacity or too many active backtests — doesn't apply to `exchangeId: user`, which reads
an already-ingested file rather than claiming worker capacity.

## Polling prepare status

`GET .../prepare/{jobId}`

A single-instrument prepare is always terminal (`status: Completed`) — decide from
`coverageRatio` (e.g. execute once it clears a chosen threshold) rather than polling for missing
hours that may never arrive. A missing hour usually means low activity, not missing data.

### Response — `PrepareJobState`

The `JobState` shape (`contextId`, `status`, `statusDetail`, `size`, `completed`, `startTime`,
`endTime`) plus a coverage summary. **Two coverage shapes**, by exchange vs. dataset:

| Field | Notes |
|---|---|
| `dataFrom`, `dataTo` | available data range. Present either way |
| `coverageRatio` | `0`–`1`. Managed exchange: `hoursWithData / totalHours`. Dataset (`exchangeId: user`): `rows / expectedStepsAtCadence` over the dataset version's own range, echoing what ingest computed once |
| `totalHours`, `hoursWithData` | managed exchange only — absent for a dataset-backed prepare |
| `hoursWithoutData` | managed exchange only — one entry per empty hour: `{hour, expected, rationale}`. `rationale` is `pending_conversion` (re-poll may fill it), `low_activity`, or `unknown` |
| `cadence`, `gaps`, `largestGapSteps` | dataset-backed only — the dataset version's own discovered cadence, and its gap count/size at that cadence |

### Example

```bash
curl https://api.qtsurfer.net/v1/backtest/binance/ticker/prepare/$PREPARE_JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "contextId": "ctx_0bjmoxd4vahkgc0hnvdldh",
  "status": "Completed",
  "size": 0,
  "completed": 24,
  "startTime": "2026-04-14T15:00:00Z",
  "endTime": "2026-04-14T15:00:01Z",
  "dataFrom": "2026-04-14T13:00:00Z",
  "dataTo": "2026-04-14T15:30:05Z",
  "coverageRatio": 0.994,
  "totalHours": 168,
  "hoursWithData": 167,
  "hoursWithoutData": [
    {"hour": "2026-04-14T02:00:00Z", "expected": 0, "rationale": "low_activity"}
  ]
}
```

## Executing a backtest

`POST .../execute`

Runs the strategy identified by `strategyId` over the data from `prepareJobId`; instrument and
date range are recovered from the prepare job, not sent again. Works unchanged for a
dataset-backed prepare. Same `(prepareJobId, strategyId, storeSignals, equityCurve)` → same
`jobId` (idempotent) — a request that omits `equityCurve` dedupes exactly as it did before that
field existed.

### Request body

| Field | Type | Notes |
|---|---|---|
| `prepareJobId` | string | required — must be a `Completed` prepare job |
| `strategyId` | string | required |
| `storeSignals` | boolean | default `false`. When `true`, the worker uploads emitted signals to object storage and the result gains `signalsUrl`/`signalsId` |
| `equityCurve` | [`EquityCurveOptions`](../openapi.yaml) | optional — reshape the curve baked into `results.equityCurve`. See [below](#requesting-a-transform-on-submit) |

### Example

```bash
curl -X POST https://api.qtsurfer.net/v1/backtest/binance/ticker/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prepareJobId":"5ikYAMIO...","strategyId":"2ul144qe9tlwzu5anhwvc6"}'
# → 202 {"jobId": "4GmNN0i9..."}
```

Errors: `400` invalid request · `404` prepare job not found or expired · `429` rate limited.

## Polling the result

`GET .../execute/{jobId}`

A `202` (empty body, `{}`) means the result isn't readable yet — keep polling under your existing
timeout, and never treat it as terminal. It's returned both while the job is still running *and*
when a terminal job's stored result couldn't be read back, so a poll loop should key off `200`
plus `state.status`, not off "not 202 anymore".

### Response — `BacktestJobResult`

`state` ([`JobState`](#response--preparejobstate)) plus `results` (`ResultMap`):

| Field | Notes |
|---|---|
| `hostName`, `iops`, `strategyId`, `instrument` | always present. `strategyId` here is the **execution context id** (`strategy:<user>:<strategyId>`) — take the segment after the last `:` to get back the id you compiled with |
| `pnlTotal`, `pnlTotalPercent`, `totalTrades`, `winRate`, `sharpeRatio`, `sortinoRatio`, `cagr`, `maxDrawdown`, `maxDrawdownPercent` | yield metrics — present once the strategy emitted at least one trade |
| `equityCurve` | [`EquityCurveResult`](#visualizing-the-equity-curve) — present under the same condition as the yield metrics |
| `notices` | diagnostics the engine raised, each `{level, code, message, provenance: execute}`. **Absent means nothing was raised** — the one surface where silence is a real answer. Raised on failed/aborted runs too, and those are the most worth reading: a run with no trades often says why here |
| `noticesTruncated` | how many notices were dropped past the cap of 50; absent when none were |
| `signalCount`, `signalsId`, `signalsUrl`, `signalsUpload`, `signalsUploadedAt`, `signalsUploadReason` | only when the request set `storeSignals: true`. `signalsUpload` is `Done` \| `Failed` \| `Skipped`; `signalsUrl` is a Parquet file with **every** emitted signal (indicator values, markers) — the full detail behind the summary `equityCurve` |

### Example

```bash
curl https://api.qtsurfer.net/v1/backtest/binance/ticker/execute/$EXECUTE_JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "state": {"status": "Completed", "completed": 85058},
  "results": {
    "pnlTotal": 42.75, "pnlTotalPercent": 2.25, "totalTrades": 156, "winRate": 58.33,
    "sharpeRatio": 1.245, "sortinoRatio": 1.872, "cagr": 0.1534,
    "maxDrawdown": 12.50, "maxDrawdownPercent": 8.75, "iops": 123956.53,
    "equityCurve": {
      "points": [
        {"timestamp": 1700000000000, "equity": 100.0},
        {"timestamp": 1700000060000, "equity": 110.5},
        {"timestamp": 1700000120000, "equity": 90.25}
      ],
      "meta": {
        "inputPointCount": 3, "outputPointCount": 3,
        "resampled": false, "differential": false, "outMode": "ARRAY"
      }
    }
  }
}
```

Errors: `400` invalid request · `404` execution job not found.

## Cancelling

`DELETE .../execute/{jobId}`

Requests cancellation; status transitions to `Aborted` once processed — asynchronous, so poll
`GET` to confirm. `200` `{"status": "cancelling", "jobId": "..."}` · `404` not found.

## Visualizing the equity curve

`results.equityCurve.points` is ready to plot directly — no Parquet download needed for this.
Element 0 is an anchor at the backtest's `from` with the initial capital; every point after that is
one sample per emitted yield, each an [`EquityPoint`](../openapi.yaml): `timestamp` (epoch ms) and
`equity` (`initialCapital + cumulativePnl` at that point).

`equityCurve` always carries a `meta` object alongside the points — [`EquityCurveMeta`](../openapi.yaml):
`inputPointCount`/`outputPointCount` (curve size before/after any server-side reshaping),
`resampled`/`differential` (whether each stage actually changed anything — not whether you asked
for it), and `outMode` (`ARRAY` here; the same type is `SHORT` — `{timestamps, equities}` parallel
arrays — for a large sweep-selected curve served the compact way, see
[`docs/backtest_sweep.md`](backtest_sweep.md#the-native-path-submit-with-equitycurve)).
With no `equityCurve` on the request, the plain-execute path returns `ARRAY`, unresampled,
un-delta-encoded — the same default it always had. This shape is shared with the sweep path so
both are read identically.

For the full trade-by-trade detail behind that curve — indicator values, buy/sell markers — set
`storeSignals: true` on the execute request and load `signalsUrl`'s Parquet file instead.

![Illustrative equity curve, cumulative PnL rising from 0% to +18.3% over 30 days with a drawdown to -4% around day 10](img/equity-curve.svg)

### Requesting a transform on submit

Unlike a sweep-selected curve — which stays fetchable by pointer, so `outMode`/`resample`/
`differential` can be chosen per-`GET` — a plain backtest's `equityCurve` is baked into the job's
result once, at execute time. There is no read-time endpoint to reshape it afterward, so ask for
the shape you want on the **submit** request itself. `equityCurve` is optional and every field
inside it is too; omitting the whole block is exactly today's default (`ARRAY`, unresampled,
not delta-encoded).

Because the transform is part of what determines the stored result, it is also part of the
idempotency key: `(prepareJobId, strategyId, storeSignals, equityCurve)` → `jobId`. A resubmit
that only changes `equityCurve` is a different request and gets a different `jobId` — it does not
silently reuse an earlier submit's shape.

A large backtest, served compact and delta-encoded:

```bash
curl -X POST https://api.qtsurfer.net/v1/backtest/binance/ticker/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prepareJobId": "5ikYAMIO...",
    "strategyId": "2ul144qe9tlwzu5anhwvc6",
    "equityCurve": {"resample": 500, "differential": true, "outMode": "SHORT"}
  }'
```

```json
{
  "results": {
    "equityCurve": {
      "timestamps": [1700000000000, 60000, 60000],
      "equities": [100.0, 10.5, -20.25],
      "meta": {
        "inputPointCount": 85000, "outputPointCount": 500,
        "resampled": true, "differential": true, "outMode": "SHORT"
      }
    }
  }
}
```

`timestamps`/`equities` after the first element are deltas from the previous point, not absolute
values — the same encoding rule the sweep doc's
[`differential=true` example](backtest_sweep.md#the-native-path-submit-with-equitycurve) uses.
A server-side size guard can still force a smaller/deflated shape above its own thresholds
regardless of what was requested — `meta`, not the request, is the source of truth for what shape
actually came back.
