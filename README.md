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
- [`oil_energy_market_returns.ipynb`](oil_energy_market_returns.ipynb) — weekly,
  monthly, quarterly, and annual oil/energy changes versus current and future sector returns.
- [`sp500_market_breadth.ipynb`](sp500_market_breadth.ipynb) — point-in-time-aware S&P 500
  breadth, one-month/one-year participation, moving-average breadth, divergences, and highs/lows.
- [`global_equity_screen.ipynb`](global_equity_screen.ipynb) — country-aware
  universe discovery, momentum, volatility, and drawdown screening.
- [`vix_regime_softmax_blend.ipynb`](vix_regime_softmax_blend.ipynb) — tests alternative
  and blended VIX regime signals against the backend's recency-weighted z-score (a
  softmax-weighted score, a 0-100 percentile composite index, a True Strength Index
  momentum signal at various frequencies/windows/targets — including downside deviation,
  max adverse excursion, and momentum-direction overlays gated on raw vs softmaxed TSI —
  and searched 2-way/3-way blends), validated against forward realized-vol/drawdown
  upside/downside with time-series and scatter visualizations against SPY. Ends with a
  final recommended production design (Part 13): a `vix_index` (0-100, the Part 5
  slow-TSI blend — the one construction that meaningfully beats the base signal) plus a
  nullable `direction` field gated on short-term TSI, with ready-to-port
  `compute_vix_index_series` / `compute_vix_direction_series` functions and a suggested
  `VixRegimeResponse` schema extension for `app/services/vix_regime.py`.
- [`spy_hmm_regimes.ipynb`](spy_hmm_regimes.ipynb) — a 3-state hidden Markov regime model on
  SPY (Bull / Choppy / Bear) following Yuan & Mitra, SSRN 3406068, via
  `statsmodels.MarkovRegression`. Selects the state count on persistence rather than BIC alone,
  labels states from fitted parameters, and characterises them with time series, a
  volatility-vs-return regime map, per-episode scatterplots, and multi-horizon reversal
  correlations that establish *why the middle state is "choppy" rather than "mean-reverting"*.
  Tests the VOL Regime Index as a driver of time-varying transition probabilities (it earns its
  place: ΔBIC ≈ −100), replicates across QQQ / DIA / IWM, and runs a walk-forward,
  causally-filtered out-of-sample evaluation of position sizing, volatility targeting and
  hysteresis rules. Closes on the signal-processing question — debouncing the flickering state
  path is the largest single improvement, and a Kalman filter is shown to be *algebraically the
  same estimator* as the EMA unless a slope state is added. Every hyperparameter is stress-tested
  against a walk-forward selector to price the hindsight in it. Deterministic — `RANDOM_SEED` pins
  the EM restarts.

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
