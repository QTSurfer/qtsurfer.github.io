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
hourly files, datasets or backtests, so its id is `400` in every route that takes an `exchangeId` except the
two instrument routes, which list its pools. Use either instrument route with the id of any exchange
`GET /exchanges` lists:

| Route | Meaning |
| --- | --- |
| `GET /exchange/{exchangeId}/instruments` | Instruments in the default `spot` segment |
| `GET /exchange/{exchangeId}/{segment}/instruments` | Instruments in an explicit segment: `spot` or `futures`, or a protocol of a `dex` exchange (`uniswap-v3`) |

An instrument response is a HAL envelope. Its `data` array contains `id`, `symbol`, `base`, `quote`, current
`lastPrice` and `volume24h`, plus independent `coverage.tickers` and `coverage.klines` windows.
`meta.updatedAt` identifies when the catalogue was assembled; `meta.segment` identifies the segment
actually served and `meta.venueType` the venue type of the exchange (`cex` here, `dex` for a listing of
pools). Treat coverage as live platform state rather than a promise that every timestamp is available
forever.

Both kinds of listing, instruments and [pools](#pools-of-a-decentralized-exchange), can be read the same way:
the fields below mean the same in each, and the rest belong to one kind only.

| Field | Meaning | In |
| --- | --- | --- |
| `meta.venueType` | `cex` or `dex`, as `GET /exchanges` lists the exchange | both |
| `id` | Identifier to use in the other routes: the pair of an instrument (`BTC/USDT`), the address of a pool | both |
| `symbol` | The name of the instrument or pair, the way the signals of a run name it. The same as `id` for an instrument | both |
| `base`, `quote` | Symbol of each side | both |
| `lastPrice` | Price of one base in the quote currency; `null` when there is none | both |
| `volume24h` | Volume over the last 24 hours, in the quote currency; `null` when there is none | both |
| `coverage` | Time range of the data held, per data type | instruments only |
| `settle` | Settlement currency of a futures instrument | futures instruments only |
| `baseAddress`, `quoteAddress`, `feePercent`, `tvlUsd`, `volume24hUsd`, `createdAt` | Token addresses, fee tier, liquidity and volume in US dollars, creation date | pools only |

`lastPrice` and `volume24h` of an instrument are refreshed every few minutes; those of a pool are as of
`meta.updatedAt`, which is refreshed every hour, so a pool's price can be up to one hour old.

```bash
curl https://api.qtsurfer.net/v1/exchange/binance/spot/instruments \
  -H "Authorization: Bearer $QTSURFER_JWT"
```

The response's `_links` provide `self`, `spot`, and `futures` discovery links. An exchange `GET /exchanges`
does not list, and a segment the exchange does not have, return `400`; a catalogue that is not available
returns `404`. The segment is written in lower-case.

### Pools of a decentralized exchange

For a `dex` exchange the instruments are its pools, and this is where to find the address to put in
`instruments` of a [live run](live.md#dex-pools):

```bash
curl https://api.qtsurfer.net/v1/exchange/robinhood/uniswap-v3/instruments \
  -H "Authorization: Bearer $QTSURFER_JWT"
```

```json
{
  "data": [
    {"id": "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca", "symbol": "WETH/USDG", "base": "WETH", "quote": "USDG",
     "baseAddress": "0x0bd7d308f8e1639fab988df18a8011f41eacad73", "quoteAddress": "0x5fc5360d0400a0fd4f2af552add042d716f1d168",
     "feePercent": 0.01, "lastPrice": 2411.285967, "volume24h": 274033077.4, "tvlUsd": 19857902.02,
     "volume24hUsd": 273876056.45, "createdAt": "2026-07-02T20:51:08Z"}
  ],
  "meta": {"updatedAt": "2026-10-14T22:32:34Z", "exchange": "robinhood", "segment": "uniswap-v3", "venueType": "dex", "minTvlUsd": 10000, "limit": 50},
  "_links": {"self": {"href": "/v1/exchange/robinhood/uniswap-v3/instruments"}, "uniswap-v3": {"href": "/v1/exchange/robinhood/uniswap-v3/instruments"}}
}
```

A pool's `id` is its address, in lower case. `symbol` is the pair as the signals of a run name it, which is
not always the order other sites show it in (the same pool can read `USDG / WETH` elsewhere), so identify a
pool by its address. A protocol can have several pools of one pair, one per fee tier (`feePercent`).

`lastPrice` is the price of one base in the quote token (`2411.285967` USDG for one WETH above) and
`volume24h` is what traded over the last 24 hours in that quote token; `volume24hUsd` is the same volume in
US dollars, and the listing is ranked by it. Both can be `null`. They are as of `meta.updatedAt`, up to one
hour old.

The listing has the 50 pools with the most volume over the last 24 hours (`volume24hUsd`) among those with at
least 10,000 US dollars of liquidity (`tvlUsd`), and is refreshed every hour (`meta.updatedAt`); `meta`
states both limits. It is a place to start, not the whole market: a live run can read any pool of the
protocol, listed or not. `404` means the listing is not available at the moment.

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
