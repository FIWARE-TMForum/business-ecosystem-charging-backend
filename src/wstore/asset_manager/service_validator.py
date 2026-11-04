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

from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.specification_validator import SpecificationValidator
from wstore.asset_manager.resource_plugins.decorators import (
    on_pre_service_spec_creation,
    on_pre_service_spec_update,
    on_post_service_spec_creation,
    on_post_service_spec_update,
)
from wstore.store_commons.service_catalog import ServiceCatalog, ServiceCatalogError


class ServiceValidator(SpecificationValidator):
    """Validate service specifications using the shared file/form validation rules."""

    kind = "service"
    characteristics_field = "specCharacteristic"
    values_field = "characteristicValueSpecification"
    error_type = ServiceError
    catalog_error = ServiceCatalogError

    def __init__(self):
        super().__init__(ServiceCatalog())

    def post_create(self, provider, service_spec):
        self._prepare_post_action(service_spec, "created")
        on_post_service_spec_creation(provider, service_spec)

    def post_update(self, provider, service_spec):
        self._prepare_post_action(service_spec, "updated")
        on_post_service_spec_update(provider, service_spec)

    @on_pre_service_spec_creation
    def _validate_specification(self, provider, service_spec, plugin_model):
        return super()._validate_specification(provider, service_spec, plugin_model)

    @on_pre_service_spec_update
    def _validate_specification_update(self, provider, service_spec, plugin_model):
        return super()._validate_specification_update(provider, service_spec, plugin_model)
