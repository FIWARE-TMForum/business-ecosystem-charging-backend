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

import os
from importlib import reload
from json import dump as jsondump
from shutil import rmtree

from bson.objectid import ObjectId
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.test import TestCase
from mock import MagicMock, call
from parameterized import parameterized
from requests.exceptions import HTTPError
from wstore.asset_manager.resource_plugins import decorators, plugin, plugin_loader
from wstore.asset_manager.resource_plugins.plugin_error import PluginError
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
                "Plugin Error: No Plugin implementation has been found",
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
            self.assertEquals(plugin_model.formats, expected["formats"])

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
        plugin_loader.Resource.objects.filter.return_value = ["resource"]

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
                "The plugin test_plugin is being used in some resources",
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
        plugin_loader.Resource = MagicMock(name="Resource")

        self.resources_mock = MagicMock()
        plugin_loader.Resource.objects.filter.return_value = []

        plugin_loader.ResourcePlugin = MagicMock(name="ResourcePlugin")

        plugin_mock = MagicMock()
        plugin_mock.name = plugin_name
        plugin_mock.version = "1.0"
        plugin_mock.version_history = []
        plugin_mock.pull_accounting = pull
        plugin_mock.module = "wstore.asset_manager.resource_plugins.tests.TestPlugin"
        plugin_mock.usage_called = False

        plugin_loader.ResourcePlugin.objects.get.return_value = plugin_mock

        plugin_loader.rmtree = MagicMock(name="rmtree")

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
            plugin_loader.Resource.objects.filter.assert_called_once_with(resource_type=plugin_name)
            plugin_loader.rmtree.assert_called_once_with(os.path.join(plugin_l._plugins_path, "test_plugin"))
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
            ("missing_formats", MISSING_FORMATS, "Missing required field: formats"),
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
                "invalid_formats_type",
                INVALID_FORMAT_TYPE,
                "Field `formats` should be list but found str.",
            ),
            (
                "invalid_format",
                INVALID_FORMAT,
                "Format must contain at least one format of: ['FILE', 'URL']",
            ),
            (
                "invalid_media_type",
                INVALID_MEDIA_TYPE,
                "Plugin `media_types` must be a list",
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

        plugin_handler = plugin.Plugin(self._model)
        plugin_handler.get_usage_specs = MagicMock(return_value=specs)

        plugin_handler.configure_usage_spec()

        plugin.UsageClient.assert_called_once_with()
        validator(self)

    def test_usage_spec_error(self):
        plugin_handler = plugin.Plugin(self._model)
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

        plugin_handler = plugin.Plugin(self._model)

        plugin_handler.remove_usage_specs()

        validator(self)

    def test_remove_usage_spec_error(self):
        self._model.options = self._option

        error = HTTPError()
        error.response = MagicMock(status_code=500)
        self._usage_client.delete_usage_spec.side_effect = error

        plugin_handler = plugin.Plugin(self._model)

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

        plugin_handler = plugin.Plugin(self._model)
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
        plugin_handler = plugin.Plugin(self._model)
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
        plugin_handler = plugin.Plugin(self._model)
        plugin_handler.get_pending_accounting = MagicMock(return_value=([], None))

        plugin_handler.on_usage_refresh(None, None, None)
        self.assertEquals(0, plugin_handler.get_pending_accounting.call_count)


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

    # def test_product_acquired(self):
    #     # Include order and contract info
    #     bundle = self._get_offering_mock()
    #     bundle.bundled_offerings = [
    #         "61004aba5e05acc115f022f0",
    #         "61004aba5e05acc115f022f1",
    #         "61004aba5e05acc115f022f2",
    #     ]

    #     offering1 = self._get_offering_mock()
    #     offering2 = self._get_offering_mock()
    #     offering3 = self._get_offering_mock(bundle_asset=True)

    #     decorators.Offering = MagicMock()
    #     decorators.Offering.objects.get.side_effect = [
    #         bundle,
    #         offering1,
    #         offering1,
    #         offering2,
    #         offering2,
    #         offering3,
    #         offering3,
    #     ]

    #     decorators.Resource = MagicMock()
    #     asset1 = MagicMock(resource_type="asset3")
    #     asset2 = MagicMock(resource_type="asset4")
    #     decorators.Resource.objects.get.side_effect = [asset1, asset2]

    #     self._contract.offering = "61004aba5e05acc115f022f0"

    #     decorators.on_product_acquired(self._order, self._contract)

    #     # Check calls
    #     self.assertEquals(
    #         [call("asset"), call("asset"), call("asset3"), call("asset4")],
    #         decorators.load_plugin_module.call_args_list,
    #     )

    #     self.assertEquals(
    #         [
    #             call(offering1.asset, self._contract, self._order),
    #             call(offering2.asset, self._contract, self._order),
    #             call(asset1, self._contract, self._order),
    #             call(asset2, self._contract, self._order),
    #         ],
    #         self._module.on_product_acquisition.call_args_list,
    #     )

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
