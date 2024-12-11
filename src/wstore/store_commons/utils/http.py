# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 - Future Internet Consulting and Development Solutions S.L.

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

import json
from logging import getLogger

from django.conf import settings
from django.http import HttpResponse

from wstore.store_commons.utils import mimeparser
from wstore.store_commons.utils.error_response import get_json_response, get_unicode_response, get_xml_response

logger = getLogger("wstore.default_logger")


class JsonResponse(HttpResponse):
    def __init__(self, status, content):
        super(JsonResponse, self).__init__(
            content=json.dumps(content),
            content_type="application/json; charset=utf-8",
            status=status,
        )


FORMATTERS = {
    "application/json; charset=utf-8": get_json_response,
    "application/xml; charset=utf-8": get_xml_response,
    "text/plain; charset=utf-8": get_unicode_response,
}


def build_response(request, status_code, msg, extra_formats=None, headers=None, extra_content = None):
    logger.debug(f"Building response for {request.method} {request.path}")
    if extra_formats is not None:
        formatters = extra_formats.copy()
        formatters.update(FORMATTERS)
    else:
        formatters = FORMATTERS

    if request.META.get("HTTP_X_REQUESTED_WITH", "") == "XMLHttpRequest":
        mimetype = "application/json; charset=utf-8"
    else:
        mimetype = mimeparser.best_match(formatters.keys(), request.META.get("HTTP_ACCEPT", "text/plain"))

    response = HttpResponse(
        formatters[mimetype](request, mimetype, status_code, msg, extra_content),
        content_type=mimetype,
        status=status_code,
    )
    if headers is None:
        headers = {}

    for header_name in headers:
        response[header_name] = headers[header_name]

    print("salida")
    return response


def get_content_type(request):
    content_type_header = request.META.get("CONTENT_TYPE")
    if content_type_header is None:
        return "", ""
    else:
        return content_type_header.split(";", 1)


def authentication_required(func):
    def wrapper(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return build_response(
                request,
                401,
                "Authentication required",
                headers={
                    "WWW-Authenticate": 'Cookie realm="Acme" form-action="%s" cookie-name="%s"'
                    % (settings.LOGIN_URL, settings.SESSION_COOKIE_NAME)
                },
            )

        return func(self, request, *args, **kwargs)

    return wrapper


def supported_request_mime_types(mime_types):
    def wrap(func):
        def wrapper(self, request, *args, **kwargs):
            if get_content_type(request)[0] not in mime_types:
                msg = "Unsupported request media type"
                return build_response(request, 415, msg)

            return func(self, request, *args, **kwargs)

        return wrapper

    return wrap
