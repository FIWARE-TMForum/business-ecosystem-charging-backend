# -*- coding: utf-8 -*-

# Copyright (c) 2024 Future Internet Consulting and Development Solutions S.L.

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

import requests
import json

from django.conf import settings
from logging import getLogger

from wstore.charging_engine.engines.engine import Engine
from wstore.ordering.inventory_client import InventoryClient


logger = getLogger("wstore.default_logger")


class DomeEngine(Engine):
    def __init__(self, order):
        super().__init__(order)

    def end_charging(self, transactions, free_contracts, concept):
        # set the order as paid
        # Update renovation dates
        # Update applied customer billing rates
        pass

    def _build_item(self, contract):
        return {
            "id": contract.item_id,
            "action": "add",
            "quantity": 1,
            "itemTotalPrice": [{
                "productOfferingPrice": contract.pricing_model
            }],
            "productOffering": {
                "id": contract.offering,
                "href": contract.offering
            },
            "product": {
                "productCharacteristic": contract.options
            }
        }

    def execute_billing(self, item, raw_order):
        inventory = InventoryClient()

        product = inventory.build_product_model(
                    item, raw_order["id"], raw_order["billingAccount"])

        logger.info("Calling the billing engine with " + json.dumps(product))

        # Use the dome billing engine to resolve the charging
        url = settings.DOME_BILLING_URL + "/billing/instantBill"

        resp = requests.post(url, json=product)
        resp.raise_for_status()

        return resp.json()
