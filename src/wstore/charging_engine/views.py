# -*- coding: utf-8 -*-

# Copyright (c) 2013 CoNWeT Lab., Universidad Politécnica de Madrid
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

import json

from copy import deepcopy
from logging import getLogger
from requests.exceptions import HTTPError

from bson import ObjectId

from django.http import HttpResponse

from wstore.asset_manager.resource_plugins.decorators import on_product_acquired
from wstore.rss.cdr_manager import CDRManager
from wstore.charging_engine.charging_engine import ChargingEngine
from wstore.charging_engine.payment_client.payment_client import PaymentClient, PaymentClientError
from wstore.ordering.errors import PaymentError, PaymentTimeoutError
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import Offering, Order
from wstore.ordering.ordering_client import OrderingClient
from wstore.ordering.ordering_management import OrderingManager
from wstore.store_commons.database import get_database_connection
from wstore.store_commons.resource import Resource
from wstore.store_commons.utils.http import authentication_required, build_response, supported_request_mime_types
from wstore.charging_engine.pricing_engine import PriceEngine

logger = getLogger("wstore.default_logger")


class PaymentConfirmation(Resource):
    def _set_initial_states(self, transactions, raw_order, order):
        def is_digital_contract(contract):
            # off = Offering.objects.get(pk=ObjectId(contract.offering))
            # return off.is_digital
            return True
            ### We are asuming all the offers are digitals

        # Set order items of digital products as completed
        involved_items = [t["item"] for t in transactions]

        digital_items = [
            item
            for item in raw_order["productOrderItem"]
            if item["id"] in involved_items and is_digital_contract(order.get_item_contract(item["id"]))
        ]

        # Oder Items state is not checked
        # self.ordering_client.update_items_state(raw_order, 'InProgress', digital_items)
        # self.ordering_client.update_items_state(raw_order, "completed", digital_items)

        # Notify order completed
        try:
            om = OrderingManager()
            om.notify_completed(raw_order)
        except:
            # The order is correct so we cannot set is as failed
            logger.error("The products for order {} could not be created".format(raw_order["id"]))

    def _set_renovation_states(self, transactions, raw_order, order):
        inventory_client = InventoryClient()

        for transaction in transactions:
            try:
                contract = order.get_item_contract(transaction["item"])
                inventory_client.activate_product(contract.product_id)

                # Activate the product
                on_product_acquired(order, contract)
            except:
                pass

    def _get_raw_order(self, order):
        raw_order = self.ordering_client.get_order(order.order_id)

        if raw_order is None:
            raise ValueError(f"No raw order found for order: {order.order_id}")

        return raw_order

    def _set_order_failed(self, order, raw_order):
        """Sets an order as failed when the payment acceptance process fails."""

        logger.info(f"Order {order.order_id} failed payment confirmation.")

        if order.pending_payment["concept"] == "initial":
            # Set the order to failed in the ordering API
            # Set all items as Failed, mark the whole order as failed
            self.ordering_client.update_items_state(raw_order, "failed")
            order.delete()
        else:
            order.state = "paid"
            order.pending_payment = None
            order.save()

    def _check_confirmation_request(self, request_data, payment_client):
        """Checks if the request data is valid an returns the action, the order reference and object.

        Args:
            request_data (dict): The parsed json data of the request
            payment_client (PaymentClient): A payment_client object instance
        """

        if "confirm_action" not in request_data or request_data["confirm_action"] not in ("accept", "cancel"):
            raise ValueError("No valid action provided.")

        if "reference" not in request_data or not all(
            param in request_data for param in payment_client.END_PAYMENT_PARAMS
        ):
            raise ValueError(
                f"Missing required field. It must contain {[*payment_client.END_PAYMENT_PARAMS, 'reference']} field(s)."
            )

        confirm_action = request_data["confirm_action"]
        reference = request_data["reference"]
        order = Order.objects.filter(pk=ObjectId(reference)).first()

        if not order:
            raise ValueError("The provided reference does not identify a valid order")

        logger.debug(f"Payment confirmation request for order {order.order_id} OK")
        return confirm_action, reference, order

    def _accept_confirmation_request(
        self, reference, order, raw_order, request_user, payment_client, payment_confirmation_data
    ):
        """Handler for 'accept' requests

        Args:
            reference (str): The order reference number.
            order (Order): The order object whose payment is confirmed.
            request_user: The request.user object.
            payment_client (PaymentClient): The PaymentClient object to use
            payment_confirmation_data (dict): The data passed by the payment client.
        """
        db = get_database_connection()

        # Uses an atomic operation to get and set the _lock value in the purchase
        # document
        pre_value = db.wstore_order.find_one_and_update({"_id": ObjectId(reference)}, {"$set": {"_lock": True}})

        # If the value of _lock before setting it to true was true, means
        # that the time out function has acquired it previously so the
        # view ends
        if not pre_value or "_lock" in pre_value and pre_value["_lock"]:
            raise PaymentTimeoutError("The timeout set to process the payment has finished")

        pending_info = order.pending_payment
        concept = pending_info["concept"]

        # If the order state value is different from pending means that
        # the timeout function has completely ended before acquiring the resource
        # so _lock is set to false and the view ends
        # if pre_value["state"] != "pending":
        #     db.wstore_order.find_one_and_update({"_id": ObjectId(reference)}, {"$set": {"_lock": False}})
        #     raise PaymentTimeoutError("The timeout set to process the payment has finished")

        # Check that the request user is authorized to end the payment
        if request_user.userprofile.current_organization != order.owner_organization or request_user != order.customer:
            raise PaymentError("You are not authorized to execute the payment")

        transactions = pending_info["transactions"]

        # build the payment client
        client = payment_client(order)
        order.sales_ids = client.end_redirection_payment(**payment_confirmation_data)
        order.save()

        charging_engine = ChargingEngine(order)
        charging_engine.end_charging(transactions, pending_info["free_contracts"], concept)

        # Change states of TMForum resources (orderItems, products, etc)
        # depending on the concept of the payment

        states_processors = {
            "initial": self._set_initial_states,
            "recurring": self._set_renovation_states,
            "usage": self._set_renovation_states,
        }
        # Include the free contracts as transactions in order to activate them
        ext_transactions = deepcopy(transactions)
        ext_transactions.extend([{"item": contract.item_id} for contract in pending_info["free_contracts"]])

        states_processors[concept](ext_transactions, raw_order, order)

        # _lock is set to false
        db.wstore_order.find_one_and_update({"_id": ObjectId(reference)}, {"$set": {"_lock": False}})

        logger.debug(f"Payment accepted for order {order.order_id}.")
        return 200, "Ok"

    def _cancel_confirmation_request(self, order, raw_order):
        """Handler for 'cancel' requests

        Args:
            order (Order): The order object whose payment is confirmed
        """
        # Set the order to failed in the ordering API
        # Set all items as Failed, mark the whole order as Failed
        # client.update_state(raw_order, 'Failed')
        self.ordering_client.update_items_state(raw_order, "failed")
        order.delete()

        logger.debug(f"Payment candelled for order {order.order_id}.")
        return 200, "Ok"

    # This method is used to receive the payment (Paypal, Stripe, ..) confirmation
    # when the customer is paying using his PayPal account
    # @supported_request_mime_types(("application/json",))
    # @authentication_required
    def create(self, request):
        order = None
        self.ordering_client = OrderingClient()
        try:
            # Extract payment information
            data = json.loads(request.body)

            payment_client = PaymentClient.get_payment_client_class()

            confirm_action, reference, order = self._check_confirmation_request(data, payment_client)
            raw_order = self.ordering_client.get_order(order.order_id)

            if confirm_action == "accept":
                response = self._accept_confirmation_request(
                    reference, order, raw_order, request.user, payment_client, data
                )
            else:
                response = self._cancel_confirmation_request(order, raw_order)

        # Error in request (check failed)
        except ValueError as e:
            response = 400, f"Invalid request: {str(e)}"
        # Error getting raw_order
        except HTTPError as e:
            response = 400, f"Invalid request: {str(e)}"
        except PaymentClientError as e:
            self._set_order_failed(order, raw_order)
            response = 503, f"Error with payment service provider: {str(e)}"
        # Error while accepting payment, timed out.
        except PaymentTimeoutError as e:
            # order and raw order are guaranteed to be defined here.
            self._set_order_failed(order, raw_order)
            response = 403, f"The payment has timed out: {str(e)}"
        # Error while accepting payment, usually no permissions.
        except PaymentError as e:
            # order and raw order are guaranteed to be defined here.
            self._set_order_failed(order, raw_order)
            response = 403, f"The payment has been canceled: {str(e)}"
        # Server error, catches everything.
        except Exception:
            # order and raw order are guaranteed to be defined here.
            self._set_order_failed(order, raw_order)
            response = 500, "The payment has been canceled due to an unexpected error."

        return build_response(request, *response)


class PaymentRefund(Resource):
    # This method is used when the user cancel a charge
    # when is using a PayPal account
    @supported_request_mime_types(("application/json",))
    @authentication_required
    def create(self, request):
        # In case the user cancels the payment is necessary to update
        # the database in order to avoid an inconsistent state
        try:
            data = json.loads(request.body)
            order = Order.objects.get(order_id=data["orderId"])

            payment_client = PaymentClient.get_payment_client_class()

            # build the payment client
            client = payment_client(order)

            for sale in order.sales_ids:
                client.refund(sale)

            # Only those orders with all its order items in ack state can be refunded
            # that means that all the contracts have been refunded
            for contract in order.get_contracts():
                if len(contract.charges) > 0:
                    cdr_manager = CDRManager(order, contract)
                    charge = contract.charges[-1]

                    # Create a refund CDR for each contract
                    cdr_manager.refund_cdrs(
                        charge["cost"],
                        charge["duty_free"],
                        charge["date"].isoformat() + "Z",
                    )

            order.delete()
        except:
            return build_response(request, 400, "Sales cannot be refunded")

        return build_response(request, 200, "Ok")


class PaymentPreview(Resource):

    @supported_request_mime_types(("application/json",))
    #@authentication_required
    def create(self, request):
        response = {
            "orderTotalPrice": []
        }

        try:
            data = json.loads(request.body)

            order = data
            usage = []
            if "productOrder" in data:
                order = data["productOrder"]

            if "usage" in data:
                usage = data["usage"]

            price_engine = PriceEngine()
            response = {
                "orderTotalPrice": price_engine.calculate_prices(order, usage=usage)
            }
        except:
            return build_response(request, 400, "Invalid order format")

        # Check if a discount needs to be applied
        return HttpResponse(
            json.dumps(response),
            content_type="application/json; charset=utf-8",
            status=200,
        )
