# tyche-client

Python client + Jupyter examples for pulling time-series data from a Tyche backend
into pandas — prices, returns, correlations, indices, VIX/PCR, and macro series
(FRED / EIA / World Bank / DataHub / StatCan).

This package is standalone: it talks to the backend's read-only `/data/v1` API over
HTTPS using an API key, so it runs anywhere (no access to the backend repo needed).

## 1. Get an API key

Log into the Tyche (zibaldon(dot)com) web app and mint a key (Settings → API keys), or via the API:

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
# or, with notebook extras (needed for the notebooks below):
pip install -e ".[notebook]"
```

## 3. Configure

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
# then edit .env:
#   TYCHE_BASE_URL = http://localhost:8000
#   TYCHE_API_KEY  = tyk_your_key_here
```

`.env` is gitignored — every notebook in this repo loads it via `python-dotenv` rather
than hardcoding a key inline, so nothing secret ends up committed.

## 4. Use

```python
import os
import pandas as pd
from dotenv import load_dotenv
from tyche_client import TycheClient

load_dotenv()
client = TycheClient(os.getenv("TYCHE_BASE_URL"), os.getenv("TYCHE_API_KEY"))

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
client.constituents("sp500", as_of="2010-01-04")  # point-in-time membership
client.constituents("russell1000", include_history=True)  # every membership period

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

## Notebook examples

This repository now keeps the client-focused examples under [`examples/`](examples/).
They demonstrate API access and analyses that are useful when learning or validating the
client:

| Notebook | What it demonstrates |
|----------|----------------------|
| [`example.ipynb`](examples/example.ipynb) | Minimal setup, authentication, prices, macro series, returns, and correlations. |
| [`global_equity_screen.ipynb`](examples/global_equity_screen.ipynb) | Country-aware universe discovery and cross-sectional momentum, volatility, and drawdown screening. |
| [`macro_regime_analysis.ipynb`](examples/macro_regime_analysis.ipynb) | FRED macro regimes and rolling relationships across equities, bonds, commodities, and volatility. |
| [`oil_energy_market_returns.ipynb`](examples/oil_energy_market_returns.ipynb) | Weekly through annual oil and energy-sector changes compared with current and subsequent returns. |
| [`portfolio_risk_analysis.ipynb`](examples/portfolio_risk_analysis.ipynb) | Portfolio performance, volatility, drawdowns, correlations, and component risk contributions. |
| [`accumulation_validation.ipynb`](examples/accumulation_validation.ipynb) | Validation of accumulation-style signals against subsequent market returns. |
| [`sp500_market_breadth.ipynb`](examples/sp500_market_breadth.ipynb) | Point-in-time S&P 500 breadth, participation, moving-average breadth, divergences, and new highs/lows. |

Longer research notebooks have moved to
[`scrying-quant/notebooks`](https://github.com/doublebigmak/scrying-quant/tree/main/notebooks).
That project installs `tyche-client` as a pinned Git dependency and runs the notebooks
through its `qsibyl` research platform. The migrated work includes data discovery,
SPY/VIX exploratory analysis, hidden-Markov market regimes, and VIX regime-signal blending.

## What you can build with the client

The API methods return pandas objects, so they can feed notebooks, scheduled research
jobs, screening tools, dashboards, or a separate backtesting system. Some practical
starting points follow.

### Point-in-time index research

Avoid survivorship bias by asking who belonged to an index on each historical date, or
retrieve complete membership intervals for your own point-in-time joins:

```python
members_then = client.constituents("sp500", as_of="2010-01-04")
membership_history = client.constituents("russell1000", include_history=True)

# Pull the prices of a historically resolved group after selecting its tickers.
tickers = members_then["ticker"].tolist()
historical_prices = client.ohlcv(tickers, start="2010-01-04", end="2010-12-31")
```

Potential uses include breadth indicators, constituent-entry studies, sector leadership,
index turnover, and point-in-time backtest universes.

### Cross-sectional screens

Build a classified universe first, then calculate signals locally from bulk prices:

```python
universe = client.universe(
    index="sp500",
    sector="Technology",
    market_cap_min=10_000_000_000,
)
prices = client.price_matrix(universe["ticker"].tolist(), start="2024-01-01")

screen = prices.pct_change(63).iloc[-1].rename("momentum_3m").sort_values(ascending=False)
leaders = screen.head(20)
```

The same pattern supports momentum and reversal screens, volatility ranking, drawdown
monitoring, regional comparisons, sector rotation, and industry peer analysis.

### Macro and market overlays

Align economic, energy, volatility, and market data on a shared pandas index:

```python
unemployment = client.series("fred", "UNRATE", start="2000-01-01")
oil = client.search("crude oil", source="eia")       # discover the desired series ID
vix = client.series("vix", "VIX", start="2000-01-01")
spy = client.prices("SPY", start="2000-01-01")["Close"]

macro_panel = pd.concat(
    {"unemployment": unemployment, "vix": vix, "spy": spy}, axis=1
)
```

This is useful for regime classification, event studies, recession dashboards,
inflation-sensitive asset comparisons, volatility conditioning, and macro signal research.

### Portfolio and risk monitoring

Use the convenience methods for a compact research pipeline:

```python
assets = ["SPY", "QQQ", "TLT", "GLD"]
returns = client.returns(assets, start="2020-01-01")
correlations = returns.corr()
rolling_spy_tlt = client.rolling_correlation(
    "ticker", "SPY", "ticker", "TLT", start_date="2020-01-01"
)

annualized_volatility = returns.std() * (252 ** 0.5)
```

From there you can add allocation weights, risk contributions, rolling drawdowns,
diversification alerts, stress windows, or report generation.

### Other useful workflows

- Explore unfamiliar datasets with `sources()`, `search()`, and `indices()` before writing
  data-specific code.
- Download tidy OHLCV batches for database ingestion, feature engineering, or model training.
- Compare current constituents across sectors, industries, exchanges, countries, and market-cap
  thresholds.
- Study lead/lag relationships with server-side rolling correlation and locally calculated
  forward returns.
- Combine VIX and put/call series with asset returns for sentiment, hedging, or tail-risk research.
- Use `index_prices()` to go directly from a classified index slice to an analysis-ready price
  panel without manually coordinating constituent and batch-price calls.

## API surface

| Method | Returns | Backend endpoint |
|--------|---------|------------------|
| `sources()` | DataFrame | `GET /data/v1/catalog/sources` |
| `search(q, source, limit)` | DataFrame | `GET /data/v1/catalog/search` |
| `indices()` | DataFrame | `GET /data/v1/indices` |
| `constituents(slug, sector, exchange, as_of, include_history)` | DataFrame | `GET /data/v1/indices/{slug}/constituents` |
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
