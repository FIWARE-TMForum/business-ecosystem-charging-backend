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

from urllib.parse import quote

import requests
from django.conf import settings

from wstore.store_commons.utils.url import get_service_url


class ProductCatalogError(Exception):
    pass


class ProductCatalog:
    """Read product catalog documents for validation and plugin resolution."""

    def _get(self, collection, document_id):
        path = "/" + collection + "/" + quote(document_id, safe="")
        url = get_service_url("catalog", path)

        try:
            response = requests.get(url, verify=settings.VERIFY_REQUESTS, timeout=30)
            response.raise_for_status()

            document = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProductCatalogError("Cannot retrieve " + collection + ": " + document_id) from exc

        if not isinstance(document, dict) or document.get("id") != document_id:
            raise ProductCatalogError("Invalid " + collection + " reference: " + document_id)

        return document

    def get_specification(self, specification_id):
        return self._get("productSpecification", specification_id)

    def get_offering(self, offering_id):
        return self._get("productOffering", offering_id)

    def get_price(self, price_id):
        return self._get("productOfferingPrice", price_id)
