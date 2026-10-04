"""Thin client for the Tyche Data API (/data/v1).

Returns date-indexed pandas objects ready for analysis and plotting.
"""
from __future__ import annotations

import warnings
from typing import Optional, Sequence

import pandas as pd
import requests

__all__ = ["TycheClient", "TycheApiError"]

MAX_BATCH_TICKERS = 50
MAX_UNIVERSE_ROWS = 5000


def _ticker_batches(tickers: Sequence[str]):
    clean = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))
    for start in range(0, len(clean), MAX_BATCH_TICKERS):
        yield clean[start : start + MAX_BATCH_TICKERS]


class TycheApiError(RuntimeError):
    """Raised when the Data API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: object):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class TycheClient:
    """Pull time-series data from a Tyche backend with an API key.

    Mint a key in the web app under Settings → API keys (or POST /me/api-keys/),
    then::

        client = TycheClient("http://localhost:8000", "tyk_...")
        client.prices("AAPL", start="2024-01-01").Close.plot()
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        if not api_key:
            raise ValueError("api_key is required")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    # ── transport ──────────────────────────────────────────────────────────
    def _get(self, path: str, params: Optional[dict] = None):
        return self._request("GET", path, params=params)

    def _post(self, path: str, params: Optional[dict] = None, json=None):
        return self._request("POST", path, params=params, json=json)

    def _request(self, method: str, path: str, params=None, json=None):
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        resp = self._session.request(
            method, f"{self.base_url}/data/v1{path}", params=clean, json=json, timeout=self.timeout
        )
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise TycheApiError(resp.status_code, detail)
        return resp.json()

    # ── discovery ──────────────────────────────────────────────────────────
    def sources(self) -> pd.DataFrame:
        """List the kinds of data available to retrieve and how to query each."""
        return pd.DataFrame(self._get("/catalog/sources").get("sources", []))

    def search(self, q: str, source: Optional[str] = None, limit: int = 10) -> pd.DataFrame:
        """Search the catalog for tickers and series, optionally within one source."""
        data = self._get("/catalog/search", {"q": q, "source": source, "limit": limit})
        return pd.DataFrame(data.get("results", []))

    def indices(self) -> pd.DataFrame:
        """List tracked official indexes (S&P 500, Nasdaq 100, ...)."""
        return pd.DataFrame(self._get("/indices"))

    def constituents(
        self,
        slug: str,
        sector: Optional[str] = None,
        exchange: Optional[str] = None,
        as_of: Optional[str] = None,
        include_history: bool = False,
    ) -> pd.DataFrame:
        """Current, point-in-time, or all historical index constituents.

        Use ``as_of="YYYY-MM-DD"`` for a point-in-time S&P 500 or Russell 1000
        membership snapshot. Use ``include_history=True`` to return all recorded
        membership periods (including ``start_date`` and ``end_date``).
        """
        if as_of and include_history:
            raise ValueError("as_of and include_history cannot be combined")
        params = {
            "sector": sector,
            "exchange": exchange,
            "as_of": as_of,
            "include_history": include_history or None,
        }
        return pd.DataFrame(self._get(f"/indices/{slug}/constituents", params))

    def universe(
        self,
        index: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        exchange: Optional[str] = None,
        market_cap_min: Optional[float] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Classified ticker universe (ticker, name, sector, industry, exchange, country, market_cap).

        Filter by ``index`` slug, ``sector``, ``industry``, ``country`` (US/CA/JP/KR/TW/...),
        ``exchange``, and ``market_cap_min``. Tickers with no ``industry`` classification are
        excluded from an industry-filtered result (a warning reports how many were dropped).
        """
        data = self._get(
            "/universe",
            {
                "index": index,
                "sector": sector,
                "exchange": exchange,
                "country": country,
                "market_cap_min": market_cap_min,
                # ponytail: /universe has no pagination; move industry filtering
                # server-side when classified coverage can exceed this endpoint cap.
                "limit": MAX_UNIVERSE_ROWS if industry else limit,
            },
        )
        df = pd.DataFrame(data.get("rows", []))
        if industry and not df.empty:
            if len(df) >= MAX_UNIVERSE_ROWS:
                warnings.warn(
                    "Industry filtering reached the API's 5,000-row cap; results may be incomplete",
                    stacklevel=2,
                )
            has_industry = df["industry"].notna() & (df["industry"].astype(str).str.strip() != "")
            missing = int((~has_industry).sum())
            if missing:
                warnings.warn(
                    f"{missing} of {len(df)} tickers excluded: no industry classification",
                    stacklevel=2,
                )
            df = df[has_industry & (df["industry"].str.lower() == industry.strip().lower())]
            df = df.head(limit).reset_index(drop=True)
        return df

    # ── series ─────────────────────────────────────────────────────────────
    def prices(
        self,
        ticker: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """OHLCV history for one ticker, date-indexed with title-cased columns."""
        data = self._get(
            f"/prices/{ticker}", {"start": start, "end": end, "interval": interval}
        )
        df = pd.DataFrame(data["bars"])
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )
        return df

    def series(
        self,
        source: str,
        series_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.Series:
        """A single-value series from any source (ticker, vix, pcr, fred, eia, wbnk, datahub, statcan)."""
        data = self._get(
            "/series", {"source": source, "id": series_id, "start": start, "end": end}
        )
        points = data["points"]
        if not points:
            return pd.Series(dtype="float64", name=data["id"])
        df = pd.DataFrame(points)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["value"].rename(data["id"])

    def price_matrix(
        self,
        tickers: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Aligned close-price matrix (one column per ticker)."""
        cols = {}
        for chunk in _ticker_batches(tickers):
            data = self._post(
                "/prices/closes/batch",
                params={"start": start, "end": end},
                json=chunk,
            )
            for ticker, payload in data.items():
                bars = payload.get("bars", [])
                if not bars:
                    continue
                s = pd.DataFrame(bars)
                s["date"] = pd.to_datetime(s["date"])
                cols[ticker] = s.set_index("date")["close"]
        if not cols:
            return pd.DataFrame()
        return pd.DataFrame(cols).sort_index()

    def ohlcv(
        self,
        tickers: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "1d",
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """Full OHLCV for many tickers as a long/tidy frame.

        Columns: ``ticker``, ``date``, ``Open``, ``High``, ``Low``, ``Close``,
        ``Adjusted Close``, ``Volume``
        (one row per ticker per day). ``fields`` optionally subsets the price columns,
        e.g. ``fields=["Close", "Volume"]``. Requests are chunked under the API's
        per-call ticker cap, so a whole index can be passed at once.
        """
        rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "adjusted_close": "Adjusted Close", "volume": "Volume"}
        frames = []
        for chunk in _ticker_batches(tickers):
            data = self._post(
                "/prices/ohlcv/batch",
                params={"start": start, "end": end, "interval": interval},
                json=chunk,
            )
            for ticker, payload in data.items():
                bars = payload.get("bars", [])
                if not bars:
                    continue
                df = pd.DataFrame(bars).rename(columns=rename)
                df.insert(0, "ticker", ticker)
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        out["date"] = pd.to_datetime(out["date"])
        cols = ["ticker", "date"] + (list(fields) if fields else ["Open", "High", "Low", "Close", "Adjusted Close", "Volume"])
        out = out[[c for c in cols if c in out.columns]]
        return out.sort_values(["ticker", "date"]).reset_index(drop=True)

    def index_prices(
        self,
        slug: str,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        interval: str = "1d",
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """OHLCV for an index's constituents, optionally filtered by sector/industry/country.

        Returns the same long/tidy frame as :meth:`ohlcv`. When ``industry`` or ``country``
        is given the constituents are resolved through :meth:`universe` (so industry-less
        tickers are dropped with a warning); otherwise the official constituent list is used.
        """
        if industry or country:
            members = self.universe(index=slug, sector=sector, industry=industry, country=country)
        else:
            members = self.constituents(slug, sector=sector)
        if members.empty or "ticker" not in members:
            return pd.DataFrame()
        return self.ohlcv(
            members["ticker"].tolist(), start=start, end=end, interval=interval, fields=fields
        )

    # ── derived analytics (computed locally) ──────────────────────────────
    def returns(
        self,
        tickers: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Daily simple returns derived from the close-price matrix."""
        return self.price_matrix(tickers, start, end).pct_change().dropna(how="all")

    def correlation_matrix(
        self,
        tickers: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Pairwise return correlation matrix."""
        return self.returns(tickers, start, end).corr()

    def rolling_correlation(
        self,
        x_source: str,
        x_series: str,
        y_source: str,
        y_series: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        frequency: str = "1d",
        x_lag: int = 0,
        y_lag: int = 0,
    ) -> pd.DataFrame:
        """Server-computed 1-year rolling Pearson correlation between two series."""
        data = self._get(
            "/correlation/rolling",
            {
                "x_source": x_source,
                "x_series": x_series,
                "y_source": y_source,
                "y_series": y_series,
                "start_date": start_date,
                "end_date": end_date,
                "frequency": frequency,
                "x_lag": x_lag,
                "y_lag": y_lag,
            },
        )
        df = pd.DataFrame(data["points"])
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")
