# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid
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

from functools import wraps

from django.conf import settings
from logging import getLogger

from wstore.asset_manager.errors import ServiceError
from wstore.asset_manager.resource_plugins.resolver import CatalogResolver
from wstore.models import Organization, ResourcePlugin
from wstore.ordering.inventory_client import InventoryClient

logger = getLogger("wstore.default_logger")


def _get_plugin_model(category_id):
    plugins = list(ResourcePlugin.objects.filter(category_id=category_id))

    if len(plugins) > 1:
        raise ServiceError("The service category resolves to more than one installed plugin")

    return plugins[0] if plugins else None


def load_plugin_module(service_spec):
    entries = service_spec.get("specCharacteristic")
    if not isinstance(entries, list):
        return None

    service_types = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and entry["name"].strip().lower() == "service type"
    ]

    if not service_types:
        return None

    if len(service_types) != 1:
        raise ServiceError("The service specification must contain exactly one Service Type characteristic")

    values = service_types[0].get("characteristicValueSpecification")

    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
        raise ServiceError("The Service Type characteristic must contain exactly one value")

    category_id = values[0].get("value")

    return _load_category_plugin(category_id)


def load_service_plugin_module(service):
    """Resolve an activation plugin from the inventory service's own characteristics."""
    entries = service.get("serviceCharacteristic")
    if not isinstance(entries, list):
        return None

    service_types = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and entry["name"].strip().lower() == "service type"
    ]

    if not service_types:
        return None

    if len(service_types) != 1:
        raise ServiceError("The inventory service must contain exactly one Service Type characteristic")

    return _load_category_plugin(service_types[0].get("value"))


def _load_category_plugin(category_id):
    if not isinstance(category_id, str) or not category_id.strip():
        raise ServiceError("Service Type must contain a non-empty service category id string")

    plugin_model = _get_plugin_model(category_id=category_id)

    return _load_plugin_model(plugin_model) if plugin_model is not None else None


def _load_plugin_model(plugin_model):
    module = plugin_model.module
    module_class_name = module.split(".")[-1]
    module_package = module.partition("." + module_class_name)[0]

    module_class = getattr(
        __import__(module_package, globals(), locals(), [module_class_name], 0),
        module_class_name,
    )

    logger.debug("Loaded plugin module %s", module)
    return module_class(plugin_model)


def _get_plugins(associations):
    plugins = []

    for service_spec, product_spec in associations:
        plugin = load_plugin_module(service_spec=service_spec)

        if plugin is not None:
            plugins.append((plugin, service_spec, product_spec))

    return plugins


def on_product_spec_validation(provider, product_spec):
    associations = CatalogResolver().product_services(product_spec)

    for plugin, service_spec, product in _get_plugins(associations):
        plugin.on_product_spec_validation(provider, service_spec, product)


def on_product_offering_validation(func):
    @wraps(func)
    def wrapper(self, provider, product_offering):
        associations = CatalogResolver().offering_services(product_offering)
        plugins = _get_plugins(associations)

        for plugin, service_spec, product_spec in plugins:
            plugin.on_pre_product_offering_validation(provider, service_spec, product_spec, product_offering)

        result = func(self, provider, product_offering)

        for plugin, service_spec, product_spec in plugins:
            plugin.on_post_product_offering_validation(provider, service_spec, product_spec, product_offering)

        return result

    return wrapper


def _get_product_organization(product, role):
    party_ids = {
        party["id"]
        for party in product.get("relatedParty", [])
        if isinstance(party, dict)
        and isinstance(party.get("role"), str)
        and party["role"].lower() == role.lower()
        and isinstance(party.get("id"), str)
        and party["id"].strip()
    }

    if len(party_ids) != 1:
        raise ServiceError("The inventory product must identify one organization for role " + role)

    return Organization.objects.get(actor_id=party_ids.pop())


def on_product_activation(product, order, contract=None):
    """Dispatch product activation to its service plugins without interrupting purchase completion."""
    references = product.get("realizingService", [])

    if not isinstance(references, list):
        logger.error(
            "Cannot notify activation for product %s: realizingService must be a list", product.get("id")
        )
        return

    inventory = InventoryClient()
    organizations = None

    for reference in references:
        try:
            if (
                not isinstance(reference, dict)
                or not isinstance(reference.get("id"), str)
                or not reference["id"].strip()
            ):
                raise ServiceError("Each realizingService reference must contain a service id")

            service = inventory.get_service(reference["id"])

            if not isinstance(service, dict) or service.get("id") != reference["id"]:
                raise ServiceError("Invalid inventory service reference: " + reference["id"])

            plugin = load_service_plugin_module(service)

            if plugin is not None:
                if organizations is None:
                    organizations = (
                        _get_product_organization(product, settings.PROVIDER_ROLE),
                        _get_product_organization(product, settings.CUSTOMER_ROLE),
                    )
                provider, buyer = organizations
                plugin.on_service_activation(provider, buyer, service, product, order, contract)
        except Exception:
            # Payment has completed: a plugin notification must not block the purchase.
            logger.exception(
                "Service activation notification failed for order %s, product %s, service %s",
                order.get("id"),
                product.get("id"),
                reference.get("id") if isinstance(reference, dict) else None,
            )


def process_product_notification(order, contract, type_):
    # Purchased-service dispatch is integrated in its own lifecycle step.
    pass


def on_product_suspended(order, contract):
    process_product_notification(order, contract, "suspend")


def on_usage_refreshed(order, contract):
    process_product_notification(order, contract, "usage")


def on_service_spec_validation(func):
    @wraps(func)
    def wrapper(self, provider, service_spec):
        plugin = load_plugin_module(service_spec=service_spec)

        if plugin is None:
            return

        plugin.on_pre_service_spec_validation(provider, service_spec)

        result = func(self, provider, service_spec, plugin._model)

        plugin.on_post_service_spec_validation(provider, service_spec)

        return result

    return wrapper
