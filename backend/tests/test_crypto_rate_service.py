import os
import unittest
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core import config as cfg
from app.services.crypto_rate_service import CryptoRateService


class CryptoRateServiceTests(unittest.TestCase):
    def setUp(self):
        CryptoRateService._last_good.clear()

    def test_wallex_uses_best_ask_in_toman(self):
        with patch.object(
            CryptoRateService,
            "_http_get",
            return_value={"result": {"ask": [{"price": 164_500}, {"price": 164_600}]}},
        ):
            rate = CryptoRateService._fetch_wallex("USDT")
        self.assertEqual(rate, Decimal("164500"))

    def test_nobitex_converts_irr_to_toman(self):
        with patch.object(
            CryptoRateService,
            "_http_get",
            return_value={"status": "ok", "asks": [["1645000", "1"]]},
        ):
            rate = CryptoRateService._fetch_nobitex("USDT")
        self.assertEqual(rate, Decimal("164500"))

    def test_tabdeal_uses_best_ask_in_toman(self):
        with patch.object(
            CryptoRateService,
            "_http_get",
            return_value={"asks": [["164500", "12.5"], ["164600", "9"]]},
        ):
            rate = CryptoRateService._fetch_tabdeal("USDT")
        self.assertEqual(rate, Decimal("164500"))

    def test_fallback_provider_is_used(self):
        original_primary = cfg.CRYPTO_RATE_PROVIDER_PRIMARY
        original_fallback = cfg.CRYPTO_RATE_PROVIDER_FALLBACK
        original_third = getattr(cfg, "CRYPTO_RATE_PROVIDER_THIRD", "tabdeal")
        original_providers = list(getattr(cfg, "CRYPTO_RATE_PROVIDERS", []))
        cfg.CRYPTO_RATE_PROVIDER_PRIMARY = "nobitex"
        cfg.CRYPTO_RATE_PROVIDER_FALLBACK = "wallex"
        cfg.CRYPTO_RATE_PROVIDER_THIRD = "tabdeal"
        cfg.CRYPTO_RATE_PROVIDERS = ["nobitex", "wallex", "tabdeal"]
        try:
            with patch.object(
                CryptoRateService,
                "_fetch",
                side_effect=[RuntimeError("primary down"), DecimalQuoteFactory.wallex_usdt()],
            ):
                quote = CryptoRateService.get_live_quote("USDT")
        finally:
            cfg.CRYPTO_RATE_PROVIDER_PRIMARY = original_primary
            cfg.CRYPTO_RATE_PROVIDER_FALLBACK = original_fallback
            cfg.CRYPTO_RATE_PROVIDER_THIRD = original_third
            cfg.CRYPTO_RATE_PROVIDERS = original_providers
        self.assertEqual(quote.provider, "wallex")
        self.assertEqual(quote.rate_toman, Decimal("164500"))

    def test_ton_cross_rate_uses_binance_and_usdt_toman(self):
        responses = [
            {"asks": [["3.25", "10"]]},
            {"status": "ok", "asks": [["900000", "100"]]},
        ]
        with patch.object(CryptoRateService, "_http_get", side_effect=responses):
            quote = CryptoRateService._fetch_ton_cross(["nobitex"])
        self.assertEqual(quote.asset, "TON")
        self.assertEqual(quote.provider, "binance+nobitex")
        self.assertEqual(quote.rate_toman, Decimal("292500"))

    def test_ton_cross_rate_falls_back_to_coingecko_when_binance_is_unavailable(self):
        def fake_http_get(url, *, params=None):
            if "binance" in url or "data-api.binance" in url:
                raise RuntimeError("binance blocked")
            if "coingecko" in url:
                return {"the-open-network": {"usd": 1.65, "last_updated_at": 1779092258}}
            if "wallex" in url:
                return {"result": {"ask": [{"price": 176000}]}}
            raise RuntimeError(f"unexpected url: {url}")

        with patch.object(CryptoRateService, "_http_get", side_effect=fake_http_get):
            quote = CryptoRateService._fetch_ton_cross(["wallex"])

        self.assertEqual(quote.asset, "TON")
        self.assertEqual(quote.provider, "coingecko+wallex")
        self.assertEqual(quote.rate_toman, Decimal("290400.00"))


class DecimalQuoteFactory:
    @staticmethod
    def wallex_usdt():
        from app.services.crypto_rate_service import CryptoRateQuote
        from datetime import datetime, timezone

        return CryptoRateQuote(
            asset="USDT",
            rate_toman=Decimal("164500"),
            provider="wallex",
            fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )


if __name__ == "__main__":
    unittest.main()
