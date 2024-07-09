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


from copy import deepcopy
from importlib import reload
from urllib.parse import quote

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.test.utils import override_settings
from mock import MagicMock, mock_open
from parameterized import parameterized

from wstore.asset_manager import asset_manager, models
from wstore.asset_manager.test.resource_test_data import *
from wstore.store_commons.errors import ConflictError
from wstore.store_commons.utils.testing import decorator_mock


class ResourceRetrievingTestCase(TestCase):
    tags = ("asset-manager",)

    def _mock_resource(self, info, provider):
        # Mock resource model
        resource = MagicMock()
        resource.pk = info["pk"]
        resource.provider = provider
        resource.version = info["version"]
        resource.content_type = info["content_type"]
        resource.state = info["state"]
        resource.download_link = info["download_link"]
        resource.resource_type = info["type"]
        resource.meta_info = {}

        resource.get_url.return_value = info["download_link"]
        resource.get_uri.return_value = info["uri"]

        return resource

    def setUp(self):
        self.user = MagicMock()
        self.org = MagicMock()
        self.user.userprofile.current_organization = self.org

        asset_manager.Resource = MagicMock()

        asset_manager.Resource.objects.filter.return_value = [self._mock_resource(r, self.org) for r in EXISTING_INFO]
        asset_manager.Resource.objects.get.return_value = self._mock_resource(EXISTING_INFO[0], self.org)
    
    @classmethod
    def tearDownClass(cls):
        # Restore resource model
        reload(asset_manager)
        super(ResourceRetrievingTestCase, cls).tearDownClass()

    def validate_response(self, result, expected_result, error, err_type, err_msg):
        if err_type is None:
            # Assert that no error occurs
            self.assertEquals(error, None)
            # Check result
            self.assertEquals(result, expected_result)
        else:
            self.assertTrue(isinstance(error, err_type))
            self.assertEquals(str(error), err_msg)

    @parameterized.expand(
        [
            ([RESOURCE_DATA1, RESOURCE_DATA2, RESOURCE_DATA3, RESOURCE_DATA4],),
            ([RESOURCE_DATA1], {"offset": 0, "size": 1}),
            ([RESOURCE_DATA2, RESOURCE_DATA3], {"offset": 1, "size": 2}),
            ([], {"offset": 5}, ValueError, "Missing required parameter in pagination"),
            ([], {"size": 8}, ValueError, "Missing required parameter in pagination"),
            ([], {"offset": -1, "size": 8}, ValueError, "Invalid pagination limits"),
            ([], {"offset": 1, "size": 0}, ValueError, "Invalid pagination limits"),
            ([], {"offset": 5, "size": -1}, ValueError, "Invalid pagination limits"),
            ([], {"offset": -6, "size": 2}, ValueError, "Invalid pagination limits"),
            ([], {"offset": -1, "size": 0}, ValueError, "Invalid pagination limits"),
        ]
    )
    def test_resource_retrieving(self, expected_result, pagination=None, err_type=None, err_msg=None):
        # Call the method
        error = None
        result = None
        try:
            am = asset_manager.AssetManager()
            result = am.get_provider_assets_info(self.user, pagination)
        except Exception as e:
            error = e

        self.validate_response(result, expected_result, error, err_type, err_msg)

    def _not_found(self):
        asset_manager.Resource.objects.get.side_effect = Exception("Not found")

    @parameterized.expand(
        [
            (
                "basic",
                RESOURCE_DATA1,
            ),
            (
                "not_found",
                [],
                _not_found,
                ObjectDoesNotExist,
                "The specified digital asset does not exist",
            ),
        ]
    )
    def test_single_asset_retrieving(self, name, expected_result, side_effect=None, err_type=None, err_msg=None):
        if side_effect is not None:
            side_effect(self)

        error = None
        result = None
        try:
            am = asset_manager.AssetManager()
            result = am.get_asset_info("111")
        except Exception as e:
            error = e

        self.validate_response(result, expected_result, error, err_type, err_msg)

    @parameterized.expand([("basic", [RESOURCE_DATA1, RESOURCE_DATA2, RESOURCE_DATA3, RESOURCE_DATA4])])
    def test_assets_from_product(self, name, expected_result, side_effect=None, err_type=None, err_msg=None):
        if side_effect is not None:
            side_effect(self)

        error = None
        result = None
        try:
            am = asset_manager.AssetManager()
            result = am.get_product_assets("123")
        except Exception as e:
            error = e

        asset_manager.Resource.objects.filter.assert_called_once_with(product_id="123")
        self.validate_response(result, expected_result, error, err_type, err_msg)


class UploadAssetTestCase(TestCase):
    tags = ("asset-manager",)
    _file = None

    def setUp(self):
        import wstore.store_commons.rollback

        wstore.store_commons.rollback.rollback = decorator_mock
        self._user = MagicMock()
        self._user.userprofile.current_organization.name = "test_user"

        asset_manager.boto3.client = MagicMock()
        asset_manager.boto3.client.return_value.get_bucket_location.return_value = {'LocationConstraint':'eu-north-1'}
        asset_manager.settings.SITE = "http://testdomain.com/"
        asset_manager.settings.AWS_ACCESS_KEY_ID = "testKey/"
        asset_manager.settings.AWS_SECRET_ACCESS_KEY = "testSecretKey/"
        asset_manager.settings.BUCKET_NAME= "test"
        asset_manager.settings.ACL_ENABLED= False

        asset_manager.Resource = MagicMock()
        self.res_mock = MagicMock()
        self.res_mock.get_url.return_value = "http://locationurl.com/"
        self.res_mock.get_uri.return_value = "http://uri.com/"
        asset_manager.Resource.objects.create.return_value = self.res_mock
        asset_manager.Resource.objects.get.return_value = self.res_mock

        self._old_is_dir = asset_manager.os.path.isdir
        asset_manager.os.path.isdir = MagicMock()

        self._old_remove = asset_manager.os.remove
        asset_manager.os.remove = MagicMock()

        self._old_exists = asset_manager.os.path.exists
        asset_manager.os.path.exists = MagicMock()
        asset_manager.os.path.exists.return_value = False

        self.open_mock = mock_open()
        self._old_open = asset_manager.__builtins__["open"]
        asset_manager.__builtins__["open"] = self.open_mock

    def tearDown(self):
        asset_manager.os.path.isdir = self._old_is_dir
        asset_manager.os.path.exists = self._old_exists
        asset_manager.os.remove= self._old_remove
        import wstore.store_commons.rollback

        reload(wstore.store_commons.rollback)

        self._file = None
        asset_manager.__builtins__["open"] = self._old_open
        reload(asset_manager)

    def _use_file(self):
        # Mock file
        self._file = MagicMock(name="example.wgt")
        self._file.name = "example.wgt"
        self._file.read.return_value = "Test data content".encode()
        asset_manager.os.path.isdir.return_value = False
        # asset_manager.os.mkdir = MagicMock()
        asset_manager.os.makedirs = MagicMock()

    def _file_conflict(self):
        asset_manager.os.path.exists.return_value = True
        self.res_mock.product_id = None

    def _file_conflict_err(self):
        asset_manager.os.path.exists.return_value = True
        self.res_mock.product_id = "1"

    def _check_file_calls(self, file_name="example.wgt", aws= False):
        final_dir = "test_user" if not aws else "temp"
        asset_manager.os.path.isdir.assert_called_once_with("/home/test/media/assets/{}".format(final_dir))
        asset_manager.os.path.exists.assert_called_once_with("/home/test/media/assets/{}/{}".format(final_dir, file_name))
        self.open_mock.assert_called_once_with("/home/test/media/assets/{}/{}".format(final_dir, file_name), "wb")
        self.open_mock().write.assert_called_once_with("Test data content".encode())

    def _aws_mocks(self, side_effect, err):
        if side_effect is not None:
            asset_manager.boto3.client.return_value.upload_file.side_effect =  Exception({'Error': {'Code': side_effect, 'Message': err}}, 'upload_file')
        else:
            asset_manager.boto3.client.return_value.upload_file.return_value = None

    @parameterized.expand(
        [
            ("basic", False, UPLOAD_CONTENT),
            ("basic_2", True, UPLOAD_CONTENT),
            ("basic_3", False, UPLOAD_CONTENT_AWS),
            (
                "whitespce_name",
                False,
                UPLOAD_CONTENT_WHITESPACE,
                None,
                None,
                None,
                None,
                "example file.wgt",
            ),
            ("file", False, {"contentType": "application/x-widget", "isPublic":False}, _use_file),
            ("existing_override", False, UPLOAD_CONTENT, _file_conflict, True),
            (
                "missing_type",
                False,
                MISSING_TYPE,
                None,
                False,
                ValueError,
                "Missing required field: contentType",
            ),
            (
                "inv_file_name",
                False,
                UPLOAD_INV_FILENAME,
                None,
                False,
                ValueError,
                "Invalid file name format: Unsupported character",
            ),
            (
                "existing",
                False,
                UPLOAD_CONTENT,
                _file_conflict_err,
                True,
                ConflictError,
                "The provided digital asset file (example.wgt) already exists",
            ),
            (
                "not_provided",
                False,
                {"contentType": "application/x-widget"},
                None,
                False,
                ValueError,
                "The digital asset has not been provided",
            ),
            (
                "inv_content_field",
                False,
                {
                    "contentType": "application/x-widget",
                    "content": ["http://content.com"],
                },
                None,
                False,
                TypeError,
                "`content` field has an unsupported type, expected string or object",
            ),
        ]
    )
    @override_settings(MEDIA_ROOT="/home/test/media")
    def test_upload_asset(
        self,
        name,
        aws,
        data,
        side_effect=None,
        override=False,
        err_type=None,
        err_msg=None,
        file_name="example.wgt",
    ):
        asset_manager.settings.AWS_ENABLED= aws
        if side_effect is not None:
            side_effect(self)

        am = asset_manager.AssetManager()
        am.rollback_logger = {"files": [], "models": []}

        error = None
        try:
            resource = am.upload_asset(self._user, data, file_=self._file)
        except Exception as e:
            error = e

        if err_type is None:
            # Check not error
            self.assertTrue(error is None)

            # Check calls
            self.assertEquals(self.res_mock, resource)
            self.assertEquals("http://locationurl.com/", resource.get_url())
            self.assertEqual("http://uri.com/", resource.get_uri())
            self._check_file_calls(file_name)

            # Check rollback logger
            self.assertEquals(
                {
                    "files": ["/home/test/media/assets/test_user/{}".format(file_name)],
                    "models": [self.res_mock],
                },
                am.rollback_logger,
            )

            # Check file calls
            if self._file is not None:
                self._file.seek.assert_called_once_with(0)
                asset_manager.os.makedirs.assert_called_once_with("/home/test/media/assets/test_user", exist_ok=True)

            # Check override calls
            if override:
                asset_manager.Resource.objects.get.assert_called_once_with(
                    resource_path="media/assets/test_user/{}".format(file_name)
                )
                self.res_mock.delete.assert_called_once_with()

            # Check resource creation
            asset_manager.Resource.objects.create.assert_called_once_with(
                provider=self._user.userprofile.current_organization,
                version="",
                download_link="http://testdomain.com/charging/media/assets/test_user/{}".format(quote(file_name)),
                resource_path="media/assets/test_user/{}".format(file_name),
                content_type="application/x-widget",
                resource_type="",
                state="",
                is_public=data["isPublic"],
                meta_info={},
            )
        else:
            self.assertTrue(isinstance(error, err_type))
            self.assertEquals(err_msg, str(error))
    
    @parameterized.expand([("basic", UPLOAD_CONTENT_AWS, True), ("basic", UPLOAD_CONTENT_AWS, True, "AccessDenied", "Access Denied") ])
    @override_settings(MEDIA_ROOT="/home/test/media")
    def test_upload_asset_aws(
        self,
        name,
        data,
        awsEnabled,
        side_effect=None,
        err_msg=None,
        file_name="example.wgt",
    ):
        asset_manager.settings.AWS_ENABLED= awsEnabled
        am = asset_manager.AssetManager()
        am.rollback_logger = {"files": [], "models": []}
        self._aws_mocks(side_effect, err_msg)
        error = None
        try:
            resource = am.upload_asset(self._user, data, file_=self._file)
        except Exception as e:
            error = e
        # Check not error
        if side_effect is None:
            # Check calls
            self.assertEquals("http://locationurl.com/", resource.get_url())
            self.assertEqual("http://uri.com/", resource.get_uri())
            self._check_file_calls(file_name, True)
            # Check rollback logger
            self.assertEquals(["/home/test/media/assets/temp/{}".format(file_name)],
                am.rollback_logger["files"])
            # Check file calls
            if self._file is not None:
                self._file.seek.assert_called_once_with(0)
                asset_manager.os.makedirs.assert_called_once_with("/home/test/media/assets/temp", exist_ok=True)
            if self._file is not None:
                self._file.seek.assert_called_once_with(0)
                asset_manager.os.makedirs.assert_called_once_with("/home/test/media/assets/temp", exist_ok=True)
                # Check resource creation
        else:
            self.assertEquals("({'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}}, 'upload_file')", str(error))

    def _mock_resource_type(self, form):
        asset_manager.ResourcePlugin = MagicMock()
        asset_manager.Resource.objects.filter.return_value = []
        asset_manager.ResourcePlugin.objects.filter.return_value = [
            MagicMock(media_types=[], name="service", formats=["URL"], form=form)
        ]

    BASIC_META = {"field1": "value", "field2": True, "field3": "value2"}

    BASIC_FORM = {
        "field1": {"type": "text"},
        "field2": {"type": "checkbox"},
        "field3": {"type": "select", "options": [{"value": "value2"}]},
    }
    LINK = "http://myservices.com"
    LINK_CONTENT = {
        "contentType": "application/json",
        "resourceType": "service",
        "content": LINK,
    }

    @parameterized.expand(
        [
            ("no_metainfo", None, {}, {}),
            ("metainfo", BASIC_META, BASIC_META, BASIC_FORM),
            (
                "default_metainfo",
                {"field1": "value1"},
                {"field1": "value1", "field2": "value2"},
                {
                    "field1": {"type": "text"},
                    "field2": {"type": "text", "default": "value2"},
                },
            ),
        ]
    )
    def test_upload_asset_url_type(self, name, meta, exp_meta, form):
        content = deepcopy(self.LINK_CONTENT)

        if meta is not None:
            content["metadata"] = meta

        self._mock_resource_type(form)

        am = asset_manager.AssetManager()
        am.rollback_logger = {"files": [], "models": []}

        am.upload_asset(self._user, content)

        self.assertEquals({"files": [], "models": [self.res_mock]}, am.rollback_logger)

        # Check calls
        asset_manager.ResourcePlugin.objects.filter.assert_called_once_with(name="service")

        # Check resource creation
        asset_manager.Resource.objects.create.assert_called_once_with(
            provider=self._user.userprofile.current_organization,
            version="",
            download_link=self.LINK,
            resource_path="",
            content_type="application/json",
            resource_type="service",
            state="",
            is_public=False,
            meta_info=exp_meta,
        )

    def _existing_asset(self):
        asset_manager.Resource.objects.filter.return_value = [MagicMock(product_id="1")]

    def _type_not_found(self):
        asset_manager.ResourcePlugin.objects.filter.return_value = []

    def _inv_content(self):
        asset_manager.ResourcePlugin.objects.filter.return_value = [
            MagicMock(
                media_types=["text"],
                name="service",
                formats=["URL"],
            )
        ]

    def _inv_format(self):
        asset_manager.ResourcePlugin.objects.filter.return_value = [
            MagicMock(
                media_types=[],
                name="service",
                formats=["FILE"],
            )
        ]

    @parameterized.expand(
        [
            (
                "invalid_url",
                {
                    "contentType": "application/json",
                    "resourceType": "service",
                    "content": "invalid url",
                },
                None,
                None,
                {},
                ValueError,
                "The provided content is not a valid URL",
            ),
            (
                "no_type_metadata",
                {"contentType": "application/json", "content": LINK},
                None,
                BASIC_META,
                {},
                ValueError,
                "You have to specify a valid asset type for providing meta data",
            ),
            (
                "type_not_found",
                deepcopy(LINK_CONTENT),
                _type_not_found,
                None,
                {},
                ObjectDoesNotExist,
                "The asset type service does not exist",
            ),
            (
                "inv_content",
                deepcopy(LINK_CONTENT),
                _inv_content,
                None,
                {},
                ValueError,
                "The content type application/json is not valid for the specified asset type",
            ),
            (
                "inv_format",
                deepcopy(LINK_CONTENT),
                _inv_format,
                None,
                {},
                ValueError,
                "The format used for providing the digital asset (URL) is not valid for the given asset type",
            ),
            (
                "meta_not_allowed",
                deepcopy(LINK_CONTENT),
                None,
                BASIC_META,
                {},
                ValueError,
                "The specified asset type does not allow meta data",
            ),
            (
                "missing_mandatory_meta",
                deepcopy(LINK_CONTENT),
                None,
                BASIC_META,
                {
                    "field1": {"type": "text"},
                    "field2": {"type": "checkbox"},
                    "field3": {
                        "type": "text",
                    },
                    "field4": {"type": "text", "mandatory": True},
                },
                ValueError,
                "Missing mandatory field field4 in metadata",
            ),
            (
                "inv_meta_text_type",
                deepcopy(LINK_CONTENT),
                None,
                {"field1": True, "field2": True, "field3": "value2"},
                BASIC_FORM,
                TypeError,
                "Metadata field field1 must be a string",
            ),
            (
                "inv_meta_bool_type",
                deepcopy(LINK_CONTENT),
                None,
                {"field1": "value", "field2": "true", "field3": "value2"},
                BASIC_FORM,
                TypeError,
                "Metadata field field2 must be a boolean",
            ),
            (
                "unkown_option",
                deepcopy(LINK_CONTENT),
                None,
                {"field1": "value", "field2": True, "field3": "value5"},
                BASIC_FORM,
                ValueError,
                "Metadata field field3 value is not one of the available options",
            ),
        ]
    )
    def test_upload_asset_url_type_error(self, name, content, side_effect, meta, form, err_type, err_msg):
        if meta is not None:
            content["metadata"] = meta

        self._mock_resource_type(form)

        if side_effect is not None:
            side_effect(self)

        am = asset_manager.AssetManager()

        error = None
        try:
            am.upload_asset(self._user, content)
        except Exception as e:
            error = e

        self.assertTrue(isinstance(error, err_type))
        self.assertEquals(err_msg, str(error))

    def _mock_timer(self):
        timer = MagicMock()
        asset_manager.threading = MagicMock()
        asset_manager.threading.Timer = MagicMock(return_value=timer)

        return timer

    @override_settings(MEDIA_ROOT="/home/test/media")
    def test_upgrade_asset(self):
        asset_id = "1"
        prev_path = "media/assets/test_user/example1.wgt"
        prev_link = "http://testdomain.com/charging/media/assets/test_user/example1.wgt"
        prev_type = "application/x-widget-old"
        prev_version = "1.0"

        asset = MagicMock(
            product_id="2",
            is_public=False,
            resource_path=prev_path,
            download_link=prev_link,
            content_type=prev_type,
            version=prev_version,
            state="attached",
            old_versions=[],
        )

        asset_manager.Resource.objects.filter.return_value = [asset]

        timer = self._mock_timer()

        am = asset_manager.AssetManager()
        am.rollback_logger = {"files": [], "models": []}

        resource = am.upgrade_asset(asset_id, self._user, UPLOAD_CONTENT, file_=None)

        # Check calls
        asset_manager.Resource.objects.filter.assert_called_once_with(pk=asset_id)
        self.assertEquals(asset, resource)
        self._check_file_calls()

        # Check rollback logger
        self.assertEquals(
            {"files": ["/home/test/media/assets/test_user/example.wgt"], "models": []},
            am.rollback_logger,
        )

        self.assertEquals(asset, am._to_downgrade)

        # Check resource creation
        self.assertEquals("media/assets/test_user/example.wgt", asset.resource_path)
        self.assertEquals(
            "http://testdomain.com/charging/media/assets/test_user/example.wgt",
            asset.download_link,
        )
        self.assertEquals("application/x-widget", asset.content_type)
        self.assertEquals("upgrading", asset.state)
        self.assertEquals("", asset.version)

        self.assertEquals(1, len(asset.old_versions))

        old_version = asset.old_versions[0]

        self.assertEquals(prev_path, old_version["resource_path"])
        self.assertEquals(prev_link, old_version["download_link"])
        self.assertEquals(prev_type, old_version["content_type"])
        self.assertEquals(prev_version, old_version["version"])

        asset_manager.threading.Timer.assert_called_once_with(15, am._upgrade_timer)
        timer.start.assert_called_once_with()

    def _asset_empty(self):
        return []

    def _public_asset(self):
        return [MagicMock(product_id="2", is_public=True)]

    def _not_attached_asset(self):
        return [MagicMock(product_id=None, is_public=False)]

    def _upgrading_asset(self):
        return [MagicMock(product_id="2", state="upgrading", is_public=False)]

    @parameterized.expand(
        [
            (
                "not_found",
                _asset_empty,
                ObjectDoesNotExist,
                "The specified asset does not exist",
            ),
            (
                "public_asset",
                _public_asset,
                ValueError,
                "It is not allowed to upgrade public assets, create a new one instead",
            ),
            (
                "not_attached",
                _not_attached_asset,
                ValueError,
                "It is not possible to upgrade an asset not included in a product specification",
            ),
            (
                "upgrading",
                _upgrading_asset,
                ValueError,
                "The provided asset is already in upgrading state",
            ),
        ]
    )
    def test_upgrade_asset_error(self, name, asset_mock, err_type, err_msg):
        self._mock_timer()
        asset_resp = asset_mock(self)
        asset_manager.Resource.objects.filter.return_value = asset_resp

        error = None
        try:
            am = asset_manager.AssetManager()
            am.upgrade_asset("1", self._user, UPLOAD_CONTENT, file_=None)
        except Exception as e:
            error = e

        self.assertTrue(isinstance(error, err_type))
        self.assertEquals(err_msg, str(error))

    def _test_timer(self, state, check_calls):
        asset_pk = "1234"

        lock = MagicMock()
        asset_manager.DocumentLock = MagicMock(return_value=lock)

        asset = MagicMock(pk=asset_pk, state=state)
        asset_manager.Resource.objects.get.return_value = asset
        asset_manager.downgrade_asset = MagicMock()

        am = asset_manager.AssetManager()
        am._to_downgrade = MagicMock(pk=asset_pk)

        am._upgrade_timer()

        asset_manager.DocumentLock.assert_called_once_with("wstore_resource", asset_pk, "asset")
        lock.wait_document.assert_called_once_with()
        lock.unlock_document.assert_called_once_with()

        asset_manager.Resource.objects.get.assert_called_once_with(pk=asset_pk)

        check_calls(asset)

    def test_upgrade_timer(self):
        def check_calls(asset):
            asset_manager.downgrade_asset.assert_called_once_with(asset)

        self._test_timer("upgrading", check_calls)

    def test_upgrade_timer_attached(self):
        def check_calls(asset):
            self.assertEquals(0, asset_manager.downgrade_asset.call_count)

        self._test_timer("attached", check_calls)


class ResourceModelTestCase(TestCase):
    tags = ("resource-model",)

    def test_resource_model(self):
        models.settings.SITE = "http://testserver.com/"

        url = "http://example.com/media/resource"

        from wstore.models import Organization

        org = Organization.objects.create(name="Test")

        res = models.Resource.objects.create(
            provider=org,
            version="1.0",
            download_link=url,
            resource_path="",
            content_type="",
            resource_type="",
            state="",
        )

        uri = "http://testserver.com/charging/api/assetManagement/assets/" + str(res.pk)
        self.assertEquals(url, res.get_url())
        self.assertEquals(uri, res.get_uri())

        reload(models)
