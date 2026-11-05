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


import json
import os
from logging import getLogger
from tempfile import TemporaryDirectory
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, RequestDataTooBig
from django.http import HttpResponse
from django.http.multipartparser import MultiPartParserError
from requests.exceptions import ConnectionError, HTTPError, Timeout
from wstore.asset_manager.resource_plugins.plugin_error import (
    PluginCatalogError,
    PluginConflictError,
    PluginError,
    PluginSizeError,
    PluginUnavailableError,
    PluginUsageError,
)
from wstore.asset_manager.resource_plugins.plugin_loader import PluginLoader
from wstore.models import ResourcePlugin
from wstore.store_commons.resource import Resource
from wstore.store_commons.resource_catalog import ResourceCatalogError
from wstore.store_commons.service_catalog import ServiceCatalogError
from wstore.store_commons.utils.http import authentication_required, build_response, get_content_type

logger = getLogger("wstore.default_logger")


def get_plugin_info(plugin):
    site = settings.SITE
    plugin_url = urljoin(site, "charging/api/assetManagement/assetTypes/" + plugin.plugin_id)
    plugin_info = {
        "id": plugin.plugin_id,
        "href": plugin_url,
        "name": plugin.name,
        "type": plugin.type,
        "author": plugin.author,
        "version": plugin.version,
        "categoryId": plugin.category_id,
        "mediaTypes": plugin.media_types,
        "requiresFile": plugin.requires_file,
        "overrides": plugin.overrides,
        "formOrder": plugin.form_order,
    }
    if plugin.form:
        plugin_info["form"] = plugin.form

    return plugin_info


class PluginCollection(Resource):
    @authentication_required
    def read(self, request):
        """
        This view is used to retrieve the existing resource plugin types
        """
        # Load basic types
        result = []

        plugin_type = request.GET.get("type")
        if plugin_type is None:
            plugins = ResourcePlugin.objects.all()
        elif plugin_type in ("service", "resource"):
            plugins = ResourcePlugin.objects.filter(type=plugin_type)
        else:
            return build_response(request, 400, "The type parameter must be service or resource")

        for plugin in plugins:
            result.append(get_plugin_info(plugin))

        mime_type = "application/JSON; charset=UTF-8"
        return HttpResponse(json.dumps(result), status=200, content_type=mime_type)


class PluginInstallCollection(Resource):
    @authentication_required
    def create(self, request):
        if not request.user.is_staff:
            return build_response(request, 403, "Only administrators can install plugins")
        if get_content_type(request)[0] != "multipart/form-data":
            return build_response(request, 415, "Expected a multipart/form-data plugin upload")

        actor = request.user.pk
        logger.info("Plugin installation requested by administrator %s", actor)
        try:
            files = request.FILES
            if set(files) != {"file"} or len(files.getlist("file")) != 1:
                return build_response(request, 400, "Provide exactly one plugin package in the file field")
            upload = files["file"]
            if not upload.size:
                return build_response(request, 400, "The plugin package is empty")

            with TemporaryDirectory(prefix="charging-plugin-") as temporary:
                path = os.path.join(temporary, "package.zip")
                size = 0
                with open(path, "xb") as target:
                    for chunk in upload.chunks():
                        size += len(chunk)
                        target.write(chunk)
                if not size:
                    return build_response(request, 400, "The plugin package is empty")
                plugin_id = PluginLoader().install_plugin(path)

            # Installation has completed. A metadata read failure must not reinstall it.
            logger.info("Administrator %s installed plugin %s", actor, plugin_id)
            metadata = get_plugin_info(ResourcePlugin.objects.get(plugin_id=plugin_id))
            response = HttpResponse(json.dumps(metadata), status=200, content_type="application/json; charset=utf-8")
            response["Location"] = metadata["href"]
            return response
        except Exception as exc:
            if isinstance(exc, (RequestDataTooBig, PluginSizeError)):
                status, message = 413, "Plugin package exceeds the configured size limits"
            elif isinstance(exc, MultiPartParserError):
                status, message = 400, "Invalid multipart upload"
            elif isinstance(exc, PluginConflictError):
                status, message = (
                    409,
                    "Plugin version conflicts with an existing installation or package management is busy",
                )
            elif isinstance(exc, (PluginUnavailableError, ConnectionError, Timeout)):
                status, message = 503, "Plugin installation dependency is unavailable"
            elif isinstance(exc, (PluginCatalogError, HTTPError)):
                status, message = 502, "Plugin catalog operation failed"
            elif isinstance(exc, PluginError):
                status, message = 422, "Plugin package validation or initialization failed"
            else:
                status, message = 500, "Plugin installation could not be completed; check the installed plugin state"
            logger.exception("Plugin installation request by administrator %s failed (%s)", actor, status)
            return build_response(request, status, message)


class PluginEntry(Resource):
    @authentication_required
    def read(self, request, plugin_id):
        try:
            plugin = ResourcePlugin.objects.get(plugin_id=plugin_id)
        except:
            return build_response(request, 404, "Digital asset type not found")

        plugin_info = get_plugin_info(plugin)
        mime_type = "application/JSON; charset=UTF-8"
        return HttpResponse(json.dumps(plugin_info), status=200, content_type=mime_type)

    @authentication_required
    def delete(self, request, plugin_id):
        if not request.user.is_staff:
            return build_response(request, 403, "Only administrators can uninstall plugins")

        actor = request.user.pk
        logger.info("Administrator %s requested removal of plugin %s", actor, plugin_id)
        try:
            PluginLoader().uninstall_plugin(plugin_id)
        except Exception as exc:
            if isinstance(exc, ObjectDoesNotExist):
                status, message = 404, "Plugin is not installed"
            elif isinstance(exc, PermissionDenied):
                status, message = 409, "Plugin is in use and cannot be uninstalled"
            elif isinstance(exc, PluginConflictError):
                status, message = 409, "Another plugin management operation is in progress"
            elif isinstance(exc, (PluginUnavailableError, ConnectionError, Timeout)):
                status, message = 503, "Plugin removal dependency is unavailable"
            elif isinstance(
                exc, (PluginCatalogError, PluginUsageError, ServiceCatalogError, ResourceCatalogError, HTTPError)
            ):
                status, message = 502, "Plugin usage verification or catalog operation failed"
            elif isinstance(exc, PluginError):
                status, message = 422, "Plugin removal could not be validated; check the plugin configuration"
            else:
                status, message = 500, "Plugin removal could not be completed; check the installed plugin state"
            logger.exception("Plugin removal request by administrator %s for %s failed (%s)", actor, plugin_id, status)
            return build_response(request, status, message)

        logger.info("Administrator %s uninstalled plugin %s", actor, plugin_id)
        return HttpResponse(status=204)
