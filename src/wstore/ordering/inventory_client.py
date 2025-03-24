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


from copy import deepcopy
from datetime import datetime
from uuid import uuid4
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class InventoryClient:
    def __init__(self):
        self._inventory_api = settings.INVENTORY

    def _build_callback_url(self):
        # Use the local site for registering the callback
        site = settings.LOCAL_SITE

        return urljoin(site, "charging/api/orderManagement/products")

    def get_hubs(self):
        r = requests.get(self._inventory_api + "/hub")
        r.raise_for_status()
        return r.json()

    def create_inventory_subscription(self):
        """
        Creates a subscription to the inventory API so the server will be able to activate products
        """

        callback_url = self._build_callback_url()

        for hub in self.get_hubs():
            if hub["callback"] == callback_url:
                break
        else:
            callback = {"callback": callback_url}

            r = requests.post(self._inventory_api + "/hub", json=callback)

            if r.status_code != 201 and r.status_code != 409:
                msg = "It hasn't been possible to create inventory subscription, "
                msg += "please check that the inventory API is correctly configured "
                msg += "and that the inventory API is up and running"
                raise ImproperlyConfigured(msg)

    def get_product(self, product_id):
        url = self._inventory_api + "/product/" + str(product_id)

        r = requests.get(url)
        r.raise_for_status()

        return r.json()

    def get_products(self, query={}):
        """
        Retrieves a set of products that can be filtered providing a query dict
        :param query: Dict containing the query used to filter the products
        :return: List of resulting products
        """

        qs = "?"
        for k, v in query.items():
            qs += "{}={}&".format(k, v)

        url = self._inventory_api + "/product" + qs[:-1]

        r = requests.get(url)
        r.raise_for_status()

        return r.json()

    def patch_product(self, product_id, patch_body):
        """
        Patch a given product according to the provided patch values
        :param product_id: Id if the product to be patched
        :param patch_body: New values for the product fields to be patched
        """
        # Build product url
        url = self._inventory_api + "/product/" + str(product_id)

        try:
            response = requests.patch(url, json=patch_body)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise

        return response.json()

    def activate_product(self, product_id):
        """
        Activates a given product by changing its state to Active and providing a startDate
        :param product_id: Id of the product to be activated
        """
        patch_body = {
            "status": "active",
            "startDate": datetime.utcnow().isoformat() + "Z",
        }
        self.patch_product(product_id, patch_body)

    def suspend_product(self, product_id):
        """
        Suspends a given product by changing its state to Suspended
        :param product_id: Id of the product to be suspended
        """
        patch_body = {"status": "suspended"}
        self.patch_product(product_id, patch_body)

    def terminate_product(self, product_id):
        """
        terminates a given product by changing its state to Terminated
        :param product_id: Id of the product to be terminated
        """

        # Activate the product since it must be in active state to be terminated
        try:
            self.activate_product(product_id)
        except:
            pass

        patch_body = {
            "status": "terminated",
            "terminationDate": datetime.utcnow().isoformat() + "Z",
        }
        self.patch_product(product_id, patch_body)

    def create_product(self, product):
        url = self._inventory_api + "/product/"

        response = requests.post(url, json=product)
        response.raise_for_status()

        return response.json()

    ####
    def download_spec(self, catalog_endpoint, spec_path, spec_id):
        catalog = urlparse(catalog_endpoint)
        resource_spec_url = "{}://{}{}/{}".format(catalog.scheme, catalog.netloc, catalog.path + spec_path, spec_id)

        resp = requests.get(resource_spec_url, verify=settings.VERIFY_REQUESTS)
        return resp.json()

    def build_inventory_char(self, spec_char, value_field):
        value = None
        for val in spec_char[value_field]:
            if val["isDefault"]:
                if "valueFrom" in val:
                    value = str(val["valueFrom"]) + " - " + str(val["valueTo"])
                else:
                    value = str(val["value"])

                if "unitOfMeasure" in val:
                    value += " " + val["unitOfMeasure"]

        return {
            "id": "urn:ngsi-ld:characteristic:{}".format(str(uuid4())),
            "name": spec_char["name"],
            "valueType": "string",
            "value": value
        }

    def create_resource(self, resource_id, customer_party):
        # Get resource specification        
        resource_spec = self.download_spec(settings.RESOURCE_CATALOG, '/resourceSpecification', resource_id)

        resource = {
            #"resourceCharacteristic": [self.build_inventory_char(char, "resourceSpecCharacteristicValue") for char in resource_spec["resourceSpecCharacteristic"]],
            "relatedParty": [customer_party],
            "resourceStatus": "reserved",
            "startOperatingDate": datetime.now().isoformat() + "Z"
        }

        if "name" in resource_spec:
            resource["name"] = resource_spec["name"]

        if "description" in resource_spec:
            resource["description"] = resource_spec["description"]

        inventory = urlparse(settings.RESOURCE_INVENTORY)
        resource_url = "{}://{}{}".format(inventory.scheme, inventory.netloc, inventory.path + '/resource')

        inv_response = requests.post(resource_url, json=resource, verify=settings.VERIFY_REQUESTS)
        inv_resource = inv_response.json()

        return inv_resource["id"]

    def create_service(self, service_id, customer_party):
        # Get service specification
        service_spec = self.download_spec(settings.SERVICE_CATALOG, '/serviceSpecification', service_id)
        service = {
            "serviceCharacteristic": [self.build_inventory_char(char, "characteristicValueSpecification") for char in service_spec["specCharacteristic"]],
            "relatedParty": [customer_party],
            "state": "reserved",
            "startDate": datetime.now().isoformat() + "Z"
        }
        if "name" in service_spec:
            service["name"] = service_spec["name"]

        if "description" in service_spec:
            service["description"] = service_spec["description"]
        inventory = urlparse(settings.SERVICE_INVENTORY)
        resource_url = "{}://{}{}".format(inventory.scheme, inventory.netloc, inventory.path + '/service')

        inv_response = requests.post(resource_url, json=service, verify=settings.VERIFY_REQUESTS)
        inv_service = inv_response.json()
        return inv_service["id"]

    def get_product_price(self, price):
        # Build a price object compatible with 
        return {
            "productOfferingPrice": {
                "id": price["id"],
                "href": price["id"]
            }
        }

    def get_price_component(self, price_id):
        catalog = urlparse(settings.CATALOG)
        price_url = "{}://{}{}/{}".format(
            catalog.scheme, catalog.netloc, catalog.path + "/productOfferingPrice", price_id
        )
        resp = requests.get(price_url, verify=settings.VERIFY_REQUESTS)
        price = resp.json()

        return price

    def get_list_of_prices(self, price_model):
        price = self.get_price_component(price_model["id"])
        result = [self.get_product_price(price)]

        if "isBundle" in price and price["isBundle"]:
            result.extend([
                self.get_product_price(self.get_price_component(bundle["id"]))
            for bundle in price["bundledPopRelationship"]])

        return result

    def build_product_model(self, order_item, order_id, billing_account):
        product = deepcopy(order_item["product"])

        product["name"] = "oid={}".format(order_id)
        product["status"] = "created"
        product["productOffering"] = order_item["productOffering"]

        if "productCharacteristic" not in product:
                product["productCharacteristic"] = []

        if "itemTotalPrice" in order_item and len(order_item["itemTotalPrice"]) > 0:
            product["productPrice"] = self.get_list_of_prices(order_item["itemTotalPrice"][0]["productOfferingPrice"])

        product["billingAccount"] = billing_account

        # Add the referred type
        product["relatedParty"] = [
            {
                "id": party["id"],
                "href": party["href"],
                "role": party["role"],
                "@referredType": "organization"
            } for party in product["relatedParty"]
        ]

        return product
