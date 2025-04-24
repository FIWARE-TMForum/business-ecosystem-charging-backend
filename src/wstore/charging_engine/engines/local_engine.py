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

from logging import getLogger
from decimal import Decimal

from wstore.charging_engine.engines.engine import Engine
from wstore.charging_engine.pricing_engine import PriceEngine


logger = getLogger("wstore.default_logger")

class LocalEngine(Engine):

    def __init__(self, order):
        super().__init__(order)
        self._price_engine = PriceEngine()

    def end_charging(self, transactions, free_contracts, concept):
        # set the order as paid
        # Update renovation dates
        # Update applied customer billing rates
        pass

    def _build_charges(self, item, billing_account):
        prices = self._price_engine.calculate_prices({
            "productOrderItem": [item]
        })

        # Only prices to be paid now are considered
        rates = []
        for price in prices:
            if price["priceType"].lower() == "one time" or price["priceType"].lower() == "recurring-prepaid":
                currency = price["price"]["dutyFreeAmount"]["unit"]
                inc = Decimal(price["price"]["taxIncludedAmount"]["value"])
                excl = Decimal(price["price"]["dutyFreeAmount"]["value"])
                rate_type = "One time" if price["priceType"].lower() == "one time" else "Recurring"

                tax = str(inc - excl)
                rates.append({
                    "appliedBillingRateType": rate_type,
                    "isBilled": False,
                    "appliedTax": [
                        {
                            "taxCategory": 'VAT',
                            "taxRate": price["price"]["taxRate"],
                            "taxAmount": {
                                "unit": currency,
                                "value": tax
                            }
                        }
                    ],
                    "taxIncludedAmount": {
                        "unit": currency,
                        "value": price["price"]["taxIncludedAmount"]["value"]
                    },
                    "taxExcludedAmount": {
                        "unit": currency,
                        "value": price["price"]["dutyFreeAmount"]["value"]
                    },
                    "billingAccount": billing_account
                })

        return rates

    def execute_billing(self, item, raw_order):
        return self._build_charges(item, raw_order["billingAccount"])
