# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project Overview

Public-facing OpenAPI documentation for the QTSurfer API, hosted at **[qtsurfer.github.io](https://qtsurfer.github.io)** via GitHub Pages.

## How It Works

```
openapi.yaml ──► GitHub Actions ──► Redocly CLI ──► index.html ──► GitHub Pages
```

1. Edit `openapi.yaml` (the single source of truth)
2. Push to `main`
3. GitHub Actions workflow (`.github/workflows/redoc_index.yml`) runs `redocly build-docs` and auto-commits the generated `index.html`
4. GitHub Pages serves `index.html` at the public URL

## Files

| File | Description |
|------|-------------|
| `openapi.yaml` | OpenAPI 3.1.0 spec — **edit this** |
| `asyncapi.yaml` | AsyncAPI 3.1.0 spec of the Live Execution WebSocket (Centrifugo client protocol): frames, `sig:<runId>` channels, the `live.params` RPC, error codes. Reuses `openapi.yaml` schemas by `$ref` — **edit this** for any WebSocket change |
| `scripts/live_ws_conformance.py` | Checks `asyncapi.yaml`: `--examples` offline against its own schemas, or live against the running service (needs `QTSURFER_APIKEY`) |
| `index.html` | Generated Redoc HTML — **never edit manually** |
| `README.md` | Repo README with strategy example and API quickstart |
| `docs/*.md` | Per-endpoint-group reference (full params, examples, response fields) that the README links out to instead of inlining — e.g. `docs/backtest_execute.md`, `docs/backtest_sweep.md` |
| `.github/workflows/redoc_index.yml` | CI: regenerates `index.html` on push |

## Common Tasks

### Update the API spec
Edit `openapi.yaml` directly. The spec follows OpenAPI 3.1.0 and uses:
- `bearerAuth` security scheme (JWT)
- Tags: `Exchange`, `Backtesting`, `Strategy`
- Schemas in `#/components/schemas/`

### Update the WebSocket contract
Edit `asyncapi.yaml`. The signal payload and the `live.params` result are **not** redefined there:
they are `$ref`s into `openapi.yaml` (`LiveSignal`, `LiveParamsUpdateResult`), so a change to either
schema changes both contracts at once — keep those schemas plain JSON Schema (OpenAPI 3.1 style:
`type: ['string', 'null']`, never the 3.0 `nullable: true`, which JSON Schema ignores). Then:
```bash
npx @asyncapi/cli@6.2.0 validate asyncapi.yaml
uv run scripts/live_ws_conformance.py --examples     # every example matches its schema
QTSURFER_APIKEY=... uv run scripts/live_ws_conformance.py   # the running service matches the spec
```
Describe only what a client sees on the socket. Server-side wiring (proxies, internal routes, the
message bus behind the relay) stays out, and so do channel namespaces that are not a public product.

### Preview locally
```bash
npx @redocly/cli preview-docs openapi.yaml
# Opens browser at http://localhost:8080
```

### Regenerate HTML locally
```bash
npx @redocly/cli build-docs openapi.yaml --output=index.html
```

### Validate spec
```bash
npx @redocly/cli lint openapi.yaml
```

## Key Conventions

- **openapi.yaml is the source of truth** — the spec is maintained here, not extracted from code
- **index.html is generated** — the CI auto-commits it, so expect merge noise if editing the spec in a branch
- **Only one CI generates it.** This repo is mirrored, and the mirror's CI reads `.github/workflows`
  too, so the job is guarded to run on GitHub alone. Without that guard both sides regenerate
  `index.html` and commit it, and the mirrors diverge by two content-identical commits on every spec
  change. Do not remove the guard
- **This is a public repo** — no internal URLs, credentials, or infrastructure details
- **Server URLs**: staging is `api.qtsurfer.net`, and it is the one that actually serves the API.
  `api.qtsurfer.com` is listed as production but is reserved and not yet live — do not point examples
  or defaults at it. Generated clients take their default base URL from the **first** `servers`
  entry, so its order is load-bearing, not cosmetic
- **`asyncapi.yaml` has its own `info.version`**, bumped only when the WebSocket surface changes (a
  frame, a channel, an RPC method, an error code). It does not follow `openapi.yaml`'s version: a
  REST-only change leaves it alone. A change to a shared schema (`LiveSignal`, `LiveParamsUpdateResult`)
  bumps both
- **Version** is in `info.version` inside `openapi.yaml` — bump it when the API surface changes: a
  schema, an operation, a parameter, a response. Editing `servers`, descriptions or examples is not
  an API change and does not need one
