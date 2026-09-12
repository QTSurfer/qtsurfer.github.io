# Account — tier limits and live usage

All account routes require a bearer JWT obtained from [authentication](../README.md#api-quick-start).
Split into two endpoints on purpose: your tier and its limits never change mid-session and cost
nothing to fetch, while usage is a live figure that changes on every dataset upload or strategy
execution.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/account` | Your identity and tier limits |
| `GET` | `/account/usage` | Your live storage usage against those limits |

## Getting your tier and limits

`GET /account` — no database call behind it, safe to call on every page load.

```bash
curl https://api.qtsurfer.net/v1/account \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "userId": "76b90203-03c2-46f6-b366-9944f167e818",
  "tier": "free",
  "maxDatasets": 3,
  "maxDatasetBytes": 52428800,
  "maxTotalStorageBytes": 104857600,
  "_links": {
    "self": { "href": "/v1/account" },
    "usage": { "href": "/v1/account/usage" }
  }
}
```

| Field | Notes |
|---|---|
| `userId` | your account id — the JWT `sub` claim |
| `tier` | your current subscription tier |
| `maxDatasets` | maximum number of active [datasets](datasets.md) your tier allows |
| `maxDatasetBytes` | maximum size, in bytes, of a single dataset version |
| `maxTotalStorageBytes` | maximum combined storage, in bytes, across every dataset, strategy-execution signal, and registered strategy on your account — see below |

## Getting your live usage

`GET /account/usage` — how much of `maxTotalStorageBytes` you're currently using. **One shared
pool, not one cap per resource type**: datasets, strategy-execution signals, and registered
[strategies](strategy.md) all count against the same total, since they compete for the same
underlying storage. Not guaranteed real-time — a just-completed upload or strategy execution may
take a short moment to be reflected here.

```bash
curl https://api.qtsurfer.net/v1/account/usage \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "datasetsUsed": 2,
  "datasetBytesUsed": 15728640,
  "signalsUsed": 1,
  "signalBytesUsed": 524288,
  "strategiesUsed": 4,
  "strategyBytesUsed": 40960,
  "storageBytesUsed": 16293888,
  "_links": {
    "self": { "href": "/v1/account/usage" },
    "account": { "href": "/v1/account" }
  }
}
```

| Field | Notes |
|---|---|
| `datasetsUsed` / `datasetBytesUsed` | active datasets and their combined current-version bytes — the same set `maxDatasets` limits |
| `signalsUsed` / `signalBytesUsed` | recorded strategy-execution signal uploads and their combined bytes |
| `strategiesUsed` / `strategyBytesUsed` | registered strategies and the combined bytes of each one's source plus its latest compiled bytecode (superseded compilations aren't counted) |
| `storageBytesUsed` | `datasetBytesUsed + signalBytesUsed + strategyBytesUsed` — the number checked against `GET /account`'s `maxTotalStorageBytes` |

## Where the limit is enforced

`maxTotalStorageBytes` is checked when you add new dataset bytes — `POST /datasets/{datasetId}/uploads/{uploadId}/finalize`
and `POST /datasets/imports` both return `429` if your account is already at or over the limit (see
[Datasets](datasets.md) for the exact wording). Strategy-execution signals and registered
strategies are reported in `storageBytesUsed` but do not themselves trigger a `429` today — delete
a dataset to free space if you're at your limit.

## Related guides

- [Datasets](datasets.md) — the resource that both counts toward, and can be blocked by,
  `maxTotalStorageBytes`.
- [Strategies](strategy.md) — registered strategies count toward `strategyBytesUsed`.
