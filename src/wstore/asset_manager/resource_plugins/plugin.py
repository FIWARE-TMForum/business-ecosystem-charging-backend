# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2017 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S. L.

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
from logging import getLogger

from requests.exceptions import HTTPError

from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.charging_engine.accounting.usage_client import UsageClient

logger = getLogger("wstore.default_logger")


class Plugin:
    def __init__(self, plugin_model):
        self._model = plugin_model

    def on_pre_product_spec_validation(self, provider, asset_t, media_type, url):
        pass

    def on_post_product_spec_validation(self, provider, asset):
        pass

    def on_pre_service_spec_attachment(self, asset, asset_t, service_spec):
        pass

    def on_post_service_spec_attachment(self, asset, asset_t, service_spec):
        pass

    def on_pre_service_spec_validation(self, provider, asset_t, media_type, url):
        pass

    def on_post_service_spec_validation(self, provider, asset):
        pass

    def on_pre_service_spec_upgrade(self, asset, asset_t, service_spec):
        pass

    def on_post_service_spec_upgrade(self, asset, asset_t, service_spec):
        pass

    def on_pre_product_offering_validation(self, asset, product_offering):
        pass

    def on_post_product_offering_validation(self, asset, product_offering):
        pass

    def on_product_acquisition(self, asset, contract, order):
        pass

    def on_product_suspension(self, asset, contract, order):
        pass

    def get_usage_specs(self):
        return []

    def _get_usage_characteristic(self, name, description, type_):
        return {
            "name": name,
            "description": description,
            "configurable": False,
            "usageSpecCharacteristicValue": [{"valueType": type_, "default": False, "value": ""}],
        }

    def configure_usage_spec(self):
        logger.debug(f"Configuring usage specifications for {self._model}")

        # Build common usage spec
        specification_template = {
            "usageSpecCharacteristic": [
                self._get_usage_characteristic("orderId", "Order identifier", "string"),
                self._get_usage_characteristic("productId", "Product identifier", "string"),
                self._get_usage_characteristic("correlationNumber", "Accounting correlation number", "number"),
                self._get_usage_characteristic("unit", "Accounting unit", "string"),
                self._get_usage_characteristic("value", "Accounting value", "number"),
            ]
        }

        usage_specs = self.get_usage_specs()
        usage_client = UsageClient()

        # Create usage specifications for supported units
        for spec in usage_specs:
            if "name" not in spec or "description" not in spec:
                logger.error("`name` or `description` not in spec")
                raise PluginError("Invalid product specification configuration, must include name and description")

            logger.debug(f"Creating usage specifications for {spec['name']}")

            # Check if the usage spec is already registered
            if "usage" not in self._model.options or spec["name"].lower() not in self._model.options["usage"]:
                usage_spec = deepcopy(specification_template)
                usage_spec["name"] = spec["name"]
                usage_spec["description"] = spec["description"]
                created_spec = usage_client.create_usage_spec(usage_spec)

                if "usage" not in self._model.options:
                    self._model.options["usage"] = {}

                # Save the spec href to be used in usage documents
                self._model.options["usage"][spec["name"].lower()] = created_spec["href"]
                self._model.save()
                logger.debug("Usage specifications created")

    def remove_usage_specs(self):
        logger.debug(f"Removing usage specifications for {self._model}")

        if "usage" in self._model.options:
            try:
                usage_client = UsageClient()

                for unit, href in self._model.options["usage"].items():
                    spec_id = href.split("/")[-1]
                    usage_client.delete_usage_spec(spec_id)
            except HTTPError as e:
                if e.response.status_code != 404:
                    raise e

    def get_pending_accounting(self, asset, contract, order):
        return []

    def on_usage_refresh(self, asset, contract, order):
        logger.debug(f"Running usage refresh hook for {self._model}")

        if not self._model.pull_accounting:
            return

        pending_accounting, last_usage = self.get_pending_accounting(asset, contract, order)
        usage_template = {
            "type": "event",
            "status": "Received",
            "usageCharacteristic": [
                {"name": "orderId", "value": order.order_id},
                {"name": "productId", "value": contract.product_id},
            ],
            "relatedParty": [
                {
                    "role": "customer",
                    "id": order.owner_organization.name,
                    "href": order.owner_organization.get_party_url(),
                }
            ],
        }

        usage_client = UsageClient()
        for usage_record in pending_accounting:
            if "date" not in usage_record or "unit" not in usage_record or "value" not in usage_record:
                raise PluginError("Invalid usage record, it must include date, unit and value")

            # Generate a TMForum usage document for each usage record
            usage = deepcopy(usage_template)

            usage["date"] = usage_record["date"]

            usage["usageSpecification"] = {
                "href": self._model.options["usage"][usage_record["unit"]],
                "name": usage_record["unit"],
            }

            usage["usageCharacteristic"].append({"name": "unit", "value": usage_record["unit"]})

            usage["usageCharacteristic"].append({"name": "correlationNumber", "value": contract.correlation_number})

            usage["usageCharacteristic"].append({"name": "value", "value": usage_record["value"]})

            usage_doc = usage_client.create_usage(usage)
            # All the  information is known so the document is directly created in Guided state
            usage_client.update_usage_state(usage_doc["id"], "Guided")

            contract.correlation_number += 1
            order.save()

        if last_usage is not None:
            contract.last_usage = last_usage
            order.save()
