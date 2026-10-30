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

from urllib.parse import quote

import requests
from django.conf import settings

from wstore.store_commons.utils.url import get_service_url


class ServiceCatalogError(Exception):
    pass


class ServiceCatalog:
    def _request(self, method, path, **kwargs):
        response = requests.request(
            method, get_service_url("service_catalog", path), verify=settings.VERIFY_REQUESTS, timeout=30, **kwargs
        )
        response.raise_for_status()
        return response

    @staticmethod
    def category_data(name, version):
        return {"name": name, "version": version}

    def create_category(self, name, version):
        category = self._request("POST", "/serviceCategory", json=self.category_data(name, version)).json()
        if not isinstance(category, dict) or not category.get("id"):
            raise ServiceCatalogError("Service catalog returned a category without an id")
        return str(category["id"])

    def update_category(self, category_id, name, version):
        self._request(
            "PATCH", "/serviceCategory/" + quote(str(category_id), safe=""), json=self.category_data(name, version)
        )

    def category_in_use(self, category_id):
        # Existence is enough: no need to download every matching candidate.
        candidates = self._request("GET", "/serviceCandidate", params={"category.id": category_id, "limit": 1}).json()
        if not isinstance(candidates, list):
            raise ServiceCatalogError("Service catalog returned an invalid candidate collection")
        return bool(candidates)

    def delete_category(self, category_id):
        self._request("DELETE", "/serviceCategory/" + quote(str(category_id), safe=""))

    def get_specification(self, specification_id):
        """Retrieve a service specification from the catalog."""
        url = get_service_url("service_catalog", f"/serviceSpecification/{specification_id}")
        response = requests.get(url, verify=settings.VERIFY_REQUESTS)

        return response.json()
