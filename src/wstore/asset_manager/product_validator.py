# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2023 Future Internet Consulting and Development Solutions S.L

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

from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.resource_plugins.decorators import (
    on_pre_product_spec_creation,
    on_post_product_spec_creation,
    on_pre_product_spec_update,
    on_post_product_spec_update,
)


class ProductValidator(CatalogValidator):
    """Dispatch product callbacks before and after successful catalog writes."""

    def validate_creation(self, provider, catalog_element):
        on_pre_product_spec_creation(provider, catalog_element)

    def validate_update(self, provider, catalog_element):
        on_pre_product_spec_update(provider, catalog_element)

    def post_create(self, provider, catalog_element):
        on_post_product_spec_creation(provider, catalog_element)

    def post_update(self, provider, catalog_element):
        on_post_product_spec_update(provider, catalog_element)
