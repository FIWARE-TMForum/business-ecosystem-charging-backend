# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
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


from importlib import reload

from bson import ObjectId
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.test.utils import override_settings
from mock import MagicMock, call
from parameterized import parameterized

from wstore.store_commons import database, middleware, rollback
from wstore.store_commons.utils.url import is_valid_url

__test__ = False


@override_settings(
    ADMIN_ROLE="provider",
    PROVIDER_ROLE="seller",
    CUSTOMER_ROLE="customer",
    PROPAGATE_TOKEN=True,
)
class AuthenticationMiddlewareTestCase(TestCase):
    tags = ("middleware",)

    def setUp(self):
        self.request = MagicMock()
        self.request.META = {
            "HTTP_X_ACTOR_ID": "test-user",
            "HTTP_X_DISPLAY_NAME": "Test user",
            "HTTP_X_USER_ID": "test-user",
        }

        self._user_model = MagicMock()
        self._user_inst = MagicMock()
        self._user_inst.username = "test-user"
        self._user_model.objects.get.return_value = self._user_inst
        self._user_model.objects.create.return_value = self._user_inst

        import wstore.models

        wstore.models.User = self._user_model

        self._org_model = MagicMock()
        self._org_instance = MagicMock()
        self._org_instance.pk = "org"
        self._org_model.objects.get.return_value = self._org_instance
        self._org_model.objects.create.return_value = self._org_instance

        wstore.models.Organization = self._org_model

    def tearDown(self):
        import wstore.models

        reload(wstore.models)

    def _new_user(self):
        self._user_model.objects.get.side_effect = Exception("Not found")

    def _missing_header(self):
        self.request.META = {}

    def _missing_token(self):
        del self.request.META["HTTP_AUTHORIZATION"]

    def _invalid_token(self):
        self.request.META["HTTP_AUTHORIZATION"] = "1234567890abcdf"

    def _missing_email(self):
        del self.request.META["HTTP_X_EMAIL"]

    @parameterized.expand(
        [
            ("basic", "provider,seller,", True, ["provider"]),
            ("customer", "customer", False, ["customer"]),
            ("new_user", "seller", False, ["provider"], _new_user),
            ("empty", "", False, []),
            ("missing_header", "", False, [], _missing_header, False, True),
            ("missing_token", "", False, [], _missing_token, False, True),
            ("missing_email", "", False, [], _missing_email, False, True),
            ("invalid_token", "", False, [], _invalid_token, False, True),
        ]
    )
    def test_get_api_user(
        self,
        name,
        roles,
        staff,
        expected_roles,
        side_effect=None,
        created=False,
        anonymous=False,
    ):
        self.request.META["HTTP_X_ROLES"] = roles
        self.request.META["HTTP_AUTHORIZATION"] = "Bearer 1234567890abcdf"
        self.request.META["HTTP_X_EMAIL"] = "user@email.com"
        self.request.META["HTTP_X_EXT_NAME"] = "user"
        self.request.META["HTTP_X_IDP_ID"] = "local"
        self.request.META["HTTP_X_PARTY_ID"] = "urn:party:local:test-user"
        self.request.META["HTTP_X_USER_PARTY_ID"] = "urn:party:local:test-user"

        if side_effect is not None:
            side_effect(self)

        response = MagicMock()

        def get_response(request):
            return response

        middleware_class = middleware.AuthenticationMiddleware(get_response)
        resp = middleware_class(self.request)
        user = self.request.user

        self.assertEqual(response, resp)

        if not anonymous:
            self.assertEquals(self._user_inst, user)

            # Check user info
            if not created:
                self._user_model.objects.get.assert_called_once_with(username="test-user")
            else:
                self._user_model.objects.create.assert_called_once_with(username="test-user")

            self.assertEquals(self._user_inst.is_staff, staff)

            self._org_model.objects.get.assert_called_once_with(name="test-user")

            self.assertEquals("user@email.com", self._user_inst.email)
            self.assertEquals("1234567890abcdf", self._user_inst.userprofile.access_token)
            self.assertEquals("Test user", self._user_inst.userprofile.complete_name)
            self.assertEquals("urn:party:local:test-user", self._user_inst.userprofile.actor_id)

            self.assertEquals(expected_roles, self._user_inst.userprofile.current_roles)
            self.assertEquals(self._org_instance, self._user_inst.userprofile.current_organization)

            self.assertEqual("local", self._org_instance.idp)

            self._org_instance.save.assert_called_once_with()
            self._user_inst.userprofile.save.assert_called_once_with()
            self._user_inst.save.assert_called_once_with()

        else:
            self.assertEquals(AnonymousUser(), user)

    @override_settings(
        ADMIN_ROLE="provider",
        PROVIDER_ROLE="seller",
        CUSTOMER_ROLE="customer",
        PROPAGATE_TOKEN=False,
    )
    def test_get_api_user_no_token(self):
        self.request.META = {
            "HTTP_X_ACTOR_ID": "000000000000023",
            "HTTP_X_DISPLAY_NAME": "Test Org",
            "HTTP_X_USER_ID": "test-user",
            "HTTP_X_ROLES": "customer",
            "HTTP_X_EMAIL": "org@email.com",
            "HTTP_X_EXT_NAME": "",
            "HTTP_X_IDP_ID": "local",
            "HTTP_X_PARTY_ID": "urn:party:local:test-org",
            "HTTP_X_USER_PARTY_ID": "urn:party:local:test-user"
        }

        response = MagicMock()

        def get_response(request):
            return response

        middleware_class = middleware.AuthenticationMiddleware(get_response)
        resp = middleware_class(self.request)
        user = self.request.user

        self.assertEquals(self._user_inst, user)
        self.assertEquals("token", self._user_inst.userprofile.access_token)

    def test_get_api_user_org(self):
        self.request.META = {
            "HTTP_X_ACTOR_ID": "000000000000023",
            "HTTP_X_DISPLAY_NAME": "Test Org",
            "HTTP_X_USER_ID": "test-user",
            "HTTP_X_ROLES": "customer",
            "HTTP_AUTHORIZATION": "Bearer 1234567890abcdf",
            "HTTP_X_EMAIL": "org@email.com",
            "HTTP_X_EXT_NAME": "",
            "HTTP_X_IDP_ID": "local",
            "HTTP_X_PARTY_ID": "urn:party:local:test-org",
            "HTTP_X_USER_PARTY_ID": "urn:party:local:test-user"
        }
        self._org_model.objects.get.side_effect = Exception("Not found")

        response = MagicMock()

        def get_response(request):
            return response

        middleware_class = middleware.AuthenticationMiddleware(get_response)
        resp = middleware_class(self.request)
        user = self.request.user

        self.assertEquals(self._user_inst, user)
        self._org_model.objects.create.assert_called_once_with(name="000000000000023")

        self.assertEquals(["customer"], self._user_inst.userprofile.current_roles)
        self.assertEquals(self._org_instance, self._user_inst.userprofile.current_organization)

        self.assertFalse(self._org_instance.private)
        self.assertEqual("urn:party:local:test-org", self._org_instance.actor_id)
        self.assertEqual("local", self._org_instance.idp)

        self._org_instance.save.assert_called_once_with()
        self._user_inst.userprofile.save.assert_called_once_with()


@override_settings(BASEDIR="/base/dir")
class RollbackTestCase(TestCase):
    tags = ("rollback",)

    def setUp(self):
        self._old_exists = rollback.os.path.exists
        rollback.os.path.exists = MagicMock()

    def tearDown(self):
        rollback.os.path.exists = self._old_exists

    def test_rollback_correct(self):
        called_method = MagicMock()
        called_method.return_value = "Returned"

        wrap = rollback.rollback()
        wrapper = wrap(called_method)

        ref = MagicMock()

        value = wrapper(ref, "value")

        called_method.assert_called_once_with(ref, "value")
        self.assertEquals("Returned", value)
        self.assertEquals({"files": [], "models": []}, ref.rollback_logger)

    @parameterized.expand(
        [
            ("with_post", True),
            ("without_post", False),
        ]
    )
    def test_rollback_exception(self, name, has_post):
        model = MagicMock()

        post_action = None
        if has_post:
            post_action = MagicMock()

        rollback.os = MagicMock()

        def called_method(ref):
            ref.rollback_logger["files"].append("/home/test/testfile.pdf")
            ref.rollback_logger["models"].append(model)
            raise ValueError("Value error")

        wrap = rollback.rollback(post_action=post_action)
        wrapper = wrap(called_method)

        wrapper_ref = MagicMock()
        error = False
        try:
            wrapper(wrapper_ref)
        except ValueError as e:
            error = True
            self.assertEquals("Value error", str(e))

        self.assertTrue(error)
        rollback.os.remove.assert_called_once_with("/home/test/testfile.pdf")
        model.delete.assert_called_once_with()

        if has_post:
            post_action.assert_called_once_with(wrapper_ref)

    def _not_exists(self):
        rollback.os.path.exists.return_value = False

    def _to_remove(self):
        rollback.os.path.exists.return_value = True

    def _exists_not_called(self):
        self.assertEquals(0, rollback.os.path.exists.call_count)

    def _exists_called(self):
        rollback.os.path.exists.assert_called_once_with("/base/dir/new/path")
        self.assertEquals(0, rollback.os.remove.call_count)

    def _remove_called(self):
        rollback.os.path.exists.assert_called_once_with("/base/dir/new/path")
        rollback.os.remove.assert_called_once_with("/base/dir/new/path")

    @parameterized.expand(
        [
            ("no_path", "", _exists_not_called),
            ("file_not_found", "new/path", _exists_called, _not_exists),
            ("to_remove", "new/path", _remove_called, _to_remove),
        ]
    )
    def test_downgrade_post_action(self, name, res_path, check, side_effect=None):
        rollback.os = MagicMock()

        if side_effect is not None:
            side_effect(self)

        asset = MagicMock(
            resource_path=res_path,
            download_link="http://host/new/path",
            content_type="new_type",
            version="2.0",
            state="upgrading",
            old_versions=[
                MagicMock(
                    resource_path="old/path",
                    download_link="http://host/old/path",
                    content_type="old_type",
                    version="1.0",
                )
            ],
        )
        downgrade_object = MagicMock(_to_downgrade=asset)

        rollback.downgrade_asset_pa(downgrade_object)

        self.assertEquals("old/path", asset.resource_path)
        self.assertEquals("http://host/old/path", asset.download_link)
        self.assertEquals("old_type", asset.content_type)
        self.assertEquals("1.0", asset.version)
        self.assertEquals([], asset.old_versions)

        asset.save.assert_called_once_with()
        check(self)

    def test_downgrade_post_action_none(self):
        downgrade_object = MagicMock(_to_downgrade=None)

        rollback.downgrade_asset_pa(downgrade_object)

    def test_downgrade_post_action_not_defined(self):
        class manager:
            pass

        rollback.downgrade_asset_pa(manager())


class DocumentLockTestCase(TestCase):
    tags = ("lock",)

    _id = "59f76ace051eb500613cbbc7"
    _collection = "test_collection"
    _lock_id = "_lock_test"

    def setUp(self):
        self._connection = MagicMock()
        database.get_database_connection = MagicMock(return_value=self._connection)

    def test_wait_for_document(self):
        self._connection[self._collection].find_one_and_update.side_effect = [
            {self._lock_id: True},
            {self._lock_id: False},
        ]

        lock = database.DocumentLock(self._collection, self._id, "test")
        lock.wait_document()

        # Check database calls
        self.assertEquals(
            [
                call({"_id": self._id}, {"$set": {self._lock_id: True}}),
                call({"_id": self._id}, {"$set": {self._lock_id: True}}),
            ],
            self._connection[self._collection].find_one_and_update.call_args_list,
        )

    def test_unlock_document(self):
        lock = database.DocumentLock(self._collection, self._id, "test")
        lock.unlock_document()

        # Check database calls
        self._connection[self._collection].find_one_and_update.assert_called_once_with(
            {"_id": self._id}, {"$set": {self._lock_id: False}}
        )


class URLUtilsTestCase(TestCase):
    tags = ("utils", "url-utils")

    def test_invalid_url_protocol(self):
        self.assertFalse(is_valid_url("sftp://localhost/"))

    def test_invalid_url_number(self):
        self.assertFalse(is_valid_url(1))

    def test_invalid_url_list(self):
        self.assertFalse(is_valid_url(("sftp://localhost@c",)))

    def test_invalid_url_relative(self):
        self.assertFalse(is_valid_url("/my/path"))

    def test_invalid_url_relative_schema(self):
        self.assertFalse(is_valid_url("//my/path"))

    def test_invalid_characters(self):
        self.assertFalse(is_valid_url("http://data.source.commy/path a"))

    def test_valid_absolute_url_http(self):
        self.assertTrue(is_valid_url("http://data.source.commy/path"))

    def test_valid_absolute_url_http_port(self):
        self.assertTrue(is_valid_url("http://data.source.commy:5000/path"))

    def test_valid_absolute_url_http_query(self):
        self.assertTrue(is_valid_url("http://data.source.commy/path?a=b"))

    def test_valid_absolute_url_https(self):
        self.assertTrue(is_valid_url("https://data.source.commy/path"))

    def test_valid_absolute_url_https_port(self):
        self.assertTrue(is_valid_url("https://data.source.commy:300/path"))

    def test_valid_absolute_url_https_query(self):
        self.assertTrue(is_valid_url("https://data.source.commy/path?a=b"))

    def test_valid_absolute_url_https_ckan(self):
        self.assertTrue(is_valid_url("https://data.opplafy.eu/dataset/4d3d9728-39bb-4749-8c8f-d9cea51abe4b"))
