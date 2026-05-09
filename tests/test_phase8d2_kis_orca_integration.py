import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class Phase8d2KisOrcaIntegrationTests(unittest.TestCase):
    def _data_module(self):
        from orca import data

        return data

    @patch("shared.broker.kis.KisClient")
    def test_kis_no_env(self, mock_class):
        """Unconfigured KIS client returns None."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = False
        mock_class.return_value = mock_client

        result = self._data_module()._fetch_kis_investor_flow()

        self.assertIsNone(result)
        mock_client.get_investor_flow.assert_not_called()

    @patch("shared.broker.kis.KisClient")
    def test_kis_success(self, mock_class):
        """KIS success returns the fetch_krx_flow contract shape."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_investor_flow.return_value = {
            "ticker": "005930",
            "foreign_net": -50000,
            "institution_net": 30000,
            "individual_net": 20000,
            "date": "20260509",
            "source": "kis",
        }
        mock_class.return_value = mock_client

        result = self._data_module()._fetch_kis_investor_flow()

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "kis")
        self.assertEqual(result["foreign_net"], "-50000")
        self.assertEqual(result["institution_net"], "30000")
        self.assertEqual(result["individual_net"], "20000")
        self.assertEqual(result["date"], "20260509")
        self.assertEqual(result["foreign_buy"], "N/A")
        self.assertEqual(result["foreign_sell"], "N/A")

    @patch("shared.broker.kis.KisClient")
    def test_kis_exception(self, mock_class):
        """KIS exceptions return None so the fallback chain can continue."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_investor_flow.side_effect = Exception("API down")
        mock_class.return_value = mock_client

        result = self._data_module()._fetch_kis_investor_flow()

        self.assertIsNone(result)

    @patch("shared.broker.kis.KisClient")
    def test_kis_empty_response(self, mock_class):
        """Empty KIS responses return None."""
        mock_client = MagicMock()
        mock_client.is_configured.return_value = True
        mock_client.get_investor_flow.return_value = None
        mock_class.return_value = mock_client

        result = self._data_module()._fetch_kis_investor_flow()

        self.assertIsNone(result)

    def test_fetch_krx_flow_kis_first(self):
        """fetch_krx_flow returns KIS data first when available."""
        data = self._data_module()
        kis_result = {
            "foreign_net": "-50000",
            "institution_net": "30000",
            "individual_net": "20000",
            "foreign_buy": "N/A",
            "foreign_sell": "N/A",
            "source": "kis",
            "date": "20260509",
            "krx_kospi_close": "N/A",
            "krx_kospi_change": "N/A",
        }

        with patch.object(data, "_fetch_kis_investor_flow", return_value=kis_result) as mock_kis:
            result = data.fetch_krx_flow()

        self.assertEqual(result["source"], "kis")
        self.assertEqual(result["foreign_net"], "-50000")
        mock_kis.assert_called_once()

    def test_fetch_krx_flow_kis_skip_to_krx(self):
        """KIS miss falls back to the existing KRX flow."""
        data = self._data_module()

        with patch.object(data, "_fetch_kis_investor_flow", return_value=None) as mock_kis:
            with patch.dict(os.environ, {}, clear=True):
                result = data.fetch_krx_flow()

        mock_kis.assert_called_once()
        self.assertEqual(result["source"], "none")

    def test_no_env_no_kis_call(self):
        """Missing env keeps KIS as a no-op."""
        with patch.dict(os.environ, {}, clear=True):
            result = self._data_module()._fetch_kis_investor_flow()

        self.assertIsNone(result)


class Phase8d2AgentsSourceBranchTests(unittest.TestCase):
    def test_kis_source_in_no_penalty_set(self):
        """source='kis' is the only investor-flow real-data source."""
        sources_no_penalty = ("kis",)

        self.assertIn("kis", sources_no_penalty)
        self.assertNotIn("krx_api", sources_no_penalty)
        self.assertNotIn("none", sources_no_penalty)
        self.assertNotIn("ewy", sources_no_penalty)

    def test_agents_source_branch_contains_kis(self):
        """agents.py excludes kis source from flow-data penalties."""
        source = Path("modules/orca/pipeline/agents.py").read_text(encoding="utf-8")

        self.assertIn('md.get("krx_flow_source") == "kis"', source)
        self.assertNotIn("krx_api", source)
