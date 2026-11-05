from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from requests.exceptions import ConnectionError, HTTPError

from wstore.ordering.inventory_client import InventoryClient
from wstore.store_commons.service_catalog import ServiceCatalog, ServiceCatalogError
from wstore.store_commons.resource_catalog import ResourceCatalog, ResourceCatalogError


@override_settings(SERVICE_CATALOG="https://catalog.example/tmf-api/serviceCatalogManagement/v4", VERIFY_REQUESTS=True)
class ServiceCatalogTests(SimpleTestCase):
    @patch("wstore.store_commons.service_catalog.requests.request")
    def test_category_payload_and_configured_url(self, request):
        request.return_value.json.return_value = {"id": "category-1"}
        self.assertEqual("category-1", ServiceCatalog().create_category("test", "1.0"))
        request.assert_called_once_with(
            "POST",
            "https://catalog.example/tmf-api/serviceCatalogManagement/v4/serviceCategory",
            verify=True,
            timeout=30,
            json={"name": "test", "version": "1.0"},
        )
        request.return_value.raise_for_status.assert_called_once_with()

    @patch("wstore.store_commons.service_catalog.requests.request")
    def test_category_http_failure_propagates(self, request):
        request.return_value.raise_for_status.side_effect = HTTPError("offline")
        with self.assertRaises(HTTPError):
            ServiceCatalog().delete_category("category-1")

    @patch("wstore.store_commons.service_catalog.requests.request")
    def test_invalid_category_response_raises_catalog_error(self, request):
        for body in [None, [], {}, {"name": "test"}]:
            with self.subTest(body=body):
                request.return_value.json.return_value = body
                with self.assertRaises(ServiceCatalogError):
                    ServiceCatalog().create_category("test", "1.0")

    @patch("wstore.store_commons.service_catalog.requests.get")
    def test_specification_read_preserves_inventory_response_contract(self, get):
        for document in [{"name": "service without id"}, {"error": "not found"}, []]:
            with self.subTest(document=document):
                get.return_value.json.return_value = document
                self.assertIs(document, ServiceCatalog().get_specification("spec-1"))

        get.assert_called_with(
            "https://catalog.example/tmf-api/serviceCatalogManagement/v4/serviceSpecification/spec-1",
            verify=True,
        )
        get.return_value.raise_for_status.assert_not_called()

    @override_settings(SERVICE_CATALOG="https://catalog.example/custom/", VERIFY_REQUESTS=False)
    @patch("wstore.store_commons.service_catalog.requests.get")
    def test_specification_read_preserves_url_and_tls_configuration(self, get):
        ServiceCatalog().get_specification("urn:service:123")

        get.assert_called_once_with("https://catalog.example/custom/serviceSpecification/urn:service:123", verify=False)

    @patch("wstore.store_commons.service_catalog.requests.get")
    def test_specification_read_propagates_existing_transport_and_json_errors(self, get):
        get.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            ServiceCatalog().get_specification("spec-1")

        get.side_effect = None
        get.return_value.json.side_effect = ValueError("invalid JSON")
        with self.assertRaises(ValueError):
            ServiceCatalog().get_specification("spec-1")


@override_settings(
    SERVICE_CATALOG="https://catalog.example/services",
    RESOURCE_CATALOG="https://catalog.example/resources",
    SERVICE_INVENTORY="https://inventory.example/services",
    VERIFY_REQUESTS=True,
)
class InventorySpecificationTests(SimpleTestCase):
    @patch("wstore.ordering.inventory_client.requests.get")
    def test_specification_download_remains_generic(self, get):
        document = {"name": "specification"}
        get.return_value.json.return_value = document

        for catalog, path, url in [
            (
                "service_catalog",
                "/serviceSpecification",
                "https://catalog.example/services/serviceSpecification/spec-1",
            ),
            (
                "resource_catalog",
                "/resourceSpecification",
                "https://catalog.example/resources/resourceSpecification/spec-1",
            ),
            ("service_catalog", "/customSpecification", "https://catalog.example/services/customSpecification/spec-1"),
        ]:
            with self.subTest(catalog=catalog, path=path):
                result = InventoryClient().download_spec(catalog, path, "spec-1")

                self.assertIs(document, result)
                get.assert_called_with(url, verify=True)

        get.return_value.raise_for_status.assert_not_called()

    @patch("wstore.ordering.inventory_client.uuid4", return_value="characteristic-1")
    @patch("wstore.ordering.inventory_client.datetime")
    @patch("wstore.ordering.inventory_client.normalize_party_ref", side_effect=deepcopy)
    @patch("wstore.ordering.inventory_client.requests.post")
    @patch("wstore.ordering.inventory_client.requests.get")
    def test_service_creation_preserves_inventory_payload(self, get, post, normalize, clock, uuid):
        specification = {
            "name": "service",
            "description": "existing service",
            "specCharacteristic": [
                {
                    "name": "Region",
                    "characteristicValueSpecification": [{"isDefault": True, "value": "EU"}],
                }
            ],
        }
        original = deepcopy(specification)
        get.return_value.json.return_value = specification
        post.return_value.json.return_value = {"id": "inventory-service-1"}
        clock.now.return_value = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        parties = [{"id": "seller-1", "role": "Seller"}]

        result = InventoryClient().create_service("spec-1", parties)

        self.assertEqual("inventory-service-1", result)
        self.assertEqual(original, specification)
        get.assert_called_once_with("https://catalog.example/services/serviceSpecification/spec-1", verify=True)
        post.assert_called_once_with(
            "https://inventory.example/services/service",
            json={
                "name": "service",
                "serviceSpecification": {"id": "spec-1", "href": "spec-1", "name": "service"},
                "description": "existing service",
                "serviceCharacteristic": [
                    {
                        "id": "urn:ngsi-ld:characteristic:characteristic-1",
                        "name": "Region",
                        "valueType": "string",
                        "value": "EU",
                    }
                ],
                "relatedParty": parties,
                "state": "reserved",
                "startDate": "2026-10-29T12:00:00Z",
            },
            verify=True,
        )
        post.return_value.raise_for_status.assert_called_once_with()


@override_settings(
    RESOURCE_CATALOG="https://resources.example/tmf-api/resourceCatalog/v4/", VERIFY_REQUESTS=True
)
class ResourceCatalogTests(SimpleTestCase):
    @patch("wstore.store_commons.resource_catalog.requests.request")
    def test_resource_category_operations_use_resource_catalog(self, request):
        client = ResourceCatalog()
        request.return_value.json.return_value = {"id": "category-1"}
        self.assertEqual("category-1", client.create_category("test", "1.0"))
        self.assertEqual(
            ("POST", "https://resources.example/tmf-api/resourceCatalog/v4/resourceCategory"),
            request.call_args.args,
        )
        self.assertEqual({"name": "test", "version": "1.0"}, request.call_args.kwargs["json"])
        client.update_category("category:1", "test", "2.0")
        self.assertEqual(
            ("PATCH", "https://resources.example/tmf-api/resourceCatalog/v4/resourceCategory/category%3A1"),
            request.call_args.args,
        )
        client.delete_category("category-1")
        self.assertEqual(
            ("DELETE", "https://resources.example/tmf-api/resourceCatalog/v4/resourceCategory/category-1"),
            request.call_args.args,
        )
        for invocation in request.call_args_list:
            self.assertEqual(30, invocation.kwargs["timeout"])
            self.assertIs(True, invocation.kwargs["verify"])

    @patch("wstore.store_commons.resource_catalog.requests.request")
    def test_invalid_resource_responses_raise_resource_catalog_errors(self, request):
        for document in (None, [], {}, {"name": "missing id"}):
            request.return_value.json.return_value = document
            with self.assertRaises(ResourceCatalogError):
                ResourceCatalog().create_category("test", "1.0")
        request.return_value.raise_for_status.side_effect = HTTPError("offline")
        with self.assertRaises(HTTPError):
            ResourceCatalog().delete_category("category-1")
