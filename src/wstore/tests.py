# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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

from bson import ObjectId
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from mock import MagicMock, call, patch
from parameterized import parameterized
from requests.exceptions import HTTPError, Timeout

from wstore.ordering.errors import InventoryError

from wstore import views
from wstore.admin.users.tests import *
from wstore.store_commons.tests import *


@override_settings(
    MEDIA_ROOT="/home/test/media/", MEDIA_URL="/media/", MEDIA_DIR="media/", USE_XSENDFILE=False, CUSTOMER_ROLE="Buyer"
)
class ServeMediaTestCase(TestCase):
    tags = ("media",)

    _resource_path = "media/assets/test_user/widget.wgt"
    _expected_file = "assets/test_user/widget.wgt"
    _file_id = "507f1f77bcf86cd799439011"
    _customer_id = "urn:ngsi-ld:organization:customer-1"

    def setUp(self):
        for name in ("Organization", "Resource", "ResourcePlugin", "Order", "serve", "smart_str"):
            patcher = patch.object(views, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

        self.inventory_patch = patch.object(views, "InventoryClient")
        self.inventory = self.inventory_patch.start()
        self.addCleanup(self.inventory_patch.stop)
        self.client = self.inventory.return_value
        file_patcher = patch.object(views.os.path, "isfile", return_value=True)
        self.file_exists = file_patcher.start()
        self.addCleanup(file_patcher.stop)

        self._user = MagicMock(is_anonymous=False)
        self._org = SimpleNamespace(actor_id="provider-party", name="test_user")
        self._user.userprofile.current_organization = self._org
        self.Organization.objects.get.return_value = self._org
        self._asset_inst = MagicMock(pk=ObjectId(self._file_id), is_public=False, provider=self._org)
        self.Resource.objects.filter.return_value = [self._asset_inst]
        self.ResourcePlugin.objects.filter.return_value.exists.return_value = True
        self.Order.objects.get.return_value.owner_organization = self._org
        self.smart_str.return_value = "smart string"

        self.service = {
            "id": "service-1",
            "state": "reserved",
            "serviceCharacteristic": [
                {"name": "Service Type", "value": "file-category"},
                {"name": "File", "value": self._file_id},
            ],
        }
        self.product = {
            "id": "product-1",
            "status": "active",
            "realizingService": [{"id": "service-1"}],
            "relatedParty": [{"id": self._customer_id, "role": views.settings.CUSTOMER_ROLE}],
        }
        self.client.iter_services.return_value = [self.service]
        self.client.iter_products.return_value = [self.product]

    def _request(self, path="assets/test_user", name="widget.wgt"):
        self.request = RequestFactory().get("/charging/media/" + path + "/" + name)
        self.request.user = self._user
        return views.ServeMedia(permitted_methods=("GET",)).read(self.request, path, name)

    def _validate_res_call(self):
        self.Resource.objects.filter.assert_called_once_with(resource_path=self._resource_path)
        self.Order.objects.get.assert_not_called()

    def _validate_inventory_call(self):
        self._validate_res_call()
        self.client.iter_services.assert_called_once_with(query={"serviceCharacteristic.value": self._file_id})
        self.client.iter_products.assert_called_once_with(
            query={
                "realizingService.id": "service-1",
                "relatedParty.id": self._customer_id,
                "status": "active",
            }
        )
        self.ResourcePlugin.objects.filter.assert_called_once_with(category_id="file-category", type="service", requires_file=True)

    def _validate_upgrading_call(self):
        self.assertEqual(
            [
                call(resource_path=self._resource_path),
                call(state="upgrading", provider=self._org),
            ],
            self.Resource.objects.filter.call_args_list,
        )
        self.Organization.objects.get.assert_called_once_with(name="test_user")

    def _validate_order_call(self):
        self.Order.objects.get.assert_called_once_with(pk="111111111111111111111111")
        self.Resource.objects.get.assert_not_called()

    def _validate_empty_call(self):
        self.Resource.objects.get.assert_not_called()
        self.Order.objects.get.assert_not_called()

    def _validate_error(self, response, expected):
        self.assertEqual(expected[0], response.status_code)
        self.assertEqual(expected[1], json.loads(response.content))
        self.serve.assert_not_called()

    def _validate_serve(self, response, expected):
        self.file_exists.assert_called_once_with("/home/test/media/" + expected)
        self.serve.assert_called_once_with(self.request, expected, document_root="/home/test/media/")

    def _validate_xfile(self, response, expected):
        self.file_exists.assert_called_once_with("/home/test/media/" + expected)
        self.smart_str.assert_called_once_with(expected)
        self.assertEqual("smart string", response["X-Sendfile"])

    def _public_asset(self):
        self._asset_inst.is_public = True
        self._asset_inst.provider = SimpleNamespace(actor_id="other-provider")

    def _usexfiles(self):
        override = override_settings(USE_XSENDFILE=True)
        override.enable()
        self.addCleanup(override.disable)

    def _asset_error(self):
        self.Resource.objects.filter.return_value = []

    def _order_error(self):
        self.Order.objects.get.side_effect = Exception("Not found")

    def _unauthorized(self):
        self._acquired()
        self.client.iter_products.return_value = []

    def _not_loged(self):
        self._user.is_anonymous = True

    def _not_found(self):
        self.file_exists.return_value = False

    def _acquired(self):
        self._user.userprofile.current_organization = SimpleNamespace(actor_id=self._customer_id, name="buyer")

    def _bundle_acquired(self):
        self._acquired()
        self.product["realizingService"].insert(0, {"id": "other-service"})

    def _product_bundle_acquired(self):
        self._bundle_acquired()
        self.product["isBundle"] = True

    def _upgrading(self):
        self._asset_inst.old_versions = [MagicMock(resource_path=self._resource_path)]
        self.Resource.objects.filter.side_effect = [[], [MagicMock(old_versions=[]), self._asset_inst]]

    @parameterized.expand(
        [
            ("asset", "assets/test_user", "widget.wgt", _validate_res_call, _validate_serve, _expected_file),
            (
                "asset_acquired",
                "assets/test_user",
                "widget.wgt",
                _validate_inventory_call,
                _validate_serve,
                _expected_file,
                _acquired,
            ),
            (
                "asset_in_bundle",
                "assets/test_user",
                "widget.wgt",
                _validate_inventory_call,
                _validate_serve,
                _expected_file,
                _bundle_acquired,
            ),
            (
                "asset_in_product_bundle",
                "assets/test_user",
                "widget.wgt",
                _validate_inventory_call,
                _validate_serve,
                _expected_file,
                _product_bundle_acquired,
            ),
            (
                "public_asset",
                "assets/test_user",
                "widget.wgt",
                _validate_res_call,
                _validate_serve,
                _expected_file,
                _public_asset,
            ),
            (
                "upgrading_asset",
                "assets/test_user",
                "widget.wgt",
                _validate_upgrading_call,
                _validate_serve,
                _expected_file,
                _upgrading,
            ),
            (
                "invoice",
                "bills",
                "111111111111111111111111_userbill.pdf",
                _validate_order_call,
                _validate_xfile,
                "bills/111111111111111111111111_userbill.pdf",
                _usexfiles,
            ),
            (
                "asset_not_found",
                "assets/test_user",
                "widget.wgt",
                _validate_upgrading_call,
                _validate_error,
                (404, {"result": "error", "error": "The specified asset does not exists"}),
                _asset_error,
            ),
            (
                "asset_anonymous",
                "assets/test_user",
                "widget.wgt",
                _validate_res_call,
                _validate_error,
                (401, {"result": "error", "error": "You must be authenticated to download the specified asset"}),
                _not_loged,
            ),
            (
                "asset_unauthorized",
                "assets/test_user",
                "widget.wgt",
                _validate_res_call,
                _validate_error,
                (403, {"result": "error", "error": "You are not authorized to download the specified asset"}),
                _unauthorized,
            ),
            (
                "invoice_not_found",
                "bills",
                "111111111111111111111111_userbill.pdf",
                _validate_order_call,
                _validate_error,
                (404, {"result": "error", "error": "The specified invoice does not exists"}),
                _order_error,
            ),
            (
                "invoice_anonymous",
                "bills",
                "111111111111111111111111_userbill.pdf",
                _validate_empty_call,
                _validate_error,
                (401, {"result": "error", "error": "You must provide credentials for downloading invoices"}),
                _not_loged,
            ),
            (
                "invoice_unauthorized",
                "bills",
                "111111111111111111111111_userbill.pdf",
                _validate_order_call,
                _validate_error,
                (403, {"result": "error", "error": "You are not authorized to download the specified invoice"}),
                _unauthorized,
            ),
            (
                "file_not_found",
                "assets/test_user",
                "widget.wgt",
                _validate_res_call,
                _validate_error,
                (404, {"result": "error", "error": "Resource not found"}),
                _not_found,
            ),
            (
                "invalid_type",
                "invalid/user",
                "widget.wgt",
                _validate_empty_call,
                _validate_error,
                (404, {"result": "error", "error": "Resource not found"}),
            ),
        ]
    )
    def test_serve_media(self, name, path, file_name, call_validator, res_validator, expected, side_effect=None):
        if side_effect is not None:
            side_effect(self)

        response = self._request(path, file_name)
        call_validator(self)
        res_validator(self, response, expected)

    def test_owner_and_public_downloads_do_not_query_inventory(self):
        self._request()
        self.inventory.assert_not_called()
        self._public_asset()
        self._not_loged()
        self._request()
        self.inventory.assert_not_called()

    def test_file_name_and_value_must_belong_to_the_same_characteristic(self):
        self._acquired()
        self.service["serviceCharacteristic"] = [
            {"name": "Service Type", "value": "file-category"},
            {"name": "File", "value": "another-file"},
            {"name": "endpoint", "value": self._file_id},
        ]
        self.assertEqual(403, self._request().status_code)
        self.client.iter_products.assert_not_called()
        self.ResourcePlugin.objects.filter.assert_not_called()

    def test_party_id_and_customer_role_must_belong_to_the_same_party(self):
        self._acquired()
        self.product["relatedParty"] = [
            {"id": self._customer_id, "role": "Seller"},
            {"id": "another-organization", "role": views.settings.CUSTOMER_ROLE},
        ]
        self.assertEqual(403, self._request().status_code)
        self.serve.assert_not_called()

    def test_actual_product_status_and_service_reference_are_checked(self):
        self._acquired()
        for status in ("created", "pendingActive", "suspended", "terminated", None):
            with self.subTest(status=status):
                self.product["status"] = status
                self.assertEqual(403, self._request().status_code)

        self.product["status"] = "active"
        self.product["realizingService"] = [{"id": "another-service"}]
        self.assertEqual(403, self._request().status_code)
        self.serve.assert_not_called()

    def test_characteristic_names_and_customer_role_are_case_insensitive(self):
        self._acquired()
        self.service["serviceCharacteristic"][0]["name"] = " service TYPE "
        self.service["serviceCharacteristic"][1]["name"] = "file"
        self.product["relatedParty"][0]["role"] = views.settings.CUSTOMER_ROLE.lower()
        self._request()
        self.serve.assert_called_once()

    @override_settings(CUSTOMER_ROLE="Purchaser")
    def test_configured_customer_role_is_required(self):
        self._acquired()

        for role in ("Customer", "Buyer", "Seller"):
            with self.subTest(role=role):
                self.product["relatedParty"][0]["role"] = role
                self.assertEqual(403, self._request().status_code)

        self.product["relatedParty"][0]["role"] = "pUrChAsEr"
        self._request()
        self.serve.assert_called_once()

    def test_other_party_ids_and_missing_customer_roles_do_not_grant_access(self):
        self._acquired()
        for parties in (
            [{"id": "another-customer", "role": views.settings.CUSTOMER_ROLE}],
            [{"id": self._customer_id}],
            [],
        ):
            with self.subTest(parties=parties):
                self.product["relatedParty"] = parties
                self.assertEqual(403, self._request().status_code)
        self.serve.assert_not_called()

    def test_no_party_id_does_not_query_inventory(self):
        self._acquired()
        self._user.userprofile.current_organization.actor_id = None
        self.assertEqual(403, self._request().status_code)
        self.inventory.assert_not_called()

    def test_non_file_plugins_and_services_without_service_type_do_not_grant_access(self):
        self._acquired()
        self.ResourcePlugin.objects.filter.return_value.exists.return_value = False
        self.assertEqual(403, self._request().status_code)
        self.service["serviceCharacteristic"].pop(0)
        self.ResourcePlugin.objects.filter.reset_mock()
        self.assertEqual(403, self._request().status_code)
        self.client.iter_products.assert_not_called()
        self.ResourcePlugin.objects.filter.assert_not_called()

    def test_false_positive_services_are_skipped_before_product_queries(self):
        self._acquired()
        false_positive = deepcopy(self.service)
        false_positive["id"] = "wrong-service"
        false_positive["serviceCharacteristic"][1] = {"name": "endpoint", "value": self._file_id}
        self.client.iter_services.return_value = [false_positive, self.service]
        self._request()
        self._validate_inventory_call()
        self.serve.assert_called_once()

    def test_later_matching_service_and_product_can_grant_access(self):
        self._acquired()
        second_service = deepcopy(self.service)
        second_service["id"] = "service-2"
        wrong_product = deepcopy(self.product)
        wrong_product["relatedParty"] = [{"id": self._customer_id, "role": "Seller"}]
        self.product["realizingService"] = [{"id": "service-2"}]
        self.client.iter_services.return_value = [self.service, second_service]
        self.client.iter_products.side_effect = [[wrong_product], [wrong_product, self.product]]
        self._request()
        self.assertEqual(2, self.client.iter_products.call_count)
        self.serve.assert_called_once()

    def test_inventory_failures_do_not_serve_the_file(self):
        self._acquired()
        for method in (self.client.iter_services, self.client.iter_products):
            for error in (
                HTTPError("offline"),
                Timeout("timeout"),
                ValueError("invalid JSON"),
                InventoryError("invalid response"),
            ):
                with self.subTest(method=method, error=error):
                    method.side_effect = error
                    self.assertEqual(503, self._request().status_code)
                    method.side_effect = None
        self.serve.assert_not_called()

    @patch("wstore.ordering.inventory_client.requests.get")
    def test_real_inventory_client_queries_and_post_filters_api_results(self, get):
        self._acquired()
        self.inventory_patch.stop()
        bad_service = deepcopy(self.service)
        bad_service["id"] = "wrong-service"
        bad_service["serviceCharacteristic"][1] = {"name": "unrelated", "value": self._file_id}
        bad_product = deepcopy(self.product)
        bad_product["relatedParty"] = [
            {"id": self._customer_id, "role": "Seller"},
            {"id": "another-customer", "role": views.settings.CUSTOMER_ROLE},
        ]
        service_response = MagicMock()
        service_response.json.side_effect = [[bad_service] * 100, [self.service]]
        product_response = MagicMock()
        product_response.json.side_effect = [[bad_product] * 100, [self.product]]
        get.side_effect = [service_response, service_response, product_response, product_response]

        self._request()

        self.assertEqual(4, get.call_count)
        self.assertEqual([0, 100, 0, 100], [c.kwargs["params"]["offset"] for c in get.call_args_list])
        self.assertEqual(
            {"serviceCharacteristic.value": self._file_id, "offset": 0, "limit": 100},
            get.call_args_list[0].kwargs["params"],
        )
        self.assertEqual(
            {
                "realizingService.id": "service-1",
                "relatedParty.id": self._customer_id,
                "status": "active",
                "offset": 0,
                "limit": 100,
            },
            get.call_args_list[2].kwargs["params"],
        )
        self.serve.assert_called_once()
