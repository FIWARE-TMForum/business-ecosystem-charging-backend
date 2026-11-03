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
from wstore.store_commons.resource_catalog import ResourceCatalog


def reference_ids(document, field):
    references = document.get(field, [])

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


def _check_document(document, kind):
    if not isinstance(document, dict):
        raise ProductError("The " + kind + " must be an object")

    if "isBundle" in document and not isinstance(document["isBundle"], bool):
        raise ProductError("The field isBundle must be a boolean")


class CatalogResolver:
    """Resolve specification/product associations without invoking catalog validation."""

    def __init__(self):
        self._catalog = ProductCatalog()
        self._service_catalog = ServiceCatalog()
        self._resource_catalog = ResourceCatalog()

    def product_services(self, product_spec):
        return [
            (specification, product)
            for _, specification, product in self.product_specifications(
                product_spec, plugin_types=("service",)
            )
        ]

    def product_specifications(self, product_spec, plugin_types=("service", "resource")):
        """Resolve typed service/resource associations for individual products or bundles."""
        _check_document(product_spec, "product specification")

        bundled_ids = reference_ids(product_spec, "bundledProductSpecification")
        specification_ids = {
            kind: reference_ids(product_spec, kind + "Specification") for kind in plugin_types
        }

        if product_spec.get("isBundle", False):
            if len(bundled_ids) < 2:
                raise ProductError("A product spec bundle must contain at least two bundled product specs")

            for kind, ids in specification_ids.items():
                if ids:
                    raise ProductError("Product spec bundles cannot define their own " + kind + "s")

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

        catalogs = {"service": self._service_catalog, "resource": self._resource_catalog}
        for product in products:
            for kind in plugin_types:
                for specification_id in reference_ids(product, kind + "Specification"):
                    try:
                        specification = catalogs[kind].get_specification(specification_id)
                    except (RequestException, ValueError) as exc:
                        raise ProductError(
                            "Cannot retrieve " + kind + " specification: " + specification_id
                        ) from exc

                    if not isinstance(specification, dict) or specification.get("id") != specification_id:
                        raise ProductError(
                            "Invalid " + kind + " specification reference: " + specification_id
                        )

                    associations.append((kind, specification, product))

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
