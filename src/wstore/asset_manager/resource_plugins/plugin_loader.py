# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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
import os
import zipfile
from logging import getLogger
from shutil import rmtree

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from wstore.asset_manager.resource_plugins.plugin import Plugin
from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.asset_manager.resource_plugins.plugin_rollback import installPluginRollback
from wstore.asset_manager.resource_plugins.plugin_validator import PluginValidator
from wstore.models import Resource, ResourcePlugin
from wstore.store_commons.utils.version import is_lower_version
from wstore.asset_manager import service_category_manager

logger = getLogger("wstore.default_logger")


class PluginLoader:
    _plugin_manager = None
    _plugins_path = None
    _plugins_module = None

    def __init__(self):
        logger.debug("Creating new PluginLoader")

        self._plugin_manager = PluginValidator()
        self._plugins_path = os.path.join(settings.BASEDIR, "wstore", "asset_manager", "resource_plugins", "plugins")
        self._plugins_module = "wstore.asset_manager.resource_plugins.plugins."

        logger.debug(f"Plugins path: {self._plugins_path}")

    def _get_plugin_module(self, module):
        module_class_name = module.split(".")[-1]
        module_package = module.partition("." + module_class_name)[0]

        logger.debug(f"Plugin module: {module_package}.{module_class_name}")
        return getattr(
            __import__(module_package, globals(), locals(), [module_class_name], 0),
            module_class_name,
        )

    def _update_model_data_from_json(self, model, module, json_info):
        # Create or update plugin model data
        model.category_id = json_info["category_id"]
        model.name = json_info["name"]
        model.version = json_info["version"]
        model.author = json_info["author"]
        model.module = module
        model.formats = json_info["formats"]
        model.media_types = json_info.get("media_types", [])
        model.form = json_info.get("form", {})
        model.form_order = json_info.get("form_order", [])
        model.overrides = json_info.get("overrides", [])
        model.pull_accounting = json_info.get("pull_accounting", False)
        model.save()

    @installPluginRollback
    def install_plugin(self, path, rb_log=None):
        logger.info(f"Installing plugin: {path}")

        # Validate package file
        if not zipfile.is_zipfile(path):
            logger.error("Invalid package format: Not a zip file")
            raise PluginError("Invalid package format: Not a zip file")

        # Uncompress plugin file
        with zipfile.ZipFile(path, "r") as z:
            # Validate that the file package.json exists
            if "package.json" not in z.namelist():
                logger.error("Invalid package format: Missing package.json file")
                raise PluginError("Missing package.json file")

            logger.debug("Found `package.json`")

            # Read package metainfo
            json_file = z.read("package.json")
            try:
                json_info = json.loads(json_file)
            except json.JSONDecodeError:
                logger.error("Invalid format in `package.json`")
                raise PluginError("Invalid format in package.json file. JSON cannot be parsed")

            # Create a directory for the plugin
            # Validate plugin info
            validation_errors = self._plugin_manager.validate_plugin_info(json_info)

            if validation_errors:
                logger.error("Invalid format in `package.json`")
                raise PluginError("Invalid format in package.json file.\n" + "\n".join(validation_errors))
            logger.debug("Successfully validated `package.json`")

            # Create plugin id
            plugin_id = json_info["name"].lower().replace(" ", "-")

            # Check if the directory already exists
            plugin_dir = f"{plugin_id}-{json_info['version'].replace('.', '-')}"
            plugin_path = os.path.join(self._plugins_path, plugin_dir)

            # Create the directory
            try:
                os.makedirs(plugin_path)
            except FileExistsError:
                raise PluginError("An equal version of this plugin is already installed")

            rb_log.log_action("PATH", plugin_path)

            # Extract files
            z.extractall(plugin_path)
            logger.debug(f"Plugin extracted to {plugin_path}")

        # Get plugin model
        try:
            plugin_model = ResourcePlugin.objects.get(plugin_id=plugin_id)
            if not is_lower_version(plugin_model.version, json_info["version"]):
                logger.error("A newer version of this plugin is already installed")
                raise PluginError("A newer version of this plugin is already installed")
            plugin_model.version_history.append(plugin_model.version)
        except ObjectDoesNotExist:
            plugin_model = ResourcePlugin(plugin_id=plugin_id)

        # Create a  __init__.py file if needed
        open(os.path.join(plugin_path, "__init__.py"), "a").close()

        # Validate plugin main class
        module = self._plugins_module + plugin_dir + "." + json_info["module"]
        module_class = self._get_plugin_module(module)

        if Plugin not in module_class.__bases__:
            logger.error("No plugin implementation has been found")
            raise PluginError("No Plugin implementation has been found")

        # Check accounting implementations
        pull_accounting_errors = self._plugin_manager.validate_pull_accounting(json_info, module_class)
        if pull_accounting_errors:
            logger.error("Error in implementation for pull accounting")
            raise PluginError(pull_accounting_errors)
        
        #####################
        # service category
        logger.debug("Creating API entry")
        s_cat = service_category_manager.ServiceCategoryManager()
        created_cat = s_cat.create_service_cat(json_info)
        logger.debug("Antes del rb_log")
        rb_log.log_action("API", created_cat["name"])
        logger.debug("Antes de crear el cateogy_id en el json")
        json_info["category_id"] = created_cat["id"]
        logger.debug("Tras crearlo en el API")
        #####################

        self._update_model_data_from_json(plugin_model, module, json_info)
        rb_log.log_action("MODEL", plugin_model)
        logger.debug("Plugin model saved to database")

        # Configure usage specifications if needed
        if plugin_model.pull_accounting:
            module_class(plugin_model).configure_usage_spec()

        logger.info(f"Plugin {plugin_id} installed.")

        return plugin_id

    def _downgrade_plugin_to_last_version(self, plugin_id, plugin_model):
        cur_version = plugin_model.version
        dg_version = plugin_model.version_history.pop()
        cur_plugin_dir = f"{plugin_id}-{cur_version.replace('.', '-')}"
        dg_plugin_dir = f"{plugin_id}-{dg_version.replace('.', '-')}"
        cur_plugin_path = os.path.join(self._plugins_path, cur_plugin_dir)
        dg_plugin_path = os.path.join(self._plugins_path, dg_plugin_dir)

        logger.info(f"Downgrading plugin {plugin_id} from {cur_version} to {dg_version}")

        with open(os.path.join(dg_plugin_path, "package.json"), "r") as dg_json_file:
            dg_json_info = json.load(dg_json_file)
            dg_module = self._plugins_module + dg_plugin_dir + "." + dg_json_info["module"]

        # Remove usage specifications if needed
        if plugin_model.pull_accounting:
            cur_module_class = self._get_plugin_module(plugin_model.module)
            cur_module_class(plugin_model).remove_usage_specs()

        self._update_model_data_from_json(plugin_model, dg_module, dg_json_info)
        logger.debug("Plugin model updated")

        # Configure usage specifications if needed
        if plugin_model.pull_accounting:
            dg_module_class = self._get_plugin_module(plugin_model.module)
            dg_module_class(plugin_model).configure_usage_spec()

        rmtree(cur_plugin_path)
        logger.info(f"Version {cur_version} of plugin {plugin_id} removed successfully")

    def downgrade_plugin(self, plugin_id, version=None):
        """
        Downgrades a plugin to a specified version. Newer versions are removed.
        """

        # Get plugin model
        try:
            plugin_model = ResourcePlugin.objects.get(plugin_id=plugin_id)
        except ResourcePlugin.DoesNotExist:
            raise PluginError("Plugin name not found")     
        except Exception as e:
            raise PluginError("Error while retrieving the plugin")

        if version is None:
            version = plugin_model.version_history[-1] if plugin_model.version_history else None
        if version not in plugin_model.version_history:
            logger.error("Cannot find version to downgrade to")
            raise PluginError(
                "Specified version is not installed for this plugin or plugin cannot be further downgraded"
            )

        logger.info(f"Downgrading plugin {plugin_id} to {version}")

        while plugin_model.version != version:
            self._downgrade_plugin_to_last_version(plugin_id, plugin_model)
        category_id = plugin_model.category_id
        ###############
        # En la base de datos del api solo se guardará la versión acctual
        # service category
        s_cat = service_category_manager.ServiceCategoryManager()
        s_cat.update_service_cat(category_id, plugin_model)
        ###############

        logger.info(f"Plugin {plugin_id} successfully downgraded")

    def uninstall_plugin(self, plugin_id):
        """
        Removes a plugin from the system including model and files
        """
        # Get plugin model
        try:
            plugin_model = ResourcePlugin.objects.get(plugin_id=plugin_id)
        except ObjectDoesNotExist as e:
            raise ObjectDoesNotExist(f"The plugin {plugin_id} is not registered") from e

        logger.info(f"Uninstalling plugin {plugin_id}")

        name = plugin_model.name
        # Check if the plugin is in use
        resources = Resource.objects.filter(resource_type=name)

        if len(resources) > 0:
            logger.error(f"Plugin {plugin_id} is in use")
            raise PermissionDenied("The plugin " + plugin_id + " is being used in some resources")

        while plugin_model.version_history:
            self._downgrade_plugin_to_last_version(plugin_id, plugin_model)

        if plugin_model.pull_accounting:
            module_class = self._get_plugin_module(plugin_model.module)
            module_class(plugin_model).remove_usage_specs()

        # Remove plugin files
        plugin_path = self._plugins_path
        for file in os.listdir(plugin_path):
            if file.startswith(f"{plugin_id}-"):
                rmtree(os.path.join(plugin_path, file))

        ###############
        # service category
        s_cat = service_category_manager.ServiceCategoryManager()
        s_cat.remove_service_cat(plugin_model.category_id)
        ###############

        # Remove model
        plugin_model.delete()
        logger.info(f"Plugin {plugin_id} successfully uninstalled")
