# tyche-client

Python client + Jupyter notebook for pulling time-series data from a Tyche backend
into pandas — prices, returns, correlations, indices, VIX/PCR, and macro series
(FRED / EIA / World Bank / DataHub / StatCan).

This package is standalone: it talks to the backend's read-only `/data/v1` API over
HTTPS using an API key, so it runs anywhere (no access to the backend repo needed).

## 1. Get an API key

Log into the Tyche web app and mint a key (Settings → API keys), or via the API:

```bash
# obtain a web session token first, then:
curl -X POST http://localhost:8000/me/api-keys/ \
  -H "Authorization: Bearer <your-web-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my notebook"}'
# → {"key": "tyk_....", ...}   ← copy this; it is shown only once
```

Keys are long-lived, read-only, and revocable. Treat the `tyk_...` value like a password.

## 2. Install

```bash
pip install -e .            # from this folder
# or, with notebook extras:
pip install -e ".[notebook]"
```

## 3. Use

```python
from tyche_client import TycheClient

client = TycheClient("http://localhost:8000", "tyk_your_key_here")

# Single ticker OHLCV
aapl = client.prices("AAPL", start="2024-01-01")
aapl.Close.plot()

# A price matrix, returns, and a correlation matrix
client.price_matrix(["SPY", "QQQ", "TLT", "GLD"], start="2023-01-01")
client.returns(["SPY", "QQQ"], start="2024-01-01")
client.correlation_matrix(["SPY", "QQQ", "TLT", "GLD"], start="2023-01-01")

# Macro / volatility series
client.series("fred", "UNRATE")        # unemployment rate
client.series("vix", "VIX")            # CBOE VIX
client.series("pcr", "PCR_TOTAL")      # total put/call ratio

# Discovery
client.sources()                       # what kinds of data are available
client.search("apple")                 # find a ticker/series
client.search("oil", source="eia")     # search within one source
client.indices()
client.constituents("sp500")
client.constituents("sp500", sector="Energy")

# Filter a classified universe (carries industry + country), then pull prices
client.universe(index="sp500", sector="Technology")
client.universe(sector="Energy", country="CA", market_cap_min=1e9)
client.universe(index="sp500", industry="Semiconductors")   # warns on unclassified

# Full OHLCV for many tickers as a long/tidy frame (chunked automatically)
client.ohlcv(["AAPL", "MSFT", "NVDA"], start="2024-01-01")

# Index constituents → OHLCV in one call, optionally sector/industry/country filtered
client.index_prices("sp500", sector="Energy", start="2024-01-01")

# Server-side rolling correlation
client.rolling_correlation("ticker", "AAPL", "ticker", "MSFT")
```

See [`example.ipynb`](example.ipynb) for a quickstart, and
[`data_discovery_and_analysis.ipynb`](data_discovery_and_analysis.ipynb) for a fuller
walkthrough of discovery / `universe` / bulk `ohlcv` / `index_prices` with a worked
sector analysis.

More analysis examples:

- [`portfolio_risk_analysis.ipynb`](portfolio_risk_analysis.ipynb) — performance,
  volatility, drawdowns, correlations, and risk contributions.
- [`macro_regime_analysis.ipynb`](macro_regime_analysis.ipynb) — FRED regimes and
  server-side rolling cross-asset relationships.
- [`global_equity_screen.ipynb`](global_equity_screen.ipynb) — country-aware
  universe discovery, momentum, volatility, and drawdown screening.

## API surface

| Method | Returns | Backend endpoint |
|--------|---------|------------------|
| `sources()` | DataFrame | `GET /data/v1/catalog/sources` |
| `search(q, source, limit)` | DataFrame | `GET /data/v1/catalog/search` |
| `indices()` | DataFrame | `GET /data/v1/indices` |
| `constituents(slug, sector, exchange)` | DataFrame | `GET /data/v1/indices/{slug}/constituents` |
| `universe(index, sector, industry, country, exchange, market_cap_min, limit)` | DataFrame | `GET /data/v1/universe` |
| `prices(ticker, start, end, interval)` | OHLCV DataFrame | `GET /data/v1/prices/{ticker}` |
| `ohlcv(tickers, start, end, interval, fields)` | long/tidy DataFrame | `POST /data/v1/prices/ohlcv/batch` |
| `index_prices(slug, sector, industry, country, start, end, interval, fields)` | long/tidy DataFrame | (composes `universe`/`constituents` + `ohlcv`) |
| `series(source, series_id, start, end)` | Series | `GET /data/v1/series` |
| `price_matrix(tickers, start, end)` | DataFrame | `POST /data/v1/prices/closes/batch` |
| `returns(tickers, start, end)` | DataFrame | (local `pct_change`) |
| `correlation_matrix(tickers, start, end)` | DataFrame | (local `corr`) |
| `rolling_correlation(...)` | DataFrame | `GET /data/v1/correlation/rolling` |

`source` is one of: `ticker`, `vix`, `pcr`, `fred`, `wbnk`, `datahub`, `eia`, `statcan`.
`country` is a 2-letter market code derived from the ticker suffix: `US`, `CA`, `JP`, `KR`, `TW`, `GB`, `DE`, `FR`, … `industry` is only on the classified `universe` (constituents carry `sector` but not `industry`); tickers with no industry classification are dropped from an industry-filtered universe with a warning.
