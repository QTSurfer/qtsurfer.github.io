# Market data

All market-data routes require a bearer JWT obtained from [authentication](../README.md#api-quick-start).
They expose the exchange catalogue and historical data that QTSurfer manages; they do not submit a
backtest or create server-side state.

## Discover exchanges and instruments

`GET /exchanges` lists the exchange ids currently available. Use an id with either instrument route:

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

The response's `_links` provide `self`, `spot`, and `futures` discovery links. A missing exchange,
unknown segment, or unavailable catalogue returns `404`.

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
- [Datasets](datasets.md) covers caller-uploaded CSV data when managed exchange coverage is not the
  desired source.
