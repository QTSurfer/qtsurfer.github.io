# Market data

All market-data routes require a bearer JWT obtained from [authentication](../README.md#api-quick-start).
They expose the exchange catalogue and historical data that QTSurfer manages; they do not submit a
backtest or create server-side state.

## Discover exchanges and instruments

`GET /exchanges` lists the exchanges the platform knows, centralized and decentralized, each with its
`venueType` and the `segments` it offers. Ids, venue types and segments are lower-case, written the same
way wherever the API takes them:

```json
[
  {"id": "binance", "name": "Binance", "venueType": "cex", "segments": ["spot", "futures"], "liveSegments": ["spot"]},
  {"id": "bybit", "name": "Bybit", "venueType": "cex", "segments": ["spot", "futures"], "liveSegments": ["spot"]},
  {"id": "robinhood", "name": "Robinhood Chain", "venueType": "dex", "segments": ["uniswap-v3"], "liveSegments": ["uniswap-v3"]}
]
```

`venueType` is `cex` for a centralized exchange and `dex` for a decentralized one. The `segments` of a `cex`
exchange are the market segments its instruments are listed under; `liveSegments` are the ones among them a
live run can read, because live data is published for them (`spot` today). For a `dex` exchange both are the
protocols whose pools a live run can read (see [DEX pools](live.md#dex-pools)). A `dex` exchange has no
instrument catalogue: the instrument of a run on it is a pool's address. Use the id of a `cex` exchange with
either instrument route:

| Route | Meaning |
| --- | --- |
| `GET /exchange/{exchangeId}/instruments` | Instruments in the default `spot` segment |
| `GET /exchange/{exchangeId}/{segment}/instruments` | Instruments in an explicit `spot` or `futures` segment |

An instrument response is a HAL envelope. Its `data` array contains `id`, `base`, `quote`, current
`lastPrice` and `volume24h`, plus independent `coverage.tickers` and `coverage.klines` windows.
`meta.updatedAt` identifies when the catalogue was assembled; `meta.segment` identifies the segment
actually served. Treat coverage as live platform state rather than a promise that every timestamp is
available forever.

```bash
curl https://api.qtsurfer.net/v1/exchange/binance/spot/instruments \
  -H "Authorization: Bearer $QTSURFER_JWT"
```

The response's `_links` provide `self`, `spot`, and `futures` discovery links. An exchange that has no
instrument catalogue (an id `GET /exchanges` does not list, or a `dex` exchange) and a segment that is not
`spot` or `futures` return `400`; a catalogue that is not available returns `404`. The segment is written in
lower-case.

## Download hourly segments

Two routes return bytes rather than JSON:

| Route | Payload |
| --- | --- |
| `GET /exchange/{exchangeId}/tickers/{base}/{quote}` | Raw ticker events for one UTC hour |
| `GET /exchange/{exchangeId}/klines/{base}/{quote}` | Aggregated exchange-native klines for one UTC hour |

Both require the `hour` query parameter in `YYYY-MM-DDTHH` UTC form. For example,
`2026-01-15T10` covers `[2026-01-15T10:00:00Z, 2026-01-15T11:00:00Z)`. The default
`format=lastra` is QTSurfer's compact columnar format; `format=parquet` asks the service to convert
the same segment on demand. The response is respectively `application/vnd.lastra` or
`application/vnd.apache.parquet`, and `Content-Disposition` supplies a useful filename.

```bash
curl --fail --remote-name \
  "https://api.qtsurfer.net/v1/exchange/binance/tickers/BTC/USDT?hour=2026-01-15T10&format=parquet" \
  -H "Authorization: Bearer $QTSURFER_JWT"
```

Use a kline segment when bar-level data is enough; tickers can be much larger. A malformed hour or
parameter is `400`; a valid hour with no stored segment is `404`. Download consumers should stream
the response to disk or a compatible reader instead of buffering an hour in memory.

## Related guides

- [Backtests](backtest_execute.md) use managed exchange data after preparing a requested window.
- [Datasets](datasets.md) covers caller-uploaded data — CSV or parquet — when managed exchange
  coverage is not the desired source.
