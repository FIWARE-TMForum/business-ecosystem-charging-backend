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
from datetime import datetime, timezone

from django.conf import settings
from logging import getLogger
from wstore.charging_engine.pricing_engine import PriceEngine

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

    def normalize_charges(self, acbrs: list, product_price_refs):
        logger.info(f"normalize product price refs: {product_price_refs}")
        for price_ref in product_price_refs:
            pop_id = price_ref["productOfferingPrice"]["id"]
            logger.info(f"pop_id: {pop_id}")
            pop = PriceEngine().download_pricing(pop_id)
            logger.debug(pop)
            rate_type = pop.get("priceType", "").lower()
            if rate_type in ["usage", "recurring"]:
                acbrs.append({
                    "appliedBillingRateType": rate_type
                })


    def execute_billing(self, item, raw_order):
        inventory = InventoryClient()
        start_date = datetime.now(timezone.utc).isoformat()

        product = inventory.build_product_model(
                    item, raw_order["id"], raw_order["billingAccount"], start_date)

        logger.info("Calling the billing engine with " + json.dumps(product))

        # Use the dome billing engine to resolve the charging
        url = settings.DOME_BILLING_URL + "/billing/instantBill"

        logger.debug({"product": product, "date": start_date})
        resp = requests.post(url, json={"product": product, "date": start_date})
        resp.raise_for_status()
        instant = resp.json()
        acbrs = instant[0]["acbrs"]
        self.normalize_charges(acbrs, product["productPrice"])

        return acbrs, instant[0]["customerBill"], product
