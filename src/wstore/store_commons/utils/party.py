# -*- coding: utf-8 -*-

# Copyright (c) 2025 Future Internet Consulting and Development Solutions S.L.

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

from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache

from wstore.store_commons.utils.url import get_service_url

CACHE_KEY = "operator:party_id"
CACHE_TTL = 24 * 3600  # 1 day

PARTY_TTL = 2 * 3600  # 2 hours


class PartyClient:

    def _build_local_party_url(self, path):
        parsed_url = urlparse(settings.PARTY)
        api_path = parsed_url.path.rstrip("/")

        return f"{parsed_url.scheme}://{parsed_url.netloc}{api_path}/{path.lstrip('/')}"

    def _get_party_id(self, query):
        party_url = get_service_url("party", f"/organization{query}")
        response = requests.get(party_url)

        party_id = None
        if response.status_code == 200:
            data = response.json()

            if len(data) > 0:
                party_id = data[0]['id']

        return party_id

    def get_operator(self):
        # If no operator is defined, return None
        if settings.OPERATOR_ID is None:
            return None

        # Search by organizationIdentification
        did = settings.OPERATOR_ID
        if not settings.OPERATOR_ID.startswith('did'):
            did = f'did:elsi:{settings.OPERATOR_ID}'

        query = f"?organizationIdentification.identificationId={did}"
        party_id = self._get_party_id(query)

        if party_id is None:
            # Search by externalReference
            query = f"?externalReference.name={did}"
            party_id = self._get_party_id(query)

            # Just in case it is registered without did:elsi: prefix
            if party_id is None:
                query = f"?externalReference.name={settings.OPERATOR_ID}"
                party_id = self._get_party_id(query)

        return party_id

    def get_party_ext_id(self, party_id):
        party_url = get_service_url("party", f"/organization/{party_id}")

        response = requests.get(party_url)

        party_ext_id = None
        if response.status_code == 200:
            data = response.json()

            for ext_ref in data.get('externalReference', []):
                if ext_ref['externalReferenceType'] == 'idm_id':
                    party_ext_id = ext_ref['name']
                    break

        return party_ext_id

    def get_local_party(self, party_id):
        cache_key = f"party_obj:{party_id}"
        party = cache.get(cache_key)
        if party is not None:
            return party

        party_url = self._build_local_party_url(f"/organization/{party_id}")

        try:
            response = requests.get(party_url)
        except requests.RequestException:
            return None

        if response.status_code != 200:
            return None

        party = response.json()
        cache.set(cache_key, party, PARTY_TTL)
        return party


def get_operator_party_id():
    party_id = cache.get(CACHE_KEY)
    if party_id is None:
        client = PartyClient()
        party_id = client.get_operator()
        cache.set(CACHE_KEY, party_id, CACHE_TTL)
    return party_id


def get_operator_party_roles():
    related_parties = []
    party_id = get_operator_party_id()

    if party_id is not None:
        related_parties.extend([{
            "id": party_id,
            "href": party_id,
            "name": settings.OPERATOR_ID,
            "role": settings.SELLER_OPERATOR_ROLE,
            "@referredType": "Organization"
        }, {
            "id": party_id,
            "href": party_id,
            "name": settings.OPERATOR_ID,
            "role": settings.BUYER_OPERATOR_ROLE,
            "@referredType": "Organization"
        }])

    return related_parties


def normalize_party_ref(party_ref):
    party_id = party_ref["id"]

    cache_key = f"party_ext:{party_id}"
    party_ext_id = cache.get(cache_key)
    if party_ext_id is None:
        client = PartyClient()
        party_ext_id = client.get_party_ext_id(party_id)

        if party_ext_id is not None:
            cache.set(cache_key, party_ext_id, PARTY_TTL)

    referredType = "Organization" if "organization" in party_id.lower() else "Individual"

    href = party_id
    if "href" in party_ref:
        href = party_ref["href"]

    related_party = {
        "id": party_id,
        "href": href,
        "role": party_ref["role"],
        "@referredType": referredType
    }

    if party_ext_id is not None:
        related_party["name"] = party_ext_id

    return related_party
