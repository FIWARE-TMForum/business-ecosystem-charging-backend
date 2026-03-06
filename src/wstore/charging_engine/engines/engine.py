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

import uuid
import requests
import json

from django.db.utils import DatabaseError
from django.conf import settings
from logging import getLogger

from wstore.charging_engine.payment_client.payment_client import PaymentClient
from wstore.charging_engine.charging.billing_client import BillingClient
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import Order

logger = getLogger("wstore.default_logger")

class Engine:
    def __init__(self, order: Order):
        self._order = order

    def _get_item(self, item_id, raw_order):
        items = [item for item in raw_order["productOrderItem"] if item["id"] == item_id]

        return items[0] if items else None

    def end_charging(self, transactions, free_contracts, concept):
        # set the order as paid
        # Update renovation dates
        # Update applied customer billing rates
        pass

    def execute_billing(self, item, raw_order):
        pass

    def process_initial_charging(self, raw_order, related_contract= None):
        try:
            # The billing engine processes the products one by one
            transactions = []
            billing_client = BillingClient()
            inventory_client = InventoryClient()
            contracts = self._order.contracts if related_contract is None else related_contract
            for contract in contracts:

                logger.debug(f"contract: {contract.product_id}")

                # TODO: In the future I will transform this _get_item that is O(n^2) to a hashmap o Dict in this case that is O(1) complexity
                item = self._get_item(contract.item_id, raw_order)

                product = inventory_client.build_product_model(item, raw_order["id"], raw_order["billingAccount"])
                # attributes that needs to be set after the payments
                contract.prd_after_paid = {"product_price": product.pop("productPrice", None), "product_characteristic": product.pop("productCharacteristic", None)}
                # TODO: reset product to created and before this method, terminate cb and acbrs (I think it is not needed based on what Stefania said in dc).
                new_product = inventory_client.create_product(product) if related_contract is None else inventory_client.get_product(contract.product_id)

                response = self.execute_billing(item, raw_order)
                if len(response) > 0:
                    logger.info("Received response " + json.dumps(response))

                    seller_id = None
                    curated_party = []

                    logger.info("setting curated party")
                    for party in item["product"]["relatedParty"]:
                        curated_party.append({
                            "id": party["id"],
                            "href": party["href"],
                            "role": party["role"],
                            "@referredType": "organization"
                        })

                        if party["role"].lower() == settings.PROVIDER_ROLE.lower():
                            seller_id = party["id"]

                    logger.info("creating acbrs")
                    # Create the Billing rates as not billed

                    #TODO: if related_contract exists, set another name in acbrs.
                    message = None if related_contract is None else "INITIAL MODIFICATION PAYMENT"
                    created_rates, recurring = billing_client.create_batch_customer_rates(response, curated_party, new_product, message)

                    # created_cb is {} if there is no billable rates
                    logger.info("creating customer bills")
                    created_cb = billing_client.create_customer_bill(created_rates, raw_order["billingAccount"], curated_party)
                    if "id" not in created_cb:
                        created_cb["id"] = str(uuid.uuid4())
                        created_cb["internal"] = True

                    contract.applied_rates = [ n_rate["id"] for n_rate in created_rates ]
                    contract.customer_bill = created_cb
                    contract.product_id = new_product["id"]

                    transactions.append({
                        "item": contract.item_id,
                        "provider": seller_id,
                        "billId": created_cb["id"],
                        "price": created_cb.get("taxIncludedAmount", 0),
                        "duty_free": created_cb.get("taxExcludedAmount", 0),
                        "description": '',
                        "currency": created_cb.get("unit", "EUR"),
                        "recurring": recurring, # related_model is not used apart from local_engine_v1 so we can replace it with recurring: Boolean
                    })


            if len(transactions) == 0:
                logger.info("No transactions to process")
                return None

            # Update the order with the new contracts
            pending_payment = {  # Payment model
                "transactions": transactions,
                "concept": 'initial',
                "free_contracts": [],
            }

            self._order.pending_payment = pending_payment
            self._order.hash_key = uuid.uuid4().hex.encode()
            self._order.used = False
            try:
                logger.debug(f"Saving order {self._order.order_id}")
                self._order.save()
                logger.debug(f"Order {self._order.order_id} saved successfully")
            except DatabaseError as e:
                logger.error(f"Error saving order {self._order.order_id}: {str(e)}")
                logger.exception("Database error details:")
                raise

            # Load payment client
            logger.debug("Loading payment client for {settings.PAYMENT_CLIENT}")
            payment_client = PaymentClient.get_payment_client_class()

            # build the payment client
            client = payment_client(self._order)

            # Call the payment gateway
            client.start_redirection_payment(transactions)

            # Return the redirect URL to process the payment
            logger.info("Billing processed")
            return client.get_checkout_url()

        except Exception as e:
            logger.error(f"Error in process_initial_charging: {type(e).__name__}: {str(e)}")
            logger.error(f"Order ID: {self._order.order_id if hasattr(self._order, 'order_id') else 'Unknown'}")
            logger.error(f"Raw order: {json.dumps(raw_order, indent=2) if raw_order else 'None'}")
            raise

    def resolve_charging(self, type_="initial", related_contracts=None, raw_order=None):

        # TODO: Process other types of charging, renewal, usage, etc.
        if type_ == "initial":
            return self.process_initial_charging(raw_order, related_contracts)
