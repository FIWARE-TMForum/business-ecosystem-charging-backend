# -*- coding: utf-8 -*-

# Copyright (c) 2016 CoNWeT Lab., Universidad Politécnica de Madrid
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


import requests
import datetime

from decimal import Decimal
from logging import getLogger
from urllib.parse import urljoin, urlparse

from django.conf import settings


logger = getLogger("wstore.default_logger")

class BillingClient:
    def __init__(self):
        self._billing_api = settings.BILLING
        if not self._billing_api.endswith("/"):
            self._billing_api += "/"

    def get_billing_account(self, account_id):
        account_api = settings.ACCOUNT
        if not account_api.endswith("/"):
            account_api += "/"

        url = '{}billingAccount/{}'.format(account_api, account_id)

        response = requests.get(url, verify=settings.VERIFY_REQUESTS)
        response.raise_for_status()

        return response.json()

    def create_customer_bill(self):
        # FIXME: This objects is being created with the minum information
        # We will need to add here the payment information and the invoice
        # numbers
        url = '{}customerBill'.format(self._billing_api)
        data = {
            "billDate": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        }

        try:
            response = requests.post(url, json=data, verify=settings.VERIFY_REQUESTS)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error creating customer bill: " + str(e))
            raise

        return response.json()["id"]

    def update_customer_rate(self, rate_id, product_id):
        # TODO: To be able to se the isBilled, the bill needs to be created
        bill_id = self.create_customer_bill()

        data = {
            "isBilled": True,
            "product": {
                "id": product_id,
                "href": product_id
            },
            "bill": {
                "id": bill_id,
                "href": bill_id
            }
        }

        url = '{}appliedCustomerBillingRate/{}'.format(self._billing_api, rate_id)

        try:
            response = requests.patch(url, json=data, verify=settings.VERIFY_REQUESTS)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error updating customer rate: " + str(e))
            raise

    def create_customer_rate(self, rate_type, currency, tax_rate, tax, tax_included, tax_excluded, billing_account, coverage_period=None, parties=None):
        # TODO: Billing address and dates
        data = {
            # "appliedBillingRateType": rate_type,
            "type": rate_type,
            "isBilled": False,
            "date": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "appliedTax": [{
                "taxCategory": "VAT",
                "taxRate": tax_rate,
                "taxAmount": {
                    "unit": currency,
                    "value": tax
                }
            }],
            "taxIncludedAmount": {
                "unit": currency,
                "value": tax_included
            },
            "taxExcludedAmount": {
                "unit": currency,
                "value": tax_excluded
            },
            "billingAccount": billing_account
        }

        if coverage_period is not None:
            data["periodCoverage"] = coverage_period

        if parties is not None:
            data["relatedParty"] = parties
            data["@schemaLocation"] = "https://raw.githubusercontent.com/DOME-Marketplace/dome-odrl-profile/refs/heads/add-related-party-ref/schemas/simplified/RelatedPartyRef.schema.json"

        url = '{}appliedCustomerBillingRate'.format(self._billing_api)

        try:
            response = requests.post(url, json=data, verify=settings.VERIFY_REQUESTS)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error creating customer rate: " + str(e))
            raise

        return response.json()

    def create_batch_customer_rates(self, rates, parties):
        created_rates = []
        for rate in rates:
            if "appliedBillingRateType" in rate:
                rate_type = rate["appliedBillingRateType"]
            else:
                rate_type = rate["type"]

            currency = rate["taxIncludedAmount"]["unit"]
            tax_rate = rate["appliedTax"][0]["taxRate"]
            tax = rate["appliedTax"][0]["taxAmount"]["value"]
            tax_included = rate["taxIncludedAmount"]["value"]
            tax_excluded = rate["taxExcludedAmount"]["value"]
            billing_account = rate["billingAccount"]

            coverage_period = rate["periodCoverage"] if "periodCoverage" in rate else None

            new_rate = self.create_customer_rate(
                rate_type, currency, tax_rate, tax, tax_included, tax_excluded,
                billing_account, coverage_period=coverage_period, parties=parties)

            created_rates.append(new_rate)

        return created_rates

    def create_charge(self, charge_model, product_id, start_date=None, end_date=None):
        # This Object is now part of the CustomerBillManagement API, not yet integrated
        pass
        # str_time = charge_model["date"].isoformat() + "Z"
        # tax_rate = (
        #     (Decimal(charge_model["cost"]) - Decimal(charge_model["duty_free"]))
        #     * Decimal("100")
        #     / Decimal(charge_model["cost"])
        # )

        # domain = settings.SITE
        # invoice_url = urljoin(domain, charge_model["invoice"])
        # description = (
        #     charge_model["concept"]
        #     + " charge of "
        #     + charge_model["cost"]
        #     + " "
        #     + charge_model["currency"]
        #     + " "
        #     + invoice_url
        # )

        # charge = {
        #     "date": str_time,
        #     "description": description,
        #     "type": charge_model["concept"],
        #     "currencyCode": charge_model["currency"],
        #     "taxIncludedAmount": charge_model["cost"],
        #     "taxExcludedAmount": charge_model["duty_free"],
        #     "appliedCustomerBillingTaxRate": [{"amount": str(tax_rate), "taxCategory": "VAT"}],
        #     "serviceId": [{"id": product_id, "type": "Inventory product"}],
        # }

        # if end_date is not None or start_date is not None:
        #     start_period = start_date.isoformat() + "Z" if start_date is not None else str_time
        #     end_period = end_date.isoformat() + "Z" if end_date is not None else str_time

        #     charge["period"] = [{"startPeriod": start_period, "endPeriod": end_period}]

        # url = self._billing_api + "api/billingManagement/v2/appliedCustomerBillingCharge"
        # req = Request("POST", url, json=charge)

        # session = Session()
        # prepped = session.prepare_request(req)

        # # Override host header to avoid inconsistent hrefs in the API
        # prepped.headers["Host"] = urlparse(domain).netloc

        # resp = session.send(prepped)
        # resp.raise_for_status()
