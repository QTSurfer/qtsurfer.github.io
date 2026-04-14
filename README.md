# QTSurfer

Quantitative trading strategy backtesting platform.

Write trading strategies in Java, submit them to be compiled, run backtests against historical exchange data, and visualize results with millions of data points — all through a REST API.

## API Documentation

**[qtsurfer.github.io](https://qtsurfer.github.io)** — Interactive OpenAPI documentation

## How It Works

```
Strategy (Java) ──► Compile ──► Prepare Data ──► Execute ──► Signals (Parquet) ──► Visualize
```

1. **Write** a trading strategy in Java using the strategy SDK (indicators, signals, execution)
2. **Compile** it via `POST /strategy` — no build tools needed on the client
3. **Prepare** historical market data via `POST /backtest/{exchange}/{type}/prepare` — returns a `jobId`
4. **Execute** the strategy against prepared data via `POST /backtest/{exchange}/{type}/execute` — returns a `jobId`
5. **Visualize** results — signals are stored as Parquet files, loaded in-browser via DuckDB-WASM

## Strategy Example

```java
import com.wualabs.qtsurfer.engine.strategy.AbstractTickerStrategy;
import com.wualabs.qtsurfer.engine.strategy.AbstractOnChangeListener;
import com.wualabs.qtsurfer.engine.strategy.event.signal.InfoStrategySignal;
import com.wualabs.qtsurfer.engine.indicators.helpers.WindowTimeRTIndicator.WindowTime;
import com.wualabs.qtsurfer.engine.indicators.helpers.group.InstrumentGroupRTIndicator;
import com.wualabs.qtsurfer.engine.core.state.StateStoreSupport;

public class EmaCrossStrategy extends AbstractTickerStrategy {

    @Override
    protected void setupIndicators(InstrumentGroupRTIndicator indicators) {
        indicators
            .addPrice()
            .ema("fast", 20)
            .ema("slow", 50)
            .window("fast", WindowTime.s1, new CrossListener(indicators));
    }

    private class CrossListener extends AbstractOnChangeListener {
        public CrossListener(InstrumentGroupRTIndicator indicators) {
            super(EmaCrossStrategy.this, indicators);
        }

        @Override
        public void onChange(StateStoreSupport s, double prev, double actual) {
            initStore(s);
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

## API Quick Start

All endpoints require JWT authentication (`Authorization: Bearer <token>`).

### Compile a strategy
```bash
curl -X POST https://api.qtsurfer.com/v1/strategy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/plain" \
  --data-binary @MyStrategy.java
# → {"strategyId": "2ul144qe9tlwzu5anhwvc6"}
```

### Prepare market data
```bash
curl -X POST https://api.qtsurfer.com/v1/backtest/binance/ticker/prepare \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instrument":"BTC/USDT","from":"2026-03-14","to":"2026-03-15"}'
# → 202 {"jobId": "5ikYAMIO..."}
```

Poll until completion:
```bash
curl https://api.qtsurfer.com/v1/backtest/binance/ticker/prepare/$PREPARE_JOB_ID \
  -H "Authorization: Bearer $TOKEN"
# → {"status": "Completed", ...}
```

### Execute backtest
```bash
curl -X POST https://api.qtsurfer.com/v1/backtest/binance/ticker/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prepareJobId":"5ikYAMIO...","strategyId":"2ul144qe9tlwzu5anhwvc6"}'
# → 202 {"jobId": "4GmNN0i9..."}
```

### Poll results
```bash
curl https://api.qtsurfer.com/v1/backtest/binance/ticker/execute/$EXECUTE_JOB_ID \
  -H "Authorization: Bearer $TOKEN"
# → {"state": {"status": "Completed", "completed": 85058},
#    "results": {"pnlTotal": 42.75, "totalTrades": 156, "winRate": 58.33,
#                "sharpeRatio": 1.245, "sortinoRatio": 1.872, "cagr": 0.1534,
#                "maxDrawdown": 12.50, "maxDrawdownPercent": 8.75,
#                "iops": 101346.81, "signalsUrl": "https://storage.qtsurfer.com/..."}}
```

The response includes yield metrics (PnL, win rate, Sharpe, Sortino, CAGR, max drawdown) and a `signalsUrl` pointing to a Parquet file with all emitted signals, ready for visualization.

> The same input parameters always return the same `jobId` — repeated calls don't re-enqueue work.

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
