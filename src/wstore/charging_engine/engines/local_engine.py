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
import datetime

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
        now = datetime.datetime.now(datetime.timezone.utc)
        now = now.replace(hour=0, minute=0, second=0, microsecond=0) # Rounded to ensure consistent periods over all the rates

        prices = self._price_engine.calculate_prices({
            "productOrderItem": [item],
            "billingAccount":{ "resolved": self._order.tax_address["country"]}
        }, preview=False)

        # Only prices to be paid now are considered
        rates = []
        for price in prices:
            if price["priceType"].lower() == "one time" or price["priceType"].lower() == "recurring-prepaid":

                currency = price["price"]["dutyFreeAmount"]["unit"]
                inc = Decimal(price["price"]["taxIncludedAmount"]["value"])
                excl = Decimal(price["price"]["dutyFreeAmount"]["value"])
                rate_type = price["priceType"].lower()

                tax = str(inc - excl)
                rates.append({
                    "name": price["name"],
                    "description": price.get("description", ""),
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
                    "billingAccount": billing_account,
                    "periodCoverage": self._build_period_coverage(price["recurringChargePeriod"], now)
                })
            elif price["priceType"].lower() == "recurring" or price["priceType"].lower() == "usage":
                rate_type = price["priceType"].lower()
                rates.append({
                    "appliedBillingRateType": rate_type
                })
        return rates


    def _build_period_coverage(self, chargePeriod, now):
        start_datetime = now.isoformat().replace('+00:00', 'Z')
        end_datetime = None

        logger.info("recurringChargePeriod: %s", chargePeriod)
        if chargePeriod == PriceEngine.PERIOD_ONETIME:
            pass
        elif chargePeriod == PriceEngine.PERIOD_MONTH or chargePeriod == "1 month":
            # usage period or 1 month
            end_time = now + datetime.timedelta(days=30)
            end_datetime = end_time.isoformat().replace('+00:00', 'Z')
        else:
            # Other periods such as "3 month", "1 week", etc.
            parts = chargePeriod.split()
            if len(parts) == 2:
                amount = int(parts[0])
                unit = parts[1].lower()

                if unit in ["month", "months"]:
                    end_time = now + datetime.timedelta(days=30 * amount)
                elif unit in ["week", "weeks"]:
                    end_time = now + datetime.timedelta(weeks=amount)
                elif unit in ["day", "days"]:
                    end_time = now + datetime.timedelta(days=amount)
                elif unit in ["year", "years"]:
                    end_time = now + datetime.timedelta(days=365 * amount)
                else:
                    raise ValueError("Invalid charge period")
                end_datetime = end_time.isoformat().replace('+00:00', 'Z')
            else:
                raise ValueError("Invalid charge period")

        result =  {
            "startDateTime": start_datetime
        }
        if end_datetime:
            result["endDateTime"] = end_datetime
        return result


    def execute_billing(self, item, raw_order):
        return self._build_charges(item, raw_order["billingAccount"])
