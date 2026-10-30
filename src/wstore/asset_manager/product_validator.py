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

from urllib.parse import quote

import requests
from django.conf import settings

from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.errors import ProductError
from wstore.asset_manager.resource_plugins.decorators import on_product_spec_validation
from wstore.store_commons.service_catalog import ServiceCatalog
from wstore.store_commons.utils.url import get_service_url


class ProductValidator(CatalogValidator):
    """Validate product/service associations before the proxy writes the catalog."""

    def __init__(self):
        super().__init__()

        self._service_catalog = ServiceCatalog()

    @staticmethod
    def _prepare(product_spec):
        if not isinstance(product_spec, dict):
            raise ProductError("The product specification must be an object")

        if "isBundle" in product_spec and not isinstance(product_spec["isBundle"], bool):
            raise ProductError("The field isBundle must be a boolean")

    @staticmethod
    def _reference_ids(specification, field):
        references = specification.get(field, [])

        if not isinstance(references, list):
            raise ProductError("The field " + field + " must be a list of references")

        ids = []

        for reference in references:
            if (
                not isinstance(reference, dict)
                or not isinstance(reference.get("id"), str)
                or not reference["id"].strip()
            ):
                raise ProductError("Each " + field + " reference must contain an id")

            if reference["id"] in ids:
                raise ProductError("Duplicate " + field + " reference: " + reference["id"])

            ids.append(reference["id"])

        return ids

    @staticmethod
    def _check_specification(specification, specification_id, kind):
        if not isinstance(specification, dict) or specification.get("id") != specification_id:
            raise ProductError("Invalid " + kind + " specification reference: " + specification_id)

        return specification

    def _get_product_spec(self, specification_id):
        url = get_service_url("catalog", "/productSpecification/" + quote(specification_id, safe=""))

        try:
            response = requests.get(url, verify=settings.VERIFY_REQUESTS, timeout=30)
            response.raise_for_status()

            specification = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProductError("Cannot retrieve product specification: " + specification_id) from exc

        return self._check_specification(specification, specification_id, "product")

    def _get_service_specs(self, product_spec):
        specifications = []

        for specification_id in self._reference_ids(product_spec, "serviceSpecification"):
            try:
                specification = self._service_catalog.get_specification(specification_id)
            except (requests.RequestException, ValueError) as exc:
                raise ProductError("Cannot retrieve service specification: " + specification_id) from exc

            specifications.append(self._check_specification(specification, specification_id, "service"))

        return specifications

    def validate_creation(self, provider, catalog_element):
        self._prepare(catalog_element)

        bundled_ids = self._reference_ids(catalog_element, "bundledProductSpecification")
        service_ids = self._reference_ids(catalog_element, "serviceSpecification")

        if catalog_element.get("isBundle", False):
            if len(bundled_ids) < 2:
                raise ProductError("A product spec bundle must contain at least two bundled product specs")

            if service_ids:
                raise ProductError("Product spec bundles cannot define their own services")

            products = [self._get_product_spec(specification_id) for specification_id in bundled_ids]

            for product in products:
                self._prepare(product)

                if product.get("isBundle", False) or self._reference_ids(product, "bundledProductSpecification"):
                    raise ProductError("Product spec bundles cannot contain other bundles")
        else:
            if bundled_ids:
                raise ProductError("Individual product specs cannot contain bundled product specs")

            products = [catalog_element]

        # Resolve every reference before invoking plugins; missing services cannot be silently skipped.
        associations = [(product, self._get_service_specs(product)) for product in products]

        for product, services in associations:
            for service in services:
                on_product_spec_validation(provider, service, product)

    def validate_update(self, provider, catalog_element):
        self.validate_creation(provider, catalog_element)
