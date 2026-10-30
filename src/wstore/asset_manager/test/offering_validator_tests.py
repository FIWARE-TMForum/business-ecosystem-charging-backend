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

from importlib import reload
from mock import MagicMock, call
from parameterized import parameterized
from bson import ObjectId

from django.test.testcases import TestCase
from django.test.utils import override_settings

from wstore.asset_manager import offering_validator
from wstore.asset_manager.test.offering_validator_test_data import *
from wstore.asset_manager.test.product_validator_test_data import BASIC_PRODUCT


@override_settings(CATALOG='https://tmf-catalog.com')
class OfferingValidatorTestCase(TestCase):
    tags = ("offering-validator",)

    def setUp(self):
        reload(offering_validator)
        self._provider = MagicMock()

        offering_validator.Offering.objects.create = MagicMock()

        self._asset_instance = MagicMock()
        self._asset_instance.resource_type = "Widget"
        self._asset_instance.content_type = "application/x-widget"
        self._asset_instance.provider = self._provider
        self._asset_instance.product_id = None
        self._asset_instance.is_public = False
        self._asset_instance.pk = ObjectId("61004aba5e05acc115f022f0")

        offering_validator.Resource.objects.filter = MagicMock()
        offering_validator.Resource.objects.filter.return_value = [self._asset_instance]

        self._plugin_instance = MagicMock()
        self._plugin_instance.media_types = ["application/x-widget"]
        self._plugin_instance.formats = ["FILE"]
        self._plugin_instance.module = "wstore.asset_manager.resource_plugins.plugin.Plugin"
        self._plugin_instance.form = {}

        import wstore.asset_manager.resource_plugins.decorators

        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin = MagicMock()
        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.return_value = self._plugin_instance

    def tearDown(self):
        reload(offering_validator)

    def _mock_requests(self, responses):
        offering_validator.requests = MagicMock()

        mock_responses = []
        for response in responses:
            resp = MagicMock()
            resp.json.return_value = response
            resp.status_code = 200
            mock_responses.append(resp)
        
        offering_validator.requests.get.side_effect = mock_responses

    def _mock_offering_bundle(self, offering, is_digital=True):
        offering_validator.Offering = MagicMock()

        self._bundles = (
            [[]]
            if "bundledProductOffering" not in offering
            else [[MagicMock(id=off["id"], is_digital=is_digital)] for off in offering["bundledProductOffering"]]
        )
        offering_validator.Offering.objects.filter.side_effect = self._bundles

    def _validate_offering_calls(self, offering, asset, is_digital, is_open=False, is_custom=False):
        # Check resource retrieving if needed
        self.assertEquals([
            call(product_id=offering["productSpecification"]["id"]),
            #call(product_id=offering["productSpecification"]["id"])
        ], offering_validator.Resource.objects.filter.call_args_list)

        # Check offering creation
        offering_validator.Offering.objects.create.assert_called_once_with(
            owner_organization=self._provider,
            name=offering["name"],
            description="",
            version=offering["version"],
            is_digital=is_digital,
            is_open=is_open,
            asset=asset,
            bundled_offerings=[],
            is_custom=is_custom
        )

    def _validate_single_offering_calls(self, offering):
        self.assertEquals([
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:1234')),
            call("{}/productSpecification/{}".format('https://tmf-catalog.com', 'urn:ProductSpecification:12345'))
        ], offering_validator.requests.get.call_args_list)
        self._validate_offering_calls(offering, self._asset_instance, True)

    def _validate_physical_offering_calls(self, offering):
        self._validate_offering_calls(offering, None, False)

    def _validate_bundle_offering_calls(self, offering, is_digital, is_open=False):
        self.assertEquals(
            [call(off_id=off["id"]) for off in offering["bundledProductOffering"]],
            offering_validator.Offering.objects.filter.call_args_list,
        )

        # Validate offering creation
        offering_validator.Offering.objects.create.assert_called_once_with(
            owner_organization=self._provider,
            name=offering["name"],
            description="",
            version=offering["version"],
            is_digital=is_digital,
            is_open=is_open,
            is_custom=False,
            asset=None,
            bundled_offerings=[off[0].pk for off in self._bundles],
        )

    def _validate_bundle_digital_offering_calls(self, offering):
        self._validate_bundle_offering_calls(offering, True)

    def _validate_bundle_physical_offering_calls(self, offering):
        self._validate_bundle_offering_calls(offering, False)

    def _validate_open_offering_calls(self, offering):
        offering_validator.requests.get.assert_called_once_with(
            "{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:1234')
        )
        self._validate_offering_calls(offering, self._asset_instance, True, is_open=True)

        self.assertTrue(self._asset_instance.is_public)
        self._asset_instance.save.assert_called_once_with()

    def _validate_open_bundle_calls(self, offering):
        self._validate_bundle_offering_calls(offering, True, is_open=True)

    def _validate_custom_pricing_calls(self, offering):
        offering_validator.requests.get.assert_called_once_with(
            "{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:1234')
        )
        self._validate_offering_calls(offering, self._asset_instance, True, False, True)

    def _validate_custom_pricing_calls_multiple(self, offering):
        self.assertEquals([
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:1234')),
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:4567'))
        ], offering_validator.requests.get.call_args_list)

        self._validate_offering_calls(offering, self._asset_instance, True, False, True)

    def _validate_profile_plan(self, offering):
        self.assertEquals([
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:1234')),
            call("{}/productSpecification/{}".format('https://tmf-catalog.com', 'urn:ProductSpecification:12345'))
        ], offering_validator.requests.get.call_args_list)

        self._validate_offering_calls(offering, self._asset_instance, True)

    def _validate_profile_multiple(self, offering):
        self.assertEquals([
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:1234')),
            call("{}/productSpecification/{}".format('https://tmf-catalog.com', 'urn:ProductSpecification:12345')),
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:ProductOfferingPrice:1111')),
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:ProductOfferingPrice:1112'))
        ], offering_validator.requests.get.call_args_list)

        self._validate_offering_calls(offering, self._asset_instance, True)

    def _validate_component_multiple(self, offering):
        self.assertEquals([
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:product-offering-price:1234')),
            call("{}/productSpecification/{}".format('https://tmf-catalog.com', 'urn:ProductSpecification:12345')),
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:ProductOfferingPrice:1111')),
            call("{}/productOfferingPrice/{}".format('https://tmf-catalog.com', 'urn:ProductOfferingPrice:1112'))
        ], offering_validator.requests.get.call_args_list)

        self._validate_offering_calls(offering, self._asset_instance, True)

    def _non_digital_offering(self):
        offering_validator.Resource.objects.filter.return_value = []

    def _non_digital_bundle(self):
        self._mock_offering_bundle(BUNDLE_OFFERING, is_digital=False)

    def _open_bundled(self):
        for bundle_resp in self._bundles:
            for bundle in bundle_resp:
                bundle.is_open = True

    def _non_digital_offering(self):
        offering_validator.Resource.objects.filter.return_value = []

    def _invalid_bundled(self):
        offering_validator.Offering.objects.filter.side_effect = None
        offering_validator.Offering.objects.filter.return_value = []

    def _open_existing(self):
        offering_validator.Offering.objects.filter.side_effect = [[MagicMock(id="6"), MagicMock(id="8")]]

    def _mixed_bundled_offerings(self):
        offering_validator.Offering.objects.filter.side_effect = [
            [MagicMock(id="6", is_digital=True)],
            [MagicMock(id="7", is_digital=False)],
        ]

    def _catalog_api_error(self):
        offering_validator.requests.get().status_code = 500

    def _non_open_bundled(self):
        for bundle_resp in self._bundles:
            for bundle in bundle_resp:
                bundle.is_open = False

    @parameterized.expand([
        ("onetime_pricing", BASE_OFFERING, [OT_OFFERING_PRICE, BASIC_PROD_SPEC], _validate_single_offering_calls),
        ("free_offering", FREE_OFFERING, [], _validate_physical_offering_calls, _non_digital_offering),
        ("bundle_offering", BUNDLE_OFFERING, [], _validate_bundle_digital_offering_calls),
        ("bundle_offering_non_digital", BUNDLE_OFFERING, [], _validate_bundle_physical_offering_calls, _non_digital_bundle),
        ("open_offering", BASE_OFFERING, [OPEN_OFFERING_PRICE], _validate_open_offering_calls),
        ("open_bundle", OPEN_BUNDLE, [OPEN_OFFERING_PRICE], _validate_open_bundle_calls, _open_bundled),
        ("custom_pricing", BASE_OFFERING, [CUSTOM_OFFERING_PRICING], _validate_custom_pricing_calls),
        ("custom_pricing_multiple", BASE_OFFERING_MULTIPLE, [CUSTOM_OFFERING_PRICING, CUSTOM_OFFERING_PRICING_2], _validate_custom_pricing_calls_multiple),
        ("profile_plan_single", BASE_OFFERING, [PROFILE_PLAN, PROFILE_PROD_SPEC], _validate_profile_plan),
        ("profile_plan_multiple", BASE_OFFERING, [PROFILE_PLAN_MULTIPLE, PROFILE_PROD_SPEC, PRICE_COMPONENT_1, PRICE_COMPONENT_2], _validate_profile_multiple),
        ("component_char_plan", BASE_OFFERING, [COMPONENT_PLAN, PROFILE_PROD_SPEC, PRICE_COMPONENT_3, PRICE_COMPONENT_4], _validate_component_multiple)
    ])
    def test_create_offering_validation(self, name, offering, requests, checker, side_effect=None):
        # Mock requests
        self._mock_requests(requests)
        self._mock_offering_bundle(offering)

        if side_effect is not None:
            side_effect(self)

        validator = offering_validator.OfferingValidator()
        validator.validate("create", self._provider, offering)

        checker(self, offering)

    @parameterized.expand([
        ("zero_offering", BASE_OFFERING, [ZERO_PRICING, BASIC_PROD_SPEC], "Invalid price, it must be greater than zero."),
        ("missing_type", BASE_OFFERING, [MISSING_PRICETYPE, BASIC_PROD_SPEC], "Missing required field priceType in productOfferingPrice component"),
        ("invalid_type", BASE_OFFERING, [INVALID_PRICETYPE, BASIC_PROD_SPEC], "Invalid priceType, it must be one time, recurring, or usage"),
        ("missing_charge_period", BASE_OFFERING, [MISSING_PERIOD, BASIC_PROD_SPEC], "Missing required field recurringChargePeriodType for recurring priceType"),
        ("invalid_period", BASE_OFFERING, [INVALID_PERIOD, BASIC_PROD_SPEC], "Unrecognized recurringChargePeriodType: invalid"),
        ("missing_price", BASE_OFFERING, [MISSING_PRICE, BASIC_PROD_SPEC], "Missing required field price in productOfferingPrice",),
        ("missing_currency", BASE_OFFERING, [MISSING_CURRENCY, BASIC_PROD_SPEC], "Missing currency code in price"),
        ("invalid_currency", BASE_OFFERING, [INVALID_CURRENCY, BASIC_PROD_SPEC], "Unrecognized currency: invalid"),
        ("missing_name", BASE_OFFERING, [MISSING_NAME], "Missing required field name in productOfferingPrice"),
        ("multiple_names", BASE_OFFERING_MULTIPLE, [OT_OFFERING_PRICE, BASIC_PROD_SPEC, OT_OFFERING_PRICE_2], "Price plans names must be unique (plan)"),
        ("bundle_missing", BUNDLE_MISSING_FIELD, [], "Offering bundles must contain a bundledProductOffering field"),
        ("bundle_invalid_number", BUNDLE_MISSING_ELEMS, [], "Offering bundles must contain at least two bundled offerings"),
        ("open_mixed", OPEN_MIXED, [OPEN_OFFERING_PRICE, OPEN_MIXED_PRICE, BASIC_PROD_SPEC], "Open offerings cannot include price plans"),
        ("custom_pricing_error", BASE_OFFERING_MULTIPLE, [CUSTOM_OFFERING_PRICING, OT_OFFERING_PRICE_2, BASIC_PROD_SPEC], "Custom pricing offerings cannot include processed price plans"),
        ("bundle_inv_bundled", BUNDLE_OFFERING, [], "The bundled offering 6 is not registered", _invalid_bundled),
        ("bundle_mixed", BUNDLE_OFFERING, [], "Mixed bundle offerings are not allowed. All bundled offerings must be digital or physical", _mixed_bundled_offerings),
        ("open_multiple_offers", BASE_OFFERING, [OPEN_OFFERING_PRICE], "Assets of open offerings cannot be monetized in other offerings", _open_existing),
        ("open_non_digital", BASE_OFFERING, [OPEN_OFFERING_PRICE], "Non digital products cannot be open", _non_digital_offering),
        ("open_bundle_mixed", OPEN_BUNDLE, [OPEN_OFFERING_PRICE], "If a bundle is open all the bundled offerings must be open", _non_open_bundled),
        ("invalid_spec", INVALID_SPEC, [PROFILE_PLAN, INVALID_PROD_SPEC], "The productSpecValueUse point to an invalid product specification"),
        ("invalid_char_use", BASE_OFFERING, [INVALID_USE, PROFILE_PROD_SPEC], "ProductSpecValueUse refers to non-existing product characteristic"),
        ("invalid_char_use_value", BASE_OFFERING, [INVALID_USE_VALUE, PROFILE_PROD_SPEC], "ProductSpecValueUse refers to non-existing product characteristic value")
    ])
    def test_create_offering_validation_error(self, name, offering, pricing, msg, side_effect=None):
        self._mock_requests(pricing)
        self._mock_offering_bundle(offering)

        if side_effect is not None:
            side_effect(self)

        err = False
        try:
            validator = offering_validator.OfferingValidator()
            validator.validate("create", self._provider, offering)
        except ValueError as e:
            self.assertEquals(str(e), msg)
            err = True

        self.assertTrue(err)

    def test_attachment_is_not_a_catalog_action(self):
        offering_validator.Offering = MagicMock()
        validator = offering_validator.OfferingValidator()
        with self.assertRaisesRegex(ValueError, "not valid"):
            validator.validate("attach", self._provider, BASE_OFFERING)
        offering_validator.Offering.objects.filter.assert_not_called()
        offering_validator.Offering.objects.create.assert_not_called()

    def _mock_offering_update(self, pricing):
        offering_validator.Resource.objects.filter.return_value = [self._asset_instance]

        self._mock_requests(pricing)

        offering_validator.Offering = MagicMock()
        offering_validator.Offering.objects.filter.return_value = []

    def test_update_offering_validator(self):
        self._mock_offering_update([OT_OFFERING_PRICE, BASIC_PROD_SPEC])

        validator = offering_validator.OfferingValidator()
        validator.validate("update", self._provider, BASE_OFFERING)

        # Validate calls
        self.assertEquals(0, offering_validator.Offering.objects.filter.call_count)
        self.assertFalse(self._asset_instance.is_public)
        self._asset_instance.save.assert_called_once_with()

    def test_update_open_offering(self):
        self._mock_offering_update([OPEN_OFFERING_PRICE])

        validator = offering_validator.OfferingValidator()
        validator.validate("update", self._provider, BASE_OFFERING)

        # Validate calls
        offering_validator.Offering.objects.filter.assert_called_once_with(asset=self._asset_instance)
        self.assertTrue(self._asset_instance.is_public)
        self._asset_instance.save.assert_called_once_with()

    def test_update_open_offering_multiple_error(self):
        self._mock_offering_update([OPEN_OFFERING_PRICE])

        offering_validator.Offering.objects.filter.return_value = [
            MagicMock(),
            MagicMock(),
        ]
        error = None
        try:
            validator = offering_validator.OfferingValidator()
            validator.validate("update", self._provider, BASE_OFFERING)
        except Exception as e:
            error = e

        self.assertTrue(isinstance(error, ValueError))
        self.assertEqual(
            str(error),
            "Assets of open offerings cannot be monetized in other offerings",
        )

    @parameterized.expand([
        ("continuous_single_char", ANTICOLLISION_CONTINUOUS_SINGLE),
        ("continuous_multiple_segments", ANTICOLLISION_CONTINUOUS_MULTIPLE_SEGMENTS),
        ("continuous_with_multiple_values", ANTICOLLISION_CONTINUOUS_WITH_MULTIPLE_VALUES),
        ("continuous_with_duplicates", ANTICOLLISION_CONTINUOUS_WITH_DUPLICATES),
        ("multiple_chars_all_continuous", ANTICOLLISION_MULTIPLE_CHARS_ALL_CONTINUOUS),
        ("exact_boundaries", ANTICOLLISION_EXACT_BOUNDARIES),
        ("complex_branches", ANTICOLLISION_COMPLEX_BRANCHES)
    ])
    def test_check_range_collision_continuous(self, name, anti_collision_data):
        from copy import deepcopy
        validator = offering_validator.OfferingValidator()

        # deepcopy to avoid modifying the test data (method pops total_range)
        test_data = deepcopy(anti_collision_data)

        # Should not raise any exception
        result = validator._check_range_collision(test_data)
        self.assertIsNone(result)

    @parameterized.expand([
        ("non_continuous_gap", ANTICOLLISION_NON_CONTINUOUS_GAP, "urn:Characteristic:9999"),
        ("multiple_chars_one_non_continuous", ANTICOLLISION_MULTIPLE_CHARS_ONE_NON_CONTINUOUS, "urn:Characteristic:4444")
    ])
    def test_check_range_collision_non_continuous(self, name, anti_collision_data, expected_char_id):
        from copy import deepcopy
        validator = offering_validator.OfferingValidator()

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
        validator = offering_validator.OfferingValidator()

        record = {
            "from-1": [10],
            "from-11": [20]
        }

        # Should find path from 1 to 20
        result = validator._recursive_anti_collision(1, 20, record)
        self.assertTrue(result)

        # Should not find path from 1 to 30
        result = validator._recursive_anti_collision(1, 30, record)
        self.assertFalse(result)

    def test_recursive_anti_collision_multiple_paths(self):
        validator = offering_validator.OfferingValidator()

        record = {
            "from-1": [10, 15, 20],
            "from-11": [25],
            "from-16": [30],
            "from-21": [35],
            "from-26": [40],
            "from-31": [45],
            "from-36": [50]
        }

        # Should find path from 1 to 50 through multiple branches
        result = validator._recursive_anti_collision(1, 50, record)
        self.assertTrue(result)

        # Should find path from 1 to 40
        result = validator._recursive_anti_collision(1, 40, record)
        self.assertTrue(result)

    def test_recursive_anti_collision_empty_record(self):
        validator = offering_validator.OfferingValidator()

        record = {}

        # Should return False for empty record
        result = validator._recursive_anti_collision(1, 100, record)
        self.assertFalse(result)

    def test_recursive_anti_collision_no_path(self):
        validator = offering_validator.OfferingValidator()

        record = {
            "from-1": [50],
            "from-60": [100]
        }

        # Should not find path from 1 to 100 due to gap
        result = validator._recursive_anti_collision(1, 100, record)
        self.assertFalse(result)
