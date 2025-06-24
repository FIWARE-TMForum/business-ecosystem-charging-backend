# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid
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


from urllib.parse import urljoin
from logging import getLogger

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from wstore.store_commons.utils.url import get_service_url


logger = getLogger("wstore.default_logger")

class OrderingClient:
    def __init__(self):
        pass

    def create_ordering_subscription(self):
        """
        Create a subscription in the ordering API for being notified on product orders creation
        :return:
        """

        # Use the local site for registering the callback
        site = settings.LOCAL_SITE

        callback = {"callback": urljoin(site, "charging/api/orderManagement/orders")}

        url = get_service_url("ordering", "/productOrdering/v2/hub")
        r = requests.post(url, callback)

        if r.status_code != 200 and r.status_code != 409:
            msg = "It hasn't been possible to create ordering subscription, "
            msg += "please check that the ordering API is correctly configured "
            msg += "and that the ordering API is up and running"
            raise ImproperlyConfigured(msg)

    def get_order(self, order_id):
        path = "/productOrder/" + str(order_id)

        url = get_service_url("ordering", path)
        r = requests.get(url)
        r.raise_for_status()

        return r.json()

    def update_state(self, order, state):
        """
        Change the state of a given order including without changing the state of the items
        :param order: Order object as returned by the ordering API
        :param state: New state
        :return:
        """

        # Build patch body
        patch = {
            "state": state,
        }

        # Make PATCH request
        path = "/productOrder/" + str(order["id"])

        url = get_service_url("ordering", path)
        # Get the order first to avoid losing the order items

        try:
            resp1 = requests.get(url)
            resp1.raise_for_status()
            prev_order = resp1.json()

            patch["productOrderItem"] = prev_order["productOrderItem"]

            response = requests.patch(url, json=patch)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error Updating order state: " + str(e))
            raise

    def update_items_state(self, order, state, items=None):
        """
        Change the state of a given order including its order items
        :param order: Order object as returned by the ordering API
        :param items: list of order items to be updated
        :param state: New state
        :return:
        """

        # Build patch body
        patch = {
            "productOrderItem": [],
        }

        if items is None:
            items = order["productOrderItem"]

        for orderItem in order["productOrderItem"]:
            for item in items:
                if orderItem["id"] == item["id"]:
                    orderItem["state"] = state

            patch["productOrderItem"].append(orderItem)

        # Make PATCH request
        path = "/productOrder/" + str(order["id"])

        url = get_service_url("ordering", path)
        try:
            response = requests.patch(url, json=patch)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error Updating order items: " + str(e))
            raise

    def update_all_states(self, order, state):
        self.update_items_state(order, state)
        self.update_state(order, state)
