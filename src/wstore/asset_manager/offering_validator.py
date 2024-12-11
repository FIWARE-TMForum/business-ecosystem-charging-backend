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

    def _count_resource_offerings(self, assets):
        count = 0
        if len(assets)>0:
            offerings = Offering.objects.filter(asset__overlap=assets)
            count = len(offerings)
        return count

    def _set_asset_public_status(self, assets, is_open):
        for asset in assets:
            asset.is_public = is_open
            asset.save()

    def _get_price(self, id_):
        url = "{}/productOfferingPrice/{}".format(settings.CATALOG, id_)
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

    @on_product_offering_validation
    def _validate_offering_pricing(self, provider, product_offering, bundled_offerings, assets):
        is_open = False
        is_custom = False

        # Validate offering pricing fields
        if "productOfferingPrice" in product_offering:
            names = []
            customs = 0

            # Check if the pricing is included or it is needed to download it
            for price in product_offering["productOfferingPrice"]:
                recurringKey = "recurringChargePeriod"
                if "id" in price and "href" in price and "priceType" not in price:

                    # This field is different depending on whether the model is embedded
                    recurringKey = "recurringChargePeriodType"
                    price_model = self._get_price(price["id"])
                else:
                    price_model = price

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

                # Validate price unit
                if "priceType" not in price_model:
                    raise ValueError("Missing required field priceType in productOfferingPrice")

                if (
                    price_model["priceType"] != "one time"
                    and price_model["priceType"] != "recurring"
                    and price_model["priceType"] != "usage"
                    and price_model["priceType"] != "custom"
                ):
                    raise ValueError("Invalid priceType, it must be one time, recurring, usage, or custom")

                # If the model is custom no extra validation is required
                if price_model["priceType"] == "custom":
                    is_custom = True
                    customs += 1
                    continue

                if price_model["priceType"] == "recurring" and recurringKey not in price_model:
                    raise ValueError("Missing required field {} for recurring priceType".format(recurringKey))

                if price_model["priceType"] == "recurring" and not ChargePeriod.contains(
                    price_model[recurringKey]
                ):
                    raise ValueError(
                        "Unrecognized " + recurringKey + ": " + price_model[recurringKey]
                    )

                # Validate currency
                if "price" not in price_model:
                    raise ValueError("Missing required field price in productOfferingPrice")

                price_unit = price_model["price"]
                if "taxIncludedAmount" in price_model["price"]:
                    price_unit = price_model["price"]["taxIncludedAmount"]

                self._validate_value_price(price_unit)

            if is_open and len(names) > 1:
                raise ValueError("Open offerings cannot include price plans")

            if is_custom and len(names) != customs:
                raise ValueError("Custom pricing offerings cannot include processed price plans")

        return is_open, is_custom

    def _get_offering_asset(self, product_offering, bundled_offerings):
        assets = []
        
        # Check if the offering is not a bundle
        if not len(bundled_offerings):
            product_specs = self._get_product_specs(product_offering["productSpecification"]["id"])
            if len(product_specs) == 0:
                raise ValueError("Product specs inside the offering does not exist")
            # product_specs list has at maximum 1 object
            for service_spec_ref in product_specs[0]["serviceSpecification"]:
                assets.extend(Resource.objects.filter(service_spec_id=service_spec_ref["id"]))
        return assets

    # def _validate_offering_model(self, product_offering, bundled_offerings, is_open):
    #     assets = self._get_offering_asset(product_offering, bundled_offerings)

        # If the offering is a bundle and is open all the bundled offerings must be open
        # Unsupported
        # if is_open and len(bundled_offerings) != len([offer for offer in bundled_offerings if offer.is_open]):
        #     raise ValueError("If a bundle is open all the bundled offerings must be open")

        # return assets
        
    def _build_offering_model(self, provider, product_offering, bundled_offerings, assets, is_open, is_custom=False):

        # Open products can only be included in a single offering
        # Unsupported
        # offering_count = self._count_resource_offerings(assets)
        # is_public= any(el.is_public for el in assets)
        # if (is_open and offering_count > 0) or (not is_open and offering_count == 1 and is_public):
        #     raise ValueError("Assets of open offerings cannot be monetized in other offerings")

        # Check if the offering contains a description
        description = ""
        if "description" in product_offering:
            description = product_offering["description"]

        # Unsupported
        # if len(assets) > 0:
        #     self._set_asset_public_status(assets, is_open)
        try:
            offering = Offering.objects.create(
                owner_organization=provider,
                name=product_offering["name"],
                description=description,
                version=product_offering["version"],
                is_open=is_open,
                is_custom=is_custom,
                bundled_offerings=[offering.pk for offering in bundled_offerings],
            )
            print(offering)
            offering.asset.set(assets)
            offering.save()
        except Exception as e:
            raise Exception(f"Offering Creation Error: {e}")

    def attach_info(self, provider, product_offering):
        print("attach info")
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
        assets = self._get_offering_asset(product_offering, bundled_offerings)
        print(assets)
        is_open, is_custom = self._validate_offering_pricing(provider, product_offering, bundled_offerings, assets)
        print(1)
        self._build_offering_model(provider, product_offering, bundled_offerings, assets, is_open, is_custom)
        print(2)

    def validate_update(self, provider, product_offering):
        bundled_offerings = self._get_bundled_offerings(product_offering)
        assets = self._get_offering_asset(product_offering, bundled_offerings)
        self._validate_offering_pricing(provider, product_offering, bundled_offerings, assets)
        
        #assets = self._validate_offering_model(product_offering, bundled_offerings, is_open)

        # Open products can only be included in a single offering
        # Unsupported
        # if is_open and self._count_resource_offerings(assets) > 1:
        #     raise ValueError("Assets of open offerings cannot be monetized in other offerings")

        # if assets is not None:
        #     self._set_asset_public_status(assets, is_open)
