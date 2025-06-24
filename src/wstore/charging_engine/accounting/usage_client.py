# -*- coding: utf-8 -*-

# Copyright (c) 2016 CoNWeT Lab., Universidad Politécnica de Madrid

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

from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

from wstore.charging_engine.accounting.errors import UsageError
from wstore.store_commons.utils.url import get_service_url


class UsageClient:
    def __init__(self):
        pass

    def _validate_state(self, state):
        valid_states = ["guided", "rated", "rejected", "billed"]

        if state not in valid_states:
            raise UsageError("Invalid usage status " + state)

    def _belongs_to_product(self, usage, product_id):
        belongs = False
        for char in usage["usageCharacteristic"]:
            if char["name"].lower() == "productid" and char["value"] == product_id:
                belongs = True
                break

        return belongs

    def _create_usage_item(self, url, usage_item):
        # Override the needed headers to avoid spec hrefs to be created with internal host and port
        headers = {"Host": urlparse(settings.SITE).netloc}

        r = requests.post(url, headers=headers, json=usage_item)
        r.raise_for_status()

        return r.json()

    def create_usage_spec(self, usage_spec):
        """
        Creates a new usage specification in the usage API
        :param usage_spec: usage specification to be created
        :return: the created usage specification
        """
        path = "usageSpecification/"
        url = get_service_url("usage", path)

        return self._create_usage_item(url, usage_spec)

    def create_usage(self, usage):
        """
        Creates a new usage document in the usage API
        :param usage: usage document to be created
        :return:the created usage document
        """

        path = "usage/"
        url = get_service_url("usage", path)

        return self._create_usage_item(url, usage)

    def delete_usage_spec(self, spec_id):
        """
        Deletes a usage specification from the usage API
        :param spec_id: id of the usage specification to be deleted
        """
        path = "usageSpecification/" + spec_id
        url = get_service_url("usage", path)

        r = requests.delete(url)
        r.raise_for_status()

    def get_customer_usage(self, customer, product_id, state=None):
        """
        Retrieves the usage made by a customer filtered by service and status
        :param customer: username of the customer
        :param product_id: id of the acquired product being used
        :param state: state of the usage to be retrieved
        :return: List of customer usages
        """
        # Get customer usage filtered by state
        path = "usage"
        url = get_service_url("usage", f"{path}?relatedParty.id={customer}")

        if state is not None:
            self._validate_state(state)
            url += "&status=" + state

        r = requests.get(url, headers={"Accept": "application/json"})

        r.raise_for_status()

        raw_usage = r.json()
        # Filter only the usage belonging to the specified product
        return [usage_doc for usage_doc in raw_usage if self._belongs_to_product(usage_doc, product_id)]

    def _patch_usage(self, usage_id, patch):
        path = "usage/" + str(usage_id)
        url = get_service_url("usage", path)

        r = requests.patch(url, json=patch)
        r.raise_for_status()

    def update_usage_state(self, usage_id, state):
        """
        Updates the status of a given usage
        :param usage_id: usage to be modified
        :param state: new status
        """
        self._validate_state(state)

        # Update document state
        patch = {"status": state}
        self._patch_usage(usage_id, patch)

    def rate_usage(self, usage_id, timestamp, duty_free, price, rate, currency, product_id):
        """
        Rates a product with the amount to be charge to the customer based on the given usage
        :param usage_id: usage where the rate is going to be included
        :param timestamp: Timestamp when the used was rated
        :param duty_free: rate value without taxes
        :param price: rate value with taxes
        :param rate: applied tax rate
        :param currency: currency of the amount
        :param product_id: Id of the product that generates the usage
        :return:
        """
        product_url = get_service_url("inventory", f"api/productInventory/v2/product/{str(product_id)}")
        
        patch = {
            "status": "rated",
            "ratedProductUsage": [
                {
                    "ratingDate": timestamp.replace(" ", "T"),
                    "usageRatingTag": "usage",
                    "isBilled": False,
                    "ratingAmountType": "Total",
                    "taxIncludedRatingAmount": price,
                    "taxExcludedRatingAmount": duty_free,
                    "taxRate": rate,
                    "isTaxExempt": False,
                    "offerTariffType": "Normal",
                    "currencyCode": currency,
                    "productRef": product_url,
                }
            ],
        }

        self._patch_usage(usage_id, patch)
