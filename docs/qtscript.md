# QTScript (beta)

QTScript is a compact way to write a strategy: you keep the part that is yours — indicators, windows,
signals — and leave out the ceremony of a Java class (package, imports, class, base class, property
annotations, listener boilerplate). **Every `{ }` body is plain Java**, so everything the [Java
strategy API](strategy_coding.md) offers inside a body works unchanged. A QTScript file becomes exactly
one Java class and goes through the same server-side compilation as a Java strategy.

It is **in beta** and will gain syntax. Java remains the established route, with the full engine API;
anything QTScript cannot express is written in Java (see [what it does not do](#what-it-does-not-do)).

## Submit it like any strategy

There is no separate endpoint and no header to set: send the raw source to
[`POST /strategy`](strategy.md#compiling-a-strategy) with `Content-Type: text/plain`, exactly as for
Java. The platform tells the two apart by the text — a QTScript source starts with `strategy`, and
whitespace or comments (`//`, `/* */`) before it are ignored, so a description can sit on top of the
file. `.qtscript` is the conventional file extension; only the text is sent.

```bash
curl -X POST https://api.qtsurfer.net/v1/strategy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/plain" \
  --data-binary @rsi-reversion.qtscript
```

The answer is the same as for Java: a `strategyId` and the `declaredProperties` — every `param` you
declared is listed there.

## A whole strategy

This is the complete file: no imports, no class, no listener.

```
strategy "RSI reversion"

param rsiLow  = 30  "Oversold"
param rsiHigh = 70  "Overbought"

instruments */usdt

setup:
  rsi(14) window m1 {
    if (actual < rsiLow)  emitBuy(price);
    if (actual > rsiHigh) emitSell(price);
  }
```

It declares two parameters, accepts any base quoted in USDT, registers a 14-period RSI and watches it
on a one-minute window, emitting a signal on each threshold.

## The parts of a file

| Part | What it does | Example |
|---|---|---|
| `strategy` | The first line: the name and, optionally, the data source (`ticker` by default, `kline`, `funding`) | `strategy "RSI reversion"` · `strategy Bars kline` |
| `param` | A configurable value. The type comes from the literal (`9` → `int`, `0.5` → `double`, `true` → `boolean`, `"text"` → `String`). **The name is the key** that a run's `params` and a sweep axis use | `param rsiLow = 30 "Oversold"` |
| `init { }` | Optional. Plain Java run once when the strategy is built — engine setters | `init { setPercentGain(0.5); }` |
| `instruments` | Optional. Which markets: pairs (`BASE/QUOTE`, either side may be `*`), regular expressions (`~"..."`, matched against the whole symbol), or a Java body for full control | `instruments */usdt` · `instruments btc/usdt, eth/*` |
| `setup:` | The indicators, **one builder call per line** (the same catalogue a Java strategy uses). The lines under `setup:` are indented, and the first line back at column 0 ends the section | `ema(12)` · `bollinger(20, 2)` |
| Windows | Where the logic goes — see below | `rsi(14) window m1 { ... }` |

## Windows

A window fires when its period closes, not on every tick, and wraps one indicator. A period is one of
`s1 s5 s10 s30 m1 m3 m5`, or a whole number of seconds (`window 900 { ... }`); omitted, it is `s1`.
Five ways to write one:

```
setup:
  rsi(14) window m1 { ... }      // inline, on the indicator this line registers
  rsi(33) window Oversold        // same, with the body in a named section below
  window price m5 { ... }        // inline, on an indicator by name
  window ema12 Trend             // by name, body in a named section

window Oversold m1 { ... }       // a named section, at column 0
Trend s5 { ... }                 // `window` is optional here
```

A section called `Main` that nothing references watches the primary value (`price`, or `rate` on
funding), which makes the shortest useful file:

```
strategy Simple

Main m1 {
  if (actual > prev) emitBuy(price);
}
```

### Which indicator a window is on

Inside any window body, `$indicator` is the name of the indicator that window is attached to, as a
`String`: `"ema12"` for a window written on the line `ema(12)`, `"price"` on a `Main` (`"rate"` on
funding). The `$` marks a name QTScript provides; the names you declare cannot start with one. A named
section attached to several indicators sees, each time it fires, the indicator that fired.

It is also how a body reaches an indicator that the same builder call registered beside the one it is on.
`bollinger(20, 2)` registers three under one name: the middle band, `blgr20_2`, and the outer bands, that
name followed by `Upper` and `Lower`. A window written on that line attaches to the middle band, so
`actual` is the middle band's value, and `value($indicator + "Upper")` and `value($indicator + "Lower")`
read the other two:

```
setup:
  bollinger(20, 2) window m1 {
    if (price > value($indicator + "Upper")) emitSell(price);
    if (price < value($indicator + "Lower")) emitBuy(price);
  }
```

A window that names an indicator which is not registered, such as `window nosuch m1 { ... }`, is not
rejected when you register the source. Whether the name exists can depend on your `param`s (a `param
fast` used as `ema(fast)` registers a different name for each value) and on indicators registered from
Java, so it is only found when the strategy is [validated](strategy.md#checking-it-actually-runs), which
then fails on the window's line: `QTScript line 4: unknown indicator 'nosuch'`.

## Inside a body

Your Java, plus what is already in scope — nothing needs importing:

| In scope | What it is |
|---|---|
| `actual`, `prev` | the window's new and previous value |
| `price` (ticker) · `price open high low close volume` (kline) · `rate` (funding) | the current values, as plain variables |
| `value("name")` | any other indicator's current value |
| `$indicator` | the name of the indicator this window is on, as a `String` — [see above](#which-indicator-a-window-is-on) |
| `store` | the per-instrument state shared by every window of that instrument |
| `emitBuy(price)`, `emitSell(price)`, `emitInfo(key, values…)`, `emitSignal(signal)` | signal emission |
| every `param` | readable by its name |

A position flag in the store, emitting on the crossing only once:

```
strategy "EMA cross"

param fast = 9  "Fast EMA"
param slow = 21 "Slow EMA"

setup:
  ema(fast)
  ema(slow)
  window price s5 {
    double f = value("ema" + fast);
    double s = value("ema" + slow);
    if (f > s && !store.is("long")) {
      store.set("long");
      emitBuy(price);
    }
    if (f < s && store.is("long")) {
      store.unset("long");
      emitSell(price);
    }
  }
```

`value("ema" + fast)` reads any registered indicator by name; `store` is the same store every window of
the instrument shares.

## Candles

`strategy … kline` gives the bar's fields as plain variables. A kline strategy never takes an
interval: the bar width is the `cadence` you [prepare the data at](backtest_execute.md#kline-you-choose-the-bar-width),
so the same file runs at any of them.

```
strategy "Range breakout" kline

param minRange = 0.5 "Minimum range, percent"

setup:
  window close m1 {
    double range = (high - low) / low * 100.0;
    if (range < minRange) return;
    if (close > open) emitBuy(close);
    else              emitSell(close);
  }
```

## Running it

A registered QTScript strategy is prepared, executed and swept like any other:
[`prepare`, `execute`](backtest_execute.md) and [`executeSweep`](backtest_sweep.md), with the
`strategyId` you got back. Sweep axes and `params` use the names of your `param` lines.

| `strategy …` | Prepare | Execute | Sweep |
|---|---|---|---|
| ticker (default) | yes | yes | yes |
| `kline` | yes | yes | yes |
| `funding` | yes | not yet | not yet |

See [Data sources](backtest_execute.md#data-sources) for the details, including why a `funding`
strategy can be registered and its data prepared but not yet run.

## When something is wrong

Errors are reported against **your** file, never the generated Java. Registering a source with a
mistake is a `400` whose message carries `Line N, Column M:` entries, for QTScript's own errors (an
unknown section, a bad period, a duplicate parameter, a malformed instrument pattern) and for Java
errors from inside a body. A failure while the strategy runs is recorded on the job the same way,
on the line the body came from:

```
QTScript line 6: Index 2 out of bounds for length 1
```

## The strategy id

`POST /strategy` returns the same `strategyId` for the same source. For QTScript the id comes from
the text, because indentation is part of the grammar: a byte-order mark, the style of line endings,
whitespace at the end of a line and blank lines before the first and after the last line are ignored;
anything else — a comment, the indentation, a blank line in between — gives a different id. (Java
strategies are more forgiving; see [Strategies](strategy.md#compiling-a-strategy).)

## What it does not do

By design, and each one is a reason to write the strategy in Java instead:

- **No `update()`.** Windows are the model; a strategy that has to see every tick belongs in Java.
- **No cross-instrument logic** — reading other instruments' indicators needs the full class.
- **No custom indicator classes**, no extra fields or methods beyond what the sections declare, and
  no multi-source strategies.
- **One class.** Anything that wants helper types is a Java strategy.

Switching is never a dead end: a `.qtscript` file is a Java class with the ceremony left out.

## Going further

The maintained **`qtsurfer-qtscript-strategy`** skill has the full language reference — every section,
the instrument filter in detail, reserved names, and more examples — and works with agents that read
skills:

```bash
npx skills add QTSurfer/strategy-skills --skill qtsurfer-qtscript-strategy
```

The bodies are written against the strategy API documented in the
[`qtsurfer-java-strategy`](https://github.com/QTSurfer/strategy-skills) skill and in
[Coding Java strategies](strategy_coding.md).
