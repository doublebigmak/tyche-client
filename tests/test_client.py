import unittest
from unittest.mock import patch

from tyche_client import TycheClient


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


if __name__ == "__main__":
    unittest.main()
