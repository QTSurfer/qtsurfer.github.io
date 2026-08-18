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
| `index.html` | Generated Redoc HTML — **never edit manually** |
| `README.md` | Repo README with strategy example and API quickstart |
| `.github/workflows/redoc_index.yml` | CI: regenerates `index.html` on push |

## Common Tasks

### Update the API spec
Edit `openapi.yaml` directly. The spec follows OpenAPI 3.1.0 and uses:
- `bearerAuth` security scheme (JWT)
- Tags: `Exchange`, `Backtesting`, `Strategy`
- Schemas in `#/components/schemas/`

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
- **Version** is in `info.version` inside `openapi.yaml` — bump it when the API surface changes: a
  schema, an operation, a parameter, a response. Editing `servers`, descriptions or examples is not
  an API change and does not need one
