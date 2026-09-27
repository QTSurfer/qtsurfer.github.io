# Coding Java strategies

A QTSurfer strategy consumes market data, updates indicators and state, and emits signals. This guide
covers signal emission — the point where an observation becomes either an instruction to trade or data
to inspect later — and [receiving a command](#receiving-commands) from outside a live run.

For the complete class API, use the [Engine Javadoc][engine-javadoc], particularly the [strategy
signal package][signal-javadoc]. For agent-assisted authoring, install the maintained
[`qtsurfer-java-strategy` skill][strategy-skill]:

```bash
npx skills add QTSurfer/strategy-skills --skill qtsurfer-java-strategy
```

The skill also covers choosing a strategy base class, configuring indicators, and managing
per-instrument state. Once the source is ready, [compile and validate it through the
API](strategy.md).

The signal helpers in this guide are not tied to a Java class: the `{ }` bodies of a
[QTScript](qtscript.md) strategy (beta) — a compact way to write a strategy that leaves out the
class, imports and listener — call `emitBuy`, `emitSell`, `emitInfo` and `emitSignal` exactly as
shown here.

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

Everything you `set` on a signal is its `data`, and it is published with the signal in a live run: whoever may read the run
may read it, so on a `public` run it is public. A signal whose `data` is over 8 KiB (8,192 bytes of its JSON) is not pushed
on the WebSocket channel; `GET /live/{runId}/signals` still returns it whole.

For a single value, `emitInfo` is the shortest form:

```java
emitInfo("zscore", zscore);
```

It also accepts nested name/value pairs:

```java
emitInfo("averages", "fast", fast, "slow", slow);
```

`emitInfo` takes the same arguments in a [QTScript](qtscript.md#inside-a-body) body — the
[README](../README.md#the-same-strategy-in-qtscript) shows the moving-average example above with its
chart markers written that way.

Use the longer `createInfoSignal()` form when one event needs several top-level values or marker
metadata. Information signals are useful for explaining a decision, but they never replace the
corresponding `emitBuy` or `emitSell` when the strategy is meant to trade.

## Receiving commands

A live run's owner can tell it a command from outside — `POST /live/{runId}/commands` — while it keeps
running, without restarting it. To act on one, implement `CommandRequestHandler`:

```java
import com.wualabs.qtsurfer.engine.strategy.event.request.CommandRequest;
import com.wualabs.qtsurfer.engine.strategy.event.request.CommandRequestHandler;

public class MyStrategy extends AbstractTickerStrategy implements CommandRequestHandler {

    @Override
    public void handle(CommandRequest request) {
        if ("flatten".equals(request.getCommand())) {
            // close the position, cancel pending orders, whatever "flatten" means for this strategy
        }
    }
}
```

`handle` runs on the same thread as `update()`, right before the market event the command targets, so it
sees the strategy's state exactly as it was at that point and can call anything `update()` can — read
indicators, emit a signal, change internal fields. A `RuntimeException` it throws is caught and counted,
the same as one from `update()`; an `Error` unwinds the run.

A command is always a plain string, and it is transient. It may also carry a `properties` object of your
own choosing, alongside `command` in the request body — not `params`, which stays what a run starts with
and `PUT /live/{runId}/params` changes. Each property lands as a top-level entry on `CommandRequest`'s own
map, so read one straight off `request` by name — `request.get("<key>")` — no key is off limits, since the
command's own text is kept separately (`getCommand()` reads it, unaffected by any of it). A
value keeps whatever JSON type it arrived as, so assigning it to a `String` field when the caller sent a
number or an object throws a `ClassCastException` inside `handle`; a QTScript `onCommand` body reads the
same value with `$command.<key>` instead, which always widens it to a `String` (`null` for an absent key,
never a cast failure). A command, and its properties, are not stored as part of the run: a replica that
restarts replays only the last stretch of market data, and a command from before that window simply never
reaches it.

A command has no instrument attached the way `update()` does; when its own properties name one, reach that
instrument's store with `getStateStore(String)`:

```java
@Override
public void handle(CommandRequest request) {
    String instrument = request.get("instrument");
    if (instrument != null) {
        getStateStore(instrument).set("flattened");
    }
}
```

**Neither a `@StrategyProperty` field nor a `StateStore` written from inside `handle` is durable.** Both
change immediately, in memory, the same as any other assignment, but neither is written to the run's
stored parameter set — a replica that restarts (or one that starts later, and never ran `handle` for that
command) starts from whatever `PUT /live/{runId}/params` last set, not from what a command assigned. The
only durable write is a real `PUT /live/{runId}/params` call, from outside the run — a strategy cannot
call its own REST API from inside `handle`.

A run whose strategy does not implement `CommandRequestHandler` answers every command with a `409` —
implementing the interface is what makes `POST /live/{runId}/commands` do anything at all.

A QTScript strategy implements it too, through its own `onCommand { }` section (see
[QTScript](qtscript.md#handling-a-command)) — the platform recognizes the generated class as
`CommandRequestHandler` the same way it recognizes this one.

See [Commands](live.md#commands) for the request/response shape and error codes.

## See also

- [QTScript (beta)](qtscript.md) — the same strategies written with the ceremony left out.
- [Strategies](strategy.md) — compile, validate, list and read back a strategy, in either language.

[engine-javadoc]: https://qtsurfer.github.io/qtsurfer-engine-java-docs/
[market-hint-javadoc]: https://qtsurfer.github.io/qtsurfer-engine-java-docs/com/wualabs/qtsurfer/engine/strategy/event/signal/MarketHintSignal.html
[signal-javadoc]: https://qtsurfer.github.io/qtsurfer-engine-java-docs/com/wualabs/qtsurfer/engine/strategy/event/signal/package-summary.html
[strategy-skill]: https://github.com/QTSurfer/strategy-skills
