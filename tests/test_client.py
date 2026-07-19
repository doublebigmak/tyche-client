import unittest
from unittest.mock import Mock, patch

import pandas as pd

from tyche_client import TycheApiError, TycheClient


class TycheClientTest(unittest.TestCase):
    def setUp(self):
        self.client = TycheClient("https://example.test", "tyk_test")

    def tearDown(self):
        self.client._session.close()

    def test_price_matrix_cleans_and_chunks_tickers(self):
        calls = []

        def fake_post(_path, params, json):
            calls.append(json)
            return {
                ticker: {"bars": [{"date": "2026-01-02", "close": i + 1.0}]}
                for i, ticker in enumerate(json)
            }

        tickers = [f" t{i} " for i in range(51)] + ["T0", ""]
        with patch.object(self.client, "_post", side_effect=fake_post):
            result = self.client.price_matrix(tickers)

        self.assertEqual([len(chunk) for chunk in calls], [50, 1])
        self.assertEqual(list(result.columns), [f"T{i}" for i in range(51)])

    def test_industry_filter_applies_limit_after_server_results(self):
        rows = [
            {"ticker": "A", "industry": "Software"},
            {"ticker": "B", "industry": None},
            {"ticker": "C", "industry": "Software"},
        ]
        with patch.object(self.client, "_get", return_value={"rows": rows}) as get:
            with self.assertWarns(UserWarning):
                result = self.client.universe(industry="software", limit=1)

        self.assertEqual(get.call_args.args[1]["limit"], 5000)
        self.assertEqual(result["ticker"].tolist(), ["A"])

    def test_industry_filter_warns_at_the_server_ceiling(self):
        rows = [{"ticker": str(i), "industry": "Software"} for i in range(5000)]
        with patch.object(self.client, "_get", return_value={"rows": rows}):
            with self.assertWarnsRegex(UserWarning, "results may be incomplete"):
                self.client.universe(industry="Software")

    def test_transport_uses_data_api_contract_and_preserves_validation_detail(self):
        response = Mock(ok=False, status_code=422, text="validation failed")
        response.json.return_value = {"detail": [{"msg": "invalid interval"}]}

        with patch.object(self.client._session, "request", return_value=response) as request:
            with self.assertRaisesRegex(TycheApiError, "invalid interval") as raised:
                self.client.prices("AAPL", start="2026-01-01", interval="bad")

        request.assert_called_once_with(
            "GET",
            "https://example.test/data/v1/prices/AAPL",
            params={"start": "2026-01-01", "interval": "bad"},
            json=None,
            timeout=30.0,
        )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail, [{"msg": "invalid interval"}])
        self.assertEqual(self.client._session.headers["Authorization"], "Bearer tyk_test")

    def test_ohlcv_batches_and_filters_the_returned_frame(self):
        calls = []

        def fake_post(_path, params, json):
            calls.append(json)
            return {
                ticker: {
                    "bars": [
                        {
                            "date": "2026-01-02",
                            "open": 1,
                            "high": 2,
                            "low": 0.5,
                            "close": 1.5,
                            "volume": 100,
                        }
                    ]
                }
                for ticker in json
            }

        with patch.object(self.client, "_post", side_effect=fake_post):
            result = self.client.ohlcv(
                [f" t{i} " for i in range(51)] + ["T0", ""], fields=["Close"]
            )

        self.assertEqual([len(chunk) for chunk in calls], [50, 1])
        self.assertEqual(result.columns.tolist(), ["ticker", "date", "Close"])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["date"]))

    def test_index_prices_uses_the_classified_universe_for_industry(self):
        members = pd.DataFrame({"ticker": ["A", "B"]})
        expected = pd.DataFrame({"ticker": ["A", "B"]})

        with patch.object(self.client, "universe", return_value=members) as universe:
            with patch.object(self.client, "ohlcv", return_value=expected) as ohlcv:
                result = self.client.index_prices("sp500", industry="Software")

        universe.assert_called_once_with(
            index="sp500", sector=None, industry="Software", country=None
        )
        ohlcv.assert_called_once_with(
            ["A", "B"], start=None, end=None, interval="1d", fields=None
        )
        self.assertIs(result, expected)


if __name__ == "__main__":
    unittest.main()
