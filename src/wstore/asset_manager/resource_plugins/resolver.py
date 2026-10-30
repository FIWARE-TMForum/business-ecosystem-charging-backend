# -*- coding: utf-8 -*-

# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

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

from requests.exceptions import RequestException

from wstore.asset_manager.errors import ProductError
from wstore.store_commons.product_catalog import ProductCatalog
from wstore.store_commons.service_catalog import ServiceCatalog


def reference_ids(document, field):
    references = document.get(field, [])

    if not isinstance(references, list):
        raise ProductError("The field " + field + " must be a list of references")

    ids = []

    for reference in references:
        if not isinstance(reference, dict) or not isinstance(reference.get("id"), str) or not reference["id"].strip():
            raise ProductError("Each " + field + " reference must contain an id")

        if reference["id"] in ids:
            raise ProductError("Duplicate " + field + " reference: " + reference["id"])

        ids.append(reference["id"])

    return ids


def _check_document(document, kind):
    if not isinstance(document, dict):
        raise ProductError("The " + kind + " must be an object")

    if "isBundle" in document and not isinstance(document["isBundle"], bool):
        raise ProductError("The field isBundle must be a boolean")


class CatalogResolver:
    """Resolve service/product associations without invoking catalog validation."""

    def __init__(self):
        self._catalog = ProductCatalog()
        self._service_catalog = ServiceCatalog()

    def product_services(self, product_spec):
        _check_document(product_spec, "product specification")

        bundled_ids = reference_ids(product_spec, "bundledProductSpecification")
        service_ids = reference_ids(product_spec, "serviceSpecification")

        if product_spec.get("isBundle", False):
            if len(bundled_ids) < 2:
                raise ProductError("A product spec bundle must contain at least two bundled product specs")

            if service_ids:
                raise ProductError("Product spec bundles cannot define their own services")

            products = [self._catalog.get_specification(specification_id) for specification_id in bundled_ids]

            for product in products:
                _check_document(product, "product specification")

                if product.get("isBundle", False) or reference_ids(product, "bundledProductSpecification"):
                    raise ProductError("Product spec bundles cannot contain other bundles")
        else:
            if bundled_ids:
                raise ProductError("Individual product specs cannot contain bundled product specs")

            products = [product_spec]

        associations = []

        for product in products:
            for specification_id in reference_ids(product, "serviceSpecification"):
                try:
                    service_spec = self._service_catalog.get_specification(specification_id)
                except (RequestException, ValueError) as exc:
                    raise ProductError("Cannot retrieve service specification: " + specification_id) from exc

                if not isinstance(service_spec, dict) or service_spec.get("id") != specification_id:
                    raise ProductError("Invalid service specification reference: " + specification_id)

                associations.append((service_spec, product))

        return associations

    def offering_services(self, product_offering):
        _check_document(product_offering, "product offering")

        bundled_ids = reference_ids(product_offering, "bundledProductOffering")

        if product_offering.get("isBundle", False):
            if len(bundled_ids) < 2:
                raise ProductError("Offering bundles must contain at least two bundled offerings")

            offerings = [self._catalog.get_offering(offering_id) for offering_id in bundled_ids]

            for offering in offerings:
                _check_document(offering, "product offering")

                if offering.get("isBundle", False) or reference_ids(offering, "bundledProductOffering"):
                    raise ProductError("Offering bundles cannot contain other bundles")
        else:
            if bundled_ids:
                raise ProductError("Individual offerings cannot contain bundled offerings")

            offerings = [product_offering]

        associations = []

        for offering in offerings:
            product_ref = offering.get("productSpecification")
            ids = reference_ids({"productSpecification": [product_ref]}, "productSpecification")
            product_spec = self._catalog.get_specification(ids[0])

            associations.extend(self.product_services(product_spec))

        return associations
