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

import requests

from django.conf import settings

from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.models import Resource
from wstore.asset_manager.resource_plugins.decorators import on_product_offering_validation
from wstore.ordering.models import Offering
from wstore.store_commons.utils.units import ChargePeriod, CurrencyCode
from wstore.store_commons.utils.url import get_service_url


class OfferingValidator(CatalogValidator):
    def _get_bundled_offerings(self, product_offering):
        bundled_offerings = []

        # Validate Bundle fields
        if "isBundle" in product_offering and product_offering["isBundle"]:
            if "bundledProductOffering" not in product_offering:
                raise ValueError("Offering bundles must contain a bundledProductOffering field")

            if len(product_offering["bundledProductOffering"]) < 2:
                raise ValueError("Offering bundles must contain at least two bundled offerings")

            for bundle in product_offering["bundledProductOffering"]:
                # Check if the specified offerings have been already registered
                offerings = Offering.objects.filter(off_id=bundle["id"])
                if not len(offerings):
                    raise ValueError("The bundled offering " + bundle["id"] + " is not registered")

                bundled_offerings.append(offerings[0])

        return bundled_offerings

    def _count_resource_offerings(self, asset):
        count = 0
        if asset is not None:
            offerings = Offering.objects.filter(asset=asset)
            count = len(offerings)
        return count

    def _set_asset_public_status(self, asset, is_open):
        if is_open and len(asset.bundled_assets) > 0:
            # If the asset is single set the is_public flag
            raise ValueError("Product bundles cannot be published in open offerings. Create an offering bundle instead")

        asset.is_public = is_open
        asset.save()

    def _get_product_spec(self, id_):
        if self._product_spec is None:
            url = get_service_url("catalog", "/productSpecification/{}".format(id_))
            resp = requests.get(url)

            if resp.status_code != 200:
                raise ValueError("Invalid product reference")
            self._product_spec = resp.json()

        return self._product_spec

    def _get_price(self, id_):
        url = get_service_url("catalog", "/productOfferingPrice/{}".format(id_))
        resp = requests.get(url)

        if resp.status_code != 200:
            raise ValueError("Invalid pricing reference")

        return resp.json()

    def _validate_value_price(self, price):
        if "unit" not in price:
            raise ValueError("Missing currency code in price")

        if not CurrencyCode.contains(price["unit"]):
            raise ValueError("Unrecognized currency: " + price["unit"])

        if Decimal(price["value"]) <= Decimal("0"):
            raise ValueError("Invalid price, it must be greater than zero.")

    def _is_same_value(self, use_val, prd_char_value):
        use_unit = None
        if "unitOfMeasure" in use_val:
            use_unit = use_val["unitOfMeasure"].lower()

        prd_unit = None
        if "unitOfMeasure" in prd_char_value:
            prd_unit = prd_char_value["unitOfMeasure"].lower()

        # Check if we have a range
        is_same = False
        if not "value" in prd_char_value and "valueFrom" in prd_char_value and "valueTo" in prd_char_value:
            is_same = use_val["value"] >= prd_char_value["valueFrom"] and \
                use_val["value"] <= prd_char_value["valueTo"] and \
                use_unit == prd_unit
        else:
            is_same = use_val["value"] == prd_char_value["value"] and \
            use_unit == prd_unit

        return is_same

    def _validate_char_value_use(self, price_component, prod_spec_id):
        # Check if a configuration profile has been provided
        if "prodSpecCharValueUse" in price_component:
            # Get the product spec
            product_spec = self._get_product_spec(prod_spec_id)

            # Check that the characteristics exists
            for value_use in price_component["prodSpecCharValueUse"]:
                # Check the product spec ID
                if "productSpecification" in value_use and value_use["productSpecification"]["id"] != prod_spec_id:
                    raise ValueError("The productSpecValueUse point to an invalid product specification")

                # Check that the characteristic exists
                prd_char = None
                for prod_char in (product_spec["productSpecCharacteristic"] if "productSpecCharacteristic" in product_spec else []):
                    if prod_char["id"] == value_use["id"]:
                        prd_char = prod_char
                        break

                if prd_char is None:
                    raise ValueError("ProductSpecValueUse refers to non-existing product characteristic")

                # Check that the value is valid
                if "productSpecCharacteristicValue" in value_use:
                    for use_val in value_use["productSpecCharacteristicValue"]:
                        for prd_char_value in prd_char["productSpecCharacteristicValue"]:
                            if self._is_same_value(use_val, prd_char_value):
                                break
                        else:
                            raise ValueError("ProductSpecValueUse refers to non-existing product characteristic value")

    def _validate_price_component(self, price_component, prod_spec_id):
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
            raise ValueError(
                "Unrecognized " + recurringKey + ": " + price_component[recurringKey]
            )

        # Validate currency
        if "price" not in price_component:
            raise ValueError("Missing required field price in productOfferingPrice")

        self._validate_value_price(price_component["price"])
        self._validate_char_value_use(price_component, prod_spec_id)

    @on_product_offering_validation
    def _validate_offering_pricing(self, provider, product_offering, bundled_offerings):
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
                # if "id" in price and "href" in price and "priceType" not in price:
                #     # This field is different depending on whether the model is embedded
                #     price_model = self._get_price(price["id"])
                # else:
                #     # Embedded pricing not supported
                #     raise ValueError("Embedded pricing is not supported")

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

                # Validate price components
                if "isBundle" in price_model and price_model["isBundle"]:
                    # The plan may include a configuration profile
                    self._validate_char_value_use(price_model, product_offering['productSpecification']['id'])

                    # The price plan has the price components linked
                    [self._validate_price_component(self._get_price(price_comp["id"]), product_offering['productSpecification']['id'])
                        for price_comp in price_model["bundledPopRelationship"]]

                else:
                    # The price plan has 1 single price component attached
                    self._validate_price_component(price_model, product_offering['productSpecification']['id'])

            if is_open and len(names) > 1:
                raise ValueError("Open offerings cannot include price plans")

            if is_custom and len(names) != customs:
                raise ValueError("Custom pricing offerings cannot include processed price plans")

        return is_open, is_custom

    def _download(self, url):
        r = requests.get(url)

        if r.status_code != 200:
            raise ValueError("There has been a problem accessing the product spec included in the offering")

        return r.json()

    def _get_offering_asset(self, product_offering, bundled_offerings):
        asset = None
        # Check if the offering is a bundle
        if not len(bundled_offerings):
            assets = Resource.objects.filter(product_id=product_offering["productSpecification"]["id"])

            if len(assets):
                asset = assets[0]

            is_digital = asset is not None
        else:
            # Check if the bundle is digital
            digital = len([offering for offering in bundled_offerings if offering.is_digital])

            if digital > 0 and digital != len(bundled_offerings):
                raise ValueError(
                    "Mixed bundle offerings are not allowed. All bundled offerings must be digital or physical"
                )

            is_digital = digital > 0

        return asset, is_digital

    def _validate_offering_model(self, product_offering, bundled_offerings, is_open):
        asset, is_digital = self._get_offering_asset(product_offering, bundled_offerings)

        # Open offerings only can be digital
        if is_open and not is_digital:
            raise ValueError("Non digital products cannot be open")

        # If the offering is a bundle and is open all the bundled offerings must be open
        if is_open and len(bundled_offerings) != len([offer for offer in bundled_offerings if offer.is_open]):
            raise ValueError("If a bundle is open all the bundled offerings must be open")

        return asset, is_digital

    def _build_offering_model(self, provider, product_offering, bundled_offerings, is_open, is_custom=False):
        asset, is_digital = self._validate_offering_model(product_offering, bundled_offerings, is_open)

        # Open products can only be included in a single offering
        offering_count = self._count_resource_offerings(asset)
        if is_digital and (
            (is_open and offering_count > 0) or (not is_open and offering_count == 1 and asset.is_public)
        ):
            raise ValueError("Assets of open offerings cannot be monetized in other offerings")

        # Check if the offering contains a description
        description = ""
        if "description" in product_offering:
            description = product_offering["description"]

        if asset is not None:
            self._set_asset_public_status(asset, is_open)

        Offering.objects.create(
            owner_organization=provider,
            name=product_offering["name"],
            description=description,
            version=product_offering["version"],
            is_digital=is_digital,
            asset=asset,
            is_open=is_open,
            is_custom=is_custom,
            bundled_offerings=[offering.pk for offering in bundled_offerings],
        )

    def attach_info(self, provider, product_offering):
        # Find the offering model to attach the info
        offerings = Offering.objects.filter(
            off_id=None,
            owner_organization=provider,
            name=product_offering["name"],
            version=product_offering["version"],
        )

        if not len(offerings):
            raise ValueError("The specified offering has not been registered")

        offering = offerings[0]
        offering.off_id = product_offering["id"]
        offering.href = product_offering["href"]
        offering.save()

    def validate_creation(self, provider, product_offering):
        bundled_offerings = self._get_bundled_offerings(product_offering)
        is_open, is_custom = self._validate_offering_pricing(provider, product_offering, bundled_offerings)
        self._build_offering_model(provider, product_offering, bundled_offerings, is_open, is_custom)

    def validate_update(self, provider, product_offering):
        bundled_offerings = self._get_bundled_offerings(product_offering)
        is_open, is_custom = self._validate_offering_pricing(provider, product_offering, bundled_offerings)

        asset, is_digital = self._validate_offering_model(product_offering, bundled_offerings, is_open)

        # Open products can only be included in a single offering
        if is_open and self._count_resource_offerings(asset) > 1:
            raise ValueError("Assets of open offerings cannot be monetized in other offerings")

        if asset is not None:
            self._set_asset_public_status(asset, is_open)
