# QTSurfer

Quantitative trading strategy backtesting platform.

Write trading strategies in Java, submit them to be compiled, run backtests against historical exchange data, and visualize results with millions of data points — all through a REST API.

## API Documentation

**[qtsurfer.github.io](https://qtsurfer.github.io)** — Interactive OpenAPI documentation

## How It Works

```
Strategy (Java) ──► Compile ──► Prepare Data ──┬─► Execute ──► Signals (Parquet) ──► Visualize
                                               └─► Execute Sweep ──► Ranked trials
```

1. **Write** a trading strategy in Java using the strategy SDK (indicators, signals, execution)
2. **Compile** it via `POST /strategy` — no build tools needed on the client
3. **Prepare** historical market data via `POST /backtest/{exchange}/{type}/prepare` — returns a `jobId`. `{exchange}` can be a managed exchange (e.g. `binance`) or the reserved value `user` to prepare from your own uploaded [dataset](#bring-your-own-data-datasets) instead
4. **Execute** either one backtest via `POST /backtest/{exchange}/{type}/execute` or a parameter sweep via `POST /backtest/{exchange}/{type}/executeSweep/{prepareJobId}`
5. **Inspect** the result or ranked sweep trials; individual backtest signals are stored as Parquet files and loaded in-browser via DuckDB-WASM

## Strategy Example

```java
import com.wualabs.qtsurfer.engine.strategy.AbstractTickerStrategy;
import com.wualabs.qtsurfer.engine.strategy.AbstractWindowListener;
import com.wualabs.qtsurfer.engine.strategy.event.signal.InfoStrategySignal;
import com.wualabs.qtsurfer.engine.indicators.helpers.WindowTimeRTIndicator.WindowTime;
import com.wualabs.qtsurfer.engine.indicators.helpers.group.InstrumentGroupRTIndicator;
import com.wualabs.qtsurfer.engine.core.state.StateStore;

public class EmaCrossStrategy extends AbstractTickerStrategy {

    @Override
    protected void setupIndicators(InstrumentGroupRTIndicator indicators) {
        indicators
            .addPrice()
            .ema("fast", 20)
            .ema("slow", 50)
            .window("fast", WindowTime.s1, new CrossListener(indicators));
    }

    private class CrossListener extends AbstractWindowListener {
        public CrossListener(InstrumentGroupRTIndicator indicators) {
            super(EmaCrossStrategy.this, indicators);
        }

        @Override
        public void onChange(StateStore store, double prev, double actual) {
            double price = indicators.getValue("price");
            double fast  = indicators.getValue("fast");
            double slow  = indicators.getValue("slow");

            InfoStrategySignal signal = createInfoSignal();
            signal.set("price", price);
            signal.set("fast", fast);
            signal.set("slow", slow);

            boolean wasBullish = store.is("bullish");
            boolean isBullish = fast > slow;

            if (isBullish && !wasBullish) {
                store.set("bullish");
                signal.set("_m", "position", "belowBar", "shape", "arrowUp",
                    "color", "#26a69a", "text", "BUY");
            } else if (!isBullish && wasBullish) {
                store.unset("bullish");
                signal.set("_m", "position", "aboveBar", "shape", "arrowDown",
                    "color", "#ef5350", "text", "SELL");
            }

            emitSignal(signal);
        }
    }
}
```

## Servers

The spec lists two, and only one of them serves the API today:

| | URL | Status |
|---|---|---|
| **Staging** | `https://api.qtsurfer.net/v1` | **Live.** What this specification describes, and what to develop against. Generated clients default here. |
| Production | `https://api.qtsurfer.com/v1` | Reserved, not yet serving. Listed so the eventual address is known in advance. |

While the API is pre-1.0 the staging host is the API: it is where the versions described here are
deployed, and it can change shape between releases in the way a pre-1.0 spec implies. Pointing a
client at the production URL today will not reach anything — it is a placeholder for an address that
has not been switched on. The examples below use the live host for that reason.

## API Quick Start

All endpoints require JWT authentication (`Authorization: Bearer <token>`).

### Compile a strategy
```bash
curl -X POST https://api.qtsurfer.net/v1/strategy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/plain" \
  --data-binary @MyStrategy.java
# → {"strategyId": "2ul144qe9tlwzu5anhwvc6"}
```

### List your strategies
```bash
curl https://api.qtsurfer.net/v1/strategies \
  -H "Authorization: Bearer $TOKEN"
# → {"strategies": [{"strategyId": "2ul144qe9tlwzu5anhwvc6",
#                     "compiledAt": "2026-08-19T10:15:00Z", "requiredSources": ["Ticker"]}]}
```

### Get a strategy's source
```bash
curl https://api.qtsurfer.net/v1/strategy/2ul144qe9tlwzu5anhwvc6/code \
  -H "Authorization: Bearer $TOKEN"
# → {"strategyId": "2ul144qe9tlwzu5anhwvc6", "code": "package strategy;\npublic class..."}
```

### Delete a strategy

Frees up the slot on a plan capped at a strategy count. Backtests already run against it are
unaffected — this only stops it from being validated, executed, or listed going forward.

```bash
curl -X DELETE https://api.qtsurfer.net/v1/strategy/2ul144qe9tlwzu5anhwvc6 \
  -H "Authorization: Bearer $TOKEN"
# → {"strategyId": "2ul144qe9tlwzu5anhwvc6", "deleted": true}
```

### Prepare market data
```bash
curl -X POST https://api.qtsurfer.net/v1/backtest/binance/ticker/prepare \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instrument":"BTC/USDT","from":"2026-03-14","to":"2026-03-15"}'
# → 202 {"jobId": "5ikYAMIO..."}
```

Poll until completion:
```bash
curl https://api.qtsurfer.net/v1/backtest/binance/ticker/prepare/$PREPARE_JOB_ID \
  -H "Authorization: Bearer $TOKEN"
# → {"status": "Completed", ...}
```

### Execute backtest
```bash
curl -X POST https://api.qtsurfer.net/v1/backtest/binance/ticker/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prepareJobId":"5ikYAMIO...","strategyId":"2ul144qe9tlwzu5anhwvc6"}'
# → 202 {"jobId": "4GmNN0i9..."}
```

### Poll results
```bash
curl https://api.qtsurfer.net/v1/backtest/binance/ticker/execute/$EXECUTE_JOB_ID \
  -H "Authorization: Bearer $TOKEN"
# → {"state": {"status": "Completed", "completed": 85058},
#    "results": {"pnlTotal": 42.75, "totalTrades": 156, "winRate": 58.33,
#                "sharpeRatio": 1.245, "sortinoRatio": 1.872, "cagr": 0.1534,
#                "maxDrawdown": 12.50, "maxDrawdownPercent": 8.75,
#                "iops": 101346.81, "signalsUrl": "https://storage.qtsurfer.com/..."}}
```

The response includes yield metrics (PnL, win rate, Sharpe, Sortino, CAGR, max drawdown) and a `signalsUrl` pointing to a Parquet file with all emitted signals, ready for visualization.

### Execute a parameter sweep

The sweep reuses the same prepared dataset. Its path `requestId` is the `jobId` returned by the existing prepare endpoint.

```bash
curl -X POST "https://api.qtsurfer.net/v1/backtest/binance/ticker/executeSweep/$PREPARE_JOB_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategyId": "2ul144qe9tlwzu5anhwvc6",
    "sweep": {
      "sampler": "grid",
      "objective": "sharpe",
      "params": {
        "rsiPeriod": {"from": 7, "to": 28, "step": 1},
        "useTrendFilter": {"values": [true, false]}
      }
    }
  }'
# → 202 {"sweepId":"swp_95e47a7f0966ce11","requestId":"5ikYAMIO...",
#        "totalRuns":44,"shards":1,"seed":487221,"queued":true}
```

Poll the ranked leaderboard:

```bash
curl "https://api.qtsurfer.net/v1/backtest/binance/ticker/executeSweep/$PREPARE_JOB_ID/$SWEEP_ID" \
  -H "Authorization: Bearer $TOKEN"
# → {"status":"RUNNING","ranking":"plateau",
#    "progress":{"done":31,"total":44,"aborted":0,"failedShards":0,"retrying":0,"notStarted":1,
#                 "etaSeconds":12},
#    "leaderboard":[{"runIx":12,"rank":1,"params":{...},"sharpe":1.84,
#                     "plateauScore":1.61,"neighbourCount":6}]}
```

Results rank by **plateau score** by default — the objective of the worst neighbour in a parameter point's immediate vicinity, so a spike that does not survive the parameters moving slightly does not win. Pass `?ranking=raw` for the unadjusted objective order, or `order=natural` to retrieve every available row in stable `runIx` order, without leaderboard truncation. The server returns the effective random seed so sampled sweeps can be reproduced exactly, and `progress` says whether a stalled sweep is retrying, still queueing shards, or actually dead.

> Identical prepare and execute requests are idempotent. Repeated sweeps return the same `sweepId` with `queued: false` instead of enqueueing duplicate work.

### Validate a sweep out of sample (walk-forward)

Add `walkForward` to test whether the winning parameters keep working, not just which ones won. The data splits into sequential folds; each optimizes on its own window and is scored only on the window immediately after — data it was not chosen on.

```bash
curl -X POST "https://api.qtsurfer.net/v1/backtest/binance/ticker/executeSweep/$PREPARE_JOB_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategyId": "2ul144qe9tlwzu5anhwvc6",
    "sweep": {"sampler":"grid","objective":"sharpe",
              "params":{"rsiPeriod":{"from":7,"to":28,"step":1}}},
    "walkForward": {"folds": 4}
  }'
# → 202 {"sweepId":"swp_...","walkForward":{"folds":4,"inSamplePct":66,"totalRuns":92}}
```

The leaderboard becomes one row per fold — that fold's winner, scored **out of sample** — and a `walkForward` section adds the in-sample/out-of-sample pair behind each row plus `paramDrift`: how much the winning parameters moved fold to fold. A tight, stable value means the parameter is real; one that jumps around every fold means the sweep is fitting noise.

### Parameter sensitivity

`GET .../executeSweep/{prepareJobId}/{sweepId}/sensitivity` aggregates the sweep's stored rows into per-parameter marginals (best/mean/worst at each value, collapsing every other axis) and pairwise heatmaps — which axes actually moved the objective, computed from rows already in, no re-run.

### Bring your own data (datasets)

Backtest against a CSV you upload instead of a managed exchange. Create a dataset, PUT the file to
the returned presigned URL, finalize it to trigger ingest, then prepare/execute exactly as above
but with `user` in place of the exchange id.

```bash
curl -X POST https://api.qtsurfer.net/v1/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My BTC ticks","instrument":"BTC/USDT"}'
# → 201 {"datasetId":"ds_3f9a1c2e7b0d4a5f","name":"My BTC ticks","type":"ticker",
#        "instrument":"BTC/USDT","uploadId":"up_1a2b3c4d5e6f7a8b",
#        "upload":{"url":"https://storage.qtsurfer.com/...","expiresInMinutes":15}}
```

The CSV needs a header row with `timestamp` (ISO-8601 or epoch seconds/millis/micros) and `close`
columns at minimum; `open`, `high`, `low`, `volume`, `quoteVolume`, `bid`, `bidSize`, `ask`,
`askSize` are optional. Cadence and timestamp unit are discovered from the data, not declared.

```bash
curl -X PUT "$UPLOAD_URL" --data-binary @my-btc-ticks.csv

curl -X POST https://api.qtsurfer.net/v1/datasets/$DATASET_ID/uploads/$UPLOAD_ID/finalize \
  -H "Authorization: Bearer $TOKEN"
# → 202 {"jobId": "dataset-upload:..."}
```

Poll until ingest finishes:
```bash
curl https://api.qtsurfer.net/v1/datasets/$DATASET_ID/uploads/$UPLOAD_ID \
  -H "Authorization: Bearer $TOKEN"
# → {"uploadId":"up_1a2b3c4d5e6f7a8b","status":"ready",
#    "version":{"datasetId":"ds_3f9a1c2e7b0d4a5f","id":"dsv_8e2b4f19c6a03d7e",
#               "bytes":4831022,"rows":86400,"cadence":"1s","timestampUnit":"iso",
#               "gaps":0,"largestGapSteps":0}}
```

Then prepare and execute against `exchangeId: user`, sending `datasetId` instead of `instrument`:
```bash
curl -X POST https://api.qtsurfer.net/v1/backtest/user/ticker/prepare \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"datasetId":"ds_3f9a1c2e7b0d4a5f","from":"2026-03-14","to":"2026-03-15"}'
# → 202 {"jobId":"5ikYAMIO...","datasetId":"ds_3f9a1c2e7b0d4a5f",
#        "datasetVersionId":"dsv_8e2b4f19c6a03d7e"}
```

`execute` is unchanged — same request body as against a managed exchange, since the instrument and
range are recovered from `prepareJobId` either way.

## Key Technologies

| Layer | Technology |
|-------|-----------|
| Strategy runtime | Java |
| Signal storage | Apache Parquet, S3-compatible object storage |
| Visualization | [svelte-timeseries](https://github.com/QTSurfer/svelte-timeseries) (DuckDB-WASM + ECharts) |

## Data Sources

| Type | Description |
|------|-------------|
| `ticker` | Real-time bid/ask/last/volume |
| `kline` | Candlestick OHLCV |
| `frate` | Funding rates (futures) |

## Related Projects

| Repository | Description |
|------------|-------------|
| [svelte-timeseries](https://github.com/QTSurfer/svelte-timeseries) | OSS Svelte component for time-series visualization |

## License

Apache-2.0
