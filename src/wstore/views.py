# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2023 Future Internet Consulting and Development Solutions S.L.

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

import os

from django.conf import settings
from django.http import HttpResponse
from django.utils.encoding import smart_str
from django.views.static import serve
from requests.exceptions import RequestException

from wstore.models import Organization, Resource, ResourcePlugin
from wstore.ordering.errors import InventoryError
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import Order
from wstore.store_commons.resource import Resource as API_Resource
from wstore.store_commons.utils.http import build_response


class ServeMedia(API_Resource):
    def _get_asset(self, resource_path):
        assets = Resource.objects.filter(resource_path=resource_path)
        asset = None

        if not len(assets):
            # Get the name of the potential asset provider from the resource_path
            owner_name = resource_path.split("/")[-2]
            org = Organization.objects.get(name=owner_name)

            # Check if the resource path refers to an asset that is being upgraded
            # Get only those upgrading assets belonging to the same provider
            assets = Resource.objects.filter(state="upgrading", provider=org)

            for upgrading_asset in assets:
                if (
                    len(upgrading_asset.old_versions)
                    and upgrading_asset.old_versions[-1].resource_path == resource_path
                ):
                    asset = upgrading_asset
                    break
        else:
            asset = assets[0]

        if asset is None:
            raise Exception()

        return asset

    def _is_file_item(self, item, file_id, kind):
        characteristics = item.get(kind + "Characteristic", [])

        if not isinstance(characteristics, list):
            return False

        characteristics = [
            characteristic
            for characteristic in characteristics
            if isinstance(characteristic, dict) and isinstance(characteristic.get("name"), str)
        ]

        if not any(
            characteristic["name"].strip().lower() == "file" and characteristic.get("value") == file_id
            for characteristic in characteristics
        ):
            return False

        category_ids = [
            characteristic.get("value")
            for characteristic in characteristics
            if characteristic["name"].strip().lower() == kind + " type"
        ]

        if len(category_ids) != 1 or not isinstance(category_ids[0], str) or not category_ids[0].strip():
            return False

        return ResourcePlugin.objects.filter(category_id=category_ids[0], type=kind, requires_file=True).exists()

    def _has_file_purchase(self, organization, asset):
        party_id = organization.actor_id

        if not party_id:
            return False

        client = InventoryClient()
        file_id = str(asset.pk)

        for kind in ("service", "resource"):
            if self._has_inventory_file_purchase(client, party_id, file_id, kind):
                return True

        return False

    def _has_inventory_file_purchase(self, client, party_id, file_id, kind):
        items = getattr(client, "iter_" + kind + "s")(query={kind + "Characteristic.value": file_id})
        reference_field = "realizing" + kind.capitalize()

        for item in items:
            if not isinstance(item, dict) or not self._is_file_item(item, file_id, kind):
                continue

            item_id = item.get("id")

            if not isinstance(item_id, str) or not item_id:
                continue

            products = client.iter_products(
                query={
                    reference_field + ".id": item_id,
                    "relatedParty.id": party_id,
                    "status": "active",
                }
            )

            for product in products:
                if not isinstance(product, dict) or product.get("status") != "active":
                    continue

                if not any(
                    isinstance(reference, dict) and reference.get("id") == item_id
                    for reference in product.get(reference_field, [])
                ):
                    continue

                if any(
                    isinstance(party, dict)
                    and party.get("id") == party_id
                    and isinstance(party.get("role"), str)
                    and party["role"].lower() == settings.CUSTOMER_ROLE.lower()
                    for party in product.get("relatedParty", [])
                ):
                    return True

        return False

    def _validate_asset_permissions(self, user, path, name):
        try:
            resource_path = os.path.join(settings.MEDIA_DIR, path, name)
            asset = self._get_asset(resource_path)
        except:
            return 404, "The specified asset does not exists"

        if asset.is_public:
            return None, None

        if user.is_anonymous:
            return 401, "You must be authenticated to download the specified asset"

        organization = user.userprofile.current_organization

        if organization == asset.provider:
            return None, None

        try:
            if self._has_file_purchase(organization, asset):
                return None, None
        except (RequestException, InventoryError, ValueError):
            return 503, "Unable to verify download permissions"

        return 403, "You are not authorized to download the specified asset"

    def _validate_invoice_permissions(self, user, name):
        err_code, err_msg = None, None

        if user.is_anonymous:
            err_code, err_msg = (
                401,
                "You must provide credentials for downloading invoices",
            )
        else:
            try:
                order = Order.objects.get(pk=name[:24])
            except:
                err_code, err_msg = 404, "The specified invoice does not exists"

            if err_code is None and order.owner_organization != user.userprofile.current_organization:
                err_code, err_msg = (
                    403,
                    "You are not authorized to download the specified invoice",
                )

        return err_code, err_msg

    def read(self, request, path, name):
        # Protect the resources from not authorized downloads
        if path.startswith("assets"):
            err_code, err_msg = self._validate_asset_permissions(request.user, path, name)
        elif path.startswith("bills"):
            err_code, err_msg = self._validate_invoice_permissions(request.user, name)
        else:
            err_code, err_msg = 404, "Resource not found"

        local_path = os.path.join(path, name)
        if err_code is None and not os.path.isfile(os.path.join(settings.MEDIA_ROOT, local_path)):
            err_code, err_msg = 404, "Resource not found"

        if err_code is not None:
            response = build_response(request, err_code, err_msg)
        elif not getattr(settings, "USE_XSENDFILE", False):
            response = serve(request, local_path, document_root=settings.MEDIA_ROOT)
        else:
            response = HttpResponse()
            response["X-Sendfile"] = smart_str(local_path)

        return response
