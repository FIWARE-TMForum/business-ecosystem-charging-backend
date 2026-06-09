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

from django.conf import settings
from wstore.store_commons.utils.url import get_service_url
from wstore.store_commons.utils.party import get_operator_party_roles, normalize_party_ref


logger = getLogger("wstore.default_logger")

class BillingClient:
    def __init__(self):
        pass

    def get_billing_account(self, account_id):
        url = get_service_url("account", f"billingAccount/{account_id}")

        response = requests.get(url, verify=settings.VERIFY_REQUESTS)
        response.raise_for_status()

        return response.json()

    def update_customer_rate(self, rate_id, product_id):

        data = {
            "product": {
                "id": product_id,
                "href": product_id
            }
        }

        url = get_service_url("billing", f"appliedCustomerBillingRate/{rate_id}")

        try:
            response = requests.patch(url, json=data, verify=settings.VERIFY_REQUESTS)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error updating customer rate: " + str(e))
            raise

    def set_acbrs_cb(self, batch_acbr, customer_bill_id):

        data = {
            "isBilled": True,
            "bill": {
                "id": customer_bill_id,
                "href": customer_bill_id
            }
        }
        # TODO: rollback for acbrs in case an error appears or some way to make it transactional
        for acbr in batch_acbr:
            url = get_service_url("billing", f"appliedCustomerBillingRate/{acbr['id']}")
            try:
                response = requests.patch(url, json=data, verify=settings.VERIFY_REQUESTS)
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logger.error("Error updating customer rate: " + str(e))
                raise

    def create_customer_rate(self, name, description, rate_type, currency, tax_rate, tax, tax_included, tax_excluded, billing_account, product_id, coverage_period=None, party=[], message= None):
        raw_rate = Decimal(str(tax_rate))
        decimal_rate = raw_rate / Decimal("100") if raw_rate > Decimal("1") else raw_rate
        data = {
            # "appliedBillingRateType": rate_type,
            "name": f"INITIAL PAYMENT - {name}" if message is None else message,
            "description": description,
            "type": rate_type,
            "isBilled": False,
            "date": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "appliedTax": [{
                "taxCategory": "VAT",
                "taxRate": decimal_rate,
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
            "billingAccount": billing_account,
            "product": {
                "id": product_id,
                "href": product_id
            }
        }

        if coverage_period is not None:
            data["periodCoverage"] = coverage_period

        if party is not None:
            data["relatedParty"] = [normalize_party_ref(party_ref) for party_ref in party]
            data["relatedParty"].extend(get_operator_party_roles())
            data["@schemaLocation"] = settings.RELATED_PARTY_SCHEMA_LOCATION

        url = get_service_url("billing", "appliedCustomerBillingRate")

        try:
            response = requests.post(url, json=data, verify=settings.VERIFY_REQUESTS)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error creating customer rate: " + str(e))
            raise

        return response.json()

    def create_batch_customer_rates(self, acbr_models, party, product, message=None):
        created_rates = []
        recurring = False
        for acbr_model in acbr_models:
            rate_type = acbr_model.get("appliedBillingRateType") or acbr_model["type"] # error if rate["type"] is called and it doesn't exist

            if rate_type == "recurring-prepaid":
                recurring = True
            elif rate_type in ["recurring", "usage"]:
                recurring = True
                continue

            currency = acbr_model["taxIncludedAmount"]["unit"]
            tax_rate = acbr_model["appliedTax"][0]["taxRate"]
            tax = acbr_model["appliedTax"][0]["taxAmount"]["value"]
            tax_included = acbr_model["taxIncludedAmount"]["value"]
            tax_excluded = acbr_model["taxExcludedAmount"]["value"]
            billing_account = acbr_model["billingAccount"]

            coverage_period = acbr_model["periodCoverage"] if "periodCoverage" in acbr_model else None

            new_rate = self.create_customer_rate(
                acbr_model["name"], acbr_model["description"],
                rate_type, currency, tax_rate, tax, tax_included, tax_excluded,
                billing_account, product["id"], coverage_period=coverage_period, party=party, message= message)

            created_rates.append(new_rate)

        logger.info('--BATCH RATES-- %s, recurring payment %s', created_rates, recurring)

        return created_rates, recurring

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

    def create_customer_bill(self, created_acbrs, cb_model):
        if len(created_acbrs) == 0:
            return {}

        created_cb = self._create_cb_api(cb_model)
        self.set_acbrs_cb(created_acbrs, created_cb["id"])

        cb = {}
        cb["id"] = created_cb["id"]
        # Remove Decimal type
        cb["taxIncludedAmount"] = created_cb["taxIncludedAmount"]["value"]
        cb["taxExcludedAmount"] = created_cb["taxExcludedAmount"]["value"]
        cb["unit"] = cb_model["taxIncludedAmount"]["unit"]
        logger.info("---CUSTOMER BILL EXTRA DATA--- %s", cb)
        return cb

    def set_customer_bill(self, state, billId):
        logger.info("set_customer_bill")
        if state not in ["new", "sent", "partiallySettled", "settled"]:
            raise ValueError("invalid customer bill state")
        data = {
            "state": state,
        }
        url = get_service_url("billing", f"customerBill/{billId}")

        try:
            response = requests.patch(url, json=data, verify=settings.VERIFY_REQUESTS)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error patching customer bill: " + str(e) + " data:" + str(data))
            raise

    def _create_cb_api(self, cb_model):
        cb_model["state"] = "sent"
        url = get_service_url("billing", "customerBill")

        try:
            response = requests.post(url, json=cb_model, verify=settings.VERIFY_REQUESTS)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error("Error creating customer bill: " + str(e))
            raise
        logger.info("--CB_CREATION--- %s", response.json())
        return response.json()
