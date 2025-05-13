# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

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


import re
from datetime import datetime
from decimal import Decimal
from logging import getLogger
from urllib.parse import urlparse

import requests
from bson import ObjectId
from django.conf import settings

from wstore.charging_engine.charging.billing_client import BillingClient
from wstore.asset_manager.product_validator import ProductValidator
from wstore.asset_manager.resource_plugins.decorators import on_product_suspended, on_product_acquired
from wstore.charging_engine.charging_engine import ChargingEngine
from wstore.ordering.errors import OrderingError
from wstore.ordering.inventory_client import InventoryClient
from wstore.ordering.models import Contract, Offering, Order
from wstore.ordering.ordering_client import OrderingClient
from wstore.store_commons.rollback import rollback

logger = getLogger("wstore.default_logger")


class OrderingManager:
    def __init__(self):
        self._customer = None
        self._validator = ProductValidator()

    def _download(self, url, element, item_id):
        r = requests.get(url, verify=settings.VERIFY_REQUESTS)

        if r.status_code != 200:
            logger.error(f"The {element} specified in order item {item_id} does not exist")
            raise OrderingError(f"The {element} specified in order item {item_id} does not exist")

        return r.json()

    def _get_offering_info(self, item):
        # Download related product offering and product specification
        catalog = urlparse(settings.CATALOG)

        offering_id = item["productOffering"]["href"]
        offering_url = "{}://{}{}/{}".format(
            catalog.scheme, catalog.netloc, catalog.path + "/productOffering", offering_id
        )

        offering_info = self._download(offering_url, "product offering", item["id"])
        return offering_info

    def _get_offering(self, item):
        offering_info = self._get_offering_info(item)
        offering_id = offering_info["id"]

        # Check if the offering has been already loaded in the system
        if len(Offering.objects.filter(off_id=offering_id)) > 0:
            offering = Offering.objects.get(off_id=offering_id)

            # If the offering defines a digital product, check if the customer already owns it
            included_offerings = [Offering.objects.get(pk=ObjectId(off_pk)) for off_pk in offering.bundled_offerings]
            included_offerings.append(offering)

            for off in included_offerings:
                if off.is_digital and off.pk in self._customer.userprofile.current_organization.acquired_offerings:
                    logger.error(
                        f"The customer already owns the digital product offering {off.name} with id {off.off_id}"
                    )
                    raise OrderingError(
                        f"The customer already owns the digital product offering {off.name} with id {off.off_id}"
                    )
        else:
            logger.error(f"The offering {offering_id} has not been previously registered")
            raise OrderingError(f"The offering {offering_id} has not been previously registered")

        return offering, offering_info

    def _parse_price(self, model_mapper, price):
        if price["priceType"].lower() not in model_mapper:
            logger.error(f"Cant parse price: Invalid price model {price['priceType']}")
            raise OrderingError(f"Invalid price model {price['priceType']}")

        unit_field = {
            "one time": "priceType",
            "recurring": "recurringChargePeriod",
            "usage": "unitOfMeasure",
        }

        value = str(price["price"]["taxIncludedAmount"]["value"])
        tax_rate = str(price["price"]["taxRate"])
        duty_free = str(Decimal(value) - ((Decimal(value) * Decimal(tax_rate)) / 100))
        return {
            "value": value,
            "unit": price[unit_field[price["priceType"].lower()]].lower(),
            "tax_rate": tax_rate,
            "duty_free": duty_free,
        }

    def _parse_alteration(self, alteration, type_):
        # Alterations cannot specify usage models
        if alteration["priceType"].lower() != "one time" and alteration["priceType"].lower() != "recurring":
            logger.error("Invalid priceType in price alteration, it must be one time or recurring")
            raise OrderingError("Invalid priceType in price alteration, it must be one time or recurring")

        # Check if it is a fixed value or a percentage
        if "percentage" in alteration["price"] and Decimal(alteration["price"]["percentage"]) > Decimal(0):
            value = alteration["price"]["percentage"]
        else:
            value = {
                "value": alteration["price"]["taxIncludedAmount"],
                "duty_free": alteration["price"]["dutyFreeAmount"],
            }

        alt_model = {
            "type": type_,
            "value": value,
            "period": alteration["priceType"].lower(),
        }

        # Parse condition
        if "priceCondition" in alteration and len(alteration["priceCondition"]):
            exp = re.compile(r"^(eq|lt|gt|le|ge) \d+(\.\d+)?$")

            if not exp.match(alteration["priceCondition"]):
                logger.error(
                    "Invalid priceCondition in price alteration, format must be: [eq | lt | gt | le | ge] value"
                )
                raise OrderingError(
                    "Invalid priceCondition in price alteration, format must be: [eq | lt | gt | le | ge] value"
                )

            op, value = alteration["priceCondition"].split(" ")

            alt_model["condition"] = {"operation": op, "value": value}

        return alt_model

    def _get_effective_pricing(self, item_id, product_price, offering_info):
        # Search the pricing chosen by the user
        def field_included(pricing, field):
            return field in pricing and len(pricing[field]) > 0

        offering_pricing = None
        for off_price in offering_info["productOfferingPrice"]:
            if off_price["id"] == product_price["productOfferingPrice"]["id"]:
                # Download the product offering price model
                catalog = urlparse(settings.CATALOG)
                price_url = "{}://{}{}/{}".format(
                    catalog.scheme, catalog.netloc, catalog.path + "/productOfferingPrice", off_price["id"]
                )
                offering_pricing = self._download(price_url, "product offering price", off_price["id"])

                break
        else:
            # The given price does not match any from the product offering
            logger.error("Product price does not match any prices in offering")
            raise OrderingError(
                f"The product price included in productOrderItem {item_id} "
                "does not match with any of the prices included in the related offering"
            )

        # Validate that all pricing fields match
        # MATCHING NO LONGER NEEDED ONLY ID IS PROVIDED NOW
        if (
            offering_pricing["priceType"].lower() != product_price["priceType"].lower()
            or (
                field_included(offering_pricing, "unitOfMeasure") and not field_included(product_price, "unitOfMeasure")
            )
            or (
                not field_included(offering_pricing, "unitOfMeasure") and field_included(product_price, "unitOfMeasure")
            )
            or (
                field_included(offering_pricing, "unitOfMeasure")
                and field_included(product_price, "unitOfMeasure")
                and offering_pricing["unitOfMeasure"]["units"].lower() != product_price["unitOfMeasure"].lower()
            )
            or (
                field_included(offering_pricing, "recurringChargePeriodType")
                and not field_included(product_price, "recurringChargePeriod")
            )
            or (
                not field_included(offering_pricing, "recurringChargePeriodType")
                and field_included(product_price, "recurringChargePeriod")
            )
            or (
                field_included(offering_pricing, "recurringChargePeriodType")
                and field_included(product_price, "recurringChargePeriod")
                and offering_pricing["recurringChargePeriodType"].lower()
                != product_price["recurringChargePeriod"].lower()
            )
            or Decimal(offering_pricing["price"]["value"])
            != Decimal(product_price["price"]["taxIncludedAmount"]["value"])
            or offering_pricing["price"]["unit"].lower() != product_price["price"]["taxIncludedAmount"]["unit"].lower()
        ):
            logger.error("Product price does not match any prices in offering")
            raise OrderingError(
                f"The product price included in productOrderItem {item_id} "
                "does not match with any of the prices included in the related offering"
            )

        return product_price

    def _get_mode(self, offering_info):
        if "productOfferingTerm" in offering_info:
            for term in offering_info["productOfferingTerm"]:
                if "name" in term and "description" in term and term["name"].lower() == "procurement":
                    return term["description"].lower()

    def _filter_item(self, item):
        # Get the product offering
        offering_info = self._get_offering_info(item)

        product_price = None
        if "itemTotalPrice" in item and len(item["itemTotalPrice"]) > 0 and "productOfferingPrice" in item["itemTotalPrice"][0]:
            product_price = item["itemTotalPrice"][0]["productOfferingPrice"]

        # Check if the product price has not been included but must
        if product_price is None and len(offering_info["productOfferingPrice"]):
            raise OrderingError(f"The price model has not been included for productOrderItem {item['id']}")

        if product_price is not None:
            o_prices = [op for op in offering_info["productOfferingPrice"] if op["id"] == product_price["id"]]
            if len(o_prices) == 0:
                raise OrderingError(f"The product price included in productOrderItem {item['id']} does not match with any of the prices included in the related offering")

        mode = self._get_mode(offering_info)
        if mode is None:
            mode = "manual"
        elif mode not in ["manual", "payment-automatic", "automatic"]:
            raise OrderingError(f"The procurement mode {mode} is not supported")

        # Download the POP if the offering is not free
        offering_pricing = None
        if product_price is not None:
            catalog = urlparse(settings.CATALOG)
            price_url = "{}://{}{}/{}".format(
                catalog.scheme, catalog.netloc, catalog.path + "/productOfferingPrice", product_price["id"]
            )
            offering_pricing = self._download(price_url, "product offering price", product_price["id"])

        if (offering_pricing is not None and "priceType" in offering_pricing and offering_pricing["priceType"].lower() == "custom") or \
                mode == "manual":

            return None, offering_info, mode

        if product_price is None:
            product_price = {}

        return Contract(
            item_id=item["id"],
            pricing_model=product_price,
            offering=offering_info["id"],
            options=item.get("product", {}).get("productCharacteristic", []),
        ), offering_info, mode

    def _build_contract(self, item):
        # Build offering
        offering, offering_info = self._get_offering(item)

        # Now pricing is taken from a different field
        #
        product_price = None
        if "itemTotalPrice" in item and len(item["itemTotalPrice"]) > 0 and "productOfferingPrice" in item["itemTotalPrice"][0]:
            product_price = item["itemTotalPrice"][0]["productOfferingPrice"]

        # Check if the product price has not been included but must
        if product_price is None and len(offering_info["productOfferingPrice"]) and not offering.is_custom:
            raise OrderingError(f"The price model has not been included for productOrderItem {item['id']}")

        # Build pricing if included
        pricing = {}
        if product_price is not None:
            if offering.is_custom:
                raise OrderingError(f"Custom pricing models are handled externally, please don't include a price in product")

            # model_mapper = {
            #     "one time": "single_payment",
            #     "recurring": "subscription",
            #     "usage": "pay_per_use",
            # }

            # price = self._get_effective_pricing(item["id"], item["product"]["productPrice"][0], offering_info)

            # price_unit = self._parse_price(model_mapper, price)

            # pricing["general_currency"] = price["price"]["taxIncludedAmount"]["unit"]
            # pricing[model_mapper[price["priceType"].lower()]] = [price_unit]

            # # Process price alterations
            # # TODO: Current implementation of the Catalog API does not support price alterations
            # if "productOfferPriceAlteration" in price:
            #     alteration = price["productOfferPriceAlteration"]

            #     # Check type of alteration (discount or fee)
            #     if "discount" in alteration["name"].lower() and "fee" not in alteration["name"].lower():
            #         # Is a discount
            #         pricing["alteration"] = self._parse_alteration(alteration, "discount")

            #     elif "discount" not in alteration["name"].lower() and "fee" in alteration["name"].lower():
            #         # Is a fee
            #         if "priceCondition" not in alteration or not len(alteration["priceCondition"]):
            #             # In this case the alteration is processed as another price
            #             price_unit = self._parse_price(model_mapper, alteration)

            #             if model_mapper[alteration["priceType"].lower()] not in pricing:
            #                 pricing[model_mapper[alteration["priceType"].lower()]] = []

            #             pricing[model_mapper[alteration["priceType"].lower()]].append(price_unit)
            #         else:
            #             pricing["alteration"] = self._parse_alteration(alteration, "fee")
            #     else:
            #         logger.error("Invalid price alteration")
            #         raise OrderingError(
            #             "Invalid price alteration, it is not possible to determine if it is a discount or a fee"
            #         )

        # Calculate the revenue sharing class
        # revenue_class = offering_info["serviceCandidate"]["id"]

        return Contract(
            item_id=item["id"],
            pricing_model=pricing,
            # revenue_class=revenue_class,
            offering=offering.pk,
        )

    def _get_billing_address(self, billing_account):
        # Download BillingAccount
        account = None
        try:
            billing_client = BillingClient()
            account = billing_client.get_billing_account(billing_account["id"])
        except Exception as e:
            logger.error("Error retriving billing account {}".format(str(e)))
            raise OrderingError("Invalid billing account, billing account could not be loaded")

        if not "contact" in account or len(account["contact"]) == 0:
            logger.error("Provided Billing Account does not contain a Postal Address")
            raise OrderingError("Provided Billing Account does not contain a Postal Address")

        postal_addresses = [
            contactMedium
            for contactMedium in account["contact"][0]["contactMedium"]
            if contactMedium["mediumType"] == "PostalAddress"
        ]

        if len(postal_addresses) != 1:
            logger.error("Provided Billing Account does not contain a Postal Address")
            raise OrderingError("Provided Billing Account does not contain a Postal Address")

        postal_address = postal_addresses[0]["characteristic"]

        return {
            "street": postal_address["street1"] + "\n" + postal_address.get("street2", ""),
            "postal": postal_address["postCode"],
            "city": postal_address["city"],
            "province": postal_address["stateOrProvince"],
            "country": postal_address["country"],
        }

    def _terms_found(self, offering_info):
        expected_terms = ["procurement"]
        found = False
        if "productOfferingTerm" in offering_info:
            for term in offering_info["productOfferingTerm"]:
                if term["name"].lower() not in expected_terms:
                    found = True
                    break

        return found

    def _filter_add_items(self, items):
        process_items = []
        for item in items:
            new_contract, offering_info, mode = self._filter_item(item)
            if new_contract is not None:
                process_items.append({
                    'item': item,
                    'offering_info': offering_info,
                    'contract': new_contract,
                    'mode': mode
                })

        return process_items

    def _process_add_items(self, item_info, order, description, terms_accepted):
        order_id = order["id"]
        billing_account = order["billingAccount"]

        terms_found = False
        new_contracts = []
        for item in item_info:
            terms_found = terms_found or self._terms_found(item["offering_info"])
            new_contracts.append(item["contract"])

        if terms_found and not terms_accepted:
            logger.error("Terms and conditions of the offering not accepted")
            raise OrderingError("You must accept the terms and conditions of the offering to acquire it")

        current_org = self._customer.userprofile.current_organization
        order_obj = Order.objects.create(
            order_id=order_id,
            customer=self._customer,
            owner_organization=current_org,
            date=datetime.utcnow(),
            state="pending",
            tax_address=self._get_billing_address(billing_account),
            contracts=new_contracts,
            description=description,
        )

        logger.info("Order model created in the database")

        self.rollback_logger["models"].append(order_obj)

        charging_engine = ChargingEngine(order_obj)
        return charging_engine.resolve_charging(raw_order=order)

    def _get_existing_contract(self, inv_client, product_id):
        # Get product info
        raw_product = inv_client.get_product(product_id)

        # Get related order
        order = Order.objects.get(order_id=raw_product["name"].split("=")[1])

        # Get the existing contract
        contract = order.get_product_contract(product_id)

        # TODO: Process pay per use case
        if "subscription" in contract.pricing_model:
            # Check if there are a pending subscription
            now = datetime.utcnow()

            for subs in contract.pricing_model["subscription"]:
                timedelta = subs["renovation_date"] - now
                if timedelta.days > 0:
                    logger.error(f"Subscription for {product_id} has not expired yet")
                    raise OrderingError(
                        "You cannot modify a product with a recurring payment until the subscription expires"
                    )

        return order, contract

    def _process_modify_items(self, items):
        if len(items) > 1:
            logger.error("Only a modify item is supported per order item")
            raise OrderingError("Only a modify item is supported per order item")

        item = items[0]
        if "product" not in item:
            logger.error("It is required to specify product information in modify order items")
            raise OrderingError("It is required to specify product information in modify order items")

        product = item["product"]

        if "id" not in product:
            logger.error("It is required to provide product id in modify order items")
            raise OrderingError("It is required to provide product id in modify order items")

        client = InventoryClient()
        order, contract = self._get_existing_contract(client, product["id"])

        # Build the new contract
        new_contract = self._build_contract(item)
        if new_contract.pricing_model != {}:
            contract.pricing_model = new_contract.pricing_model
            contract.revenue_class = new_contract.revenue_class

        order.save()

        # The modified item is treated as an initial payment
        charging_engine = ChargingEngine(order)
        return charging_engine.resolve_charging(type_="initial", related_contracts=[contract])

    def _process_delete_items(self, items):
        for item in items:
            if "product" not in item:
                logger.error("It is required to specify product information in delete order items")
                raise OrderingError("It is required to specify product information in delete order items")

            product = item["product"]

            if "id" not in product:
                logger.error("It is required to provide product id in delete order items")
                raise OrderingError("It is required to provide product id in delete order items")

            # Set the contract as terminated
            client = InventoryClient()
            order, contract = self._get_existing_contract(client, product["id"])

            # Suspend the access to the service
            on_product_suspended(order, contract)

            contract.terminated = True
            order.save()

            # Terminate product in the inventory
            client.terminate_product(product["id"])

    @rollback()
    def process_order(self, customer, order, terms_accepted=False):
        """
        Process the different order items included in a given ordering depending on its action field
        :param customer:
        :param order:
        :return:
        """

        self._customer = customer

        # Classify order items by action
        items = {"add": [], "modify": [], "delete": [], "no_change": []}
        for item in order["productOrderItem"]:
            items[item["action"].lower()].append(item)

        if len(items["add"]) and len(items["modify"]):
            logger.error("It is not possible to process add and modify items in the same order")
            raise OrderingError("It is not possible to process add and modify items in the same order")

        # Process order items separately depending on its action. no_change items are not processed
        if len(items["delete"]):
            self._process_delete_items(items["delete"])

        redirection_url = None
        if len(items["modify"]):
            redirection_url = self._process_modify_items(items["modify"])

        # Process add items
        if len(items["add"]):
            description = ""
            if "description" in order:
                description = order["description"]

            if "billingAccount" not in order:
                raise OrderingError("Missing billing account in product order")

            # Filter out the items that are not going to be processed
            process_items = self._filter_add_items(items["add"])
            logger.info("Items are being processed")

            if len(process_items) == 0:
                # No contracts to process, all the items as manual
                return None

            ordering_client = OrderingClient()
            # Update status of items to be processed
            ordering_client.update_items_state(order, "inProgress", items=[item["item"] for item in process_items])
            ordering_client.update_state(order, "inProgress")

            logger.info("Status of orders and items set to inProgress")

            redirection_url = self._process_add_items(process_items, order, description, terms_accepted)

        return redirection_url

    def get_offer_info(self, orderItem):
        catalog = urlparse(settings.CATALOG)

        offering_id = orderItem["productOffering"]["href"]
        offering_url = "{}://{}{}/{}".format(
            catalog.scheme, catalog.netloc, catalog.path + "/productOffering", offering_id
        )

        offering_info = self._download(offering_url, "product offering", orderItem["id"])
        return offering_info

    def create_inventory_product(self, order, orderItem, offering_info, extra_char=None):
        resources = []
        services = []
        inventory_client = InventoryClient()

        product = inventory_client.build_product_model(orderItem, order["id"], order["billingAccount"])
        customer_party = None
        for party in product["relatedParty"]:
            if party["role"].lower() == "customer":
                customer_party = party
                break

        # Instantiate services and resources if needed
        if "productSpecification" in offering_info:
            catalog = urlparse(settings.CATALOG)
            spec_id = offering_info["productSpecification"]["id"]
            spec_url = "{}://{}{}/{}".format(
                catalog.scheme, catalog.netloc, catalog.path + "/productSpecification", spec_id
            )

            spec_info = self._download(spec_url, "product specification", orderItem["id"])

            if "resourceSpecification" in spec_info:
                # Create resources in the inventory
                resources = [
                    inventory_client.create_resource(resource["id"], customer_party)
                    for resource in spec_info["resourceSpecification"]
                ]

            # if "serviceSpecification" in spec_info:
            #     # Create services in the inventory
            #     services = [
            #         inventory_client.create_service(service["id"], customer_party)
            #         for service in spec_info["serviceSpecification"]
            #     ]

        if len(resources) > 0:
            product["realizingResource"] = [{"id": resource, "href": resource} for resource in resources]

        # if len(services) > 0:
        #     product["realizingService"] = [{"id": service, "href": service} for service in services]

        # This cannot work until the Service Intentory API is published
        product["productCharacteristic"].extend([{"name": "service", "value": service}] for service in services)

        if extra_char is not None:
            product["productCharacteristic"].extend(extra_char)

        logger.info("Creating product in the inventory")
        new_product = inventory_client.create_product(product)

        return new_product

    def notify_completed(self, order):
        #####
        ### TODO: We need to refactor this method to create the inventory items when the
        ### Product order is completed for other methods
        #####

        # Process product order items to instantiate the inventory
        # Get order from the database
        order_model = Order.objects.get(order_id=order["id"])

        extra_char = []
        for sale_id in order_model.sales_ids:
            extra_char.append({"name": "paymentPreAuthorizationId", "value": sale_id})

        processed_items = []
        for orderItem in order["productOrderItem"]:
            contracts = [ cnt for cnt in order_model.get_contracts() if cnt.item_id == orderItem["id"] ]
            if len(contracts) == 0:
                continue

            contract = contracts[0]

            # Get product offering
            offering_info = self.get_offer_info(orderItem)

            if "productOfferingTerm" in offering_info:
                mode = 'manual'
                for term in offering_info["productOfferingTerm"]:
                    if term["name"].lower() == "procurement":
                        mode = term["description"].lower()
                        break

                if mode != 'automatic':
                    continue

            new_product = self.create_inventory_product(order, orderItem, offering_info, extra_char=extra_char)

            # Update the billing for automatic procurement
            for inv_id in contract.applied_rates:
                billing_client = BillingClient()
                billing_client.update_customer_rate(inv_id, new_product["id"])

            logger.info("Rates updates")
            self.activate_product(order["id"], new_product)
            processed_items.append(orderItem)

        ordering_client = OrderingClient()
        ordering_client.update_items_state(order, "completed", items=processed_items)

        if len(processed_items) == len(order["productOrderItem"]):
            ordering_client.update_state(order, "completed")

        logger.info("Items completed")

    def process_order_completed(self, order):
        orders = Order.objects.filter(order_id=order["id"])

        order_model = None
        if len(orders) > 0:
            logger.info("Order not found in the database, externally processed or fully manual")
            order_model = orders[0]

        extra_char = []
        if order_model is not None:
            for sale_id in order_model.sales_ids:
                extra_char.append({"name": "paymentPreAuthorizationId", "value": sale_id})

        for orderItem in order["productOrderItem"]:
            contract = None
            if order_model is not None:
                contracts = [ cnt for cnt in order_model.get_contracts() if cnt.item_id == orderItem["id"] ]

                if len(contracts) > 0:
                    contract = contracts[0]

            # Create the product for the orderItem
            offering_info = self.get_offer_info(orderItem)
            new_product = self.create_inventory_product(order, orderItem, offering_info, extra_char=extra_char)

            # Update the billing for automatic procurement
            if contract is not None:
                for inv_id in contract.applied_rates:
                    billing_client = BillingClient()
                    billing_client.update_customer_rate(inv_id, new_product["id"])


    def activate_product(self, order_id, product):
        # Get order
        order = Order.objects.get(order_id=order_id)
        contract = None

        # Search contract
        new_contracts = []
        for cont in order.get_contracts():
            if product["productOffering"]["id"] == cont.offering:
                contract = cont

            new_contracts.append(cont)

        if contract is None:
            return 404, "There is not a contract for the specified product"

        # Save contract id
        contract.product_id = product["id"]

        # Needed to update the contract info with new model
        order.contracts = new_contracts
        order.save()

        # Activate asset
        try:
            on_product_acquired(order, contract)
        except:
            return 400, "The asset has failed to be activated"

        # Change product state to active
        inventory_client = InventoryClient()
        inventory_client.activate_product(product["id"])

        # Create the initial charge in the billing API
        ## TODO: This is going to be created with the applied customer billing rates generated by the billing engine
        if contract.charges is not None and len(contract.charges) == 1:
            billing_client = BillingClient()
            valid_to = None
            # If the initial charge was a subscription is needed to determine the expiration date
            if "subscription" in contract.pricing_model:
                valid_to = contract.pricing_model["subscription"][0]["renovation_date"]

            # billing_client.create_charge(
            #     contract.charges[0],
            #     contract.product_id,
            #     start_date=None,
            #     end_date=valid_to,
            # )
