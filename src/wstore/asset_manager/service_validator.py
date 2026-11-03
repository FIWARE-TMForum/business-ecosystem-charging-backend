# -*- coding: utf-8 -*-

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

from copy import deepcopy

from bson import ObjectId
from django.core.exceptions import PermissionDenied

from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.models import Resource
from wstore.asset_manager.resource_plugins.decorators import on_service_spec_validation
from wstore.store_commons.service_catalog import ServiceCatalog, ServiceCatalogError
from wstore.store_commons.utils.version import is_valid_version


class ServiceValidator(CatalogValidator):
    """Validate service form values and references to provider-owned uploaded files."""

    def __init__(self):
        super().__init__()
        self._catalog = ServiceCatalog()

    def parse_spec_characteristics(self, service_spec):
        """Parse Service Type and index the characteristics of a plugin-backed specification."""
        entries = service_spec["specCharacteristic"]
        characteristics = {}

        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                raise ServiceError("Each service characteristic must have a name")

            characteristics.setdefault(entry["name"].strip().lower(), []).append(entry)

        service_type = self._get_spec_characteristic_value(characteristics, "service type")

        if (
            not isinstance(service_type, dict)
            or not isinstance(service_type.get("id"), str)
            or not service_type["id"].strip()
        ):
            raise ServiceError("Service Type must contain a service category reference with an id")

        return characteristics

    @staticmethod
    def _get_spec_characteristic_value(characteristics, name):
        entries = characteristics.get(name, [])

        if len(entries) != 1:
            raise ServiceError("The service specification must contain exactly one " + name + " characteristic")

        values = entries[0].get("characteristicValueSpecification")

        if (
            not isinstance(values, list)
            or len(values) != 1
            or not isinstance(values[0], dict)
            or "value" not in values[0]
        ):
            raise ServiceError("The characteristic " + name + " must contain exactly one value")

        return values[0]["value"]

    def _get_service_characteristics(self, characteristics, form):
        names = {name.strip().lower() for name in (form or {})}

        return {
            name: self._get_spec_characteristic_value(characteristics, name)
            for name in names
            if name in characteristics
        }

    @staticmethod
    def validate_asset_characteristics(plugin_model, values):
        if plugin_model is None:
            return

        # The old asset metadata keys are now individual specification characteristics.
        for name, field in (plugin_model.form or {}).items():
            key = name.strip().lower()

            if key not in values:
                if field.get("mandatory"):
                    raise ServiceError("Missing mandatory service characteristic " + name)

                continue

            value = values[key]

            if field["type"] == "checkbox":
                if not isinstance(value, bool):
                    raise ServiceError("The characteristic " + name + " must be a boolean")
            elif not isinstance(value, str):
                raise ServiceError("The characteristic " + name + " must be a string")

            if field["type"] == "select" and value.lower() not in [
                option["value"].lower() for option in field["options"]
            ]:
                raise ServiceError("The characteristic " + name + " must be one of the configured options")

    def _validate_file(self, provider, characteristics, plugin_model):
        if "file" not in characteristics:
            raise ServiceError("The service specification must contain a File characteristic")

        reference = self._get_spec_characteristic_value(characteristics, "file")

        if (
            not isinstance(reference, dict)
            or not isinstance(reference.get("id"), str)
            or not ObjectId.is_valid(reference["id"])
        ):
            raise ServiceError("File must contain an uploaded file reference with a valid id")

        try:
            resource = Resource.objects.get(pk=ObjectId(reference["id"]))
        except Resource.DoesNotExist:
            raise ServiceError("The uploaded file does not exist")

        if resource.provider_id != provider.pk:
            raise PermissionDenied("The uploaded file does not belong to the provider")

        if not resource.resource_path:
            raise ServiceError("File must reference an uploaded file, not an external URL")

        if plugin_model.media_types and resource.content_type.lower() not in [
            media_type.lower() for media_type in plugin_model.media_types
        ]:
            raise ServiceError("The uploaded file's media type is not supported by the service specification's plugin")

    def _validate_service_characteristics(self, provider, service_spec, plugin_model):
        characteristics = self.parse_spec_characteristics(service_spec)

        if plugin_model.requires_file:
            self._validate_file(provider, characteristics, plugin_model)

        values = self._get_service_characteristics(characteristics, plugin_model.form)

        self.validate_asset_characteristics(plugin_model, values)

    def _prepare(self, service_spec):
        if not isinstance(service_spec, dict):
            raise ServiceError("The service specification must be an object")

        if "version" in service_spec and (
            not isinstance(service_spec["version"], str) or not is_valid_version(service_spec["version"])
        ):
            raise ServiceError("The field version does not have a valid format")

    @on_service_spec_validation
    def _validate_service(self, provider, service_spec, plugin_model):
        self._validate_service_characteristics(provider, service_spec, plugin_model)

    def validate_creation(self, provider, catalog_element):
        self._prepare(catalog_element)
        self._validate_service(provider, catalog_element)

    def _persisted(self, service_spec):
        if not isinstance(service_spec, dict) or not isinstance(service_spec.get("id"), str) or not service_spec["id"]:
            raise ServiceError("A service specification id is required")

        specification = self._catalog.get_specification(service_spec["id"])

        if not isinstance(specification, dict) or str(specification.get("id")) != service_spec["id"]:
            raise ServiceCatalogError("Service catalog returned an invalid service specification")

        return specification

    def _proposed_update(self, service_spec):
        previous = self._persisted(service_spec)
        proposed = {**deepcopy(previous), **deepcopy(service_spec)}

        return previous, proposed

    @on_service_spec_validation
    def _validate_service_update(self, provider, service_spec, plugin_model):
        previous, proposed = self._proposed_update(service_spec)

        if proposed.get("version") != previous.get("version"):
            raise ServiceError("Service specification version changes are not supported yet")

        self._validate_service_characteristics(provider, service_spec, plugin_model)

    def validate_update(self, provider, catalog_element):
        self._prepare(catalog_element)

        self._validate_service_update(provider, catalog_element)
