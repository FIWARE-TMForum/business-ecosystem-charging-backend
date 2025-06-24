# -*- coding: utf-8 -*-

# Copyright (c) 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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

import math
from logging import getLogger
from threading import Thread

import requests
from django.conf import settings
from requests.exceptions import HTTPError

from wstore.admin.users.notification_handler import NotificationsHandler
from wstore.models import Context, Resource
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import Offering, Order
from wstore.store_commons.database import DocumentLock
from wstore.store_commons.utils.url import get_service_url

logger = getLogger("wstore.default_logger")
PAGE_LEN = 100.0


class InventoryUpgrader(Thread):
    def __init__(self, asset):
        super().__init__()
        self._asset = asset
        self._client = InventoryClient()

        # Get product name
        try:
            prod_path = "/api/catalogManagement/v2/productSpecification/{}?fields=name".format(
                self._asset.product_id
            )

            prod_url = get_service_url("catalog", prod_path)
            resp = requests.get(prod_url)
            resp.raise_for_status()

            self._product_name = resp.json()["name"]
        except HTTPError:
            self._product_name = None

    def _save_failed(self, pending_off, pending_products):
        # The failed upgrades list may be upgraded by other threads or other server instances
        # In this case context must be accessed as a shared resource
        context_id = Context.objects.all()[0].pk

        lock = DocumentLock("wstore_context", context_id, "ctx")
        lock.wait_document()

        # At this point only the current thread can modify the list of pending upgrades
        context = Context.objects.all()[0]
        context.failed_upgrades.append(
            {
                "asset_id": self._asset.pk,
                "pending_offerings": pending_off,
                "pending_products": pending_products,
            }
        )
        context.save()

        lock.unlock_document()

    def _notify_user(self, patched_product):
        if self._product_name is not None:
            try:
                not_handler = NotificationsHandler()
                order = Order.objects.get(order_id=patched_product["name"].split("=")[-1])

                not_handler.send_product_upgraded_notification(
                    order,
                    order.get_product_contract(str(patched_product["id"])),
                    self._product_name,
                )

            except:
                # A failure in the email notification is not relevant
                pass

    def upgrade_products(self, product_ids, id_filter):
        def is_digital_char(characteristic):
            # Return whether a characteristics is defining asset info for the given one
            def is_product(id_):
                sp = id_.split(":")
                return len(sp) == 2 and sp[0] == "product" and sp[1] == self._asset.product_id

            def is_offering(id_):
                sp = id_.split(":")
                offerings = []

                if len(sp) == 2 and sp[0] == "offering":
                    offerings = Offering.objects.filter(off_id=sp[1])

                return len(offerings) == 1 and (
                    offerings[0].asset == self._asset or self._asset.pk in offerings[0].asset.bundled_assets
                )

            dig_char = False
            id_str = ""

            name = characteristic["name"].lower()

            if name.endswith("asset type") or name.endswith("media type") or name.endswith("location"):
                # There are several formats for asset characteristics within the inventory products depending on
                # the number and the structure of the involved bundles
                # name: Asset Type  , For single offering with single product
                # name: offering:123 Asset Type   , For bundle offering with single product
                # name: product:123 Asset Type    , For single offering with bundle product
                # name: offering:123 product:345 Asset Type  , For bundle offering with bundle product

                id_str = name.replace("asset type", "").replace("media type", "").replace("location", "")
                bundle_ids = id_str.split(" ")

                dig_char = (
                    len(bundle_ids) == 1
                    or (len(bundle_ids) == 2 and (is_product(bundle_ids[0]) or is_offering(bundle_ids[0])))
                    or (len(bundle_ids) == 3 and is_offering(bundle_ids[0]) and is_product(bundle_ids[1]))
                )

            return dig_char, id_str

        n_pages = int(math.ceil(len(product_ids) / PAGE_LEN))

        missing_upgrades = []
        for page in range(0, n_pages):
            # Get the ids related to the current product page
            offset = page * int(PAGE_LEN)

            page_ids = [str(id_filter(p_id)) for p_id in product_ids[offset : offset + int(PAGE_LEN)]]
            ids = ",".join(page_ids)

            # Get product characteristics field
            try:
                products = self._client.get_products(query={"id": ids, "fields": "id,productCharacteristic"})
            except HTTPError:
                missing_upgrades.extend(page_ids)
                continue

            # Patch product to include new asset information
            for product in products:
                pre_ids = ""
                product_id = str(product["id"])

                new_characteristics = []
                for char in product["productCharacteristic"]:
                    is_dig, ids_str = is_digital_char(char)
                    if not is_dig:
                        new_characteristics.append(char)
                    else:
                        pre_ids = ids_str

                new_characteristics.append(
                    {
                        "name": "{}Media Type".format(pre_ids),
                        "value": self._asset.content_type,
                    }
                )

                new_characteristics.append(
                    {
                        "name": "{}Asset Type".format(pre_ids),
                        "value": self._asset.resource_type,
                    }
                )

                new_characteristics.append(
                    {
                        "name": "{}Location".format(pre_ids),
                        "value": self._asset.download_link,
                    }
                )

                try:
                    # The inventory API returns the product after patching
                    patched_product = self._client.patch_product(
                        product_id, {"productCharacteristic": new_characteristics}
                    )
                except HTTPError:
                    missing_upgrades.append(product_id)
                    continue

                self._notify_user(patched_product)

        return missing_upgrades

    def upgrade_asset_products(self, offering_ids):
        # Get all the product ids related to the given product offering
        missing_off = []
        missing_products = []
        for off_id in offering_ids:
            try:
                product_ids = self._client.get_products(query={"productOffering.id": off_id, "fields": "id"})
            except HTTPError:
                # Failure reading the available product ids, all upgrades pending
                missing_off.append(off_id)
                continue

            missing_products.extend(self.upgrade_products(product_ids, lambda p_id: p_id["id"]))

        return missing_off, missing_products

    def _get_providing_offerings(self):
        # Get product bundles that contain the included asset
        assets = [self._asset]
        assets.extend(Resource.objects.filter(bundled_assets=self._asset.pk))

        # Get all the offerings that include the asset or one of the bundles
        offerings = []
        for asset in assets:
            offerings.extend(Offering.objects.filter(asset=asset))

        # Get all the offering bundles which include the previous offerings
        bundles = []
        for off in offerings:
            bundles.extend(Offering.objects.filter(bundled_offerings=off.pk))

        offerings.extend(bundles)
        return offerings

    def run(self):
        # Get all the offerings that give access to the provided digital asset
        offerings = self._get_providing_offerings()

        # Upgrade all the products related to the provided asset
        missing_off, missing_products = self.upgrade_asset_products([offering.off_id for offering in offerings])

        if len(missing_off) > 0 or len(missing_products) > 0:
            self._save_failed(missing_off, missing_products)
