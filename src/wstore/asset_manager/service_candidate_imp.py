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


class ServiceCandidate:
    def __init__(self):
        self._serviceCandidate_api = settings.SERVICE
        if not self._serviceCandidate_api.endswith("/"):
            self._serviceCandidate_api += "/"

    def _create_serviceCandidate_item(self, url, serviceCandidate_item):
        # Override the needed headers to avoid spec hrefs to be created with internal host and port
        headers = {"Host": urlparse(settings.SITE).netloc}

        r = requests.post(url, headers=headers, json=serviceCandidate_item)
        r.raise_for_status()

        return r.json()
    
    def create_service_candidate(self, serviceCandidate):
        """
        Creates a new serviceCandidate in the serviceCandidate API
        :param serviceCandidate: serviceCandidate document to be created
        :return:the created serviceCandidate document
        """
        path = "serviceCandidate"
        url = urljoin(self._serviceCandidate_api, path)

        return self._create_serviceCandidate_item(url, serviceCandidate)

    def delete_service_candidate(self, spec_id):
        """
        Deletes a serviceCandidate from the serviceCandidate API
        :param spec_id: id of the serviceCandidate to be deleted
        """
        path = "serviceCandidate/" + spec_id
        url = urljoin(self._serviceCandidate_api, path)

        r = requests.delete(url)
        r.raise_for_status()

    def get_service_candidate(self, serviceCandidate_name=None):
        """
        Retrieves the serviceCandidate made by a customer filtered by service and status
        :param customer: username of the customer
        :param state: state of the serviceCandidate to be retrieved
        :return: List of customer serviceCandidates
        """
        #A ver se non me equivoco o relatedParty non debería de facer falta
        #en principio os plugins son os que hai, antes non se filtraba
        #consigues todos os plugins e chamas directamente pa rexistralos
        #tampouco debería facer falta o state

        # Get customer serviceCandidate filtered by state
        path = "serviceCandidate/"
        url = urljoin(self._serviceCandidate_api, path) #+ "?relatedParty.id=" + customer

        if serviceCandidate_name is not None:
            url += "?name=" + str(serviceCandidate_name)

        r = requests.get(url, headers={"Accept": "application/json"})

        r.raise_for_status()

        raw_serviceCandidate = r.json()

        return r.json()


    def _patch_serviceCandidate(self, serviceCandidate_id, patch):
        path = "serviceCandidate/" + str(serviceCandidate_id)
        url = urljoin(self._serviceCandidate_api, path)

        r = requests.patch(url, json=patch)
        r.raise_for_status()

    def update_service_candidate(self, serviceCandidate_id, state):
        """
        Updates the status of a given serviceCandidate
        :param serviceCandidate_id: serviceCandidate to be modified
        :param state: new status
        """
        self._patch_serviceCandidate(serviceCandidate_id, state)