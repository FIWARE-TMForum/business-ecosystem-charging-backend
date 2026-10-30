# -*- coding: utf-8 -*-

# Copyright (c) 2016 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2020 Future Internet Consulting and Development Solutions S.L.

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

from decimal import Decimal
from logging import getLogger

from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.resource_plugins.decorators import on_product_offering_validation
from wstore.store_commons.product_catalog import ProductCatalog
from wstore.store_commons.utils.units import ChargePeriod, CurrencyCode

logger = getLogger("wstore.default_logger")


class OfferingValidator(CatalogValidator):
    def __init__(self):
        super().__init__()

        self._catalog = ProductCatalog()

    def _get_product_spec(self, id_):
        if self._product_spec is None:
            self._product_spec = self._catalog.get_specification(id_)

        return self._product_spec

    def _get_price(self, id_):
        return self._catalog.get_price(id_)

    def _validate_value_price(self, price):
        if "unit" not in price:
            raise ValueError("Missing currency code in price")

        if not CurrencyCode.contains(price["unit"]):
            raise ValueError("Unrecognized currency: " + price["unit"])

        if Decimal(price["value"]) <= Decimal("0"):
            raise ValueError("Invalid price, it must be greater than zero.")

    def _is_same_value(self, value_use_value_item, value_use_id, prd_char_value, anti_collision: dict):
        use_unit = None

        if "unitOfMeasure" in value_use_value_item:
            use_unit = value_use_value_item["unitOfMeasure"].lower()

        prd_unit = None

        if "unitOfMeasure" in prd_char_value:
            prd_unit = prd_char_value["unitOfMeasure"].lower()

        # Check if we have a range
        is_same = False

        if not "value" in prd_char_value and "valueFrom" in prd_char_value and "valueTo" in prd_char_value:
            if value_use_value_item["valueFrom"] > value_use_value_item["valueTo"]:
                raise ValueError("valueFrom should not be greater than valueTo")

            is_same = (
                value_use_value_item["valueFrom"] >= prd_char_value["valueFrom"]
                and value_use_value_item["valueTo"] <= prd_char_value["valueTo"]
            )

            if anti_collision is not None:
                if not anti_collision.get(value_use_id, False):  # if the characteristic is not recorded
                    anti_collision[value_use_id] = {
                        "total_range": prd_char_value  # record total range of the product spec char
                    }

                if not anti_collision[value_use_id].get(f"from-{value_use_value_item['valueFrom']}", False):
                    anti_collision[value_use_id][f"from-{value_use_value_item['valueFrom']}"] = []

                anti_collision[value_use_id][f"from-{value_use_value_item['valueFrom']}"].append(
                    value_use_value_item["valueTo"]
                )
        else:
            is_same = value_use_value_item["value"] == prd_char_value["value"] and use_unit == prd_unit

        return is_same

    def _validate_char_value_use(self, price_component, product_spec, anti_collision_record=None):
        # Check if a configuration profile has been provided
        if "prodSpecCharValueUse" in price_component:
            # Check that the characteristics exists
            for value_use in price_component["prodSpecCharValueUse"]:
                # Check the product spec ID
                if (
                    "productSpecification" in value_use
                    and value_use["productSpecification"]["id"] != product_spec["id"]
                ):
                    raise ValueError("The productSpecValueUse point to an invalid product specification")

                # Check that the characteristic exists
                prd_char = None

                for prod_char in (
                    product_spec["productSpecCharacteristic"] if "productSpecCharacteristic" in product_spec else []
                ):
                    if prod_char["id"] == value_use["id"]:
                        prd_char = prod_char
                        break

                if prd_char is None:
                    raise ValueError("ProductSpecValueUse refers to non-existing product characteristic")

                # Check that the value is valid
                if "productSpecCharacteristicValue" in value_use:
                    for value_use_value_item in value_use["productSpecCharacteristicValue"]:
                        for prd_char_value in prd_char["productSpecCharacteristicValue"]:
                            if self._is_same_value(
                                value_use_value_item, value_use["id"], prd_char_value, anti_collision_record
                            ):
                                break
                        else:
                            raise ValueError("ProductSpecValueUse refers to non-existing product characteristic value")

    def _validate_price_component(self, price_component, product_spec, anti_collision=None, has_profile=False):
        # validate config profile
        if has_profile and "prodSpecCharValueUse" in price_component and len(price_component["prodSpecCharValueUse"]):
            raise ValueError(
                "A price plan with a configuration profile cannot contain pricing components with characteristics"
            )

        recurringKey = "recurringChargePeriodType"
        recurring_pricing = ["recurring", "recurring-prepaid", "recurring-postpaid"]
        valid_pricing = ["one time", "usage"]
        valid_pricing.extend(recurring_pricing)

        # Validate price unit
        if "priceType" not in price_component:
            raise ValueError("Missing required field priceType in productOfferingPrice component")

        if price_component["priceType"].lower() not in valid_pricing:
            raise ValueError("Invalid priceType, it must be one time, recurring, or usage")

        if price_component["priceType"].lower() in recurring_pricing and recurringKey not in price_component:
            raise ValueError("Missing required field {} for recurring priceType".format(recurringKey))

        if price_component["priceType"].lower() in recurring_pricing and not ChargePeriod.contains(
            price_component[recurringKey]
        ):
            raise ValueError("Unrecognized " + recurringKey + ": " + price_component[recurringKey])

        # Validate currency
        if "price" not in price_component:
            raise ValueError("Missing required field price in productOfferingPrice")

        self._validate_value_price(price_component["price"])
        self._validate_char_value_use(price_component, product_spec, anti_collision_record=anti_collision)

    @on_product_offering_validation
    def _validate_offering_pricing(self, provider, product_offering):
        self._product_spec = None

        is_open = False
        is_custom = False

        # Validate offering pricing fields
        if "productOfferingPrice" in product_offering:
            names = []
            customs = 0

            # Check if the pricing is included or if it is needed to download it
            for price in product_offering["productOfferingPrice"]:
                price_model = self._get_price(price["id"])

                if "name" not in price_model:
                    raise ValueError("Missing required field name in productOfferingPrice")

                if price_model["name"].lower() in names:
                    raise ValueError("Price plans names must be unique (" + price_model["name"] + ")")

                names.append(price_model["name"].lower())

                # Check if the offering is an open offering
                if price_model["name"].lower() == "open" and (
                    len(price_model.keys()) == 3 or (len(price_model.keys()) == 4 and "description" in price_model)
                ):
                    is_open = True
                    continue

                # If the model is custom no extra validation is required
                if "priceType" in price_model and price_model["priceType"] == "custom":
                    is_custom = True
                    customs += 1
                    continue

                # Get the product spec
                product_spec = self._get_product_spec(product_offering["productSpecification"]["id"])

                # Validate price components
                if "isBundle" in price_model and price_model["isBundle"]:
                    has_profile = "prodSpecCharValueUse" in price_model and len(price_model["prodSpecCharValueUse"]) > 0

                    anti_collision = {}
                    # The plan may include a configuration profile
                    self._validate_char_value_use(price_model, product_spec)

                    # The price plan has the price components linked
                    [
                        self._validate_price_component(
                            self._get_price(price_comp["id"]), product_spec, anti_collision, has_profile
                        )
                        for price_comp in price_model.get("bundledPopRelationship", [])
                    ]

                    if len(anti_collision) != 0:
                        self._check_range_collision(anti_collision)

                else:
                    # The price plan has 1 single price component attached
                    self._validate_price_component(price_model, product_spec)

            if is_open and len(names) > 1:
                raise ValueError("Open offerings cannot include price plans")

            if is_custom and len(names) != customs:
                raise ValueError("Custom pricing offerings cannot include processed price plans")

        return is_open, is_custom

    def _recursive_anti_collision(self, value_search, value_end, record):
        value_nexts = record.get(f"from-{value_search}", None)

        if value_nexts is None or len(value_nexts) == 0:
            return False

        for value_next in value_nexts:
            if value_next == value_end:
                return True
            else:
                reached = self._recursive_anti_collision(value_next + 1, value_end, record)

                if reached:
                    return reached

        return False

    def _check_range_collision(self, anti_collision: dict):
        for k, char_range_record in anti_collision.items():
            total_range = char_range_record.pop("total_range")
            value_init = total_range["valueFrom"]
            value_end = total_range["valueTo"]
            continous = self._recursive_anti_collision(value_init, value_end, char_range_record)

            if not continous:
                logger.error(f"Offering price linked to Characteristic with key: {k} doesn't have continous subranges")
                raise ValueError(
                    f"Offering price linked to Characteristic with key: {k} doesn't have continous subranges"
                )

        return None

    def validate_creation(self, provider, catalog_element):
        self._validate_offering_pricing(provider, catalog_element)

    def validate_update(self, provider, catalog_element):
        self._validate_offering_pricing(provider, catalog_element)
