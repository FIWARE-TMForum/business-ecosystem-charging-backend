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


from importlib import reload
from django.conf import settings

from django.core.exceptions import PermissionDenied
from django.test.testcases import TestCase
from mock import MagicMock, call
from parameterized import parameterized

from wstore.asset_manager import product_validator, catalog_validator
from wstore.asset_manager.errors import ProductError
from wstore.asset_manager.test.product_validator_test_data import *
from wstore.store_commons.errors import ConflictError
from wstore.asset_manager.test.service_validator_test_data import *
import wstore.asset_manager.resource_plugins.decorators

class ValidatorTestCase(TestCase):
    tags = ("product-validator",)

    def _mock_validator_imports(self, module):
        reload(module)


    def setUp(self):
        self._provider = MagicMock()
        
        self._plugin_instance = MagicMock()
        self._plugin_instance.media_types = ["application/x-widget"]
        self._plugin_instance.formats = ["FILE"]
        self._plugin_instance.module = "wstore.asset_manager.resource_plugins.plugin.Plugin"
        self._plugin_instance.form = {}
        self._plugin_instance.name = "Widget"
        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects = MagicMock()
        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.return_value = self._plugin_instance
        wstore.asset_manager.resource_plugins.decorators.on_product_spec_validation = MagicMock(side_effect=lambda func: func)

        mock_response = MagicMock()
        mock_response.json.return_value = [BASIC_SERVICE["service"]]
        
        catalog_validator.requests = MagicMock()
        catalog_validator.requests.get.return_value = mock_response
        
        # Mock Site
        product_validator.settings.CATALOG = "http://testcataloglocation.org/"
        product_validator.settings.SERVICE_CATALOG = "http://testcataloglocation.org/"
        

    def tearDown(self):
        reload(product_validator)
        reload(catalog_validator)
        reload(wstore.asset_manager.resource_plugins.decorators)

    def _not_supported(self):
        import wstore.asset_manager.resource_plugins.decorators

        wstore.asset_manager.resource_plugins.decorators.ResourcePlugin.objects.get.side_effect = Exception("Not found")
        self._mock_validator_imports(product_validator)

    def test_validate_creation_registered_file(self):
        self._mock_validator_imports(product_validator)

        validator = product_validator.ProductValidator()
        validator.validate("create", self._provider, BASIC_PRODUCT["product"])
        catalog_validator.requests.get.assert_called_once_with(f"{settings.SERVICE_CATALOG}/serviceSpecification?id=id")


    def test_validate_creation_new_url(self):
        self._mock_validator_imports(product_validator)
        validator = product_validator.ProductValidator()
        validator.validate("create", self._provider, BASIC_PRODUCT["product"])
        product_validator.on_product_spec_validation.assert_called_once()

    @parameterized.expand(
        [
            (
                "invalid_action",
                INVALID_P_ACTION,
                ValueError,
                "The provided action (invalid) is not valid. Allowed values are create, attach, update, upgrade, and delete",
            ),
            ("invalid product spec bundle", INVALID_BUNDLE_CREATION, ProductError, "ProductError: A product spec bundle must contain at least two bundled product specs")
        ]
    )
    def test_validate_error(self, name, data, err_type, err_msg):
        self._mock_validator_imports(product_validator)
        print(data)
        error = None
        try:
            validator = product_validator.ProductValidator()
            validator.validate(data["action"], self._provider, data["product"])
        except Exception as e:
            error = e
        self.assertIsNotNone(error)
        self.assertIsInstance(error, err_type)
        self.assertEquals(err_msg, str(error))

    # def _mock_upgrading_asset(self, version):
    #     self._asset_instance.state = "upgrading"
    #     self._asset_instance.product_id = UPGRADE_PRODUCT["product"]["id"]
    #     self._asset_instance.version = version
    #     self._asset_instance.old_versions = [MagicMock(version="1.0")]

    # def _mock_document_lock(self):
    #     document_lock = MagicMock()
    #     product_validator.DocumentLock = MagicMock(return_value=document_lock)

    #     return document_lock

    # def test_validate_upgrade(self):
    #     self._mock_validator_imports(product_validator)
    #     self._mock_upgrading_asset("")

    #     doc_lock = self._mock_document_lock()

    #     validator = product_validator.ProductValidator()
    #     validator.validate("upgrade", self._provider, UPGRADE_PRODUCT["product"])

    #     self.assertEquals(UPGRADE_PRODUCT["product"]["version"], self._asset_instance.version)
    #     self.assertEquals("upgrading", self._asset_instance.state)
    #     self._asset_instance.save.assert_called_once_with()

    #     product_validator.DocumentLock.assert_called_once_with("wstore_resource", self._asset_instance.pk, "asset")
    #     doc_lock.wait_document.assert_called_once_with()
    #     doc_lock.unlock_document.assert_called_once_with()

    # def test_attach_upgrade(self):
    #     self._mock_validator_imports(product_validator)
    #     self._mock_upgrading_asset(UPGRADE_PRODUCT["product"]["version"])

    #     doc_lock = self._mock_document_lock()

    #     # Mock inventory upgrader class
    #     product_validator.InventoryUpgrader = MagicMock()

    #     validator = product_validator.ProductValidator()
    #     validator.validate("attach_upgrade", self._provider, UPGRADE_PRODUCT["product"])

    #     self.assertEquals("attached", self._asset_instance.state)

    #     product_validator.InventoryUpgrader.assert_called_once_with(self._asset_instance)
    #     product_validator.InventoryUpgrader().start.assert_called_once_with()

    #     self._asset_instance.save.assert_called_once_with()

    #     product_validator.DocumentLock.assert_called_once_with("wstore_resource", self._asset_instance.pk, "asset")
    #     doc_lock.wait_document.assert_called_once_with()
    #     doc_lock.unlock_document.assert_called_once_with()

    # def test_attach_upgrade_non_digital(self):
    #     self._mock_validator_imports(product_validator)

    #     validator = product_validator.ProductValidator()
    #     validator.validate(
    #         "attach_upgrade",
    #         self._provider,
    #         {"version": "1.0", "productSpecCharacteristic": []},
    #     )

    #     # The method did nothing
    #     self.assertEquals(0, product_validator.ResourcePlugin.objects.get.call_count)

    # @parameterized.expand(
    #     [
    #         ("missing_version", {}),
    #         ("missing_charact", {"version": "1.0"}),
    #         ("non_digital", {"version": "1.0", "productSpecCharacteristic": []}),
    #     ]
    # )
    # def test_validate_upgrade_missing_info(self, name, data):
    #     self._mock_validator_imports(product_validator)
    #     self._asset_instance.state = "upgrading"

    #     validator = product_validator.ProductValidator()
    #     validator.validate("upgrade", self._provider, data)

    #     self.assertEquals("upgrading", self._asset_instance.state)

    # def _non_digital(self):
    #     return [[], []]

    # def _mixed_assets(self):
    #     digital_asset = MagicMock(pk="1")
    #     product_validator.Resource.objects.filter.side_effect = [[], [digital_asset]]

    # def _all_digital(self):
    #     digital_asset = MagicMock(pk="1")
    #     digital_asset1 = MagicMock(pk="2")
    #     return [[digital_asset], [digital_asset1]]

    def test_bundle_creation(self):
        self._mock_validator_imports(product_validator)

        validator = product_validator.ProductValidator()
        error=None
        try:
            validator.validate(
                BASIC_BUNDLE_CREATION["action"],
                self._provider,
                BASIC_BUNDLE_CREATION["product"],
            )
        except Exception as e:
            error = e
        
        self.assertIsNone(error)
        



    # def _validate_bundle_creation_error(self, product_request, msg, side_effect=None):
    #     self._mock_validator_imports(product_validator)

    #     if side_effect is not None:
    #         side_effect()

    #     try:
    #         validator = product_validator.ProductValidator()
    #         validator.validate(product_request["action"], self._provider, product_request["product"])
    #     except ProductError as e:
    #         error = e

    #     self.assertEquals(msg, str(error))

    # def test_bundle_creation_missing_products(self):
    #     self._validate_bundle_creation_error(
    #         {"action": "create", "product": {"isBundle": True}},
    #         "ProductError: A product spec bundle must contain at least two bundled product specs",
    #     )

    # def _non_pending_bundles(self):
    #     product_validator.Resource.objects.filter.return_value = []

    # def _pending_bundles(self):
    #     product1 = MagicMock(product_id="1", pk="1a")
    #     product2 = MagicMock(product_id="2", pk="2a")

    #     bundle1 = MagicMock()
    #     bundle1.bundled_assets = [{}]

    #     bundle2 = MagicMock()
    #     bundle2.bundled_assets = ["2a", "3a"]

    #     self._asset_instance.bundled_assets = ["1a", "2a"]

    #     product_validator.Resource.objects.filter.side_effect = [
    #         [bundle1, bundle2, self._asset_instance],
    #         [product1],
    #         [product2],
    #     ]

    # @parameterized.expand(
    #     [
    #         ("digital_asset", BASIC_PRODUCT["product"], True, True),
    #         ("non_digital", {"isBundle": False}),
    #         (
    #             "bundle_non_pending",
    #             BASIC_BUNDLE_CREATION["product"],
    #             False,
    #             False,
    #             True,
    #             _non_pending_bundles,
    #         ),
    #         (
    #             "bundle_multiple_pending",
    #             BASIC_BUNDLE_CREATION["product"],
    #             False,
    #             True,
    #             True,
    #             _pending_bundles,
    #         ),
    #     ]
    # )
    # def test_attach_info(
    #     self,
    #     name,
    #     product_spec,
    #     is_digital=False,
    #     is_attached=False,
    #     is_bundle=False,
    #     filter_mock=None,
    # ):
    #     self._mock_validator_imports(product_validator)

    #     if filter_mock is not None:
    #         filter_mock(self)

    #     validator = product_validator.ProductValidator()

    #     digital_chars = (
    #         ("type", "media", "http://location", "61004aba5e05acc115f022f0") if is_digital else (None, None, None, None)
    #     )
    #     validator.parse_characteristics = MagicMock(return_value=digital_chars)

    #     validator.validate("attach", self._provider, product_spec)

    #     # Check calls
    #     validator.parse_characteristics.assert_called_once_with(product_spec)
    #     if is_digital:
    #         product_validator.Resource.objects.get.assert_called_once_with(pk=ObjectId(digital_chars[3]))
    #         self.assertEquals(0, product_validator.Resource.objects.filter.call_count)

    #     if is_bundle:
    #         self.assertEquals(
    #             [
    #                 call(
    #                     product_id=None,
    #                     provider=self._provider,
    #                     content_type="bundle",
    #                     resource_path="",
    #                     download_link="",
    #                 ),
    #                 call(product_id="1"),
    #                 call(product_id="2"),
    #             ],
    #             product_validator.Resource.objects.filter.call_args_list,
    #         )
    #         self.assertEquals(0, product_validator.Resource.objects.get.call_count)

    #     if is_attached:
    #         self.assertEquals(product_spec["id"], self._asset_instance.product_id)
    #         self.assertEquals(product_spec["version"], self._asset_instance.version)
    #         self.assertEquals(digital_chars[0], self._asset_instance.resource_type)
    #         self.assertEquals("attached", self._asset_instance.state)

    #         self._asset_instance.save.assert_called_once_with()
    #     else:
    #         self.assertEquals(0, self._asset_instance.save.call_count)

    # @parameterized.expand([("no_chars", NO_CHARS_PRODUCT), ("no_digital_chars", EMPTY_CHARS_PRODUCT)])
    # def test_validate_physical(self, name, product):
    #     self._mock_validator_imports(product_validator)
    #     validator = product_validator.ProductValidator()
    #     validator.validate("create", self._provider, product)

    #     self.assertEquals(0, product_validator.ResourcePlugin.objects.get.call_count)
    #     self.assertEquals(0, product_validator.Resource.objects.get.call_count)
    #     self.assertEquals(0, product_validator.Resource.objects.create.call_count)