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
from wstore.asset_manager.models import Resource
from wstore.store_commons.utils.version import is_valid_version


class SpecificationValidator(CatalogValidator):
    """Common validation for plugin-backed service and resource specifications."""

    def __init__(self, catalog):
        super().__init__()
        self._catalog = catalog

    def parse_spec_characteristics(self, specification):
        """Index the characteristics of a plugin-backed specification."""
        entries = specification[self.characteristics_field]
        characteristics = {}

        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                raise self.error_type("Each " + self.kind + " characteristic must have a name")

            characteristics.setdefault(entry["name"].strip().lower(), []).append(entry)

        plugin_type = self._get_spec_characteristic_value(characteristics, self.kind + " type")

        if not isinstance(plugin_type, str) or not plugin_type.strip():
            raise self.error_type(
                self.kind.title() + " Type must contain a non-empty " + self.kind + " category id string"
            )

        return characteristics

    @classmethod
    def _get_spec_characteristic_value(cls, characteristics, name):
        entries = characteristics.get(name, [])

        if len(entries) != 1:
            raise cls.error_type(
                "The " + cls.kind + " specification must contain exactly one " + name + " characteristic"
            )

        values = entries[0].get(cls.values_field)

        if (
            not isinstance(values, list)
            or len(values) != 1
            or not isinstance(values[0], dict)
            or "value" not in values[0]
        ):
            raise cls.error_type("The characteristic " + name + " must contain exactly one value")

        return values[0]["value"]

    def _get_form_characteristics(self, characteristics, form):
        names = {name.strip().lower() for name in (form or {})}

        return {
            name: self._get_spec_characteristic_value(characteristics, name)
            for name in names
            if name in characteristics
        }

    @classmethod
    def validate_asset_characteristics(cls, plugin_model, values):
        if plugin_model is None:
            return

        # The old asset metadata keys are now individual specification characteristics.
        for name, field in (plugin_model.form or {}).items():
            key = name.strip().lower()

            if key not in values:
                if field.get("mandatory"):
                    raise cls.error_type("Missing mandatory " + cls.kind + " characteristic " + name)

                continue

            value = values[key]

            if field["type"] == "checkbox":
                if not isinstance(value, bool):
                    raise cls.error_type("The characteristic " + name + " must be a boolean")
            elif not isinstance(value, str):
                raise cls.error_type("The characteristic " + name + " must be a string")

            if field["type"] == "select" and value.lower() not in [
                option["value"].lower() for option in field["options"]
            ]:
                raise cls.error_type("The characteristic " + name + " must be one of the configured options")

    def _validate_file(self, provider, characteristics, plugin_model):
        if "file" not in characteristics:
            raise self.error_type("The " + self.kind + " specification must contain a File characteristic")

        file_id = self._get_spec_characteristic_value(characteristics, "file")

        if not isinstance(file_id, str) or not ObjectId.is_valid(file_id):
            raise self.error_type("File must contain a valid uploaded file id string")

        try:
            resource = Resource.objects.get(pk=ObjectId(file_id))
        except Resource.DoesNotExist:
            raise self.error_type("The uploaded file does not exist")

        if resource.provider_id != provider.pk:
            raise PermissionDenied("The uploaded file does not belong to the provider")

        if not resource.resource_path:
            raise self.error_type("File must reference an uploaded file, not an external URL")

        if plugin_model.media_types and resource.content_type.lower() not in [
            media_type.lower() for media_type in plugin_model.media_types
        ]:
            raise self.error_type(
                "The uploaded file's media type is not supported by the "
                + self.kind
                + " specification's plugin"
            )

    def _validate_characteristics(self, provider, specification, plugin_model):
        characteristics = self.parse_spec_characteristics(specification)

        if plugin_model.requires_file:
            self._validate_file(provider, characteristics, plugin_model)

        values = self._get_form_characteristics(characteristics, plugin_model.form)

        self.validate_asset_characteristics(plugin_model, values)

    def _prepare(self, specification):
        if not isinstance(specification, dict):
            raise self.error_type("The " + self.kind + " specification must be an object")

        if "version" in specification and (
            not isinstance(specification["version"], str) or not is_valid_version(specification["version"])
        ):
            raise self.error_type("The field version does not have a valid format")

    def _validate_specification(self, provider, specification, plugin_model):
        self._validate_characteristics(provider, specification, plugin_model)

    def validate_creation(self, provider, catalog_element):
        self._prepare(catalog_element)
        self._validate_specification(provider, catalog_element)

    def _prepare_post_action(self, catalog_element, operation):
        """Require a persisted specification before notifying its plugin."""
        if not isinstance(catalog_element, dict):
            raise self.error_type("The " + self.kind + " specification must be an object")
        if not isinstance(catalog_element.get("id"), str) or not catalog_element["id"].strip():
            raise self.error_type("A " + operation + " " + self.kind + " specification id is required")

    def _persisted(self, specification):
        if (
            not isinstance(specification, dict)
            or not isinstance(specification.get("id"), str)
            or not specification["id"]
        ):
            raise self.error_type("A " + self.kind + " specification id is required")

        persisted = self._catalog.get_specification(specification["id"])

        if not isinstance(persisted, dict) or str(persisted.get("id")) != specification["id"]:
            raise self.catalog_error(
                self.kind.title() + " catalog returned an invalid " + self.kind + " specification"
            )

        return persisted

    def _proposed_update(self, specification):
        previous = self._persisted(specification)
        proposed = {**deepcopy(previous), **deepcopy(specification)}

        return previous, proposed

    def _validate_specification_update(self, provider, specification, plugin_model):
        previous, proposed = self._proposed_update(specification)

        if proposed.get("version") != previous.get("version"):
            raise self.error_type(self.kind.title() + " specification version changes are not supported yet")

        self._validate_characteristics(provider, specification, plugin_model)

    def validate_update(self, provider, catalog_element):
        self._prepare(catalog_element)

        self._validate_specification_update(provider, catalog_element)
