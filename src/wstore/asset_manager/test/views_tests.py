# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
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

import io
import json
from importlib import reload

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.test import TestCase
from django.test.client import MULTIPART_CONTENT, RequestFactory
from mock import MagicMock
from parameterized import parameterized

from wstore.asset_manager import views
from wstore.asset_manager.errors import ProductError
from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.models import UserProfile
from wstore.store_commons.errors import ConflictError

RESOURCE_DATA = {
    "contentType": "application/zip",
    "content": {"name": "testfile.zip", "content": "content"},
}

BASIC_PRODUCT = {"action": "create", "product": {}}

MISSING_ACTION = {"product": {}}

MISSING_PRODUCT = {"action": "create"}


class AssetCollectionTestCase(TestCase):
    tags = ("asset-api",)

    def setUp(self):
        # Create request factory
        self.factory = RequestFactory()
        # Create testing user
        self.user = User.objects.create_user(username="test_user", email="", password="passwd")
        self.user.userprofile.get_current_roles = MagicMock(name="get_current_roles")
        self.user.userprofile.get_current_roles.return_value = ["provider", "customer"]
        self.user.userprofile.save()
        self.user.is_staff = False
        views.AssetManager = MagicMock()
        self.am_instance = MagicMock()
        views.AssetManager.return_value = self.am_instance
        views.User = MagicMock()
        views.User.objects.get.return_value = MagicMock()
        views.UserProfile = MagicMock()
        views.UserProfile.objets.get.return_value = MagicMock()
        views.UserProfile.objets.get().current_organization = "organization"

    @classmethod
    def tearDownClass(cls):
        reload(views)
        super(AssetCollectionTestCase, cls).tearDownClass()

    def _no_provider(self):
        self.user.userprofile.get_current_roles = MagicMock(name="get_current_roles")
        self.user.userprofile.get_current_roles.return_value = ["customer"]
        self.user.userprofile.save()

    def _anonymous(self):
        self.user = AnonymousUser()

    def _call_exception(self):
        self.am_instance.get_provider_assets_info.side_effect = Exception("Getting resources error")

    def _user_not_found(self):
        views.User.objects.get.side_effect = Exception("error")

    @parameterized.expand(
        [
            ([{"name": "test_resource", "provider": "test_user", "version": "1.0"}],),
            (
                [{"name": "test_resource", "provider": "test_user", "version": "1.0"}],
                None,
                200,
                None,
                None,
                "user",
            ),
            (
                [{"name": "test_resource", "provider": "test_user", "version": "1.0"}],
                None,
                200,
                None,
                {"offset": "1", "size": "1"},
            ),
            ([], _anonymous, 401, "Authentication required"),
            ([], _call_exception, 400, "Getting resources error"),
            (
                [],
                _user_not_found,
                404,
                "User user does not exist, error: error",
                None,
                "user",
            ),
        ]
    )
    def test_get_assets(
        self,
        return_value,
        side_effect=None,
        code=200,
        error_msg=None,
        pagination=None,
        user=None,
    ):
        # Mock get asset_manager method
        resource_collection = views.AssetCollection(permitted_methods=("GET",))

        self.am_instance.get_provider_assets_info.return_value = return_value

        path = "/api/offering/resources"

        if pagination is not None:
            path += "?offset=" + pagination["offset"] + "&size=" + pagination["size"]

        if user is not None:
            path += "{}user={}".format("&" if "?" in path else "?", user)

        request = self.factory.get(path, HTTP_ACCEPT="application/json")

        views.User.reset_mock()
        views.UserProfile.reset_mock()

        # Create the side effect if needed
        if side_effect:
            side_effect(self)

        request.user = self.user

        # Call the view
        response = resource_collection.read(request)

        self.assertEquals(response.status_code, code)
        self.assertEqual(response.get("Content-type"), "application/json; charset=utf-8")
        body_response = json.loads(response.content)

        if not error_msg:
            views.AssetManager.assert_called_once_with()
            if user is not None:
                views.User.objects.get.assert_called_with(username=user)
                views.UserProfile.objects.get.assert_called_with(user=views.User.objects.get())
            user_called = self.user.userprofile if user is None else views.UserProfile.objects.get()
            self.am_instance.get_provider_assets_info.assert_called_once_with(user_called, pagination=pagination)
            self.assertEquals(type(body_response), list)
            self.assertEquals(body_response, return_value)
        else:
            self.assertEqual(type(body_response), dict)
            self.assertEqual(body_response["error"], error_msg)
            self.assertEqual(body_response["result"], "error")

    def _not_found_asset(self):
        self.am_instance.get_asset_info.side_effect = ObjectDoesNotExist("Not found")

    def _call_exception_single(self):
        self.am_instance.get_asset_info.side_effect = Exception("Getting resources error")

    def _forbidden_asset(self):
        self.am_instance.get_asset_info.side_effect = PermissionDenied("Forbidden")

    @parameterized.expand(
        [
            ("basic", {"id": "1111"}, 200),
            (
                "not_found",
                {"error": "Not found", "result": "error"},
                404,
                _not_found_asset,
            ),
            (
                "exception",
                {"error": "An unexpected error occurred", "result": "error"},
                500,
                _call_exception_single,
            ),
            (
                "forbidden",
                {"error": "Forbidden", "result": "error"},
                403,
                _forbidden_asset,
            ),
        ]
    )
    def test_get_asset(self, name, exp_value, exp_code, side_effect=None, called=True):
        resource_entry = views.AssetEntry(permitted_methods=("GET",))
        self.am_instance.get_asset_info.return_value = exp_value

        if side_effect is not None:
            side_effect(self)

        request = self.factory.get("/charging/api/assetsManagement/assets/1111", HTTP_ACCEPT="application/json")
        request.user = self.user

        response = resource_entry.read(request, "1111")
        self.assertEquals(response.status_code, exp_code)
        self.assertEqual(response.get("Content-type"), "application/json; charset=utf-8")

        body_response = json.loads(response.content)
        self.assertEquals(body_response, exp_value)

        if called:
            self.am_instance.get_asset_info.assert_called_once_with("1111")
        else:
            self.assertEquals(self.am_instance.get_asset_info.call_count, 0)

    def _call_exception_product(self):
        self.am_instance.get_product_assets.side_effect = Exception("Getting resources error")

    def _forbidden_product(self):
        self.am_instance.get_product_assets.side_effect = PermissionDenied("Forbidden")

    @parameterized.expand(
        [
            ("basic", [{"id": "2345"}], 200),
            (
                "exception",
                {"error": "An unexpected error occurred", "result": "error"},
                500,
                _call_exception_product,
            ),
            (
                "forbidden",
                {"error": "Forbidden", "result": "error"},
                403,
                _forbidden_product,
            ),
        ]
    )
    def test_get_assets_product(self, name, exp_value, exp_code, side_effect=None, called=True):
        resource_entry = views.AssetEntryFromProduct(permitted_methods=("GET",))
        self.am_instance.get_product_assets.return_value = exp_value

        if side_effect is not None:
            side_effect(self)

        request = self.factory.get(
            "/charging/api/assetsManagement/assets/product/111",
            HTTP_ACCEPT="application/json",
        )

        response = resource_entry.read(request, "111")
        self.assertEquals(response.status_code, exp_code)
        self.assertEquals(response.get("Content-type"), "application/json; charset=utf-8")

        body_response = json.loads(response.content)
        self.assertEquals(body_response, exp_value)

        if called:
            self.am_instance.get_product_assets.assert_called_once_with("111")
        else:
            self.assertEquals(self.am_instance.get_product_assets.call_count, 0)

    def _no_provider_method(self, method):
        def side(ref):
            self._no_provider()

        return side

    def _creation_exception(self, method):
        def side(ref):
            method.side_effect = Exception("Resource creation exception")

        return side

    def _existing(self, method):
        def side(ref):
            method.side_effect = ConflictError("Resource exists")

        return side

    def _value_error(self, method):
        def side(ref):
            method.side_effect = ValueError("Error in some value")

        return side

    def _not_found(self, method):
        def side(ref):
            method.side_effect = ObjectDoesNotExist("Object not found")

        return side

    def _unauthorized(self, method):
        def side(ref):
            method.side_effect = PermissionDenied("Forbidden")

        return side

    def _test_post_api(
        self,
        collection,
        content,
        content_type,
        side_effect=None,
        code=201,
        validator=None,
        param=None,
    ):
        resource_collection = collection(permitted_methods=("POST",))

        # Build the request
        request = self.factory.post(
            "/api/offering/resources",
            content,
            content_type=content_type,
            HTTP_ACCEPT="application/json",
        )
        request.user = self.user

        # Create the side effect if needed
        if side_effect:
            side_effect(self)

        # Call the views
        if param is None:
            response = resource_collection.create(request)
        else:
            response = resource_collection.create(request, param)

        self.assertEqual(response.status_code, code)
        self.assertEqual(response.get("Content-type"), "application/json; charset=utf-8")
        body_response = json.loads(response.content)

        self.assertEqual(type(body_response), dict)
        validator(request, body_response)

    def _test_upload(
        self,
        mock_method,
        collection,
        data,
        file_,
        side_effect,
        error,
        code,
        msg,
        asset_id=None,
    ):
        content_type = "application/json"

        if file_:
            f = io.StringIO()
            f.name = "test_file.txt"
            f.write("test file")
            content = {"json": json.dumps(data), "file": f}
            content_type = MULTIPART_CONTENT
        else:
            content = json.dumps(data)

        resource = MagicMock()
        resource.pk = "123456"
        resource.get_url.return_value = "http://locationurl.com/"
        resource.get_uri.return_value = "http://uri.com/"
        mock_method.return_value = resource

        def validator(request, body_response):
            if not error:
                # Check correct call
                argv = (self.user, data) if asset_id is None else (asset_id, self.user, data)

                if not file_:
                    mock_method.assert_called_once_with(*argv)
                else:
                    expected_file = request.FILES["file"]
                    mock_method.assert_called_once_with(*argv, file_=expected_file)

                self.assertEquals(
                    body_response,
                    {
                        "contentType": "application/zip",
                        "content": "http://locationurl.com/",
                        "id": "123456",
                        "href": "http://uri.com/",
                    },
                )
            else:
                self.assertEqual(body_response, {"error": msg, "result": "error"})

        self._test_post_api(collection, content, content_type, side_effect, code, validator, asset_id)

    @parameterized.expand(
        [
            (RESOURCE_DATA,),
            (RESOURCE_DATA, True),
            (
                RESOURCE_DATA,
                False,
                _creation_exception,
                True,
                400,
                "Resource creation exception",
            ),
            (
                RESOURCE_DATA,
                True,
                _creation_exception,
                True,
                400,
                "Resource creation exception",
            ),
            (
                RESOURCE_DATA,
                True,
                _creation_exception,
                True,
                400,
                "Resource creation exception",
            ),
            (RESOURCE_DATA, True, _value_error, True, 422, "Error in some value"),
            (RESOURCE_DATA, True, _existing, True, 409, "Resource exists"),
            (RESOURCE_DATA, True, _not_found, True, 404, "Object not found"),
            (RESOURCE_DATA, True, _unauthorized, True, 403, "Forbidden"),
        ]
    )
    def test_upload_asset(self, data, file_=False, side_effect=None, error=False, code=200, msg="Created"):
        method_side_effect = None
        if side_effect is not None:
            method_side_effect = side_effect(self, self.am_instance.upload_asset)

        self._test_upload(
            self.am_instance.upload_asset,
            views.UploadCollection,
            data,
            file_,
            method_side_effect,
            error,
            code,
            msg,
        )

    @parameterized.expand(
        [
            (RESOURCE_DATA,),
            (RESOURCE_DATA, True),
            (
                RESOURCE_DATA,
                False,
                _creation_exception,
                True,
                400,
                "Resource creation exception",
            ),
            (
                RESOURCE_DATA,
                True,
                _creation_exception,
                True,
                400,
                "Resource creation exception",
            ),
            (
                RESOURCE_DATA,
                True,
                _creation_exception,
                True,
                400,
                "Resource creation exception",
            ),
            (RESOURCE_DATA, True, _value_error, True, 422, "Error in some value"),
            (RESOURCE_DATA, True, _existing, True, 409, "Resource exists"),
            (RESOURCE_DATA, True, _not_found, True, 404, "Object not found"),
            (RESOURCE_DATA, True, _unauthorized, True, 403, "Forbidden"),
        ]
    )
    def test_upgrade_asset(self, data, file_=False, side_effect=None, error=False, code=200, msg="Created"):
        method_side_effect = None
        if side_effect is not None:
            method_side_effect = side_effect(self, self.am_instance.upgrade_asset)

        self._test_upload(
            self.am_instance.upgrade_asset,
            views.UpgradeCollection,
            data,
            file_,
            method_side_effect,
            error,
            code,
            msg,
            "1",
        )

    def _prod_val_value_error(self):
        self.validator_instance.validate.side_effect = ValueError("Invalid value in product")

    def _prod_val_product_error(self):
        self.validator_instance.validate.side_effect = ProductError("Missing product information")

    def _prod_val_permission_denied(self):
        self.validator_instance.validate.side_effect = PermissionDenied("Permission denied")

    def _prod_val_conflict(self):
        self.validator_instance.validate.side_effect = ConflictError("Conflict")

    def _prod_val_plugin_error(self):
        self.validator_instance.validate.side_effect = PluginError("error")

    def _prod_val_exception(self):
        self.validator_instance.validate.side_effect = Exception("Unexpected error")

    @parameterized.expand(
        [
            ("basic", BASIC_PRODUCT),
            (
                "not_provider",
                BASIC_PRODUCT,
                _no_provider,
                True,
                403,
                "You don't have the seller role",
            ),
            (
                "invalid_content",
                "inv",
                None,
                True,
                400,
                "The content is not a valid JSON document",
            ),
            (
                "missing_action",
                MISSING_ACTION,
                None,
                True,
                400,
                "Missing required field: action",
            ),
            (
                "missing_product",
                MISSING_PRODUCT,
                None,
                True,
                400,
                "Missing required field: product",
            ),
            (
                "value_error",
                BASIC_PRODUCT,
                _prod_val_value_error,
                True,
                400,
                "Invalid value in product",
            ),
            (
                "product_error",
                BASIC_PRODUCT,
                _prod_val_product_error,
                True,
                400,
                "ProductError: Missing product information",
            ),
            (
                "permission_denied",
                BASIC_PRODUCT,
                _prod_val_permission_denied,
                True,
                403,
                "Permission denied",
            ),
            ("conflict", BASIC_PRODUCT, _prod_val_conflict, True, 409, "Conflict"),
            (
                "plugin_error",
                BASIC_PRODUCT,
                _prod_val_plugin_error,
                True,
                422,
                "Plugin Error: error",
            ),
            (
                "exception",
                BASIC_PRODUCT,
                _prod_val_exception,
                True,
                500,
                "An unexpected error has occurred",
            ),
        ]
    )
    def test_validate_resource(self, name, data, side_effect=None, error=False, code=200, msg="OK"):
        views.ProductValidator = MagicMock()
        self.validator_instance = MagicMock()
        views.ProductValidator.return_value = self.validator_instance

        if isinstance(data, dict):
            content = json.dumps(data)
        else:
            content = data

        def validator(request, body_response):
            if not error:
                self.assertEqual(body_response["message"], msg)
                views.ProductValidator.assert_called_once_with()
                self.assertEqual(body_response["result"], "correct")
                self.validator_instance.validate.assert_called_once_with(
                    data["action"],
                    self.user.userprofile.current_organization,
                    data["product"],
                )
            else:
                self.assertEqual(body_response["error"], msg)
                self.assertEqual(body_response["result"], "error")

        self._test_post_api(
            views.ValidateCollection,
            content,
            "application/json",
            side_effect,
            code,
            validator,
        )

    def test_validate_offering(self):
        # Only the basic call is tested since the aux method used for processing the request has been already tested
        views.OfferingValidator = MagicMock()
        off_validator = MagicMock()
        views.OfferingValidator.return_value = off_validator

        data = json.dumps({"action": "create", "offering": {}})

        def validator(request, body_response):
            views.OfferingValidator.assert_called_once_with()
            self.assertEquals(body_response, {"result": "correct", "message": "OK"})
            off_validator.validate.assert_called_once_with("create", self.user.userprofile.current_organization, {})

        self._test_post_api(
            views.ValidateOfferingCollection,
            data,
            "application/json",
            None,
            200,
            validator,
        )
