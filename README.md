# QTSurfer OpenAPI specification

**[QTSurfer](https://www.qtsurfer.com)** is a quantitative trading strategy backtesting platform.

Write trading strategies in Java — or in QTScript, a compact language, currently in beta, that compiles to Java — submit them to be compiled, run backtests against historical exchange data, and visualize results with millions of data points — all through a REST API. Everything about the platform lives at **[www.qtsurfer.com](https://www.qtsurfer.com)**.

## API Documentation

**[QTSurfer API documentation](https://www.qtsurfer.com/docs/developers/api)** — the developer documentation, on the public site

**[qtsurfer.github.io](https://qtsurfer.github.io)** — Interactive OpenAPI documentation

**[Engine Javadoc](https://qtsurfer.github.io/qtsurfer-engine-java-docs/)** — strategy SDK classes (indicators, signals, execution) referenced below

**[Java strategy coding guide](docs/strategy_coding.md)** — signal emission, order parameters, chart metadata, and links to the maintained authoring skill

The Markdown guides in [`docs/`](docs/) are the source of the per-area documentation — full parameter tables, request/response examples and error cases. The [API Quick Start](#api-quick-start) below links to each one.

## How It Works

```
Strategy (Java or QTScript) ──► Compile ──► Prepare Data ──┬─► Execute ──► Signals (Parquet) ──► Visualize
                                                           └─► Execute Sweep ──► Ranked trials
```

1. **Write** a trading strategy in Java using the strategy SDK (indicators, signals, execution) — or in QTScript (beta), which compiles to Java
2. **Compile** it via `POST /strategy` — no build tools needed on the client
3. **Prepare** historical market data via `POST /backtest/{exchange}/{type}/prepare` — returns a `jobId`. `{exchange}` can be a managed exchange (e.g. `binance`) or the reserved value `user` to prepare from your own uploaded [dataset](docs/datasets.md) instead
4. **Execute** either one backtest via `POST /backtest/{exchange}/{type}/execute` or a parameter sweep via `POST /backtest/{exchange}/{type}/executeSweep/{prepareJobId}`
5. **Inspect** the result or ranked sweep trials; individual backtest signals are stored as Parquet files and loaded in-browser via DuckDB-WASM

## Strategy Example

A strategy is written in Java, or in [QTScript](docs/strategy.md#qtscript-beta), a compact language that compiles to Java. Both are submitted the same way — the raw source to `POST /strategy` — and the platform tells them apart by their text.

The Java example emits two different kinds of signal: `emitBuy`/`emitSell` drive execution, while the
`InfoStrategySignal` records indicator values and chart-marker metadata. See [Coding Java
strategies](docs/strategy_coding.md) for the signal helpers and their advanced order parameters.
For agent-assisted authoring, install the maintained
[`qtsurfer-java-strategy`](https://github.com/QTSurfer/strategy-skills) skill:

```bash
npx skills add QTSurfer/strategy-skills --skill qtsurfer-java-strategy
```

```java
import com.wualabs.qtsurfer.engine.strategy.*;
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

            boolean wasBullish = store.is("bullish");
            boolean isBullish = fast > slow;

            if (isBullish && !wasBullish) {
                store.set("bullish");
                signal.set("_m", "position", "belowBar", "shape", "arrowUp",
                    "color", "#26a69a", "text", "BUY");
                emitBuy(price);
            } else if (!isBullish && wasBullish) {
                store.unset("bullish");
                signal.set("_m", "position", "aboveBar", "shape", "arrowDown",
                    "color", "#ef5350", "text", "SELL");
                emitSell(price);
            }

            emitSignal(signal);
        }
    }
}
```

### The same strategy in QTScript

QTScript drops the ceremony — imports, class, base class, listener — and keeps every `{ }` body as plain Java. This file is the whole strategy: the same crossing logic, the same buy/sell signals and the same chart markers as the Java above, and run over the same data it produces the same trades and metrics.

```
strategy "EMA cross"

setup:
  ema(20)
  ema(50)
  window ema20 s1 {
    boolean bullish = actual > value("ema50");
    if (bullish && !store.is("bullish")) {
      store.set("bullish");
      emitInfo("_m", "position", "belowBar", "shape", "arrowUp", "color", "#26a69a", "text", "BUY");
      emitBuy(price);
    } else if (!bullish && store.is("bullish")) {
      store.unset("bullish");
      emitInfo("_m", "position", "aboveBar", "shape", "arrowDown", "color", "#ef5350", "text", "SELL");
      emitSell(price);
    }
  }
```

QTScript is in beta. Java remains the route with the full engine API, and anything QTScript cannot express is written in Java. See the [QTScript guide](docs/qtscript.md) for the language and [Strategies](docs/strategy.md#qtscript-beta) for how a source is recognised and how its `strategyId` is derived. To write QTScript with an agent, install the maintained skill:

```bash
npx skills add QTSurfer/strategy-skills --skill qtsurfer-qtscript-strategy
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

All endpoints require JWT authentication (`Authorization: Bearer <token>`). The JWT is short-lived
and obtained by exchanging your API key — issued via the web app — at `POST /auth/token`:

```bash
curl -X POST https://api.qtsurfer.net/v1/auth/token \
  -H "X-API-Key: <your-api-key>"
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scopes": ["STRATEGIES:READ", "STRATEGIES:WRITE", "..."],
  "tier": "free"
}
```

Send `access_token` as `Authorization: Bearer <token>` on every other call; refresh before it
expires (or on a `401`) by calling `/auth/token` again. `X-API-Key` is accepted only on this one
endpoint — everywhere else expects the bearer token, not the raw API key.

Each area below has its own doc with full parameter tables, request/response examples, and error
cases — this README stays a map, not a mirror, so a growing endpoint only ever needs its own doc
touched.

| Area | Covers |
|---|---|
| **[Strategy coding](docs/strategy_coding.md)** | Write Java strategies; emit execution and information signals; configure orders and chart markers |
| **[QTScript (beta)](docs/qtscript.md)** | Write a strategy in a compact language whose braced bodies are plain Java — the parts of a file, windows, examples |
| **[Market data](docs/market_data.md)** | Discover exchanges and instruments; download hourly ticker or kline segments |
| **[Strategies](docs/strategy.md)** | Compile a Java or QTScript strategy, validate, list, inspect, delete it; read back its source |
| **[Backtests](docs/backtest_execute.md)** | Prepare a dataset, run a strategy once, poll the result, plot the equity curve |
| **[Parameter sweeps](docs/backtest_sweep.md)** | Run across a parameter grid, walk-forward validation, sensitivity marginals/heatmaps |
| **[Equity curves](docs/equity_curves.md)** | Plot, compact, resample, delta-encode, retain and fetch backtest or sweep curves |
| **[Datasets](docs/datasets.md)** | Bring your own data instead of a managed exchange |
| **[Account](docs/account.md)** | Your tier limits and live storage usage |

## Key Technologies

| Layer | Technology |
|-------|-----------|
| Strategy runtime | Java (QTScript compiles to it) |
| Signal storage | Apache Parquet, S3-compatible object storage |
| Visualization | [svelte-timeseries](https://github.com/QTSurfer/svelte-timeseries) (DuckDB-WASM + ECharts) |

## Data Sources

The `{type}` of the `/backtest/{exchange}/{type}/...` paths:

| Type | Description | Backtests |
|------|-------------|-----------|
| `ticker` | Real-time bid/ask/last/volume | prepare, execute, sweep |
| `kline` | Candlestick OHLCV, at the `cadence` you prepare the data at | prepare, execute, sweep |
| `funding` | Funding rates (futures) | prepare only, for now |

See [Backtests](docs/backtest_execute.md#data-sources) for what each one can run.

## SDKs & Client Libraries

High-level, opinionated SDKs (where the developer experience lives) and their low-level
auto-generated API clients, per language. Install the SDK; it depends on the matching client
underneath.

| Language | SDK (high-level) | API client (low-level, generated) |
|----------|------------------|-----------------------------------|
| Java | [sdk-java](https://github.com/QTSurfer/sdk-java) | [api-client-java](https://github.com/QTSurfer/api-client-java) |
| TypeScript | [sdk-ts](https://github.com/QTSurfer/sdk-ts) | [api-client-ts](https://github.com/QTSurfer/api-client-ts) |
| Python | [sdk-python](https://github.com/QTSurfer/sdk-python) | [api-client-python](https://github.com/QTSurfer/api-client-python) |

Also part of the ecosystem:

- [lastra-ts](https://github.com/QTSurfer/lastra-ts) / [lastra-py](https://github.com/QTSurfer/lastra-py) — low-level readers for the Lastra columnar format in the browser / Python
- [mcp-java](https://github.com/QTSurfer/mcp-java) — Model Context Protocol server exposing the API as AI-agent tools (`qtsurfer-mcp`)
- [strategy-skills](https://github.com/QTSurfer/strategy-skills) — maintained agent skills for writing Java and QTScript strategies

## Related Projects

| Repository | Description |
|------------|-------------|
| [strategy-skills](https://github.com/QTSurfer/strategy-skills) | Maintained agent skills for writing, reviewing, and debugging QTSurfer strategies in Java and QTScript |
| [svelte-timeseries](https://github.com/QTSurfer/svelte-timeseries) | OSS Svelte component for time-series visualization |

## License

Apache-2.0
