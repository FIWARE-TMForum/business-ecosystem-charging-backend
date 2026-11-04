# -*- coding: utf-8 -*-

# Copyright (c) 2024 Future Internet Consulting and Development Solutions S.L.

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

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
import json

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve
from parameterized import parameterized

from wstore.asset_manager.offering_validator import OfferingValidator
from wstore.asset_manager.errors import ProductError
from wstore.asset_manager.resource_plugins.plugin import ServicePlugin
from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.asset_manager.test import offering_validator_test_data as data
from wstore.asset_manager.test.product_validator_tests import product_spec, service_spec, resource_spec
from wstore.store_commons.product_catalog import ProductCatalog, ProductCatalogError


class OfferingPricingTests(SimpleTestCase):
    def setUp(self):
        patcher = patch("wstore.asset_manager.resource_plugins.decorators.CatalogResolver")
        self.resolver = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.resolver.offering_specifications.return_value = []

        self.validator = OfferingValidator()
        self.validator._catalog = Mock(spec=ProductCatalog)
        self.provider = object()

    def pricing(self, offering, prices, product=data.BASIC_PROD_SPEC):
        self.validator._catalog.get_price.side_effect = deepcopy(prices)
        self.validator._catalog.get_specification.return_value = deepcopy(product)

        return self.validator._validate_offering_pricing(self.provider, deepcopy(offering))

    @parameterized.expand(
        [
            ("one_time", data.BASE_OFFERING, [data.OT_OFFERING_PRICE], data.BASIC_PROD_SPEC, (False, False)),
            ("free", data.FREE_OFFERING, [], data.BASIC_PROD_SPEC, (False, False)),
            ("open", data.BASE_OFFERING, [data.OPEN_OFFERING_PRICE], data.BASIC_PROD_SPEC, (True, False)),
            ("custom", data.BASE_OFFERING, [data.CUSTOM_OFFERING_PRICING], data.BASIC_PROD_SPEC, (False, True)),
            (
                "multiple_custom",
                data.BASE_OFFERING_MULTIPLE,
                [data.CUSTOM_OFFERING_PRICING, data.CUSTOM_OFFERING_PRICING_2],
                data.BASIC_PROD_SPEC,
                (False, True),
            ),
            ("profile_single", data.BASE_OFFERING, [data.PROFILE_PLAN], data.PROFILE_PROD_SPEC, (False, False)),
            (
                "profile_multiple",
                data.BASE_OFFERING,
                [data.PROFILE_PLAN_MULTIPLE, data.PRICE_COMPONENT_1, data.PRICE_COMPONENT_2],
                data.PROFILE_PROD_SPEC,
                (False, False),
            ),
            (
                "component_conditions",
                data.BASE_OFFERING,
                [data.COMPONENT_PLAN, data.PRICE_COMPONENT_3, data.PRICE_COMPONENT_4],
                data.PROFILE_PROD_SPEC,
                (False, False),
            ),
        ]
    )
    def test_current_price_plans(self, name, offering, prices, product, expected):
        self.assertEqual(expected, self.pricing(offering, prices, product))
        self.assertEqual(len(prices), self.validator._catalog.get_price.call_count)

    @parameterized.expand(
        [
            ("zero", data.BASE_OFFERING, [data.ZERO_PRICING], data.BASIC_PROD_SPEC, "greater than zero"),
            (
                "missing_type",
                data.BASE_OFFERING,
                [data.MISSING_PRICETYPE],
                data.BASIC_PROD_SPEC,
                "Missing required field priceType",
            ),
            ("invalid_type", data.BASE_OFFERING, [data.INVALID_PRICETYPE], data.BASIC_PROD_SPEC, "Invalid priceType"),
            (
                "missing_period",
                data.BASE_OFFERING,
                [data.MISSING_PERIOD],
                data.BASIC_PROD_SPEC,
                "Missing required field recurringChargePeriodType",
            ),
            (
                "invalid_period",
                data.BASE_OFFERING,
                [data.INVALID_PERIOD],
                data.BASIC_PROD_SPEC,
                "Unrecognized recurringChargePeriodType",
            ),
            (
                "missing_price",
                data.BASE_OFFERING,
                [data.MISSING_PRICE],
                data.BASIC_PROD_SPEC,
                "Missing required field price",
            ),
            ("missing_currency", data.BASE_OFFERING, [data.MISSING_CURRENCY], data.BASIC_PROD_SPEC, "Missing currency"),
            (
                "invalid_currency",
                data.BASE_OFFERING,
                [data.INVALID_CURRENCY],
                data.BASIC_PROD_SPEC,
                "Unrecognized currency",
            ),
            (
                "missing_name",
                data.BASE_OFFERING,
                [data.MISSING_NAME],
                data.BASIC_PROD_SPEC,
                "Missing required field name",
            ),
            (
                "duplicate_names",
                data.BASE_OFFERING_MULTIPLE,
                [data.OT_OFFERING_PRICE, data.OT_OFFERING_PRICE_2],
                data.BASIC_PROD_SPEC,
                "names must be unique",
            ),
            (
                "open_mixed",
                data.OPEN_MIXED,
                [data.OPEN_OFFERING_PRICE, data.OPEN_MIXED_PRICE],
                data.BASIC_PROD_SPEC,
                "Open offerings cannot include price plans",
            ),
            (
                "custom_mixed",
                data.BASE_OFFERING_MULTIPLE,
                [data.CUSTOM_OFFERING_PRICING, data.OT_OFFERING_PRICE_2],
                data.BASIC_PROD_SPEC,
                "Custom pricing offerings cannot include",
            ),
            (
                "invalid_product",
                data.INVALID_SPEC,
                [data.PROFILE_PLAN],
                data.INVALID_PROD_SPEC,
                "invalid product specification",
            ),
            (
                "invalid_characteristic",
                data.BASE_OFFERING,
                [data.INVALID_USE],
                data.PROFILE_PROD_SPEC,
                "non-existing product characteristic",
            ),
            (
                "invalid_value",
                data.BASE_OFFERING,
                [data.INVALID_USE_VALUE],
                data.PROFILE_PROD_SPEC,
                "non-existing product characteristic value",
            ),
        ]
    )
    def test_current_price_plan_rejections(self, name, offering, prices, product, message):
        with self.assertRaisesRegex(ValueError, message):
            self.pricing(offering, prices, product)

    def test_profile_and_component_conditions_cannot_be_combined(self):
        component = deepcopy(data.PRICE_COMPONENT_1)
        component["prodSpecCharValueUse"] = deepcopy(data.PROFILE_PLAN["prodSpecCharValueUse"])

        with self.assertRaisesRegex(ValueError, "configuration profile"):
            self.pricing(data.BASE_OFFERING, [data.PROFILE_PLAN_MULTIPLE, component], data.PROFILE_PROD_SPEC)

    def test_recurring_variants_and_referenced_component_downloads(self):
        for price_type in ("recurring", "recurring-prepaid", "recurring-postpaid"):
            with self.subTest(price_type=price_type):
                price = {**data.OT_OFFERING_PRICE, "priceType": price_type, "recurringChargePeriodType": "month"}
                self.assertEqual((False, False), self.pricing(data.BASE_OFFERING, [price]))

        self.validator._catalog.reset_mock()
        self.pricing(
            data.BASE_OFFERING,
            [data.COMPONENT_PLAN, data.PRICE_COMPONENT_3, data.PRICE_COMPONENT_4],
            data.PROFILE_PROD_SPEC,
        )

        expected = [call(data.BASE_OFFERING["productOfferingPrice"][0]["id"])]
        expected.extend(call(ref["id"]) for ref in data.COMPONENT_PLAN["bundledPopRelationship"])
        self.assertEqual(expected, self.validator._catalog.get_price.call_args_list)


class OfferingRangeTests(SimpleTestCase):
    @parameterized.expand(
        [
            ("continuous_single_char", data.ANTICOLLISION_CONTINUOUS_SINGLE),
            ("continuous_multiple_segments", data.ANTICOLLISION_CONTINUOUS_MULTIPLE_SEGMENTS),
            ("continuous_with_multiple_values", data.ANTICOLLISION_CONTINUOUS_WITH_MULTIPLE_VALUES),
            ("continuous_with_duplicates", data.ANTICOLLISION_CONTINUOUS_WITH_DUPLICATES),
            ("multiple_chars_all_continuous", data.ANTICOLLISION_MULTIPLE_CHARS_ALL_CONTINUOUS),
            ("exact_boundaries", data.ANTICOLLISION_EXACT_BOUNDARIES),
            ("complex_branches", data.ANTICOLLISION_COMPLEX_BRANCHES),
        ]
    )
    def test_check_range_collision_continuous(self, name, anti_collision_data):
        from copy import deepcopy

        validator = OfferingValidator()

        # deepcopy to avoid modifying the test data (method pops total_range)
        test_data = deepcopy(anti_collision_data)

        # Should not raise any exception
        result = validator._check_range_collision(test_data)
        self.assertIsNone(result)

    @parameterized.expand(
        [
            ("non_continuous_gap", data.ANTICOLLISION_NON_CONTINUOUS_GAP, "urn:Characteristic:9999"),
            (
                "multiple_chars_one_non_continuous",
                data.ANTICOLLISION_MULTIPLE_CHARS_ONE_NON_CONTINUOUS,
                "urn:Characteristic:4444",
            ),
        ]
    )
    def test_check_range_collision_non_continuous(self, name, anti_collision_data, expected_char_id):
        from copy import deepcopy

        validator = OfferingValidator()

        # deepcopy to avoid modifying the test data
        test_data = deepcopy(anti_collision_data)

        error = None
        try:
            validator._check_range_collision(test_data)
        except ValueError as e:
            error = e

        self.assertIsNotNone(error)
        self.assertIn(expected_char_id, str(error))
        self.assertIn("doesn't have continous subranges", str(error))

    def test_recursive_anti_collision_basic(self):
        validator = OfferingValidator()

        record = {"from-1": [10], "from-11": [20]}

        # Should find path from 1 to 20
        result = validator._recursive_anti_collision(1, 20, record)
        self.assertTrue(result)

        # Should not find path from 1 to 30
        result = validator._recursive_anti_collision(1, 30, record)
        self.assertFalse(result)

    def test_recursive_anti_collision_multiple_paths(self):
        validator = OfferingValidator()

        record = {
            "from-1": [10, 15, 20],
            "from-11": [25],
            "from-16": [30],
            "from-21": [35],
            "from-26": [40],
            "from-31": [45],
            "from-36": [50],
        }

        # Should find path from 1 to 50 through multiple branches
        result = validator._recursive_anti_collision(1, 50, record)
        self.assertTrue(result)

        # Should find path from 1 to 40
        result = validator._recursive_anti_collision(1, 40, record)
        self.assertTrue(result)

    def test_recursive_anti_collision_empty_record(self):
        validator = OfferingValidator()

        record = {}

        # Should return False for empty record
        result = validator._recursive_anti_collision(1, 100, record)
        self.assertFalse(result)

    def test_recursive_anti_collision_no_path(self):
        validator = OfferingValidator()

        record = {"from-1": [50], "from-60": [100]}

        # Should not find path from 1 to 100 due to gap
        result = validator._recursive_anti_collision(1, 100, record)
        self.assertFalse(result)


class OfferingPluginTests(SimpleTestCase):
    def setUp(self):
        self.provider = object()
        self.catalog = Mock(spec=ProductCatalog)
        self.services = Mock()

        for target, value in (
            ("wstore.asset_manager.resource_plugins.resolver.ProductCatalog", self.catalog),
            ("wstore.asset_manager.offering_validator.ProductCatalog", self.catalog),
            ("wstore.asset_manager.resource_plugins.resolver.ServiceCatalog", self.services),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.product = product_spec(services=("s1", "ordinary", "s2"))
        self.specs = {
            "s1": service_spec("s1", "c1"),
            "s2": service_spec("s2", "c2"),
            "ordinary": service_spec("ordinary"),
        }
        self.services.get_specification.side_effect = self.specs.get
        self.catalog.get_specification.return_value = self.product
        self.catalog.get_price.return_value = deepcopy(data.OT_OFFERING_PRICE)
        self.offer = {**deepcopy(data.BASE_OFFERING), "productSpecification": {"id": self.product["id"]}}
        self.plugins = {"c1": Mock(spec=ServicePlugin), "c2": Mock(spec=ServicePlugin)}

        patcher = patch(
            "wstore.asset_manager.resource_plugins.decorators._get_plugin_model",
            side_effect=lambda category_id, plugin_type: category_id,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch(
            "wstore.asset_manager.resource_plugins.decorators._load_plugin_model", side_effect=self.plugins.get
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.validator = OfferingValidator()

    def test_pre_pricing_post_order_and_service_arguments(self):
        events = Mock()
        events.attach_mock(self.plugins["c1"], "first")
        events.attach_mock(self.plugins["c2"], "second")
        events.attach_mock(self.catalog.get_price, "price")

        self.validator.validate("create", self.provider, self.offer)

        first = (self.provider, self.specs["s1"], self.product, self.offer)
        second = (self.provider, self.specs["s2"], self.product, self.offer)
        self.assertEqual(
            [
                call.first.on_pre_product_offering_validation(*first),
                call.second.on_pre_product_offering_validation(*second),
                call.price(self.offer["productOfferingPrice"][0]["id"]),
                call.first.on_post_product_offering_validation(*first),
                call.second.on_post_product_offering_validation(*second),
            ],
            events.mock_calls,
        )
        self.plugins["c1"].on_product_spec_validation.assert_not_called()
        self.plugins["c1"].on_pre_service_spec_creation.assert_not_called()

    def test_pre_failure_prevents_price_validation_and_post_hooks(self):
        self.plugins["c1"].on_pre_product_offering_validation.side_effect = PluginError("reject")

        with self.assertRaises(PluginError):
            self.validator.validate("create", self.provider, self.offer)

        self.catalog.get_price.assert_not_called()
        self.plugins["c2"].on_pre_product_offering_validation.assert_not_called()
        self.plugins["c1"].on_post_product_offering_validation.assert_not_called()

    def test_backend_failure_prevents_all_post_hooks(self):
        self.catalog.get_price.return_value = deepcopy(data.ZERO_PRICING)

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self.validator.validate("create", self.provider, self.offer)

        for plugin in self.plugins.values():
            plugin.on_pre_product_offering_validation.assert_called_once()
            plugin.on_post_product_offering_validation.assert_not_called()

    def test_post_failure_is_reported(self):
        self.plugins["c1"].on_post_product_offering_validation.side_effect = PluginError("reject")

        with self.assertRaises(PluginError):
            self.validator.validate("create", self.provider, self.offer)

        self.plugins["c2"].on_post_product_offering_validation.assert_not_called()

    def test_ordinary_service_still_receives_price_validation(self):
        self.product["serviceSpecification"] = [{"id": "ordinary"}]
        self.catalog.get_price.return_value = deepcopy(data.ZERO_PRICING)

        with self.assertRaises(ValueError):
            self.validator.validate("create", self.provider, self.offer)

        self.catalog.get_price.assert_called_once()
        self.plugins["c1"].on_pre_product_offering_validation.assert_not_called()

    def test_free_open_and_custom_offerings_still_invoke_plugins(self):
        for prices in ([], [data.OPEN_OFFERING_PRICE], [data.CUSTOM_OFFERING_PRICING]):
            with self.subTest(prices=prices):
                self.plugins["c1"].reset_mock()
                self.offer["productOfferingPrice"] = [{"id": price["id"]} for price in prices]
                self.catalog.get_price.side_effect = deepcopy(prices)

                self.validator.validate("create", self.provider, self.offer)

                self.plugins["c1"].on_post_product_offering_validation.assert_called_once_with(
                    self.provider, self.specs["s1"], self.product, self.offer
                )

    def test_update_uses_proposed_document_without_loading_old_offering(self):
        proposed = {**self.offer, "name": "Renamed"}
        original = deepcopy(proposed)

        self.validator.validate_update(provider=self.provider, catalog_element=proposed)

        self.catalog.get_offering.assert_not_called()
        self.assertEqual(original, proposed)
        self.assertIs(proposed, self.plugins["c1"].on_pre_product_offering_validation.call_args.args[3])

    def test_product_bundle_reuses_product_service_resolution(self):
        first = product_spec("p1", ("s1",))
        second = product_spec("p2", ("s1", "s2"))
        bundle = {"id": "bundle", "isBundle": True, "bundledProductSpecification": [{"id": "p1"}, {"id": "p2"}]}
        self.catalog.get_specification.side_effect = {"bundle": bundle, "p1": first, "p2": second}.get
        self.offer["productSpecification"] = {"id": "bundle"}
        self.offer["productOfferingPrice"] = []

        self.validator.validate("create", self.provider, self.offer)

        self.assertEqual(
            [
                call(self.provider, self.specs["s1"], first, self.offer),
                call(self.provider, self.specs["s1"], second, self.offer),
            ],
            self.plugins["c1"].on_post_product_offering_validation.call_args_list,
        )
        self.plugins["c2"].on_post_product_offering_validation.assert_called_once_with(
            self.provider, self.specs["s2"], second, self.offer
        )

    def test_offering_bundle_downloads_catalog_offerings(self):
        first = product_spec("p1", ("s1",))
        second = product_spec("p2", ("s2",))
        self.catalog.get_offering.side_effect = {
            "o1": {"id": "o1", "productSpecification": {"id": "p1"}},
            "o2": {"id": "o2", "productSpecification": {"id": "p2"}},
        }.get
        self.catalog.get_specification.side_effect = {"p1": first, "p2": second}.get
        offer = {"isBundle": True, "bundledProductOffering": [{"id": "o1"}, {"id": "o2"}]}

        self.validator.validate("create", self.provider, offer)

        self.assertEqual([call("o1"), call("o2")], self.catalog.get_offering.call_args_list)
        self.plugins["c2"].on_post_product_offering_validation.assert_called_once_with(
            self.provider, self.specs["s2"], second, offer
        )

    def test_nested_offering_bundle_is_rejected_before_service_lookup_or_hooks(self):
        offer = {"isBundle": True, "bundledProductOffering": [{"id": "o1"}, {"id": "o2"}]}
        self.catalog.get_offering.side_effect = [
            {"id": "o1", "productSpecification": {"id": "p1"}},
            {
                "id": "o2",
                "isBundle": True,
                "bundledProductOffering": [{"id": "o3"}, {"id": "o4"}],
            },
        ]

        with self.assertRaisesRegex(ProductError, "cannot contain other bundles"):
            self.validator.validate("create", self.provider, offer)

        self.assertEqual([call("o1"), call("o2")], self.catalog.get_offering.call_args_list)
        self.catalog.get_specification.assert_not_called()
        self.services.get_specification.assert_not_called()
        self.catalog.get_price.assert_not_called()
        self.plugins["c1"].on_pre_product_offering_validation.assert_not_called()

    def test_invalid_references_stop_before_hooks(self):
        self.services.get_specification.side_effect = None
        self.services.get_specification.return_value = {"error": "missing"}

        with self.assertRaises(ProductError):
            self.validator.validate("create", self.provider, self.offer)

        self.catalog.get_price.assert_not_called()
        self.plugins["c1"].on_pre_product_offering_validation.assert_not_called()

    def test_parent_dispatch_and_signatures_are_preserved(self):
        from inspect import signature
        from wstore.asset_manager.catalog_validator import CatalogValidator

        self.assertIs(CatalogValidator.validate, OfferingValidator.validate)
        for name in ("validate_creation", "validate_update"):
            self.assertEqual(signature(getattr(CatalogValidator, name)), signature(getattr(OfferingValidator, name)))

    def test_endpoint_maps_plugin_catalog_and_backend_failures(self):
        user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(current_organization=self.provider, get_current_roles=lambda: ["provider"]),
        )

        def invoke():
            request = RequestFactory().post(
                "/charging/api/assetManagement/assets/offeringJob",
                data=json.dumps({"action": "create", "offering": self.offer}),
                content_type="application/json",
            )
            request.user = user
            return resolve(request.path).func(request)

        self.assertEqual(200, invoke().status_code)
        self.plugins["c1"].on_pre_product_offering_validation.side_effect = PluginError("reject")
        self.assertEqual(422, invoke().status_code)
        self.plugins["c1"].on_pre_product_offering_validation.side_effect = None
        self.catalog.get_price.return_value = deepcopy(data.ZERO_PRICING)
        self.assertEqual(400, invoke().status_code)
        self.catalog.get_specification.side_effect = ProductCatalogError("offline")
        self.assertEqual(422, invoke().status_code)


class ResourceOfferingPluginTests(SimpleTestCase):
    def setUp(self):
        from wstore.asset_manager.resource_plugins.plugin import ResourcePlugin

        OfferingPluginTests.setUp(self)
        self.resources = Mock()
        patcher = patch(
            "wstore.asset_manager.resource_plugins.resolver.ResourceCatalog", return_value=self.resources
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.resource_specs = {
            "r1": resource_spec("r1", "c1"),
            "r2": resource_spec("r2", "c2"),
            "ordinary-resource": resource_spec("ordinary-resource"),
        }
        self.resources.get_specification.side_effect = self.resource_specs.get
        self.product["resourceSpecification"] = [{"id": id_} for id_ in self.resource_specs]
        self.resource_plugins = {"c1": Mock(spec=ResourcePlugin), "c2": Mock(spec=ResourcePlugin)}
        typed_plugins = {
            **{("service", category): plugin for category, plugin in self.plugins.items()},
            **{("resource", category): plugin for category, plugin in self.resource_plugins.items()},
        }
        patcher = patch(
            "wstore.asset_manager.resource_plugins.decorators._get_plugin_model",
            side_effect=lambda category_id, plugin_type: (plugin_type, category_id)
            if (plugin_type, category_id) in typed_plugins
            else None,
        )
        self.lookup = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch(
            "wstore.asset_manager.resource_plugins.decorators._load_plugin_model",
            side_effect=typed_plugins.get,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_mixed_plugins_all_run_pre_then_pricing_then_post(self):
        events = Mock()
        for name, plugin in (
            ("s1", self.plugins["c1"]),
            ("s2", self.plugins["c2"]),
            ("r1", self.resource_plugins["c1"]),
            ("r2", self.resource_plugins["c2"]),
        ):
            events.attach_mock(plugin, name)
        events.attach_mock(self.catalog.get_price, "price")
        self.validator.validate("create", self.provider, self.offer)
        self.assertEqual(
            [
                "s1.on_pre_product_offering_validation",
                "s2.on_pre_product_offering_validation",
                "r1.on_pre_product_offering_validation",
                "r2.on_pre_product_offering_validation",
                "price",
                "s1.on_post_product_offering_validation",
                "s2.on_post_product_offering_validation",
                "r1.on_post_product_offering_validation",
                "r2.on_post_product_offering_validation",
            ],
            [invocation[0] for invocation in events.mock_calls],
        )
        for n in (1, 2):
            expected = (self.provider, self.resource_specs[f"r{n}"], self.product, self.offer)
            self.resource_plugins[f"c{n}"].on_pre_product_offering_validation.assert_called_once_with(
                *expected
            )
            self.resource_plugins[f"c{n}"].on_post_product_offering_validation.assert_called_once_with(
                *expected
            )
            self.resource_plugins[f"c{n}"].on_product_spec_validation.assert_not_called()
            self.resource_plugins[f"c{n}"].on_pre_resource_spec_creation.assert_not_called()
        self.lookup.assert_any_call(category_id="c1", plugin_type="service")
        self.lookup.assert_any_call(category_id="c1", plugin_type="resource")

    def test_resource_only_product_does_not_read_service_catalog(self):
        self.product.pop("serviceSpecification")
        self.validator.validate("create", self.provider, self.offer)
        self.services.get_specification.assert_not_called()
        self.resource_plugins["c1"].on_post_product_offering_validation.assert_called_once()

    def test_ordinary_and_uninstalled_resource_types_skip_hooks_but_keep_pricing(self):
        self.product["serviceSpecification"] = []
        self.product["resourceSpecification"] = [{"id": "ordinary-resource"}, {"id": "external"}]
        self.resource_specs["external"] = resource_spec("external", "external-category")
        self.validator.validate("create", self.provider, self.offer)
        self.catalog.get_price.assert_called_once()
        for plugin in self.resource_plugins.values():
            self.assertEqual([], plugin.method_calls)

    @parameterized.expand([("create",), ("update",)])
    def test_resource_hooks_receive_complete_proposed_offering(self, action):
        self.offer["name"] = "Proposed name"
        before = deepcopy(self.offer)
        self.validator.validate(action, self.provider, self.offer)
        self.catalog.get_offering.assert_not_called()
        self.assertEqual(before, self.offer)
        self.assertIs(
            self.offer, self.resource_plugins["c1"].on_post_product_offering_validation.call_args.args[3]
        )

    def test_free_open_custom_offerings_still_run_resource_hooks(self):
        for prices in ([], [data.OPEN_OFFERING_PRICE], [data.CUSTOM_OFFERING_PRICING]):
            with self.subTest(prices=prices):
                self.resource_plugins["c1"].reset_mock()
                self.offer["productOfferingPrice"] = [{"id": price["id"]} for price in prices]
                self.catalog.get_price.side_effect = deepcopy(prices)
                self.validator.validate("create", self.provider, self.offer)
                self.resource_plugins["c1"].on_post_product_offering_validation.assert_called_once()

    def test_product_bundle_resource_hooks_keep_containing_product(self):
        first, second = product_spec("p1"), product_spec("p2")
        for product in (first, second):
            product["resourceSpecification"] = [{"id": "r1"}]
        bundle = {
            "id": "bundle",
            "isBundle": True,
            "bundledProductSpecification": [{"id": "p1"}, {"id": "p2"}],
        }
        self.catalog.get_specification.side_effect = {"bundle": bundle, "p1": first, "p2": second}.get
        self.offer["productSpecification"] = {"id": "bundle"}
        self.offer["productOfferingPrice"] = []
        self.validator.validate("create", self.provider, self.offer)
        self.assertEqual(
            [
                call(self.provider, self.resource_specs["r1"], first, self.offer),
                call(self.provider, self.resource_specs["r1"], second, self.offer),
            ],
            self.resource_plugins["c1"].on_post_product_offering_validation.call_args_list,
        )

    def test_offering_bundle_resource_hooks_receive_original_offering(self):
        first, second = product_spec("p1"), product_spec("p2")
        first["resourceSpecification"] = [{"id": "r1"}]
        second["resourceSpecification"] = [{"id": "r2"}]
        self.catalog.get_specification.side_effect = {"p1": first, "p2": second}.get
        self.catalog.get_offering.side_effect = {
            "o1": {"id": "o1", "productSpecification": {"id": "p1"}},
            "o2": {"id": "o2", "productSpecification": {"id": "p2"}},
        }.get
        offer = {"isBundle": True, "bundledProductOffering": [{"id": "o1"}, {"id": "o2"}]}
        self.validator.validate("create", self.provider, offer)
        self.resource_plugins["c1"].on_post_product_offering_validation.assert_called_once_with(
            self.provider, self.resource_specs["r1"], first, offer
        )
        self.resource_plugins["c2"].on_post_product_offering_validation.assert_called_once_with(
            self.provider, self.resource_specs["r2"], second, offer
        )

    def test_nested_offering_bundle_rejected_before_resource_reads(self):
        self.catalog.get_offering.side_effect = [
            {"id": "o1", "productSpecification": {"id": self.product["id"]}},
            {"id": "o2", "isBundle": True},
        ]
        offer = {"isBundle": True, "bundledProductOffering": [{"id": "o1"}, {"id": "o2"}]}
        with self.assertRaises(ProductError):
            self.validator.validate("create", self.provider, offer)
        self.resources.get_specification.assert_not_called()
        self.resource_plugins["c1"].on_pre_product_offering_validation.assert_not_called()

    def test_invalid_resource_reference_prevents_all_pre_hooks_and_pricing(self):
        self.resources.get_specification.side_effect = None
        self.resources.get_specification.return_value = {"id": "wrong-resource"}
        with self.assertRaises(ProductError):
            self.validator.validate("create", self.provider, self.offer)
        self.catalog.get_price.assert_not_called()
        self.plugins["c1"].on_pre_product_offering_validation.assert_not_called()
        self.resource_plugins["c1"].on_pre_product_offering_validation.assert_not_called()

    def test_resource_pre_hook_failure_blocks_pricing_and_all_post_hooks(self):
        self.resource_plugins["c1"].on_pre_product_offering_validation.side_effect = PluginError("reject")
        with self.assertRaises(PluginError):
            self.validator.validate("create", self.provider, self.offer)
        self.catalog.get_price.assert_not_called()
        self.resource_plugins["c2"].on_pre_product_offering_validation.assert_not_called()
        self.plugins["c1"].on_post_product_offering_validation.assert_not_called()

    def test_pricing_failure_prevents_resource_post_hooks(self):
        self.catalog.get_price.return_value = deepcopy(data.ZERO_PRICING)
        with self.assertRaises(ValueError):
            self.validator.validate("create", self.provider, self.offer)
        self.resource_plugins["c1"].on_pre_product_offering_validation.assert_called_once()
        self.resource_plugins["c1"].on_post_product_offering_validation.assert_not_called()

    def test_resource_post_hook_rejection_is_reported(self):
        self.resource_plugins["c1"].on_post_product_offering_validation.side_effect = PluginError("reject")
        with self.assertRaises(PluginError):
            self.validator.validate("create", self.provider, self.offer)
        self.catalog.get_price.assert_called_once()
        self.resource_plugins["c2"].on_post_product_offering_validation.assert_not_called()

    def test_endpoint_invokes_resource_hooks_and_reports_plugin_failure(self):
        user = SimpleNamespace(
            is_anonymous=False,
            is_staff=False,
            userprofile=SimpleNamespace(
                current_organization=self.provider,
                get_current_roles=lambda: ["provider"],
            ),
        )

        def invoke():
            request = RequestFactory().post(
                "/charging/api/assetManagement/assets/offeringJob",
                data=json.dumps({"action": "create", "offering": self.offer}),
                content_type="application/json",
            )
            request.user = user
            return resolve(request.path).func(request)

        self.assertEqual(200, invoke().status_code)
        self.resource_plugins["c1"].on_pre_product_offering_validation.side_effect = PluginError("reject")
        self.assertEqual(422, invoke().status_code)
