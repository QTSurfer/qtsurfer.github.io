# Coding Java strategies

A QTSurfer strategy consumes market data, updates indicators and state, and emits signals. This
guide focuses on signal emission: the point where an observation becomes either an instruction to
trade or data to inspect later.

For the complete class API, use the [Engine Javadoc][engine-javadoc], particularly the [strategy
signal package][signal-javadoc]. For agent-assisted authoring, install the maintained
[`qtsurfer-java-strategy` skill][strategy-skill]:

```bash
npx skills add QTSurfer/strategy-skills --skill qtsurfer-java-strategy
```

The skill also covers choosing a strategy base class, configuring indicators, and managing
per-instrument state. Once the source is ready, [compile and validate it through the
API](strategy.md).

## Execution signals and information signals

These signal families have different effects:

| Signal | Purpose | Causes a trade? |
|---|---|---|
| `BuySignal` | Expresses a buy instruction and its order configuration | Yes |
| `SellSignal` | Expresses a sell instruction and its order configuration | Yes |
| `InfoStrategySignal` | Records indicators, diagnostics, or visualization metadata | No |

An information signal labelled `BUY` is still only information. Conversely, `emitBuy(price)`
emits an executable buy signal even if no chart metadata is attached.

The [README example](../README.md#strategy-example) deliberately emits both. It publishes an
information signal on every window update so the indicator series can be inspected, but emits a
buy or sell only when the moving averages cross:

```java
InfoStrategySignal signal = createInfoSignal();
signal.set("fast", fast);
signal.set("slow", slow);

if (isBullish && !wasBullish) {
    emitBuy(price);
} else if (!isBullish && wasBullish) {
    emitSell(price);
}

emitSignal(signal);
```

## Signal helpers

Inside an `AbstractWindowListener`, the listener already knows its strategy and instrument:

| Helper | Result |
|---|---|
| `emitBuy(price)` | Creates and immediately emits a market `BuySignal` |
| `emitSell(price)` | Creates and immediately emits a market `SellSignal` |
| `createBuySignal(price)` | Creates a buy signal to customize before emission |
| `createSellSignal(price)` | Creates a sell signal to customize before emission |
| `createInfoSignal()` | Creates an information signal to populate before emission |
| `emitInfo(key, values...)` | Creates, populates, and immediately emits one information signal |
| `emitSignal(signal)` | Emits a signal created or customized by the listener |

At strategy-class level the equivalent trade helpers take the instrument explicitly:
`emitBuy(instrument, price)`, `emitSell(instrument, price)`, `createBuySignal(instrument, price)`,
and `createSellSignal(instrument, price)`. Use `createInfoStrategySignal(instrument)` when building
an information signal there.

The `price` passed to the basic trade helpers is the strategy's current reference price. The
signal defaults to `market`; when a signal is changed to `limit`, that price becomes its limit
price.

## Customizing buy and sell signals

The immediate helpers intentionally accept only a price. To configure an order, create its signal,
set the required options, and emit it exactly once:

```java
import com.wualabs.qtsurfer.engine.exchange.trade.OrderFlag;
import com.wualabs.qtsurfer.engine.strategy.event.signal.BuySignal;
import com.wualabs.qtsurfer.engine.strategy.event.signal.MarketHintSignal.OrderKind;

BuySignal buy = createBuySignal(price);
buy.setOrderKind(OrderKind.limit);
buy.setMaxTries(3);
buy.setFlags(OrderFlag.GTC);
buy.set("reason", "ema-cross");
emitSignal(buy);
```

`BuySignal` and `SellSignal` inherit these options from
[`MarketHintSignal`][market-hint-javadoc], the common base class and authoritative method reference:

| Method | Meaning |
|---|---|
| `setOrderKind(OrderKind.market)` | Market order; this is the default |
| `setOrderKind(OrderKind.limit)` | Limit order at the signal's `price` |
| `setMaxTries(n)` | Maximum attempts for a limit buy; `n` must be positive |
| `setFlags(flags...)` | Order flags such as `FOK`, `IOC`, or `GTC`; actual support depends on the venue |
| `setSellPercent(percent)` | Percentage of the position to close; intended for multiple-long execution, default `100` |
| `setStopPrice(price)` | Fixed protective stop to arm after the entry fills |
| `setStopLimitPrice(price)` | Optional limit price for that fixed stop; without it the stop exits at market |
| `setTrailPercent(percent)` | Trailing protective stop, expressed as a percentage from the running favourable price extreme |
| `setStopCondition(condition)` | Live predicate that gates an engine-managed fixed or trailing stop |
| `set(key, values...)` | Arbitrary analytics, provenance, or visualization metadata carried with the signal |

Treat `stop` and `stopTrailing` as engine-managed order kinds. Strategy code should express
protective risk on the entry signal with `setStopPrice` or `setTrailPercent`, rather than emitting a
standalone stop order.

### Protective stops

A long entry can arm a fixed stop as part of the same signal:

```java
BuySignal buy = createBuySignal(price);
buy.setStopPrice(price * 0.95);
emitSignal(buy);
```

Use `setStopLimitPrice` as well when the protective exit must be stop-limit rather than
stop-market. A trailing stop follows the favourable extreme and triggers after the configured
percentage retracement:

```java
BuySignal buy = createBuySignal(price);
buy.setTrailPercent(2.0);
emitSignal(buy);
```

The same fields apply symmetrically to a short entry. A stop condition is evaluated repeatedly by
the engine and can suppress the stop until a wider strategy condition permits it. It is live
strategy logic, not serializable signal data.

## Information and chart metadata

`createInfoSignal()` is listener-local syntactic sugar: it creates an `InfoStrategySignal` already
bound to the current strategy and instrument. Populate it with `set` and emit it when ready:

```java
InfoStrategySignal signal = createInfoSignal();
signal.set("price", price);
signal.set("fast", fast);
signal.set("slow", slow);
emitSignal(signal);
```

`set` stores one value directly. An even list of name/value pairs creates a nested object under the
given key, which is why chart markers use this form:

```java
signal.set("_m",
    "position", "belowBar",
    "shape", "arrowUp",
    "color", "#26a69a",
    "text", "BUY");
```

The marker positions used by the standard visualization are `aboveBar`, `belowBar`, and `inBar`;
the portable shapes are `circle`, `arrowUp`, `arrowDown`, and `square`. Prefixing a property with
`_` reserves it as control metadata rather than a normal plotted series, as `_m` does here.

For a single value, `emitInfo` is the shortest form:

```java
emitInfo("zscore", zscore);
```

It also accepts nested name/value pairs:

```java
emitInfo("averages", "fast", fast, "slow", slow);
```

Use the longer `createInfoSignal()` form when one event needs several top-level values or marker
metadata. Information signals are useful for explaining a decision, but they never replace the
corresponding `emitBuy` or `emitSell` when the strategy is meant to trade.

[engine-javadoc]: https://qtsurfer.github.io/qtsurfer-engine-java-docs/
[market-hint-javadoc]: https://qtsurfer.github.io/qtsurfer-engine-java-docs/com/wualabs/qtsurfer/engine/strategy/event/signal/MarketHintSignal.html
[signal-javadoc]: https://qtsurfer.github.io/qtsurfer-engine-java-docs/com/wualabs/qtsurfer/engine/strategy/event/signal/package-summary.html
[strategy-skill]: https://github.com/QTSurfer/strategy-skills
