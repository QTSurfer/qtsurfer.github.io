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
3. **Prepare** historical market data via `POST /backtest/{exchange}/{type}/prepare` — returns a `jobId`. `{exchange}` can be a managed exchange (e.g. `binance`) or the reserved value `user` to prepare from your own uploaded [dataset](docs/datasets.md) instead
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
has not been switched on. The examples in `docs/` use the live host for that reason.

## API Quick Start

All endpoints require JWT authentication (`Authorization: Bearer <token>`). Each area below has
its own doc with full parameter tables, request/response examples, and error cases — this README
stays a map, not a mirror, so a growing endpoint only ever needs its own doc touched.

| Area | Covers |
|---|---|
| **[docs/strategy.md](docs/strategy.md)** | Compile, validate, list, inspect, delete a strategy; read back its source |
| **[docs/backtest_execute.md](docs/backtest_execute.md)** | Prepare a dataset, run a strategy once, poll the result, plot the equity curve |
| **[docs/backtest_sweep.md](docs/backtest_sweep.md)** | Run across a parameter grid, walk-forward validation, sensitivity marginals/heatmaps |
| **[docs/datasets.md](docs/datasets.md)** | Bring your own CSV instead of a managed exchange |

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
