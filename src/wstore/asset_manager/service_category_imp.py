# -*- coding: utf-8 -*-

# Copyright (c) 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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

from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

#from wstore.charging_engine.accounting.errors import ServiceError


class ServiceCategory:
    def __init__(self):
        self._serviceCategory_api = settings.SERVICE_CATALOG
        if not self._serviceCategory_api.endswith("/"):
            self._serviceCategory_api += "/"

    def _create_serviceCategory_item(self, url, serviceCategory_item):
        # Override the needed headers to avoid spec hrefs to be created with internal host and port
        headers = {"Host": urlparse(settings.SITE).netloc}

        r = requests.post(url, headers=headers, json=serviceCategory_item)
        r.raise_for_status()

        return r.json()
    
    def create_service_category(self, serviceCategory):
        """
        Creates a new serviceCategory in the serviceCategory API
        :param serviceCategory: serviceCategory document to be created
        :return:the created serviceCategory document
        """
        path = "serviceCategory"
        url = urljoin(self._serviceCategory_api, path)

        return self._create_serviceCategory_item(url, serviceCategory)

    def delete_service_category(self, spec_id):
        """
        Deletes a serviceCategory from the serviceCategory API
        :param spec_id: id of the serviceCategory to be deleted
        """
        path = "serviceCategory/" + spec_id
        url = urljoin(self._serviceCategory_api, path)

        r = requests.delete(url)
        r.raise_for_status()

    def get_service_category(self, serviceCategory_name=None):
        """
        Retrieves the serviceCategory made by a customer filtered by service and status
        :param customer: username of the customer
        :param state: state of the serviceCategory to be retrieved
        :return: List of customer serviceCategorys
        """
        #A ver se non me equivoco o relatedParty non debería de facer falta
        #en principio os plugins son os que hai, antes non se filtraba
        #consigues todos os plugins e chamas directamente pa rexistralos
        #tampouco debería facer falta o state

        # Get customer serviceCategory filtered by state
        path = "serviceCategory/"
        url = urljoin(self._serviceCategory_api, path)

        if serviceCategory_name is not None:
            url += "?name=" + str(serviceCategory_name)

        r = requests.get(url, headers={"Accept": "application/json"})

        r.raise_for_status()

        raw_serviceCategory = r.json()

        return r.json()


    def _patch_serviceCategory(self, serviceCategory_id, patch):
        path = "serviceCategory/" + str(serviceCategory_id)
        url = urljoin(self._serviceCategory_api, path)

        r = requests.patch(url, json=patch)
        r.raise_for_status()

    def update_service_category(self, serviceCategory_id, serviceCategory):
        """
        Updates the status of a given serviceCategory
        :param serviceCategory_id: serviceCategory to be modified
        :param state: new status
        """
        self._patch_serviceCategory(serviceCategory_id, serviceCategory)