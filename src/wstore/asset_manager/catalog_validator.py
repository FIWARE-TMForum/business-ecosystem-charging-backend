# -*- coding: utf-8 -*-

# Copyright (c) 2016 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid

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
from django.conf import settings
from wstore.asset_manager.errors import ProductError, ServiceError


class CatalogValidator:
    def __init__(self):
        self._has_terms = False

    def _get_characteristic_value(self, characteristic):
        if len(characteristic["productSpecCharacteristicValue"]) > 1:
            raise ProductError(f"The characteristic {characteristic['name']} must not contain multiple values")
        return characteristic["productSpecCharacteristicValue"][0]["value"]
    
    def _get_spec_characteristic_value(self, characteristic):                              
        if len(characteristic["characteristicValueSpecification"]) > 1:
            raise ServiceError(f"The characteristic {characteristic['name']} must not contain multiple values")
        if "value" not in characteristic["characteristicValueSpecification"][0]:
            raise ServiceError(f"Missing 'value' attribute in {characteristic['name']} at characteristicValueSpecification")
        return characteristic["characteristicValueSpecification"][0]["value"]
    
    ###############################################
    #TODO: Ya no se usa, hay que cambiarlo
    def parse_characteristics(self, product_spec):

        expected_chars = {
            "asset type": [],
            "media type": [],
            "location": [],
            "asset": [],
        }

        asset_type = None
        media_type = None
        location = None
        asset_id = None

        if "productSpecCharacteristic" in product_spec:
            terms = []

            # Extract the needed characteristics for processing digital assets
            is_digital = False
            for char in product_spec["productSpecCharacteristic"]:
                if char["name"].lower() in expected_chars:
                    is_digital = True
                    expected_chars[char["name"].lower()].append(self._get_characteristic_value(char))

                if char["name"].lower() == "license":
                    terms.append(self._get_characteristic_value(char))

            for char_name in expected_chars:
                # Validate the existence of the characteristic
                if not len(expected_chars[char_name]) and is_digital:
                    raise ProductError("Digital product specifications must contain a " + char_name + " characteristic")

                # Validate that only a value has been provided
                if len(expected_chars[char_name]) > 1:
                    raise ProductError(
                        "The product specification must not contain more than one " + char_name + " characteristic"
                    )

            if len(terms) > 1:
                raise ProductError("The product specification must not contain more than one license characteristic")

            self._has_terms = len(terms) > 0

            if is_digital:
                asset_type = expected_chars["asset type"][0]
                media_type = expected_chars["media type"][0]
                location = expected_chars["location"][0]
                asset_id = expected_chars["asset"][0]

        return asset_type, media_type, location, asset_id
    
    ############################################
    def _get_specs(self, url):
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def _get_service_specs(self, ref_ids):
        url = f"{settings.SERVICE_CATALOG}/serviceSpecification?id={ref_ids}"
        return self._get_specs(url)

    def _get_product_specs(self, ref_ids):
        url = f"{settings.CATALOG}/productSpecification?id={ref_ids}"
        return self._get_specs(url)

    def parse_spec_characteristics(self, service_spec):

        print("Entra en parse_spec_characteristics")

        expected_chars = {
            "asset type": [],
            "media type": [],
            "location": [],
            "asset": [], 
        }

        asset_type = None
        media_type = None
        location = None
        asset_id = None

        if "specCharacteristic" in service_spec:

            #print("Entra if specCharacteristic")
            print(service_spec["specCharacteristic"])

            terms = []

            # Extract the needed characteristics for processing digital assets
            is_digital = False
            for char in service_spec["specCharacteristic"]:
                print(char["name"])
                if char["name"].lower() in expected_chars:
                    is_digital = True
                    expected_chars[char["name"].lower()].append(self._get_spec_characteristic_value(char))
                elif char["name"].lower() == "license":
                    terms.append(self._get_spec_characteristic_value(char))
            if not len(expected_chars["asset"]):
                # asset id is set to None for automatic creation of the asset
                expected_chars["asset"].append(None)

            for char_name in expected_chars:
                if not len(expected_chars[char_name]) and is_digital:
                    raise ServiceError("Digital service specifications must contain a " + char_name + " characteristic")
                # Validate that only a value has been provided
                if len(expected_chars[char_name]) > 1:
                    raise ServiceError(
                        "The service specification must not contain more than one " + char_name + " characteristic"
                    )

            if len(terms) > 1:
                raise ServiceError("The service specification must not contain more than one license characteristic")

            self._has_terms = len(terms) > 0

            if is_digital:
                asset_type = expected_chars["asset type"][0]
                media_type = expected_chars["media type"][0]
                location = expected_chars["location"][0]
                asset_id = expected_chars["asset"][0]

        print("Antes del return")
        print(f"asset_id ->{asset_id}")

        return asset_type, media_type, location, asset_id
    
    ############################################

    def validate_creation(self, provider, catalog_element):
        raise NotImplementedError("This action is not allowed to be called.")

    def attach_info(self, provider, catalog_element):
         raise NotImplementedError("This action is not allowed to be called.")

    def rollback_create(self, provider, catalog_element):
        raise NotImplementedError("This action is not allowed to be called.")

    def validate_update(self, provider, catalog_element):
        raise NotImplementedError("This action is not allowed to be called.")

    def validate_upgrade(self, provider, catalog_element):
        raise NotImplementedError("This action is not allowed to be called.")

    def rollback_upgrade(self, provider, catalog_element):
        raise NotImplementedError("This action is not allowed to be called.")

    def attach_upgrade(self, provider, catalog_element):
        raise NotImplementedError("This action is not allowed to be called.")

    def validate_deletion(self, provider, catalog_element):
        raise NotImplementedError("This action is not allowed to be called.")

    def validate(self, action, provider, catalog_element):

        #print("Entra en validate en catalog validator")

        validators = {
            "create": self.validate_creation,
            "attach": self.attach_info,
            "rollback_create": self.rollback_create,
            "update": self.validate_update,
            "upgrade": self.validate_upgrade,
            "rollback_upgrade": self.rollback_upgrade,
            "attach_upgrade": self.attach_upgrade,
            "delete": self.validate_deletion,
        }

        if action not in validators:
            msg = "The provided action (" + action
            msg += ") is not valid. Allowed values are create, attach, update, upgrade, and delete"
            raise ValueError(msg)

        return validators[action](provider, catalog_element)
