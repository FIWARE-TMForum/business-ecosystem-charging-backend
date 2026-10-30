# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve
from requests.exceptions import ConnectionError, HTTPError

from wstore.asset_manager.errors import ProductError, ServiceError
from wstore.asset_manager.product_validator import ProductValidator
from wstore.asset_manager.resource_plugins.resolver import CatalogResolver
from wstore.asset_manager.resource_plugins.plugin import Plugin
from wstore.asset_manager.resource_plugins.plugin_error import PluginError


def service_spec(specification_id, category=None):
    specification = {"id": specification_id, "specCharacteristic": []}
    if category:
        specification["specCharacteristic"].append(
            {
                "name": "Service Type",
                "characteristicValueSpecification": [{"value": {"id": category}}],
            }
        )
    return specification


def product_spec(specification_id="product-1", services=()):
    return {
        "id": specification_id,
        "name": "Example product",
        "version": "1.0",
        "isBundle": False,
        "serviceSpecification": [{"id": service} for service in services],
    }


class ValidatorTestCase(SimpleTestCase):
    tags = ("product-validator",)

    def setUp(self):
        self.provider = object()
        self.validator = ProductValidator()
        self.resolver = CatalogResolver()
        self.services = {
            "service-1": service_spec("service-1", "category-1"),
            "service-2": service_spec("service-2", "category-2"),
            "ordinary": service_spec("ordinary"),
        }
        for name, patcher in (
            ("catalog", patch.object(self.resolver, "_service_catalog")),
            ("product_catalog", patch.object(self.resolver, "_catalog")),
            (
                "resolve",
                patch("wstore.asset_manager.resource_plugins.decorators.CatalogResolver", return_value=self.resolver),
            ),
            ("lookup", patch("wstore.asset_manager.resource_plugins.decorators._get_plugin_model")),
            ("load", patch("wstore.asset_manager.resource_plugins.decorators._load_plugin_model")),
        ):
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.catalog.get_specification.side_effect = self.services.get
        self.plugins = {"category-1": Mock(spec=Plugin), "category-2": Mock(spec=Plugin)}
        self.lookup.side_effect = lambda category_id: category_id if category_id in self.plugins else None
        self.load.side_effect = self.plugins.get
        self.product = product_spec(services=("service-1", "ordinary", "service-2"))

    def test_multiple_plugins_receive_their_own_services_and_product(self):
        events = Mock()
        for category, plugin in self.plugins.items():
            events.attach_mock(plugin, category)

        self.validator.validate("create", self.provider, self.product)

        self.assertEqual(
            [
                call.__getattr__("category-1").on_product_spec_validation(
                    self.provider, self.services["service-1"], self.product
                ),
                call.__getattr__("category-2").on_product_spec_validation(
                    self.provider, self.services["service-2"], self.product
                ),
            ],
            events.mock_calls,
        )

        for plugin in self.plugins.values():
            plugin.on_pre_service_spec_validation.assert_not_called()
            plugin.on_post_service_spec_validation.assert_not_called()
        self.catalog.get_specification.assert_has_calls([call("service-1"), call("ordinary"), call("service-2")])

    def test_two_services_using_same_plugin_receive_separate_calls(self):
        self.services["service-2"] = service_spec("service-2", "category-1")

        self.validator.validate("create", self.provider, self.product)
        self.assertEqual(
            [
                call(self.provider, self.services["service-1"], self.product),
                call(self.provider, self.services["service-2"], self.product),
            ],
            self.plugins["category-1"].on_product_spec_validation.call_args_list,
        )

        self.plugins["category-2"].on_product_spec_validation.assert_not_called()

    def test_ordinary_and_non_plugin_categories_do_not_invoke_plugins(self):
        self.services["ordinary"] = service_spec("ordinary", "external-category")

        self.validator.validate("create", self.provider, product_spec(services=("ordinary",)))

        self.catalog.get_specification.assert_called_once_with("ordinary")
        self.load.assert_not_called()

    def test_product_without_services_needs_no_asset_or_catalog_lookup(self):
        self.validator.validate("create", self.provider, product_spec())
        self.catalog.get_specification.assert_not_called()
        self.lookup.assert_not_called()

    def test_product_characteristics_are_not_parsed_as_asset_metadata(self):
        self.product["productSpecCharacteristic"] = [{"name": "Media Type", "productSpecCharacteristicValue": []}]

        self.validator.validate("create", self.provider, self.product)

    def test_plugin_failure_is_reported_without_catalog_writes(self):
        self.plugins["category-1"].on_product_spec_validation.side_effect = PluginError("reject")

        with self.assertRaises(PluginError):
            self.validator.validate("create", self.provider, self.product)
        self.plugins["category-2"].on_product_spec_validation.assert_not_called()

        self.assertEqual(
            [
                call.get_specification("service-1"),
                call.get_specification("ordinary"),
                call.get_specification("service-2"),
            ],
            self.catalog.mock_calls,
        )

    def test_invalid_service_references_fail_before_any_hook(self):
        for response in (None, [], {}, {"id": "wrong"}, {"error": "not found"}):
            with self.subTest(response=response):
                self.catalog.get_specification.side_effect = [self.services["service-1"], response]
                with self.assertRaises(ProductError):
                    self.validator.validate("create", self.provider, product_spec(services=("service-1", "missing")))
        self.load.assert_not_called()

    def test_service_catalog_failures_are_validation_errors(self):
        for error in (ConnectionError("offline"), HTTPError("404"), ValueError("invalid JSON")):
            with self.subTest(error=error):
                self.catalog.get_specification.side_effect = error
                with self.assertRaises(ProductError):
                    self.validator.validate("create", self.provider, self.product)
        self.load.assert_not_called()

    def test_malformed_service_type_is_rejected(self):
        self.services["service-1"]["specCharacteristic"][0]["characteristicValueSpecification"] = []

        with self.assertRaises(ServiceError):
            self.validator.validate("create", self.provider, self.product)

    def test_invalid_product_shapes_and_references(self):
        invalid = [
            None,
            [],
            {"isBundle": "false"},
            {"serviceSpecification": {}},
            {"serviceSpecification": [None]},
            {"serviceSpecification": [{"id": " "}]},
            {"serviceSpecification": [{"id": "service-1"}, {"id": "service-1"}]},
            {"isBundle": False, "bundledProductSpecification": [{"id": "p"}]},
        ]
        for specification in invalid:
            with self.subTest(specification=specification), self.assertRaises(ProductError):
                self.validator.validate("create", self.provider, specification)

    def test_product_characteristics_are_forwarded_without_terms_validation(self):
        self.product["productSpecCharacteristic"] = [{"name": "License"}, {"name": "license"}]
        original = deepcopy(self.product)

        self.validator.validate("create", self.provider, self.product)

        self.assertEqual(original, self.product)
        self.plugins["category-1"].on_product_spec_validation.assert_called_once_with(
            self.provider, self.services["service-1"], original
        )

    def test_parent_interface_keyword_arguments_work_for_creation_and_update(self):
        self.validator.validate_creation(provider=self.provider, catalog_element=self.product)
        self.plugins["category-1"].on_product_spec_validation.assert_called_once_with(
            self.provider, self.services["service-1"], self.product
        )
        self.plugins["category-1"].reset_mock()

        self.validator.validate_update(provider=self.provider, catalog_element=self.product)

        self.plugins["category-1"].on_product_spec_validation.assert_called_once_with(
            self.provider, self.services["service-1"], self.product
        )

    def test_update_uses_supplied_product_without_fetching_previous_version(self):
        proposed = product_spec(services=("service-2",))
        original = deepcopy(proposed)

        with patch.object(self.product_catalog, "get_specification") as get_product:
            self.validator.validate("update", self.provider, proposed)

        get_product.assert_not_called()
        self.catalog.get_specification.assert_called_once_with("service-2")
        self.plugins["category-1"].on_product_spec_validation.assert_not_called()
        self.plugins["category-2"].on_product_spec_validation.assert_called_once_with(
            self.provider, self.services["service-2"], proposed
        )
        self.assertIs(proposed, self.plugins["category-2"].on_product_spec_validation.call_args.args[2])
        self.assertEqual(original, proposed)

    def test_dispatch_and_unimplemented_operations_are_inherited(self):
        from wstore.asset_manager.catalog_validator import CatalogValidator

        self.assertIs(ProductValidator.validate, CatalogValidator.validate)
        for action in ("upgrade", "delete"):
            with self.subTest(action=action):
                self.validator.validate(action, self.provider, self.product)
        self.catalog.get_specification.assert_not_called()
        self.load.assert_not_called()
        for action in ("attach", "attach_upgrade", "rollback_create", "rollback_upgrade", "invalid"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.validator.validate(action, self.provider, self.product)


class ProductBundleTests(SimpleTestCase):
    def setUp(self):
        ValidatorTestCase.setUp(self)
        self.bundle = {"isBundle": True, "bundledProductSpecification": [{"id": "p1"}, {"id": "p2"}]}
        self.products = {
            "p1": product_spec("p1", ("service-1", "ordinary")),
            "p2": product_spec("p2", ("service-1", "service-2")),
        }
        patcher = patch.object(self.product_catalog, "get_specification", side_effect=self.products.get)
        self.get_product = patcher.start()
        self.addCleanup(patcher.stop)

    def test_bundle_services_receive_their_directly_containing_product(self):
        self.validator.validate("create", self.provider, self.bundle)
        self.plugins["category-1"].on_product_spec_validation.assert_has_calls(
            [
                call(self.provider, self.services["service-1"], self.products["p1"]),
                call(self.provider, self.services["service-1"], self.products["p2"]),
            ]
        )

        self.assertEqual(2, self.plugins["category-1"].on_product_spec_validation.call_count)
        self.plugins["category-2"].on_product_spec_validation.assert_called_once_with(
            self.provider, self.services["service-2"], self.products["p2"]
        )

    def test_nested_bundle_rejected_before_hooks_or_service_downloads(self):
        self.products["p2"] = {
            "id": "p2",
            "isBundle": True,
            "bundledProductSpecification": [{"id": "p3"}, {"id": "p4"}],
        }

        with self.assertRaisesRegex(ProductError, "other bundles"):
            self.validator.validate("create", self.provider, self.bundle)
        self.catalog.get_specification.assert_not_called()
        self.load.assert_not_called()

        self.assertEqual([call("p1"), call("p2")], self.get_product.call_args_list)

    def test_bundle_structure_restrictions(self):
        for refs in ([], [{"id": "p1"}], [{"id": "p1"}, {"id": "p1"}]):
            with self.subTest(refs=refs), self.assertRaises(ProductError):
                self.validator.validate(
                    "create", self.provider, {"isBundle": True, "bundledProductSpecification": refs}
                )
        self.bundle["serviceSpecification"] = [{"id": "service-1"}]

        with self.assertRaisesRegex(ProductError, "own services"):
            self.validator.validate("create", self.provider, self.bundle)

    def test_bundle_update_resolves_supplied_children_without_loading_previous_bundle(self):
        self.products["p3"] = product_spec("p3", ("service-2",))
        proposed = {
            "id": "bundle",
            "isBundle": True,
            "bundledProductSpecification": [{"id": "p1"}, {"id": "p3"}],
        }

        self.validator.validate("update", self.provider, proposed)

        self.assertEqual([call("p1"), call("p3")], self.get_product.call_args_list)
        self.plugins["category-2"].on_product_spec_validation.assert_called_once_with(
            self.provider, self.services["service-2"], self.products["p3"]
        )


class ProductEndpointTests(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(current_organization=object(), get_current_roles=lambda: ["provider"]),
        )
        self.factory = RequestFactory()

    def request(self, body):
        request = self.factory.post(
            "/charging/api/assetManagement/assets/validateJob", data=json.dumps(body), content_type="application/json"
        )
        request.user = self.user
        return request

    @patch("wstore.asset_manager.resource_plugins.decorators._load_plugin_model")
    @patch("wstore.asset_manager.resource_plugins.decorators._get_plugin_model")
    @patch("wstore.asset_manager.resource_plugins.resolver.ServiceCatalog.get_specification")
    def test_creation_route_runs_single_hook_before_success(self, get, lookup, load):
        service = service_spec("service-1", "category-1")
        get.return_value = service
        plugin = load.return_value
        product = product_spec(services=("service-1",))

        request = self.request({"action": "create", "product": product})

        response = resolve(request.path).func(request)

        self.assertEqual(200, response.status_code)
        lookup.assert_called_once_with(category_id="category-1")
        plugin.on_product_spec_validation.assert_called_once_with(
            self.user.userprofile.current_organization, service, product
        )
        plugin.on_product_spec_validation.side_effect = PluginError("reject")

        request = self.request({"action": "create", "product": product})

        self.assertEqual(422, resolve(request.path).func(request).status_code)

    def test_ordinary_products_and_parent_default_actions(self):
        for action, status in (
            ("create", 200),
            ("attach", 400),
            ("upgrade", 200),
            ("attach_upgrade", 400),
            ("invalid", 400),
        ):
            with self.subTest(action=action):
                request = self.request({"action": action, "product": product_spec()})
                self.assertEqual(status, resolve(request.path).func(request).status_code)

    @patch("wstore.asset_manager.resource_plugins.resolver.ServiceCatalog.get_specification")
    def test_missing_reference_and_invalid_service_type_are_400(self, get):
        for service in ({"error": "not found"}, {"id": "service-1", "specCharacteristic": [{"name": "Service Type"}]}):
            with self.subTest(service=service):
                get.return_value = service
                request = self.request({"action": "create", "product": product_spec(services=("service-1",))})
                self.assertEqual(400, resolve(request.path).func(request).status_code)

    def test_invalid_body_and_non_provider_are_rejected(self):
        request = self.request([])

        self.assertEqual(400, resolve(request.path).func(request).status_code)
        self.user.userprofile.get_current_roles = lambda: []

        request = self.request({"action": "create", "product": product_spec()})

        self.assertEqual(403, resolve(request.path).func(request).status_code)
