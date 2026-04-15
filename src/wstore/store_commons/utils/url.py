# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

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

from urllib.parse import quote, quote_plus, urlsplit, urlunsplit, urlparse, urlunparse

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.conf import settings

from wstore.store_commons.request_context import get_current_party_id


def is_valid_url(url):
    valid = True
    validator = URLValidator()
    try:
        validator(url)
    except ValidationError:
        valid = False

    return valid


def url_fix(s):
    scheme, netloc, path, qs, anchor = urlsplit(s)

    path = quote(path, "/%")
    qs = quote_plus(qs, ":&=")

    return urlunsplit((scheme, netloc, path, qs, anchor))


def add_slash(url):
    if url[-1] != "/":
        url += "/"

    return url


def _get_tmf_api_url(api):
    tmf_apis = {
        "catalog": settings.CATALOG,
        "party": settings.PARTY,
        "resource_catalog": settings.RESOURCE_CATALOG,
        "service_catalog": settings.SERVICE_CATALOG,
        "inventory": settings.INVENTORY,
        "resource_inventory": settings.RESOURCE_INVENTORY,
        "service_inventory": settings.SERVICE_INVENTORY,
        "ordering": settings.ORDERING,
        "account": settings.ACCOUNT,
        "billing": settings.BILLING,
        "usage": settings.USAGE,
    }

    api_url = tmf_apis.get(api, None)
    if api_url is None:
        raise ValueError(f"Invalid API name: {api}")

    return api_url


def _build_service_url(api_url, path):
    parsed_url = urlparse(api_url)
    api_path = parsed_url.path.rstrip("/")

    return f"{parsed_url.scheme}://{parsed_url.netloc}{api_path}/{path.lstrip('/')}"


def _get_party_tmforum_endpoint(party_id):
    from wstore.store_commons.utils.party import PartyClient

    party = PartyClient().get_local_party(party_id)
    if not isinstance(party, dict):
        return None

    for characteristic in party.get("partyCharacteristic", []):
        if characteristic.get("name").lower() != "tmforumendpoint":
            continue

        value = characteristic.get("value")
        if isinstance(value, str) and is_valid_url(value):
            return value

    return None


def _get_federated_api_url(api_url):
    if not settings.FEDERATION_ENABLED:
        return api_url

    party_id = get_current_party_id()
    if not party_id:
        return api_url

    endpoint = _get_party_tmforum_endpoint(party_id)
    if endpoint is None:
        return api_url

    parsed_api_url = urlparse(api_url)
    parsed_endpoint = urlparse(endpoint)

    return urlunparse(
        (
            parsed_endpoint.scheme,
            parsed_endpoint.netloc,
            parsed_api_url.path,
            parsed_api_url.params,
            parsed_api_url.query,
            parsed_api_url.fragment,
        )
    )


def get_service_url(api, path):
    api_url = _get_tmf_api_url(api)
    api_url = _get_federated_api_url(api_url)
    return _build_service_url(api_url, path)


def get_local_service_url(api, path):
    api_url = _get_tmf_api_url(api)
    return _build_service_url(api_url, path)
