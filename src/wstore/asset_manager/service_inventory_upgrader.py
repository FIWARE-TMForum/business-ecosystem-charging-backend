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

from wstore.asset_manager.errors import ServiceError
from wstore.admin.users.notification_handler import NotificationsHandler
from wstore.models import Context, Resource
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import Offering, Order
from wstore.store_commons.database import DocumentLock

logger = getLogger("wstore.default_logger")
PAGE_LEN = 100.0


class ServiceInventoryUpgrader(Thread):
    def __init__(self, asset):
        super().__init__()
        self._asset = asset
        self._client = InventoryClient()

        # Get service name
        try:
            service_url = f"{settings.SERVICE_CATALOG}/serviceSpecification/{self._asset.service_spec_id}?fields=name"
            print(service_url)
            resp = requests.get(service_url)
            resp.raise_for_status()

            self._service_spec_name = resp.json()["name"]
        except HTTPError:
            self._service_spec_name = None

    def _save_failed(self, pending_services):
        # The failed upgrades list may be upgraded by other threads or other server instances
        # In this case context must be accessed as a shared resource
        context_id = Context.objects.all()[0].pk

        lock = DocumentLock("wstore_context", context_id, "ctx")
        lock.wait_document()
        print("save_failed")
        try:
            # At this point only the current thread can modify the list of pending upgrades
            context = Context.objects.all()[0]
            context.failed_upgrades.append(
                {
                    "asset_id": self._asset.pk,
                    "pending_services": pending_services,
                }
            )
            context.save()
        finally:
            lock.unlock_document()

    def _notify_user(self, patched_service):
        products = self._client.get_products(query={"realizingService.id": patched_service["id"], "fields": "id,name"})
        print(products)
        if self._service_spec_name is not None:
            for product in products:
                try:
                    notif_handler = NotificationsHandler()
                    print("get order")
                    order = Order.objects.get(order_id=product["name"].split("=")[-1])
                    print(order)
                    print("send product upgraded notification")
                    print(self._service_spec_name)
                    notif_handler.send_product_upgraded_notification(
                        order,
                        order.get_product_contract(str(product["id"])),
                        self._service_spec_name,
                    )
                    print("finish notif")

                except:
                    print("error notif")
                    # A failure in the email notification is not relevant
                    pass

    def upgrade_asset_services(self):
        
        missing_upgrades = []
        remain = True
        offset = 0
        while remain:
            # Get the ids related to the current service page
            # Get service characteristics field
            try:
                print("get_services")
                services = self._client.get_services(query={"serviceSpecification.id": self._asset.service_spec_id, "fields": "id,serviceCharacteristic,serviceSpecification", "limit": PAGE_LEN, 'offset' : offset})
                print("services:")
                print(services)
                if len(services) == 0:
                    break
                offset = offset + int(PAGE_LEN)
            except HTTPError as e:
                print("error getting services")
                # The api should not return error code 500
                if e.response.status_code == 500:
                    break
                page_ids = list(map(lambda p_id: p_id["id"], services))
                missing_upgrades.extend(page_ids)
                continue
            
            
            # Patch service for including new asset information
            for service in services:
                service_id = str(service["id"])

                new_characteristics = []
                # updating all characteristic
                for char in service["serviceCharacteristic"]:
                    charName = char["name"].lower()
                    if charName == "asset type":
                        char["value"] = self._asset.resource_type
                    elif charName == "media type":
                        char["value"] = self._asset.content_type
                    elif charName == "location":
                        char["value"] = self._asset.download_link
                    new_characteristics.append(char)
                        
                service["serviceSpecification"]["version"]= self._asset.version
                print("new char")
                print(new_characteristics)
                try:
                    # The inventory API returns the service after patching
                    print("patching service")
                    patched_service = self._client.patch_service(
                        service_id, {"serviceCharacteristic": new_characteristics, "serviceSpecification": service["serviceSpecification"]}
                    )
                    print("patched")
                    print(patched_service)
                except HTTPError:
                    print("error patching services")
                    missing_upgrades.append(service_id)
                    continue

                print("notify")
                self._notify_user(patched_service)
        print("final upgrade services")
        return missing_upgrades

    def run(self):
        # Upgrade all the services related to the provided asset
        print("upgrade_asset_services")
        missing_services = self.upgrade_asset_services()
        print("check missing offerings")
        if len(missing_services) > 0:
            self._save_failed(missing_services)
