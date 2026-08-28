# Strategies

Compile a Java strategy, check it can actually run, list/inspect/delete what you've registered,
and read back its source.

This page documents the strategy REST resources. For the Java source itself — base classes,
execution and information signals, advanced order parameters, and chart metadata — see [Coding
Java strategies](strategy_coding.md).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/strategy` | Compile and register |
| `GET` | `/strategies` | List your registered strategies |
| `GET` | `/strategy/{strategyId}` | Get one, including validation state |
| `POST` | `/strategy/{strategyId}/validate` | Check it actually runs |
| `GET` | `/strategy/{strategyId}/code` | Read back the registered source |
| `DELETE` | `/strategy/{strategyId}` | Release it |

## Compiling a strategy

`POST /strategy` — body is the raw Java source, `Content-Type: text/plain`.

```bash
curl -X POST https://api.qtsurfer.net/v1/strategy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/plain" \
  --data-binary @MyStrategy.java
```

```json
{
  "strategyId": "2ul144qe9tlwzu5anhwvc6",
  "declaredProperties": [
    {"name": "rsi.period", "description": "RSI period", "defaultValue": "14",
     "reflected": true, "min": 2, "max": 50, "step": 1},
    {"name": "enabled", "description": "Enabled", "reflected": true}
  ]
}
```

**This answers one question: is the source valid Java.** It compiles, registers, and hands back
the id — nothing more. Whether the class can actually run is [`validate`](#checking-it-actually-runs);
everything known about a strategy, validation included, is read from [`GET
/strategy/{strategyId}`](#getting-a-strategy).

**`strategyId` is derived from what the code *means*, not from how it's written.** A comment, a
blank line, re-indenting, reordering imports, or moving a method around all return the **same**
id — you have not created a second strategy. Renaming a variable, changing an identifier's case,
or reordering fields/statements returns a **different** one. Two consequences:

- re-submitting a strategy you only reformatted is free — you get back the id you already had,
  along with any validation already recorded against it;
- the id says nothing about *behaviour*. Two sources computing the same thing by different means
  are two strategies, since deciding otherwise would mean deciding program equivalence.

### `declaredProperties` — `DeclaredProperty`

The sweep/execute param-key vocabulary this strategy is known to accept — established without
constructing the strategy, so a caller can catch a typo'd key before submitting a sweep instead
of only learning it from a rejected one. **Best-effort, not exhaustive**: a property registered
imperatively (e.g. through an attached `RiskConfig`) needs a live instance to discover and won't
appear here — a name absent from this list may still be valid.

| Field | Notes |
|---|---|
| `name` | the key a sweep or execute param map uses for this property |
| `description` | human-readable label, as declared |
| `defaultValue` | the declared default, as a string. **Absent, not `null`, when none was declared** |
| `reflected` | `true` — a value is injected into the strategy's field; `false` — only available through the property map |
| `min`, `max`, `step` | suggested sweep/range bounds, if declared. **Advisory only, never validated** |

Errors: `400` not valid Java — the message carries the compiler diagnostics, nothing is
registered · `429` too many compilations in flight, retry later.

## Checking it actually runs

`POST /strategy/{strategyId}/validate`

Instantiates the compiled class and drives it through a bounded synthetic series, so a wiring
fault surfaces here instead of at your first real backtest. The verdict — pass or fail, plus any
engine notices — is recorded and served from `GET /strategy/{strategyId}`.

**Idempotent.** If a verdict already exists for the current compilation it comes straight back
with `200` and nothing is queued; otherwise the check is queued and this returns `202`. **The
status code, not the body, is what tells the two apart** — a `200` can also carry `validation:
pending`, left by a check an earlier call queued. `202` means *this call started a check*;
`pending` means only *a check is outstanding*. Poll `GET /strategy/{strategyId}` until
`validation` leaves `pending`.

Recompiling supersedes a verdict — the old answer described bytecode that would no longer run —
which is what makes this callable again after an edit.

```bash
curl -X POST https://api.qtsurfer.net/v1/strategy/2ul144qe9tlwzu5anhwvc6/validate \
  -H "Authorization: Bearer $TOKEN"
# → 202 {"strategyId": "2ul144qe9tlwzu5anhwvc6", "validation": "pending"}
```

Errors: `404` no such registered strategy for this user.

## Getting a strategy

`GET /strategy/{strategyId}` — response is `StrategyState`, the same shape `validate`'s
already-validated `200` returns.

**`validation: passed` does not mean the strategy is correct.** It means the class loaded and
survived the first event of a short synthetic run — a floor, not a guarantee. When
`dryRunIncomplete` is `true` it's a lower floor still, since the run didn't finish.

| Field | Notes |
|---|---|
| `validation` | `not_validated` \| `pending` \| `passed` \| `failed` |
| `compiledAt` | when the live compilation was produced |
| `requiredSources` | market data the strategy needs (`Ticker`, `KLine`, `FundingRate`), read off the compiled class. **Absent is not "needs nothing"** — absent means the platform couldn't establish the answer without constructing the strategy (a `MultiSourceStrategy`, a class overriding `getMarketDataSource()`, or anything registered before this field existed). Re-registering the source fills it in |
| `validatedAt` | when the verdict was recorded; absent until there is one |
| `detail` | why validation failed, or why a queued check hasn't reported. Present on `failed`, and alongside `validationStalled` |
| `notices` | what the run surfaced. An empty/absent list is **not** a clean bill of health when `dryRunIncomplete` is `true` |
| `noticesTruncated` | notices dropped past the cap; absent when none were |
| `dryRunIncomplete` | the check didn't finish its budget — ran out of time, was refused (too many unfinishable runs already in flight), or hit a failure attributable to the synthetic instrument rather than the strategy. The verdict stands as far as it went |
| `validationStalled` | a queued check hasn't reported for far longer than one takes. Nothing is disproved — the check just hasn't run. Stop waiting and re-request later |
| `_links.code` | present on a full body (`200` here, and `validate`'s already-validated `200`), absent from `validate`'s `202` stub. Points at [`GET .../code`](#reading-back-the-source) — following it can still `404` for a strategy with no source of its own (see below) |

```json
{
  "strategyId": "6bsh31ikwkuivhtgcoa6s4",
  "validation": "passed",
  "compiledAt": "2026-08-04T16:23:04Z",
  "requiredSources": ["Ticker"],
  "validatedAt": "2026-08-04T16:24:11Z",
  "notices": [
    {"level": "WARN", "code": "indicator.bar-data-on-ticker-path",
     "message": "Indicator requires bar data but is on the ticker path",
     "provenance": "compile-dry-run"}
  ],
  "_links": {"code": {"href": "/v1/strategy/6bsh31ikwkuivhtgcoa6s4/code"}}
}
```

Errors: `404` no such registered strategy for this user — never stale/expired, registration and
verdict are stored durably, not cached.

## Listing your strategies

`GET /strategies` — every strategy you've registered and not deleted, most recently compiled
first. **Never a `404`** — an empty array if you have none.

Each entry (`StrategySummary`) carries the same `compiledAt`/`requiredSources` provenance as
`StrategyState`, but **not** validation state, so listing stays cheap regardless of how many
strategies you have. Check a specific one's validation with `GET /strategy/{strategyId}`.

```bash
curl https://api.qtsurfer.net/v1/strategies -H "Authorization: Bearer $TOKEN"
```

```json
{
  "strategies": [
    {"strategyId": "6bsh31ikwkuivhtgcoa6s4", "compiledAt": "2026-08-19T10:15:00Z", "requiredSources": ["Ticker"]},
    {"strategyId": "2ul144qe9tlwzu5anhwvc6", "compiledAt": "2026-08-12T09:02:11Z"}
  ]
}
```

## Reading back the source

`GET /strategy/{strategyId}/code` — the exact source last submitted for this id, whitespace and
comments included: the same text `strategyId` was derived from.

**"If available", not "always".** A strategy resolved only through a shared/marketplace listing
you copied by reference carries no source of its own, and reads as `404` here — the same as a
`strategyId` you never registered. That's the honest answer either way: nothing is there to
return.

```bash
curl https://api.qtsurfer.net/v1/strategy/2ul144qe9tlwzu5anhwvc6/code \
  -H "Authorization: Bearer $TOKEN"
# → {"strategyId": "2ul144qe9tlwzu5anhwvc6", "code": "package strategy;\npublic class..."}
```

Errors: `404` no such registered strategy for this user, or nothing to read for this id.

## Deleting a strategy

`DELETE /strategy/{strategyId}` — frees up the slot on a plan capped at a strategy count.

Removes it from `GET /strategy/{strategyId}` and `GET /strategies`. **Not** undone by
re-submitting the same source — that registers a new strategy, with a new id. **Backtests
already run against it are unaffected**: deleting stops it from counting against your account and
stops you validating/re-running it under this id, but doesn't erase what already happened. Only
removes a strategy you registered yourself — deleting your copy of a shared/marketplace listing
never affects the original.

```bash
curl -X DELETE https://api.qtsurfer.net/v1/strategy/2ul144qe9tlwzu5anhwvc6 \
  -H "Authorization: Bearer $TOKEN"
# → {"strategyId": "2ul144qe9tlwzu5anhwvc6", "deleted": true}
```

Errors: `404` no such registered strategy for this user.
