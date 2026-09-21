from __future__ import annotations

import unittest
from types import SimpleNamespace

from amava_agent.check_un_gated import AmazonEligibilityChecker
from amava_agent.profit import AmazonProfitCalculator
from sp_api_amazon.sections.fees import ProductFeesAPI
from sp_api_amazon.sections.restrictions import ListingsRestrictionsAPI


class Response:
    def __init__(self, payload):
        self.payload = payload


class FakeCatalog:
    def __init__(self, asin="B000TEST01"):
        self.asin = asin
        self.calls = []

    def search_catalog_items(self, **kwargs):
        self.calls.append(kwargs)
        return Response({"items": [{"asin": self.asin}]})


class FakeRestrictions:
    def __init__(self, restrictions=None):
        self.value = restrictions or []
        self.calls = []

    def get_listings_restrictions(self, asin, **kwargs):
        self.calls.append((asin, kwargs))
        return Response({"restrictions": self.value})


class FakePricing:
    def get_item_offers(self, asin, **kwargs):
        return Response({
            "Summary": {
                "LowestPrices": [
                    {
                        "fulfillmentChannel": "Amazon",
                        "ListingPrice": {"Amount": 30, "CurrencyCode": "USD"},
                        "Shipping": {"Amount": 0, "CurrencyCode": "USD"},
                        "LandedPrice": {"Amount": 30, "CurrencyCode": "USD"},
                    },
                    {
                        "fulfillmentChannel": "Merchant",
                        "ListingPrice": {"Amount": 25, "CurrencyCode": "USD"},
                        "Shipping": {"Amount": 5, "CurrencyCode": "USD"},
                        "LandedPrice": {"Amount": 30, "CurrencyCode": "USD"},
                    },
                ]
            }
        })


class FakeFees:
    def __init__(self):
        self.calls = []

    def get_my_fees_estimate_for_asin(self, asin, **kwargs):
        self.calls.append((asin, kwargs))
        return Response({
            "FeesEstimateResult": {
                "FeesEstimate": {
                    "TotalFeesEstimate": {"Amount": 8},
                    "FeeDetailList": [{
                        "FeeType": "FBAFees",
                        "FinalFee": {"Amount": 3},
                        "IncludedFeeList": [{
                            "FeeType": "FBAPerUnitFulfillmentFee",
                            "FinalFee": {"Amount": 3},
                        }],
                    }],
                }
            }
        })


def fake_sp(*, restrictions=None):
    return SimpleNamespace(
        config=SimpleNamespace(
            seller_id="SELLER1",
            marketplace=SimpleNamespace(name="US", marketplace_id="ATVPDKIKX0DER"),
        ),
        catalog=FakeCatalog(),
        restrictions=FakeRestrictions(restrictions),
        pricing=FakePricing(),
        fees=FakeFees(),
    )


class EligibilityTests(unittest.TestCase):
    def test_upc_is_resolved_and_unrestricted_item_is_ungated(self):
        sp = fake_sp()
        result = AmazonEligibilityChecker(sp).check_many(["012345678905"], unit="UPC")

        item = result["results"]["012345678905"][0]
        self.assertEqual(item["productASIN"], "B000TEST01")
        self.assertEqual(item["eligibility"], "ungated")
        self.assertEqual(result["summary"]["ungated"], 1)
        self.assertEqual(sp.catalog.calls[0]["identifiers_type"], "UPC")

    def test_approval_required_is_reported_as_gated(self):
        sp = fake_sp(restrictions=[{
            "reasons": [{"reasonCode": "APPROVAL_REQUIRED", "message": "Apply to sell"}]
        }])
        item = AmazonEligibilityChecker(sp).check_one("B000TEST01", unit="ASIN")

        self.assertEqual(item["eligibility"], "gated")
        self.assertTrue(item["approval_required"])
        self.assertIn("APPROVAL_REQUIRED", item["reason_codes"])


class ProfitTests(unittest.TestCase):
    def test_fba_uses_only_amazon_fulfilled_offer(self):
        sp = fake_sp()
        result = AmazonProfitCalculator(sp).calculate("B000TEST01", 10, fulfillment="FBA")

        self.assertEqual(result["price"], 30)
        self.assertEqual(result["profit"], 12)
        self.assertEqual(result["fulfillment_fee"], 3)
        self.assertTrue(sp.fees.calls[0][1]["is_amazon_fulfilled"])

    def test_manual_fbm_accounts_for_customer_and_seller_shipping(self):
        sp = fake_sp()
        result = AmazonProfitCalculator(sp).calculate(
            "B000TEST01", 10, fulfillment="FBM", price=40,
            customer_shipping=5, shipping_cost=7,
        )

        self.assertEqual(result["price_source"], "manual")
        self.assertEqual(result["price"], 45)
        self.assertEqual(result["profit"], 20)
        self.assertFalse(sp.fees.calls[0][1]["is_amazon_fulfilled"])


class CaptureClient:
    def __init__(self):
        self.config = SimpleNamespace(
            seller_id="SELLER1",
            marketplace=SimpleNamespace(marketplace_id="ATVPDKIKX0DER"),
        )
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return Response({})


class SectionRequestTests(unittest.TestCase):
    def test_restrictions_section_builds_seller_scoped_request(self):
        client = CaptureClient()
        ListingsRestrictionsAPI(client).get_listings_restrictions("B000TEST01")

        method, path, kwargs = client.calls[0]
        self.assertEqual((method, path), ("GET", "/listings/2021-08-01/restrictions"))
        self.assertEqual(kwargs["operation"], "getListingsRestrictions")
        self.assertEqual(kwargs["params"]["sellerId"], "SELLER1")

    def test_fees_section_builds_fbm_fee_request(self):
        client = CaptureClient()
        ProductFeesAPI(client).get_my_fees_estimate_for_asin(
            "B000TEST01", price=40, shipping_price=5,
            currency_code="USD", is_amazon_fulfilled=False,
            identifier="test-id",
        )

        method, path, kwargs = client.calls[0]
        self.assertEqual((method, path), ("POST", "/products/fees/v0/items/B000TEST01/feesEstimate"))
        request = kwargs["json_body"]["FeesEstimateRequest"]
        self.assertFalse(request["IsAmazonFulfilled"])
        self.assertEqual(request["PriceToEstimateFees"]["Shipping"]["Amount"], 5)


if __name__ == "__main__":
    unittest.main()
