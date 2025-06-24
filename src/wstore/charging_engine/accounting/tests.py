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
from datetime import datetime
from importlib import reload

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from mock import MagicMock
from parameterized import parameterized

from wstore.charging_engine.accounting import sdr_manager, usage_client, views
from wstore.charging_engine.accounting.errors import UsageError

BASIC_SDR = {
    "status": "Received",
    "date": "2015-10-20 17:31:57.100000",
    "relatedParty": [{"id": "test_user"}],
    "usageCharacteristic": [
        {"name": "orderId", "value": "1"},
        {"name": "productId", "value": "2"},
        {"name": "correlationNumber", "value": "1"},
        {"name": "value", "value": "10"},
        {"name": "unit", "value": "invocation"},
    ],
}


class SDRManagerTestCase(TestCase):
    tags = ("sdr",)

    def setUp(self):
        sdr_manager.Organization = MagicMock()
        org = MagicMock()
        org.pk = "1111"
        sdr_manager.Organization.objects.filter.return_value = [org]

        # Create Order mock
        self._order = MagicMock()
        self._order.owner_organization = org

        self._contract = MagicMock()
        self._contract.pricing_model = {"pay_per_use": [{"unit": "invocation"}]}
        self._contract.correlation_number = 1
        self._contract.last_usage = None

        sdr_manager.Order = MagicMock()
        sdr_manager.Order.objects.get.return_value = self._order
        self._order.get_product_contract.return_value = self._contract

        self._user = MagicMock()
        self._user.is_staff = True
        self._user.userprofile.organizations = [{"organization": "1111"}]
        sdr_manager.User = MagicMock()
        sdr_manager.User.objects.get.return_value = self._user

        self._timestamp = datetime.strptime("2015-10-20 17:31:57.100", "%Y-%m-%d %H:%M:%S.%f")

    def _side_cust_not_exists(self):
        sdr_manager.Organization.objects.filter.return_value = []

    def _side_user_not_auth(self):
        self._user.userprofile.organizations = [{"organization": "2222"}]

    def _side_inv_purchase(self):
        self._contract.pricing_model = {
            "global_currency": "EUR",
            "single_payment": [{"value": 10}],
        }

    def _side_inv_label(self):
        self._contract.pricing_model = {
            "global_currency": "EUR",
            "pay_per_use": [{"value": 10, "unit": "call"}],
        }

    def _side_inv_time(self):
        self._contract.last_usage = datetime.strptime("2016-05-01 11:10:01.234", "%Y-%m-%d %H:%M:%S.%f")

    def _side_inv_order(self):
        sdr_manager.Order.objects.get.side_effect = Exception()

    def _side_inv_product(self):
        self._order.get_product_contract.side_effect = Exception()

    def _mod_inc_corr(self, sdr):
        sdr["usageCharacteristic"][2]["value"] = "2"
        sdr["date"] = "2015-10-20T17:31:57.838123"

    def _mod_inv_value(self, sdr):
        sdr["usageCharacteristic"][3]["value"] = "a"

    def _mod_no_chars(self, sdr):
        del sdr["usageCharacteristic"]

    def _mod_inv_state(self, sdr):
        sdr["status"] = "rated"

    def _mod_multiple_values(self, sdr):
        sdr["usageCharacteristic"].append({"name": "unit", "value": "invocation"})

    def _mod_missing_values(self, sdr):
        sdr["usageCharacteristic"] = [{"name": "unit", "value": "invocation"}]

    def _mod_no_party(self, sdr):
        del sdr["relatedParty"]

    @parameterized.expand(
        [
            ("basic",),
            (
                "inv_value",
                _mod_inv_value,
                None,
                ValueError,
                "The provided value is not a valid number",
            ),
            (
                "customer_not_existing",
                None,
                _side_cust_not_exists,
                ValueError,
                "The specified customer test_user does not exist",
            ),
            (
                "user_not_auth",
                None,
                _side_user_not_auth,
                PermissionDenied,
                "You don't belong to the customer organization",
            ),
            (
                "inv_corr",
                _mod_inc_corr,
                None,
                ValueError,
                "Invalid correlation number, expected: 1",
            ),
            (
                "inv_time",
                None,
                _side_inv_time,
                ValueError,
                "The provided timestamp specifies a lower timing than the last SDR received",
            ),
            (
                "inv_purch",
                None,
                _side_inv_purchase,
                ValueError,
                "The pricing model of the offering does not define pay-per-use components",
            ),
            (
                "inv_label",
                None,
                _side_inv_label,
                ValueError,
                "The specified unit is not included in the pricing model",
            ),
            (
                "inv_state",
                _mod_inv_state,
                None,
                ValueError,
                "Invalid initial status, must be Received",
            ),
            (
                "missing_chars",
                _mod_no_chars,
                None,
                ValueError,
                "Missing required field usageCharacteristic",
            ),
            (
                "multiple_values",
                _mod_multiple_values,
                None,
                ValueError,
                "Only a value is supported for characteristic unit",
            ),
            (
                "missing_value",
                _mod_missing_values,
                None,
                ValueError,
                "Missing mandatory characteristics, must be: orderId, productId, correlationNumber, unit, value",
            ),
            (
                "missing_party",
                _mod_no_party,
                None,
                ValueError,
                "Missing required field relatedParty",
            ),
            (
                "inv_order",
                None,
                _side_inv_order,
                ValueError,
                "Invalid orderId, the order does not exists",
            ),
            (
                "inv_product",
                None,
                _side_inv_product,
                ValueError,
                "Invalid productId, the contract does not exist",
            ),
        ]
    )
    def test_sdr_feeding(self, name, mod=None, side_effect=None, err_type=None, err_msg=None):
        sdr = deepcopy(BASIC_SDR)

        if mod is not None:
            mod(self, sdr)

        if side_effect is not None:
            side_effect(self)

        sdr_mng = sdr_manager.SDRManager()

        error = None
        try:
            sdr_mng.validate_sdr(sdr)
        except Exception as e:
            error = e

        if err_type is None:
            self.assertTrue(error is None)
            sdr_manager.Organization.objects.filter.assert_called_once_with(name="test_user")

            sdr_manager.Order.objects.get.assert_called_once_with(order_id="1")
            self._order.get_product_contract.assert_called_once_with("2")

            self.assertEquals(self._contract, sdr_mng._contract)
            self.assertEquals(self._order, sdr_mng._order)
            self.assertEquals(self._timestamp, sdr_mng._time_stamp)

            sdr_manager.User.objects.get.assert_called_once_with(username="test_user")
        else:
            self.assertTrue(isinstance(error, err_type))
            self.assertEquals(str(error), err_msg)

    def test_update_usage(self):
        sdr_mng = sdr_manager.SDRManager()
        sdr_mng._contract = self._contract
        sdr_mng._order = self._order
        sdr_mng._time_stamp = self._timestamp

        sdr_mng.update_usage()

        self.assertEquals(2, self._contract.correlation_number)
        self.assertEquals(self._timestamp, self._contract.last_usage)

        self._order.save.assert_called_once_with()


BASIC_USAGE = {
    "id": "3",
    "usageCharacteristic": [
        {"name": "orderId", "value": "2"},
        {"name": "ProductId", "value": "1"},
    ],
}

NON_PRODUCT_USAGE = {
    "usageCharacteristic": [
        {"name": "orderId", "value": "2"},
        {"name": "ProductId", "value": "2"},
    ]
}


class UsageClientTestCase(TestCase):
    tags = ("usage-client",)

    def setUp(self):
        usage_client.settings.USAGE = "http://example.com"
        usage_client.requests = MagicMock()
        self._old_inv = usage_client.settings.INVENTORY
        usage_client.settings.INVENTORY = "http://localhost:8080/DSProductInventory"

        self._customer = "test_customer"
        self._product_id = "1"

    def tearDown(self):
        usage_client.settings.INVENTORY = self._old_inv

    @parameterized.expand(
        [
            ("all_usages", [NON_PRODUCT_USAGE, BASIC_USAGE], [BASIC_USAGE]),
            (
                "filtered_by_state",
                [NON_PRODUCT_USAGE, BASIC_USAGE],
                [BASIC_USAGE],
                "&status=guided",
                "guided",
            ),
            ("product_not_found", [NON_PRODUCT_USAGE], []),
        ]
    )
    def test_retrieve_usage(self, name, response, exp_resp, extra_query="", state=None):
        # Create mocks
        mock_response = MagicMock()
        mock_response.json.return_value = response
        usage_client.requests.get.return_value = mock_response
        client = usage_client.UsageClient()

        cust_usage = client.get_customer_usage(self._customer, self._product_id, state=state)

        # Verify response
        self.assertEquals(exp_resp, cust_usage)

        # Verify calls
        usage_client.requests.get.assert_called_once_with(
            usage_client.settings.USAGE + "/usage?relatedParty.id=" + self._customer + extra_query,
            headers={"Accept": "application/json"},
        )

        mock_response.raise_for_status.assert_called_once_with()
        mock_response.json.assert_called_once_with()

    def _test_invalid_state(self, method, args, kwargs):
        error = None
        try:
            method(*args, **kwargs)
        except UsageError as e:
            error = e

        self.assertTrue(error is not None)
        self.assertEquals("UsageError: Invalid usage status invalid", str(error))

    def test_retrieve_usage_invalid_state(self):
        client = usage_client.UsageClient()
        self._test_invalid_state(
            client.get_customer_usage,
            (self._customer, self._product_id),
            {"state": "invalid"},
        )

    def _test_patch(self, expected_json, method, args):
        mock_response = MagicMock()
        usage_client.requests.patch.return_value = mock_response

        method(*args)

        # Verify calls
        usage_client.requests.patch.assert_called_once_with(
            usage_client.settings.USAGE + "/usage/" + BASIC_USAGE["id"],
            json=expected_json,
        )

        mock_response.raise_for_status.assert_called_once_with()

    def test_update_usage_state(self):
        # Create Mocks
        status = "rated"
        expected_json = {"status": status}
        client = usage_client.UsageClient()

        self._test_patch(expected_json, client.update_usage_state, (BASIC_USAGE["id"], status))

    def test_update_usage_invalid_state(self):
        client = usage_client.UsageClient()
        self._test_invalid_state(client.update_usage_state, (BASIC_USAGE["id"], "invalid"), {})

    def test_rate_usage(self):
        site = "http://example.com/"
        usage_client.settings.SITE = site

        timestamp = "2016-04-15"
        duty_free = "10"
        price = "12"
        rate = "20"
        currency = "EUR"
        product_url = "http://localhost:8080/DSProductInventory/api/productInventory/v2/product/" + self._product_id

        expected_json = {
            "status": "rated",
            "ratedProductUsage": [
                {
                    "ratingDate": timestamp,
                    "usageRatingTag": "usage",
                    "isBilled": False,
                    "ratingAmountType": "Total",
                    "taxIncludedRatingAmount": price,
                    "taxExcludedRatingAmount": duty_free,
                    "taxRate": rate,
                    "isTaxExempt": False,
                    "offerTariffType": "Normal",
                    "currencyCode": currency,
                    "productRef": product_url,
                }
            ],
        }

        client = usage_client.UsageClient()
        self._test_patch(
            expected_json,
            client.rate_usage,
            (
                BASIC_USAGE["id"],
                timestamp,
                duty_free,
                price,
                rate,
                currency,
                self._product_id,
            ),
        )
        reload(usage_client)


MANAGER_DENIED_RESP = {"result": "error", "error": "Permission denied"}

MANAGER_VALUE_RESP = {"result": "error", "error": "Value error"}


class SDRCollectionTestCase(TestCase):
    tags = ("sdr",)

    def setUp(self):
        views.Order = MagicMock()
        views.SDRManager = MagicMock()

        self._manager_inst = MagicMock()
        views.SDRManager.return_value = self._manager_inst

        usage_inst = MagicMock()
        views.UsageClient = MagicMock()
        views.UsageClient.return_value = usage_inst

        self.request = MagicMock()
        self.request.user.is_anonymous = False
        self.request.META.get.return_value = "application/json"
        self.request.GET.get.return_value = None

    def _inv_order(self):
        views.Order.objects.get.side_effect = Exception("Not found")

    def _inv_product(self):
        views.Order.objects.get().get_product_contract.side_effect = Exception("Not found")

    def _permission_denied(self):
        self._manager_inst.validate_sdr.side_effect = PermissionDenied("Permission denied")

    def _value_error(self):
        self._manager_inst.validate_sdr.side_effect = ValueError("Value error")

    def _exception(self):
        self._manager_inst.validate_sdr.side_effect = Exception("error")

    def _validate_response(self, response, exp_code, exp_response):
        # Validate response
        self.assertEquals(exp_code, response.status_code)
        body = json.loads(response.content)

        self.assertEquals(exp_response, body)

    @parameterized.expand(
        [
            ("correct", BASIC_SDR, 200, {"result": "correct", "message": "OK"}),
            (
                "invalid_json",
                "invalid",
                400,
                {
                    "result": "error",
                    "error": "The request does not contain a valid JSON object",
                },
            ),
            (
                "manager_permission_denied",
                BASIC_SDR,
                403,
                MANAGER_DENIED_RESP,
                _permission_denied,
            ),
            ("manager_value_error", BASIC_SDR, 422, MANAGER_VALUE_RESP, _value_error),
            (
                "manager_exception",
                BASIC_SDR,
                500,
                {
                    "result": "error",
                    "error": "The SDR document could not be processed due to an unexpected error",
                },
                _exception,
            ),
        ]
    )
    def test_feed_sdr(self, name, prov_data, exp_code, exp_response, side_effect=None):
        if isinstance(prov_data, dict):
            data = deepcopy(prov_data)
            data["id"] = "1"
            data = json.dumps(data)
        else:
            data = prov_data

        self.request.body = data

        if side_effect is not None:
            side_effect(self)

        collection = views.ServiceRecordCollection(permitted_methods=("POST",))
        response = collection.create(self.request)

        self._validate_response(response, exp_code, exp_response)
        if exp_code != 400:
            parsed_data = json.loads(data)
            if exp_code == 200:
                views.SDRManager.assert_called_once_with()
                self._manager_inst.validate_sdr.assert_called_once_with(parsed_data)
                views.UsageClient().update_usage_state.assert_called_once_with("1", "guided")
                self._manager_inst.update_usage.assert_called_once_with()
            else:
                views.UsageClient().update_usage_state.assert_called_once_with("1", "rejected")
                self.assertEquals(0, self._manager_inst.update_usage.call_count)
