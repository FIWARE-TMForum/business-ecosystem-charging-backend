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

from logging import getLogger

import requests
from django.conf import settings

from wstore.asset_manager.resource_plugins.plugin_error import PluginError
from wstore.charging_engine.accounting.usage_client import UsageClient
from wstore.charging_engine.utils import to_utc_z, utc_z_to_dt
from wstore.ordering.inventory_client import InventoryClient
from wstore.store_commons.utils.url import get_service_url
from wstore.store_commons.utils.party import normalize_party_ref, get_operator_party_roles

logger = getLogger("wstore.default_logger")


class Plugin:
    """Shared plugin configuration and accounting utilities."""

    def __init__(self, plugin_model):
        self._model = plugin_model

    def get_usage_specs(self):
        """Declare supported metric templates for future provider tooling.

        These definitions do not create, own or delete usage specifications.
        Providers create their specifications and reference them from usage prices.
        """
        return []

    def _get_usage_prices(self, product):
        """Group billed metrics within each provider-selected usage specification."""
        inventory = InventoryClient()
        prices = {}
        for price in product.get("productPrice", []):
            component = inventory.get_price_component(price["productOfferingPrice"]["id"])

            if component.get("isBundle", False) or component.get("priceType", "").lower() != "usage":
                continue

            metric = component.get("unitOfMeasure", {}).get("units")
            specification_id = component.get("usageSpecId")

            if not isinstance(metric, str) or not metric.strip():
                raise PluginError("Usage prices must identify a metric in unitOfMeasure.units")

            if not isinstance(specification_id, str) or not specification_id.strip():
                raise PluginError("Usage prices must identify a provider usage specification in usageSpecId")

            prices.setdefault(specification_id, set()).add(metric)
        return prices

    def _get_usage_specification(self, specification_id):
        url = get_service_url("usage", "usageSpecification/" + specification_id)
        response = requests.get(url, verify=settings.VERIFY_REQUESTS, timeout=30)
        response.raise_for_status()
        specification = response.json()
        if not isinstance(specification, dict) or specification.get("id") != specification_id:
            raise PluginError("The usage API returned an invalid usage specification")
        return specification

    def _usage_characteristics(self, specification, record):
        """Validate the metric's decimal value and emit it as a string."""
        from decimal import Decimal, InvalidOperation

        definitions = specification.get("specCharacteristic")
        if not isinstance(definitions, list):
            raise PluginError("The usage specification must declare its characteristics")

        metric = record["unit"]
        matching = [
            definition for definition in definitions
            if isinstance(definition, dict) and definition.get("name") == metric
        ]
        if len(matching) != 1:
            raise PluginError("The usage specification must declare exactly one accounting metric: " + metric)
        value = record["value"]
        try:
            numeric_value = Decimal(str(value))
            if not numeric_value.is_finite() or numeric_value < 0:
                raise ValueError
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PluginError("Accounting values must be non-negative finite numbers or numeric strings") from exc

        return [{"name": metric, "value": str(value)}]

    def _build_usage_document(self, usage_date, specification, product, record):
        usage_client = UsageClient()

        reference = {key: specification[key] for key in ("id", "href", "name") if key in specification}
        purchase_roles = {settings.PROVIDER_ROLE.lower(), settings.CUSTOMER_ROLE.lower()}
        related_parties = [
            normalize_party_ref(party)
            for party in product["relatedParty"]
            if isinstance(party.get("role"), str) and party["role"].lower() in purchase_roles
        ]
        related_parties.extend(get_operator_party_roles())
        usage = {
            "usageType": "event",
            "status": "received",
            "usageDate": usage_date,
            "usageSpecification": reference,
            "usageCharacteristic": self._usage_characteristics(specification, record),
            "ratedProductUsage": [{"productRef": {"id": product["id"]}}],
            "relatedParty": related_parties,
        }
        usage_client.create_usage(usage)

    def _refresh_usage(self, instance, product, contract, order):
        """Publish date/unit/value accounting records against provider specifications.

        The unit names the measured characteristic and must match the usage price's
        unitOfMeasure.units. Specifications are read from that price's usageSpecId;
        legacy plugin.options['usage'] mappings are not used.
        """
        logger.debug("Running usage refresh hook for %s", self._model)
        if not self._model.pull_accounting:
            return

        pending_accounting = self.get_pending_accounting(instance, contract, order)
        prices = None
        specifications = {}

        for record in pending_accounting:
            if not isinstance(record, dict) or not all(key in record for key in ("date", "unit", "value")):
                raise PluginError("Invalid usage record, it must include date, unit and value")

            metric = record["unit"]
            if not isinstance(metric, str) or not metric.strip():
                raise PluginError("Accounting units must be non-empty metric names")

            try:
                usage_date = to_utc_z(utc_z_to_dt(record["date"]))
            except (AttributeError, TypeError, ValueError) as exc:
                raise PluginError("Accounting dates must be ISO 8601 strings") from exc

            if prices is None:
                prices = self._get_usage_prices(product)

            matching = {specification_id for specification_id, metrics in prices.items() if metric in metrics}
            if not matching:
                raise PluginError("Accounting metric does not match a purchased usage specification: " + metric)

            if len(matching) == 1:
                specification_id = next(iter(matching))
            else:
                specification_id = record.get("usageSpecId")
                if not isinstance(specification_id, str) or specification_id not in matching:
                    raise PluginError(
                        "Accounting record must include a matching usageSpecId when multiple specifications "
                        "declare metric: " + metric
                    )

            if specification_id not in specifications:
                specifications[specification_id] = self._get_usage_specification(specification_id)

            specification = specifications[specification_id]
            self._build_usage_document(usage_date, specification, product, record)


class ServicePlugin(Plugin):
    """Service specification and inventory lifecycle interface."""

    def on_pre_service_spec_creation(self, provider, service_spec):
        """Validate a proposed service specification before the TMForum write."""
        pass

    def on_post_service_spec_creation(self, provider, service_spec):
        """Handle the created TMForum specification; failures do not undo creation."""
        pass

    def on_pre_service_spec_update(self, provider, service_spec):
        """Validate an ordinary specification update before the TMForum write."""
        pass

    def on_post_service_spec_update(self, provider, service_spec):
        """Handle the updated TMForum specification; failures do not undo the update."""
        pass

    def on_pre_service_spec_upgrade(self, provider, service_spec):
        """Validate an update to the existing service specification."""
        pass

    def on_post_service_spec_upgrade(self, provider, service_spec):
        """Notify successful catalog update of the upgraded service specification."""
        pass

    def on_pre_product_spec_creation(self, provider, service_spec, product_spec):
        """Validate before the TMForum write."""
        pass

    def on_post_product_spec_creation(self, provider, service_spec, product_spec):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_pre_product_spec_update(self, provider, service_spec, product_spec):
        """Validate before the TMForum write."""
        pass

    def on_post_product_spec_update(self, provider, service_spec, product_spec):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_pre_product_offering_creation(self, provider, service_spec, product_spec, product_offering):
        """Validate before the TMForum write."""
        pass

    def on_post_product_offering_creation(self, provider, service_spec, product_spec, product_offering):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_pre_product_offering_update(self, provider, service_spec, product_spec, product_offering):
        """Validate before the TMForum write."""
        pass

    def on_post_product_offering_update(self, provider, service_spec, product_spec, product_offering):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_service_activation(self, provider, buyer, service, product, order, contract=None):
        """Provision or reconfigure the service for automatic add/modify completion.

        Use the updated product and order action to handle existing provisioning
        safely. Raise on failure to prevent product activation and completion.
        """
        pass

    def on_service_termination(self, provider, buyer, service, product, order, contract=None):
        """Notify service termination; notification failure does not block termination."""
        pass

    def on_service_renewal(self, provider, buyer, service, product, order, contract=None, *, customer_bill_id):
        """Notify settled renewal; notification failure does not block processing."""
        pass

    def get_pending_accounting(self, service, contract, order):
        """Return date/unit/value accounting records for this instance."""
        return []

    def on_usage_refresh(self, provider, buyer, service, product, order, contract=None):
        """Publish accounting using the supplied purchased-product context."""

        self._refresh_usage(service, product, contract, order)


class ResourcePlugin(Plugin):
    """Resource specification and inventory lifecycle interface."""

    def on_pre_resource_spec_creation(self, provider, resource_spec):
        """Validate a proposed resource specification before the TMForum write."""
        pass

    def on_post_resource_spec_creation(self, provider, resource_spec):
        """Handle the created TMForum specification; failures do not undo creation."""
        pass

    def on_pre_resource_spec_update(self, provider, resource_spec):
        """Validate an ordinary specification update before the TMForum write."""
        pass

    def on_post_resource_spec_update(self, provider, resource_spec):
        """Handle the updated TMForum specification; failures do not undo the update."""
        pass

    def on_pre_resource_spec_upgrade(self, provider, resource_spec):
        """Validate an update to the existing resource specification."""
        pass

    def on_post_resource_spec_upgrade(self, provider, resource_spec):
        """Notify successful catalog update of the upgraded resource specification."""
        pass

    def on_pre_product_spec_creation(self, provider, resource_spec, product_spec):
        """Validate before the TMForum write."""
        pass

    def on_post_product_spec_creation(self, provider, resource_spec, product_spec):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_pre_product_spec_update(self, provider, resource_spec, product_spec):
        """Validate before the TMForum write."""
        pass

    def on_post_product_spec_update(self, provider, resource_spec, product_spec):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_pre_product_offering_creation(self, provider, resource_spec, product_spec, product_offering):
        """Validate before the TMForum write."""
        pass

    def on_post_product_offering_creation(self, provider, resource_spec, product_spec, product_offering):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_pre_product_offering_update(self, provider, resource_spec, product_spec, product_offering):
        """Validate before the TMForum write."""
        pass

    def on_post_product_offering_update(self, provider, resource_spec, product_spec, product_offering):
        """Handle the persisted TMForum document; failures do not undo the write."""
        pass

    def on_resource_activation(self, provider, buyer, resource, product, order, contract=None):
        """Provision or reconfigure the resource for automatic add/modify completion.

        Use the updated product and order action to handle existing provisioning
        safely. Raise on failure to prevent product activation and completion.
        """
        pass

    def on_resource_termination(self, provider, buyer, resource, product, order, contract=None):
        """Notify resource termination; notification failure does not block termination."""
        pass

    def on_resource_renewal(self, provider, buyer, resource, product, order, contract=None, *, customer_bill_id):
        """Notify settled renewal; notification failure does not block processing."""
        pass

    def get_pending_accounting(self, resource, contract, order):
        """Return date/unit/value accounting records for this instance."""
        return []

    def on_usage_refresh(self, provider, buyer, resource, product, order, contract=None):
        """Publish accounting using the supplied purchased-product context."""

        self._refresh_usage(resource, product, contract, order)
