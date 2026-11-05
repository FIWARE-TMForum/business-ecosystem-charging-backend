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
import fcntl
import select
import subprocess
import types
import zipfile
import os
import sys
from importlib import reload
from json import dump as jsondump
from shutil import rmtree
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZipInfo

from bson.objectid import ObjectId
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.test import SimpleTestCase, TestCase, override_settings
from mock import MagicMock, Mock, call, patch
from parameterized import parameterized
from requests.exceptions import HTTPError
from wstore.asset_manager.errors import ResourceError, ServiceError
from wstore.asset_manager.resource_plugins import decorators, plugin, plugin_loader
from wstore.asset_manager.resource_plugins.plugin import Plugin, ServicePlugin
from wstore.asset_manager.resource_plugins.plugin import ResourcePlugin as ResourcePluginHandler
from wstore.store_commons.resource_catalog import ResourceCatalog, ResourceCatalogError
from wstore.asset_manager.resource_plugins.plugin_error import (
    PluginError, PluginConflictError, PluginSizeError, PluginCatalogError, PluginUnavailableError, PluginUsageError,
)
from wstore.asset_manager.resource_plugins.plugin_loader import PluginLoader
from wstore.store_commons.service_catalog import ServiceCatalog, ServiceCatalogError
from wstore.asset_manager.resource_plugins.plugin_validator import PluginValidator
from wstore.asset_manager.resource_plugins.test_data import *
from wstore.models import ResourcePlugin


class TestPlugin:
    def __init__(self, plugin_model):
        self._plugin_model = plugin_model

    def remove_usage_specs(self):
        self._plugin_model.usage_called = True


class PluginLoaderTestCase(TestCase):
    tags = ("plugin",)

    _to_remove = None

    def setUp(self):
        catalog_patch = patch.object(plugin_loader, "ServiceCatalog")
        self.catalog_mock = catalog_patch.start().return_value
        self.catalog_mock.create_category.return_value = "category-1"
        self.addCleanup(catalog_patch.stop)
        usage_patch = patch.object(plugin_loader.requests, "get")
        self.usage_get = usage_patch.start()
        self.usage_get.return_value.json.return_value = []
        self.addCleanup(usage_patch.stop)
        # Create PluginManager mock
        plugin_loader.PluginValidator = MagicMock(name="PluginManager")
        self.manager_mock = MagicMock()
        self.manager_mock.validate_plugin_info.return_value = None
        self.manager_mock.validate_pull_accounting.return_value = None

        plugin_loader.PluginValidator.return_value = self.manager_mock

    def _clean_plugin_dir(self):
        plugin_dir = os.path.join("wstore", "test")
        for plugin_f in os.listdir(plugin_dir):
            if plugin_f != "test_plugin_files":
                rmtree(os.path.join(plugin_dir, plugin_f), True)

    def tearDown(self):
        reload(plugin_loader)
        # Clean plugin dir after each test
        self._clean_plugin_dir()

    def _inv_zip(self):
        self.zip_path = "wstore"

    def _inv_plugin_info(self):
        self.manager_mock.validate_plugin_info.return_value = ["validation error"]

    def _existing_plugin(self):
        os.mkdir(os.path.join("wstore", "test", "test-plugin-1-0"))
        ResourcePlugin.objects.create(
            name="test plugin",
            plugin_id="test-plugin",
            version="1.0",
            author="test author",
            module="test-plugin.TestPlugin",
        )

    def _pull_acc_errors(self):
        self.manager_mock.validate_pull_accounting.return_value = "Error in pull accounting"

    @parameterized.expand(
        [
            (
                "correct",
                "test_plugin.zip",
                PLUGIN_INFO,
            ),
            (
                "correct_no_optionals",
                "test_plugin_5.zip",
                PLUGIN_INFO2,
            ),
            (
                "pull_accounting",
                "test_plugin_8.zip",
                None,
                None,
                Exception,
                "Call to configure expecs",
            ),
            (
                "invalid_zip",
                "test_plugin.zip",
                None,
                _inv_zip,
                PluginError,
                "Plugin Error: Invalid package format: Not a zip file",
            ),
            (
                "missing_json",
                "test_plugin_2.zip",
                None,
                None,
                PluginError,
                "Plugin Error: Missing package.json file",
            ),
            (
                "not_plugin_imp",
                "test_plugin_3.zip",
                None,
                None,
                PluginError,
                "Plugin Error: No ServicePlugin implementation has been found",
            ),
            (
                "inv_json",
                "test_plugin_4.zip",
                None,
                None,
                PluginError,
                "Plugin Error: Invalid format in package.json file. JSON cannot be parsed",
            ),
            (
                "validation_err",
                "test_plugin.zip",
                None,
                _inv_plugin_info,
                PluginError,
                "Plugin Error: Invalid format in package.json file.\nvalidation error",
            ),
            (
                "existing",
                "test_plugin.zip",
                None,
                _existing_plugin,
                PluginError,
                "Plugin Error: An equal version of this plugin is already installed",
            ),
            (
                "pull_accounting_err",
                "test_plugin_6.zip",
                None,
                _pull_acc_errors,
                PluginError,
                "Plugin Error: Error in pull accounting",
            ),
            (
                "lower_version_err",
                "test_plugin_9.zip",
                None,
                _existing_plugin,
                PluginError,
                "Plugin Error: A newer version of this plugin is already installed",
            ),
        ]
    )
    def test_plugin_installation(
        self,
        name,
        zip_file,
        expected=None,
        side_effect=None,
        err_type=None,
        err_msg=None,
    ):
        # Build plugin loader
        plugin_l = plugin_loader.PluginLoader()

        self.plugin_dir = os.path.join("wstore", "test")

        # Mock plugin directory location
        plugin_l._plugins_path = self.plugin_dir
        plugin_l._plugins_module = "wstore.test."

        # Create a init file in the test dir
        open(os.path.join(self.plugin_dir, "__init__.py"), "a").close()

        self.zip_path = os.path.join(self.plugin_dir, "test_plugin_files")
        self.zip_path = os.path.join(self.zip_path, zip_file)

        if side_effect is not None:
            side_effect(self)

        self._to_remove = zip_file
        error = None
        try:
            plugin_l.install_plugin(self.zip_path)
        except Exception as e:
            error = e

        if err_type is None:
            self.assertEquals(error, None)
            # Check calls
            self.manager_mock.validate_plugin_info.assert_called_once_with(expected)

            # Check plugin model
            plugin_model = ResourcePlugin.objects.all()[0]
            self.assertEquals(plugin_model.name, expected["name"])
            self.assertEquals(plugin_model.plugin_id, expected["name"].lower().replace(" ", "-"))
            self.assertEquals(plugin_model.author, expected["author"])
            self.assertEquals(plugin_model.version, expected["version"])
            self.assertEquals(plugin_model.requires_file, expected["requires_file"])

            plugin_dir_name = f"{plugin_model.plugin_id}-{plugin_model.version.replace('.', '-')}"
            self.assertEquals(
                plugin_model.module,
                f"wstore.test.{plugin_dir_name}.{expected['module']}",
            )
            self.assertEquals(plugin_model.media_types, expected.get("media_types", []))
            self.assertEquals(plugin_model.form, expected.get("form", {}))

            # Check plugin files
            test_plugin_dir = os.path.join(self.plugin_dir, plugin_dir_name)
            self.assertTrue(os.path.isdir(test_plugin_dir))
            self.assertTrue(os.path.isfile(os.path.join(test_plugin_dir, "package.json")))
            self.assertTrue(os.path.isfile(os.path.join(test_plugin_dir, "test.py")))

        else:
            self.assertIsInstance(error, err_type)
            self.assertEquals(str(error), err_msg)

    def _existing_plugin_with_versions(
        self,
        versions,
        downgrade_plugin_info,
        pull_accounting=False,
    ):
        last_version = versions[-1]
        for version in versions:
            plugin_info = downgrade_plugin_info.copy()
            plugin_info["version"] = version
            version_path = os.path.join("wstore", "test", f'test-plugin-{version.replace(".", "-")}')
            os.mkdir(version_path)
            with open(os.path.join(version_path, "package.json"), "w") as package_file:
                jsondump(downgrade_plugin_info, package_file)
        return ResourcePlugin.objects.create(
            name="test plugin",
            plugin_id="test-plugin",
            version=last_version,
            version_history=versions[:-1],
            author="test author",
            module=f'test-plugin-{last_version.replace(".", "-")}.TestPlugin',
            pull_accounting=pull_accounting,
        ).plugin_id

    @parameterized.expand(
        [
            ("correct_no_version", ["0.2", "0.3"], None, PLUGIN_INFO_DOWNGRADE),
            (
                "correct_version",
                ["0.1", "0.2", "0.3", "0.4"],
                "0.2",
                PLUGIN_INFO_DOWNGRADE,
            ),
            (
                "correct_pull_accounting",
                ["0.2", "1.0"],
                "0.2",
                PLUGIN_INFO_DOWNGRADE_ACCOUNTING,
                True,
            ),
            (
                "version_not_installed",
                ["0.1", "1.0"],
                "0.2",
                PLUGIN_INFO_DOWNGRADE,
                False,
                PluginError,
                "Plugin Error: Specified version is not installed for this plugin or plugin cannot be further downgraded",
            ),
        ]
    )
    def test_plugin_downgrade(
        self,
        name,
        versions,
        downgrade_to=None,
        downgrade_plugin_info=None,
        pull=False,
        err_type=None,
        err_msg=None,
    ):
        # Build plugin loader
        plugin_l = plugin_loader.PluginLoader()

        self.plugin_dir = os.path.join("wstore", "test")

        # Mock plugin directory location
        plugin_l._plugins_path = self.plugin_dir
        plugin_l._plugins_module = "wstore.test."

        # Mock plugin class
        plugin_l._get_plugin_module = MagicMock(return_value=MagicMock())

        # Create a init file in the test dir
        open(os.path.join(self.plugin_dir, "__init__.py"), "a").close()

        plugin_id = self._existing_plugin_with_versions(versions, downgrade_plugin_info, pull)

        error = None
        try:
            plugin_l.downgrade_plugin(plugin_id, downgrade_to)
        except Exception as e:
            error = e

        if err_type is None:
            self.assertEquals(error, None)

            # Check plugin model
            plugin_model = ResourcePlugin.objects.get(plugin_id=plugin_id)
            self.assertEquals(plugin_model.version, downgrade_plugin_info["version"])

            plugin_dir_name = f"{plugin_model.plugin_id}-{plugin_model.version.replace('.', '-')}"
            self.assertEquals(plugin_model.media_types, downgrade_plugin_info.get("media_types", []))
            self.assertEquals(plugin_model.form, downgrade_plugin_info.get("form", {}))

            # Check plugin files
            test_plugin_dir = os.path.join(self.plugin_dir, plugin_dir_name)
            self.assertTrue(os.path.isdir(test_plugin_dir))
            self.assertTrue(os.path.isfile(os.path.join(test_plugin_dir, "package.json")))

        else:
            self.assertIsInstance(error, err_type)
            self.assertEquals(str(error), err_msg)

    def _plugin_in_use(self):
        self.usage_get.return_value.json.return_value = [{
            "id": "spec-1",
            "specCharacteristic": [{
                "name": "Service Type",
                "characteristicValueSpecification": [{"value": "category-1"}],
            }],
        }]

    def _plugin_not_exists(self):
        plugin_loader.ResourcePlugin.objects.get.side_effect = ObjectDoesNotExist()

    def _plugin_two_versions(self, plugin_mock):
        def remove_one_version(pid, pmodel):
            pmodel.version = pmodel.version_history.pop()

        plugin_mock.version_history = ["0.1"]
        plugin_loader.PluginLoader._downgrade_plugin_to_last_version = MagicMock(
            name="_downgrade_plugin_to_last_version"
        )
        plugin_loader.PluginLoader._downgrade_plugin_to_last_version.side_effect = remove_one_version

    @parameterized.expand(
        [
            ("correct",),
            ("pull_accounting", True),
            ("two_versions", False, _plugin_two_versions),
            (
                "plugin_used",
                False,
                _plugin_in_use,
                PermissionDenied,
                "The plugin test_plugin is being used by specifications or inventory instances",
            ),
            (
                "not_exists",
                False,
                _plugin_not_exists,
                ObjectDoesNotExist,
                "The plugin test_plugin is not registered",
            ),
        ]
    )
    def test_plugin_removal(self, name, pull=False, side_effect=None, err_type=None, err_msg=None):
        plugin_name = "Test Plugin"

        # Mock libraries
        plugin_loader.ResourcePlugin = MagicMock(name="ResourcePlugin")

        plugin_mock = MagicMock()
        plugin_mock.name = plugin_name
        plugin_mock.type = "service"
        plugin_mock.version = "1.0"
        plugin_mock.category_id = "category-1"
        plugin_mock.version_history = []
        plugin_mock.pull_accounting = pull
        plugin_mock.module = "wstore.asset_manager.resource_plugins.tests.TestPlugin"
        plugin_mock.usage_called = False

        plugin_loader.ResourcePlugin.objects.get.return_value = plugin_mock

        plugin_loader.rmtree = MagicMock(name="rmtree")
        path_patch = patch.object(plugin_loader.os.path, "isdir", return_value=True)
        path_patch.start()
        self.addCleanup(path_patch.stop)

        if side_effect is not None:
            if name == "two_versions":
                side_effect(self, plugin_mock)
            else:
                side_effect(self)

        # Build plugin loader
        plugin_l = plugin_loader.PluginLoader()

        error = None
        try:
            plugin_l.uninstall_plugin("test_plugin")
        except Exception as e:
            error = e

        if err_type is None:
            self.assertEquals(error, None)
            # Check calls
            plugin_loader.ResourcePlugin.objects.get.assert_called_once_with(plugin_id="test_plugin")
            self.catalog_mock.delete_category.assert_called_once_with("category-1")
            expected_versions = ["1.0", "0.1"] if name == "two_versions" else ["1.0"]
            self.assertEqual(
                [
                    call(os.path.join(plugin_l._plugins_path, "test_plugin-" + v.replace(".", "-")))
                    for v in expected_versions
                ],
                plugin_loader.rmtree.call_args_list,
            )
            plugin_mock.delete.assert_called_once_with()

            self.assertEquals(pull, plugin_mock.usage_called)
        else:
            self.assertIsInstance(error, err_type)
            self.assertEquals(str(error), err_msg)


class PluginValidatorTestCase(TestCase):
    tags = ("plugin",)

    @parameterized.expand(
        [
            ("correct", PLUGIN_INFO),
            ("invalid_type", "invalid", "Plugin info must be a dict instance"),
            ("missing_name", MISSING_NAME, "Missing required field: name"),
            ("invalid_name", INVALID_NAME, "Invalid name format: invalid character"),
            ("missing_author", MISSING_AUTHOR, "Missing required field: author"),
            ("missing_requires_file", MISSING_REQUIRES_FILE, "Missing required field: requires_file"),
            ("missing_module", MISSING_MODULE, "Missing required field: module"),
            ("missing_version", MISSING_VERSION, "Missing required field: version"),
            (
                "invalid_name_type",
                INVALID_NAME_TYPE,
                "Field `name` should be str but found int.",
            ),
            (
                "invalid_author_type",
                INVALID_AUTHOR_TYPE,
                "Field `author` should be str but found int.",
            ),
            (
                "invalid_requires_file_type",
                INVALID_REQUIRES_FILE_TYPE,
                "Field `requires_file` should be bool but found str.",
            ),
            (
                "invalid_requires_file",
                INVALID_REQUIRES_FILE,
                "Field `requires_file` should be bool but found int.",
            ),
            (
                "invalid_media_type",
                INVALID_MEDIA_TYPE,
                "Plugin `media_types` must be a list of non-empty strings",
            ),
            (
                "invalid_module_type",
                INVALID_MODULE_TYPE,
                "Field `module` should be str but found list.",
            ),
            ("invalid_version", INVALID_VERSION, "Invalid format in plugin version"),
            (
                "invalid_pull_format",
                INVALID_ACCOUNTING,
                "Plugin `pull_accounting` property must be a boolean",
            ),
            (
                "invalid_form_type",
                INVALID_FORM_TYPE,
                "Invalid format in `form` field, must be an object",
            ),
            (
                "invalid_form_entry_type",
                INVALID_FORM_ENTRY_TYPE,
                "Invalid form field: name entry is not an object",
            ),
            (
                "invalid_form_missing_type",
                INVALID_FORM_MISSING_TYPE,
                "Invalid form field: Missing type in name entry",
            ),
            (
                "invalid_form_inv_type",
                INVALID_FORM_INV_TYPE,
                "Invalid form field: type invalid in name entry is not a valid type",
            ),
            (
                "invalid_form_inv_name",
                INVALID_FORM_INVALID_NAME,
                "Invalid form field: inv&name is not a valid name",
            ),
            (
                "invalid_form_checkbox_def",
                INVALID_FORM_CHECKBOX_DEF,
                "\nInvalid form field: default field in check entry must be a boolean",
            ),
            (
                "invalid_form_text",
                INVALID_FORM_TEXT,
                "\nInvalid form field: default field in textf entry must be an string"
                + "\nInvalid form field: label field in textf entry must be an string\nInvalid form field: mandatory field in textf entry must be a boolean",
            ),
            (
                "invalid_form_textarea",
                INVALID_FORM_TEXTAREA,
                "\nInvalid form field: placeholder field in textf entry must be an string",
            ),
            (
                "invalid_form_select",
                INVALID_FORM_SELECT,
                "\nInvalid form field: default field in select entry must be an string"
                + "\nInvalid form field: label field in select entry must be an string\nInvalid form field: mandatory field in select entry must be a boolean",
            ),
            (
                "invalid_form_select_miss_opt",
                INVALID_FORM_SELECT_MISS_OPT,
                "\nInvalid form field: Missing or invalid options in select field",
            ),
            (
                "invalid_form_select_inv_opt",
                INVALID_FORM_SELECT_INV_OPT,
                "\nInvalid form field: Missing or invalid options in select field",
            ),
            (
                "invalid_form_select_empty_opt",
                INVALID_FORM_SELECT_EMPTY_OPT,
                "\nInvalid form field: Missing or invalid options in select field",
            ),
            (
                "invalid_form_select_inv_opt_val",
                INVALID_FORM_SELECT_INV_OPT_VAL,
                "\nInvalid form field: Invalid option in select field, wrong option type or missing field",
            ),
            (
                "invalid_form_select_inv_opt_val2",
                INVALID_FORM_SELECT_INV_OPT_VAL2,
                "\nInvalid form field: Invalid option in select field, wrong option type or missing field"
                + "\nInvalid form field: text field in select entry must be an string",
            ),
            (
                "invalid_overrides",
                INVALID_OVERRIDES,
                "Override values should be one of: ['NAME', 'VERSION', 'OPEN']",
            ),
            (
                "invalid_form_order_format",
                INVALID_FORM_ORDER_FORMAT,
                "Invalid format in `form_order`",
            ),
            (
                "invalid_form_order_no_form",
                INVALID_FORM_ORDER_NO_FORM,
                "`form_order` cannot be specified without a `form`",
            ),
            (
                "invalid_form_order_missing_key",
                INVALID_FORM_ORDER_MISSING_KEY,
                "If `form_order` is provided all form keys need to be provided",
            ),
            (
                "invalid_form_order_different_key",
                INVALID_FORM_ORDER_DIFFERENT_KEY,
                "If `form_order` is provided all form keys need to be provided",
            ),
        ]
    )
    def test_plugin_info_validation(self, name, plugin_info, validation_msg=None):
        plugin_manager = PluginValidator()

        reasons = plugin_manager.validate_plugin_info(plugin_info)
        if validation_msg:
            self.assertIn(validation_msg, reasons)

    @parameterized.expand(
        [
            (
                "correct",
                PLUGIN_INFO_ACCOUNTING,
                ["get_pending_accounting", "get_usage_specs"],
            ),
            ("no_pull_accounting", PLUGIN_INFO),
            (
                "implemented_but_false",
                PLUGIN_INFO,
                ["get_pending_accounting"],
                "Pull accounting is false, but some methods are implemented",
            ),
            (
                "not_implemented_but_true",
                PLUGIN_INFO_ACCOUNTING,
                ["get_usage_specs"],
                "Pull accounting is true, but some neccesary methods are missing",
            ),
        ]
    )
    def test_plugin_pull_accouting_validation(self, name, plugin_info, implemented_methods=[], validation_msg=None):
        plugin_manager = PluginValidator()
        plugin_class = MagicMock(name="plugin_class")
        plugin_class.__dict__ = {method: ... for method in implemented_methods}
        error = plugin_manager.validate_pull_accounting(plugin_info, plugin_class)
        if validation_msg or error:
            self.assertEquals(validation_msg, error.split(".")[0])


class PluginTestCase(TestCase):
    handler_class = ServicePlugin
    tags = ("plugin",)

    _characteristics = [
        {
            "name": "orderId",
            "description": "Order identifier",
            "configurable": False,
            "usageSpecCharacteristicValue": [{"valueType": "string", "default": False, "value": ""}],
        },
        {
            "name": "productId",
            "description": "Product identifier",
            "configurable": False,
            "usageSpecCharacteristicValue": [{"valueType": "string", "default": False, "value": ""}],
        },
        {
            "name": "correlationNumber",
            "description": "Accounting correlation number",
            "configurable": False,
            "usageSpecCharacteristicValue": [{"valueType": "number", "default": False, "value": ""}],
        },
        {
            "name": "unit",
            "description": "Accounting unit",
            "configurable": False,
            "usageSpecCharacteristicValue": [{"valueType": "string", "default": False, "value": ""}],
        },
        {
            "name": "value",
            "description": "Accounting value",
            "configurable": False,
            "usageSpecCharacteristicValue": [{"valueType": "number", "default": False, "value": ""}],
        },
    ]

    _call_spec = {"name": "api call", "description": "api calls"}

    _call_specification = {
        "name": "api call",
        "description": "api calls",
        "usageSpecCharacteristic": deepcopy(_characteristics),
    }

    _second_spec = {"name": "second", "description": "seconds of usage"}

    _second_specification = {
        "name": "second",
        "description": "seconds of usage",
        "usageSpecCharacteristic": deepcopy(_characteristics),
    }

    _option = {
        "usage": {
            "api call": "http://uploadedspec.com/spec/1",
        }
    }

    _order_id = "20"
    _product_id = "10"
    _org_name = "TestCustomer"
    _org_url = "http://exampleserver/party1"
    _date = "2017-06-06"

    _usage_record = {
        "type": "event",
        "status": "Received",
        "date": _date,
        "usageSpecification": {
            "href": "http://uploadedspec.com/spec/1",
            "name": "api call",
        },
        "usageCharacteristic": [
            {"name": "orderId", "value": _order_id},
            {"name": "productId", "value": _product_id},
            {"name": "unit", "value": "api call"},
            {"name": "correlationNumber", "value": 0},
            {"name": "value", "value": 130},
        ],
        "relatedParty": [{"role": "customer", "id": _org_name, "href": _org_url}],
    }

    def setUp(self):
        self._model = MagicMock()
        self._model.options = {}

        self._usage_client = MagicMock()
        plugin.UsageClient = MagicMock(return_value=self._usage_client)

    def _call_configured(self):
        self._model.options = self._option

    def _not_called(self):
        self.assertEqual(0, self._usage_client.create_usage_spec.call_count)
        self.assertEquals({}, self._model.options)

    def _not_called_conf(self):
        self.assertEqual(0, self._usage_client.create_usage_spec.call_count)
        self.assertEquals(self._option, self._model.options)

    def _specs_created(self):
        self.assertEquals(
            [call(self._call_specification), call(self._second_specification)],
            self._usage_client.create_usage_spec.call_args_list,
        )

    @parameterized.expand(
        [
            ("empty_specs", [], _not_called),
            ("already_config", [_call_spec], _not_called_conf, _call_configured),
            ("spec_created", [_call_spec, _second_spec], _specs_created, None),
        ]
    )
    def test_usage_spec_conf(self, name, specs, validator, side_effect=None):
        if side_effect is not None:
            side_effect(self)

        plugin_handler = self.handler_class(self._model)
        plugin_handler.get_usage_specs = MagicMock(return_value=specs)

        plugin_handler.configure_usage_spec()

        plugin.UsageClient.assert_called_once_with()
        validator(self)

    def test_usage_spec_error(self):
        plugin_handler = self.handler_class(self._model)
        plugin_handler.get_usage_specs = MagicMock(return_value=[{}])

        try:
            plugin_handler.configure_usage_spec()
        except PluginError as e:
            self.assertEquals(
                "Plugin Error: Invalid product specification configuration, must include name and description",
                str(e),
            )

    def _not_found_spec(self):
        error = HTTPError()
        error.response = MagicMock(status_code=404)
        self._usage_client.delete_usage_spec.side_effect = error

    def _delete_not_called(self):
        self.assertEquals(0, plugin.UsageClient.call_count)
        self.assertEquals(0, self._usage_client.delete_usage_spec.call_count)

    def _delete_called(self):
        plugin.UsageClient.assert_called_once_with()
        self.assertEquals([call("1"), call("2")], self._usage_client.delete_usage_spec.call_args_list)

    def _already_deleted(self):
        plugin.UsageClient.assert_called_once_with()
        self._usage_client.delete_usage_spec.assert_called_once_with("1")

    @parameterized.expand(
        [
            ("not_usage", {}, _delete_not_called),
            (
                "multiple_units",
                {
                    "usage": {
                        "api call": "http://uploadedspec.com/spec/1",
                        "second": "http://uploadedspec.com/spec/2",
                    }
                },
                _delete_called,
            ),
            ("already_deleted", _option, _already_deleted, _not_found_spec),
        ]
    )
    def test_remove_usage_specs(self, name, options, validator, side_effect=None):
        self._model.options = options

        if side_effect:
            side_effect(self)

        plugin_handler = self.handler_class(self._model)

        plugin_handler.remove_usage_specs()

        validator(self)

    def test_remove_usage_spec_error(self):
        self._model.options = self._option

        error = HTTPError()
        error.response = MagicMock(status_code=500)
        self._usage_client.delete_usage_spec.side_effect = error

        plugin_handler = self.handler_class(self._model)

        try:
            plugin_handler.remove_usage_specs()
        except HTTPError as e:
            self.assertEquals(500, e.response.status_code)

    def _mock_order(self):
        asset = MagicMock()
        contract = MagicMock(product_id=self._product_id, correlation_number=0)

        order = MagicMock(order_id=self._order_id)
        order.owner_organization.name = self._org_name
        order.owner_organization.get_party_url.return_value = self._org_url

        return asset, contract, order

    @parameterized.expand(
        [
            ("empty_uses", ([], None)),
            (
                "pending_usage",
                ([{"date": _date, "unit": "api call", "value": 130}], "2017-06-06"),
            ),
        ]
    )
    def test_usage_refresh(self, name, usages):
        self._model.options = self._option
        self._model.pull_accounting = True

        self._usage_client.create_usage.return_value = {"id": "1"}

        plugin_handler = self.handler_class(self._model)
        plugin_handler.get_pending_accounting = MagicMock(return_value=usages)

        asset, contract, order = self._mock_order()

        plugin_handler.on_usage_refresh(asset, contract, order)

        plugin_handler.get_pending_accounting.assert_called_once_with(asset, contract, order)
        plugin.UsageClient.assert_called_once_with()

        if len(usages[0]):
            # Check calls
            self._usage_client.create_usage.assert_called_once_with(self._usage_record)
            self._usage_client.update_usage_state.assert_called_once_with("1", "Guided")

            self.assertEquals(1, contract.correlation_number)
            self.assertEquals(usages[1], contract.last_usage)
            self.assertEquals([call(), call()], order.save.call_args_list)

    def test_usage_refresh_error(self):
        plugin_handler = self.handler_class(self._model)
        plugin_handler.get_pending_accounting = MagicMock(return_value=([{}], None))

        asset, contract, order = self._mock_order()
        try:
            plugin_handler.on_usage_refresh(asset, contract, order)
        except PluginError as e:
            self.assertEquals(
                "Plugin Error: Invalid usage record, it must include date, unit and value",
                str(e),
            )

    def test_usage_refresh_not_pull(self):
        self._model.pull_accounting = False
        plugin_handler = self.handler_class(self._model)
        plugin_handler.get_pending_accounting = MagicMock(return_value=([], None))

        plugin_handler.on_usage_refresh(None, None, None)
        self.assertEquals(0, plugin_handler.get_pending_accounting.call_count)


class ResourcePluginAccountingTests(PluginTestCase):
    handler_class = ResourcePluginHandler


class DecoratorsTestCase(TestCase):
    tags = ("decorators",)

    def setUp(self):
        self._module = MagicMock()
        decorators.load_plugin_module = MagicMock(return_value=self._module)
        self._order = MagicMock()
        self._contract = MagicMock()

    def tearDown(self):
        reload(decorators)

    def _get_offering_mock(self, bundle_asset=False):
        offering = MagicMock(is_digital=True, pk="61004aba5e05acc115f022f0")
        asset = MagicMock(resource_type="asset")

        if bundle_asset:
            asset.bundled_assets = ["3", "4"]
        else:
            asset.bundled_assets = []

        offering.asset = asset
        return offering

    # def test_product_suspended(self):
    #     self._contract.offering = "61004aba5e05acc115f022f0"
    #     offering = self._get_offering_mock()

    #     decorators.Offering = MagicMock()
    #     decorators.Offering.objects.get.return_value = offering

    #     decorators.on_product_suspended(self._order, self._contract)

    #     decorators.Offering.objects.get.assert_called_once_with(pk=ObjectId("61004aba5e05acc115f022f0"))
    #     decorators.load_plugin_module.assert_called_once_with("asset")
    #     self._module.on_product_suspension.assert_called_once_with(offering.asset, self._contract, self._order)

    # def test_usage_refreshed(self):
    #     self._contract.offering = "61004aba5e05acc115f022f0"
    #     offering = self._get_offering_mock()

    #     decorators.Offering = MagicMock()
    #     decorators.Offering.objects.get.return_value = offering

    #     decorators.on_usage_refreshed(self._order, self._contract)

    #     decorators.Offering.objects.get.assert_called_once_with(pk=ObjectId("61004aba5e05acc115f022f0"))
    #     decorators.load_plugin_module.assert_called_once_with("asset")
    #     self._module.on_usage_refresh.assert_called_once_with(offering.asset, self._contract, self._order)


class ServiceActivationDispatchTests(SimpleTestCase):
    def setUp(self):
        self.provider = object()
        self.buyer = object()
        self.order = {"id": "order-1", "productOrderItem": [{"id": "item-1"}]}
        self.contract = object()
        self.product = {"id": "product-1", "realizingService": [{"id": "service-1"}, {"id": "service-2"}]}
        self.services = {
            f"service-{n}": {
                "id": f"service-{n}",
                "serviceCharacteristic": [
                    {"name": "Service Type", "value": f"category-{n}"},
                    {"name": "File", "value": f"file-{n}"},
                    {"name": "enabled", "value": "False"},
                ],
            }
            for n in (1, 2)
        }
        self.product["relatedParty"] = [
            {"id": "provider-party", "role": "sElLeR"},
            {"id": "buyer-party", "role": "bUyEr"},
            {"id": "operator-party", "role": "SellerOperator"},
        ]
        self.models = {f"category-{n}": object() for n in (1, 2)}
        self.plugins = {f"category-{n}": Mock() for n in (1, 2)}
        self.modules = {model: self.plugins[category] for category, model in self.models.items()}
        for name in ("InventoryClient", "_get_plugin_model", "_load_plugin_model", "Organization"):
            patcher = patch.object(decorators, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        patcher = patch("wstore.store_commons.service_catalog.ServiceCatalog.get_specification")
        self.catalog_read = patcher.start()
        self.addCleanup(patcher.stop)
        self.Organization.objects.get.side_effect = lambda actor_id: {
            "provider-party": self.provider,
            "buyer-party": self.buyer,
        }[actor_id]
        self.inventory = self.InventoryClient.return_value
        self.inventory.get_service.side_effect = self.services.__getitem__
        self._get_plugin_model.side_effect = lambda category_id, plugin_type: self.models.get(category_id)
        self._load_plugin_model.side_effect = self.modules.get

    def tearDown(self):
        self.catalog_read.assert_not_called()

    def dispatch(self, contract=None):
        return decorators.on_product_activation(self.product, self.order, contract)

    def test_each_plugin_receives_its_inventory_service_and_purchase_arguments(self):
        self.dispatch(self.contract)
        self.assertEqual([call("service-1"), call("service-2")], self.inventory.get_service.call_args_list)
        self.assertEqual(
            [
                call(category_id="category-1", plugin_type="service"),
                call(category_id="category-2", plugin_type="service"),
            ],
            self._get_plugin_model.call_args_list,
        )
        for n in (1, 2):
            self.plugins[f"category-{n}"].on_service_activation.assert_called_once_with(
                self.provider,
                self.buyer,
                self.services[f"service-{n}"],
                self.product,
                self.order,
                self.contract,
            )
        self.inventory.patch_product.assert_not_called()

    def test_contract_is_optional(self):
        self.dispatch()
        self.assertIsNone(self.plugins["category-1"].on_service_activation.call_args.args[-1])

    def test_ordinary_services_are_skipped_without_specification_lookup(self):
        for characteristics in (None, {}, [], [{"name": "File", "value": "file-1"}]):
            with self.subTest(characteristics=characteristics):
                self.services["service-1"]["serviceCharacteristic"] = characteristics
                self.services["service-1"]["serviceSpecification"] = {"id": "spec-1"}
                self.plugins["category-2"].reset_mock()
                self.dispatch()
                self.plugins["category-1"].on_service_activation.assert_not_called()
                self.plugins["category-2"].on_service_activation.assert_called_once()

    def test_category_without_installed_plugin_is_skipped(self):
        self.models.pop("category-1")
        self.dispatch()
        self.plugins["category-1"].on_service_activation.assert_not_called()
        self.plugins["category-2"].on_service_activation.assert_called_once()

    def test_characteristic_name_is_case_insensitive(self):
        self.services["service-1"]["serviceCharacteristic"][0]["name"] = " SERVICE TYPE "
        self.dispatch()
        self.plugins["category-1"].on_service_activation.assert_called_once()

    def test_same_category_dispatches_for_each_inventory_service(self):
        self.services["service-2"]["serviceCharacteristic"][0]["value"] = "category-1"
        self.dispatch()
        self.assertEqual(
            [
                call(self.provider, self.buyer, self.services["service-1"], self.product, self.order, None),
                call(self.provider, self.buyer, self.services["service-2"], self.product, self.order, None),
            ],
            self.plugins["category-1"].on_service_activation.call_args_list,
        )
        self.plugins["category-2"].on_service_activation.assert_not_called()

    def test_product_without_services_does_not_dispatch(self):
        self.product.pop("realizingService")
        self.dispatch()
        self.inventory.get_service.assert_not_called()
        self._get_plugin_model.assert_not_called()

    def test_invalid_service_references_stop_activation(self):
        for references in (None, {}, [None], [{}], [{"id": ""}], [{"id": 1}]):
            with self.subTest(references=references):
                self.product["realizingService"] = references
                with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ServiceError):
                    self.dispatch()
        self.inventory.get_service.assert_not_called()

    def test_invalid_reference_prevents_later_service_activation(self):
        self.product["realizingService"].insert(0, {})
        with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ServiceError):
            self.dispatch()
        self.plugins["category-1"].on_service_activation.assert_not_called()
        self.plugins["category-2"].on_service_activation.assert_not_called()

    def test_invalid_service_type_stops_activation(self):
        for characteristics in (
            [{"name": "Service Type", "value": ""}],
            [{"name": "Service Type", "value": {"id": "category-1"}}],
            [{"name": "Service Type"}],
            [{"name": "Service Type", "value": "category-1"}] * 2,
        ):
            with self.subTest(characteristics=characteristics):
                self.services["service-1"]["serviceCharacteristic"] = characteristics
                self.plugins["category-2"].reset_mock()
                with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ServiceError):
                    self.dispatch()
                self.plugins["category-1"].on_service_activation.assert_not_called()
                self.plugins["category-2"].on_service_activation.assert_not_called()

    def test_invalid_downloaded_services_stop_activation(self):
        for document in (None, [], {}, {"id": "different-id"}):
            with self.subTest(document=document):
                self.plugins["category-2"].reset_mock()
                self.inventory.get_service.side_effect = (
                    lambda id_: document if id_ == "service-1" else self.services[id_]
                )
                with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ServiceError):
                    self.dispatch()
                self.plugins["category-1"].on_service_activation.assert_not_called()
                self.plugins["category-2"].on_service_activation.assert_not_called()

    def test_read_and_plugin_failures_are_logged_and_propagated(self):
        for operation in (
            self.inventory.get_service,
            self._get_plugin_model,
            self._load_plugin_model,
            self.plugins["category-1"].on_service_activation,
        ):
            original = operation.side_effect
            for error_type in (PluginError, RuntimeError):
                with self.subTest(operation=operation, error_type=error_type):
                    self.plugins["category-2"].reset_mock()
                    error = error_type("notification failed")

                    def notify(*args, **kwargs):
                        if operation.call_count == 1:
                            raise error
                        return original(*args, **kwargs) if original else None

                    operation.reset_mock()
                    operation.side_effect = notify
                    with self.assertLogs("wstore.default_logger", level="ERROR") as logs:
                        with self.assertRaises(error_type) as raised:
                            self.dispatch()
                    self.assertIs(error, raised.exception)
                    for identifier in ("order-1", "product-1", "service-1"):
                        self.assertIn(identifier, logs.output[0])
                    self.assertIs(error, logs.records[0].exc_info[1])
                    self.plugins["category-2"].on_service_activation.assert_not_called()
            operation.side_effect = original

    def test_parties_are_resolved_once_for_all_services(self):
        self.dispatch()
        self.assertEqual(
            [call(actor_id="provider-party"), call(actor_id="buyer-party")],
            self.Organization.objects.get.call_args_list,
        )

    @override_settings(PROVIDER_ROLE="Vendor", CUSTOMER_ROLE="Purchaser")
    def test_organization_resolution_uses_configured_roles(self):
        self.product["relatedParty"][0]["role"] = "vEnDoR"
        self.product["relatedParty"][1]["role"] = "pUrChAsEr"
        self.dispatch()
        self.plugins["category-1"].on_service_activation.assert_called_once_with(
            self.provider,
            self.buyer,
            self.services["service-1"],
            self.product,
            self.order,
            None,
        )

    def test_missing_or_ambiguous_organizations_stop_activation(self):
        for parties in (
            [],
            [{"id": "provider-party", "role": "Seller"}],
            [{"id": "buyer-party", "role": "Buyer"}],
            [{"id": "a", "role": "Seller"}, {"id": "b", "role": "Seller"}],
        ):
            with self.subTest(parties=parties):
                self.product["relatedParty"] = parties
                with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ServiceError):
                    self.dispatch()
                for plugin in self.plugins.values():
                    plugin.on_service_activation.assert_not_called()

    def test_organization_lookup_failure_is_propagated(self):
        self.Organization.objects.get.side_effect = RuntimeError("organization unavailable")
        with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(RuntimeError):
            self.dispatch()
        for plugin in self.plugins.values():
            plugin.on_service_activation.assert_not_called()

    def test_ordinary_services_do_not_require_organizations(self):
        for service in self.services.values():
            service.pop("serviceCharacteristic")
        self.product.pop("relatedParty")
        self.dispatch()
        self.Organization.objects.get.assert_not_called()


class ResourceActivationDispatchTests(SimpleTestCase):
    def setUp(self):
        ServiceActivationDispatchTests.setUp(self)
        self.product.pop("realizingService")
        self.product["realizingResource"] = [{"id": "resource-1"}, {"id": "resource-2"}]
        self.resources = {
            f"resource-{n}": {
                "id": f"resource-{n}",
                "resourceCharacteristic": [
                    {"name": "Resource Type", "value": f"category-{n}"},
                    {"name": "File", "value": f"file-{n}"},
                ],
            }
            for n in (1, 2)
        }
        self.resource_plugins = {f"category-{n}": Mock(spec=ResourcePluginHandler) for n in (1, 2)}
        typed_plugins = {
            **{("service", category): plugin for category, plugin in self.plugins.items()},
            **{("resource", category): plugin for category, plugin in self.resource_plugins.items()},
        }
        self.inventory.get_resource.side_effect = self.resources.__getitem__
        self._get_plugin_model.side_effect = lambda category_id, plugin_type: (
            (plugin_type, category_id) if (plugin_type, category_id) in typed_plugins else None
        )
        self._load_plugin_model.side_effect = typed_plugins.get
        patcher = patch("wstore.store_commons.resource_catalog.ResourceCatalog.get_specification")
        self.resource_catalog_read = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        ServiceActivationDispatchTests.tearDown(self)
        self.resource_catalog_read.assert_not_called()

    def dispatch(self, contract=None):
        return decorators.on_product_activation(self.product, self.order, contract)

    def test_resource_only_product_dispatches_inventory_instances_with_both_organizations(self):
        self.dispatch(self.contract)
        self.inventory.get_service.assert_not_called()
        for n in (1, 2):
            self.resource_plugins[f"category-{n}"].on_resource_activation.assert_called_once_with(
                self.provider,
                self.buyer,
                self.resources[f"resource-{n}"],
                self.product,
                self.order,
                self.contract,
            )
        self.inventory.patch_product.assert_not_called()

    def test_mixed_product_uses_separate_plugins_for_identical_category_ids(self):
        self.product["realizingService"] = [{"id": "service-1"}]
        self.dispatch()
        self.plugins["category-1"].on_service_activation.assert_called_once_with(
            self.provider,
            self.buyer,
            self.services["service-1"],
            self.product,
            self.order,
            None,
        )
        self.resource_plugins["category-1"].on_resource_activation.assert_called_once_with(
            self.provider,
            self.buyer,
            self.resources["resource-1"],
            self.product,
            self.order,
            None,
        )
        self.assertEqual(2, self.Organization.objects.get.call_count)

    def test_ordinary_resources_and_uninstalled_categories_skip_callbacks(self):
        self.resources["resource-1"]["resourceCharacteristic"] = []
        self.resources["resource-1"]["resourceSpecification"] = {"id": "spec-not-to-be-fetched"}
        self.resources["resource-2"]["resourceCharacteristic"][0]["value"] = "uninstalled"
        self.dispatch()
        for plugin in self.resource_plugins.values():
            plugin.on_resource_activation.assert_not_called()
        self.Organization.objects.get.assert_not_called()

    def test_resources_sharing_plugin_receive_their_own_instances(self):
        self.resources["resource-2"]["resourceCharacteristic"][0]["value"] = "category-1"
        self.dispatch()
        self.assertEqual(
            [
                call(self.provider, self.buyer, self.resources["resource-1"], self.product, self.order, None),
                call(self.provider, self.buyer, self.resources["resource-2"], self.product, self.order, None),
            ],
            self.resource_plugins["category-1"].on_resource_activation.call_args_list,
        )

    def test_resource_type_names_are_case_insensitive(self):
        self.resources["resource-1"]["resourceCharacteristic"][0]["name"] = " RESOURCE TYPE "
        self.dispatch()
        self.resource_plugins["category-1"].on_resource_activation.assert_called_once()

    def test_plugin_failure_stops_resource_activation(self):
        self.resource_plugins["category-1"].on_resource_activation.side_effect = RuntimeError("failed")
        with self.assertLogs("wstore.default_logger", level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                self.dispatch()
        for identifier in ("order-1", "product-1", "resource-1"):
            self.assertIn(identifier, logs.output[0])
        self.resource_plugins["category-2"].on_resource_activation.assert_not_called()

    def test_service_plugin_failure_prevents_resource_activation(self):
        self.product["realizingService"] = [{"id": "service-1"}]
        self.plugins["category-1"].on_service_activation.side_effect = PluginError("failed")
        with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(PluginError):
            self.dispatch()
        self.resource_plugins["category-1"].on_resource_activation.assert_not_called()

    def test_malformed_domain_collection_stops_activation(self):
        for field, other, plugin, handler in (
            (
                "realizingService",
                "realizingResource",
                self.resource_plugins["category-1"],
                "on_resource_activation",
            ),
            ("realizingResource", "realizingService", self.plugins["category-1"], "on_service_activation"),
        ):
            with self.subTest(field=field):
                self.product[field] = {}
                self.product[other] = [{"id": "resource-1" if other == "realizingResource" else "service-1"}]
                plugin.reset_mock()
                error = ServiceError if field == "realizingService" else ResourceError
                with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(error):
                    self.dispatch()
                if field == "realizingService":
                    getattr(plugin, handler).assert_not_called()
                else:
                    # Services run before resources; successful work is not rolled back.
                    getattr(plugin, handler).assert_called_once()

    def test_invalid_resource_reference_stops_activation(self):
        self.product["realizingResource"].insert(0, {})
        with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ResourceError):
            self.dispatch()
        self.resource_plugins["category-1"].on_resource_activation.assert_not_called()
        self.resource_plugins["category-2"].on_resource_activation.assert_not_called()

    def test_resource_read_failure_stops_activation(self):
        def read(id_):
            if id_ == "resource-1":
                raise RuntimeError("inventory offline")
            return self.resources[id_]

        self.inventory.get_resource.side_effect = read
        with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(RuntimeError):
            self.dispatch()
        self.resource_plugins["category-1"].on_resource_activation.assert_not_called()
        self.resource_plugins["category-2"].on_resource_activation.assert_not_called()

    def test_invalid_resource_identity_stops_activation(self):
        self.resources["resource-1"]["id"] = "wrong-resource"
        with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ResourceError):
            self.dispatch()
        self.resource_plugins["category-1"].on_resource_activation.assert_not_called()
        self.resource_plugins["category-2"].on_resource_activation.assert_not_called()

    def test_invalid_or_duplicate_resource_type_stops_activation(self):
        for entries in (
            [{"name": "Resource Type", "value": {"id": "category-1"}}],
            [{"name": "Resource Type", "value": "category-1"}] * 2,
        ):
            with self.subTest(entries=entries):
                self.resources["resource-1"]["resourceCharacteristic"] = entries
                self.resource_plugins["category-2"].reset_mock()
                with self.assertLogs("wstore.default_logger", level="ERROR"), self.assertRaises(ResourceError):
                    self.dispatch()
                self.resource_plugins["category-1"].on_resource_activation.assert_not_called()
                self.resource_plugins["category-2"].on_resource_activation.assert_not_called()


class RecordingPlugin(ServicePlugin):
    pass


class RecordingResourcePlugin(ResourcePluginHandler):
    pass


class PackageManagementTests(SimpleTestCase):
    plugin_type = "service"
    catalog_class = ServiceCatalog
    catalog_error = ServiceCatalogError
    handler_class = RecordingPlugin

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.catalog_patch = patch(
            "wstore.asset_manager.resource_plugins.plugin_loader." + self.catalog_class.__name__
        )
        self.catalog = self.catalog_patch.start().return_value
        self.addCleanup(self.catalog_patch.stop)
        self.catalog.create_category.return_value = "category-1"
        usage_patch = patch.object(plugin_loader.requests, "get")
        self.usage_get = usage_patch.start()
        self.usage_get.return_value.json.return_value = []
        self.addCleanup(usage_patch.stop)
        self.loader = PluginLoader()
        self.loader._plugins_path = self.directory.name
        self.loader._get_plugin_module = Mock(return_value=self.handler_class)
        self.save = patch.object(ResourcePlugin, "save").start()
        self.delete = patch.object(ResourcePlugin, "delete").start()
        self.addCleanup(patch.stopall)
        self.model = ResourcePlugin(
            plugin_id="test",
            type=self.plugin_type,
            name="test",
            version="1.0",
            category_id="category-1",
            version_history=[],
            module="previous.Plugin",
            requires_file=False,
        )
        self.lookup = patch.object(ResourcePlugin.objects, "get", return_value=self.model).start()

    def package(self, version, requires_file=False):
        path = os.path.join(self.directory.name, "package.zip")
        with ZipFile(path, "w") as archive:
            archive.writestr(
                "package.json",
                json.dumps(
                    {
                        "name": "test",
                        "version": version,
                        "author": "author",
                        "module": "test.Plugin",
                        "type": self.plugin_type,
                        "requires_file": requires_file,
                    }
                ),
            )
        return path

    def test_install_creates_category_and_retains_local_asset_type(self):
        self.lookup.side_effect = ObjectDoesNotExist
        with patch.object(
            self.loader, "_update_model_data_from_json", wraps=self.loader._update_model_data_from_json
        ) as update:
            self.assertEqual("test", self.loader.install_plugin(self.package("1.0")))
        model = update.call_args.args[0]
        self.assertEqual("category-1", model.category_id)
        self.assertEqual("test", model.plugin_id)
        self.assertEqual(self.plugin_type, model.type)
        self.assertIs(False, model.requires_file)
        self.catalog.create_category.assert_called_once_with("test", "1.0")

    def test_upgrade_keeps_category_identity(self):
        self.loader.install_plugin(self.package("2.0", requires_file=True))
        self.assertIs(True, self.model.requires_file)
        self.assertEqual("category-1", self.model.category_id)
        self.assertEqual(["1.0"], self.model.version_history)
        self.catalog.create_category.assert_not_called()
        self.catalog.update_category.assert_called_once_with("category-1", "test", "2.0")

    def test_failed_upgrade_restores_previous_installation(self):
        self.save.side_effect = [RuntimeError("save failed"), None]
        with self.assertRaises(RuntimeError):
            self.loader.install_plugin(self.package("2.0"))
        self.assertEqual("1.0", self.model.version)
        self.assertEqual([], self.model.version_history)
        self.assertEqual("previous.Plugin", self.model.module)
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-2-0")))
        self.assertEqual(("category-1", "test", "1.0"), self.catalog.update_category.call_args.args)
        self.delete.assert_not_called()

    def test_failed_install_removes_only_new_category(self):
        self.lookup.side_effect = ObjectDoesNotExist
        self.save.side_effect = RuntimeError("save failed")
        with self.assertRaises(RuntimeError):
            self.loader.install_plugin(self.package("1.0"))
        self.catalog.delete_category.assert_called_once_with("category-1")
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-1-0")))

    def test_catalog_failure_leaves_package_installed(self):
        self.catalog.delete_category.side_effect = HTTPError("offline")
        with self.assertRaises(HTTPError):
            self.loader.uninstall_plugin("test")
        self.delete.assert_not_called()

    def test_invalid_usage_response_retains_plugin_error_and_installed_files(self):
        path = os.path.join(self.directory.name, "test-1-0")
        os.mkdir(path)
        self.usage_get.return_value.json.return_value = {"error": "invalid specification collection"}
        with self.assertRaises(PluginUsageError):
            self.loader.uninstall_plugin("test")
        self.assertTrue(os.path.isdir(path))
        self.delete.assert_not_called()
        self.catalog.delete_category.assert_not_called()

    def test_invalid_category_response_retains_plugin_error_and_rolls_back_install(self):
        self.lookup.side_effect = ObjectDoesNotExist
        setattr(
            self.loader,
            "_catalog" if self.plugin_type == "service" else "_resource_catalog",
            self.catalog_class(),
        )

        with patch("wstore.store_commons.service_catalog.requests.request") as request:
            request.return_value.json.return_value = {}
            with self.assertRaises(PluginError) as error:
                self.loader.install_plugin(self.package("1.0"))

        self.assertIsInstance(error.exception.__cause__, self.catalog_error)
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-1-0")))
        self.save.assert_not_called()

    def test_removal_deletes_actual_version_directories(self):
        self.model.version_history = ["0.1"]
        for directory in ["test-0-1", "test-1-0", "test-other-1-0"]:
            os.mkdir(os.path.join(self.directory.name, directory))
        self.loader.uninstall_plugin("test")
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-0-1")))
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-1-0")))
        self.assertTrue(os.path.isdir(os.path.join(self.directory.name, "test-other-1-0")))
        self.catalog.delete_category.assert_called_once_with("category-1")
        self.delete.assert_called_once_with()

    def test_existing_installation_can_publish_missing_category(self):
        self.model.category_id = None
        self.assertEqual("category-1", self.loader.synchronize_plugin_category("test"))
        self.loader.synchronize_plugin_category("test")
        self.catalog.create_category.assert_called_once_with("test", "1.0")

    def test_missing_category_blocks_removal(self):
        self.model.category_id = None
        with self.assertRaises(PluginError):
            self.loader.uninstall_plugin("test")
        self.delete.assert_not_called()

    def test_downgrade_keeps_category(self):
        self.model.version = "2.0"
        self.model.version_history = ["1.0"]
        path = os.path.join(self.directory.name, "test-1-0")
        os.mkdir(path)
        with open(os.path.join(path, "package.json"), "w") as manifest:
            json.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "author": "author",
                    "module": "test.Plugin",
                    "requires_file": False,
                    "type": self.plugin_type,
                },
                manifest,
            )
        os.mkdir(os.path.join(self.directory.name, "test-2-0"))
        self.loader.downgrade_plugin("test")
        self.assertEqual("1.0", self.model.version)
        self.assertEqual("category-1", self.model.category_id)
        self.catalog.update_category.assert_called_once_with("category-1", "test", "1.0")

    def test_install_imports_the_declared_domain_handler_from_real_package(self):
        namespace = "typed_plugin_" + self.plugin_type
        root = os.path.join(self.directory.name, namespace)
        os.mkdir(root)
        with open(os.path.join(root, "__init__.py"), "w"):
            pass
        self.loader._plugins_path = root
        self.loader._plugins_module = namespace + "."
        self.loader._get_plugin_module = PluginLoader._get_plugin_module.__get__(self.loader)
        self.lookup.side_effect = ObjectDoesNotExist
        package = self.package("1.0")
        module = "plugin"
        handler = "ServicePlugin" if self.plugin_type == "service" else "ResourcePlugin"
        with ZipFile(package, "r") as archive:
            info = json.loads(archive.read("package.json"))
        info["module"] = "implementation.Installed"
        with ZipFile(package, "w") as archive:
            archive.writestr("package.json", json.dumps(info))
            archive.writestr(
                "implementation.py",
                (
                    f"from wstore.asset_manager.resource_plugins.{module} import {handler}\n"
                    f"class Installed({handler}):\n    pass\n"
                ),
            )
        try:
            with patch.object(sys, "path", [self.directory.name] + sys.path):
                self.assertEqual("test", self.loader.install_plugin(package))
        finally:
            for name in list(sys.modules):
                if name == namespace or name.startswith(namespace + "."):
                    sys.modules.pop(name)
        self.catalog.create_category.assert_called_once_with("test", "1.0")

    def test_wrong_handler_class_is_rejected_before_catalog_writes(self):
        self.lookup.side_effect = ObjectDoesNotExist
        wrong = RecordingResourcePlugin if self.plugin_type == "service" else RecordingPlugin
        self.loader._get_plugin_module.return_value = wrong
        with self.assertRaises(PluginError):
            self.loader.install_plugin(self.package("1.0"))
        self.catalog.create_category.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-1-0")))

    def test_shared_parent_alone_is_not_a_domain_handler(self):
        self.lookup.side_effect = ObjectDoesNotExist
        self.loader._get_plugin_module.return_value = Plugin
        with self.assertRaises(PluginError):
            self.loader.install_plugin(self.package("1.0"))
        self.catalog.create_category.assert_not_called()

    def test_upgrade_cannot_switch_catalog_type(self):
        self.model.type = "resource" if self.plugin_type == "service" else "service"
        with self.assertRaisesRegex(PluginError, "cannot change type"):
            self.loader.install_plugin(self.package("2.0"))
        self.catalog.update_category.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-2-0")))

    def test_other_catalog_is_not_used(self):
        self.lookup.side_effect = ObjectDoesNotExist
        other = Mock()
        setattr(self.loader, "_resource_catalog" if self.plugin_type == "service" else "_catalog", other)
        self.loader.install_plugin(self.package("1.0"))
        self.assertEqual([], other.mock_calls)

    @parameterized.expand([
        ("traversal", "../escaped.py"),
        ("absolute", "/escaped.py"),
        ("drive", "C:/escaped.py"),
        ("nested_escape", "dir/../../escaped.py"),
        ("windows_escape", "dir\\..\\..\\escaped.py"),
        ("unc", "\\\\server/share/escaped.py"),
    ])
    def test_unsafe_archive_entry_is_rejected_before_mutation(self, _, name):
        package = self.package("2.0")
        with ZipFile(package, "a") as archive:
            archive.writestr(name, "payload")
        with self.assertRaises(PluginError):
            self.loader.install_plugin(package)
        self.lookup.assert_not_called()
        self.loader._get_plugin_module.assert_not_called()
        self.catalog.update_category.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-2-0")))

    @parameterized.expand([
        ("windows", 0, 0x20),
        ("unix_link_metadata", 3, 0o120777 << 16),
        ("other_platform_attributes", 0, 0xFFFFFFFF),
    ])
    def test_archive_attributes_do_not_control_extracted_file_type(self, _, system, attributes):
        package = self.package("2.0")
        entry = ZipInfo("payload.txt")
        entry.create_system = system
        entry.external_attr = attributes
        with ZipFile(package, "a") as archive:
            archive.writestr(entry, "../target")
        self.loader.install_plugin(package)
        path = os.path.join(self.directory.name, "test-2-0", "payload.txt")
        self.assertTrue(os.path.isfile(path))
        self.assertFalse(os.path.islink(path))
        with open(path) as payload:
            self.assertEqual("../target", payload.read())

    @parameterized.expand([
        ("dot", "./payload.txt", "payload.txt"),
        ("repeated_separator", "helpers//payload.txt", "helpers/payload.txt"),
        ("backslash", "helpers\\payload.txt", "helpers/payload.txt"),
        ("internal_parent", "helpers/../payload.txt", "payload.txt"),
    ])
    def test_safe_relative_paths_are_normalized(self, _, name, expected):
        package = self.package("2.0")
        with ZipFile(package, "a") as archive:
            archive.writestr(name, "payload")
            archive.writestr("./", "")
            archive.writestr("empty\\", "")
        self.loader.install_plugin(package)
        root = os.path.join(self.directory.name, "test-2-0")
        with open(os.path.join(root, *expected.split("/"))) as payload:
            self.assertEqual("payload", payload.read())
        self.assertTrue(os.path.isdir(os.path.join(root, "empty")))

    @parameterized.expand([
        ("stored", zipfile.ZIP_STORED),
        ("deflate", zipfile.ZIP_DEFLATED),
        ("bzip2", zipfile.ZIP_BZIP2),
        ("lzma", zipfile.ZIP_LZMA),
    ])
    def test_compression_support_is_delegated_to_python(self, _, compression):
        package = self.package("2.0")
        with ZipFile(package) as archive:
            manifest = archive.read("package.json")
        with ZipFile(package, "w", compression=compression) as archive:
            archive.writestr("package.json", manifest)
            archive.writestr("payload.txt", "compressed payload")
        self.loader.install_plugin(package)
        with open(os.path.join(self.directory.name, "test-2-0", "payload.txt")) as payload:
            self.assertEqual("compressed payload", payload.read())

    def test_native_zip_read_error_is_reported_before_installation(self):
        package = self.package("2.0")
        with patch.object(ZipFile, "read", side_effect=RuntimeError("Password required")):
            with self.assertRaisesRegex(PluginError, "Plugin archive could not be read"):
                self.loader.install_plugin(package)
        self.lookup.assert_not_called()
        self.loader._get_plugin_module.assert_not_called()

    def test_native_zip_crc_error_rolls_back_partial_extraction(self):
        package = self.package("2.0")
        payload = b"unique payload to corrupt after archive creation"
        with ZipFile(package, "a") as archive:
            archive.writestr("payload.txt", payload)
        with open(package, "rb") as source:
            data = bytearray(source.read())
        data[data.index(payload)] ^= 1
        with open(package, "wb") as target:
            target.write(data)
        with self.assertRaisesRegex(PluginError, "Invalid plugin archive contents"):
            self.loader.install_plugin(package)
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-2-0")))
        self.lookup.assert_not_called()
        self.loader._get_plugin_module.assert_not_called()

    def test_duplicate_normalized_paths_are_rejected(self):
        package = self.package("2.0")
        with ZipFile(package, "a") as archive:
            archive.writestr("payload.txt", "first")
            archive.writestr("./payload.txt", "second")
        with self.assertRaisesRegex(PluginError, "duplicate entry paths"):
            self.loader.install_plugin(package)
        self.lookup.assert_not_called()

    def test_conflicting_archive_paths_are_rejected(self):
        package = self.package("2.0")
        with ZipFile(package, "a") as archive:
            archive.writestr("module", "file")
            archive.writestr("module/child.py", "child")
        with self.assertRaises(PluginError):
            self.loader.install_plugin(package)
        self.lookup.assert_not_called()

    def test_duplicate_manifest_is_rejected(self):
        import warnings
        package = self.package("2.0")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(package, "a") as archive:
                archive.writestr("package.json", "{}")
        with self.assertRaises(PluginError):
            self.loader.install_plugin(package)
        self.lookup.assert_not_called()

    @parameterized.expand([
        ("expanded", "PLUGIN_EXPANDED_MAX_BYTES", 1),
        ("entries", "PLUGIN_ARCHIVE_MAX_ENTRIES", 0),
    ])
    def test_archive_limits_are_enforced_before_mutation(self, _, setting, limit):
        with override_settings(**{setting: limit}):
            with self.assertRaises(PluginSizeError):
                self.loader.install_plugin(self.package("2.0"))
        self.lookup.assert_not_called()
        self.loader._get_plugin_module.assert_not_called()

    def test_actual_expansion_limit_removes_partially_extracted_package(self):
        package = self.package("2.0")
        with ZipFile(package) as archive:
            entries = self.loader._validate_archive(archive)
        with patch.object(self.loader, "_validate_archive", return_value=entries):
            with override_settings(PLUGIN_EXPANDED_MAX_BYTES=1):
                with self.assertRaises(PluginSizeError):
                    self.loader.install_plugin(package)
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-2-0")))

    def test_package_mutations_share_a_nonblocking_lock(self):
        package = self.package("2.0")
        with open(os.path.join(self.directory.name, ".package-management.lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            operations = (
                lambda: self.loader.install_plugin(package),
                lambda: self.loader.downgrade_plugin("test"),
                lambda: self.loader.uninstall_plugin("test"),
                lambda: self.loader.synchronize_plugin_category("test"),
            )
            for operation in operations:
                with self.assertRaises(PluginConflictError):
                    operation()
        self.lookup.assert_not_called()
        self.loader.install_plugin(package)
        self.assertEqual("2.0", self.model.version)

    def test_another_process_cannot_mutate_while_management_lock_is_held(self):
        code = """
import sys
from types import SimpleNamespace
from wstore.asset_manager.resource_plugins.plugin_rollback import package_management
from wstore.asset_manager.resource_plugins.plugin_error import PluginConflictError
@package_management
def mutate(instance):
    raise AssertionError('Concurrent mutation was admitted')
try:
    mutate(SimpleNamespace(_plugins_path=sys.argv[1]))
except PluginConflictError:
    pass
else:
    raise AssertionError('No conflict reported')
"""
        with open(os.path.join(self.directory.name, ".package-management.lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run(
                [sys.executable, "-c", code, self.directory.name],
                env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_rollback_holds_lock_until_cleanup_finishes(self):
        original = self.loader._clear_module_namespace
        def cleanup(namespace):
            with self.assertRaises(PluginConflictError):
                self.loader.synchronize_plugin_category("test")
            original(namespace)
        self.loader._clear_module_namespace = Mock(side_effect=cleanup)
        self.save.side_effect = [RuntimeError("save failed"), None]
        with self.assertRaises(RuntimeError):
            self.loader.install_plugin(self.package("2.0"))
        self.loader._clear_module_namespace.assert_called_once()
        self.lookup.reset_mock()
        self.loader.synchronize_plugin_category("test")
        self.lookup.assert_called_once()

    def test_failed_install_clears_only_attempted_module_namespace(self):
        namespace = self.loader._plugins_module + "test-2-0"
        previous = self.loader._plugins_module + "test-1-0"
        sentinel = types.ModuleType(previous)
        sys.modules[previous] = sentinel
        self.addCleanup(sys.modules.pop, previous, None)
        def import_attempt(module):
            sys.modules[namespace] = types.ModuleType(namespace)
            sys.modules[namespace + ".implementation"] = types.ModuleType(namespace + ".implementation")
            return self.handler_class
        self.loader._get_plugin_module.side_effect = import_attempt
        self.save.side_effect = [RuntimeError("save failed"), None]
        with self.assertRaises(RuntimeError):
            self.loader.install_plugin(self.package("2.0"))
        self.assertNotIn(namespace, sys.modules)
        self.assertNotIn(namespace + ".implementation", sys.modules)
        self.assertIs(sentinel, sys.modules[previous])
        self.save.side_effect = None
        self.assertEqual("test", self.loader.install_plugin(self.package("2.0")))
        self.addCleanup(self.loader._clear_module_namespace, namespace)

    def test_catalog_failures_have_typed_errors_and_rollback(self):
        from requests.exceptions import ConnectionError, Timeout
        for failure, expected in (
            (self.catalog_error("bad response"), PluginCatalogError),
            (HTTPError("upstream rejected"), PluginCatalogError),
            (ConnectionError("offline"), PluginUnavailableError),
            (Timeout("timed out"), PluginUnavailableError),
        ):
            with self.subTest(failure=type(failure).__name__):
                self.catalog.update_category.side_effect = [failure, None]
                with self.assertRaises(expected):
                    self.loader.install_plugin(self.package("2.0"))
                self.assertEqual("1.0", self.model.version)
                self.assertFalse(os.path.exists(os.path.join(self.directory.name, "test-2-0")))

    def test_installed_and_older_versions_raise_conflicts(self):
        for version in ("1.0", "0.1"):
            with self.assertRaises(PluginConflictError):
                self.loader.install_plugin(self.package(version))
        self.catalog.update_category.assert_not_called()

    def test_real_failed_import_can_be_retried_with_corrected_same_version(self):
        namespace = "retry_plugin_" + self.plugin_type
        root = os.path.join(self.directory.name, namespace)
        os.mkdir(root)
        with open(os.path.join(root, "__init__.py"), "w"):
            pass
        self.loader._plugins_path = root
        self.loader._plugins_module = namespace + "."
        self.loader._get_plugin_module = PluginLoader._get_plugin_module.__get__(self.loader)
        self.addCleanup(self.loader._clear_module_namespace, namespace)
        self.lookup.side_effect = ObjectDoesNotExist
        package = self.package("1.0")
        with ZipFile(package) as archive:
            info = json.loads(archive.read("package.json"))
        info["module"] = "implementation.Installed"
        def write(source):
            with ZipFile(package, "w") as archive:
                archive.writestr("package.json", json.dumps(info))
                archive.writestr("implementation.py", source)
        handler = "ServicePlugin" if self.plugin_type == "service" else "ResourcePlugin"
        with patch.object(sys, "path", [self.directory.name] + sys.path):
            write("raise RuntimeError('initial import failed')")
            with self.assertRaises(PluginError):
                self.loader.install_plugin(package)
            self.assertFalse(any(name.startswith(namespace + ".test-1-0") for name in sys.modules))
            self.catalog.create_category.assert_not_called()
            write(
                f"from wstore.asset_manager.resource_plugins.plugin import {handler}\n"
                f"class Installed({handler}):\n    pass\n"
            )
            self.assertEqual("test", self.loader.install_plugin(package))
        self.catalog.create_category.assert_called_once_with("test", "1.0")

    def test_filesystem_import_errors_are_not_reported_as_invalid_packages(self):
        with patch.object(plugin_loader, "__import__", side_effect=PermissionError("unreadable"), create=True):
            with self.assertRaises(PermissionError):
                PluginLoader._get_plugin_module(self.loader, "package.Implementation")

    def test_rollback_logs_cleanup_failure_without_masking_original_error(self):
        self.save.side_effect = [RuntimeError("save failed"), None]
        with patch("wstore.asset_manager.resource_plugins.plugin_rollback.rmtree", side_effect=PermissionError("denied")):
            with self.assertLogs("wstore.default_logger", level="ERROR") as logs:
                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    self.loader.install_plugin(self.package("2.0"))
        self.assertTrue(any("reconciliation required" in message for message in logs.output))
        self.assertEqual("1.0", self.model.version)

    def test_preexisting_worker_imports_new_package_without_restart(self):
        namespace = "runtime_worker_" + self.plugin_type
        root = os.path.join(self.directory.name, namespace)
        os.mkdir(root)
        with open(os.path.join(root, "__init__.py"), "w"):
            pass
        self.loader._plugins_path = root
        self.loader._plugins_module = namespace + "."
        self.loader._get_plugin_module = PluginLoader._get_plugin_module.__get__(self.loader)
        self.addCleanup(self.loader._clear_module_namespace, namespace)
        self.lookup.side_effect = ObjectDoesNotExist
        package = self.package("1.0")
        with ZipFile(package) as archive:
            info = json.loads(archive.read("package.json"))
        info["module"] = "implementation.Installed"
        handler = "ServicePlugin" if self.plugin_type == "service" else "ResourcePlugin"
        with ZipFile(package, "w") as archive:
            archive.writestr("package.json", json.dumps(info))
            archive.writestr("implementation.py",
                f"from wstore.asset_manager.resource_plugins.plugin import {handler}\n"
                f"class Installed({handler}):\n    pass\n")
        code = """
import sys, importlib, logging
from types import SimpleNamespace
sys.argv = ['manage.py', 'test']
import django
django.setup()
from wstore.asset_manager.resource_plugins.decorators import _load_plugin_model
namespace = sys.stdin.readline().strip()
importlib.import_module(namespace)
assert importlib.util.find_spec(namespace + '.test-1-0') is None
print('ready', flush=True)
module = sys.stdin.readline().strip()
print(type(_load_plugin_model(SimpleNamespace(module=module))).__name__, flush=True)
"""
        worker = subprocess.Popen(
            [sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env={**os.environ, "PYTHONPATH": os.pathsep.join([self.directory.name] + sys.path)},
        )
        try:
            worker.stdin.write(namespace + "\n")
            worker.stdin.flush()
            self.assertTrue(select.select([worker.stdout], [], [], 10)[0], "Worker did not initialize")
            self.assertEqual("ready", worker.stdout.readline().strip())
            with patch.object(sys, "path", [self.directory.name] + sys.path):
                self.loader.install_plugin(package)
            output, errors = worker.communicate(namespace + ".test-1-0.implementation.Installed\n", timeout=10)
            self.assertEqual(0, worker.returncode, errors)
            self.assertEqual("Installed", output.strip())
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.communicate()

    def usage_document(self, source, value="category-1"):
        field = "specCharacteristic" if self.plugin_type == "service" else "resourceSpecCharacteristic"
        value_field = "characteristicValueSpecification" if self.plugin_type == "service" else "resourceSpecCharacteristicValue"
        entry = {"name": " " + self.plugin_type.title() + " Type ", "value": value}
        if source == "specification":
            entry = {"name": entry["name"], value_field: [{"value": value}]}
        else:
            field = self.plugin_type + "Characteristic"
        return {"id": source + "-1", field: [entry]}

    def assert_uninstall_preserved(self):
        self.catalog.delete_category.assert_not_called()
        self.delete.assert_not_called()
        self.loader._get_plugin_module.assert_not_called()

    @parameterized.expand([("string", "category-1"), ("legacy_reference", {"id": "category-1"})])
    def test_specification_reference_blocks_uninstall(self, _, value):
        self.usage_get.return_value.json.return_value = [self.usage_document("specification", value)]
        path = os.path.join(self.directory.name, "test-1-0")
        os.mkdir(path)
        self.model.pull_accounting = True
        with self.assertRaises(PermissionDenied):
            self.loader.uninstall_plugin("test")
        self.assert_uninstall_preserved()
        self.assertTrue(os.path.isdir(path))

    @parameterized.expand([("active",), ("suspended",), ("terminated",)])
    def test_inventory_reference_blocks_uninstall_without_specification(self, state):
        document = self.usage_document("inventory")
        document["state" if self.plugin_type == "service" else "resourceStatus"] = state
        empty, used = Mock(), Mock()
        empty.json.return_value = []
        used.json.return_value = [document]
        self.usage_get.side_effect = [empty, used]
        with self.assertRaises(PermissionDenied):
            self.loader.uninstall_plugin("test")
        self.assert_uninstall_preserved()
        self.assertEqual(2, self.usage_get.call_count)
        self.assertTrue(self.usage_get.call_args.args[0].endswith("/" + self.plugin_type))

    @parameterized.expand([("specification",), ("inventory",)])
    def test_reference_on_later_short_page_blocks_uninstall(self, source):
        ordinary = self.usage_document(source, "other-category")
        used = self.usage_document(source)
        used["id"] = "referenced-instance"
        def response(documents):
            result = Mock()
            result.json.return_value = documents
            return result
        pages = [response([ordinary]), response([used])]
        if source == "inventory":
            pages.insert(0, response([]))
        self.usage_get.side_effect = pages
        with self.assertRaises(PermissionDenied):
            self.loader.uninstall_plugin("test")
        self.assert_uninstall_preserved()
        self.assertEqual({"offset": 1, "limit": 100}, self.usage_get.call_args.kwargs["params"])

    def test_unreferenced_plugin_checks_both_domains_before_deletion(self):
        self.loader.uninstall_plugin("test")
        calls = self.usage_get.call_args_list
        self.assertEqual(2, len(calls))
        self.assertTrue(calls[0].args[0].endswith("/" + self.plugin_type + "Specification"))
        self.assertTrue(calls[1].args[0].endswith("/" + self.plugin_type))
        self.assertEqual([call.delete_category("category-1")], self.catalog.method_calls)
        self.delete.assert_called_once()

    def test_reference_for_other_type_is_not_mistaken_for_usage(self):
        document = self.usage_document("specification")
        field = "specCharacteristic" if self.plugin_type == "service" else "resourceSpecCharacteristic"
        document[field][0]["name"] = "Resource Type" if self.plugin_type == "service" else "Service Type"
        page, empty = Mock(), Mock()
        page.json.return_value = [document]
        empty.json.return_value = []
        self.usage_get.side_effect = [page, empty, empty]
        self.loader.uninstall_plugin("test")
        self.delete.assert_called_once()

    @parameterized.expand([
        ("object", {"error": "upstream failed"}),
        ("invalid_document", [None]),
        ("missing_id", [{}]),
        ("invalid_characteristics", [{"id": "spec-1", "specCharacteristic": {}, "resourceSpecCharacteristic": {}}]),
    ])
    def test_unverifiable_usage_blocks_removal(self, _, documents):
        self.usage_get.return_value.json.return_value = documents
        with self.assertRaises(PluginUsageError):
            self.loader.uninstall_plugin("test")
        self.assert_uninstall_preserved()

    def test_invalid_usage_json_blocks_removal(self):
        self.usage_get.return_value.json.side_effect = ValueError("invalid JSON")
        with self.assertRaises(PluginUsageError):
            self.loader.uninstall_plugin("test")
        self.assert_uninstall_preserved()

    def test_ignored_pagination_is_not_treated_as_no_usage(self):
        self.usage_get.return_value.json.return_value = [self.usage_document("specification", "other-category")]
        with self.assertRaises(PluginUsageError):
            self.loader.uninstall_plugin("test")
        self.assertEqual(2, self.usage_get.call_count)
        self.assert_uninstall_preserved()

    @parameterized.expand([("missing", None), ("wrong_type", 42), ("empty", "")])
    def test_invalid_plugin_type_reference_blocks_removal(self, _, value):
        self.usage_get.return_value.json.return_value = [self.usage_document("specification", value)]
        with self.assertRaises(PluginUsageError):
            self.loader.uninstall_plugin("test")
        self.assert_uninstall_preserved()

    def test_usage_http_failure_keeps_plugin_installed(self):
        self.usage_get.side_effect = HTTPError("usage API unavailable")
        with self.assertRaises(HTTPError):
            self.loader.uninstall_plugin("test")
        self.assert_uninstall_preserved()


class ResourcePackageManagementTests(PackageManagementTests):
    plugin_type = "resource"
    catalog_class = ResourceCatalog
    catalog_error = ResourceCatalogError
    handler_class = RecordingResourcePlugin


class FilePluginContractTests(SimpleTestCase):
    def setUp(self):
        self.info = {
            "name": "test",
            "version": "1.0",
            "author": "author",
            "module": "test.Plugin",
            "type": "service",
            "requires_file": False,
        }
        self.validator = PluginValidator()

    def test_requires_file_is_an_explicit_boolean_including_false(self):
        for value in (True, False):
            self.info["requires_file"] = value
            self.assertEqual([], self.validator.validate_plugin_info(self.info))

        for value in (0, 1, "true", None, []):
            self.info["requires_file"] = value
            self.assertTrue(self.validator.validate_plugin_info(self.info))

    def test_file_characteristic_name_is_reserved_case_insensitively(self):
        for name in ("File", "file", "FILE"):
            self.info["form"] = {name: {"type": "text"}}
            self.assertTrue(self.validator.validate_plugin_info(self.info))

    def test_url_is_allowed_as_a_plugin_defined_text_field(self):
        self.info["form"] = {"URL": {"type": "text", "mandatory": True}}
        self.assertEqual([], self.validator.validate_plugin_info(self.info))

    def test_supported_media_types_must_be_strings(self):
        for value in ([123], [None], [""], [" "]):
            self.info["media_types"] = value
            self.assertTrue(self.validator.validate_plugin_info(self.info))

    def test_asset_type_api_exposes_requires_file_boolean(self):
        from wstore.asset_manager.resource_plugins.views import get_plugin_info

        model = ResourcePlugin(plugin_id="test", name="test", requires_file=False)
        info = get_plugin_info(model)
        self.assertIs(False, info["requiresFile"])
        self.assertNotIn("formats", info)

    def test_manifest_type_is_required_and_has_only_two_values(self):
        for value in (None, True, 1, "", "Service", "other"):
            with self.subTest(value=value):
                self.info["type"] = value
                self.assertTrue(self.validator.validate_plugin_info(self.info))
        self.info.pop("type")
        self.assertIn("Missing required field: type", self.validator.validate_plugin_info(self.info))
        for value in ("service", "resource"):
            self.info["type"] = value
            self.assertEqual([], self.validator.validate_plugin_info(self.info))

    def test_interfaces_do_not_inherit_other_domain_hooks(self):
        self.assertTrue(issubclass(ServicePlugin, Plugin))
        self.assertTrue(issubclass(ResourcePluginHandler, Plugin))
        self.assertFalse(hasattr(Plugin, "on_service_activation"))
        self.assertFalse(hasattr(Plugin, "on_resource_activation"))
        self.assertFalse(issubclass(ServicePlugin, ResourcePluginHandler))
        self.assertFalse(issubclass(ResourcePluginHandler, ServicePlugin))
        for suffix in ("activation", "suspension", "resumption", "termination", "modification", "renewal"):
            self.assertTrue(hasattr(ServicePlugin, "on_service_" + suffix))
            self.assertFalse(hasattr(ServicePlugin, "on_resource_" + suffix))
            self.assertTrue(hasattr(ResourcePluginHandler, "on_resource_" + suffix))
            self.assertFalse(hasattr(ResourcePluginHandler, "on_service_" + suffix))

    def test_api_metadata_exposes_domain(self):
        from wstore.asset_manager.resource_plugins.views import get_plugin_info

        for plugin_type in ("service", "resource"):
            model = ResourcePlugin(plugin_id="test", name="test", type=plugin_type, requires_file=False)
            self.assertEqual(plugin_type, get_plugin_info(model)["type"])


class PluginCollectionTests(SimpleTestCase):
    def setUp(self):
        from django.test import RequestFactory
        from wstore.asset_manager.resource_plugins import views

        self.factory = RequestFactory()
        self.view = views.PluginCollection(permitted_methods=("GET",))
        self.plugins = [
            ResourcePlugin(plugin_id="service-plugin", name="service plugin", type="service", requires_file=False),
            ResourcePlugin(plugin_id="resource-plugin", name="resource plugin", type="resource", requires_file=True),
        ]
        patcher = patch.object(views, "ResourcePlugin")
        self.registry = patcher.start()
        self.addCleanup(patcher.stop)
        self.registry.objects.all.return_value = self.plugins
        self.registry.objects.filter.side_effect = lambda type: [p for p in self.plugins if p.type == type]

    def request(self, query=None, anonymous=False):
        request = self.factory.get("/charging/api/assetManagement/assetTypes", query or {})
        request.user = Mock(is_anonymous=anonymous)
        return self.view(request)

    def test_no_type_returns_all_plugins(self):
        response = self.request()
        self.assertEqual(200, response.status_code)
        self.assertEqual(["service", "resource"], [p["type"] for p in json.loads(response.content)])
        self.registry.objects.all.assert_called_once_with()
        self.registry.objects.filter.assert_not_called()

    @parameterized.expand([("service",), ("resource",)])
    def test_filter_by_type(self, plugin_type):
        response = self.request({"type": plugin_type})
        self.assertEqual(200, response.status_code)
        self.assertEqual([plugin_type], [p["type"] for p in json.loads(response.content)])
        self.registry.objects.filter.assert_called_once_with(type=plugin_type)
        self.registry.objects.all.assert_not_called()

    def test_filter_with_no_matches_returns_empty_list(self):
        self.registry.objects.filter.side_effect = None
        self.registry.objects.filter.return_value = []
        response = self.request({"type": "resource"})
        self.assertEqual(200, response.status_code)
        self.assertEqual([], json.loads(response.content))

    def test_invalid_type_returns_bad_request_without_reading_registry(self):
        for plugin_type in ("", "other", "Service"):
            with self.subTest(plugin_type=plugin_type):
                response = self.request({"type": plugin_type})
                self.assertEqual(400, response.status_code)
        self.registry.objects.all.assert_not_called()
        self.registry.objects.filter.assert_not_called()

    def test_filter_still_requires_authentication(self):
        response = self.request({"type": "resource"}, anonymous=True)
        self.assertEqual(401, response.status_code)
        self.registry.objects.all.assert_not_called()
        self.registry.objects.filter.assert_not_called()


class SuspensionDispatchTests(SimpleTestCase):
    def setUp(self):
        from types import SimpleNamespace

        self.local_order = SimpleNamespace(order_id="order-1")
        self.contract = SimpleNamespace(product_id="p1", suspended=False)
        self.raw_order = {"id": "order-1", "productOrderItem": [{"id": "i1"}]}
        self.provider, self.buyer = object(), object()
        self.product = {
            "id": "p1",
            "relatedParty": [{"id": "seller", "role": "Seller"}, {"id": "buyer", "role": "Buyer"}],
            "realizingService": [{"id": "s1"}],
            "realizingResource": [{"id": "r1"}],
        }
        self.instances = {
            kind: {"id": id_, kind + "Characteristic": [{"name": kind.title() + " Type", "value": "same-category"}]}
            for kind, id_ in (("service", "s1"), ("resource", "r1"))
        }
        self.plugins = {"service": Mock(spec=ServicePlugin), "resource": Mock(spec=ResourcePluginHandler)}
        for name in ("InventoryClient", "OrderingClient", "Organization", "_get_plugin_model", "_load_plugin_model"):
            patcher = patch.object(decorators, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.inventory = self.InventoryClient.return_value
        self.inventory.get_product.return_value = self.product
        self.inventory.get_service.return_value = self.instances["service"]
        self.inventory.get_resource.return_value = self.instances["resource"]
        self.OrderingClient.return_value.get_order.return_value = self.raw_order
        self.Organization.objects.get.side_effect = (
            lambda actor_id: self.provider if actor_id == "seller" else self.buyer
        )
        self._get_plugin_model.side_effect = lambda category_id, plugin_type: plugin_type
        self._load_plugin_model.side_effect = self.plugins.__getitem__
        self.catalog_reads = []
        for catalog in (ServiceCatalog, ResourceCatalog):
            patcher = patch.object(catalog, "get_specification")
            self.catalog_reads.append(patcher.start())
            self.addCleanup(patcher.stop)

    def dispatch(self):
        decorators.on_product_suspended(self.local_order, self.contract)

    def test_mixed_instances_receive_buyer_provider_inventory_and_raw_order(self):
        self.dispatch()
        self.inventory.get_product.assert_called_once_with("p1")
        self.OrderingClient.return_value.get_order.assert_called_once_with("order-1")
        for kind, plugin in self.plugins.items():
            getattr(plugin, "on_" + kind + "_suspension").assert_called_once_with(
                self.provider, self.buyer, self.instances[kind], self.product, self.raw_order, self.contract
            )
            self.assertEqual(["on_" + kind + "_suspension"], [invocation[0] for invocation in plugin.method_calls])
            self._get_plugin_model.assert_any_call(category_id="same-category", plugin_type=kind)
        for read in self.catalog_reads:
            read.assert_not_called()
        self.inventory.patch_product.assert_not_called()
        self.assertFalse(self.contract.suspended)

    @parameterized.expand([("service",), ("resource",)])
    def test_each_domain_can_be_suspended_alone(self, kind):
        other = "resource" if kind == "service" else "service"
        del self.product["realizing" + other.title()]
        self.dispatch()
        getattr(self.plugins[kind], "on_" + kind + "_suspension").assert_called_once()
        self.assertEqual([], self.plugins[other].method_calls)

    def test_ordinary_and_uninstalled_instances_skip_handlers(self):
        self.instances["service"]["serviceCharacteristic"] = [{"name": "File", "value": "ordinary-file"}]
        self._get_plugin_model.side_effect = None
        self._get_plugin_model.return_value = None
        self.dispatch()
        self._load_plugin_model.assert_not_called()
        for plugin in self.plugins.values():
            self.assertEqual([], plugin.method_calls)

    def test_failure_is_logged_and_remaining_instances_are_notified(self):
        self.plugins["service"].on_service_suspension.side_effect = PluginError("external failure")
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.dispatch()
        self.plugins["resource"].on_resource_suspension.assert_called_once()
        self.assertFalse(self.contract.suspended)
        self.inventory.suspend_product.assert_not_called()

    def test_bad_instance_reference_does_not_prevent_other_domain_notification(self):
        self.inventory.get_service.return_value = {"id": "wrong"}
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.dispatch()
        self.plugins["service"].on_service_suspension.assert_not_called()
        self.plugins["resource"].on_resource_suspension.assert_called_once()

    def test_malformed_collection_does_not_prevent_other_domain_notification(self):
        self.product["realizingService"] = None
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.dispatch()
        self.plugins["resource"].on_resource_suspension.assert_called_once()

    def test_dispatch_does_not_add_a_suspended_state_guard(self):
        self.contract.suspended = True
        self.dispatch()
        self.plugins["service"].on_service_suspension.assert_called_once()
        self.plugins["resource"].on_resource_suspension.assert_called_once()

    def test_invalid_product_or_order_is_logged_without_changing_callers(self):
        for product, raw_order in (
            ({"id": "wrong"}, self.raw_order),
            (self.product, None),
            (self.product, {"id": "wrong"}),
        ):
            with self.subTest(product=product, order=raw_order):
                self.inventory.get_product.return_value = product
                self.OrderingClient.return_value.get_order.return_value = raw_order
                with self.assertLogs("wstore.default_logger", level="ERROR"):
                    self.dispatch()
        self._load_plugin_model.assert_not_called()

    def test_missing_provider_is_logged_without_invoking_handlers(self):
        self.product["relatedParty"] = [{"id": "buyer", "role": "Buyer"}]
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.dispatch()
        for plugin in self.plugins.values():
            self.assertEqual([], plugin.method_calls)

    def test_inherited_suspension_hooks_are_optional_and_match_activation_arguments(self):
        self._load_plugin_model.side_effect = lambda kind: (
            ServicePlugin if kind == "service" else ResourcePluginHandler
        )(object())
        self.dispatch()

    def test_usage_remains_disconnected(self):
        decorators.on_usage_refreshed(self.local_order, self.contract)
        self.InventoryClient.assert_not_called()
        self.OrderingClient.assert_not_called()


class TerminationDispatchTests(SimpleTestCase):
    setUp = SuspensionDispatchTests.setUp

    def dispatch(self):
        decorators.on_product_termination(self.local_order, self.contract)

    def test_mixed_instances_receive_inventory_context_without_specification_reads(self):
        self.dispatch()
        self.inventory.get_product.assert_called_once_with("p1")
        self.OrderingClient.return_value.get_order.assert_called_once_with("order-1")
        for kind, plugin in self.plugins.items():
            getattr(plugin, "on_" + kind + "_termination").assert_called_once_with(
                self.provider, self.buyer, self.instances[kind], self.product, self.raw_order, self.contract
            )
            self.assertEqual(["on_" + kind + "_termination"], [c[0] for c in plugin.method_calls])
            self._get_plugin_model.assert_any_call(category_id="same-category", plugin_type=kind)
        for read in self.catalog_reads:
            read.assert_not_called()
        self.inventory.patch_product.assert_not_called()

    @parameterized.expand([("service",), ("resource",)])
    def test_each_domain_can_be_terminated_alone(self, kind):
        other = "resource" if kind == "service" else "service"
        del self.product["realizing" + other.title()]
        self.dispatch()
        getattr(self.plugins[kind], "on_" + kind + "_termination").assert_called_once()
        self.assertEqual([], self.plugins[other].method_calls)

    def test_ordinary_and_uninstalled_instances_skip_hooks(self):
        self.instances["service"]["serviceCharacteristic"] = []
        self._get_plugin_model.side_effect = None
        self._get_plugin_model.return_value = None
        self.dispatch()
        self._load_plugin_model.assert_not_called()
        for plugin in self.plugins.values():
            self.assertEqual([], plugin.method_calls)

    def test_failure_propagates_and_stops_remaining_hooks(self):
        self.plugins["service"].on_service_termination.side_effect = PluginError("cleanup failed")
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            with self.assertRaisesRegex(PluginError, "cleanup failed"):
                self.dispatch()
        self.plugins["resource"].on_resource_termination.assert_not_called()
        self.inventory.patch_product.assert_not_called()

    def test_invalid_context_blocks_termination(self):
        for product, raw_order in (
            ({"id": "wrong"}, self.raw_order),
            (self.product, None),
            (self.product, {"id": "wrong"}),
        ):
            with self.subTest(product=product, order=raw_order):
                self.inventory.get_product.return_value = product
                self.OrderingClient.return_value.get_order.return_value = raw_order
                with self.assertLogs("wstore.default_logger", level="ERROR"):
                    with self.assertRaises(PluginError):
                        self.dispatch()
        self._load_plugin_model.assert_not_called()

    def test_missing_provider_blocks_termination(self):
        self.product["relatedParty"] = [{"id": "buyer", "role": "Buyer"}]
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            with self.assertRaises(ServiceError):
                self.dispatch()
        for plugin in self.plugins.values():
            self.assertEqual([], plugin.method_calls)

    def test_invalid_reference_blocks_termination(self):
        self.inventory.get_service.return_value = {"id": "wrong"}
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            with self.assertRaises(ServiceError):
                self.dispatch()
        self.plugins["resource"].on_resource_termination.assert_not_called()

    def test_inherited_termination_hooks_are_optional(self):
        self._load_plugin_model.side_effect = lambda kind: (
            ServicePlugin if kind == "service" else ResourcePluginHandler
        )(object())
        self.dispatch()


class PluginInstallationApiTests(SimpleTestCase):
    url = "/charging/api/assetManagement/assetTypes/installJob"

    def setUp(self):
        from django.test import RequestFactory
        from wstore.asset_manager.resource_plugins import views
        self.views = views
        self.factory = RequestFactory()
        self.view = views.PluginInstallCollection(permitted_methods=("POST",))
        self.model = ResourcePlugin(
            plugin_id="example", name="Example", type="service", version="1.0",
            category_id="category-1", author="Test", requires_file=False,
        )
        for name in ("PluginLoader", "ResourcePlugin"):
            patcher = patch.object(views, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.PluginLoader.return_value.install_plugin.return_value = "example"
        self.ResourcePlugin.objects.get.return_value = self.model
        self.paths = []
        def install(path):
            self.assertTrue(os.path.isfile(path))
            with open(path, "rb") as package:
                self.assertEqual(b"package-bytes", package.read())
            self.paths.append(path)
            return "example"
        self.PluginLoader.return_value.install_plugin.side_effect = install

    def request(self, data=None, anonymous=False, staff=True):
        from django.core.files.uploadedfile import SimpleUploadedFile
        if data is None:
            data = {"file": SimpleUploadedFile("plugin.zip", b"package-bytes", "application/zip")}
        request = self.factory.post(self.url, data)
        request.user = Mock(is_anonymous=anonymous, is_staff=staff, pk="admin-1")
        return request

    @parameterized.expand([
        ("service", False), ("service", True), ("resource", False), ("resource", True),
    ])
    def test_success_uses_one_installer_call_then_returns_metadata_and_cleans_upload(self, kind, requires_file):
        self.model.type = kind
        self.model.requires_file = requires_file
        response = self.view(self.request())
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.views.get_plugin_info(self.model), json.loads(response.content))
        self.assertEqual(json.loads(response.content)["href"], response["Location"])
        self.PluginLoader.return_value.install_plugin.assert_called_once_with(self.paths[0])
        self.ResourcePlugin.objects.get.assert_called_once_with(plugin_id="example")
        self.assertFalse(os.path.exists(self.paths[0]))
        self.assertFalse(os.path.exists(os.path.dirname(self.paths[0])))

    @parameterized.expand([("anonymous", True, False, 401), ("customer", False, False, 403)])
    def test_authorization_precedes_upload_parsing(self, _, anonymous, staff, expected):
        request = self.request(anonymous=anonymous, staff=staff)
        request._load_post_and_files = Mock(side_effect=AssertionError("Upload parsed before authorization"))
        self.assertEqual(expected, self.view(request).status_code)
        request._load_post_and_files.assert_not_called()
        self.PluginLoader.assert_not_called()

    def test_unsupported_content_type_does_not_invoke_installer(self):
        request = self.factory.post(self.url, "{}", content_type="application/json")
        request.user = Mock(is_anonymous=False, is_staff=True, pk="admin-1")
        self.assertEqual(415, self.view(request).status_code)
        self.PluginLoader.assert_not_called()

    def test_only_post_is_routable(self):
        from django.urls import resolve
        for path in (self.url, self.url + "/"):
            view = resolve(path).func
            self.assertIsInstance(view, self.views.PluginInstallCollection)
            self.assertEqual(405, view(self.factory.get(path)).status_code)

    def test_missing_empty_multiple_and_wrong_file_fields_are_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        for data in (
            {},
            {"file": SimpleUploadedFile("empty.zip", b"")},
            {"file": [SimpleUploadedFile("a.zip", b"a"), SimpleUploadedFile("b.zip", b"b")]},
            {"other": SimpleUploadedFile("plugin.zip", b"x")},
        ):
            with self.subTest(fields=list(data)):
                self.assertEqual(400, self.view(self.request(data)).status_code)
        self.PluginLoader.assert_not_called()

    def test_existing_request_size_rejection_returns_413_without_calling_installer(self):
        from django.core.exceptions import RequestDataTooBig

        request = self.request()
        request._load_post_and_files = Mock(side_effect=RequestDataTooBig("Request too large"))
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.assertEqual(413, self.view(request).status_code)
        self.PluginLoader.assert_not_called()

    @parameterized.expand([
        ("conflict", PluginConflictError, 409),
        ("limit", PluginSizeError, 413),
        ("invalid", PluginError, 422),
        ("catalog", PluginCatalogError, 502),
        ("unavailable", PluginUnavailableError, 503),
        ("unexpected", RuntimeError, 500),
    ])
    def test_install_errors_map_to_status_and_remove_temporary_files(self, _, error, expected):
        def fail(path):
            self.paths.append(path)
            raise error("sensitive /server/path must not appear in response")
        self.PluginLoader.return_value.install_plugin.side_effect = fail
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            response = self.view(self.request())
        self.assertEqual(expected, response.status_code)
        self.assertNotIn(b"/server/path", response.content)
        self.assertFalse(os.path.exists(os.path.dirname(self.paths[0])))
        self.ResourcePlugin.objects.get.assert_not_called()

    def test_malformed_multipart_returns_bad_request(self):
        request = self.factory.generic("POST", self.url, b"invalid", content_type="multipart/form-data")
        request.user = Mock(is_anonymous=False, is_staff=True, pk="admin-1")
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.assertEqual(400, self.view(request).status_code)
        self.PluginLoader.assert_not_called()

    def test_upload_read_failure_cleans_partial_file_without_calling_installer(self):
        request = self.request()
        def chunks():
            yield b"partial"
            raise OSError("read failed")
        request.FILES["file"].chunks = chunks
        directories = []
        def temporary_directory(*args, **kwargs):
            directory = TemporaryDirectory(*args, **kwargs)
            directories.append(directory.name)
            return directory
        with patch.object(self.views, "TemporaryDirectory", side_effect=temporary_directory):
            with self.assertLogs("wstore.default_logger", level="ERROR"):
                self.assertEqual(500, self.view(request).status_code)
        self.assertFalse(os.path.exists(directories[0]))
        self.PluginLoader.assert_not_called()

    def test_metadata_failure_does_not_reinstall_completed_package(self):
        self.ResourcePlugin.objects.get.side_effect = RuntimeError("database unavailable")
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            self.assertEqual(500, self.view(self.request()).status_code)
        self.PluginLoader.return_value.install_plugin.assert_called_once()
        self.assertFalse(os.path.exists(os.path.dirname(self.paths[0])))


class PluginUninstallApiTests(SimpleTestCase):
    url = "/charging/api/assetManagement/assetTypes/example"

    def setUp(self):
        from django.test import RequestFactory
        from wstore.asset_manager.resource_plugins import views

        self.views = views
        self.factory = RequestFactory()
        self.view = views.PluginEntry(permitted_methods=("GET", "DELETE"))
        patcher = patch.object(views, "PluginLoader")
        self.loader_class = patcher.start()
        self.addCleanup(patcher.stop)
        self.loader = self.loader_class.return_value

    def request(self, anonymous=False, staff=True):
        request = self.factory.delete(self.url)
        request.user = Mock(is_anonymous=anonymous, is_staff=staff, pk="admin-1")
        return request

    def test_admin_deletes_through_shared_loader_without_request_body(self):
        request = self.request()
        request._load_post_and_files = Mock(side_effect=AssertionError("No upload should be parsed"))
        response = self.view(request, plugin_id="example")
        self.assertEqual(204, response.status_code)
        self.assertEqual(b"", response.content)
        self.loader_class.assert_called_once_with()
        self.loader.uninstall_plugin.assert_called_once_with("example")
        self.assertEqual([call.uninstall_plugin("example")], self.loader.method_calls)
        request._load_post_and_files.assert_not_called()

    @parameterized.expand([("anonymous", True, False, 401), ("non_admin", False, False, 403)])
    def test_authorization_precedes_loader_access(self, _, anonymous, staff, expected):
        response = self.view(self.request(anonymous=anonymous, staff=staff), plugin_id="example")
        self.assertEqual(expected, response.status_code)
        self.loader_class.assert_not_called()

    def test_delete_route_supports_optional_trailing_slash_and_rejects_post(self):
        from django.urls import resolve

        for path in (self.url, self.url + "/"):
            match = resolve(path)
            self.assertIsInstance(match.func, self.views.PluginEntry)
            self.assertEqual("example", match.kwargs["plugin_id"])
            self.assertEqual(204, match.func(self.request(), **match.kwargs).status_code)
            self.assertEqual(405, match.func(self.factory.post(path), **match.kwargs).status_code)
        install = resolve("/charging/api/assetManagement/assetTypes/installJob")
        self.assertEqual(405, install.func(self.request()).status_code)

    @parameterized.expand([
        ("missing", ObjectDoesNotExist, 404),
        ("in_use", PermissionDenied, 409),
        ("busy", PluginConflictError, 409),
        ("configuration", PluginError, 422),
        ("catalog", PluginCatalogError, 502),
        ("service_catalog", ServiceCatalogError, 502),
        ("usage_verification", PluginUsageError, 502),
        ("resource_catalog", ResourceCatalogError, 502),
        ("http", HTTPError, 502),
        ("unavailable", PluginUnavailableError, 503),
        ("unexpected", RuntimeError, 500),
    ])
    def test_removal_errors_map_to_status_without_leaking_details(self, _, error, expected):
        self.loader.uninstall_plugin.side_effect = error("sensitive /server/path")
        with self.assertLogs("wstore.default_logger", level="ERROR"):
            response = self.view(self.request(), plugin_id="example")
        self.assertEqual(expected, response.status_code)
        body = json.loads(response.content)
        self.assertEqual("error", body["result"])
        self.assertNotIn("/server/path", body["error"])
        self.loader.uninstall_plugin.assert_called_once_with("example")

    def test_network_failures_return_service_unavailable(self):
        from requests.exceptions import ConnectionError, Timeout

        for error in (ConnectionError, Timeout):
            with self.subTest(error=error.__name__):
                self.loader.uninstall_plugin.side_effect = error("offline")
                with self.assertLogs("wstore.default_logger", level="ERROR"):
                    self.assertEqual(503, self.view(self.request(), plugin_id="example").status_code)

    def test_existing_get_metadata_remains_available_to_authenticated_non_admins(self):
        model = ResourcePlugin(plugin_id="example", name="Example", type="service", requires_file=False)
        request = self.factory.get(self.url)
        request.user = Mock(is_anonymous=False, is_staff=False)
        with patch.object(self.views, "ResourcePlugin") as registry:
            registry.objects.get.return_value = model
            response = self.view(request, plugin_id="example")
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.views.get_plugin_info(model), json.loads(response.content))
        self.loader_class.assert_not_called()
