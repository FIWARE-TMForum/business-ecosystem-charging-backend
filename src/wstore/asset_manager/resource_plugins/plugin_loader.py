# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S. L.

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

import importlib
import json
import os
import posixpath
import sys
import zipfile
import zlib
from copy import deepcopy
from logging import getLogger
from pathlib import PurePosixPath, PureWindowsPath
from shutil import rmtree

import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from requests.exceptions import ConnectionError, HTTPError, Timeout
from wstore.asset_manager.resource_plugins.plugin import ResourcePlugin as ResourcePluginHandler
from wstore.asset_manager.resource_plugins.plugin import ServicePlugin
from wstore.asset_manager.resource_plugins.plugin_error import (
    PluginCatalogError,
    PluginConflictError,
    PluginError,
    PluginSizeError,
    PluginUnavailableError,
    PluginUsageError,
)
from wstore.asset_manager.resource_plugins.plugin_rollback import installPluginRollback, package_management
from wstore.asset_manager.resource_plugins.plugin_validator import PluginValidator
from wstore.models import ResourcePlugin
from wstore.store_commons.resource_catalog import ResourceCatalog, ResourceCatalogError
from wstore.store_commons.service_catalog import ServiceCatalog, ServiceCatalogError
from wstore.store_commons.utils.url import get_service_url
from wstore.store_commons.utils.version import is_lower_version

logger = getLogger("wstore.default_logger")


class PluginLoader:
    _plugin_manager = None
    _plugins_path = None
    _plugins_module = None

    def __init__(self):
        logger.debug("Creating new PluginLoader")

        self._plugin_manager = PluginValidator()
        self._catalog = ServiceCatalog()
        self._resource_catalog = ResourceCatalog()
        self._plugins_path = os.path.join(settings.BASEDIR, "wstore", "asset_manager", "resource_plugins", "plugins")
        self._plugins_module = "wstore.asset_manager.resource_plugins.plugins."

        logger.debug(f"Plugins path: {self._plugins_path}")

    def _get_plugin_module(self, module):
        module_class_name = module.split(".")[-1]
        module_package = module.partition("." + module_class_name)[0]

        logger.debug(f"Plugin module: {module_package}.{module_class_name}")
        importlib.invalidate_caches()
        try:
            return getattr(
                __import__(module_package, globals(), locals(), [module_class_name], 0),
                module_class_name,
            )
        except OSError:
            raise
        except Exception as exc:
            raise PluginError("The plugin implementation could not be imported") from exc

    def _validate_archive(self, archive):
        entries = archive.infolist()
        if len(entries) > settings.PLUGIN_ARCHIVE_MAX_ENTRIES:
            raise PluginSizeError("Plugin archive contains too many entries")

        if sum(entry.file_size for entry in entries) > settings.PLUGIN_EXPANDED_MAX_BYTES:
            raise PluginSizeError("Expanded plugin package is too large")

        paths, files, validated = set(), set(), []
        for entry in entries:
            original = entry.filename.replace("\\", "/")
            name = posixpath.normpath(original)
            is_directory = original.endswith("/")

            if (
                not original
                or posixpath.isabs(original)
                or PureWindowsPath(original).drive
                or name == ".."
                or name.startswith("../")
                or (name == "." and not is_directory)
            ):
                raise PluginError("Plugin archive entry escapes the installation directory or has an invalid path")

            if name in paths:
                raise PluginError("Plugin archive contains duplicate entry paths")

            paths.add(name)
            if not is_directory:
                files.add(name)

            validated.append((entry, name, is_directory))

        for name in paths:
            if any(str(parent) in files for parent in PurePosixPath(name).parents):
                raise PluginError("Plugin archive contains conflicting file paths")
        return validated

    def _extract_archive(self, archive, destination, entries):
        total = 0
        try:
            for entry, name, is_directory in entries:
                path = os.path.join(destination, *name.split("/"))
                if is_directory:
                    os.makedirs(path, exist_ok=True)
                    continue

                os.makedirs(os.path.dirname(path), exist_ok=True)

                with archive.open(entry) as source, open(path, "xb") as target:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break

                        total += len(chunk)
                        if total > settings.PLUGIN_EXPANDED_MAX_BYTES:
                            raise PluginSizeError("Expanded plugin package is too large")

                        target.write(chunk)

        except (zipfile.BadZipFile, EOFError, RuntimeError, zlib.error) as exc:
            raise PluginError("Invalid plugin archive contents") from exc

    @staticmethod
    def _clear_module_namespace(namespace):
        for name in list(sys.modules):
            if name == namespace or name.startswith(namespace + "."):
                sys.modules.pop(name, None)
        importlib.invalidate_caches()

    def _catalog_for_type(self, plugin_type):
        if plugin_type == "service":
            return self._catalog
        if plugin_type == "resource":
            return self._resource_catalog
        raise PluginError("Plugin type must be service or resource")

    def _validate_plugin_class(self, info, module_class):
        expected = {"service": ServicePlugin, "resource": ResourcePluginHandler}[info["type"]]
        if not isinstance(module_class, type) or not issubclass(module_class, expected) or module_class is expected:
            raise PluginError("No " + expected.__name__ + " implementation has been found")
        other = ResourcePluginHandler if info["type"] == "service" else ServicePlugin
        if issubclass(module_class, other):
            raise PluginError("A plugin implementation cannot handle both services and resources")
        errors = self._plugin_manager.validate_pull_accounting(info, module_class)
        if errors:
            raise PluginError(errors)

    def _update_model_data_from_json(self, model, module, json_info):
        # Create or update plugin model data
        model.type = json_info["type"]
        model.name = json_info["name"]
        model.version = json_info["version"]
        model.author = json_info["author"]
        model.module = module
        model.requires_file = json_info["requires_file"]
        model.media_types = json_info.get("media_types", [])
        model.form = json_info.get("form", {})
        model.form_order = json_info.get("form_order", [])
        model.overrides = json_info.get("overrides", [])
        model.pull_accounting = json_info.get("pull_accounting", False)
        model.save()

    def _snapshot_model(self, model, rb_log):
        previous = deepcopy(model.__dict__)

        def restore():
            model.__dict__.clear()
            model.__dict__.update(previous)
            model.save()

        rb_log.log_action("RESTORE_MODEL", restore)

    def _synchronize_category(self, model, info, rb_log):
        try:
            return self._write_category(model, info, rb_log)
        except (ConnectionError, Timeout) as exc:
            raise PluginUnavailableError("Plugin catalog is unavailable") from exc
        except (ServiceCatalogError, ResourceCatalogError, HTTPError, ValueError) as exc:
            raise PluginCatalogError("Plugin catalog operation failed") from exc

    def _write_category(self, model, info, rb_log):
        catalog = self._catalog_for_type(info["type"])
        if model.category_id:
            category_id, name, version = model.category_id, model.name, model.version
            rb_log.log_action(
                "RESTORE_CATEGORY",
                lambda: catalog.update_category(category_id, name, version),
            )
            catalog.update_category(category_id, info["name"], info["version"])
        else:
            try:
                category_id = catalog.create_category(info["name"], info["version"])
            except (ServiceCatalogError, ResourceCatalogError) as exc:
                raise PluginCatalogError("Plugin catalog operation failed") from exc

            rb_log.log_action("DELETE_CATEGORY", lambda: catalog.delete_category(category_id))
            model.category_id = category_id

    @package_management
    @installPluginRollback
    def install_plugin(self, path, rb_log=None):
        logger.info(f"Installing plugin: {path}")

        # Validate package file
        if not zipfile.is_zipfile(path):
            logger.error("Invalid package format: Not a zip file")
            raise PluginError("Invalid package format: Not a zip file")

        # Uncompress plugin file
        try:
            archive = zipfile.ZipFile(path, "r")
        except zipfile.BadZipFile as exc:
            raise PluginError("Invalid plugin archive") from exc

        with archive as z:
            entries = self._validate_archive(z)
            # Validate that the file package.json exists
            if "package.json" not in z.namelist():
                logger.error("Invalid package format: Not a zip file")
                raise PluginError("Missing package.json file")

            logger.debug("Found `package.json`")

            # Read package metainfo
            try:
                json_file = z.read("package.json")
            except (zipfile.BadZipFile, EOFError, RuntimeError, zlib.error) as exc:
                raise PluginError("Plugin archive could not be read") from exc

            try:
                json_info = json.loads(json_file)
            except ValueError:
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
                os.mkdir(plugin_path)
            except FileExistsError:
                raise PluginConflictError("An equal version of this plugin is already installed")

            rb_log.log_action("PATH", plugin_path)
            namespace = self._plugins_module + plugin_dir
            rb_log.log_action("MODULES", lambda: self._clear_module_namespace(namespace))

            # Extract files
            self._extract_archive(z, plugin_path, entries)
            logger.debug(f"Plugin extracted to {plugin_path}")

        # Get plugin model
        try:
            plugin_model = ResourcePlugin.objects.get(plugin_id=plugin_id)
            if plugin_model.type != json_info["type"]:
                raise PluginError("A plugin cannot change type during upgrade")
            if not is_lower_version(plugin_model.version, json_info["version"]):
                logger.error("A newer version of this plugin is already installed")
                raise PluginConflictError("A newer version of this plugin is already installed")

            self._snapshot_model(plugin_model, rb_log)
            plugin_model.version_history.append(plugin_model.version)
        except ObjectDoesNotExist:
            plugin_model = ResourcePlugin(plugin_id=plugin_id)
            rb_log.log_action("MODEL", plugin_model)

        # Create a  __init__.py file if needed
        open(os.path.join(plugin_path, "__init__.py"), "a").close()

        # Validate plugin main class
        module = self._plugins_module + plugin_dir + "." + json_info["module"]
        module_class = self._get_plugin_module(module)

        self._validate_plugin_class(json_info, module_class)

        self._synchronize_category(plugin_model, json_info, rb_log)
        self._update_model_data_from_json(plugin_model, module, json_info)
        logger.debug("Plugin model saved to database")

        # Configure usage specifications if needed
        if plugin_model.pull_accounting:
            module_class(plugin_model).configure_usage_spec()

        logger.info("Plugin %s version %s installed", plugin_id, json_info["version"])

        return plugin_id

    @installPluginRollback
    def _downgrade_plugin_to_last_version(self, plugin_id, plugin_model, rb_log=None):
        self._snapshot_model(plugin_model, rb_log)
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

        self._synchronize_category(plugin_model, dg_json_info, rb_log)
        self._update_model_data_from_json(plugin_model, dg_module, dg_json_info)
        logger.debug("Plugin model updated")

        # Configure usage specifications if needed
        if plugin_model.pull_accounting:
            dg_module_class = self._get_plugin_module(plugin_model.module)
            dg_module_class(plugin_model).configure_usage_spec()

        rmtree(cur_plugin_path)
        logger.info(f"Version {cur_version} of plugin {plugin_id} removed successfully")

    @package_management
    def downgrade_plugin(self, plugin_id, version=None):
        """
        Downgrades a plugin to a specified version. Newer versions are removed.
        """

        # Get plugin model
        plugin_model = ResourcePlugin.objects.get(plugin_id=plugin_id)

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

        logger.info(f"Plugin {plugin_id} successfully downgraded")

    @package_management
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

        catalog = self._catalog_for_type(plugin_model.type)
        if not plugin_model.category_id:
            raise PluginError("Plugin has no category; run syncplugincategories before removal")
        if self._plugin_references_exist(plugin_model):
            raise PermissionDenied(
                "The plugin " + plugin_id + " is being used by specifications or inventory instances"
            )

        # Do not downgrade through old versions merely to remove a package.
        if plugin_model.pull_accounting:
            module_class = self._get_plugin_module(plugin_model.module)
            module_class(plugin_model).remove_usage_specs()

        # Keep the package and registry if the catalog refuses deletion.
        catalog.delete_category(plugin_model.category_id)
        for version in [plugin_model.version] + plugin_model.version_history:
            plugin_dir = f"{plugin_id}-{version.replace('.', '-')}"
            plugin_path = os.path.join(self._plugins_path, plugin_dir)
            if os.path.isdir(plugin_path):
                rmtree(plugin_path)
        plugin_model.delete()
        logger.info(f"Plugin {plugin_id} successfully uninstalled")

    def _iter_usage_documents(self, api, path):
        """Scan full collections; nested characteristic filters are not assumed supported."""
        offset, seen = 0, set()
        while True:
            response = requests.get(
                get_service_url(api, path),
                params={"offset": offset, "limit": 100},
                verify=settings.VERIFY_REQUESTS,
                timeout=30,
            )
            response.raise_for_status()
            try:
                documents = response.json()
            except ValueError as exc:
                raise PluginUsageError("Plugin usage verification returned invalid JSON") from exc
            if not isinstance(documents, list):
                raise PluginUsageError("Plugin usage verification returned an invalid collection")
            if not documents:
                return
            for document in documents:
                if (
                    not isinstance(document, dict)
                    or not isinstance(document.get("id"), str)
                    or not document["id"].strip()
                    or document["id"] in seen
                ):
                    raise PluginUsageError("Plugin usage pagination returned invalid or repeated documents")
                seen.add(document["id"])
                yield document
            # Continue even after short pages: APIs can impose a lower page-size cap.
            offset += len(documents)

    def _plugin_references_exist(self, model):
        kind = model.type
        field, values_field = (
            ("specCharacteristic", "characteristicValueSpecification")
            if kind == "service"
            else ("resourceSpecCharacteristic", "resourceSpecCharacteristicValue")
        )
        sources = (
            (kind + "_catalog", "/" + kind + "Specification", field, values_field),
            (kind + "_inventory", "/" + kind, kind + "Characteristic", None),
        )
        for api, path, characteristic_field, value_field in sources:
            for document in self._iter_usage_documents(api, path):
                characteristics = document.get(characteristic_field, [])
                if not isinstance(characteristics, list):
                    raise PluginUsageError("Plugin usage verification returned invalid characteristics")
                for characteristic in characteristics:
                    if not isinstance(characteristic, dict):
                        raise PluginUsageError("Plugin usage verification returned an invalid characteristic")
                    name = characteristic.get("name", "")
                    if not isinstance(name, str) or name.strip().lower() != kind + " type":
                        continue
                    values = characteristic.get(value_field) if value_field else [characteristic]
                    if not isinstance(values, list) or not values:
                        raise PluginUsageError("Plugin type reference cannot be verified")
                    for entry in values:
                        if not isinstance(entry, dict) or "value" not in entry:
                            raise PluginUsageError("Plugin type reference cannot be verified")
                        value = entry["value"]
                        # Legacy malformed references still represent a dependency.
                        if isinstance(value, dict):
                            value = value.get("id")
                        if not isinstance(value, str) or not value.strip():
                            raise PluginUsageError("Plugin type reference cannot be verified")
                        if value == model.category_id:
                            logger.info("Plugin %s is referenced by %s %s", model.plugin_id, api, document["id"])
                            return True
        return False

    @package_management
    @installPluginRollback
    def synchronize_plugin_category(self, plugin_id, rb_log=None):
        """Publish a category for an existing installation without reinstalling it."""
        model = ResourcePlugin.objects.get(plugin_id=plugin_id)
        if not model.category_id:
            self._snapshot_model(model, rb_log)
            self._synchronize_category(
                model, {"name": model.name, "version": model.version, "type": model.type}, rb_log
            )
            model.save()
        return model.category_id
