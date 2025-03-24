# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
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


import json

from bson.objectid import ObjectId
from django.http import HttpResponse
from logging import getLogger

from wstore.asset_manager.resource_plugins.decorators import (
    on_product_acquired,
    on_product_suspended,
    on_usage_refreshed,
)
from wstore.charging_engine.charging.billing_client import BillingClient
from wstore.charging_engine.charging_engine import ChargingEngine
from wstore.ordering.errors import OrderingError
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import Offering, Order
from wstore.ordering.ordering_client import OrderingClient
from wstore.ordering.ordering_management import OrderingManager
from wstore.store_commons.resource import Resource
from wstore.store_commons.utils.http import authentication_required, build_response, supported_request_mime_types

logger = getLogger("wstore.default_logger")


class OrderingCollection(Resource):
    @authentication_required
    @supported_request_mime_types(("application/json",))
    def create(self, request):
        """
        Receives notifications from the ordering API when a new order is created
        :param request:
        :return:
        """
        user = request.user
        try:
            order = json.loads(request.body)
        except:
            return build_response(request, 400, "The provided data is not a valid JSON object")

        client = OrderingClient()
        # we are not setting all the items as inProgress
        # client.update_items_state(order, "inProgress")

        terms_accepted = request.META.get("HTTP_X_TERMS_ACCEPTED", "").lower() == "true"

        logger.info("New product order received: {}".format(order["id"]))

        try:
            response = None
            om = OrderingManager()
            redirect_url = om.process_order(user, order, terms_accepted=terms_accepted)

            if redirect_url is not None:
                # logger.info("Order items set as pending: {}".format(order["id"]))
                # client.update_items_state(order, "pending")

                response = HttpResponse(
                    json.dumps({"redirectUrl": redirect_url}),
                    status=200,
                    content_type="application/json; charset=utf-8",
                )

            else:
                # Trigger the notification, the process will check the procurement mode
                try:
                    om.notify_completed(order)
                except:
                    # The order is correct so we cannot set is as failed
                    logger.error("The products for order {} could not be created".format(order["id"]))

                response = build_response(request, 200, "OK")

        except OrderingError as e:
            response = build_response(request, 400, str(e.value))
            client.update_all_states(order, "failed")
        except Exception as e:
            response = build_response(request, 500, "Your order could not be processed")
            client.update_all_states(order, "failed")

        return response


class NotifyOrderCollection(Resource):
    @authentication_required
    @supported_request_mime_types(("application/json",))
    def create(self, request, order_id):
        """
        This mthod is called when a product order is completed
        :param request:
        :return:
        """

        oc = OrderingClient()
        try:
            order = oc.get_order(order_id)
        except Exception as e:
            # The order is correct so we cannot set is as failed
            logger.error("The order {} could not be retrieved {}".format(order["id"], str(e.value)))
            return build_response(request, 400, 'Error accessing the product order')

        om = OrderingManager()
        try:
            om.process_order_completed(order)
        except Exception as e:
            # The order is correct so we cannot set is as failed
            logger.error("The products for order {} could not be created {}".format(order["id"], str(e.value)))
            return build_response(request, 400, 'Error creating product in the inventory')

        return build_response(request, 200, "OK")


class InventoryCollection(Resource):
    @supported_request_mime_types(("application/json",))
    def create(self, request):
        try:
            event = json.loads(request.body)
        except:
            return build_response(request, 400, "The provided data is not a valid JSON object")

        if event["eventType"] != "ProductCreationNotification":
            return build_response(request, 200, "OK")

        product = event["event"]["product"]

        # Extract order id
        order_id = product["name"].split("=")[1]

        om = OrderingManager()
        code, error = om.activate_product(order_id, product)

        if error is not None:
            return build_response(request, code, error)

        return build_response(request, 200, "OK")


def validate_product_job(self, request):
    try:
        task = json.loads(request.body)
    except:
        return (
            None,
            None,
            None,
            build_response(request, 400, "The provided data is not a valid JSON object"),
        )

    # Check the products to be renovated
    if "name" not in task or "id" not in task or "priceType" not in task:
        return (
            None,
            None,
            None,
            build_response(
                request,
                400,
                "Missing required field, must contain name, id  and priceType fields",
            ),
        )

    if task["priceType"].lower() not in ["recurring", "usage"]:
        return (
            None,
            None,
            None,
            build_response(
                request,
                400,
                "Invalid priceType only recurring and usage types can be renovated",
            ),
        )

    # Parse oid from product name
    parsed_name = task["name"].split("=")

    try:
        order = Order.objects.get(order_id=parsed_name[1])
    except:
        return (
            None,
            None,
            None,
            build_response(request, 404, "The oid specified in the product name is not valid"),
        )

    # Get contract to renovate
    if isinstance(task["id"], int):
        task["id"] = str(task["id"])

    try:
        contract = order.get_product_contract(task["id"])
    except:
        return (
            None,
            None,
            None,
            build_response(request, 404, "The specified product id is not valid"),
        )

    return task, order, contract, None


def process_product_payment(self, request, task, order, contract):
    # Refresh accounting information
    on_usage_refreshed(order, contract)

    # Build charging engine
    charging_engine = ChargingEngine(order)

    redirect_url = None
    try:
        redirect_url = charging_engine.resolve_charging(type_=task["priceType"].lower(), related_contracts=[contract])
    except ValueError as e:
        return None, build_response(request, 400, str(e))
    except OrderingError as e:
        # The error might be raised because renewing a suspended product not expired
        if str(e) == "OrderingError: There is not recurring payments to renovate" and contract.suspended:
            try:
                on_product_acquired(order, contract)

                # Change product state to active
                contract.suspended = False
                order.save()

                inventory_client = InventoryClient()
                inventory_client.activate_product(contract.product_id)
            except:
                return None, build_response(request, 400, "The asset has failed to be activated")

        else:
            return None, build_response(request, 422, str(e))
    except:
        return None, build_response(request, 500, "An unexpected event prevented your payment to be created")

    return redirect_url, None


class UnsubscriptionCollection(Resource):
    @authentication_required
    @supported_request_mime_types(("application/json",))
    def create(self, request):
        task, order, contract, error_response = validate_product_job(self, request)

        if error_response is not None:
            return error_response

        # If the model is pay-per-use charge for pending payment
        redirect_url = None
        if task["priceType"].lower() == "usage":
            # The update of the product status need to be postponed if there is a pending payment
            redirect_url, error_response = process_product_payment(self, request, task, order, contract)

            if error_response is not None:
                return error_response

        response = build_response(request, 200, "OK")

        # Include redirection header if needed
        if redirect_url is not None:
            response["X-Redirect-URL"] = redirect_url
        else:
            # Suspend the product as no pending payment
            on_product_suspended(order, contract)

            contract.suspended = True
            order.save()

            client = InventoryClient()
            client.suspend_product(contract.product_id)

        return response


class RenovationCollection(Resource):
    @authentication_required
    @supported_request_mime_types(("application/json",))
    def create(self, request):
        task, order, contract, error_response = validate_product_job(self, request)

        if error_response is not None:
            return error_response

        redirect_url, error_response = process_product_payment(self, request, task, order, contract)
        if error_response is not None:
            return error_response

        response = build_response(request, 200, "OK")

        # Include redirection header if needed
        if redirect_url is not None:
            response["X-Redirect-URL"] = redirect_url

        return response
