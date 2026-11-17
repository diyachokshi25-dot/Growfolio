import unittest

from ingest import chunk_pages


class IngestionTests(unittest.TestCase):
    def test_removes_split_chart_values_and_period_labels(self) -> None:
        page = {
            "source_id": "hdfc_elss",
            "title": "HDFC ELSS Tax Saver Fund Direct Plan Growth",
            "url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
            "fetched_at": "2026-11-17",
            "text": (
                "## HDFC ELSS Tax Saver Fund Direct Plan Growth\n"
                "ELSS 3Y Lock-in\n"
                "Very High Risk\n"
                "+13.88\n%\n3Y annualised\n+0.42\n%\n"
                "1D\n1M\n6M\n1Y\n3Y\n5Y\nAll\n"
                "NAV: 16 Nov 2026\n1553.50\nMin. for SIP 500\n"
                "Expense ratio\n1.00%"
            ),
        }

        chunks = chunk_pages([page])
        content = " ".join(chunk["text"] for chunk in chunks)

        self.assertIn("3Y Lock-in", content)
        self.assertIn("Min. for SIP 500", content)
        self.assertIn("Expense ratio 1.00%", content)
        self.assertNotIn("13.88", content)
        self.assertNotIn("0.42", content)
        self.assertNotIn("1D", content)
        self.assertNotIn("3Y annualised", content)

    def test_removes_chart_returns_but_preserves_elss_facts(self) -> None:
        page = {
            "source_id": "hdfc_elss",
            "title": "HDFC ELSS Tax Saver Fund Direct Plan Growth",
            "url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
            "fetched_at": "2026-11-17",
            "text": (
                "## HDFC ELSS Tax Saver Fund Direct Plan Growth\n"
                "ELSS 3Y Lock-in Equity ELSS Very High Risk +13.88 % +0.42 % "
                "1D 1M 6M 1Y 3Y 5Y All NAV: 16 Nov 2026 1553.50 "
                "Min. for SIP 500"
            ),
        }

        chunks = chunk_pages([page])
        content = " ".join(chunk["text"] for chunk in chunks)

        self.assertIn("3Y Lock-in", content)
        self.assertIn("Min. for SIP 500", content)
        self.assertNotIn("13.88", content)
        self.assertNotIn("0.42", content)
        self.assertNotIn("1D 1M", content)


if __name__ == "__main__":
    unittest.main()
