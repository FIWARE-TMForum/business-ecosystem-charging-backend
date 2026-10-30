from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from requests.exceptions import ConnectionError, HTTPError

from wstore.store_commons.product_catalog import ProductCatalog, ProductCatalogError


@override_settings(CATALOG="https://catalog.example/tmf-api/productCatalogManagement/v4/", VERIFY_REQUESTS=False)
class ProductCatalogReferenceTests(SimpleTestCase):
    @patch("wstore.store_commons.product_catalog.requests.get")
    def test_reference_download_uses_configured_url_tls_and_timeout(self, get):
        get.return_value.json.return_value = {"id": "p/1"}

        self.assertEqual("p/1", ProductCatalog().get_specification("p/1")["id"])
        get.assert_called_once_with(
            "https://catalog.example/tmf-api/productCatalogManagement/v4/productSpecification/p%2F1",
            verify=False,
            timeout=30,
        )
        get.return_value.raise_for_status.assert_called_once_with()

    @patch("wstore.store_commons.product_catalog.requests.get")
    def test_catalog_failures_and_missing_or_wrong_documents_are_rejected(self, get):
        catalog = ProductCatalog()
        for document in (None, [], {}, {"id": "wrong"}):
            with self.subTest(document=document), self.assertRaises(ProductCatalogError):
                get.return_value.json.return_value = document
                catalog.get_specification("p1")
        get.return_value.raise_for_status.side_effect = HTTPError("404")

        with self.assertRaises(ProductCatalogError):
            catalog.get_specification("p1")
        get.side_effect = ConnectionError("offline")

        with self.assertRaises(ProductCatalogError):
            catalog.get_specification("p1")


@override_settings(CATALOG="https://catalog.example/tmf-api/productCatalogManagement/v4", VERIFY_REQUESTS=True)
class OfferingPriceClientTests(SimpleTestCase):
    @patch("wstore.store_commons.product_catalog.requests.get")
    def test_offering_and_price_reads_use_the_shared_product_catalog(self, get):
        catalog = ProductCatalog()

        for method, collection in (
            (catalog.get_offering, "productOffering"),
            (catalog.get_price, "productOfferingPrice"),
        ):
            with self.subTest(collection=collection):
                get.reset_mock()
                document = {"id": "urn:example:1", "name": "Example"}
                get.return_value.json.return_value = document

                self.assertIs(document, method("urn:example:1"))

                get.assert_called_once_with(
                    "https://catalog.example/tmf-api/productCatalogManagement/v4/" + collection + "/urn%3Aexample%3A1",
                    verify=True,
                    timeout=30,
                )
                get.return_value.raise_for_status.assert_called_once_with()

    @patch("wstore.store_commons.product_catalog.requests.get")
    def test_price_http_json_and_identity_errors_are_not_accepted(self, get):
        catalog = ProductCatalog()
        get.return_value.raise_for_status.side_effect = HTTPError("404")

        with self.assertRaises(ProductCatalogError):
            catalog.get_price("price-1")

        get.return_value.raise_for_status.side_effect = None
        get.return_value.json.side_effect = ValueError("invalid JSON")

        with self.assertRaises(ProductCatalogError):
            catalog.get_price("price-1")

        get.return_value.json.side_effect = None
        get.return_value.json.return_value = {"id": "different-price"}

        with self.assertRaises(ProductCatalogError):
            catalog.get_price("price-1")
