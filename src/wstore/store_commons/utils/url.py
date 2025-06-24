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

from urllib.parse import quote, quote_plus, urlsplit, urlunsplit, urlparse

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.conf import settings


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


def get_service_url(api, path):
    TMF_APIS = {
        "catalog": settings.CATALOG,
        "resource_catalog": settings.RESOURCE_CATALOG,
        "service_catalog": settings.SERVICE_CATALOG,
        "inventory": settings.INVENTORY,
        "resource_inventory": settings.RESOURCE_INVENTORY,
        "service_inventory": settings.SERVICE_INVENTORY,
        "ordering": settings.ORDERING,
        "account": settings.ACCOUNT,
        "billing": settings.BILLING,
        "usage": settings.USAGE
    }

    api_url = TMF_APIS.get(api, None)
    if api_url is None:
        raise ValueError(f"Invalid API name: {api}")

    parsed_url = urlparse(api_url)
    host = parsed_url.netloc
    api_path = parsed_url.path

    if api_path.endswith('/'):
        api_path = api_path.rstrip('/')

    return f"{parsed_url.scheme}://{host}{api_path}/{path.lstrip('/')}"
