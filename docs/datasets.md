# Datasets — bring your own data

Backtest against a CSV or parquet file you upload instead of a managed exchange: create a dataset,
`PUT` the file to a presigned URL, finalize it to trigger ingest, then
[prepare/execute](backtest_execute.md) exactly as normal but with the reserved `exchangeId: user`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/datasets` | Create a dataset + first upload session |
| `GET` | `/datasets` | List your datasets |
| `GET` | `/datasets/{datasetId}` | Get one |
| `DELETE` | `/datasets/{datasetId}` | Delete |
| `POST` | `/datasets/{datasetId}/uploads` | Open a new upload session for an existing dataset |
| `POST` | `/datasets/{datasetId}/uploads/{uploadId}/finalize` | Trigger ingest |
| `GET` | `/datasets/{datasetId}/uploads/{uploadId}` | Poll upload/ingest state |
| `POST` | `/datasets/imports` | Create a dataset by fetching history instead of uploading it |
| `GET` | `/datasets/{datasetId}/imports/{importId}` | Poll fetch/ingest state |

v1 is ticker data only — `type` is always `"ticker"`. `instrument` must be a plain spot pair
(`BASE/QUOTE`, exactly one `/`); derivative forms (`BTC/USDT:USDT`) are rejected.

## Creating a dataset

`POST /datasets` — creates the dataset **and** its first upload session in one call: a presigned
URL your client `PUT`s the file to directly, no API credentials involved in that `PUT`.

| Field | Type | Notes |
|---|---|---|
| `name` | string | required, unique among your datasets. `409` if already taken |
| `instrument` | string | required, plain spot pair |

```bash
curl -X POST https://api.qtsurfer.net/v1/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My BTC ticks","instrument":"BTC/USDT"}'
```

`DatasetCreated` (`201`) — the metadata available immediately after creation plus the upload
session. It is not yet the full [`Dataset`](#dataset-shape): lifecycle fields such as `createdAt`,
`currentVersionId`, range, and cadence are obtained from `GET /datasets/{datasetId}` after the
relevant lifecycle stages.

```json
{
  "datasetId": "ds_3f9a1c2e7b0d4a5f", "name": "My BTC ticks",
  "type": "ticker", "instrument": "BTC/USDT",
  "uploadId": "up_1a2b3c4d5e6f7a8b",
  "upload": {
    "url": "https://storage.qtsurfer.com/.../uploads/up_1a2b3c4d5e6f7a8b/raw.csv?X-Amz-...",
    "expiresInMinutes": 15
  }
}
```

`uploadId` is what you pass to [finalize](#finalizing-an-upload-triggering-ingest); `upload.url`
is the presigned target — `PUT` the raw file there directly, no `Authorization` header.

Lost this response? Nothing lost — call [`POST .../uploads`](#opening-a-new-upload-session) on
this dataset's id and you get the very same upload session back, as long as you haven't finalized
it yet.

Errors: `400` invalid request, or `instrument` isn't a plain spot pair · `409` dataset name
already taken · `429` your tier's dataset count limit is reached — delete one, or upgrade.

## Opening a new upload session

`POST /datasets/{datasetId}/uploads` — get a fresh upload session for a dataset you already have:
a corrected file, or the next chunk of history. Same idempotency contract as `POST /datasets`'s
own upload half: at most one session is open per dataset at a time, so calling this again before
finalizing just hands back that same session — safe to retry if a response gets lost. Once a
session has been finalized (successfully or not), the next call here opens a genuinely new one.

```bash
curl -X POST https://api.qtsurfer.net/v1/datasets/$DATASET_ID/uploads \
  -H "Authorization: Bearer $TOKEN"
```

`201` — the same `{uploadId, upload}` shape `POST /datasets` returns, without the dataset
metadata around it:

```json
{
  "uploadId": "up_1a2b3c4d5e6f7a8b",
  "upload": {
    "url": "https://storage.qtsurfer.com/.../uploads/up_1a2b3c4d5e6f7a8b/raw.csv?X-Amz-...",
    "expiresInMinutes": 15
  }
}
```

Errors: `404` no such dataset for this user.

## Uploading the file

**CSV or parquet.** A CSV needs a header row; a parquet file carries its columns by name already.
Either way, `timestamp` (ISO-8601, or numeric epoch seconds / millis / micros — detected from the
first row, then enforced for every later row) and `close` are required. Optional: `open`, `high`,
`low`, `volume`, `quoteVolume`, `bid`, `bidSize`, `ask`, `askSize`. **Cadence and timestamp unit
are discovered from the data, not declared.**

A CSV upload is converted to our native columnar format (`lastra`) for storage. A parquet upload
is stored as-is today. Either way, check `dataFormat` on the [ready
version](#datasetversion--one-successfully-ingested-upload) for which one you actually get back —
don't assume it from how you uploaded it.

The bytes `PUT` to `upload.url` may be that file directly, gzipped (`.gz`), or zipped (`.zip`,
exactly one file inside — a dataset is one file regardless of how it travels). Format is detected
from the content itself: there is no filename or `Content-Type` anywhere in this flow for a
client to declare it with, so nothing needs to be sent besides the bytes.

```bash
curl -X PUT "$UPLOAD_URL" --data-binary @my-btc-ticks.csv
# or gzip/zip it first -- detected from content, no extra parameter needed
curl -X PUT "$UPLOAD_URL" --data-binary @my-btc-ticks.csv.gz
```

## Finalizing an upload (triggering ingest)

`POST /datasets/{datasetId}/uploads/{uploadId}/finalize` — call once the `PUT` above completes.
Enqueues ingest and returns immediately; poll [`GET .../uploads/{uploadId}`](#polling-ingest)
below. **Idempotent while the upload is still open** — a repeat finalize before it has produced a
version returns the same `jobId` rather than enqueueing a second ingest. Once it HAS produced a
version, `uploadId` is spent: finalizing it again is a `409`, even with different bytes freshly
`PUT` to the same URL — [open a new upload session](#opening-a-new-upload-session) instead of
reusing a spent one.

```bash
curl -X POST https://api.qtsurfer.net/v1/datasets/$DATASET_ID/uploads/$UPLOAD_ID/finalize \
  -H "Authorization: Bearer $TOKEN"
# → 202 {"jobId": "dataset-upload:.../ds_3f9a1c2e7b0d4a5f:up_1a2b3c4d5e6f7a8b"}
```

Errors: `404` no such dataset for this user; `uploadId` wasn't issued for this dataset (never
minted, or minted for a different one); or nothing was `PUT` to `upload.url` yet — a finalize with
nothing to finalize · `409` `uploadId` already produced a version (the error message names it) ·
`413` the uploaded file exceeds your tier's size limit for a dataset.

## Polling ingest

`GET /datasets/{datasetId}/uploads/{uploadId}` — poll after finalize until `status` is `ready` or
`failed`. Also reports `uploading` (finalize not called yet, but the file was `PUT`) before you
finalize at all. **Durably recorded once a version exists**, so `ready`/`failed` are permanent
answers; `uploading`/`ingesting` reflect in-flight state that can itself age out (see the `404`
case below).

### Response — `DatasetUploadState`

| Field | Notes |
|---|---|
| `status` | `uploading` (file `PUT`, not finalized yet) → `ingesting` (finalize called, worker parsing/validating) → `ready` (`version` carries the result) \| `failed` (e.g. bad CSV contract, mixed timestamp units, a `.zip` with no file inside or more than one) |
| `jobId` | the ingest job id, while `status` is `ingesting` |
| `error` | human-readable reason, present when `status` is `failed`. Durably recorded alongside the failure — stays available however long after the fact you poll |
| `version` | a [`DatasetVersion`](#datasetversion--one-successfully-ingested-upload), present when `status` is `ready` or `failed` |

#### `DatasetVersion` — one successfully ingested upload

| Field | Notes |
|---|---|
| `id` | the version id — pass as `datasetVersionId` on prepare to pin it |
| `bytes` | size of the **stored** file (`dataUrl`) — a converted `lastra` for a CSV upload (decompressed first, if it arrived as `.gz`/`.zip`), or the parquet file itself for a parquet upload. Not the size of the bytes originally `PUT` |
| `rows` | number of data rows |
| `cadence` | discovered bar cadence (`1s`, `1m`, `1h`, ...) |
| `timestampUnit` | `iso` \| `s` \| `ms` \| `us` — the unit the `timestamp` column arrived in |
| `gaps`, `largestGapSteps` | gap count at the discovered cadence, and the largest one's size in cadence steps |
| `dataUrl` | presigned GET URL to the stored file — see `dataFormat`. Present once `ready` |
| `dataFormat` | `lastra` (converted, from a CSV/gzip/zip upload) \| `parquet` (unconverted, from a parquet upload) |

```bash
curl https://api.qtsurfer.net/v1/datasets/$DATASET_ID/uploads/$UPLOAD_ID \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "uploadId": "up_1a2b3c4d5e6f7a8b",
  "status": "ready",
  "version": {
    "datasetId": "ds_3f9a1c2e7b0d4a5f", "id": "dsv_8e2b4f19c6a03d7e",
    "bytes": 4831022, "rows": 86400, "cadence": "1s",
    "timestampUnit": "iso", "gaps": 0, "largestGapSteps": 0,
    "dataUrl": "https://storage.qtsurfer.com/.../dsv_8e2b4f19c6a03d7e/ticker_BTC_USDT_....lastra?X-Amz-...",
    "dataFormat": "lastra"
  }
}
```

Errors: `404` no such dataset for this user, or genuinely nothing known about this `uploadId` — no
version, no in-flight job, nothing was ever `PUT` to its upload URL.

## Importing a dataset instead of uploading one

`POST /datasets/imports` — a second way to get data into a dataset: instead of `PUT`ting a file
yourself, ask the API to go fetch history on your behalf. Creates the dataset and starts the fetch
in the same call — there's no separate upload step, and the result lands as a dataset version
indistinguishable from an uploaded one once it's ready.

`type` selects the source. `dex` — history over a pool/pair's own on-chain market — is the only
value today; other source types join this same endpoint later. A `dex` import has two data shapes,
chosen by the top-level `cadence`:

* Omitted/blank (default) — on-chain swap history, replayed directly from the pool/pair's own
  chain, native per-trade cadence.
* `1s` \| `1m` \| `5m` — pre-aggregated candles at that width instead of raw trades. The resulting
  dataset's `type` is `klines`, not `ticker`.

| Field | Type | Notes |
|---|---|---|
| `name` | string | required, unique among your datasets. `409` if already taken |
| `instrument` | string | required, plain spot pair — the dataset's own label, independent of the pool's on-chain token order |
| `from`, `to` | string (date-time) | required, ISO-8601 UTC. `from` inclusive, `to` exclusive, `from < to`. Total span is capped by your tier |
| `cadence` | string | optional. Omitted/blank = native per-trade cadence (see below). One of `1s` \| `1m` \| `5m` instead asks for pre-aggregated candles at that width — any other value is `400` |
| `type` | string | required, `"dex"` is the only value today |
| `dex.network` | string | required, one of `ethereum` \| `robinhood` |
| `dex.id` | string | required unless `cadence` requested candles, in which case it's ignored. `"uniswap"` is the only value today — which on-chain DEX protocol `dex.contract` implements |
| `dex.version` | string | required unless `cadence` requested candles, in which case it's ignored. `"v2"` \| `"v3"` |
| `dex.contract` | string | required, the pool (v3) or pair (v2) contract address |
| `dex.factory` | string | optional — omit to auto-discover on-chain from `contract`; supply only if you already know it or the pool/pair belongs to a non-canonical factory. Either way the pool/pair is validated against whichever factory is used before anything is fetched. Ignored if `cadence` requested candles |

**On-chain cadence is native, not resampled.** A plain `dex` import (no `cadence`) keeps the
source's own per-trade event cadence — tagged `RT` on the resulting version — rather than bucketing
into candles; resample to a coarser cadence afterward as a separate step if you need one from
on-chain data. Asking for `cadence: "1s"`/`"1m"`/`"5m"` instead gets you pre-aggregated candles at
that width directly. Not every network supports every cadence yet — an unsupported combination
fails asynchronously, same as an unresolvable pool (see `failed` below), not at request time.

```bash
curl -X POST https://api.qtsurfer.net/v1/datasets/imports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weth-usdc-week",
    "instrument": "WETH/USDC",
    "from": "2026-08-01T00:00:00Z",
    "to": "2026-08-08T00:00:00Z",
    "type": "dex",
    "dex": {
      "network": "ethereum",
      "id": "uniswap",
      "version": "v3",
      "contract": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    }
  }'
# → 202 {"datasetId":"ds_3f9a1c2e7b0d4a5f","importId":"imp_01j9z...","jobId":"dataset-import:...","status":"fetching"}
```

Or, for pre-aggregated candles instead of raw on-chain swaps:

```bash
curl -X POST https://api.qtsurfer.net/v1/datasets/imports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weth-usdc-1s",
    "instrument": "WETH/USDC",
    "from": "2026-08-01T00:00:00Z",
    "to": "2026-08-01T06:00:00Z",
    "cadence": "1s",
    "type": "dex",
    "dex": {
      "network": "ethereum",
      "contract": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    }
  }'
```

`importId` is what you poll with, below — there's no separate "finalize" step the way an upload
has.

Errors: `400` invalid request, `instrument` isn't a plain spot pair, `from >= to`, `cadence`
present but not one of its supported values, the range exceeds your tier's import ceiling, the
range's rough size estimate exceeds your tier's row limit, `dex.network`/`dex.id` not one of their
supported values, `dex.contract`/`dex.factory` fail basic shape validation, or (when `cadence` is
omitted) `dex.id`/`dex.version` missing (whether the pool/pair actually resolves, and for a candle
`cadence` whether that combination is servable on the requested network, is checked later,
asynchronously — see `failed` below) · `409` dataset name already taken · `429` your tier's dataset
count limit is reached.

## Polling an import

`GET /datasets/{datasetId}/imports/{importId}` — poll after `POST /datasets/imports` until
`status` is `ready` or `failed`. An import spends real time fetching from its source before
anything is even staged; once fetched, it re-enters the exact same ingest chain an upload uses.

### Response — `DatasetImportState`

| Field | Notes |
|---|---|
| `status` | `fetching` (reading from the source, nothing staged yet — the one status only an import ever reports) → `ingesting` (fetched, staged, worker parsing/validating) → `ready` (`version` carries the result) \| `failed` |
| `jobId` | the fetch/ingest job id, while `status` is `fetching` or `ingesting` |
| `error` | human-readable reason, present when `status` is `failed` — an unresolvable pool/pair, no data in the requested range, a range older than the source retains, the fetch exceeding your tier's time ceiling, or any of the ingest-side reasons `DatasetUploadState.error` can carry, once fetching hands off to that same chain. Durably recorded, same as on the upload path |
| `version` | a [`DatasetVersion`](#datasetversion--one-successfully-ingested-upload), present when `status` is `ready` or `failed` |

```bash
curl https://api.qtsurfer.net/v1/datasets/$DATASET_ID/imports/$IMPORT_ID \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "importId": "imp_01j9z1x2y3z4a5b6c7d8e9f0g1",
  "status": "ready",
  "version": {
    "datasetId": "ds_3f9a1c2e7b0d4a5f", "id": "dsv_8e2b4f19c6a03d7e",
    "bytes": 4831022, "rows": 604800, "cadence": "RT",
    "timestampUnit": "us", "gaps": 0, "largestGapSteps": 0,
    "dataUrl": "https://storage.qtsurfer.com/.../dsv_8e2b4f19c6a03d7e/ticker_WETH_USDC_....lastra?X-Amz-...",
    "dataFormat": "lastra"
  }
}
```

Errors: `404` no such dataset for this user, or genuinely nothing known about this `importId`.

## Dataset shape

Both [`GET /datasets`](#listing-your-datasets) and [`GET
/datasets/{datasetId}`](#getting-a-dataset) return this — `from`/`to`/`cadence` mirror the
*current* version's own discovered range and cadence, so you don't need a second call to see what
a dataset covers.

| Field | Notes |
|---|---|
| `datasetId`, `name`, `type` (`"ticker"` \| `"klines"`), `instrument`, `createdAt` | always present. `type` is `"klines"` only for a `dex` import that requested a candle `cadence`; `"ticker"` for everything else (uploads, and native-cadence `dex` imports) |
| `currentVersionId` | the most recently finalized, successfully ingested version. **Absent until at least one upload has finished ingesting** |
| `updatedAt` | when `currentVersionId` last changed; absent until it has a value |
| `from`, `to`, `cadence` | the current version's own range/cadence, as discovered at ingest. **Absent until a version exists** |

`GET /datasets/{datasetId}` alone adds `dataUrl`/`dataFormat` (same meaning as on
[`DatasetVersion`](#datasetversion--one-successfully-ingested-upload)) once the current version is
`ready`, plus `_links.self`. The bulk listing never mints these — a presigned download URL for
every dataset on a screen that renders no chart isn't worth the exposure.

## Listing your datasets

`GET /datasets` — every dataset you've created and not deleted, most recently created first.
**Never a `404`** — an empty array if you have none, same convention as `GET /strategies`.

```bash
curl https://api.qtsurfer.net/v1/datasets -H "Authorization: Bearer $TOKEN"
```

## Getting a dataset

`GET /datasets/{datasetId}` — a [`Dataset`](#dataset-shape) plus a `_links.self`.

```bash
curl https://api.qtsurfer.net/v1/datasets/$DATASET_ID -H "Authorization: Bearer $TOKEN"
```

Errors: `404` no such dataset for this user.

## Deleting a dataset

`DELETE /datasets/{datasetId}` — soft delete. Stops appearing in the list/get endpoints and can
no longer be prepared from, but its object data is reclaimed later rather than purged inline, so
a backtest already running against one of its versions isn't disrupted.

```bash
curl -X DELETE https://api.qtsurfer.net/v1/datasets/$DATASET_ID -H "Authorization: Bearer $TOKEN"
# → {"datasetId": "ds_3f9a1c2e7b0d4a5f", "deleted": true}
```

Errors: `404` no such dataset for this user, or already deleted.

## Backtesting against a dataset

Once a version is `ready`, prepare and execute exactly as against a managed exchange, but with
`exchangeId: user` and `datasetId` in place of `instrument`:

```bash
curl -X POST https://api.qtsurfer.net/v1/backtest/user/ticker/prepare \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"datasetId":"ds_3f9a1c2e7b0d4a5f","from":"2026-03-14","to":"2026-03-15"}'
# → 202 {"jobId":"5ikYAMIO...","datasetId":"ds_3f9a1c2e7b0d4a5f","datasetVersionId":"dsv_8e2b4f19c6a03d7e"}
```

`execute` is unchanged — same request body as against a managed exchange, since the instrument
and range are recovered from `prepareJobId` either way. See
[`docs/backtest_execute.md`](backtest_execute.md) for the full prepare/execute reference,
including `PrepareRequest`'s `datasetId`/`datasetVersionId` fields and the dataset-backed
coverage shape on `PrepareJobState` (`cadence`/`gaps`/`largestGapSteps` in place of the
hour-walked `totalHours`/`hoursWithData`/`hoursWithoutData`).
