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

import requests
from decimal import Decimal

from django.conf import settings

from wstore.store_commons.utils.url import get_service_url


class PriceEngine():
    def _download_pricing(self, pop_id):
        price_url = get_service_url("catalog", "/productOfferingPrice/{}".format(pop_id))
        request = requests.get(price_url, verify=settings.VERIFY_REQUESTS)
        pricing = request.json()
        return pricing

    def _process_price_component(self, component, options, aggregated):
        # Check if the component needs to be applied
        tail_value = None
        if "prodSpecCharValueUse" in component:
            conditions = {}

            for val in component["prodSpecCharValueUse"]:
                value = 'tailored'
                if "productSpecCharacteristicValue" in val and len(val["productSpecCharacteristicValue"]) > 0:
                    value = val["productSpecCharacteristicValue"][0]["value"]
                conditions[val["name"].lower()] = value

            found = 0
            for option in options:
                if option["name"].lower() in conditions:
                    if conditions[option["name"].lower()] == 'tailored':
                        found += 1
                        tail_value = Decimal(str(option["value"]))
                        continue

                    if str(conditions[option["name"].lower()]) == str(option["value"]):
                        found += 1
    
            if len(conditions) != found:
                # The component is not processed
                return

        if component["priceType"] not in aggregated:
            aggregated[component["priceType"]] = {}

        period_key = "onetime"
        if "recurringChargePeriodType" in component and "recurringChargePeriodLength" in component:
            period_key = "{} {}".format(component["recurringChargePeriodLength"], component["recurringChargePeriodType"])

        if period_key not in aggregated[component["priceType"]]:
            aggregated[component["priceType"]][period_key] = {
                "value": Decimal('0')
            }

        if tail_value is None:
            aggregated[component["priceType"]][period_key]["value"] += Decimal(str(component["price"]["value"]))
        else:
            tailored_price = Decimal(str(component["price"]["value"])) * tail_value
            aggregated[component["priceType"]][period_key]["value"] += tailored_price

    def calculate_prices(self, data):
        aggregated = {}

        item = data["productOrderItem"][0]
        # 1) Download the POP
        if "itemTotalPrice" not in item or len(item["itemTotalPrice"]) == 0:
            # The item has no price, it is free
            return []

        pop_id = item["itemTotalPrice"][0]["productOfferingPrice"]["id"]
            
        pricing = self._download_pricing(pop_id)

        # If the price is a bundle download the components
        to_process = []
        if pricing["isBundle"]:
            to_process = [self._download_pricing(pop["id"]) for pop in pricing["bundledPopRelationship"]]
        else:
            to_process = [pricing]

        options = []
        if "product" in item and "productCharacteristic" in item["product"]:
            options = item["product"]["productCharacteristic"]

        for component in to_process:
            self._process_price_component(component, options, aggregated)

        # If the POP is not a bundle check the pricing
        # If the bundle is a pop download the models

        # If a characteristic has been defined check if the component have to be applied
        # If the charactristic is tailored apply the value

        result = []
        for priceType in aggregated.keys():
            for period in aggregated[priceType].keys():
                result.append({
                    "priceType": priceType,
                    "recurringChargePeriod": period,
                    "price": {
                        "taxRate": 0,
                        "dutyFreeAmount": {
                            "unit": "EUR",
                            "value": str(aggregated[priceType][period]['value'])
                        },
                        "taxIncludedAmount": {
                            "unit": "EUR",
                            "value": str(aggregated[priceType][period]['value'])
                        }
                    },
                    "priceAlteration": []
                })

        return result
