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


class ServiceSpecification:
    def __init__(self):
        self._serviceSpecification_api = settings.SERVICE_CATALOG
        if not self._serviceSpecification_api.endswith("/"):
            self._serviceSpecification_api += "/"

    def _create_serviceSpecification_item(self, url, serviceSpecification_item):
        # Override the needed headers to avoid spec hrefs to be created with internal host and port
        headers = {"Host": urlparse(settings.SITE).netloc}

        r = requests.post(url, headers=headers, json=serviceSpecification_item)
        r.raise_for_status()

        return r.json()
    
    def create_service_specification(self, serviceSpecification):
        """
        Creates a new serviceSpecification in the serviceSpecification API
        :param serviceSpecification: serviceSpecification document to be created
        :return:the created serviceSpecification document
        """
        path = "serviceSpecification"
        url = urljoin(self._serviceSpecification_api, path)

        return self._create_serviceSpecification_item(url, serviceSpecification)

    def delete_service_specification(self, spec_id):
        """
        Deletes a serviceSpecification from the serviceSpecification API
        :param spec_id: id of the serviceSpecification to be deleted
        """
        path = "serviceSpecification/" + spec_id
        url = urljoin(self._serviceSpecification_api, path)

        r = requests.delete(url)
        r.raise_for_status()

    def get_service_specification(self, serviceSpecification_name=None):
        """
        Retrieves the serviceSpecification made by a customer filtered by service and status
        :param customer: username of the customer
        :param state: state of the serviceSpecification to be retrieved
        :return: List of customer serviceSpecifications
        """
        #A ver se non me equivoco o relatedParty non debería de facer falta
        #en principio os plugins son os que hai, antes non se filtraba
        #consigues todos os plugins e chamas directamente pa rexistralos
        #tampouco debería facer falta o state

        # Get customer serviceSpecification filtered by state
        path = "serviceSpecification/"
        url = urljoin(self._serviceSpecification_api, path) #+ "?relatedParty.id=" + customer

        if serviceSpecification_name is not None:
            url += "?name=" + str(serviceSpecification_name)

        r = requests.get(url, headers={"Accept": "application/json"})

        r.raise_for_status()

        raw_serviceSpecification = r.json()

        return r.json()


    def _patch_serviceSpecification(self, serviceSpecification_id, patch):
        path = "serviceSpecification/" + str(serviceSpecification_id)
        url = urljoin(self._serviceSpecification_api, path)

        r = requests.patch(url, json=patch)
        r.raise_for_status()

    def update_service_specification(self, serviceSpecification_id, state):
        """
        Updates the status of a given serviceSpecification
        :param serviceSpecification_id: serviceSpecification to be modified
        :param state: new status
        """
        self._patch_serviceSpecification(serviceSpecification_id, state)