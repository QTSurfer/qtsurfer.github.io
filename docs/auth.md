# Authentication and scopes — getting a token and seeing what your key may do

Every route except `POST /auth/token` and the public catalogue `GET /live/public` expects a bearer
JWT (`Authorization: Bearer <token>`). The JWT is short-lived and comes from exchanging your API
key, issued in the web app, at `POST /auth/token`. The key itself is accepted on that one route
only.

## Getting a token

```bash
curl -X POST https://api.qtsurfer.net/v1/auth/token \
  -H "X-API-Key: <your-api-key>"
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scopes": { "backtests": ["read", "write", "execute"], "exchanges": ["read"] },
  "tier": "free"
}
```

| Field | Notes |
|---|---|
| `access_token` | send it as `Authorization: Bearer <token>` on every other call |
| `token_type` | always `Bearer` |
| `expires_in` | seconds until the token expires. Ask for a new one before then, or on a `401` |
| `scopes` | what your key may do, [below](#scopes) |
| `tier` | the subscription tier the token was issued for; it sets your limits, see [Account](account.md) |

A key that is unknown, revoked or expired is answered `401`; the body is `AuthTokenError` in the
API reference.

## Scopes

A key carries scopes: a map from a resource to the actions it may take on it, in lower case.

```json
{ "backtests": ["read", "write", "execute"], "exchanges": ["read"] }
```

- A key with no scopes is `{}`.
- You see them in two places, as the same map: the `scopes` of the token answer above, and the
  `scopes` of [`GET /account`](account.md#getting-your-tier-and-limits), which needs no new token.
- The token carries the scopes your key had when it was issued. Change the key's scopes and the
  change shows from the next token on, at most `expires_in` seconds later.
- **Today the API reports the scopes of a key; it does not yet refuse an operation because a scope
  is missing.** The tables below are what each operation will require once it does, so a key can be
  given the scopes it needs ahead of time.

### Resources and actions

| Resource | Actions | Covers |
|---|---|---|
| `exchanges` | `read` | the list of exchanges, their instruments and pools |
| `market_data` | `read` | the hourly ticker and kline downloads |
| `strategies` | `read`, `write` | list, inspect and read the source of a strategy; compile, validate and delete one |
| `backtests` | `read`, `write`, `execute` | prepare, run, sweep and cancel backtests; read their status and results |
| `datasets` | `read`, `write` | list and read your datasets; create, upload, import and delete them |
| `live` | `read`, `write`, `execute` | read live runs, their signals and paper accounts; change a run; start, stop and command one, and manage its stream |

`read` lists and gets. `write` creates, changes, cancels or deletes without running anything.
`execute` starts a run: a backtest, a sweep, a live run.

### The scope each operation requires

**Exchanges and market data** — [Market data](market_data.md)

| Operation | Scope |
|---|---|
| `GET /exchanges`, `GET /exchange/{exchangeId}/instruments`, `GET /exchange/{exchangeId}/{segment}/instruments` | `exchanges` : `read` |
| `GET /exchange/{exchangeId}/tickers/{base}/{quote}`, `GET /exchange/{exchangeId}/klines/{base}/{quote}` | `market_data` : `read` |

**Strategies** — [Strategies](strategy.md)

| Operation | Scope |
|---|---|
| `GET /strategies`, `GET /strategy/{strategyId}`, `GET /strategy/{strategyId}/code` | `strategies` : `read` |
| `POST /strategy`, `POST /strategy/{strategyId}/validate`, `DELETE /strategy/{strategyId}` | `strategies` : `write` |

**Backtests and sweeps** — [Backtests](backtest_execute.md), [Parameter sweeps](backtest_sweep.md)

| Operation | Scope |
|---|---|
| `POST …/prepare`, `DELETE …/execute/{jobId}`, `DELETE …/executeSweep/{requestId}/{sweepId}` | `backtests` : `write` |
| `POST …/execute`, `POST …/executeSweep/{requestId}` | `backtests` : `execute` |
| `GET …/prepare/{jobId}`, `GET …/execute/{jobId}`, `GET …/executeSweep/…` (result, sensitivity, equity curve) | `backtests` : `read` |

**Datasets** — [Datasets](datasets.md)

| Operation | Scope |
|---|---|
| `GET /datasets`, `GET /datasets/{datasetId}`, `GET /datasets/{datasetId}/uploads/{uploadId}`, `GET /datasets/{datasetId}/imports/{importId}` | `datasets` : `read` |
| `POST /datasets`, `DELETE /datasets/{datasetId}`, `POST /datasets/{datasetId}/uploads`, `POST /datasets/{datasetId}/uploads/{uploadId}/finalize`, `POST /datasets/imports` | `datasets` : `write` |

**Live runs** — [Live execution](live.md), [Paper trading](live_paper.md)

| Operation | Scope |
|---|---|
| `GET /live`, `GET /live/{runId}`, `GET /strategy/{strategyId}/live`, `GET /live/{runId}/signals`, `GET /live/{runId}/paper`, `GET /live/{runId}/paper/equity`, `POST /live/token` | `live` : `read` |
| `PATCH /live/{runId}`, `PUT /live/{runId}/params` | `live` : `write` |
| `POST /strategy/{strategyId}/live`, `DELETE /strategy/{strategyId}/live`, `POST /live/{runId}/commands`, `POST /live/{runId}/stream`, `DELETE /live/{runId}/stream` | `live` : `execute` |

**No scope:** `GET /account` and `GET /account/usage` need a valid token and nothing more;
`GET /live/public` needs no token at all.
