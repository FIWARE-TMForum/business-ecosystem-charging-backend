# -*- coding: utf-8 -*-

# Copyright (c) 2017 CoNWeT Lab., Universidad Politécnica de Madrid
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


import json

from django.core.exceptions import PermissionDenied
from requests.exceptions import HTTPError

from wstore.asset_manager.resource_plugins.decorators import on_usage_refreshed
from wstore.charging_engine.accounting.sdr_manager import SDRManager
from wstore.charging_engine.accounting.usage_client import UsageClient
from wstore.ordering.inventory_client import InventoryClient
from wstore.store_commons.resource import Resource
from wstore.store_commons.utils.http import build_response, supported_request_mime_types


class ServiceRecordCollection(Resource):
    # This method is used to load SDR documents and
    # start the charging process
    @supported_request_mime_types(("application/json",))
    def create(self, request):
        try:
            # Extract SDR document from the HTTP request
            data = json.loads(request.body)
        except:
            # The usage document is not valid, so the state cannot be changed
            return build_response(request, 400, "The request does not contain a valid JSON object")

        # Validate usage information
        response = None
        sdr_manager = SDRManager()
        try:
            sdr_manager.validate_sdr(data)
        except PermissionDenied as e:
            response = build_response(request, 403, str(e))
        except ValueError as e:
            response = build_response(request, 422, str(e))
        except:
            response = build_response(
                request,
                500,
                "The SDR document could not be processed due to an unexpected error",
            )

        usage_client = UsageClient()
        if response is not None:
            # The usage document is not valid, change its state to Rejected
            usage_client.update_usage_state(data["id"], "rejected")
        else:
            # The usage document is valid, change its state to Guided
            usage_client.update_usage_state(data["id"], "guided")
            sdr_manager.update_usage()
            response = build_response(request, 200, "OK")

        # Update usage document state
        return response


class SDRRefreshCollection(Resource):
    @supported_request_mime_types(("application/json",))
    def create(self, request):
        try:
            data = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return build_response(request, 400, "The request does not contain a valid JSON object")

        if not isinstance(data, dict):
            return build_response(request, 400, "The request does not contain a valid JSON object")

        product_id = data.get("productId")
        if not isinstance(product_id, str) or not product_id.strip():
            return build_response(request, 422, "A non-empty productId is required")

        try:
            product = InventoryClient().get_product(product_id)
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return build_response(request, 404, "The specified product id is not valid")
            raise

        on_usage_refreshed(product)

        return build_response(request, 200, "Ok")
