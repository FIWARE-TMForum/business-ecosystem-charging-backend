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

from wstore.asset_manager.errors import ResourceError
from wstore.asset_manager.specification_validator import SpecificationValidator
from wstore.asset_manager.resource_plugins.decorators import on_resource_spec_validation
from wstore.store_commons.resource_catalog import ResourceCatalog, ResourceCatalogError


class ResourceValidator(SpecificationValidator):
    """Validate resource specifications using the shared file/form validation rules."""

    kind = "resource"
    characteristics_field = "resourceSpecCharacteristic"
    values_field = "resourceSpecCharacteristicValue"
    error_type = ResourceError
    catalog_error = ResourceCatalogError

    def __init__(self):
        super().__init__(ResourceCatalog())

    @on_resource_spec_validation
    def _validate_specification(self, provider, resource_spec, plugin_model):
        return super()._validate_specification(provider, resource_spec, plugin_model)

    @on_resource_spec_validation
    def _validate_specification_update(self, provider, resource_spec, plugin_model):
        return super()._validate_specification_update(provider, resource_spec, plugin_model)
